# =============================================================================
# forensic_api/support_presence.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Verdrahtet den SSE-Lebenszyklus des Support-Modus (Build 312) mit der
#   Praesenz-Erfassung aus Build 311 (management.support_sessions). Kapselt
#   den gesamten Zustand und die dedizierte coordinator.db-Direktverbindung,
#   damit forensic_api/events.py nur noch schlanke Aufrufe (begin/heartbeat/
#   resume/end) macht.
#
# Warum eine eigene Klasse (Grundregel 10):
#   - Die Session-Bindung (SSE-client_id -> support_sessions.id) und die
#     dedizierte Schreibverbindung sind ein eigenstaendiges Belang mit eigenem
#     Lebenszyklus. Gekapselt ist sie ohne echten SSE-Stream unit-testbar
#     (siehe tests/test_events_support_wiring.py).
#   - events.py bleibt frei von coordinator.db-Schreibdetails.
#
# Architektur (Beleg: Bauplan B7 v0.6 §6.5, mc 2026-07-01):
#   Der Support-Webserver ist der ERSTE Schreiber von coordinator.db aus dem
#   Request-Pfad. Er nutzt dafuer eine DEDIZIERTE Direkt-Verbindung
#   (isolation_level=None, WAL) — GETRENNT von der ATTACHed-'cdb'-Leseverbindung
#   des DatabaseBundle. In dieser Direktverbindung sind support_sessions,
#   audit_log und investigators HAUPT-Tabellen (ohne 'cdb.'-Praefix), genau wie
#   SupportSessionsRepo/CoordinatorWriter/AuditLog es erwarten.
#
# Grace-gekoppeltes Ende (mc 2026-07-01, Entscheidung 1):
#   end() wird NICHT sofort beim Verbindungsabriss aufgerufen, sondern erst nach
#   Ablauf der Grace-Period (analog Lock-System in events.py). Reconnectet der
#   Supporter innerhalb der Grace-Period (RESUMING), wird die BESTEHENDE Sitzung
#   per resume() weitergefuehrt — es entsteht KEIN spurioses ENDED/STARTED-Paar
#   in der Audit-Kette (die sonst bei jedem Verbindungs-Blip fluten wuerde).
#
# Trennung Beleg vs. Praesenz (Build 311):
#   support_sessions ist FLUECHTIGE Praesenz (prunebar). Der permanente
#   Zugriffsbeleg (wer sah wann welchen Fall) lebt im audit_log ueber
#   SUPPORT_SESSION_STARTED / _ENDED. Heartbeats werden NICHT auditiert.
#
# Robustheit:
#   Praesenz-Bookkeeping darf den Ermittler-/Support-Arbeitsplatz NIE
#   stoeren. Jede DB-Interaktion ist gekapselt; Fehler werden GELOGGT (kein
#   stilles Versagen, Grundregel 1) aber nicht nach oben geworfen — ein
#   Sitzungs-Bookkeeping-Fehler bricht weder den SSE-Stream noch den
#   Lock-Grace-Pfad ab.
#
# Version: v0.7.312 · Build: 312 · 2026-07-02
# Beleg: Bauplan B7 v0.6 §6/§7, Projektgespraech 2026-07-01, mc 2026-07-01.
# =============================================================================

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Dict, List, Optional, Union

from core.logger import get_logger
from management.audit.audit_log import AuditLog
from management.gateway.coordinator_writer import CoordinatorWriter
from management.support_sessions.support_sessions_repo import (
    SupportSessionsError,
    SupportSessionsRepo,
)

logger = get_logger(__name__)

# Verbindungs-Timeout fuer coordinator.db (SMB-tolerant, analog ConnectionManager).
_CONNECT_TIMEOUT_SEC = 10.0
# busy_timeout in Millisekunden (WAL-Schreiberserialisierung auf SMB).
_BUSY_TIMEOUT_MS = 10000


class SupportPresenceBinder:
    """
    Bindet SSE-Support-Streams an support_sessions-Zeilen und schreibt die
    zugehoerigen Audit-Belege ueber das CoordinatorWriter-Gateway.

    Eine Instanz je Support-Webserver (ein Supporter, ein Fall). Mehrere
    gleichzeitige SSE-Streams (z. B. mehrere Fenster desselben Supporters)
    werden ueber die client_id auseinandergehalten; jeder Stream ist eine
    eigene Praesenz-Sitzung.

    Thread-Sicherheit:
        Alle oeffentlichen Methoden serialisieren ueber _lock. Die
        SQLite-Verbindung ist mit check_same_thread=False geoeffnet, da
        begin()/heartbeat() im SSE-Stream-Thread, end() aber im
        Grace-Timer-Thread laufen. Zu jedem Zeitpunkt haelt genau ein Thread
        das Lock — es gibt keine echte Nebenlaeufigkeit auf der Verbindung.
    """

    def __init__(
        self,
        coordinator_db_path: Union[str, Path],
        user_id: int,
        supporter_id: Optional[int],
        *,
        stale_sec: int = 30,
        prune_older_than_sec: int = 3600,
    ) -> None:
        """
        Oeffnet die dedizierte coordinator.db-Direktverbindung und baut die
        Repo-Kette (AuditLog -> CoordinatorWriter -> SupportSessionsRepo).

        Der Aufrufer (events.py) MUSS zuvor sichergestellt haben, dass
        coordinator_db_path existiert (sonst legt sqlite3 eine leere DB an,
        in der die Tabellen fehlen -> Repo-Fehler beim ersten Write).
        """
        self._user_id = int(user_id)
        self._supporter_id = supporter_id  # darf None sein (System/unbekannt)
        self._stale_sec = int(stale_sec)
        self._prune_older_than_sec = int(prune_older_than_sec)

        # client_id -> session_id (support_sessions.id) der LAUFENDEN Sitzung.
        self._by_client: Dict[str, int] = {}
        self._lock = threading.Lock()
        self._pruned = False  # prune() einmalig beim ersten begin()

        # Dedizierte Direktverbindung. isolation_level=None (Autocommit) ist
        # Pflicht: CoordinatorWriter steuert Transaktionen explizit ueber
        # BEGIN IMMEDIATE/COMMIT/ROLLBACK.
        self._con: sqlite3.Connection = sqlite3.connect(
            str(coordinator_db_path),
            timeout=_CONNECT_TIMEOUT_SEC,
            check_same_thread=False,
            isolation_level=None,
        )
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA busy_timeout=%d" % _BUSY_TIMEOUT_MS)

        audit = AuditLog(self._con)
        writer = CoordinatorWriter(self._con, audit)
        self._repo = SupportSessionsRepo(self._con, writer)

        logger.info(
            "SupportPresenceBinder bereit: user_id=%d supporter_id=%s db='%s'",
            self._user_id, self._supporter_id, coordinator_db_path,
        )

    # ------------------------------------------------------------------ Start
    def begin(self, client_id: str) -> Optional[int]:
        """
        Startet eine neue Praesenz-Sitzung fuer diese SSE-client_id und schreibt
        SUPPORT_SESSION_STARTED. Gibt die session_id zurueck (oder None bei
        Fehler — geloggt, nicht geworfen).

        Beim allerersten begin() wird einmalig prune() aufgerufen, um verwaiste
        Alt-Sitzungen (z. B. nach hartem Serverabbruch) zu raeumen.
        """
        with self._lock:
            self._prune_once_locked()
            # Doppel-begin fuer dieselbe client_id vermeiden (Idempotenz-Schutz).
            existing = self._by_client.get(client_id)
            if existing is not None:
                logger.debug(
                    "begin(): client_id=%s hat bereits Sitzung %d — kein Neustart",
                    client_id, existing,
                )
                return existing
            try:
                session_id = self._repo.start(
                    self._user_id,
                    self._supporter_id,
                    actor_id=self._supporter_id,
                )
            except Exception as exc:  # noqa: BLE001 — bewusst breit, siehe Modul-Doku
                logger.error(
                    "begin(): Sitzungsstart fehlgeschlagen (user_id=%d): %s",
                    self._user_id, exc,
                )
                return None
            self._by_client[client_id] = session_id
            logger.info(
                "Support-Sitzung gestartet: client_id=%s -> session_id=%d",
                client_id, session_id,
            )
            return session_id

    # -------------------------------------------------------------- Heartbeat
    def heartbeat(self, client_id: str) -> bool:
        """
        Aktualisiert last_heartbeat der zur client_id gehoerenden Sitzung.
        KEIN Audit. Gibt True zurueck, wenn eine laufende Sitzung getroffen
        wurde; False, wenn keine Bindung besteht oder die Sitzung bereits
        beendet ist.
        """
        with self._lock:
            session_id = self._by_client.get(client_id)
            if session_id is None:
                return False
            try:
                return self._repo.heartbeat(session_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "heartbeat(): fehlgeschlagen (session_id=%d): %s",
                    session_id, exc,
                )
                return False

    # ----------------------------------------------------------------- Resume
    def resume(self, old_client_id: str, new_client_id: str) -> bool:
        """
        RESUMING (Verbindungs-Blip geheilt): haengt die BESTEHENDE Sitzung der
        alten client_id auf die neue client_id um — OHNE neues start() und OHNE
        neuen Audit-Eintrag. Setzt einen frischen Heartbeat, damit die Sitzung
        nicht als stale gilt. Gibt True zurueck, wenn eine Sitzung uebernommen
        wurde; False, wenn zur alten client_id keine (mehr) bestand (dann muss
        der Aufrufer per begin() neu starten).
        """
        with self._lock:
            session_id = self._by_client.pop(old_client_id, None)
            if session_id is None:
                logger.debug(
                    "resume(): keine Sitzung fuer alte client_id=%s "
                    "(Grace bereits abgelaufen?)",
                    old_client_id,
                )
                return False
            self._by_client[new_client_id] = session_id
            # Frischer Heartbeat — best effort, Fehler nur loggen.
            try:
                self._repo.heartbeat(session_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "resume(): Heartbeat nach Umhaengen fehlgeschlagen "
                    "(session_id=%d): %s", session_id, exc,
                )
            logger.info(
                "Support-Sitzung RESUMING: session_id=%d %s -> %s",
                session_id, old_client_id, new_client_id,
            )
            return True

    # -------------------------------------------------------------------- End
    def end(self, client_id: str) -> Optional[int]:
        """
        Beendet die zur client_id gehoerende Sitzung (setzt ended_at) und
        schreibt SUPPORT_SESSION_ENDED. Idempotent: unbekannte/bereits beendete
        Bindung -> None (kein zweiter Beleg). Gibt sonst die audit-seq zurueck.

        Wird von events.py NACH Ablauf der Grace-Period aufgerufen (mc:
        Entscheidung 1). Alle Fehler werden geloggt, nicht geworfen — der
        Grace-Expiry-Pfad (Lock-Freigabe) darf nie abbrechen.
        """
        with self._lock:
            session_id = self._by_client.pop(client_id, None)
            if session_id is None:
                return None
            try:
                seq = self._repo.end(session_id, actor_id=self._supporter_id)
            except SupportSessionsError as exc:
                # z. B. Race: zwischenzeitlich beendet -> kein zweiter Beleg.
                logger.warning(
                    "end(): Sitzung %d nicht sauber beendet: %s",
                    session_id, exc,
                )
                return None
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "end(): unerwarteter Fehler (session_id=%d): %s",
                    session_id, exc,
                )
                return None
            logger.info(
                "Support-Sitzung beendet: client_id=%s session_id=%d (audit seq=%s)",
                client_id, session_id, seq,
            )
            return seq

    # --------------------------------------------------------------- Introspektion
    def active_client_ids(self) -> List[str]:
        """Liste der aktuell gebundenen SSE-client_ids (fuer Tests/Diagnose)."""
        with self._lock:
            return list(self._by_client.keys())

    def session_id_for(self, client_id: str) -> Optional[int]:
        """session_id einer client_id oder None (fuer Tests/Diagnose)."""
        with self._lock:
            return self._by_client.get(client_id)

    # ------------------------------------------------------------------ Cleanup
    def close(self) -> None:
        """
        Beendet alle noch gebundenen Sitzungen (best effort) und schliesst die
        Verbindung. Wird beim Serverende aufgerufen, damit keine Sitzung als
        'aktiv' zurueckbleibt.
        """
        with self._lock:
            for client_id, session_id in list(self._by_client.items()):
                try:
                    self._repo.end(session_id, actor_id=self._supporter_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "close(): Sitzung %d nicht sauber beendet: %s",
                        session_id, exc,
                    )
            self._by_client.clear()
            try:
                self._con.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning("close(): Verbindung nicht sauber geschlossen: %s", exc)
            logger.info("SupportPresenceBinder geschlossen (user_id=%d).", self._user_id)

    # ----------------------------------------------------------------- intern
    def _prune_once_locked(self) -> None:
        """
        Raeumt einmalig verwaiste Alt-Sitzungen. Aufrufer haelt _lock.
        Fehler werden nur geloggt (prune ist best effort, kein Beleg).
        """
        if self._pruned:
            return
        self._pruned = True
        try:
            removed = self._repo.prune(self._prune_older_than_sec)
            if removed:
                logger.info(
                    "prune(): %d verwaiste Support-Sitzung(en) entfernt "
                    "(aelter als %ds).", removed, self._prune_older_than_sec,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("prune(): fehlgeschlagen: %s", exc)

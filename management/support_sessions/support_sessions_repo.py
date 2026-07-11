# =============================================================================
# management/support_sessions/support_sessions_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Zugriffsschicht auf 'support_sessions' in coordinator.db. Erfasst LIVE-
#   Support-Sitzungen (ein is_support-Helfer schaut mit in einen Fall):
#     - start()      — Sitzung anlegen  -> AUDIT SUPPORT_SESSION_STARTED
#     - heartbeat()  — Lebenszeichen    -> KEIN Audit (nur last_heartbeat)
#     - end()        — Sitzung beenden  -> AUDIT SUPPORT_SESSION_ENDED
#     - get_active() — aktive Sitzungen eines Falls (Read, für den Indikator)
#     - prune()      — flüchtige Alt-Zeilen entfernen (KEIN Audit)
#
# Trennung Beleg vs. Präsenz:
#   support_sessions ist FLÜCHTIGER Präsenzzustand (prunebar). Der permanente
#   Zugriffsbeleg (wer sah wann welchen Fall) lebt im audit_log über Start/Ende.
#   Heartbeats werden bewusst NICHT auditiert (sonst flutet die Kette).
#
# Schreiben läuft über das CoordinatorWriter-Gateway:
#   - start/end: audited_write (Write + Audit atomar)
#   - heartbeat/prune: writer.transaction() (BEGIN IMMEDIATE/COMMIT/ROLLBACK)
#     OHNE Audit-Eintrag.
#   Die Verbindung muss (wie beim Gateway) isolation_level=None (Autocommit)
#   sein, damit die expliziten Transaktionen greifen.
#
# Beleg: Bauplan B7 v0.5 §6, Projektgespräch 2026-07-01, mc 2026-07-01.
# Version: v0.7.311 · Build: 311 · 2026-07-01
# =============================================================================

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.gateway.coordinator_writer import CoordinatorWriter

logger = logging.getLogger(__name__)


class SupportSessionsError(Exception):
    """Fachlicher Fehler (z. B. unbekannte session_id)."""


class SupportSessionsRepo:
    """Auditierte/plain Lese-/Schreibmethoden auf der Tabelle support_sessions."""

    def __init__(self, con: sqlite3.Connection, writer: CoordinatorWriter) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._writer = writer

    # --------------------------------------------------------------- Schreiben
    def start(
        self, user_id: int, supporter_id: Optional[int], *,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> int:
        """
        Legt eine laufende Support-Sitzung an und schreibt SUPPORT_SESSION_STARTED
        atomar mit. Gibt die session_id (support_sessions.id) zurück — nicht die
        audit-seq, da der Aufrufer die session_id für heartbeat()/end() braucht.
        """
        now = int(time.time())
        captured: Dict[str, int] = {}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            cur = con.execute(
                "INSERT INTO support_sessions "
                "(user_id, supporter_id, started_at, last_heartbeat) "
                "VALUES (?, ?, ?, ?)",
                (user_id, supporter_id, now, now),
            )
            sid = int(cur.lastrowid)
            captured["session_id"] = sid
            return {
                "session_id": sid,
                "user_id": user_id,
                "supporter_id": supporter_id,
                "started_at": now,
            }

        self._writer.audited_write(
            do_write=_w,
            event_type=EventType.SUPPORT_SESSION_STARTED,
            actor_id=actor_id,
            target_type="support_session",
            target_id=str(user_id),
            meta=meta,
        )
        return captured["session_id"]

    def heartbeat(self, session_id: int) -> bool:
        """
        Aktualisiert last_heartbeat einer LAUFENDEN Sitzung. KEIN Audit.
        Gibt True zurück, wenn eine laufende Sitzung getroffen wurde
        (bereits beendete/unbekannte Sitzung -> False).
        """
        now = int(time.time())
        with self._writer.transaction() as con:
            cur = con.execute(
                "UPDATE support_sessions SET last_heartbeat = ? "
                "WHERE id = ? AND ended_at IS NULL",
                (now, session_id),
            )
            hit = cur.rowcount > 0
        return hit

    def end(
        self, session_id: int, *,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> Optional[int]:
        """
        Beendet eine laufende Sitzung (setzt ended_at) und schreibt
        SUPPORT_SESSION_ENDED. Idempotent: eine bereits beendete Sitzung liefert
        None (kein zweiter Beleg). Unbekannte session_id -> SupportSessionsError.
        Gibt sonst die audit-seq zurück.
        """
        row = self._con.execute(
            "SELECT user_id, started_at, ended_at FROM support_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise SupportSessionsError("Unbekannte session_id=%s." % session_id)
        if row["ended_at"] is not None:
            return None  # bereits beendet — kein zweiter Zugriffsbeleg

        now = int(time.time())
        started_at = int(row["started_at"])
        user_id = int(row["user_id"])

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            cur = con.execute(
                "UPDATE support_sessions SET ended_at = ? "
                "WHERE id = ? AND ended_at IS NULL",
                (now, session_id),
            )
            if cur.rowcount == 0:
                # Race: zwischenzeitlich beendet -> rollback, kein Beleg.
                raise SupportSessionsError(
                    "Sitzung %s wurde bereits beendet." % session_id
                )
            return {
                "session_id": session_id,
                "user_id": user_id,
                "ended_at": now,
                "duration_sec": now - started_at,
            }

        return self._writer.audited_write(
            do_write=_w,
            event_type=EventType.SUPPORT_SESSION_ENDED,
            actor_id=actor_id,
            target_type="support_session",
            target_id=str(session_id),
            meta=meta,
        )

    def close_orphans(
        self, stale_sec: int, *, actor_id: Optional[int] = None,
    ) -> int:
        """
        Beendet AUDITIERT alle verwaisten Sitzungen (ended_at IS NULL UND
        last_heartbeat aelter als stale_sec) — Supporter ungrazil verschwunden,
        end() wurde nie erreicht. Setzt ended_at = last_heartbeat (der EHRLICHE
        letzte Praesenzbeleg, NICHT 'now') und schreibt fuer JEDE Sitzung
        SUPPORT_SESSION_ENDED mit payload.reason='orphan_timeout'.

        Zweck (Grundregel 1 — kein Beleg still uebersprungen): Ohne diesen Schritt
        wuerde prune() eine nie beendete Sitzung LOESCHEN, ohne dass im audit_log
        je ein ENDED zum STARTED stuende — der permanente 'wer sah wann welchen
        Fall'-Beleg bliebe unvollstaendig. close_orphans() vervollstaendigt den
        Audit-Trail, BEVOR prune() die (nun beendete) Zeile regulaer entfernt.

        actor_id=None => System-Aktion (kein Supporter hat aktiv beendet); der
        Grund steht im Payload. Idempotent gegen Races: eine zwischenzeitlich
        regulaer beendete Sitzung wird uebersprungen (kein Doppel-Beleg).
        Gibt die Anzahl auditiert beendeter Waisen zurueck.

        Beleg: Live-Diagnose 2026-07-07 (Waise id=5 blieb ohne ENDED liegen);
        mc 2026-07-07.
        """
        cutoff = int(time.time()) - stale_sec
        # Kandidaten zuerst als Snapshot lesen, dann einzeln auditiert beenden.
        orphans = self._con.execute(
            "SELECT id, user_id, started_at, last_heartbeat "
            "FROM support_sessions "
            "WHERE ended_at IS NULL AND last_heartbeat < ? "
            "ORDER BY id ASC",
            (cutoff,),
        ).fetchall()

        closed = 0
        for o in orphans:
            session_id = int(o["id"])
            user_id = int(o["user_id"])
            started_at = int(o["started_at"])
            ended_at = int(o["last_heartbeat"])  # ehrlicher letzter Praesenzbeleg

            # Default-Argumente binden die Schleifenwerte pro Iteration (kein
            # Late-Binding). audited_write ruft _w synchron innerhalb derselben
            # Transaktion auf (Write + Audit atomar).
            def _w(
                con: sqlite3.Connection,
                _sid: int = session_id, _uid: int = user_id,
                _start: int = started_at, _end: int = ended_at,
            ) -> Dict[str, Any]:
                cur = con.execute(
                    "UPDATE support_sessions SET ended_at = ? "
                    "WHERE id = ? AND ended_at IS NULL",
                    (_end, _sid),
                )
                if cur.rowcount == 0:
                    # Race: zwischenzeitlich regulaer beendet -> Rollback der
                    # gesamten Transaktion, KEIN zweiter Beleg fuer diese Sitzung.
                    raise SupportSessionsError(
                        "Waise %s bereits beendet." % _sid
                    )
                return {
                    "session_id": _sid,
                    "user_id": _uid,
                    "ended_at": _end,
                    "duration_sec": _end - _start,
                    "reason": "orphan_timeout",
                }

            try:
                self._writer.audited_write(
                    do_write=_w,
                    event_type=EventType.SUPPORT_SESSION_ENDED,
                    actor_id=actor_id,
                    target_type="support_session",
                    target_id=str(session_id),
                    meta=None,
                )
                closed += 1
            except SupportSessionsError:
                # Race mit regulaerem end()/parallelem close_orphans -> der Beleg
                # wurde dann anderweitig geschrieben; diese Waise ueberspringen.
                continue
        return closed

    def prune(self, older_than_sec: int) -> int:
        """
        Entfernt flüchtige Alt-Zeilen: beendete Sitzungen sowie Sitzungen ohne
        Heartbeat seit older_than_sec. KEIN Audit (nur Präsenz, kein Beleg — der
        Beleg bleibt im audit_log). Gibt die Anzahl gelöschter Zeilen zurück.
        """
        cutoff = int(time.time()) - older_than_sec
        with self._writer.transaction() as con:
            cur = con.execute(
                "DELETE FROM support_sessions WHERE "
                "(ended_at IS NOT NULL AND ended_at < ?) OR (last_heartbeat < ?)",
                (cutoff, cutoff),
            )
            n = cur.rowcount
        return n

    # ------------------------------------------------------------------- Lesen
    def get_active(self, user_id: int, stale_sec: int) -> List[Dict[str, Any]]:
        """
        Aktive Support-Sitzungen eines Falls: nicht beendet UND mit Heartbeat
        innerhalb der Stale-Schwelle. Aufsteigend nach started_at (der am
        längsten Aktive zuerst). Für den Support-Indikator.
        """
        threshold = int(time.time()) - stale_sec
        rows = self._con.execute(
            "SELECT s.id, s.supporter_id, s.started_at, i.system_username "
            "FROM support_sessions s "
            "LEFT JOIN person i ON i.id = s.supporter_id "
            "WHERE s.user_id = ? AND s.ended_at IS NULL AND s.last_heartbeat >= ? "
            "ORDER BY s.started_at ASC",
            (user_id, threshold),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_running(self) -> List[Dict[str, Any]]:
        """
        ALLE laufenden Support-Sitzungen (ended_at IS NULL), falluebergreifend,
        verknuepft mit Supporter (person) und Fall (cases.username). Read-only,
        KEINE Stale-Filterung — die Live/Stale-Bewertung erfolgt beim Aufrufer
        (Ermittler-Betreuung, Build 368). Aufsteigend nach started_at (der am
        laengsten Laufende zuerst).
        """
        rows = self._con.execute(
            "SELECT s.id, s.user_id, c.username, s.supporter_id, "
            "       p.system_username AS supporter_system_username, "
            "       p.display_name AS supporter_display_name, "
            "       s.started_at, s.last_heartbeat "
            "FROM support_sessions s "
            "LEFT JOIN person p ON p.id = s.supporter_id "
            "LEFT JOIN cases c ON c.user_id = s.user_id "
            "WHERE s.ended_at IS NULL "
            "ORDER BY s.started_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]

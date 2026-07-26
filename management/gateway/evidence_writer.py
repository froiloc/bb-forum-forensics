# =============================================================================
# management/gateway/evidence_writer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A)
# =============================================================================
# Zweck (Build 533):
#   Auditierter Schreibpfad auf evidence_<uid>.db. Bindet fachlichen Write und
#   Beleg in EINE Transaktion: entweder beide committen oder keines von beidem.
#   Das Gegenstueck zu CoordinatorWriter (coordinator.db) und TemplatesWriter
#   (templates.db).
#
# ── DER UNTERSCHIED ZU CoordinatorWriter, UND WARUM ER DIESE DATEI ERZWINGT ──
#
#   CoordinatorWriter bekommt eine EIGENE, frisch geoeffnete Verbindung und
#   darf mit ihr machen, was er will (isolation_level=None dauerhaft,
#   coordinator_writer.py:38). Fuer evidence_<uid>.db geht das NICHT, und zwar
#   aus zwei unabhaengigen Gruenden:
#
#   (1) DIE DATEI HAT SCHON EINEN SCHREIBER. evidence_<uid>.db ist die
#       HAUPTVERBINDUNG des forensischen Servers (db/connection_manager.py:203
#       — 'Haupt-DB: evidence_db (READ-WRITE)'; coordinator.db haengt als
#       ATTACH 'cdb' daran). Der Server haelt sie waehrend des gesamten
#       Betriebs offen. Eine zweite Verbindung auf dieselbe Datei zu oeffnen,
#       verstiesse gegen die im Projekt ausdruecklich festgehaltene Regel
#       "nie zwei Schreiber pro Datei" (db/review_addendum_db.py:8-11) und
#       liefe auf Sperrkonflikte mit dem laufenden Server hinaus.
#
#   (2) DIE VERBINDUNG IST GETEILT UND WIRD SERIALISIERT. Der Server laeuft mit
#       ThreadingMixIn (server/http_server.py:272). Alle Fach-DBs teilen sich
#       EINE sqlite3.Connection, die seit Build 325 in einen
#       LockingConnection-Wrapper eingepackt ist (db/locking_connection.py,
#       eingesetzt in db/connection_manager.py:337). Dieser Wrapper
#       serialisiert jeden EINZELNEN execute+fetch-Abschnitt — aber eben nur
#       einzelne. Eine Folge BEGIN IMMEDIATE / INSERT / INSERT / COMMIT waere
#       ohne weiteres Zutun zwischen zwei Threads verschraenkbar.
#
# ── WIE DIESE KLASSE BEIDES LOEST ────────────────────────────────────────────
#
#   Sie benutzt DIESELBE geteilte Verbindung und haelt fuer die Dauer der
#   Transaktion deren OEFFENTLICHEN Lock. Der Wrapper sieht diese Nutzung
#   ausdruecklich vor; sein Modulkopf nennt sie beim Namen:
#       "ESKALATION: Der oeffentliche .lock (derselbe RLock) erlaubt kuenftig
#        explizite Mehr-Statement-/Streaming-Abschnitte via 'with con.lock:'"
#       (db/locking_connection.py:34-35)
#   Der Lock ist REENTRANT (RLock, :141), die inneren execute()-Aufrufe duerfen
#   ihn also erneut nehmen. Kein Deadlock, kein zweiter Schreiber, keine
#   Verschraenkung.
#
#   Fehlt der Lock (etwa im Test auf einer rohen sqlite3.Connection), laeuft
#   die Klasse ohne ihn weiter — dann gibt es aber auch keine Nebenlaeufigkeit.
#   Das ist eine bewusste Entscheidung fuer Testbarkeit, kein stiller Verzicht:
#   Test EW06 haelt beide Wege fest.
#
# ── isolation_level: GELIEHEN, NICHT GENOMMEN ────────────────────────────────
#
#   Fuer BEGIN IMMEDIATE muss isolation_level=None sein, sonst faengt Pythons
#   sqlite3 selbst Transaktionen an. Die geteilte Verbindung gehoert uns aber
#   nicht: save_annotation (db/evidence_db.py:947) und rund 150 weitere Stellen
#   verlassen sich auf das Standardverhalten. Deshalb wird isolation_level nur
#   fuer die Dauer der Transaktion umgestellt und im finally-Zweig
#   ZURUECKGESETZT — auch im Fehlerfall.
#
#   REIHENFOLGE IST HIER NICHT EGAL: Das Setzen von isolation_level committet
#   eine offene Transaktion IMPLIZIT. Wenn also ein anderer Vorgang gerade eine
#   Transaktion offen haette, wuerden wir sie ihm ungefragt festschreiben.
#   Darum wird VOR dem Umstellen geprueft, ob con.in_transaction gesetzt ist,
#   und in diesem Fall abgebrochen (EvidenceWriteError). Lieber ein lauter
#   Abbruch als ein fremder Commit, von dem niemand etwas weiss.
#
# ── EIN BELEG OHNE HANDELNDEN IST KEIN BELEG ─────────────────────────────────
#
#   audited_write verweigert actor_id=None. Dieselbe Regel gilt bereits im
#   forensischen Server (forensic_api/results_endpoint.py:222-228). In
#   evidence_audit_log ist actor_id NULL-faehig deklariert (spaltengleich mit
#   audit_log, wo die Genesis-Zeile keinen Handelnden hat) — die Pflicht liegt
#   also im Gateway, und Test EW05 haelt sie fest.
#
# Version: v0.8.533 · Build: 533 · 2026-07-26
# =============================================================================

import logging
import sqlite3
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, Optional

from management.audit.evidence_audit_log import EvidenceAuditLog

logger = logging.getLogger(__name__)


class EvidenceWriteError(Exception):
    """Der Schreibvorgang wurde abgelehnt, BEVOR etwas geschrieben wurde."""


class EvidenceWriter:
    """Atomares Write+Audit-Gateway fuer evidence_<uid>.db."""

    def __init__(self, con: sqlite3.Connection,
                 audit: Optional[EvidenceAuditLog] = None) -> None:
        self._con = con
        self._audit = audit if audit is not None else EvidenceAuditLog(con)

    # ------------------------------------------------------------- Transaktion
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """
        Schreibtransaktion mit sofortiger Sperre auf der GETEILTEN Verbindung.

        Haelt fuer die gesamte Dauer den Lock der LockingConnection (falls
        vorhanden), stellt isolation_level voruebergehend auf None und setzt
        beides am Ende zurueck. Bei Erfolg COMMIT, bei jeder Exception
        ROLLBACK — es bleibt weder Write noch Beleg zurueck.
        """
        lock = getattr(self._con, "lock", None)

        if lock is not None:
            lock.acquire()
        try:
            # (1) Kein fremder Commit. Siehe Kopf, Abschnitt isolation_level.
            if getattr(self._con, "in_transaction", False):
                raise EvidenceWriteError(
                    "Auf der Verbindung ist bereits eine Transaktion offen. "
                    "Der Schreibvorgang wird abgebrochen, damit die fremde "
                    "Transaktion nicht ungefragt festgeschrieben wird. Es "
                    "wurde NICHTS geschrieben."
                )

            prev_isolation = getattr(self._con, "isolation_level", "")
            self._con.isolation_level = None
            try:
                self._con.execute("BEGIN IMMEDIATE")
                try:
                    yield self._con
                    self._con.execute("COMMIT")
                except Exception:
                    self._con.execute("ROLLBACK")
                    raise
            finally:
                # Die Verbindung gehoert uns nicht — Zustand zurueckgeben.
                self._con.isolation_level = prev_isolation
        finally:
            if lock is not None:
                lock.release()

    # ----------------------------------------------------------- Write + Beleg
    def audited_write(
        self,
        *,
        do_write: Callable[[sqlite3.Connection], Optional[Dict[str, Any]]],
        event_type: str,
        actor_id: int,
        target_type: Optional[str],
        target_id: Optional[str],
        meta: Optional[Any] = None,
        after_audit: Optional[Callable[[sqlite3.Connection, int], None]] = None,
    ) -> int:
        """
        Fuehrt do_write(con) aus und schreibt im selben Transaktionsrahmen den
        Beleg in evidence_audit_log. do_write liefert das Audit-Payload (dict)
        oder None (-> leeres Payload).

        after_audit(con, seq) — optionaler Hook NACH dem Append, aber noch
        INNERHALB derselben Transaktion. Er existiert aus demselben Grund wie
        bei CoordinatorWriter (coordinator_writer.py:74-81): eine abgeleitete
        Zeile soll die exakte seq ihres Belegs tragen koennen. Wirft er, wird
        die GESAMTE Transaktion zurueckgerollt.

        Gibt die seq des Beleg-Eintrags zurueck.

        Wirft EvidenceWriteError, wenn kein Handelnder angegeben ist — VOR
        jedem Schreibzugriff.
        """
        if actor_id is None:
            raise EvidenceWriteError(
                "Kein Handelnder (actor_id) — ein Beleg ohne Handelnden ist "
                "kein Beleg. Es wurde NICHTS geschrieben."
            )

        with self.transaction() as con:
            payload = do_write(con)
            if payload is None:
                payload = {}
            seq = self._audit.append(
                event_type=event_type,
                actor_id=int(actor_id),
                target_type=target_type,
                target_id=target_id,
                payload=payload,
                meta=meta,
            )
            if after_audit is not None:
                after_audit(con, seq)

        logger.debug(
            "EvidenceWriter.audited_write: type=%s target=%s/%s -> seq=%d",
            event_type, target_type, target_id, seq,
        )
        return seq

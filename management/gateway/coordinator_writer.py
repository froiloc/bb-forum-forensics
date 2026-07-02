# =============================================================================
# management/gateway/coordinator_writer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Der EINZIGE zulässige Schreibpfad auf die Management-Tabellen der
#   coordinator.db (ab Tag 2: cases, case_events; später notifications, backups).
#   Bindet fachlichen Write und zugehörigen Audit-Eintrag in EINE Transaktion:
#   entweder beide committen oder keines von beidem. Damit existiert kein
#   Management-Write ohne Audit-Eintrag und kein Audit-Eintrag ohne seinen Write.
#   Das ist der forensische Kern des Management-Interfaces.
#   (Beleg: Bauplan B7 v0.2 §2.6, mc 2026-07-01)
#
# Nebenläufigkeit:
#   transaction() öffnet BEGIN IMMEDIATE — die Schreibsperre wird sofort
#   gehalten, sodass das Tip-Lesen der Hash-Kette + der Insert atomar und gegen
#   konkurrierende Schreiber serialisiert sind (kein Race auf prev_hash).
#
# Version: v0.7.313 · Build: 313 · 2026-07-02 (after_audit-Hook, Bauplan B7 v0.8 §8.3)
# =============================================================================

import logging
import sqlite3
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, Optional

from management.audit.audit_log import AuditLog

logger = logging.getLogger(__name__)


class CoordinatorWriter:
    """Atomares Write+Audit-Gateway für coordinator.db."""

    def __init__(self, con: sqlite3.Connection, audit: AuditLog) -> None:
        self._con = con
        # Explizite Transaktionssteuerung (siehe MigrationRunner).
        self._con.isolation_level = None
        self._audit = audit

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """
        Schreibtransaktion mit sofortiger Sperre. Bei Erfolg COMMIT, bei jeder
        Exception ROLLBACK (es bleibt weder Write noch Audit-Eintrag zurück).
        """
        self._con.execute("BEGIN IMMEDIATE")
        try:
            yield self._con
            self._con.execute("COMMIT")
        except Exception:
            self._con.execute("ROLLBACK")
            raise

    def audited_write(
        self,
        *,
        do_write: Callable[[sqlite3.Connection], Optional[Dict[str, Any]]],
        event_type: str,
        actor_id: Optional[int],
        target_type: Optional[str],
        target_id: Optional[str],
        meta: Optional[Any] = None,
        after_audit: Optional[Callable[[sqlite3.Connection, int], None]] = None,
    ) -> int:
        """
        Führt do_write(con) aus und schreibt im selben Transaktionsrahmen den
        zugehörigen Audit-Eintrag. do_write liefert den Audit-Payload (dict) für
        das Ereignis (oder None -> leeres Payload).

        after_audit(con, seq) — optionaler Hook, der NACH dem Audit-Append,
        aber noch INNERHALB derselben Transaktion läuft. Er existiert, damit
        abgeleitete Lesemodell-Zeilen (z. B. case_events, Build 313) die
        exakte seq ihres audit_log-Belegs tragen können; die Kopplung
        Write + Audit + Lesemodell committet atomar oder gar nicht.
        Wirft after_audit, wird die GESAMTE Transaktion zurückgerollt —
        es bleibt weder Write noch Audit-Eintrag noch Lesemodell-Zeile
        zurück (Grundregel 1: keine stille Teil-Persistenz).
        (Beleg: Bauplan B7 v0.8 §8.3, mc 2026-07-02)

        Gibt die seq des Audit-Eintrags zurück.
        """
        with self.transaction() as con:
            payload = do_write(con)
            if payload is None:
                payload = {}
            seq = self._audit.append(
                event_type=event_type,
                actor_id=actor_id,
                target_type=target_type,
                target_id=target_id,
                payload=payload,
                meta=meta,
            )
            if after_audit is not None:
                after_audit(con, seq)
        logger.debug(
            "audited_write: type=%s target=%s/%s -> audit seq=%d",
            event_type, target_type, target_id, seq,
        )
        return seq

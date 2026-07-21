# =============================================================================
# management/gateway/templates_writer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — SF-4 (Build 421): auditierter Schreibpfad fuer templates.db
# =============================================================================
# Zweck:
#   Der EINZIGE zulaessige Schreibpfad auf templates.db (report_modules,
#   placeholder_queries, report_templates). Er bindet den fachlichen Write und
#   den zugehoerigen Audit-Eintrag (templates_audit_log) in EINE Transaktion:
#   entweder beide committen oder keines von beidem. Damit existiert kein
#   Templates-Write ohne Audit-Eintrag und kein Audit-Eintrag ohne seinen Write.
#   (Analog management/gateway/coordinator_writer.py; mc 2026-07-14, Konzept
#   v0.2 §3 SF-4.)
#
#   Hintergrund: TemplatesDb (db/templates_db.py) ist strikt READ-ONLY. Vor
#   diesem Writer wurde templates.db ausschliesslich durch Seed-Skripte
#   beschrieben. Die Authoring-Werkzeuge W1/W2/W3 (Build 422 ff.) schreiben
#   kuenftig ausschliesslich ueber diesen Writer, gegated auf 'templates.edit'.
#
# Nebenlaeufigkeit / Journal:
#   BEGIN IMMEDIATE haelt die Schreibsperre sofort; der Aufrufer oeffnet die
#   Verbindung mit journal_mode=delete (Build 408/409 — kein WAL, netzsicher)
#   und isolation_level=None (explizite Transaktionssteuerung).
#
# Audit-Vokabular:
#   templates_audit_log.target_type ist per CHECK auf ('module','query',
#   'template','placeholder') beschraenkt — 'template' seit
#   migrate_templates_audit_check (Build 421), 'placeholder' seit
#   migrate_templates_placeholders (Build 489). Ein Audit mit einem noch nicht
#   migrierten Wert scheitert an der CHECK-Constraint -> die Transaktion rollt
#   zurueck (kein Teilschreiben).
#
# Version: v0.8.489 · Build: 489 · 2026-07-21
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, Optional

logger = logging.getLogger(__name__)


class TemplatesWriteError(Exception):
    """Fachlicher Fehler im auditierten templates.db-Schreibpfad."""


class TemplatesWriter:
    """Atomares Write+Audit-Gateway fuer templates.db."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        # Explizite Transaktionssteuerung (kein impliziter Autobegin, der mit
        # dem manuellen BEGIN IMMEDIATE kollidierte).
        self._con.isolation_level = None

    # ------------------------------------------------------------------
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """
        Schreibtransaktion mit sofortiger Sperre. Bei Erfolg COMMIT, bei jeder
        Exception ROLLBACK (es bleibt weder Write noch Audit-Eintrag zurueck).
        """
        self._con.execute("BEGIN IMMEDIATE")
        try:
            yield self._con
            self._con.execute("COMMIT")
        except Exception:
            self._con.execute("ROLLBACK")
            raise

    # ------------------------------------------------------------------
    def audited_write(
        self,
        *,
        do_write: Callable[[sqlite3.Connection], Dict[str, Any]],
        action: str,
        target_type: str,
        changed_by: str,
        ts: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Fuehrt do_write(con) aus und schreibt im selben Transaktionsrahmen den
        zugehoerigen templates_audit_log-Eintrag.

        do_write MUSS ein dict liefern, das mindestens 'target_id' enthaelt;
        optional 'old_value'/'new_value' (kanonische Strings des Vorher/Nachher
        — sie werden 1:1 in den Audit-Eintrag uebernommen). Der Rueckgabewert
        von do_write wird unveraendert an den Aufrufer durchgereicht (z.B. die
        neue id einer Zeile).

        action      — z.B. 'create'|'update'|'deactivate'
        target_type — 'module'|'query'|'template'|'placeholder' (per CHECK
                      erzwungen; 'placeholder' seit Build 489)
        changed_by  — auditierte Urheber-Kennung (system_username o.ae.)
        """
        now = int(ts if ts is not None else time.time())
        with self.transaction() as con:
            result = do_write(con)
            if not isinstance(result, dict) or "target_id" not in result:
                # Kein stiller Teilschreib: die Transaktion rollt durch das
                # raise ohnehin zurueck (Grundregel 1).
                raise TemplatesWriteError(
                    "do_write muss ein dict mit 'target_id' liefern.")
            con.execute(
                "INSERT INTO templates_audit_log "
                "(action, target_id, target_type, changed_by, changed_at, "
                " old_value, new_value) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(action), str(result["target_id"]), str(target_type),
                 str(changed_by), now,
                 result.get("old_value"), result.get("new_value")),
            )
        logger.debug("templates audited_write: action=%s type=%s target=%s",
                     action, target_type, result.get("target_id"))
        return result

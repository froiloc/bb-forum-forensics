# =============================================================================
# management/capacity/reason_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kapazitaet (Welle 0)
# =============================================================================
# ReasonRepo — auditierter, Supervisor-erweiterbarer Grund-Katalog fuer
# Verfuegbarkeits-Eintraege (availability_reason, Schema m008).
#
#   add_reason  -> AVAILABILITY_REASON_ADDED (neue Zeile, audit_seq == Beleg-seq)
#   list_reasons()
#
# Bewusst nur add/list: die vereinbarte Audit-Granularitaet (mc 2026-07-10)
# kennt kein REASON_REMOVED. Die deleted_at-Spalte bleibt fuer eine spaetere
# Ausbaustufe reserviert. Ein bereits verwendeter Grund soll ohnehin erhalten
# bleiben (Historie der availability_entry-Zeilen).
#
# Beleg: Bauplan B7 v1.1 §11.4. Version: v0.7.357 · Build: 357 · 2026-07-10
# =============================================================================

import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.capacity.capacity_errors import CapacityError


class ReasonRepo:
    """Schreibt/liest availability_reason (auditiert)."""

    def __init__(self, con: sqlite3.Connection, writer) -> None:
        self._con = con
        self._writer = writer

    # ------------------------------------------------------------------ add
    def add_reason(self, code: str, label: str, *, sort: int = 0,
                   actor_id: Optional[int] = None,
                   meta: Optional[Any] = None) -> int:
        if not code or not label:
            raise CapacityError("code und label sind erforderlich.")
        now = int(time.time())

        def _w(_con: sqlite3.Connection) -> Dict[str, Any]:
            # PK ist 'code' -> Duplikat waere ein IntegrityError; wir fangen es
            # vorab mit klarer Meldung ab (kein roher DB-Fehler nach aussen).
            if _con.execute(
                "SELECT 1 FROM availability_reason WHERE code=?",
                (code,)).fetchone() is not None:
                raise CapacityError("Grund '%s' existiert bereits." % code)
            return {"code": code, "label": label, "sort": sort}

        def _after(_con: sqlite3.Connection, seq: int) -> None:
            _con.execute(
                "INSERT INTO availability_reason "
                "(code, label, sort, created_by, audit_seq, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (code, label, sort, actor_id, seq, now))

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.AVAILABILITY_REASON_ADDED,
            actor_id=actor_id, target_type="availability_reason",
            target_id=code, meta=meta, after_audit=_after)

    # ----------------------------------------------------------------- list
    def list_reasons(self, *, include_deleted: bool = False
                     ) -> List[Dict[str, Any]]:
        sql = ("SELECT code, label, sort, created_by, audit_seq, created_at, "
               "deleted_at FROM availability_reason")
        if not include_deleted:
            sql += " WHERE deleted_at IS NULL"
        sql += " ORDER BY sort ASC, code ASC"
        cur = self._con.execute(sql)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    # --------------------------------------------------------------- exists
    def is_active(self, code: str) -> bool:
        """True, wenn der Grund existiert und nicht soft-geloescht ist."""
        row = self._con.execute(
            "SELECT 1 FROM availability_reason "
            "WHERE code=? AND deleted_at IS NULL", (code,)).fetchone()
        return row is not None

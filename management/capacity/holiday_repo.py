# =============================================================================
# management/capacity/holiday_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kapazitaet (Welle 0)
# =============================================================================
# HolidayRepo — auditierter Schreibpfad fuer Feiertage (holiday, Schema m008).
# Feiertage gelten fuer ALLE (region-gescopt; region NULL = ueberall).
#
#   add_holiday    -> HOLIDAY_ADDED   (neue Zeile, audit_seq == Beleg-seq)
#   remove_holiday -> HOLIDAY_REMOVED (Soft-Delete: deleted_at gesetzt; kein
#                     hartes DELETE. Der Entfernungs-Beleg steht im audit_log
#                     mit target_id=holiday_id — das Schema fuehrt bewusst keine
#                     delete_audit_seq-Spalte, §11.4.)
#
# Grundregel 1: Entfernen einer nicht (mehr) vorhandenen Zeile -> CapacityError
# (kein stiller No-op). Duplikat-Guard fuer aktive (day, region).
#
# Beleg: Bauplan B7 v1.1 §11.4; Muster rbac_repo. mc 2026-07-10.
# Version: v0.7.356 · Build: 356 · 2026-07-10
# =============================================================================

import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.capacity.capacity_errors import CapacityError


class HolidayRepo:
    """Schreibt/liest holiday (auditiert, Soft-Delete)."""

    def __init__(self, con: sqlite3.Connection, writer) -> None:
        self._con = con
        self._writer = writer

    # ------------------------------------------------------------------ add
    def add_holiday(self, day: str, label: str, *,
                    region: Optional[str] = None,
                    actor_id: Optional[int] = None,
                    meta: Optional[Any] = None) -> int:
        if not day or not label:
            raise CapacityError("day (ISO-Datum) und label sind erforderlich.")
        now = int(time.time())

        def _w(_con: sqlite3.Connection) -> Dict[str, Any]:
            # Duplikat-Guard innerhalb der Schreibsperre (kein TOCTOU).
            # 'IS ?' ist null-sicher (region NULL vergleicht korrekt).
            if _con.execute(
                "SELECT 1 FROM holiday WHERE day=? AND region IS ? "
                "AND deleted_at IS NULL", (day, region)).fetchone() is not None:
                raise CapacityError(
                    "Aktiver Feiertag %s (Region %s) existiert bereits."
                    % (day, region if region is not None else "ueberall"))
            return {"day": day, "label": label, "region": region}

        def _after(_con: sqlite3.Connection, seq: int) -> None:
            _con.execute(
                "INSERT INTO holiday (day, label, region, audit_seq, "
                "created_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (day, label, region, seq, actor_id, now))

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.HOLIDAY_ADDED,
            actor_id=actor_id, target_type="holiday", target_id=day,
            meta=meta, after_audit=_after)

    # --------------------------------------------------------------- remove
    def remove_holiday(self, holiday_id: int, *,
                       actor_id: Optional[int] = None,
                       meta: Optional[Any] = None) -> int:
        now = int(time.time())

        def _w(_con: sqlite3.Connection) -> Dict[str, Any]:
            cur = _con.execute(
                "UPDATE holiday SET deleted_at=? "
                "WHERE id=? AND deleted_at IS NULL", (now, holiday_id))
            if cur.rowcount == 0:
                raise CapacityError(
                    "Feiertag id=%s nicht vorhanden oder bereits entfernt."
                    % holiday_id)
            return {"holiday_id": holiday_id}

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.HOLIDAY_REMOVED,
            actor_id=actor_id, target_type="holiday",
            target_id=str(holiday_id), meta=meta)

    # ----------------------------------------------------------------- list
    def list_holidays(self, *, region: Optional[str] = None,
                      include_deleted: bool = False) -> List[Dict[str, Any]]:
        sql = ("SELECT id, day, label, region, audit_seq, created_by, "
               "created_at, deleted_at FROM holiday")
        clauses = []
        params: list = []
        if not include_deleted:
            clauses.append("deleted_at IS NULL")
        if region is not None:
            clauses.append("region = ?")
            params.append(region)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY day ASC, id ASC"
        cur = self._con.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

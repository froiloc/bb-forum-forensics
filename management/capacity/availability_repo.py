# =============================================================================
# management/capacity/availability_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kapazitaet (Welle 0)
# =============================================================================
# AvailabilityRepo — auditierter Schreibpfad fuer Verfuegbarkeits-Eintraege
# (availability_entry, Schema m008): je Person/Zeitraum eine Garantie ODER eine
# Einschraenkung, ausgedrueckt als Prozent ODER Minuten (genau eines).
#
#   set_availability    -> AVAILABILITY_SET     (neue Zeile, audit_seq==Beleg)
#   remove_availability -> AVAILABILITY_REMOVED (Soft-Delete deleted_at)
#
# VALIDIERUNG (klarer Fehler vor DB-CHECK): genau eines von value_pct/
# value_minutes; kind in {garantie, einschraenkung}; value_pct in [0,100];
# value_minutes >= 0; period_start <= period_end; reason_code (falls gesetzt)
# muss ein AKTIVER Grund sein.
#
# KEIN Overlap-Guard: mehrere Garantien/Einschraenkungen fuer denselben
# Zeitraum sind zulaessig; ihr Zusammenspiel loest die Kapazitaets-Berechnung
# (Build 358) auf ("Einschraenkungen im Rahmen der Garantien", §11.4).
#
# Beleg: Bauplan B7 v1.1 §11.4. Version: v0.7.357 · Build: 357 · 2026-07-10
# =============================================================================

import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.capacity.capacity_errors import CapacityError
from management.capacity.reason_repo import ReasonRepo

_KINDS = ("garantie", "einschraenkung")


class AvailabilityRepo:
    """Schreibt/liest availability_entry (auditiert, Soft-Delete)."""

    def __init__(self, con: sqlite3.Connection, writer) -> None:
        self._con = con
        self._writer = writer

    # ------------------------------------------------------------------ set
    def set_availability(self, person_id: int, *, period_start: str,
                         period_end: str, kind: str,
                         value_pct: Optional[int] = None,
                         value_minutes: Optional[int] = None,
                         reason_code: Optional[str] = None,
                         note: Optional[str] = None,
                         actor_id: Optional[int] = None,
                         meta: Optional[Any] = None) -> int:
        # --- Validierung (klare Fehler vor dem DB-CHECK) ---
        if kind not in _KINDS:
            raise CapacityError(
                "kind muss 'garantie' oder 'einschraenkung' sein (%r)." % kind)
        if (value_pct is None) == (value_minutes is None):
            raise CapacityError(
                "Genau EINES von value_pct/value_minutes muss gesetzt sein.")
        if value_pct is not None and not (0 <= value_pct <= 100):
            raise CapacityError("value_pct muss in [0, 100] liegen.")
        if value_minutes is not None and value_minutes < 0:
            raise CapacityError("value_minutes muss >= 0 sein.")
        if not period_start or not period_end:
            raise CapacityError("period_start und period_end sind erforderlich.")
        if period_start > period_end:
            raise CapacityError(
                "period_start (%s) liegt nach period_end (%s)."
                % (period_start, period_end))
        if reason_code is not None and not ReasonRepo(
                self._con, None).is_active(reason_code):
            raise CapacityError(
                "reason_code '%s' ist kein aktiver Grund." % reason_code)
        now = int(time.time())

        def _w(_con: sqlite3.Connection) -> Dict[str, Any]:
            return {"person_id": person_id, "period_start": period_start,
                    "period_end": period_end, "kind": kind,
                    "value_pct": value_pct, "value_minutes": value_minutes,
                    "reason_code": reason_code}

        def _after(_con: sqlite3.Connection, seq: int) -> None:
            _con.execute(
                "INSERT INTO availability_entry "
                "(person_id, period_start, period_end, kind, value_pct, "
                " value_minutes, reason_code, note, audit_seq, created_by, "
                " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (person_id, period_start, period_end, kind, value_pct,
                 value_minutes, reason_code, note, seq, actor_id, now))

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.AVAILABILITY_SET,
            actor_id=actor_id, target_type="availability_entry",
            target_id=str(person_id), meta=meta, after_audit=_after)

    # --------------------------------------------------------------- remove
    def remove_availability(self, entry_id: int, *,
                            actor_id: Optional[int] = None,
                            meta: Optional[Any] = None) -> int:
        now = int(time.time())

        def _w(_con: sqlite3.Connection) -> Dict[str, Any]:
            cur = _con.execute(
                "UPDATE availability_entry SET deleted_at=?, updated_at=? "
                "WHERE id=? AND deleted_at IS NULL", (now, now, entry_id))
            if cur.rowcount == 0:
                raise CapacityError(
                    "availability_entry id=%s nicht vorhanden oder bereits "
                    "entfernt." % entry_id)
            return {"entry_id": entry_id}

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.AVAILABILITY_REMOVED,
            actor_id=actor_id, target_type="availability_entry",
            target_id=str(entry_id), meta=meta)

    # ----------------------------------------------------------------- list
    def list_availability(self, person_id: Optional[int] = None, *,
                          include_deleted: bool = False
                          ) -> List[Dict[str, Any]]:
        sql = ("SELECT id, person_id, period_start, period_end, kind, "
               "value_pct, value_minutes, reason_code, note, audit_seq, "
               "created_by, created_at, updated_at, deleted_at "
               "FROM availability_entry")
        clauses = []
        params: list = []
        if not include_deleted:
            clauses.append("deleted_at IS NULL")
        if person_id is not None:
            clauses.append("person_id = ?")
            params.append(person_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY person_id ASC, period_start ASC, id ASC"
        cur = self._con.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

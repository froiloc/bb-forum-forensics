# =============================================================================
# management/capacity/worktime_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kapazitaet (Welle 0)
# =============================================================================
# WorktimeRepo — auditierter Schreibpfad fuer die Regel-Arbeitszeit je
# Wochentag (person_worktime, Schema m008). APPEND-ONLY (mc 2026-07-10,
# Entscheidung 2): set_worktime fuegt eine NEUE datierte Zeile ein; die
# Vorgaengerzeile wird NICHT automatisch per effective_to geschlossen. Der
# Leser (Build 358) nimmt die Zeile mit groesstem effective_from <= Stichtag.
#
# Jede Zeile traegt audit_seq == seq des WORKTIME_SET-Belegs (Kopplung wie
# rbac_grant; after_audit-Hook -> Write+Audit atomar).
#
# Beleg: Bauplan B7 v1.1 §11.4; Muster rbac_repo. mc 2026-07-10.
# Version: v0.7.356 · Build: 356 · 2026-07-10
# =============================================================================

import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.capacity.capacity_errors import CapacityError

_WEEKDAYS = ("mon_min", "tue_min", "wed_min", "thu_min", "fri_min",
             "sat_min", "sun_min")


class WorktimeRepo:
    """Schreibt/liest person_worktime (auditiert, append-only, Soft-Delete)."""

    def __init__(self, con: sqlite3.Connection, writer) -> None:
        self._con = con
        self._writer = writer  # CoordinatorWriter

    # ------------------------------------------------------------------ set
    def set_worktime(self, person_id: int, *, effective_from: str,
                     mon_min: int = 0, tue_min: int = 0, wed_min: int = 0,
                     thu_min: int = 0, fri_min: int = 0, sat_min: int = 0,
                     sun_min: int = 0, effective_to: Optional[str] = None,
                     actor_id: Optional[int] = None,
                     meta: Optional[Any] = None) -> int:
        """
        Neue datierte Arbeitszeit-Regel setzen (append-only). Gibt die
        audit_log-seq (WORKTIME_SET) zurueck.
        """
        if not effective_from:
            raise CapacityError("effective_from ist erforderlich (ISO-Datum).")
        minutes = (mon_min, tue_min, wed_min, thu_min, fri_min, sat_min,
                   sun_min)
        for name, v in zip(_WEEKDAYS, minutes):
            if not isinstance(v, int) or v < 0:
                raise CapacityError(
                    "%s muss eine Minutenzahl >= 0 sein (gefunden: %r)."
                    % (name, v))
            if v > 24 * 60:
                raise CapacityError(
                    "%s > 1440 Minuten (mehr als ein Tag) ist unplausibel." % name)
        now = int(time.time())

        def _w(_con: sqlite3.Connection) -> Dict[str, Any]:
            return {"person_id": person_id, "effective_from": effective_from,
                    "effective_to": effective_to,
                    "minutes": dict(zip(_WEEKDAYS, minutes))}

        def _after(_con: sqlite3.Connection, seq: int) -> None:
            _con.execute(
                "INSERT INTO person_worktime "
                "(person_id, mon_min, tue_min, wed_min, thu_min, fri_min, "
                " sat_min, sun_min, effective_from, effective_to, audit_seq, "
                " created_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (person_id, mon_min, tue_min, wed_min, thu_min, fri_min,
                 sat_min, sun_min, effective_from, effective_to, seq,
                 actor_id, now))

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.WORKTIME_SET,
            actor_id=actor_id, target_type="person_worktime",
            target_id=str(person_id), meta=meta, after_audit=_after)

    # ----------------------------------------------------------------- list
    def list_worktime(self, person_id: Optional[int] = None, *,
                      include_deleted: bool = False) -> List[Dict[str, Any]]:
        sql = ("SELECT id, person_id, mon_min, tue_min, wed_min, thu_min, "
               "fri_min, sat_min, sun_min, effective_from, effective_to, "
               "audit_seq, created_by, created_at, deleted_at "
               "FROM person_worktime")
        clauses = []
        params: list = []
        if not include_deleted:
            clauses.append("deleted_at IS NULL")
        if person_id is not None:
            clauses.append("person_id = ?")
            params.append(person_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY person_id ASC, effective_from ASC, id ASC"
        cur = self._con.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

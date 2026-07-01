# =============================================================================
# management/cases/cases_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Zugriffsschicht auf die Fallakte 'cases' in coordinator.db. Lesende Methode
#   für das Repointing (userinfo_data.py); schreibende Methoden AUSSCHLIESSLICH
#   über das CoordinatorWriter-Gateway, sodass jede cases-Änderung und ihr
#   audit_log-Eintrag in EINER Transaktion committen. Damit gibt es keine
#   Fallzuweisung/Statusänderung ohne lückenlosen Audit-Eintrag.
#   (Beleg: Bauplan B7 v0.3 §3.4, mc 2026-07-01)
#
# Version: v0.7.307 · Build: 307 · 2026-07-01
# =============================================================================

import logging
import sqlite3
import time
from typing import Any, Dict, Optional

from management.audit.event_types import EventType
from management.gateway.coordinator_writer import CoordinatorWriter

logger = logging.getLogger(__name__)


class CasesError(Exception):
    """Fachlicher Fehler (z. B. Fall nicht vorhanden, Fall existiert bereits)."""


class CasesRepo:
    """Auditierte Lese-/Schreibmethoden auf der Tabelle cases."""

    def __init__(self, con: sqlite3.Connection, writer: CoordinatorWriter) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._writer = writer

    # ------------------------------------------------------------------- Lesen
    def get_case(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Liefert die Fallakte als dict (assigned_to als system_username aufgelöst),
        oder None wenn kein Fall existiert. Wird vom Repoint in userinfo_data.py
        genutzt — gleiche Ergebnisform wie zuvor.
        """
        row = self._con.execute(
            "SELECT c.user_id, c.username, c.status, c.priority, "
            "       i.system_username AS assigned_to, c.note, c.approved_at, "
            "       c.total_pages_scraped, c.created_at, c.updated_at "
            "FROM cases c "
            "LEFT JOIN investigators i ON i.id = c.assigned_to "
            "WHERE c.user_id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def _exists(self, con: sqlite3.Connection, user_id: int) -> bool:
        return con.execute(
            "SELECT 1 FROM cases WHERE user_id = ?", (user_id,)
        ).fetchone() is not None

    # --------------------------------------------------------------- Schreiben
    def create_case(
        self, user_id: int, username: str, *,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> int:
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            if self._exists(con, user_id):
                raise CasesError("Fall user_id=%s existiert bereits." % user_id)
            con.execute(
                "INSERT INTO cases "
                "(user_id, username, status, priority, created_at, updated_at) "
                "VALUES (?, ?, 'open', 3, ?, ?)",
                (user_id, username, now, now),
            )
            return {"user_id": user_id, "username": username,
                    "status": "open", "priority": 3}

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.CASE_CREATED,
            actor_id=actor_id, target_type="case", target_id=str(user_id), meta=meta,
        )

    def assign(
        self, user_id: int, investigator_id: Optional[int], *,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> int:
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            cur = con.execute(
                "UPDATE cases SET assigned_to = ?, updated_at = ? WHERE user_id = ?",
                (investigator_id, now, user_id),
            )
            if cur.rowcount == 0:
                raise CasesError("Kein Fall user_id=%s." % user_id)
            return {"user_id": user_id, "assigned_to": investigator_id}

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.CASE_ASSIGNED,
            actor_id=actor_id, target_type="case", target_id=str(user_id), meta=meta,
        )

    def set_status(
        self, user_id: int, status: str, *,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> int:
        now = int(time.time())
        approved = (status == "approved")

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            if approved:
                cur = con.execute(
                    "UPDATE cases SET status = ?, approved_at = ?, updated_at = ? "
                    "WHERE user_id = ?",
                    (status, now, now, user_id),
                )
            else:
                cur = con.execute(
                    "UPDATE cases SET status = ?, updated_at = ? WHERE user_id = ?",
                    (status, now, user_id),
                )
            if cur.rowcount == 0:
                raise CasesError("Kein Fall user_id=%s." % user_id)
            return {"user_id": user_id, "status": status,
                    "approved_at": now if approved else None}

        event = EventType.CASE_APPROVED if approved else EventType.CASE_STATUS_CHANGED
        return self._writer.audited_write(
            do_write=_w, event_type=event,
            actor_id=actor_id, target_type="case", target_id=str(user_id), meta=meta,
        )

    def set_priority(
        self, user_id: int, priority: int, *,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> int:
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            cur = con.execute(
                "UPDATE cases SET priority = ?, updated_at = ? WHERE user_id = ?",
                (priority, now, user_id),
            )
            if cur.rowcount == 0:
                raise CasesError("Kein Fall user_id=%s." % user_id)
            return {"user_id": user_id, "priority": priority}

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.CASE_PRIORITY_SET,
            actor_id=actor_id, target_type="case", target_id=str(user_id), meta=meta,
        )

    def set_note(
        self, user_id: int, note: Optional[str], *,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> int:
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            cur = con.execute(
                "UPDATE cases SET note = ?, updated_at = ? WHERE user_id = ?",
                (note, now, user_id),
            )
            if cur.rowcount == 0:
                raise CasesError("Kein Fall user_id=%s." % user_id)
            # Notiztext NICHT in den Audit-Payload spiegeln (kann sensibel sein);
            # nur die Tatsache 'Notiz gesetzt' + Länge protokollieren.
            return {"user_id": user_id, "note_len": len(note) if note else 0}

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.CASE_NOTE_SET,
            actor_id=actor_id, target_type="case", target_id=str(user_id), meta=meta,
        )

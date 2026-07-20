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
# Version: v0.7.469 · Build: 469 · 2026-07-20
#   Build 469: Schluesselumstellung user_id -> subject_id (M019)
#   Build 313: create_case/assign/set_status spiegeln zusätzlich eine
#   Zeitstrahl-Zeile nach case_events (after_audit-Hook, atomar mit Write
#   und Audit-Beleg; audit_seq = seq des CASE_*-Belegs). set_priority und
#   set_note werden BEWUSST NICHT gespiegelt (mc 2026-07-02: Zuweisungen,
#   Statuswechsel, Freigaben; Anlage als Zeitstrahl-Anker ergänzt, s. u.).
#   Beleg: Bauplan B7 v0.8 §8.4.
# =============================================================================

import logging
import sqlite3
import time
from typing import Any, Dict, Optional

from management.audit.event_types import EventType
from management.case_events.case_events_repo import insert_event_row
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
    def get_case(self, subject_id: int) -> Optional[Dict[str, Any]]:
        """
        Liefert die Fallakte als dict (assigned_to als system_username aufgelöst),
        oder None wenn kein Fall existiert. Wird vom Repoint in userinfo_data.py
        genutzt — gleiche Ergebnisform wie zuvor.
        """
        row = self._con.execute(
            "SELECT c.subject_id, c.username, c.status, c.priority, "
            "       i.system_username AS assigned_to, c.note, c.approved_at, "
            "       c.total_pages_scraped, c.created_at, c.updated_at "
            "FROM cases c "
            "LEFT JOIN person i ON i.id = c.assigned_to "
            "WHERE c.subject_id = ?",
            (subject_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def _exists(self, con: sqlite3.Connection, subject_id: int) -> bool:
        return con.execute(
            "SELECT 1 FROM cases WHERE subject_id = ?", (subject_id,)
        ).fetchone() is not None

    # --------------------------------------------------------------- Schreiben
    def create_case(
        self, subject_id: int, username: str, *,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> int:
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            if self._exists(con, subject_id):
                raise CasesError("Fall subject_id=%s existiert bereits." % subject_id)
            con.execute(
                "INSERT INTO cases "
                "(subject_id, username, status, priority, created_at, updated_at) "
                "VALUES (?, ?, 'open', 3, ?, ?)",
                (subject_id, username, now, now),
            )
            return {"subject_id": subject_id, "username": username,
                    "status": "open", "priority": 3}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            # Zeitstrahl-Anker: ohne 'Fall angelegt' hätte der Zeitstrahl
            # keinen Startpunkt (Bauplan B7 v0.8 §8.4).
            insert_event_row(
                con, subject_id=subject_id, event_kind="case_created",
                payload={"username": username},
                created_by=actor_id, created_at=now, audit_seq=seq,
            )

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.CASE_CREATED,
            actor_id=actor_id, target_type="case", target_id=str(subject_id), meta=meta,
            after_audit=_after,
        )

    def assign(
        self, subject_id: int, person_id: Optional[int], *,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> int:
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            cur = con.execute(
                "UPDATE cases SET assigned_to = ?, updated_at = ? WHERE subject_id = ?",
                (person_id, now, subject_id),
            )
            if cur.rowcount == 0:
                raise CasesError("Kein Fall subject_id=%s." % subject_id)
            return {"subject_id": subject_id, "assigned_to": person_id}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            # Spiegelung Zuweisung (mc 2026-07-02). assigned_to=None ist die
            # dokumentierte Entzugs-Form und erscheint ebenso im Zeitstrahl.
            insert_event_row(
                con, subject_id=subject_id, event_kind="assigned",
                payload={"assigned_to": person_id},
                created_by=actor_id, created_at=now, audit_seq=seq,
            )

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.CASE_ASSIGNED,
            actor_id=actor_id, target_type="case", target_id=str(subject_id), meta=meta,
            after_audit=_after,
        )

    def set_status(
        self, subject_id: int, status: str, *,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> int:
        now = int(time.time())
        approved = (status == "approved")

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            if approved:
                cur = con.execute(
                    "UPDATE cases SET status = ?, approved_at = ?, updated_at = ? "
                    "WHERE subject_id = ?",
                    (status, now, now, subject_id),
                )
            else:
                cur = con.execute(
                    "UPDATE cases SET status = ?, updated_at = ? WHERE subject_id = ?",
                    (status, now, subject_id),
                )
            if cur.rowcount == 0:
                raise CasesError("Kein Fall subject_id=%s." % subject_id)
            return {"subject_id": subject_id, "status": status,
                    "approved_at": now if approved else None}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            # Spiegelung Statuswechsel/Freigabe (mc 2026-07-02). 'approved'
            # ist als eigener kind ausgewiesen — das Dashboard (Tag 3) kann
            # Freigaben damit ohne Payload-Parsing hervorheben.
            insert_event_row(
                con, subject_id=subject_id,
                event_kind="approved" if approved else "status_changed",
                payload={"status": status,
                         "approved_at": now} if approved else {"status": status},
                created_by=actor_id, created_at=now, audit_seq=seq,
            )

        event = EventType.CASE_APPROVED if approved else EventType.CASE_STATUS_CHANGED
        return self._writer.audited_write(
            do_write=_w, event_type=event,
            actor_id=actor_id, target_type="case", target_id=str(subject_id), meta=meta,
            after_audit=_after,
        )

    def set_priority(
        self, subject_id: int, priority: int, *,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> int:
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            cur = con.execute(
                "UPDATE cases SET priority = ?, updated_at = ? WHERE subject_id = ?",
                (priority, now, subject_id),
            )
            if cur.rowcount == 0:
                raise CasesError("Kein Fall subject_id=%s." % subject_id)
            return {"subject_id": subject_id, "priority": priority}

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.CASE_PRIORITY_SET,
            actor_id=actor_id, target_type="case", target_id=str(subject_id), meta=meta,
        )

    def set_note(
        self, subject_id: int, note: Optional[str], *,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> int:
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            cur = con.execute(
                "UPDATE cases SET note = ?, updated_at = ? WHERE subject_id = ?",
                (note, now, subject_id),
            )
            if cur.rowcount == 0:
                raise CasesError("Kein Fall subject_id=%s." % subject_id)
            # Notiztext NICHT in den Audit-Payload spiegeln (kann sensibel sein);
            # nur die Tatsache 'Notiz gesetzt' + Länge protokollieren.
            return {"subject_id": subject_id, "note_len": len(note) if note else 0}

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.CASE_NOTE_SET,
            actor_id=actor_id, target_type="case", target_id=str(subject_id), meta=meta,
        )

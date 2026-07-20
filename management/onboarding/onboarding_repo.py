# =============================================================================
# management/onboarding/onboarding_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Onboarding/Offboarding (AP-2G)
# =============================================================================
# Zweck (Idee 31):
#   Zugriffsschicht auf 'onboarding_item' (M017). SCHREIBEN ausschliesslich ueber
#   das CoordinatorWriter-Gateway: fachlicher Write + audit_log-Beleg committen in
#   EINER Transaktion oder gar nicht. Keine Checklisten-Aenderung ohne Beleg (GR1).
#
#   Der Lesepfad liefert IMMER ALLE Katalog-Schritte (auch die noch offenen) —
#   ein offener Schritt wird NICHT verschluckt, sondern ausdruecklich als 'offen'
#   gezeigt (Grundregel 1). 'offen' ist die Abwesenheit einer Zeile; ein Reset
#   auf 'offen' LOESCHT die Zeile (auditiert).
#
# SENSIBILITAETSREGEL: Freitext (note) geht NICHT in den audit_log-Payload — nur
#   FAKTEN (person_id, kind, step_code, status) + Textlaenge.
#
# KOPPLUNG/NUTZEN (read-only): open_case_load() zaehlt die noch OFFEN zugewiesenen
#   Faelle einer Person (cases.assigned_to, status open/in_progress) — macht den
#   Offboarding-Schritt "Faelle umverteilt" konkret nachpruefbar.
#
# Version: v0.7.464 · Build: 464 · 2026-07-20
# =============================================================================

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.gateway.coordinator_writer import CoordinatorWriter
from management.onboarding.checklist_status import (
    ChecklistStatus,
    ChecklistStatusError,
    INITIAL,
)

logger = logging.getLogger(__name__)

#: Fallzustaende, die eine Zuweisung als "noch offen" gelten lassen.
_OPEN_CASE_STATUSES = ("open", "in_progress")


class OnboardingError(Exception):
    """Fachlicher Fehler (unbekannte Person/Art/Schritt, ungueltige Eingabe)."""


class OnboardingRepo:
    """Auditierte Lese-/Schreibmethoden auf 'onboarding_item'."""

    def __init__(self, con: sqlite3.Connection,
                 writer: Optional[CoordinatorWriter] = None) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._writer = writer

    # ------------------------------------------------------------------ Hilfen
    def _require_writer(self) -> CoordinatorWriter:
        if self._writer is None:
            raise OnboardingError(
                "Schreibzugriff ohne CoordinatorWriter — kein unauditierter "
                "Schreibpfad zulaessig.")
        return self._writer

    @staticmethod
    def _tlen(text: Optional[str]) -> int:
        return len(text or "")

    def _person_exists(self, con: sqlite3.Connection, person_id: int) -> bool:
        return con.execute(
            "SELECT 1 FROM person WHERE id = ?", (person_id,)
        ).fetchone() is not None

    def _row(self, con: sqlite3.Connection, person_id: int, kind: str,
             step_code: str) -> Optional[sqlite3.Row]:
        return con.execute(
            "SELECT * FROM onboarding_item "
            "WHERE person_id = ? AND kind = ? AND step_code = ?",
            (person_id, kind, step_code)).fetchone()

    # ------------------------------------------------------------------- Lesen
    def get(self, person_id: int, kind: str,
            step_code: str) -> Optional[Dict[str, Any]]:
        row = self._row(self._con, int(person_id), kind, step_code)
        return dict(row) if row is not None else None

    def checklist(self, person_id: int, kind: str) -> List[Dict[str, Any]]:
        """
        ALLE Schritte des Katalogs 'kind' fuer eine Person, mit ihrem (impliziten)
        Zustand + Klartext-Labels. Kein Schritt wird verschluckt (GR1).
        """
        ChecklistStatus.require_kind(kind)
        pid = int(person_id)
        rows = {
            r["step_code"]: r for r in self._con.execute(
                "SELECT * FROM onboarding_item WHERE person_id = ? AND kind = ?",
                (pid, kind)).fetchall()
        }
        out: List[Dict[str, Any]] = []
        for code, label in ChecklistStatus.steps(kind):
            row = rows.get(code)
            status = row["status"] if row is not None else INITIAL
            out.append({
                "step_code": code,
                "label": label,
                "status": status,
                "status_label": ChecklistStatus.label(status),
                "note": (row["note"] if row is not None else None),
                "done_by": (row["done_by"] if row is not None else None),
                "done_at": (row["done_at"] if row is not None else None),
                "requires_reason": ChecklistStatus.requires_reason(status),
            })
        return out

    def open_case_load(self, person_id: int) -> int:
        """Anzahl der noch OFFEN zugewiesenen Faelle einer Person (read-only)."""
        marks = ",".join("?" for _ in _OPEN_CASE_STATUSES)
        row = self._con.execute(
            "SELECT COUNT(*) FROM cases WHERE assigned_to = ? "
            "AND status IN (%s)" % marks,
            (int(person_id), *_OPEN_CASE_STATUSES)).fetchone()
        return int(row[0])

    # --------------------------------------------------------------- Schreiben
    def set_step(
        self, *, person_id: int, kind: str, step_code: str, status: str,
        note: str = "", actor_id: Optional[int] = None,
        meta: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Setzt einen Checklisten-Schritt (erledigt/nicht_zutreffend) ODER setzt ihn
        auf 'offen' zurueck (loescht die Zeile). Auditiert.
        -> {'status', 'audit_seq', 'created', 'removed'}.
        """
        writer = self._require_writer()
        pid = int(person_id)

        try:
            ChecklistStatus.require_step(kind, step_code)
            ChecklistStatus.require_status(status)
            ChecklistStatus.check_reason(status, note)
        except ChecklistStatusError as exc:
            raise OnboardingError(str(exc)) from exc

        now = int(time.time())
        state: Dict[str, Any] = {"created": False, "removed": False}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            if not self._person_exists(con, pid):
                raise OnboardingError("Keine Person id=%s." % pid)
            row = self._row(con, pid, kind, step_code)

            if status == INITIAL:
                # RESET auf 'offen' -> Zeile loeschen (die Historie liegt im
                # audit_log). Nichts vorhanden = No-op, aber der Beleg wird
                # dennoch geschrieben (jemand hat den Schritt bewusst geoeffnet).
                if row is not None:
                    con.execute(
                        "DELETE FROM onboarding_item WHERE id = ?", (row["id"],))
                    state["removed"] = True
                return {
                    "person_id": pid, "kind": kind, "step_code": step_code,
                    "status": INITIAL, "note_len": 0,
                }

            if row is None:
                con.execute(
                    "INSERT INTO onboarding_item "
                    "(person_id, kind, step_code, status, note, done_by, "
                    " done_at, created_at, audit_seq, created_audit_seq) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0)",
                    (pid, kind, step_code, status, (note or None),
                     actor_id, now, now),
                )
                state["created"] = True
                state["row_id"] = int(
                    con.execute("SELECT id FROM onboarding_item WHERE "
                                "person_id=? AND kind=? AND step_code=?",
                                (pid, kind, step_code)).fetchone()[0])
            else:
                con.execute(
                    "UPDATE onboarding_item SET status = ?, note = ?, "
                    "done_by = ?, done_at = ? WHERE id = ?",
                    (status, (note or None), actor_id, now, row["id"]),
                )
                state["row_id"] = int(row["id"])

            return {
                "person_id": pid, "kind": kind, "step_code": step_code,
                "status": status, "note_len": self._tlen(note),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            # Bei RESET (removed/kein row) gibt es keine Zeile zum Nachtragen.
            if "row_id" not in state:
                return
            if state["created"]:
                con.execute(
                    "UPDATE onboarding_item SET audit_seq = ?, "
                    "created_audit_seq = ? WHERE id = ?",
                    (seq, seq, state["row_id"]),
                )
            else:
                con.execute(
                    "UPDATE onboarding_item SET audit_seq = ? WHERE id = ?",
                    (seq, state["row_id"]),
                )

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.ONBOARDING_STEP_SET,
            actor_id=actor_id, target_type="onboarding_item",
            target_id=None, meta=meta, after_audit=_after,
        )
        logger.info("Checkliste %s/%s Person %s -> %s (Beleg #%d).",
                    kind, step_code, pid, status, seq)
        return {"status": status, "audit_seq": seq,
                "created": state["created"], "removed": state["removed"]}

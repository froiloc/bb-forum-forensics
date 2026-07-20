# =============================================================================
# management/cases/case_importer.py
# IT-Forensisches Ermittlungswerkzeug — Fall-Autodetektion
# =============================================================================
# CaseImporter — nimmt die vom CaseDetector als 'neu' erkannten Faelle in die
# Fallakte (coordinator.db -> cases) auf.
#
# AUDITIERT: Das Anlegen laeuft AUSSCHLIESSLICH ueber CasesRepo.create_case und
#   damit ueber den CoordinatorWriter — jeder aufgenommene Fall erzeugt zwingend
#   seinen audit_log-Beleg (case_created). Kein Direkt-SQL.
#
# AUF KNOPFDRUCK (mc 2026-07-10): Die Detektion liest nur; das Aufnehmen ist ein
#   bewusster, belegter Vorgang. Der CLI bietet zusaetzlich '--auto' fuer
#   Skripte — auch dort wird jeder Fall einzeln auditiert.
#
# GRUNDREGEL 1: Faelle ohne gueltigen Benutzernamen (uid_profile unlesbar) werden
#   NICHT aufgenommen und NICHT verschwiegen, sondern als 'skipped' gemeldet.
#   Ein Fehlschlag bei einem Fall bricht den Rest nicht ab — er wird gemeldet.
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import logging
import sqlite3
from typing import Any, Dict, Iterable, List, Optional

from management.audit.audit_log import AuditLog
from management.cases.case_detector import CaseDetector
from management.cases.cases_repo import CasesRepo
from management.gateway.coordinator_writer import CoordinatorWriter

logger = logging.getLogger(__name__)


class CaseImporter:
    """Nimmt neu erkannte Faelle auditiert in die Fallakte auf."""

    def __init__(self, con: sqlite3.Connection,
                 detector: CaseDetector) -> None:
        self._con = con
        self._detector = detector

    def import_cases(self, *, actor_id: int,
                     subject_ids: Optional[Iterable[int]] = None,
                     all_new: bool = False) -> Dict[str, Any]:
        """
        Nimmt Faelle auf. Entweder eine explizite Auswahl (subject_ids) ODER alle
        neu erkannten (all_new=True). Gibt einen Bericht zurueck.
        """
        candidates = {c.subject_id: c for c in self._detector.importable()}

        if all_new:
            wanted = list(candidates)
        else:
            wanted = [int(u) for u in (subject_ids or [])]

        imported: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []

        if not wanted:
            return {"imported": [], "skipped": [], "count": 0,
                    "detail": "Keine Faelle zur Aufnahme ausgewaehlt."}

        writer = CoordinatorWriter(self._con, AuditLog(self._con))
        repo = CasesRepo(self._con, writer)

        for uid in sorted(set(wanted)):
            cand = candidates.get(uid)
            if cand is None:
                # Nicht (mehr) aufnehmbar: bereits erfasst, vermisst oder
                # unlesbar. NICHT still uebergehen (Grundregel 1).
                skipped.append({
                    "subject_id": uid,
                    "reason": "nicht aufnehmbar (bereits erfasst, vermisst "
                              "oder Benutzername unlesbar)"})
                continue

            try:
                seq = repo.create_case(uid, cand.username, actor_id=actor_id)
            except Exception as exc:      # Ein Fehler stoppt den Rest nicht.
                logger.warning("Fall %s konnte nicht aufgenommen werden: %s",
                               uid, exc)
                skipped.append({"subject_id": uid, "reason": str(exc)})
                continue

            imported.append({"subject_id": uid, "username": cand.username,
                             "audit_seq": seq})
            logger.info("Fall %s (%s) aufgenommen, Beleg #%s",
                        uid, cand.username, seq)

        return {"imported": imported, "skipped": skipped,
                "count": len(imported)}

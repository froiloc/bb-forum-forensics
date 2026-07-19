# =============================================================================
# management/cases/escalation_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fallsteuerung (AP-2F)
# =============================================================================
# Zweck:
#   Holt die CaseOverview je Fall (DashboardRepo, read-only) und uebergibt sie
#   an die reine evaluate_escalations. DB-Zugriff hier, Regeln in escalation.py.
#
# Version: v0.7.453 · Build: 453 · 2026-07-19
# =============================================================================

from __future__ import annotations

import dataclasses
import sqlite3
import time
from typing import Optional

from management.dashboard.dashboard_repo import (
    DashboardRepo, DEFAULT_AMPEL_THRESHOLDS,
)
from management.cases.escalation import (
    evaluate_escalations, EscalationThresholds, EscalationReport,
)


class EscalationRepo:
    """Read-Model: belegte Eskalationen aus dem Fallzustand."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def compute(self, *, thresholds: Optional[EscalationThresholds] = None,
                now: Optional[int] = None) -> EscalationReport:
        thresholds = thresholds or EscalationThresholds()
        now = int(time.time()) if now is None else int(now)
        overviews = DashboardRepo(self._con).list_case_overview(
            thresholds=DEFAULT_AMPEL_THRESHOLDS, now=now)
        rows = [dataclasses.asdict(o) for o in overviews]
        return evaluate_escalations(rows, thresholds, now)

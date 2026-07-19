# =============================================================================
# management/cases/next_actions_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fallsteuerung (AP-2F)
# =============================================================================
# Zweck:
#   Holt die CaseOverview je Fall (DashboardRepo, read-only), filtert nach Scope
#   und uebergibt sie an die reine build_queue (management.cases.next_actions).
#   Trennung: DB-Zugriff hier, Ableitungslogik in next_actions (testbar).
#
# Version: v0.7.452 · Build: 452 · 2026-07-19
# =============================================================================

from __future__ import annotations

import dataclasses
import sqlite3
import time
from typing import Optional

from management.dashboard.dashboard_repo import (
    DashboardRepo, DEFAULT_AMPEL_THRESHOLDS,
)
from management.cases.next_actions import build_queue, QueueResult


class NextActionsRepo:
    """Read-Model: priorisierte 'naechstbeste Aktion'-Warteschlange."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def compute(self, *, scope: str = "alle",
                person_id: Optional[int] = None,
                now: Optional[int] = None) -> QueueResult:
        now = int(time.time()) if now is None else int(now)
        overviews = DashboardRepo(self._con).list_case_overview(
            thresholds=DEFAULT_AMPEL_THRESHOLDS, now=now)
        rows = [dataclasses.asdict(o) for o in overviews]
        if scope == "eigene":
            # Nur die dem/der Ermittler:in zugewiesenen Faelle.
            rows = [r for r in rows if r.get("assigned_to") == person_id]
        return build_queue(rows, scope, now)

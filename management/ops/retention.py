# =============================================================================
# management/ops/retention.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Betrieb/Governance (AP-2G)
# =============================================================================
# Zweck (Idee 29 — Datenschutz-/Loeschkonzept, Auswertungsteil):
#   Rein lesende Aufbewahrungs-Uebersicht: abgeschlossene Faelle (Status
#   'closed'/'approved'), deren Aufbewahrungsfrist abgelaufen ist, werden als
#   KANDIDATEN ZUR LOESCHPRUEFUNG ausgewiesen.
#
#   NIEMALS LOESCHEN (verbindlich): Dieses Modul erhebt NUR einen Vorschlag zur
#   Pruefung. Das tatsaechliche Loeschen ist eine auditierte Governance-
#   Entscheidung und NICHT Teil dieses read-only-Read-Models. So bleibt der
#   Grundsatz "kein Beleg geht verloren" (GR1) unangetastet.
#
#   FRIST-BEZUGSZEITPUNKT (belegt, nicht geraten):
#     * Status 'approved' -> approved_at (forensische Abschluss-Tatsache).
#     * Status 'closed'   -> updated_at  (es gibt keine eigene closed_at-Spalte;
#                            updated_at ist der beste vorhandene Bezug — der
#                            Vermerk macht das transparent).
#   Fehlt der Bezugszeitpunkt -> Fall wird als 'ohne Fristbezug' gefuehrt (NICHT
#   stillschweigend als Kandidat, GR1).
#
#   Vorgabefrist 730 Tage (2-Jahres-Horizont); via config.yaml retention.* /
#   Parameter uebersteuerbar. now injizierbar -> deterministisch/testbar.
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import List, Optional

_DAY = 86400
_CLOSED_STATUSES = ("closed", "approved")


@dataclass(frozen=True)
class RetentionThresholds:
    retention_days: int = 730      # Aufbewahrungsfrist (Vorgabe: 2 Jahre)


@dataclass(frozen=True)
class RetentionCandidate:
    subject_id: int
    username: str
    status: str
    reference_ts: int              # Fristbezug (approved_at bzw. updated_at)
    reference_field: str           # 'approved_at' | 'updated_at'
    days_retained: int
    over_by_days: int              # Ueberschreitung der Frist


@dataclass(frozen=True)
class RetentionReport:
    generated_at: int
    retention_days: int
    total_cases: int
    closed_cases: int
    without_reference: int
    candidates: List[RetentionCandidate]
    candidate_count: int


def evaluate_retention(cases: List[dict], thresholds: RetentionThresholds,
                       now: int) -> RetentionReport:
    """
    REINE Auswertung ueber cases-dicts (subject_id, username, status, approved_at,
    updated_at). Dateilos testbar.
    """
    now = int(now)
    candidates: List[RetentionCandidate] = []
    closed = 0
    without_ref = 0

    for c in cases:
        status = c.get("status")
        if status not in _CLOSED_STATUSES:
            continue
        closed += 1
        if status == "approved":
            ref = c.get("approved_at")
            field = "approved_at"
            if ref is None:                      # Rueckfall, sollte selten sein
                ref = c.get("updated_at")
                field = "updated_at"
        else:  # closed
            ref = c.get("updated_at")
            field = "updated_at"

        if ref is None:
            without_ref += 1
            continue

        days = max(0, (now - int(ref)) // _DAY)
        if days >= thresholds.retention_days:
            candidates.append(RetentionCandidate(
                subject_id=int(c.get("subject_id")),
                username=c.get("username") or "?", status=status,
                reference_ts=int(ref), reference_field=field,
                days_retained=days,
                over_by_days=days - thresholds.retention_days))

    # Aelteste zuerst (groesste Ueberschreitung), dann subject_id.
    candidates.sort(key=lambda x: (-x.over_by_days, x.subject_id))

    return RetentionReport(
        generated_at=now, retention_days=thresholds.retention_days,
        total_cases=len(cases), closed_cases=closed,
        without_reference=without_ref, candidates=candidates,
        candidate_count=len(candidates))


def retention_thresholds_from_config(cfg) -> RetentionThresholds:
    d = RetentionThresholds()
    if cfg is None:
        return d
    try:
        node = cfg.get("retention", {}) or {}
        return RetentionThresholds(
            retention_days=int(node.get("retention_days", d.retention_days)))
    except Exception:
        return d


def retention_to_dict(report: RetentionReport) -> dict:
    return {
        "generated_at": report.generated_at,
        "retention_days": report.retention_days,
        "total_cases": report.total_cases,
        "closed_cases": report.closed_cases,
        "without_reference": report.without_reference,
        "candidate_count": report.candidate_count,
        "candidates": [
            {"subject_id": c.subject_id, "username": c.username, "status": c.status,
             "reference_ts": c.reference_ts, "reference_field": c.reference_field,
             "days_retained": c.days_retained, "over_by_days": c.over_by_days}
            for c in report.candidates
        ],
    }


class RetentionRepo:
    """Read-Model: Aufbewahrungs-/Loeschfristen-Uebersicht (read-only)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def compute(self, *, thresholds: Optional[RetentionThresholds] = None,
                now: Optional[int] = None) -> RetentionReport:
        thresholds = thresholds or RetentionThresholds()
        now = int(time.time()) if now is None else int(now)
        rows = self._con.execute(
            "SELECT subject_id, username, status, approved_at, updated_at "
            "FROM cases").fetchall()
        cases = [
            {"subject_id": r[0], "username": r[1], "status": r[2],
             "approved_at": r[3], "updated_at": r[4]}
            for r in rows
        ]
        return evaluate_retention(cases, thresholds, now)

# =============================================================================
# management/workload/overload.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Lastverteilung (AP-2F)
# =============================================================================
# Zweck (Idee 21 — aktive Ueberlastwarnung):
#   Bislang war "Ueberlast" nur eine Ampelfarbe in der Lastverteilung. Dieses
#   Read-Model wertet die JE ERMITTLER gemessenen Lastzahlen (WorkloadRepo /
#   InvestigatorLoad) gegen KONFIGURIERBARE Schwellen aus und erhebt daraus eine
#   AKTIVE Warnung (Stufe ok/warn/overload) mit benannten Ausloesern.
#
#   MESSEN, NICHT RATEN (GR1): Grundlage sind die bereits belegten Zaehlungen
#   active_cases (open+in_progress) und ampel_rot je Ermittler. Der unzugewiesene
#   Rueckstau (is_backlog) ist KEINE Personen-Ueberlast, sondern ein SYSTEMISCHES
#   Signal -> separat als backlog_size + backlog_alert ausgewiesen.
#
#   Schwellenbedeutung eindeutig: 'warn' = Schwelle ERREICHT (einer mehr kippt),
#   'overload' = Schwelle UEBERSCHRITTEN. Rein lesend; now injizierbar.
#
# Version: v0.7.451 · Build: 451 · 2026-07-19
# =============================================================================

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import List, Optional

from management.workload.workload_repo import WorkloadRepo


@dataclass(frozen=True)
class OverloadThresholds:
    """Konfigurierbare Grenzwerte (Vorgaben; via config.yaml uebersteuerbar)."""
    max_active_cases: int = 10     # aktive Faelle (open+in_progress) je Ermittler
    max_red_cases: int = 3         # rote Faelle je Ermittler
    backlog_alert: int = 5         # unzugewiesener Rueckstau ab dieser Groesse


@dataclass(frozen=True)
class OverloadAssessment:
    investigator_id: int
    name: str
    active_cases: int
    red_cases: int
    total_cases: int
    level: str                     # 'ok' | 'warn' | 'overload'
    reasons: List[str]


@dataclass(frozen=True)
class OverloadReport:
    generated_at: int
    max_active_cases: int
    max_red_cases: int
    backlog_alert: int
    assessments: List[OverloadAssessment]
    overloaded_count: int
    warned_count: int
    backlog_size: int
    backlog_alarm: bool


def assess_load(load, thresholds: OverloadThresholds) -> OverloadAssessment:
    """
    REINE Bewertung EINER (Nicht-Rueckstau-)Lastzeile gegen die Schwellen.
    Ausloeser werden einzeln benannt (nachvollziehbar, GR1).
    """
    active = int(load.active_cases)
    red = int(load.ampel_rot)
    reasons: List[str] = []

    over_active = active > thresholds.max_active_cases
    over_red = red > thresholds.max_red_cases
    at_active = active == thresholds.max_active_cases
    at_red = red == thresholds.max_red_cases

    if over_active:
        reasons.append("aktive Faelle %d > Grenze %d"
                       % (active, thresholds.max_active_cases))
    elif at_active:
        reasons.append("aktive Faelle %d = Grenze %d (erreicht)"
                       % (active, thresholds.max_active_cases))
    if over_red:
        reasons.append("rote Faelle %d > Grenze %d"
                       % (red, thresholds.max_red_cases))
    elif at_red:
        reasons.append("rote Faelle %d = Grenze %d (erreicht)"
                       % (red, thresholds.max_red_cases))

    if over_active or over_red:
        level = "overload"
    elif at_active or at_red:
        level = "warn"
    else:
        level = "ok"

    name = load.display_name or load.system_username or ("#%d" % load.investigator_id)
    return OverloadAssessment(
        investigator_id=int(load.investigator_id), name=name,
        active_cases=active, red_cases=red, total_cases=int(load.total_cases),
        level=level, reasons=reasons)


def build_report(loads, thresholds: OverloadThresholds,
                 now: int) -> OverloadReport:
    """
    REINE Report-Bildung aus einer InvestigatorLoad-Liste (dateilos testbar).
    Der Rueckstau (is_backlog) fliesst NICHT in die Personen-Bewertung, sondern
    in backlog_size/backlog_alarm.
    """
    assessments: List[OverloadAssessment] = []
    backlog_size = 0
    for load in loads:
        if getattr(load, "is_backlog", False):
            backlog_size = int(load.total_cases)
            continue
        assessments.append(assess_load(load, thresholds))

    # Ordnung: dringlichste zuerst (overload > warn > ok), dann meiste aktive.
    rank = {"overload": 0, "warn": 1, "ok": 2}
    assessments.sort(key=lambda a: (rank[a.level], -a.active_cases,
                                    a.investigator_id))

    overloaded = sum(1 for a in assessments if a.level == "overload")
    warned = sum(1 for a in assessments if a.level == "warn")

    return OverloadReport(
        generated_at=int(now),
        max_active_cases=thresholds.max_active_cases,
        max_red_cases=thresholds.max_red_cases,
        backlog_alert=thresholds.backlog_alert,
        assessments=assessments,
        overloaded_count=overloaded, warned_count=warned,
        backlog_size=backlog_size,
        backlog_alarm=backlog_size >= thresholds.backlog_alert)


class OverloadEvaluator:
    """Erhebt aus der Lastverteilung eine aktive Ueberlastwarnung (read-only)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def evaluate(self, *, thresholds: Optional[OverloadThresholds] = None,
                 now: Optional[int] = None) -> OverloadReport:
        thresholds = thresholds or OverloadThresholds()
        now = int(time.time()) if now is None else int(now)
        loads = WorkloadRepo(self._con).list_workload(now=now)
        return build_report(loads, thresholds, now)


def overload_thresholds_from_config(cfg) -> OverloadThresholds:
    """
    Grenzwerte aus config.yaml (workload.overload.*), sonst Vorgaben. Voll
    abgesichert -> bei Fehlern Vorgaben (kein harter Ausfall).
    """
    d = OverloadThresholds()
    if cfg is None:
        return d
    try:
        node = (cfg.get("workload", {}) or {}).get("overload", {}) or {}
        return OverloadThresholds(
            max_active_cases=int(node.get("max_active_cases", d.max_active_cases)),
            max_red_cases=int(node.get("max_red_cases", d.max_red_cases)),
            backlog_alert=int(node.get("backlog_alert", d.backlog_alert)))
    except Exception:
        return d


def overload_to_dict(report: OverloadReport) -> dict:
    """Serialisierung fuer Sicht/CLI (stabile Schluessel)."""
    return {
        "generated_at": report.generated_at,
        "max_active_cases": report.max_active_cases,
        "max_red_cases": report.max_red_cases,
        "backlog_alert": report.backlog_alert,
        "overloaded_count": report.overloaded_count,
        "warned_count": report.warned_count,
        "backlog_size": report.backlog_size,
        "backlog_alarm": report.backlog_alarm,
        "assessments": [
            {"investigator_id": a.investigator_id, "name": a.name,
             "active_cases": a.active_cases, "red_cases": a.red_cases,
             "total_cases": a.total_cases, "level": a.level, "reasons": a.reasons}
            for a in report.assessments
        ],
    }

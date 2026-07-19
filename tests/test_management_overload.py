# =============================================================================
# tests/test_management_overload.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Ueberlastwarnung (AP-2F)
# =============================================================================
# Testsuite fuer Build 451: aktive Ueberlastwarnung (overload).
#
# OV01 — assess_load ok: unter allen Schwellen
# OV02 — assess_load warn: aktive Faelle == Grenze (erreicht)
# OV03 — assess_load overload: aktive Faelle > Grenze; Ausloeser benannt
# OV04 — assess_load overload: rote Faelle > Grenze
# OV05 — build_report: Rueckstau NICHT als Person bewertet -> backlog_size/alarm
# OV06 — build_report: Sortierung overload > warn > ok, dann aktive absteigend
# OV07 — build_report: overloaded_count/warned_count korrekt
# OV08 — overload_thresholds_from_config: Vorgaben ohne cfg; None-sicher
#
# Version: v0.7.451 · Build: 451 · 2026-07-19
# =============================================================================

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.workload.investigator_load import InvestigatorLoad   # noqa: E402
from management.workload.overload import (                            # noqa: E402
    OverloadThresholds, assess_load, build_report,
    overload_thresholds_from_config, overload_to_dict,
)

_TH = OverloadThresholds(max_active_cases=10, max_red_cases=3, backlog_alert=5)


def _load(iid, *, active, red, total=None, backlog=False, name="P"):
    total = total if total is not None else active
    return InvestigatorLoad(
        investigator_id=iid, system_username="h%03d" % iid, display_name=name,
        is_investigator=True, is_supervisor=False, is_support=False,
        is_backlog=backlog, total_cases=total, ampel_rot=red, ampel_gelb=0,
        ampel_gruen=0, status_open=active, status_in_progress=0,
        status_approved=0, status_closed=0, active_cases=active, done_cases=0,
        audit_action_count=0, last_action_at=None)


def test_ov01_ok():
    a = assess_load(_load(1, active=4, red=1), _TH)
    assert a.level == "ok" and a.reasons == []


def test_ov02_warn_at_threshold():
    a = assess_load(_load(1, active=10, red=0), _TH)
    assert a.level == "warn"
    assert any("erreicht" in r for r in a.reasons)


def test_ov03_overload_active():
    a = assess_load(_load(1, active=12, red=0), _TH)
    assert a.level == "overload"
    assert any("aktive Faelle 12 > Grenze 10" in r for r in a.reasons)


def test_ov04_overload_red():
    a = assess_load(_load(1, active=2, red=5), _TH)
    assert a.level == "overload"
    assert any("rote Faelle 5 > Grenze 3" in r for r in a.reasons)


def test_ov05_backlog_not_a_person():
    loads = [
        _load(1, active=2, red=0),
        _load(0, active=0, red=0, total=7, backlog=True, name="(nicht zugewiesen)"),
    ]
    rep = build_report(loads, _TH, now=1000)
    assert len(rep.assessments) == 1          # Rueckstau nicht bewertet
    assert rep.backlog_size == 7 and rep.backlog_alarm is True


def test_ov06_sorting():
    loads = [
        _load(1, active=4, red=0),            # ok
        _load(2, active=12, red=0),           # overload
        _load(3, active=10, red=0),           # warn
        _load(4, active=15, red=0),           # overload (mehr aktive)
    ]
    rep = build_report(loads, _TH, now=1000)
    levels = [a.level for a in rep.assessments]
    assert levels[0] == "overload" and levels[-1] == "ok"
    # zwei overloads: der mit mehr aktiven zuerst
    assert rep.assessments[0].investigator_id == 4
    assert rep.assessments[1].investigator_id == 2


def test_ov07_counts():
    loads = [_load(1, active=12, red=0), _load(2, active=10, red=0),
             _load(3, active=1, red=0)]
    rep = build_report(loads, _TH, now=1000)
    assert rep.overloaded_count == 1 and rep.warned_count == 1
    d = overload_to_dict(rep)
    assert d["overloaded_count"] == 1 and len(d["assessments"]) == 3


def test_ov08_thresholds_from_config():
    assert overload_thresholds_from_config(None) == OverloadThresholds()

    class _Cfg:
        def get(self, k, default=None):
            if k == "workload":
                return {"overload": {"max_active_cases": 20}}
            return default
    th = overload_thresholds_from_config(_Cfg())
    assert th.max_active_cases == 20 and th.max_red_cases == 3

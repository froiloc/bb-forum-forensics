# =============================================================================
# tests/test_management_escalation.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fallsteuerung (AP-2F)
# =============================================================================
# Testsuite fuer Build 453: Eskalationsregeln (escalation).
#
# ES01 — R1 fall_ueberfaellig: rot + >= red_overdue_days inaktiv -> hoch, Beleg
# ES02 — R1 feuert NICHT unter der Schwelle bzw. bei gruener Ampel
# ES03 — R2 fall_unbearbeitet: open+zugewiesen+>= stale_open_days -> mittel
# ES04 — keine Doppelmeldung: R1-Fall wird nicht zusaetzlich von R2 gemeldet
# ES05 — R3 rueckstau_hoch: unzugewiesen >= backlog_high -> systemisch (subject_id None)
# ES06 — abgeschlossene Faelle (approved/closed) loesen keine Fall-Eskalation aus
# ES07 — Ordnung: hoch vor mittel; Zaehlungen korrekt
# ES08 — thresholds_from_config None-sicher; escalation_to_dict serialisierbar
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.cases.escalation import (           # noqa: E402
    EscalationThresholds, evaluate_escalations,
    escalation_thresholds_from_config, escalation_to_dict,
)

_DAY = 86400
_NOW = 1_700_000_000
_TH = EscalationThresholds(red_overdue_days=30, stale_open_days=14, backlog_high=10)


def _ov(uid, *, status="open", ampel="gruen", assigned_to=1, inactive_days=0):
    return {
        "subject_id": uid, "username": "u%d" % uid, "status": status,
        "ampel": ampel, "assigned_to": assigned_to,
        "last_activity_at": _NOW - inactive_days * _DAY,
    }


def test_es01_overdue():
    rep = evaluate_escalations([_ov(1, ampel="rot", inactive_days=40)], _TH, _NOW)
    assert len(rep.items) == 1
    it = rep.items[0]
    assert it.rule_code == "fall_ueberfaellig" and it.severity == "hoch"
    assert "40 Tage inaktiv" in it.message and it.days_inactive == 40


def test_es02_no_overdue_below_or_green():
    below = evaluate_escalations([_ov(1, ampel="rot", inactive_days=10)], _TH, _NOW)
    assert not any(i.rule_code == "fall_ueberfaellig" for i in below.items)
    # frischer gruener Fall (unter allen Schwellen) -> keine Eskalation
    green = evaluate_escalations([_ov(2, ampel="gruen", inactive_days=5)], _TH, _NOW)
    assert green.items == []


def test_es03_stale_open():
    rep = evaluate_escalations(
        [_ov(1, status="open", ampel="gelb", inactive_days=20)], _TH, _NOW)
    assert any(i.rule_code == "fall_unbearbeitet" and i.severity == "mittel"
               for i in rep.items)


def test_es04_no_double_report():
    # rot + 40 Tage + open: R1 greift -> R2 darf NICHT zusaetzlich melden.
    rep = evaluate_escalations(
        [_ov(1, status="open", ampel="rot", inactive_days=40)], _TH, _NOW)
    codes = [i.rule_code for i in rep.items]
    assert codes == ["fall_ueberfaellig"]


def test_es05_backlog_systemic():
    ovs = [_ov(i, assigned_to=None, ampel="gruen") for i in range(12)]
    rep = evaluate_escalations(ovs, _TH, _NOW)
    sysitems = [i for i in rep.items if i.rule_code == "rueckstau_hoch"]
    assert len(sysitems) == 1 and sysitems[0].subject_id is None
    assert "12 Faelle" in sysitems[0].message


def test_es06_done_no_case_escalation():
    ovs = [_ov(1, status="approved", ampel="rot", inactive_days=99),
           _ov(2, status="closed", ampel="rot", inactive_days=99)]
    rep = evaluate_escalations(ovs, _TH, _NOW)
    assert rep.items == []


def test_es07_order_and_counts():
    ovs = [_ov(1, status="open", ampel="gelb", inactive_days=20),   # mittel
           _ov(2, ampel="rot", inactive_days=40)]                   # hoch
    rep = evaluate_escalations(ovs, _TH, _NOW)
    assert rep.items[0].severity == "hoch"
    assert rep.count_hoch == 1 and rep.count_mittel == 1


def test_es08_config_and_dict():
    assert escalation_thresholds_from_config(None) == EscalationThresholds()

    class _Cfg:
        def get(self, k, default=None):
            return {"red_overdue_days": 7} if k == "escalation" else default
    th = escalation_thresholds_from_config(_Cfg())
    assert th.red_overdue_days == 7 and th.stale_open_days == 14
    rep = evaluate_escalations([_ov(1, ampel="rot", inactive_days=40)], _TH, _NOW)
    d = escalation_to_dict(rep)
    assert json.dumps(d, ensure_ascii=False) and len(d["items"]) == 1

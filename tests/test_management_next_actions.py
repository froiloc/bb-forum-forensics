# =============================================================================
# tests/test_management_next_actions.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fallsteuerung (AP-2F)
# =============================================================================
# Testsuite fuer Build 452: Naechstbeste-Aktion-Warteschlange (next_actions).
#
# NA01 — derive_action: abgeschlossen (approved/closed) -> None
# NA02 — derive_action: unzugewiesen -> 'Fall zuweisen'; Ampel bestimmt Dringlichkeit
# NA03 — derive_action: rot zugewiesen -> 'ueberfaellig', dringend; Begruendung zitiert Signale
# NA04 — derive_action: gelb -> bald; gruen open -> 'Bearbeitung beginnen' routine
# NA05 — build_queue: abgeschlossene NICHT in Schlange, aber gezaehlt (done_excluded)
# NA06 — build_queue: Ordnung dringend>bald>routine, dann Prioritaet, dann Inaktivitaet
# NA07 — build_queue: last_activity None -> als aeltestes behandelt (zuerst in Stufe)
# NA08 — queue_to_dict: stabile Schluessel, json-serialisierbar
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.cases.next_actions import (          # noqa: E402
    derive_action, build_queue, queue_to_dict,
)

_NOW = 1_700_000_000


def _ov(uid, *, status="open", ampel="gruen", assigned_to=1, priority=3,
        ampel_reason="", last_activity_at=_NOW):
    return {
        "subject_id": uid, "username": "u%d" % uid, "status": status,
        "priority": priority, "assigned_to": assigned_to, "ampel": ampel,
        "ampel_reason": ampel_reason, "last_activity_at": last_activity_at,
    }


def test_na01_done_none():
    assert derive_action(_ov(1, status="approved"), "alle") is None
    assert derive_action(_ov(1, status="closed"), "alle") is None


def test_na02_unassigned():
    a = derive_action(_ov(1, assigned_to=None, ampel="rot"), "alle")
    assert a.action == "Fall zuweisen" and a.urgency == "dringend"
    b = derive_action(_ov(2, assigned_to=None, ampel="gruen"), "alle")
    assert b.urgency == "bald" and "unzugewiesen" in b.reason


def test_na03_red_assigned():
    a = derive_action(_ov(1, ampel="rot", status="in_progress",
                          ampel_reason="21 Tage inaktiv"), "alle")
    assert a.urgency == "dringend"
    assert "ueberfaellig" in a.action
    assert "in_progress" in a.reason and "21 Tage inaktiv" in a.reason


def test_na04_yellow_and_green():
    y = derive_action(_ov(1, ampel="gelb"), "alle")
    assert y.urgency == "bald" and y.action == "bald bearbeiten"
    g = derive_action(_ov(2, ampel="gruen", status="open"), "alle")
    assert g.urgency == "routine" and g.action == "Bearbeitung beginnen"


def test_na05_done_excluded_counted():
    ovs = [_ov(1, ampel="rot"), _ov(2, status="approved"),
           _ov(3, status="closed")]
    q = build_queue(ovs, "alle", _NOW)
    assert q.total_cases == 3 and q.actionable == 1 and q.done_excluded == 2


def test_na06_ordering():
    ovs = [
        _ov(1, ampel="gruen", status="open", priority=1),         # routine
        _ov(2, ampel="rot", priority=5),                          # dringend
        _ov(3, ampel="gelb", priority=2),                         # bald
        _ov(4, ampel="rot", priority=1),                          # dringend, hoehere Prio
    ]
    q = build_queue(ovs, "alle", _NOW)
    order = [a.subject_id for a in q.items]
    # dringend zuerst; unter dringend Prioritaet 1 vor 5
    assert order[0] == 4 and order[1] == 2
    assert order[-1] == 1                                          # routine zuletzt


def test_na07_none_activity_first():
    ovs = [
        _ov(1, ampel="rot", priority=3, last_activity_at=_NOW),
        _ov(2, ampel="rot", priority=3, last_activity_at=None),   # aeltestes
    ]
    q = build_queue(ovs, "alle", _NOW)
    assert q.items[0].subject_id == 2


def test_na08_to_dict():
    q = build_queue([_ov(1, ampel="rot")], "eigene", _NOW)
    d = queue_to_dict(q)
    s = json.dumps(d, ensure_ascii=False)
    assert d["scope"] == "eigene" and len(d["items"]) == 1
    assert '"action"' in s and '"reason"' in s

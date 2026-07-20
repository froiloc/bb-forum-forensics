# =============================================================================
# tests/test_management_retention.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Betrieb/Governance (AP-2G)
# =============================================================================
# Testsuite fuer Build 456: Aufbewahrungs-/Loeschfristen-Uebersicht (retention).
#
# RT01 — nur abgeschlossene Faelle (closed/approved) betrachtet; offene ignoriert
# RT02 — approved -> Fristbezug approved_at; ueberschritten -> Kandidat
# RT03 — closed -> Fristbezug updated_at
# RT04 — innerhalb der Frist -> KEIN Kandidat
# RT05 — fehlender Fristbezug -> without_reference (NICHT Kandidat, GR1)
# RT06 — Sortierung: groesste Fristueberschreitung zuerst; over_by_days korrekt
# RT07 — thresholds_from_config None-sicher; Parameter uebersteuert
# RT08 — RetentionRepo liest cases; retention_to_dict serialisierbar
#
# Version: v0.7.456 · Build: 456 · 2026-07-19
# =============================================================================

import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.ops.retention import (              # noqa: E402
    RetentionThresholds, evaluate_retention, retention_thresholds_from_config,
    retention_to_dict, RetentionRepo,
)

_DAY = 86400
_NOW = 1_700_000_000
_TH = RetentionThresholds(retention_days=730)


def _c(uid, status, *, approved_at=None, updated_at=None):
    return {"user_id": uid, "username": "u%d" % uid, "status": status,
            "approved_at": approved_at, "updated_at": updated_at}


def test_rt01_only_closed():
    cases = [_c(1, "open", updated_at=_NOW - 999 * _DAY),
             _c(2, "in_progress", updated_at=_NOW - 999 * _DAY)]
    rep = evaluate_retention(cases, _TH, _NOW)
    assert rep.closed_cases == 0 and rep.candidate_count == 0


def test_rt02_approved_candidate():
    cases = [_c(1, "approved", approved_at=_NOW - 800 * _DAY,
                updated_at=_NOW - 10 * _DAY)]
    rep = evaluate_retention(cases, _TH, _NOW)
    assert rep.candidate_count == 1
    cand = rep.candidates[0]
    assert cand.reference_field == "approved_at" and cand.days_retained == 800


def test_rt03_closed_uses_updated():
    cases = [_c(1, "closed", updated_at=_NOW - 900 * _DAY)]
    rep = evaluate_retention(cases, _TH, _NOW)
    assert rep.candidates[0].reference_field == "updated_at"


def test_rt04_within_retention():
    cases = [_c(1, "approved", approved_at=_NOW - 100 * _DAY)]
    rep = evaluate_retention(cases, _TH, _NOW)
    assert rep.candidate_count == 0 and rep.closed_cases == 1


def test_rt05_without_reference():
    cases = [_c(1, "closed", updated_at=None)]         # kein Bezug
    rep = evaluate_retention(cases, _TH, _NOW)
    assert rep.without_reference == 1 and rep.candidate_count == 0


def test_rt06_sorting_and_over_by():
    cases = [_c(1, "approved", approved_at=_NOW - 800 * _DAY),   # 70 ueber
             _c(2, "approved", approved_at=_NOW - 1100 * _DAY)]  # 370 ueber
    rep = evaluate_retention(cases, _TH, _NOW)
    assert rep.candidates[0].user_id == 2                # groesste Ueberschreitung
    assert rep.candidates[0].over_by_days == 1100 - 730


def test_rt07_config():
    assert retention_thresholds_from_config(None) == RetentionThresholds()

    class _Cfg:
        def get(self, k, default=None):
            return {"retention_days": 365} if k == "retention" else default
    assert retention_thresholds_from_config(_Cfg()).retention_days == 365


def test_rt08_repo_and_dict():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE cases(user_id INTEGER PRIMARY KEY, username TEXT, "
                "status TEXT, approved_at INTEGER, updated_at INTEGER)")
    con.execute("INSERT INTO cases VALUES(1,'a','approved',?,?)",
                (_NOW - 900 * _DAY, _NOW - 10 * _DAY))
    con.execute("INSERT INTO cases VALUES(2,'b','open',NULL,?)", (_NOW,))
    con.commit()
    rep = RetentionRepo(con).compute(thresholds=_TH, now=_NOW)
    assert rep.candidate_count == 1 and rep.candidates[0].user_id == 1
    d = retention_to_dict(rep)
    assert json.dumps(d, ensure_ascii=False) and d["candidate_count"] == 1

# =============================================================================
# tests/test_management_stats_forecast.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-2C)
# =============================================================================
# Testsuite fuer Build 446: Prognose-Modul (Forecaster).
#
# FC01 — Backlog zaehlt nur open/in_progress (nicht approved/closed)
# FC02 — Abschluesse aus case_events(approved) im Fenster -> Rate korrekt
# FC03 — drei Szenarien; optimistisch schneller (weniger Tage) als pessimistisch
# FC04 — keine Abschluesse -> data_sufficient False, Restdauer/Fertig=None, Annahme
# FC05 — Backlog 0 -> days_to_clear 0 in allen Szenarien
# FC06 — finish_day = now_day + days_to_clear (erwartet-Szenario)
# FC07 — lookback_days<=0 -> ValueError
# FC08 — Abschluss ausserhalb des Fensters wird NICHT gezaehlt
# FC09 — Kapazitaets-Kontext: keine Arbeitszeitdaten -> None + Annahme (nie werfen)
# FC10 — forecast_to_dict json-serialisierbar, stabile Schluessel
#
# Version: v0.7.446 · Build: 446 · 2026-07-19
# =============================================================================

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.stats.forecast import (            # noqa: E402
    Forecaster, forecast_to_dict, ForecastResult,
)

_DAY = 86400
_NOW = 1_700_000_000  # fixer Bezugszeitpunkt


def _con(backlog_open=0, backlog_inprog=0, done=0,
         completions_in=0, completions_out=0):
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE cases(user_id INTEGER PRIMARY KEY, status TEXT)")
    con.execute("CREATE TABLE case_events(id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "user_id INTEGER, event_kind TEXT, created_at INTEGER)")
    uid = 1
    for _ in range(backlog_open):
        con.execute("INSERT INTO cases VALUES(?, 'open')", (uid,)); uid += 1
    for _ in range(backlog_inprog):
        con.execute("INSERT INTO cases VALUES(?, 'in_progress')", (uid,)); uid += 1
    for _ in range(done):
        con.execute("INSERT INTO cases VALUES(?, 'approved')", (uid,)); uid += 1
    # Abschluesse innerhalb 30-Tage-Fenster
    for _ in range(completions_in):
        con.execute("INSERT INTO case_events(user_id,event_kind,created_at) "
                    "VALUES(1,'approved',?)", (_NOW - 5 * _DAY,))
    # Abschluesse ausserhalb (vor 40 Tagen)
    for _ in range(completions_out):
        con.execute("INSERT INTO case_events(user_id,event_kind,created_at) "
                    "VALUES(1,'approved',?)", (_NOW - 40 * _DAY,))
    con.commit()
    return con


def test_fc01_backlog_only_open_inprogress():
    con = _con(backlog_open=3, backlog_inprog=2, done=5)
    r = Forecaster(con).compute(now_ts=_NOW, lookback_days=30)
    assert r.backlog == 5


def test_fc02_rate_from_completions():
    con = _con(backlog_open=10, completions_in=15)
    r = Forecaster(con).compute(now_ts=_NOW, lookback_days=30)
    assert r.completions_observed == 15
    assert abs(r.observed_rate_per_day - 15 / 30.0) < 1e-9


def test_fc03_three_scenarios_ordering():
    con = _con(backlog_open=30, completions_in=30)
    r = Forecaster(con).compute(now_ts=_NOW, lookback_days=30)
    names = [s.name for s in r.scenarios]
    assert names == ["optimistisch", "erwartet", "pessimistisch"]
    opt = next(s for s in r.scenarios if s.name == "optimistisch")
    pes = next(s for s in r.scenarios if s.name == "pessimistisch")
    assert opt.days_to_clear < pes.days_to_clear


def test_fc04_no_completions_insufficient():
    con = _con(backlog_open=5, completions_in=0)
    r = Forecaster(con).compute(now_ts=_NOW, lookback_days=30)
    assert r.data_sufficient is False
    for s in r.scenarios:
        assert s.days_to_clear is None and s.finish_day is None
    assert any("keine Prognose" in a.lower() or "keine beobachteten" in a.lower()
               for a in r.assumptions)


def test_fc05_zero_backlog():
    con = _con(backlog_open=0, completions_in=10)
    r = Forecaster(con).compute(now_ts=_NOW, lookback_days=30)
    for s in r.scenarios:
        assert s.days_to_clear == 0


def test_fc06_finish_day_math():
    con = _con(backlog_open=30, completions_in=30)  # rate 1/Tag -> erwartet 30 Tage
    r = Forecaster(con).compute(now_ts=_NOW, lookback_days=30)
    erf = next(s for s in r.scenarios if s.name == "erwartet")
    expect = (datetime.fromtimestamp(_NOW, tz=timezone.utc).date()
              + timedelta(days=erf.days_to_clear)).isoformat()
    assert erf.finish_day == expect


def test_fc07_bad_lookback():
    con = _con(backlog_open=1, completions_in=1)
    with pytest.raises(ValueError):
        Forecaster(con).compute(now_ts=_NOW, lookback_days=0)


def test_fc08_completion_outside_window_ignored():
    con = _con(backlog_open=5, completions_in=3, completions_out=7)
    r = Forecaster(con).compute(now_ts=_NOW, lookback_days=30)
    assert r.completions_observed == 3


def test_fc09_capacity_context_none_without_worktime():
    con = _con(backlog_open=5, completions_in=5)
    # keine person_worktime-Tabelle -> guard greift, wirft nicht
    r = Forecaster(con).compute(now_ts=_NOW, lookback_days=30, include_capacity=True)
    assert r.capacity_context is None
    assert any("Kapazitaets-Kontext" in a for a in r.assumptions)


def test_fc10_to_dict_json_serializable():
    con = _con(backlog_open=5, completions_in=5)
    r = Forecaster(con).compute(now_ts=_NOW, lookback_days=30)
    d = forecast_to_dict(r)
    s = json.dumps(d, ensure_ascii=False)   # darf nicht werfen
    assert '"scenarios"' in s and '"assumptions"' in s
    assert len(d["scenarios"]) == 3

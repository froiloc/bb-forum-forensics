# =============================================================================
# tests/test_management_stats_gantt.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-2C)
# =============================================================================
# Testsuite fuer Build 447: Gantt-Read-Model (GanttModel).
#
# GT01 — Beginn = fruehestes 'assigned'; fehlt es -> cases.created_at
# GT02 — Ende = spaetestes 'approved'; offen -> ongoing=True, end_ts=now
# GT03 — kein Fall verloren: jeder cases-Datensatz ergibt genau einen Balken (GR1)
# GT04 — Lane-Gruppierung je Ermittler; unzugewiesen -> 'Rueckstau' (id None)
# GT05 — Lane-Ordnung: Ermittler alphabetisch, Rueckstau zuletzt
# GT06 — range_start/range_end = min/max ueber alle Balken
# GT07 — Anzeige-Ende nie vor Beginn (Belegtreue)
# GT08 — completed_ts = tatsaechlicher Abschluss (None bei offen)
# GT09 — gantt_to_dict json-serialisierbar, Balkenzahl stimmt
# GT10 — leere Datenlage: keine Lanes, range None (kein Absturz)
#
# Version: v0.7.447 · Build: 447 · 2026-07-19
# =============================================================================

import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.stats.gantt import GanttModel, gantt_to_dict  # noqa: E402

_DAY = 86400
_NOW = 1_700_000_000


def _con():
    con = sqlite3.connect(":memory:")
    con.executescript("""
        CREATE TABLE person(id INTEGER PRIMARY KEY, system_username TEXT, display_name TEXT);
        CREATE TABLE cases(user_id INTEGER PRIMARY KEY, username TEXT, status TEXT,
            assigned_to INTEGER, created_at INTEGER, updated_at INTEGER);
        CREATE TABLE case_events(id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, event_kind TEXT, created_at INTEGER);
        INSERT INTO person VALUES(1,'h001','Zetter, Z'),(2,'h002','Adler, A');
    """)
    return con


def _case(con, uid, status, assigned_to, created_at):
    con.execute("INSERT INTO cases VALUES(?,?,?,?,?,?)",
                (uid, "u%d" % uid, status, assigned_to, created_at, created_at))


def _ev(con, uid, kind, ts):
    con.execute("INSERT INTO case_events(user_id,event_kind,created_at) VALUES(?,?,?)",
                (uid, kind, ts))


def test_gt01_start_anchor():
    con = _con()
    _case(con, 10, "in_progress", 1, _NOW - 20 * _DAY)
    _ev(con, 10, "assigned", _NOW - 15 * _DAY)
    _ev(con, 10, "assigned", _NOW - 10 * _DAY)   # spaeter -> nicht Beginn
    # Fall ohne assign-Event -> created_at
    _case(con, 11, "open", None, _NOW - 8 * _DAY)
    con.commit()
    res = GanttModel(con).build(now_ts=_NOW)
    bars = {b.user_id: b for l in res.lanes for b in l.bars}
    assert bars[10].start_ts == _NOW - 15 * _DAY    # fruehestes assigned
    assert bars[11].start_ts == _NOW - 8 * _DAY     # created_at


def test_gt02_end_and_ongoing():
    con = _con()
    _case(con, 10, "approved", 1, _NOW - 20 * _DAY)
    _ev(con, 10, "assigned", _NOW - 18 * _DAY)
    _ev(con, 10, "approved", _NOW - 5 * _DAY)
    _case(con, 11, "in_progress", 1, _NOW - 10 * _DAY)  # offen
    con.commit()
    res = GanttModel(con).build(now_ts=_NOW)
    bars = {b.user_id: b for l in res.lanes for b in l.bars}
    assert bars[10].ongoing is False and bars[10].end_ts == _NOW - 5 * _DAY
    assert bars[11].ongoing is True and bars[11].end_ts == _NOW


def test_gt03_no_case_lost():
    con = _con()
    for i in range(5):
        _case(con, 20 + i, "open", 1 if i % 2 else None, _NOW - i * _DAY)
    con.commit()
    res = GanttModel(con).build(now_ts=_NOW)
    assert res.total_bars == 5
    assert sum(len(l.bars) for l in res.lanes) == 5


def test_gt04_backlog_lane():
    con = _con()
    _case(con, 30, "open", None, _NOW - _DAY)
    con.commit()
    res = GanttModel(con).build(now_ts=_NOW)
    backlog = [l for l in res.lanes if l.assignee_id is None]
    assert len(backlog) == 1 and backlog[0].assignee_name == "Rueckstau"


def test_gt05_lane_order():
    con = _con()
    _case(con, 40, "open", 1, _NOW - _DAY)   # Zetter
    _case(con, 41, "open", 2, _NOW - _DAY)   # Adler
    _case(con, 42, "open", None, _NOW - _DAY)  # Rueckstau
    con.commit()
    res = GanttModel(con).build(now_ts=_NOW)
    names = [l.assignee_name for l in res.lanes]
    assert names == ["Adler, A", "Zetter, Z", "Rueckstau"]


def test_gt06_range():
    con = _con()
    _case(con, 50, "approved", 1, _NOW - 30 * _DAY)
    _ev(con, 50, "approved", _NOW - 25 * _DAY)
    _case(con, 51, "in_progress", 1, _NOW - 5 * _DAY)  # ongoing -> end now
    con.commit()
    res = GanttModel(con).build(now_ts=_NOW)
    assert res.range_start == _NOW - 30 * _DAY
    assert res.range_end == _NOW


def test_gt07_end_not_before_start():
    con = _con()
    _case(con, 60, "approved", 1, _NOW - 5 * _DAY)
    _ev(con, 60, "assigned", _NOW - 5 * _DAY)
    _ev(con, 60, "approved", _NOW - 10 * _DAY)   # Abschluss VOR Zuweisung (unsauber)
    con.commit()
    res = GanttModel(con).build(now_ts=_NOW)
    b = res.lanes[0].bars[0]
    assert b.end_ts >= b.start_ts


def test_gt08_completed_ts():
    con = _con()
    _case(con, 70, "approved", 1, _NOW - 10 * _DAY)
    _ev(con, 70, "approved", _NOW - 2 * _DAY)
    _case(con, 71, "open", 1, _NOW - 3 * _DAY)
    con.commit()
    res = GanttModel(con).build(now_ts=_NOW)
    bars = {b.user_id: b for l in res.lanes for b in l.bars}
    assert bars[70].completed_ts == _NOW - 2 * _DAY
    assert bars[71].completed_ts is None


def test_gt09_to_dict():
    con = _con()
    _case(con, 80, "open", 1, _NOW - _DAY)
    con.commit()
    d = gantt_to_dict(GanttModel(con).build(now_ts=_NOW))
    s = json.dumps(d, ensure_ascii=False)
    assert '"lanes"' in s and d["total_bars"] == 1


def test_gt10_empty():
    con = _con()
    res = GanttModel(con).build(now_ts=_NOW)
    assert res.lanes == [] and res.range_start is None and res.total_bars == 0

# =============================================================================
# tests/test_management_planung_endpoints.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Prognose & Gantt (Endpunkte)
# =============================================================================
# Testsuite fuer Build 448: /api/forecast + /api/gantt (read-only, CAP_STATS,
# Scope 'alle'). Prueft Rechtegate und JSON-Form; die Rechenkerne selbst sind in
# test_management_stats_forecast.py / test_management_stats_gantt.py abgedeckt.
#
# PE01 — /api/forecast (supervisor, scope alle): 200, 3 Szenarien, backlog, Annahmen
# PE02 — /api/forecast: 403 ohne Rolle UND 403 fuer scope 'eigene' (falluebergreifend)
# PE03 — /api/gantt (supervisor): 200, lanes + total_bars; jeder Fall als Balken
# PE04 — /api/gantt: 403 fuer scope 'eigene'
#
# Version: v0.7.448 · Build: 448 · 2026-07-19
# =============================================================================

import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations
from management.audit.audit_log import AuditLog
from management.migrations.runner import MigrationRunner, discover
from management.gateway.coordinator_writer import CoordinatorWriter
from management.rbac.rbac_repo import RbacRepo
from management.cases.cases_repo import CasesRepo
from management.server.management_app import ManagementApp

_PERSON = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY AUTOINCREMENT, system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL, is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0, is_support INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
)
"""

_OLD_SCRAPE_JOBS = """
CREATE TABLE scrape_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','running','done','failed')),
    manifest_path TEXT, output_path TEXT, worker_id TEXT,
    created_at INTEGER NOT NULL, started_at INTEGER, finished_at INTEGER,
    error_message TEXT, assigned_to INTEGER, note TEXT,
    FOREIGN KEY(assigned_to) REFERENCES person(id)
)
"""


class PlanungEndpointTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        now = int(time.time())
        for pid, un, disp, sup in ((1, "h0a2898", "Chefin", 1),
                                   (2, "h002", "Mueller", 0),
                                   (3, "h003", "Gamma", 0)):
            con.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?, ?, ?, 1, ?, 0, ?)", (pid, un, disp, sup, now))
        con.execute(_OLD_SCRAPE_JOBS)
        for uid in (18, 19, 20):
            con.execute("INSERT INTO scrape_jobs (user_id, username, "
                        "created_at) VALUES (?, ?, ?)", (uid, "b%d" % uid, now))
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.con = con

        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.rbac = RbacRepo(self.con, self.writer)
        self.cases = CasesRepo(self.con, self.writer)
        self.rbac.grant("supervisor", "stats.export_sta", scope="alle", actor_id=1)
        self.rbac.grant("investigator", "stats.export_sta", scope="eigene", actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)

        # 18 in_progress (Backlog), 19 approved (Abschluss -> Rate>0),
        # 20 open, unzugewiesen (Rueckstau-Lane).
        for uid in (18, 19, 20):
            self.cases.create_case(uid, "b%d" % uid, actor_id=1)
        self.cases.assign(18, 2, actor_id=1)
        self.cases.set_status(18, "in_progress", actor_id=2)
        self.cases.assign(19, 2, actor_id=1)
        self.cases.set_status(19, "approved", actor_id=2)   # 'approved'-Ereignis
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def tearDown(self):
        try:
            self.con.close()
        except Exception:
            pass
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    def test_pe01_forecast_ok(self):
        app = ManagementApp(self._db)
        r = app.dispatch(1, "/api/forecast")
        self.assertEqual(r.status, 200)
        self.assertIn("application/json", r.content_type)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(len(d["scenarios"]), 3)
        self.assertEqual(d["backlog"], 2)          # Fall 18 (in_progress) + 20 (open)
        self.assertGreaterEqual(len(d["assumptions"]), 3)

    def test_pe02_forecast_forbidden(self):
        app = ManagementApp(self._db)
        self.assertEqual(app.dispatch(3, "/api/forecast").status, 403)  # keine Rolle
        self.assertEqual(app.dispatch(2, "/api/forecast").status, 403)  # scope eigene

    def test_pe03_gantt_ok(self):
        app = ManagementApp(self._db)
        r = app.dispatch(1, "/api/gantt")
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["total_bars"], 3)       # 18, 19, 20
        bar_uids = {b["user_id"] for lane in d["lanes"] for b in lane["bars"]}
        self.assertEqual(bar_uids, {18, 19, 20})
        # Fall 20 ist unzugewiesen -> Rueckstau-Lane (assignee_id None)
        self.assertTrue(any(lane["assignee_id"] is None for lane in d["lanes"]))

    def test_pe04_gantt_forbidden_scope_eigene(self):
        app = ManagementApp(self._db)
        self.assertEqual(app.dispatch(2, "/api/gantt").status, 403)


if __name__ == "__main__":
    unittest.main()

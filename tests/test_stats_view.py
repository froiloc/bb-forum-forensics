# =============================================================================
# tests/test_stats_view.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistiken (StA/Fuehrung)
# =============================================================================
# Testsuite fuer Build 370: StatsRepo + /api/stats (json/csv).
#
# ST01 — compute(): totals + by_status + by_priority korrekt.
# ST02 — compute(): throughput_by_day aus audit_log (Fall-Ereignisse je Tag).
# ST03 — /api/stats json: 200 mit Matrizen; 403 ohne Cap.
# ST04 — /api/stats?format=csv: text/csv + Langformat-Header.
# ST05 — scope 'eigene': nur eigene zugewiesene Faelle aggregiert.
#
# Version: v0.7.370 · Build: 370 · 2026-07-10
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
from management.stats.stats_repo import StatsRepo
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


class StatsViewTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        for pid, un, disp, sup in ((1, "h0a2898", "Chefin", 1),
                                   (2, "h002", "Mueller", 0),
                                   (3, "h003", "Gamma", 0)):
            con.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?, ?, ?, 1, ?, 0, ?)", (pid, un, disp, sup,
                                                 int(time.time())))
        con.execute(_OLD_SCRAPE_JOBS)
        now = int(time.time())
        for uid in (18, 19, 20, 21):
            con.execute("INSERT INTO scrape_jobs (user_id, username, "
                        "created_at) VALUES (?, ?, ?)", (uid, "b%d" % uid, now))
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.con = con

        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.rbac = RbacRepo(self.con, self.writer)
        self.cases = CasesRepo(self.con, self.writer)

        self.rbac.grant("supervisor", "stats.export_sta", scope="alle",
                        actor_id=1)
        self.rbac.grant("investigator", "stats.export_sta", scope="eigene",
                        actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)

        # Faelle anlegen + Zustaende/Zuweisungen setzen (erzeugt Fall-Ereignisse
        # -> Durchsatz).
        for uid in (18, 19, 20, 21):
            self.cases.create_case(uid, "b%d" % uid, actor_id=1)
        # 18 -> person 2, in_progress ; 19 -> person 2, approved ;
        # 20 -> person 3, open ; 21 unzugewiesen, open
        self.cases.assign(18, 2, actor_id=1)
        self.cases.set_status(18, "in_progress", actor_id=2)
        self.cases.assign(19, 2, actor_id=1)
        self.cases.set_status(19, "approved", actor_id=2)
        self.cases.assign(20, 3, actor_id=1)
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

    # ST01 -------------------------------------------------------------------
    def test_st01_aggregates(self):
        st = StatsRepo(self.con).compute()
        self.assertEqual(st["totals"]["cases"], 4)
        self.assertEqual(st["totals"]["assigned"], 3)
        self.assertEqual(st["totals"]["unassigned"], 1)
        self.assertEqual(st["by_status"]["in_progress"], 1)
        self.assertEqual(st["by_status"]["approved"], 1)
        self.assertEqual(st["by_status"]["open"], 2)   # 20 + 21
        # by_assignee: person 2 hat 2 Faelle, person 3 hat 1.
        by = {a["person_id"]: a["count"] for a in st["by_assignee"]}
        self.assertEqual(by[2], 2)
        self.assertEqual(by[3], 1)

    # ST02 -------------------------------------------------------------------
    def test_st02_throughput(self):
        st = StatsRepo(self.con).compute()
        # Es gab Fall-Ereignisse (create/assign/status) heute -> genau ein
        # Tages-Bucket mit count > 0.
        self.assertTrue(st["throughput_by_day"])
        total = sum(t["count"] for t in st["throughput_by_day"])
        self.assertGreaterEqual(total, 4)  # mind. 4 create-Ereignisse

    # ST03 -------------------------------------------------------------------
    def test_st03_endpoint_json_and_forbidden(self):
        app = ManagementApp(self._db)
        r = app.dispatch(1, "/api/stats")
        self.assertEqual(r.status, 200)
        self.assertIn("application/json", r.content_type)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["scope"], "alle")
        self.assertEqual(d["totals"]["cases"], 4)
        # person 3 hat keine Rolle -> 403
        self.assertEqual(app.dispatch(3, "/api/stats").status, 403)

    # ST04 -------------------------------------------------------------------
    def test_st04_csv_export(self):
        app = ManagementApp(self._db)
        r = app.dispatch(1, "/api/stats", {"format": ["csv"]})
        self.assertEqual(r.status, 200)
        self.assertIn("text/csv", r.content_type)
        text = r.body.decode("utf-8")
        lines = text.strip().splitlines()
        self.assertEqual(lines[0], "abschnitt,schluessel,wert")
        self.assertTrue(any(l.startswith("totals,cases,") for l in lines))
        self.assertTrue(any(l.startswith("by_status,approved,") for l in lines))
        self.assertTrue(any(l.startswith("throughput,") for l in lines))

    # ST05 -------------------------------------------------------------------
    def test_st05_scope_eigene(self):
        app = ManagementApp(self._db)
        d = json.loads(app.dispatch(2, "/api/stats").body.decode("utf-8"))
        self.assertEqual(d["scope"], "eigene")
        # person 2 hat 2 zugewiesene Faelle (18, 19).
        self.assertEqual(d["totals"]["cases"], 2)
        self.assertEqual(d["totals"]["assigned"], 2)
        self.assertEqual(d["by_status"]["in_progress"], 1)
        self.assertEqual(d["by_status"]["approved"], 1)


if __name__ == "__main__":
    unittest.main()

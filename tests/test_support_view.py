# =============================================================================
# tests/test_support_view.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Support-Historie
# =============================================================================
# Testsuite fuer Build 366: /api/support.
#
# SV01 — scope 'alle': alle Sitzungen; Markierungen mine_as_supporter/on_my_case.
# SV02 — scope 'eigene': nur eigene Sitzungen ODER Sitzungen an eigenen Faellen.
# SV03 — ohne support_history.view -> 403.
#
# Version: v0.7.366 · Build: 366 · 2026-07-10
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
from management.support_sessions.support_sessions_repo import SupportSessionsRepo
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


class SupportViewTests(unittest.TestCase):

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
        for uid, uname in ((18, "b18"), (19, "b19"), (20, "b20")):
            con.execute("INSERT INTO scrape_jobs (user_id, username, "
                        "created_at) VALUES (?, ?, ?)", (uid, uname, now))
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.con = con

        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.rbac = RbacRepo(self.con, self.writer)
        self.cases = CasesRepo(self.con, self.writer)
        self.sup = SupportSessionsRepo(self.con, self.writer)

        self.rbac.grant("supervisor", "support_history.view", scope="alle",
                        actor_id=1)
        self.rbac.grant("investigator", "support_history.view", scope="eigene",
                        actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)

        # Faelle: 18 -> person 2, 19 -> person 3, 20 unzugewiesen.
        for uid in (18, 19, 20):
            self.cases.create_case(uid, "b%d" % uid, actor_id=1)
        self.cases.assign(18, 2, actor_id=1)
        self.cases.assign(19, 3, actor_id=1)

        # Support-Sitzungen (start+end erzeugt die Belege):
        #   A: Fall 18, Supporter 2  -> fuer person 2: mine + on_my_case
        #   B: Fall 18, Supporter 3  -> fuer person 2: on_my_case
        #   C: Fall 19, Supporter 2  -> fuer person 2: mine
        #   D: Fall 20, Supporter 3  -> fuer person 2: keins
        for uid, supid in ((18, 2), (18, 3), (19, 2), (20, 3)):
            sid = self.sup.start(uid, supid, actor_id=supid)
            self.sup.end(sid, actor_id=supid)
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

    # SV01 -------------------------------------------------------------------
    def test_sv01_scope_alle(self):
        app = ManagementApp(self._db)
        d = json.loads(app.dispatch(1, "/api/support").body.decode("utf-8"))
        self.assertEqual(d["scope"], "alle")
        self.assertEqual(d["count"], 4)  # alle vier Sitzungen
        # Markierungen aus Sicht der Chefin (person 1): keine eigenen, keine
        # eigenen Faelle -> alle False, aber vorhanden.
        for s in d["sessions"]:
            self.assertIn("mine_as_supporter", s)
            self.assertIn("on_my_case", s)
            self.assertIn("status", s)  # volle Serialisierung

    # SV02 -------------------------------------------------------------------
    def test_sv02_scope_eigene(self):
        app = ManagementApp(self._db)
        d = json.loads(app.dispatch(2, "/api/support").body.decode("utf-8"))
        self.assertEqual(d["scope"], "eigene")
        # A (mine+case), B (case), C (mine) -> 3; D faellt raus.
        self.assertEqual(d["count"], 3)
        users = sorted(s["user_id"] for s in d["sessions"])
        self.assertNotIn(20, users)  # Fall 20 (fremd) nicht enthalten
        # Mindestens eine Sitzung mit mine_as_supporter und eine mit on_my_case.
        self.assertTrue(any(s["mine_as_supporter"] for s in d["sessions"]))
        self.assertTrue(any(s["on_my_case"] for s in d["sessions"]))
        # Fall-18-Sitzung des fremden Supporters 3: on_my_case True, mine False.
        b = [s for s in d["sessions"]
             if s["user_id"] == 18 and s["supporter_id"] == 3]
        self.assertTrue(b and b[0]["on_my_case"] and not b[0]["mine_as_supporter"])

    # SV03 -------------------------------------------------------------------
    def test_sv03_forbidden(self):
        # person 3 hat keine Rolle -> kein support_history.view -> 403.
        app = ManagementApp(self._db)
        self.assertEqual(app.dispatch(3, "/api/support").status, 403)


if __name__ == "__main__":
    unittest.main()

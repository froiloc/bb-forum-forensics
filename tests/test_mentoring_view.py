# =============================================================================
# tests/test_mentoring_view.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Ermittler-Betreuung
# =============================================================================
# Testsuite fuer Build 368: /api/mentoring (Live-Sicht laufender Sitzungen).
#
# MN01 — nur LAUFENDE Sitzungen (beendete erscheinen nicht); Live/Stale-Flag.
# MN02 — scope 'eigene': nur eigene laufende Sitzungen (supporter == ich).
# MN03 — Sortierung: stale (betreuungsbeduerftig) zuerst.
# MN04 — ohne mentoring.view -> 403.
#
# Version: v0.7.368 · Build: 368 · 2026-07-10
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
from db.coordinator_db import DEFAULT_SUPPORT_STALE_SEC

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


class MentoringViewTests(unittest.TestCase):

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

        self.rbac.grant("supervisor", "mentoring.view", scope="alle",
                        actor_id=1)
        self.rbac.grant("support", "mentoring.view", scope="eigene",
                        actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)
        self.rbac.assign_role(2, "support", actor_id=1)

        for uid in (18, 19, 20):
            self.cases.create_case(uid, "b%d" % uid, actor_id=1)

        now = int(time.time())
        # A: Fall 18, Supporter 2, LIVE (frischer Heartbeat).
        self.sid_a = self.sup.start(18, 2, actor_id=2)
        # B: Fall 19, Supporter 3, STALE (alter Heartbeat -> direkt setzen).
        self.sid_b = self.sup.start(19, 3, actor_id=3)
        self.con.execute(
            "UPDATE support_sessions SET last_heartbeat = ?, started_at = ? "
            "WHERE id = ?",
            (now - (DEFAULT_SUPPORT_STALE_SEC + 120), now - 300, self.sid_b))
        # C: Fall 20, Supporter 2, LIVE, aber BEENDET -> darf nicht erscheinen.
        self.sid_c = self.sup.start(20, 2, actor_id=2)
        self.sup.end(self.sid_c, actor_id=2)
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

    # MN01 -------------------------------------------------------------------
    def test_mn01_only_running_with_liveflag(self):
        app = ManagementApp(self._db)
        d = json.loads(app.dispatch(1, "/api/mentoring").body.decode("utf-8"))
        self.assertEqual(d["scope"], "alle")
        self.assertEqual(d["stale_sec"], DEFAULT_SUPPORT_STALE_SEC)
        ids = {s["id"] for s in d["sessions"]}
        self.assertIn(self.sid_a, ids)   # laufend
        self.assertIn(self.sid_b, ids)   # laufend (stale)
        self.assertNotIn(self.sid_c, ids)  # beendet -> nicht dabei
        by_id = {s["id"]: s for s in d["sessions"]}
        self.assertTrue(by_id[self.sid_a]["live"])
        self.assertFalse(by_id[self.sid_b]["live"])
        self.assertIn("heartbeat_age_sec", by_id[self.sid_a])
        self.assertEqual(by_id[self.sid_a]["username"], "b18")

    # MN02 -------------------------------------------------------------------
    def test_mn02_scope_eigene(self):
        app = ManagementApp(self._db)
        # person 2 (support, eigene): nur eigene laufende -> nur A (Supporter 2).
        d = json.loads(app.dispatch(2, "/api/mentoring").body.decode("utf-8"))
        self.assertEqual(d["scope"], "eigene")
        ids = {s["id"] for s in d["sessions"]}
        self.assertEqual(ids, {self.sid_a})

    # MN03 -------------------------------------------------------------------
    def test_mn03_stale_first(self):
        app = ManagementApp(self._db)
        d = json.loads(app.dispatch(1, "/api/mentoring").body.decode("utf-8"))
        # Erste Zeile ist die stale Sitzung (B), Betreuungsbedarf zuerst.
        self.assertEqual(d["sessions"][0]["id"], self.sid_b)
        self.assertFalse(d["sessions"][0]["live"])

    # MN04 -------------------------------------------------------------------
    def test_mn04_forbidden(self):
        app = ManagementApp(self._db)
        # person 3 hat keine Rolle -> kein mentoring.view.
        self.assertEqual(app.dispatch(3, "/api/mentoring").status, 403)


if __name__ == "__main__":
    unittest.main()

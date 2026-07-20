# =============================================================================
# tests/test_personal_views.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Persoenliche Sichten
# =============================================================================
# Testsuite fuer Build 363: /api/mycases + /api/myhistory + MyHistoryRepo.
#
# MC01 — /api/mycases: nur die dem Aufrufer zugewiesenen Faelle.
# MC02 — /api/mycases ohne mycases.view -> 403.
# MH01 — MyHistoryRepo: eigene Aktionen + Fall-Ereignisse der eigenen Faelle;
#        Markierung mine/mycase; fremde Historie bleibt aussen vor.
# MH02 — /api/myhistory: 200; ohne Cap -> 403; limit=... greift.
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
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
from management.personal.myhistory_repo import MyHistoryRepo
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


class PersonalViewsTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        # scrape_jobs muss VOR den Migrationen existieren (m002 precount).
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

        # Rechte: investigator -> mycases.view + myhistory.view (eigene).
        self.rbac.grant("investigator", "mycases.view", scope="eigene",
                        actor_id=1)
        self.rbac.grant("investigator", "myhistory.view", scope="eigene",
                        actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)
        self.rbac.assign_role(3, "investigator", actor_id=1)

        # Faelle anlegen (m002 legt 'cases' nur an; Zeilen kommen ueber
        # CasesRepo.create_case). Danach zuweisen.
        self.cases.create_case(18, "b18", actor_id=1)
        self.cases.create_case(19, "b19", actor_id=1)
        self.cases.create_case(20, "b20", actor_id=1)
        # Fall 18 -> person 2 (h002); Fall 19 -> person 3; 20 unzugewiesen.
        # Actor der Zuweisung ist die Chefin (1); h002 macht eine Notiz an 18.
        self.cases.assign(18, 2, actor_id=1)
        self.cases.assign(19, 3, actor_id=1)
        self.cases.set_note(18, "erste Sichtung", actor_id=2)
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

    # MC01 -------------------------------------------------------------------
    def test_mc01_mycases_only_own(self):
        app = ManagementApp(self._db)
        d = json.loads(app.dispatch(2, "/api/mycases").body.decode("utf-8"))
        uids = {c["subject_id"] for c in d["cases"]}
        self.assertEqual(uids, {18})  # nur h002s Fall

    # MC02 -------------------------------------------------------------------
    def test_mc02_forbidden(self):
        # person 1 (Chefin) hat investigator-Rolle nicht -> kein mycases.view.
        app = ManagementApp(self._db)
        r = app.dispatch(1, "/api/mycases")
        self.assertEqual(r.status, 403)

    # MH01 -------------------------------------------------------------------
    def test_mh01_repo_combines(self):
        hist = MyHistoryRepo(self.con).my_history(2)
        self.assertEqual(hist["my_case_count"], 1)  # Fall 18
        # Meine Notiz an 18: mine=True UND mycase=True.
        note_ev = [e for e in hist["events"]
                   if e["event_type"] == "case_note_set"
                   and e["target_id"] == "18"]
        self.assertTrue(note_ev)
        self.assertTrue(note_ev[0]["mine"])
        self.assertTrue(note_ev[0]["mycase"])
        # Die Zuweisung von Fall 18 (Actor Chefin=1) ist NICHT meine Aktion,
        # aber mein Fall -> erscheint mit mine=False, mycase=True.
        assign_ev = [e for e in hist["events"]
                     if e["event_type"] == "case_assigned"
                     and e["target_id"] == "18"]
        self.assertTrue(assign_ev)
        self.assertFalse(assign_ev[0]["mine"])
        self.assertTrue(assign_ev[0]["mycase"])
        # Fall 19 (person 3) darf NICHT auftauchen.
        self.assertFalse(any(e["target_id"] == "19" for e in hist["events"]))

    # MH02 -------------------------------------------------------------------
    def test_mh02_endpoint(self):
        app = ManagementApp(self._db)
        r = app.dispatch(2, "/api/myhistory")
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["person_id"], 2)
        self.assertGreaterEqual(d["count"], 1)
        # ohne Cap -> 403 (person 1)
        self.assertEqual(app.dispatch(1, "/api/myhistory").status, 403)
        # limit greift
        r2 = app.dispatch(2, "/api/myhistory", {"limit": ["1"]})
        d2 = json.loads(r2.body.decode("utf-8"))
        self.assertEqual(d2["limit"], 1)
        self.assertLessEqual(d2["count"], 1)


if __name__ == "__main__":
    unittest.main()

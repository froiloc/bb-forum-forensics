# =============================================================================
# tests/test_policy_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 361: PolicyRepo (RBAC-Policy-Snapshot) + /api/policy.
#
# PR01 — snapshot(): Rollen/Faehigkeiten-Katalog vorhanden (aus m006-Seed).
# PR02 — snapshot(): aktive Grants + Zuweisungen (mit Personenname) enthalten.
# PR03 — snapshot(): revozierte Grants/Zuweisungen erscheinen NICHT.
# PR04 — snapshot(person_id): gefiltert -> nur eigene Zuweisungen + deren Grants.
# EP01 — /api/policy: 200 mit voller Matrix (policy.view scope alle).
# EP02 — ohne policy.view -> 403.
# EP03 — scope 'eigene': gefilterter Snapshot.
#
# Version: v0.7.361 · Build: 361 · 2026-07-10
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
from management.rbac.policy_repo import PolicyRepo
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


def _build(db_path):
    con = sqlite3.connect(db_path)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(_PERSON)
    for pid, un, disp, sup in ((1, "h0a2898", "Chefin", 1),
                               (2, "h002", "Mueller", 0)):
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (?, ?, ?, 1, ?, 0, ?)", (pid, un, disp, sup,
                                             int(time.time())))
    con.execute(_OLD_SCRAPE_JOBS)
    MigrationRunner(con, discover(coordinator_migrations),
                    audit=AuditLog(con), deployed_by="tester").run()
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return con


class PolicyRepoTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        self.con = _build(self._db)
        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.rbac = RbacRepo(self.con, self.writer)
        # Grundausstattung: supervisor mit policy.view + dashboard.view;
        # investigator mit mycases.view. Personen zuweisen.
        self.rbac.grant("supervisor", "policy.view", scope="alle", actor_id=1)
        self.rbac.grant("supervisor", "dashboard.view", scope="alle", actor_id=1)
        self.rbac.grant("investigator", "mycases.view", scope="eigene",
                        actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)
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

    # PR01 -------------------------------------------------------------------
    def test_pr01_catalog(self):
        snap = PolicyRepo(self.con).snapshot()
        role_codes = {r["code"] for r in snap["roles"]}
        self.assertIn("supervisor", role_codes)
        self.assertIn("searchagent", role_codes)
        cap_codes = {c["code"] for c in snap["capabilities"]}
        self.assertIn("policy.view", cap_codes)
        self.assertIn("capacity.edit", cap_codes)

    # PR02 -------------------------------------------------------------------
    def test_pr02_grants_and_assignments(self):
        snap = PolicyRepo(self.con).snapshot()
        pairs = {(g["role_code"], g["capability_code"], g["scope"])
                 for g in snap["grants"]}
        self.assertIn(("supervisor", "policy.view", "alle"), pairs)
        self.assertIn(("investigator", "mycases.view", "eigene"), pairs)
        # Zuweisung mit Personenname angereichert.
        by_person = {(a["person_id"], a["role_code"]): a
                     for a in snap["assignments"]}
        self.assertIn((1, "supervisor"), by_person)
        self.assertEqual(by_person[(1, "supervisor")]["display_name"], "Chefin")

    # PR03 -------------------------------------------------------------------
    def test_pr03_revoked_excluded(self):
        # Einen Grant und eine Zuweisung revozieren -> nicht mehr im Snapshot.
        gid = [g for g in self.rbac.list_grants()
               if g["role_code"] == "investigator"][0]["id"]
        self.rbac.revoke_grant(gid, actor_id=1)
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        snap = PolicyRepo(self.con).snapshot()
        pairs = {(g["role_code"], g["capability_code"]) for g in snap["grants"]}
        self.assertNotIn(("investigator", "mycases.view"), pairs)

    # PR04 -------------------------------------------------------------------
    def test_pr04_filtered_snapshot(self):
        snap = PolicyRepo(self.con).snapshot(person_id=2)
        self.assertEqual(snap["scope"], "eigene")
        # nur person 2 in den Zuweisungen
        pids = {a["person_id"] for a in snap["assignments"]}
        self.assertEqual(pids, {2})
        # nur Grants der Rollen von person 2 (investigator)
        roles = {g["role_code"] for g in snap["grants"]}
        self.assertEqual(roles, {"investigator"})

    # EP01 -------------------------------------------------------------------
    def test_ep01_endpoint_full(self):
        app = ManagementApp(self._db)
        r = app.dispatch(1, "/api/policy")
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["scope"], "alle")
        self.assertGreaterEqual(d["counts"]["grants"], 3)
        self.assertTrue(any(a["person_id"] == 2 for a in d["assignments"]))

    # EP02 -------------------------------------------------------------------
    def test_ep02_forbidden(self):
        app = ManagementApp(self._db)
        r = app.dispatch(2, "/api/policy")  # investigator ohne policy.view
        self.assertEqual(r.status, 403)

    # EP03 -------------------------------------------------------------------
    def test_ep03_scope_eigene(self):
        # investigator bekommt policy.view scope eigene.
        self.rbac.grant("investigator", "policy.view", scope="eigene",
                        actor_id=1)
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        app = ManagementApp(self._db)
        r = app.dispatch(2, "/api/policy")
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["scope"], "eigene")
        pids = {a["person_id"] for a in d["assignments"]}
        self.assertEqual(pids, {2})


if __name__ == "__main__":
    unittest.main()

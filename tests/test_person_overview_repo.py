# =============================================================================
# tests/test_person_overview_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Personalverwaltung (Build 503)
# =============================================================================
# Testsuite fuer PersonOverviewRepo (management/person/person_overview_repo.py)
# — REIN LESENDES Aggregat der Personal-Sicht (Bauplan Build503 §3).
#
# PO01 — overview(): Personen sortiert, inkl. is_active/Flags; aktive Rollen
#        je Person mit person_role_id/label; widerrufene Rollen NICHT dabei.
# PO02 — Rollenkatalog vollstaendig (alle rbac_role-Codes, sortiert).
# PO03 — REIN LESEND: Zeilenzahlen (person/person_role/audit_log) vor und
#        nach overview() identisch.
#
# Version: v0.8.503 · Build: 503 · 2026-07-24
# =============================================================================

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
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.person.person_overview_repo import PersonOverviewRepo
from management.rbac.rbac_repo import RbacRepo

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


class PersonOverviewRepoTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        now = int(time.time())
        self.con.execute(_PERSON)
        self.con.execute(
            "INSERT INTO person VALUES (1,'h0chef','Chefin',1,1,0,?)", (now,))
        self.con.execute(
            "INSERT INTO person VALUES (2,'h0erm','KHK Muster',1,0,0,?)",
            (now,))
        self.con.execute(_OLD_SCRAPE_JOBS)
        self.audit = AuditLog(self.con)
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester").run()
        writer = CoordinatorWriter(self.con, self.audit)
        self.rbac = RbacRepo(self.con, writer)
        self.rbac.assign_role(1, "supervisor", actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)
        # Eine zugewiesene UND widerrufene Rolle: darf NICHT erscheinen.
        self.rbac.assign_role(2, "searchagent", actor_id=1)
        pr = self.con.execute(
            "SELECT id FROM person_role WHERE person_id=2 "
            "AND role_code='searchagent'").fetchone()
        self.rbac.revoke_role(int(pr["id"]), actor_id=1)

    def tearDown(self):
        try:
            self.con.close()
        finally:
            for fn in os.listdir(self._tmp):
                try:
                    os.remove(os.path.join(self._tmp, fn))
                except OSError:
                    pass
            os.rmdir(self._tmp)

    def _counts(self):
        return tuple(
            self.con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
            for t in ("person", "person_role", "audit_log"))

    # PO01 -------------------------------------------------------------------
    def test_po01_overview(self):
        data = PersonOverviewRepo(self.con).overview()
        persons = data["persons"]
        self.assertEqual([p["system_username"] for p in persons],
                         ["h0chef", "h0erm"])
        p1, p2 = persons
        self.assertTrue(p1["is_active"])
        self.assertTrue(p1["is_supervisor"])
        self.assertEqual([r["role_code"] for r in p1["roles"]],
                         ["supervisor"])
        self.assertEqual(p1["roles"][0]["label"],
                         "Chef-Ermittlerin / Aufsicht")
        self.assertIn("person_role_id", p1["roles"][0])
        # Widerrufene searchagent-Rolle erscheint NICHT.
        self.assertEqual([r["role_code"] for r in p2["roles"]],
                         ["investigator"])

    # PO02 -------------------------------------------------------------------
    def test_po02_roles_catalog(self):
        data = PersonOverviewRepo(self.con).overview()
        codes = [r["code"] for r in data["roles_catalog"]]
        self.assertEqual(codes, sorted(codes))
        for expected in ("investigator", "supervisor", "support", "admin"):
            self.assertIn(expected, codes)

    # PO03 -------------------------------------------------------------------
    def test_po03_read_only(self):
        before = self._counts()
        PersonOverviewRepo(self.con).overview()
        self.assertEqual(self._counts(), before)


if __name__ == "__main__":
    unittest.main()

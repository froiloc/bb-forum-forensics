# =============================================================================
# tests/test_m013_templates_authoring.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — SF-4 (Build 420): RBAC-Seed template_editor/templates.edit
# =============================================================================
# M13-01 — Nach der Migrationskette ist Rolle 'template_editor' und Faehigkeit
#          'templates.edit' in coordinator.db vorhanden (Code+Label+Desc
#          deckungsgleich mit catalog.py).
# M13-02 — up() ist idempotent: erneuter Aufruf ist ein No-op (kein Fehler,
#          keine Dublette).
# M13-03 — verify_catalog_present() ist nach der Kette erfuellt (Code ⊆ DB).
#
# Version: v0.7.420 · Build: 420 · 2026-07-14
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
import management.migrations.coordinator.m013_templates_authoring as m013
from management.audit.audit_log import AuditLog
from management.migrations.runner import MigrationRunner, discover
from management.rbac import catalog
from management.rbac.rbac_resolver import verify_catalog_present

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


class M013Tests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=delete")
        con.execute(_PERSON)
        con.execute("INSERT INTO person (id, system_username, display_name, "
                    "is_investigator, is_supervisor, is_support, created_at) "
                    "VALUES (1,'h001','Chefin',1,1,0,?)", (int(time.time()),))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con

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

    def test_m13_01_role_and_cap_seeded(self):
        role = self.con.execute(
            "SELECT code, label FROM rbac_role WHERE code='template_editor'"
        ).fetchone()
        self.assertIsNotNone(role)
        cat_role = {r.code: r.label for r in catalog.ROLES}["template_editor"]
        self.assertEqual(role["label"], cat_role)

        cap = self.con.execute(
            "SELECT code, label, description FROM rbac_capability "
            "WHERE code='templates.edit'").fetchone()
        self.assertIsNotNone(cap)
        cat_cap = {c.code: (c.label, c.description)
                   for c in catalog.CAPABILITIES}["templates.edit"]
        self.assertEqual((cap["label"], cap["description"]), cat_cap)

    def test_m13_02_idempotent(self):
        # Erneuter up()-Aufruf: No-op, kein Fehler, keine Dublette.
        m013.up(self.con)
        m013.up(self.con)
        n_role = self.con.execute(
            "SELECT COUNT(*) FROM rbac_role WHERE code='template_editor'"
        ).fetchone()[0]
        n_cap = self.con.execute(
            "SELECT COUNT(*) FROM rbac_capability WHERE code='templates.edit'"
        ).fetchone()[0]
        self.assertEqual((n_role, n_cap), (1, 1))

    def test_m13_03_verify_catalog_present(self):
        # Code-Katalog ist nach der Kette vollstaendig in der DB (kein raise).
        verify_catalog_present(self.con)


if __name__ == "__main__":
    unittest.main()

# =============================================================================
# tests/test_migration_m017_onboarding.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Onboarding/Offboarding (AP-2G)
# =============================================================================
# Testsuite fuer Build 464: Migration M017 (onboarding_item + RBAC-Seed).
#
# OM01 — Voller Lauf (M001..M017); Tabelle + Index + Rechte onboarding.view/edit;
#        2. Runner-Lauf No-Op.
# OM02 — CHECK: nur 'erledigt'/'nicht_zutreffend' erlaubt ('offen' NICHT).
# OM03 — UNIQUE(person_id, kind, step_code).
# OM04 — Idempotenz: direkter 2. up() dupliziert die Rechte nicht.
# OM05 — Katalog-Bruecke: beide Rechte in catalog.py UND DB-Seed.
#
# Version: v0.7.464 · Build: 464 · 2026-07-20
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
from management.migrations.coordinator import m017_onboarding
from management.migrations.runner import MigrationRunner, discover
from management.rbac import catalog

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


class MigrationM017Tests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        now = int(time.time())
        self.con.execute(_PERSON)
        self.con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (1, 'chef', 'Chefin', 1, 1, 0, ?)", (now,))
        self.con.execute(_OLD_SCRAPE_JOBS)
        self.audit = AuditLog(self.con)
        self.mods = discover(coordinator_migrations)
        self.runner = MigrationRunner(
            self.con, self.mods, audit=self.audit, deployed_by="tester")
        self.applied = self.runner.run()

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

    def _tbl(self, n):
        return self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (n,)).fetchone()

    def _idx(self, n):
        return self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            (n,)).fetchone()

    def _cap(self, code):
        return self.con.execute(
            "SELECT 1 FROM rbac_capability WHERE code=?", (code,)).fetchone()

    # OM01 -------------------------------------------------------------------
    def test_om01_applied_idempotent(self):
        self.assertIn(17, self.applied)
        self.assertIsNotNone(self._tbl("onboarding_item"))
        self.assertIsNotNone(self._idx("ix_onboarding_person"))
        self.assertIsNotNone(self._cap("onboarding.view"))
        self.assertIsNotNone(self._cap("onboarding.edit"))
        second = MigrationRunner(
            self.con, self.mods, audit=self.audit, deployed_by="tester").run()
        self.assertEqual(second, [])

    # OM02 -------------------------------------------------------------------
    def test_om02_status_check(self):
        seq = self.con.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0]
        now = int(time.time())
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO onboarding_item (person_id, kind, step_code, "
                "status, created_at, audit_seq, created_audit_seq) "
                "VALUES (1,'onboarding','einweisung','offen',?,?,?)",
                (now, seq, seq))
        self.con.execute(
            "INSERT INTO onboarding_item (person_id, kind, step_code, "
            "status, created_at, audit_seq, created_audit_seq) "
            "VALUES (1,'onboarding','einweisung','erledigt',?,?,?)",
            (now, seq, seq))

    # OM03 -------------------------------------------------------------------
    def test_om03_unique(self):
        seq = self.con.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0]
        now = int(time.time())
        self.con.execute(
            "INSERT INTO onboarding_item (person_id, kind, step_code, "
            "status, created_at, audit_seq, created_audit_seq) "
            "VALUES (1,'onboarding','einweisung','erledigt',?,?,?)",
            (now, seq, seq))
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO onboarding_item (person_id, kind, step_code, "
                "status, created_at, audit_seq, created_audit_seq) "
                "VALUES (1,'onboarding','einweisung','nicht_zutreffend',?,?,?)",
                (now, seq, seq))

    # OM04 -------------------------------------------------------------------
    def test_om04_up_idempotent(self):
        before = self.con.execute(
            "SELECT COUNT(*) FROM rbac_capability WHERE code LIKE 'onboarding.%'"
        ).fetchone()[0]
        m017_onboarding.up(self.con)
        after = self.con.execute(
            "SELECT COUNT(*) FROM rbac_capability WHERE code LIKE 'onboarding.%'"
        ).fetchone()[0]
        self.assertEqual(before, 2)
        self.assertEqual(after, 2)

    # OM05 -------------------------------------------------------------------
    def test_om05_catalog_bridge(self):
        self.assertIn("onboarding.view", catalog.CAPABILITY_CODES)
        self.assertIn("onboarding.edit", catalog.CAPABILITY_CODES)
        db_caps = {c["code"] for c in self.con.execute(
            "SELECT code FROM rbac_capability")}
        self.assertTrue(catalog.CAPABILITY_CODES.issubset(db_caps))


if __name__ == "__main__":
    unittest.main()

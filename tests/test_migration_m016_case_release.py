# =============================================================================
# tests/test_migration_m016_case_release.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Externe Fallfreigabe (AP-2G)
# =============================================================================
# Testsuite fuer Build 462: Migration M016 (case_release + RBAC-Seed).
#
# RM01 — Voller Lauf (M001..M016); Tabelle + Indizes + Rechte release.view/
#        release.grant vorhanden; 2. Runner-Lauf No-Op.
# RM02 — CHECK: nur 'freigegeben'/'widerrufen' erlaubt.
# RM03 — FK auf cases: eine Freigabe fuer einen NICHT existierenden Fall wird
#        (bei aktivierten FK) abgewiesen.
# RM04 — Idempotenz: direkter 2. up() dupliziert die Rechte nicht.
# RM05 — Katalog-Bruecke: beide Rechte in catalog.py UND im DB-Seed.
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
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
from management.migrations.coordinator import m016_case_release
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


class MigrationM016Tests(unittest.TestCase):

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

    # RM01 -------------------------------------------------------------------
    def test_rm01_applied_idempotent(self):
        self.assertIn(16, self.applied)
        self.assertIsNotNone(self._tbl("case_release"))
        self.assertIsNotNone(self._idx("ix_release_case"))
        self.assertIsNotNone(self._idx("ix_release_recipient"))
        self.assertIsNotNone(self._cap("release.view"))
        self.assertIsNotNone(self._cap("release.grant"))
        second = MigrationRunner(
            self.con, self.mods, audit=self.audit, deployed_by="tester").run()
        self.assertEqual(second, [])

    # RM02 -------------------------------------------------------------------
    def test_rm02_status_check(self):
        seq = self.con.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0]
        # Fall anlegen (FK), damit nur der status-CHECK greift.
        now = int(time.time())
        self.con.execute(
            "INSERT INTO cases (subject_id, username, priority, status, "
            "created_at, updated_at) VALUES (7,'u7',3,'open',?,?)", (now, now))
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO case_release (subject_id, recipient_kennung, "
                "recipient_display, umfang, status, unbedenklichkeit_grundlage, "
                "created_at, audit_seq, created_audit_seq) "
                "VALUES (7,'h0b','KHK','bericht','offen','ok',?,?,?)",
                (now, seq, seq))
        # gueltig geht durch.
        self.con.execute(
            "INSERT INTO case_release (subject_id, recipient_kennung, "
            "recipient_display, umfang, status, unbedenklichkeit_grundlage, "
            "created_at, audit_seq, created_audit_seq) "
            "VALUES (7,'h0b','KHK','bericht','freigegeben','ok',?,?,?)",
            (now, seq, seq))

    # RM03 -------------------------------------------------------------------
    def test_rm03_fk_cases(self):
        self.con.execute("PRAGMA foreign_keys=ON")
        seq = self.con.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0]
        now = int(time.time())
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO case_release (subject_id, recipient_kennung, "
                "recipient_display, umfang, status, unbedenklichkeit_grundlage, "
                "created_at, audit_seq, created_audit_seq) "
                "VALUES (4242,'h0b','KHK','bericht','freigegeben','ok',?,?,?)",
                (now, seq, seq))

    # RM04 -------------------------------------------------------------------
    def test_rm04_up_idempotent(self):
        before = self.con.execute(
            "SELECT COUNT(*) FROM rbac_capability WHERE code LIKE 'release.%'"
        ).fetchone()[0]
        m016_case_release.up(self.con)
        after = self.con.execute(
            "SELECT COUNT(*) FROM rbac_capability WHERE code LIKE 'release.%'"
        ).fetchone()[0]
        self.assertEqual(before, 2)
        self.assertEqual(after, 2)

    # RM05 -------------------------------------------------------------------
    def test_rm05_catalog_bridge(self):
        self.assertIn("release.view", catalog.CAPABILITY_CODES)
        self.assertIn("release.grant", catalog.CAPABILITY_CODES)
        db_caps = {c["code"] for c in self.con.execute(
            "SELECT code FROM rbac_capability")}
        self.assertTrue(catalog.CAPABILITY_CODES.issubset(db_caps))


if __name__ == "__main__":
    unittest.main()

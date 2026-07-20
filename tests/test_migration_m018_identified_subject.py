# =============================================================================
# tests/test_migration_m018_identified_subject.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Identitaet (AP-2A)
# =============================================================================
# Testsuite fuer Build 468: Migration M018 (identified_subject + RBAC-Seed).
#
# IM01 — Voller Lauf (M001..M018); Tabelle + Index + Rechte crossref.view/edit;
#        2. Runner-Lauf No-Op.
# IM02 — CHECK: nur 'verdacht'/'wahrscheinlich'/'gesichert' erlaubt.
# IM03 — UNIQUE(subject_id).
# IM04 — Idempotenz: direkter 2. up() dupliziert die Rechte nicht.
# IM05 — Katalog-Bruecke: beide Rechte in catalog.py UND DB-Seed.
#
# Version: v0.7.468 · Build: 468 · 2026-07-20
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
from management.migrations.coordinator import m018_identified_subject
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


class MigrationM018Tests(unittest.TestCase):

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

    # IM01 -------------------------------------------------------------------
    def test_im01_applied_idempotent(self):
        self.assertIn(18, self.applied)
        self.assertIsNotNone(self._tbl("identified_subject"))
        self.assertIsNotNone(self._idx("ix_identified_subject_confidence"))
        self.assertIsNotNone(self._cap("crossref.view"))
        self.assertIsNotNone(self._cap("crossref.edit"))
        second = MigrationRunner(
            self.con, self.mods, audit=self.audit, deployed_by="tester").run()
        self.assertEqual(second, [])

    # IM02 -------------------------------------------------------------------
    def test_im02_confidence_check(self):
        seq = self.con.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0]
        now = int(time.time())
        # Ungueltige Stufe -> IntegrityError.
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO identified_subject (subject_id, real_identity, "
                "confidence_code, confidence_ordinal, created_at, updated_at, "
                "audit_seq, created_audit_seq) "
                "VALUES (42, 'Max Mustermann', 'gerichtsfest', 99, ?, ?, ?, ?)",
                (now, now, seq, seq))
        # Alle drei gueltigen Stufen gehen durch.
        for i, code in enumerate(("verdacht", "wahrscheinlich", "gesichert")):
            self.con.execute(
                "INSERT INTO identified_subject (subject_id, real_identity, "
                "confidence_code, confidence_ordinal, created_at, updated_at, "
                "audit_seq, created_audit_seq) "
                "VALUES (?, 'X', ?, ?, ?, ?, ?, ?)",
                (100 + i, code, (i + 1) * 10, now, now, seq, seq))

    # IM03 -------------------------------------------------------------------
    def test_im03_unique_subject(self):
        seq = self.con.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0]
        now = int(time.time())
        self.con.execute(
            "INSERT INTO identified_subject (subject_id, real_identity, "
            "confidence_code, confidence_ordinal, created_at, updated_at, "
            "audit_seq, created_audit_seq) "
            "VALUES (7, 'A', 'verdacht', 10, ?, ?, ?, ?)",
            (now, now, seq, seq))
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO identified_subject (subject_id, real_identity, "
                "confidence_code, confidence_ordinal, created_at, updated_at, "
                "audit_seq, created_audit_seq) "
                "VALUES (7, 'B', 'wahrscheinlich', 20, ?, ?, ?, ?)",
                (now, now, seq, seq))

    # IM04 -------------------------------------------------------------------
    def test_im04_up_idempotent(self):
        before = self.con.execute(
            "SELECT COUNT(*) FROM rbac_capability WHERE code LIKE 'crossref.%'"
        ).fetchone()[0]
        m018_identified_subject.up(self.con)
        after = self.con.execute(
            "SELECT COUNT(*) FROM rbac_capability WHERE code LIKE 'crossref.%'"
        ).fetchone()[0]
        self.assertEqual(before, 2)
        self.assertEqual(after, 2)

    # IM05 -------------------------------------------------------------------
    def test_im05_catalog_bridge(self):
        self.assertIn("crossref.view", catalog.CAPABILITY_CODES)
        self.assertIn("crossref.edit", catalog.CAPABILITY_CODES)
        db_caps = {c["code"] for c in self.con.execute(
            "SELECT code FROM rbac_capability")}
        self.assertTrue(catalog.CAPABILITY_CODES.issubset(db_caps))


if __name__ == "__main__":
    unittest.main()

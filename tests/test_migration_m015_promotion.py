# =============================================================================
# tests/test_migration_m015_promotion.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Betrieb/Governance (AP-2G)
# =============================================================================
# Testsuite fuer Build 460: Migration M015 (forum_promotion + RBAC-Seed).
#
# PM01 — Voller Migrationslauf (M001..M015) via discover+Runner; Tabelle +
#        Index + Faehigkeit 'ops.promote' vorhanden; 2. Runner-Lauf No-Op.
# PM02 — CHECK-Constraint: nur die vier gespeicherten Zustaende sind erlaubt.
# PM03 — UNIQUE(user_id): genau eine Entscheidungszeile je Kandidat.
# PM04 — Idempotenz: direkter 2. up() ist No-op, dupliziert die Faehigkeit nicht.
# PM05 — Katalog-Bruecke: 'ops.promote' ist im Code-Katalog (catalog.py) UND
#        im DB-Seed (rbac_capability) — deckungsgleich (verify_catalog_present).
#
# Version: v0.7.460 · Build: 460 · 2026-07-20
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
from management.migrations.coordinator import m015_promotion
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


class MigrationM015Tests(unittest.TestCase):

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
            "VALUES (1, 'h001', 'Chefin', 1, 1, 0, ?)", (now,))
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

    def _table(self, name):
        return self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,)).fetchone()

    def _index(self, name):
        return self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            (name,)).fetchone()

    def _cap(self, code):
        return self.con.execute(
            "SELECT 1 FROM rbac_capability WHERE code=?", (code,)).fetchone()

    # PM01 -------------------------------------------------------------------
    def test_pm01_applied_and_idempotent(self):
        self.assertIn(15, self.applied)
        self.assertIsNotNone(self._table("forum_promotion"))
        self.assertIsNotNone(self._index("ix_promotion_status"))
        self.assertIsNotNone(self._cap("ops.promote"))
        # Zweiter Runner-Lauf: No-Op (per schema_migrations uebersprungen).
        second = MigrationRunner(
            self.con, self.mods, audit=self.audit, deployed_by="tester").run()
        self.assertEqual(second, [])

    # PM02 -------------------------------------------------------------------
    def test_pm02_status_check_constraint(self):
        # audit_seq/created_audit_seq NOT NULL -> irgendein bestehender seq.
        seq = self.con.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0]
        self.assertIsNotNone(seq)
        now = int(time.time())
        # Ein ungueltiger Zustand muss am CHECK scheitern.
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO forum_promotion "
                "(user_id, status, created_at, audit_seq, created_audit_seq) "
                "VALUES (?, 'offen', ?, ?, ?)", (100, now, seq, seq))
        # Ein gueltiger Zustand geht durch.
        self.con.execute(
            "INSERT INTO forum_promotion "
            "(user_id, status, created_at, audit_seq, created_audit_seq) "
            "VALUES (?, 'gesichtet', ?, ?, ?)", (101, now, seq, seq))

    # PM03 -------------------------------------------------------------------
    def test_pm03_unique_user_id(self):
        seq = self.con.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0]
        now = int(time.time())
        self.con.execute(
            "INSERT INTO forum_promotion "
            "(user_id, status, created_at, audit_seq, created_audit_seq) "
            "VALUES (?, 'gesichtet', ?, ?, ?)", (200, now, seq, seq))
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO forum_promotion "
                "(user_id, status, created_at, audit_seq, created_audit_seq) "
                "VALUES (?, 'zurueckgestellt', ?, ?, ?)", (200, now, seq, seq))

    # PM04 -------------------------------------------------------------------
    def test_pm04_up_idempotent_no_duplicate(self):
        before = self.con.execute(
            "SELECT COUNT(*) FROM rbac_capability WHERE code='ops.promote'"
        ).fetchone()[0]
        m015_promotion.up(self.con)          # direkter 2. up()
        after = self.con.execute(
            "SELECT COUNT(*) FROM rbac_capability WHERE code='ops.promote'"
        ).fetchone()[0]
        self.assertEqual(before, 1)
        self.assertEqual(after, 1)

    # PM05 -------------------------------------------------------------------
    def test_pm05_catalog_bridge(self):
        # Code-Katalog kennt die Faehigkeit ...
        self.assertIn("ops.promote", catalog.CAPABILITY_CODES)
        # ... und der DB-Seed ebenso (deckungsgleich fuer verify_catalog_present).
        db_caps = {
            c["code"] for c in self.con.execute(
                "SELECT code FROM rbac_capability")}
        self.assertIn("ops.promote", db_caps)
        self.assertTrue(catalog.CAPABILITY_CODES.issubset(db_caps),
                        "Code-Katalog ist nicht Teilmenge des DB-Seeds")


if __name__ == "__main__":
    unittest.main()

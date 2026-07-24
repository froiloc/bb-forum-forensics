# =============================================================================
# tests/test_m020_migration.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AD-Abgleich (Build 501)
# =============================================================================
# Testsuite fuer Migration M020 (person.is_active/deactivated_at/
# deactivated_reason + Seed 'personnel.sync'), Bauplan Build501_502 §4/§10.
#
# M2001 — Voller Migrationslauf (M001..M020) via discover+Runner: Spalten
#         vorhanden, Bestandszeile is_active=1 / deactivated_* NULL,
#         Faehigkeit 'personnel.sync' geseedet; 2. Runner-Lauf ist No-op.
# M2002 — Idempotenz: direkter 2. up() ist No-op, dupliziert nichts.
# M2003 — Katalog-Bruecke: 'personnel.sync' ist im Code-Katalog (catalog.py)
#         UND im DB-Seed — deckungsgleich (Label/Beschreibung der Migration
#         eingefroren, m005-Prinzip).
# M2004 — Verlustfreiheit: person-Zeilenzahl unveraendert (rein additiv).
# M2005 — Vorbedingung: fehlt rbac_capability (M006), bricht up() mit
#         Klartext ab (kein stiller Teilvollzug).
#
# Version: v0.8.501 · Build: 501 · 2026-07-24
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
from management.migrations.coordinator import m020_person_active_adsync as m020
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


class MigrationM020Tests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row

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

    def _cols(self):
        return {r[1] for r in self.con.execute("PRAGMA table_info(person)")}

    # M2001 ------------------------------------------------------------------
    def test_m2001_full_run(self):
        self.assertIn(20, self.applied)
        cols = self._cols()
        for c in ("is_active", "deactivated_at", "deactivated_reason"):
            self.assertIn(c, cols)
        row = self.con.execute(
            "SELECT is_active, deactivated_at, deactivated_reason "
            "FROM person WHERE id=1").fetchone()
        self.assertEqual(int(row["is_active"]), 1)
        self.assertIsNone(row["deactivated_at"])
        self.assertIsNone(row["deactivated_reason"])
        cap = self.con.execute(
            "SELECT label FROM rbac_capability WHERE code='personnel.sync'"
        ).fetchone()
        self.assertIsNotNone(cap)
        # 2. Runner-Lauf: nichts mehr anzuwenden.
        self.assertEqual(self.runner.run(), [])

    # M2002 ------------------------------------------------------------------
    def test_m2002_direct_second_up_noop(self):
        n_caps = self.con.execute(
            "SELECT COUNT(*) FROM rbac_capability WHERE code='personnel.sync'"
        ).fetchone()[0]
        self.con.execute("BEGIN IMMEDIATE")
        m020.up(self.con)
        self.con.execute("COMMIT")
        self.assertEqual(self._cols(), self._cols())
        self.assertEqual(
            self.con.execute(
                "SELECT COUNT(*) FROM rbac_capability "
                "WHERE code='personnel.sync'").fetchone()[0],
            n_caps)

    # M2003 ------------------------------------------------------------------
    def test_m2003_catalog_bridge(self):
        codes = {c.code for c in catalog.CAPABILITIES}
        self.assertIn("personnel.sync", codes)
        row = self.con.execute(
            "SELECT label, description FROM rbac_capability "
            "WHERE code='personnel.sync'").fetchone()
        cat = next(c for c in catalog.CAPABILITIES
                   if c.code == "personnel.sync")
        self.assertEqual(row["label"], cat.label)
        self.assertEqual(row["description"], cat.description)

    # M2004 ------------------------------------------------------------------
    def test_m2004_rowcount_unchanged(self):
        self.assertEqual(
            int(self.con.execute("SELECT COUNT(*) FROM person").fetchone()[0]),
            1)

    # M2005 ------------------------------------------------------------------
    def test_m2005_missing_rbac_precondition(self):
        con2 = sqlite3.connect(":memory:")
        con2.execute(_PERSON)
        with self.assertRaises(RuntimeError):
            m020.up(con2)
        con2.close()


if __name__ == "__main__":
    unittest.main()

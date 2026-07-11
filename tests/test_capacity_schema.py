# =============================================================================
# tests/test_capacity_schema.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kapazitaet (Welle 0)
# =============================================================================
# Testsuite fuer Build 355: Migration m008 (Kapazitaets-Schema) + Audit-Vokabular.
#
# CP01 — m008 legt die vier Tabellen + Indizes an; idempotent (zweiter up() ok).
# CP02 — availability_entry: CHECK 'value_pct XOR value_minutes' greift.
# CP03 — availability_entry: CHECK kind IN ('garantie','einschraenkung') greift.
# CP04 — Audit-Vokabular: die sechs Kapazitaets-Aktionen sind gueltig.
# CP05 — Tabellen starten LEER (kein Migrations-Seed).
#
# Version: v0.7.355 · Build: 355 · 2026-07-10
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
from management.audit.event_types import EventType
from management.migrations.runner import MigrationRunner, discover

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


class CapacitySchemaTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (1, 'h0a2898', 'Chefin', 1, 1, 0, ?)", (int(time.time()),))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.con = con

    def tearDown(self):
        self.con.close()
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    # CP01 -------------------------------------------------------------------
    def test_cp01_tables_indices_idempotent(self):
        tables = {r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("person_worktime", "holiday", "availability_reason",
                  "availability_entry"):
            self.assertIn(t, tables)
        idx = {r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        for ix in ("ix_worktime_person", "ix_holiday_day",
                   "ix_availability_person"):
            self.assertIn(ix, idx)
        # Zweiter up() -> No-op.
        from management.migrations.coordinator import m008_capacity
        m008_capacity.up(self.con)

    def _insert_entry(self, kind, value_pct, value_minutes):
        # audit_seq=1 = genesis (existiert). FK-Enforcement ist aus; CHECKs
        # greifen dennoch immer.
        self.con.execute(
            "INSERT INTO availability_entry "
            "(person_id, period_start, period_end, kind, value_pct, "
            " value_minutes, audit_seq, created_at) "
            "VALUES (1, '2026-07-01', '2026-07-31', ?, ?, ?, 1, ?)",
            (kind, value_pct, value_minutes, int(time.time())))

    # CP02 -------------------------------------------------------------------
    def test_cp02_check_value_xor(self):
        # genau eines gesetzt -> ok
        self._insert_entry("garantie", 80, None)
        self._insert_entry("einschraenkung", None, 120)
        # beide NULL -> Verstoss
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert_entry("garantie", None, None)
        # beide gesetzt -> Verstoss
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert_entry("garantie", 50, 60)

    # CP03 -------------------------------------------------------------------
    def test_cp03_check_kind(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert_entry("quatsch", 50, None)

    # CP04 -------------------------------------------------------------------
    def test_cp04_audit_vocab(self):
        for a in (EventType.WORKTIME_SET, EventType.HOLIDAY_ADDED,
                  EventType.HOLIDAY_REMOVED, EventType.AVAILABILITY_REASON_ADDED,
                  EventType.AVAILABILITY_SET, EventType.AVAILABILITY_REMOVED):
            self.assertTrue(EventType.is_valid(a), a)

    # CP05 -------------------------------------------------------------------
    def test_cp05_starts_empty(self):
        for t in ("person_worktime", "holiday", "availability_reason",
                  "availability_entry"):
            n = self.con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
            self.assertEqual(n, 0, t)


if __name__ == "__main__":
    unittest.main()

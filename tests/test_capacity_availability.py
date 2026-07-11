# =============================================================================
# tests/test_capacity_availability.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kapazitaet (Welle 0)
# =============================================================================
# Testsuite fuer Build 357: ReasonRepo + AvailabilityRepo + capacity_admin.
#
# RS01 — add_reason: Zeile + AVAILABILITY_REASON_ADDED-Beleg; list_reasons.
# RS02 — Duplikat-Grund -> CapacityError; is_active().
# AV01 — set_availability: Zeile + AVAILABILITY_SET-Beleg; audit_seq-Kopplung.
# AV02 — Validierung: beide/keine Werte, pct-Range, period-Reihenfolge, kind.
# AV03 — reason_code muss aktiv sein (unbekannt -> Fehler; gesetzt -> ok).
# AV04 — remove_availability: Soft-Delete + AVAILABILITY_REMOVED; kein DELETE.
# AV05 — kein Overlap-Guard: zwei Eintraege gleicher Zeitraum -> beide.
# CL01 — CLI: add-reason + set-availability + list + remove End-to-End.
#
# Version: v0.7.357 · Build: 357 · 2026-07-10
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
from management.migrations.runner import MigrationRunner, discover
from management.gateway.coordinator_writer import CoordinatorWriter
from management.capacity.reason_repo import ReasonRepo
from management.capacity.availability_repo import AvailabilityRepo
from management.capacity.capacity_errors import CapacityError
from management.capacity import capacity_admin

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


def _build_coordinator(db_path):
    con = sqlite3.connect(db_path)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(_PERSON)
    con.execute(
        "INSERT INTO person (id, system_username, display_name, "
        "is_investigator, is_supervisor, is_support, created_at) "
        "VALUES (1, 'h0a2898', 'Chefin', 1, 1, 0, ?)", (int(time.time()),))
    con.execute(
        "INSERT INTO person (id, system_username, display_name, "
        "is_investigator, is_supervisor, is_support, created_at) "
        "VALUES (2, 'h002', 'Mueller', 1, 0, 0, ?)", (int(time.time()),))
    con.execute(_OLD_SCRAPE_JOBS)
    MigrationRunner(con, discover(coordinator_migrations),
                    audit=AuditLog(con), deployed_by="tester").run()
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return con


class CapacityAvailabilityTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        self.con = _build_coordinator(self._db)
        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))

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

    # RS01 -------------------------------------------------------------------
    def test_rs01_add_reason(self):
        repo = ReasonRepo(self.con, self.writer)
        seq = repo.add_reason("urlaub", "Urlaub", sort=10, actor_id=1)
        ev = self.con.execute(
            "SELECT event_type FROM audit_log WHERE seq=?", (seq,)).fetchone()
        self.assertEqual(ev[0], "availability_reason_added")
        rows = repo.list_reasons()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["code"], "urlaub")
        self.assertEqual(rows[0]["audit_seq"], seq)

    # RS02 -------------------------------------------------------------------
    def test_rs02_duplicate_and_active(self):
        repo = ReasonRepo(self.con, self.writer)
        repo.add_reason("urlaub", "Urlaub", actor_id=1)
        with self.assertRaises(CapacityError):
            repo.add_reason("urlaub", "Urlaub 2", actor_id=1)
        self.assertTrue(repo.is_active("urlaub"))
        self.assertFalse(repo.is_active("gibtsnicht"))

    # AV01 -------------------------------------------------------------------
    def test_av01_set_availability(self):
        repo = AvailabilityRepo(self.con, self.writer)
        seq = repo.set_availability(
            2, period_start="2026-07-01", period_end="2026-07-31",
            kind="garantie", value_pct=80, actor_id=1)
        ev = self.con.execute(
            "SELECT event_type FROM audit_log WHERE seq=?", (seq,)).fetchone()
        self.assertEqual(ev[0], "availability_set")
        rows = repo.list_availability(2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["value_pct"], 80)
        self.assertEqual(rows[0]["audit_seq"], seq)

    # AV02 -------------------------------------------------------------------
    def test_av02_validation(self):
        repo = AvailabilityRepo(self.con, self.writer)
        base = dict(period_start="2026-07-01", period_end="2026-07-31",
                    kind="garantie", actor_id=1)
        # keiner gesetzt
        with self.assertRaises(CapacityError):
            repo.set_availability(2, **base)
        # beide gesetzt
        with self.assertRaises(CapacityError):
            repo.set_availability(2, value_pct=50, value_minutes=60, **base)
        # pct out of range
        with self.assertRaises(CapacityError):
            repo.set_availability(2, value_pct=150, **base)
        # period verdreht
        with self.assertRaises(CapacityError):
            repo.set_availability(2, value_pct=50, period_start="2026-08-01",
                                  period_end="2026-07-01", kind="garantie",
                                  actor_id=1)
        # ungueltiges kind
        with self.assertRaises(CapacityError):
            repo.set_availability(2, value_pct=50,
                                  period_start="2026-07-01",
                                  period_end="2026-07-31", kind="quatsch",
                                  actor_id=1)

    # AV03 -------------------------------------------------------------------
    def test_av03_reason_must_be_active(self):
        repo = AvailabilityRepo(self.con, self.writer)
        with self.assertRaises(CapacityError):
            repo.set_availability(2, period_start="2026-07-01",
                                  period_end="2026-07-31", kind="einschraenkung",
                                  value_minutes=120, reason_code="unbekannt",
                                  actor_id=1)
        ReasonRepo(self.con, self.writer).add_reason("krank", "Krank", actor_id=1)
        seq = repo.set_availability(
            2, period_start="2026-07-01", period_end="2026-07-31",
            kind="einschraenkung", value_minutes=120, reason_code="krank",
            actor_id=1)
        self.assertGreater(seq, 0)

    # AV04 -------------------------------------------------------------------
    def test_av04_remove_soft_delete(self):
        repo = AvailabilityRepo(self.con, self.writer)
        repo.set_availability(2, period_start="2026-07-01",
                              period_end="2026-07-31", kind="garantie",
                              value_pct=80, actor_id=1)
        eid = repo.list_availability(2)[0]["id"]
        seq = repo.remove_availability(eid, actor_id=1)
        ev = self.con.execute(
            "SELECT event_type FROM audit_log WHERE seq=?", (seq,)).fetchone()
        self.assertEqual(ev[0], "availability_removed")
        self.assertEqual(repo.list_availability(2), [])
        total = self.con.execute(
            "SELECT COUNT(*) FROM availability_entry").fetchone()[0]
        self.assertEqual(total, 1)  # kein hartes DELETE
        with self.assertRaises(CapacityError):
            repo.remove_availability(eid, actor_id=1)  # zweites Mal -> Fehler

    # AV05 -------------------------------------------------------------------
    def test_av05_no_overlap_guard(self):
        repo = AvailabilityRepo(self.con, self.writer)
        repo.set_availability(2, period_start="2026-07-01",
                              period_end="2026-07-31", kind="garantie",
                              value_pct=80, actor_id=1)
        repo.set_availability(2, period_start="2026-07-10",
                              period_end="2026-07-20", kind="einschraenkung",
                              value_minutes=240, actor_id=1)
        self.assertEqual(len(repo.list_availability(2)), 2)

    # CL01 -------------------------------------------------------------------
    def test_cl01_cli_end_to_end(self):
        self.con.close()
        self.assertEqual(0, capacity_admin.main([
            "add-reason", "--coordinator-db", self._db, "--actor", "h0a2898",
            "--code", "fortbildung", "--label", "Fortbildung"]))
        self.assertEqual(0, capacity_admin.main([
            "set-availability", "--coordinator-db", self._db, "--actor",
            "h0a2898", "--person-id", "2", "--start", "2026-09-01",
            "--end", "2026-09-05", "--kind", "einschraenkung",
            "--minutes", "480", "--reason", "fortbildung"]))
        self.assertEqual(0, capacity_admin.main([
            "list-availability", "--coordinator-db", self._db]))
        con = sqlite3.connect(self._db)
        eid = con.execute("SELECT id FROM availability_entry").fetchone()[0]
        con.close()
        self.assertEqual(0, capacity_admin.main([
            "remove-availability", "--coordinator-db", self._db, "--actor",
            "h0a2898", "--id", str(eid)]))
        con = sqlite3.connect(self._db)
        try:
            deleted = con.execute(
                "SELECT deleted_at FROM availability_entry WHERE id=?",
                (eid,)).fetchone()[0]
            reasons = con.execute(
                "SELECT COUNT(*) FROM availability_reason").fetchone()[0]
        finally:
            con.close()
        self.assertIsNotNone(deleted)
        self.assertEqual(reasons, 1)
        self.con = sqlite3.connect(self._db)


if __name__ == "__main__":
    unittest.main()

# =============================================================================
# tests/test_capacity_worktime_holiday.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kapazitaet (Welle 0)
# =============================================================================
# Testsuite fuer Build 356: WorktimeRepo + HolidayRepo + capacity_admin.
#
# WT01 — set_worktime: Zeile + audit_seq == WORKTIME_SET-Beleg; list_worktime.
# WT02 — append-only: zwei Regeln (versch. effective_from) -> zwei Zeilen.
# WT03 — Validierung: negative Minuten -> CapacityError.
# HL01 — add_holiday: Zeile + HOLIDAY_ADDED-Beleg; list_holidays.
# HL02 — remove_holiday: Soft-Delete (deleted_at gesetzt, kein hartes DELETE);
#        HOLIDAY_REMOVED-Beleg; nicht in aktiver Liste.
# HL03 — remove_holiday auf nicht vorhandener id -> CapacityError.
# HL04 — Duplikat-Guard: aktiver Feiertag (day, region) doppelt -> CapacityError.
# CL01 — CLI: set-worktime + add-holiday + remove-holiday End-to-End.
#
# Version: v0.7.356 · Build: 356 · 2026-07-10
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
from management.capacity.worktime_repo import WorktimeRepo
from management.capacity.holiday_repo import HolidayRepo
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


class CapacityWriteTests(unittest.TestCase):

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

    # WT01 -------------------------------------------------------------------
    def test_wt01_set_worktime_couples_audit(self):
        repo = WorktimeRepo(self.con, self.writer)
        seq = repo.set_worktime(2, effective_from="2026-07-01",
                                mon_min=480, tue_min=480, wed_min=480,
                                thu_min=480, fri_min=300, actor_id=1)
        ev = self.con.execute(
            "SELECT event_type FROM audit_log WHERE seq=?", (seq,)).fetchone()
        self.assertEqual(ev[0], "worktime_set")
        rows = repo.list_worktime(2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["audit_seq"], seq)
        self.assertEqual(rows[0]["mon_min"], 480)
        self.assertEqual(rows[0]["fri_min"], 300)
        self.assertEqual(rows[0]["created_by"], 1)

    # WT02 -------------------------------------------------------------------
    def test_wt02_append_only(self):
        repo = WorktimeRepo(self.con, self.writer)
        repo.set_worktime(2, effective_from="2026-07-01", mon_min=480, actor_id=1)
        repo.set_worktime(2, effective_from="2026-09-01", mon_min=300, actor_id=1)
        rows = repo.list_worktime(2)
        self.assertEqual(len(rows), 2)  # keine Vorgaengerzeile geschlossen
        # sortiert nach effective_from
        self.assertEqual(rows[0]["effective_from"], "2026-07-01")
        self.assertEqual(rows[1]["effective_from"], "2026-09-01")

    # WT03 -------------------------------------------------------------------
    def test_wt03_negative_minutes(self):
        repo = WorktimeRepo(self.con, self.writer)
        with self.assertRaises(CapacityError):
            repo.set_worktime(2, effective_from="2026-07-01", mon_min=-1,
                              actor_id=1)

    # HL01 -------------------------------------------------------------------
    def test_hl01_add_holiday(self):
        repo = HolidayRepo(self.con, self.writer)
        seq = repo.add_holiday("2026-12-25", "1. Weihnachtstag",
                               region="NRW", actor_id=1)
        ev = self.con.execute(
            "SELECT event_type FROM audit_log WHERE seq=?", (seq,)).fetchone()
        self.assertEqual(ev[0], "holiday_added")
        rows = repo.list_holidays()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["day"], "2026-12-25")
        self.assertEqual(rows[0]["audit_seq"], seq)

    # HL02 -------------------------------------------------------------------
    def test_hl02_remove_soft_delete(self):
        repo = HolidayRepo(self.con, self.writer)
        repo.add_holiday("2026-12-25", "Weihnachten", actor_id=1)
        hid = repo.list_holidays()[0]["id"]
        seq = repo.remove_holiday(hid, actor_id=1)
        ev = self.con.execute(
            "SELECT event_type FROM audit_log WHERE seq=?", (seq,)).fetchone()
        self.assertEqual(ev[0], "holiday_removed")
        # Nicht in aktiver Liste, aber Zeile existiert noch (kein hartes DELETE).
        self.assertEqual(repo.list_holidays(), [])
        total = self.con.execute("SELECT COUNT(*) FROM holiday").fetchone()[0]
        self.assertEqual(total, 1)
        deleted = self.con.execute(
            "SELECT deleted_at FROM holiday WHERE id=?", (hid,)).fetchone()[0]
        self.assertIsNotNone(deleted)

    # HL03 -------------------------------------------------------------------
    def test_hl03_remove_missing(self):
        repo = HolidayRepo(self.con, self.writer)
        with self.assertRaises(CapacityError):
            repo.remove_holiday(9999, actor_id=1)

    # HL04 -------------------------------------------------------------------
    def test_hl04_duplicate_guard(self):
        repo = HolidayRepo(self.con, self.writer)
        repo.add_holiday("2026-12-25", "Weihnachten", region="NRW", actor_id=1)
        with self.assertRaises(CapacityError):
            repo.add_holiday("2026-12-25", "Weihnachten", region="NRW",
                             actor_id=1)
        # anderer Region -> erlaubt
        repo.add_holiday("2026-12-25", "Weihnachten", region="BY", actor_id=1)
        self.assertEqual(len(repo.list_holidays()), 2)

    # CL01 -------------------------------------------------------------------
    def test_cl01_cli_end_to_end(self):
        self.con.close()
        rc = capacity_admin.main([
            "set-worktime", "--coordinator-db", self._db, "--actor", "h0a2898",
            "--person-id", "2", "--from", "2026-07-01",
            "--mon", "480", "--tue", "480"])
        self.assertEqual(rc, 0)
        rc = capacity_admin.main([
            "add-holiday", "--coordinator-db", self._db, "--actor", "h0a2898",
            "--day", "2026-10-03", "--label", "Tag der Deutschen Einheit"])
        self.assertEqual(rc, 0)
        rc = capacity_admin.main([
            "list-holidays", "--coordinator-db", self._db])
        self.assertEqual(rc, 0)
        # Feiertag wieder entfernen.
        con = sqlite3.connect(self._db)
        hid = con.execute("SELECT id FROM holiday").fetchone()[0]
        con.close()
        rc = capacity_admin.main([
            "remove-holiday", "--coordinator-db", self._db, "--actor",
            "h0a2898", "--id", str(hid)])
        self.assertEqual(rc, 0)
        # Kontrolle: Arbeitszeit-Zeile + Feiertag soft-deleted.
        con = sqlite3.connect(self._db)
        try:
            wt = con.execute("SELECT COUNT(*) FROM person_worktime").fetchone()[0]
            deleted = con.execute(
                "SELECT deleted_at FROM holiday WHERE id=?", (hid,)).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(wt, 1)
        self.assertIsNotNone(deleted)
        self.con = sqlite3.connect(self._db)  # fuer tearDown


if __name__ == "__main__":
    unittest.main()

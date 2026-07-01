# =============================================================================
# tests/test_management_cases.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite für Tag 2: M002 (scrape_jobs-Rebuild + cases), CasesRepo, Gateway.
#
# B01 — M002 Rebuild: scrape_jobs ohne assigned_to/note, übrige Spalten+Indizes da
# B02 — M002: Zeilenzahl scrape_jobs vorher == nachher (Invariante, Registry)
# B03 — M002: foreign_key_check sauber; cases angelegt
# B04 — create_case → cases-Zeile + CASE_CREATED atomar
# B05 — assign → assigned_to gesetzt + CASE_ASSIGNED
# B06 — set_status('approved') → approved_at gesetzt + CASE_APPROVED
# B07 — ungültiger Status → CHECK-Verletzung (Rollback, kein Audit)
# B08 — Gateway-Rollback: fehlgeschlagener Write ohne cases-Änderung/Audit
# B09 — Repoint-Read: get_case gleiche Schlüssel; None bei fehlendem Fall
# B10 — Audit-Kette verifiziert nach cases-Writes (inkl. M001/M002)
#
# Version: v0.7.307 · Build: 307 · 2026-07-01
# =============================================================================

import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.audit.audit_log import AuditLog
from management.audit.event_types import EventType
from management.cases.cases_repo import CasesError, CasesRepo
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.coordinator import m001_audit_log, m002_cases
from management.migrations.runner import MigrationRunner

_OLD_SCRAPE_JOBS = """
CREATE TABLE scrape_jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    username      TEXT    NOT NULL,
    priority      INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status        TEXT    NOT NULL DEFAULT 'pending'
                  CHECK(status IN ('pending','running','done','failed')),
    manifest_path TEXT,
    output_path   TEXT,
    worker_id     TEXT,
    created_at    INTEGER NOT NULL,
    started_at    INTEGER,
    finished_at   INTEGER,
    error_message TEXT,
    assigned_to   INTEGER,
    note          TEXT,
    FOREIGN KEY(assigned_to) REFERENCES investigators(id)
)
"""

_INVESTIGATORS = """
CREATE TABLE investigators (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    system_username TEXT    NOT NULL UNIQUE,
    display_name    TEXT    NOT NULL,
    is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor   INTEGER NOT NULL DEFAULT 0,
    is_support      INTEGER NOT NULL DEFAULT 0,
    created_at      INTEGER NOT NULL
)
"""


class ManagementCasesTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")

        now = int(time.time())
        # Ausgangszustand: investigators + ALTE scrape_jobs (mit assigned_to/note).
        self.con.execute(_INVESTIGATORS)
        self.con.executemany(
            "INSERT INTO investigators "
            "(id, system_username, display_name, is_investigator, is_supervisor, "
            " is_support, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(1, "h001", "Alpha", 1, 1, 0, now),
             (2, "h002", "Beta", 1, 0, 0, now)],
        )
        self.con.execute(_OLD_SCRAPE_JOBS)
        self.con.execute("CREATE INDEX scrape_jobs_status_idx ON scrape_jobs(status)")
        self.con.execute("CREATE INDEX scrape_jobs_user_idx   ON scrape_jobs(user_id)")
        self.con.executemany(
            "INSERT INTO scrape_jobs "
            "(user_id, username, priority, status, created_at, assigned_to, note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(18, "KEKa", 3, "pending", now, None, None),
             (19, "LMN",  2, "pending", now, 2, "Notiz")],
        )

        # Migrationen M001 + M002 anwenden.
        self.audit = AuditLog(self.con)
        self.runner = MigrationRunner(
            self.con, [m001_audit_log, m002_cases],
            audit=self.audit, deployed_by="tester",
        )
        self.applied = self.runner.run()

        self.writer = CoordinatorWriter(self.con, self.audit)
        self.repo = CasesRepo(self.con, self.writer)

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

    # Helfer -----------------------------------------------------------------
    def _cols(self, table):
        return {r[1] for r in self.con.execute("PRAGMA table_info(%s)" % table)}

    def _last_audit(self):
        return self.con.execute(
            "SELECT event_type, target_id FROM audit_log ORDER BY seq DESC LIMIT 1"
        ).fetchone()

    def _audit_count(self):
        return self.con.execute(
            "SELECT COUNT(*) AS c FROM audit_log"
        ).fetchone()["c"]

    # ------------------------------------------------------------------- B01
    def test_b01_rebuild_columns_and_indexes(self):
        self.assertEqual(self.applied, [1, 2])
        cols = self._cols("scrape_jobs")
        self.assertNotIn("assigned_to", cols)
        self.assertNotIn("note", cols)
        self.assertTrue(
            {"id", "user_id", "username", "priority", "status", "manifest_path",
             "output_path", "worker_id", "created_at", "started_at",
             "finished_at", "error_message"} <= cols
        )
        idx = {r[1] for r in self.con.execute("PRAGMA index_list(scrape_jobs)")}
        self.assertIn("scrape_jobs_status_idx", idx)
        self.assertIn("scrape_jobs_user_idx", idx)

    # ------------------------------------------------------------------- B02
    def test_b02_rowcount_invariant(self):
        n = self.con.execute("SELECT COUNT(*) AS c FROM scrape_jobs").fetchone()["c"]
        self.assertEqual(n, 2)
        mig = self.con.execute(
            "SELECT kind, row_count_before, row_count_after "
            "FROM schema_migrations WHERE version = 2"
        ).fetchone()
        self.assertEqual(mig["kind"], "destructive")
        self.assertEqual(mig["row_count_before"], 2)
        self.assertEqual(mig["row_count_after"], 2)

    # ------------------------------------------------------------------- B03
    def test_b03_fk_check_and_cases_created(self):
        self.assertEqual(
            self.con.execute("PRAGMA foreign_key_check(cases)").fetchall(), []
        )
        self.assertEqual(
            self.con.execute("PRAGMA foreign_key_check(scrape_jobs)").fetchall(), []
        )
        tables = {r["name"] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        self.assertIn("cases", tables)

    # ------------------------------------------------------------------- B04
    def test_b04_create_case_atomic(self):
        seq = self.repo.create_case(100, "TestUser", actor_id=None)
        row = self.con.execute(
            "SELECT status, priority FROM cases WHERE user_id = 100"
        ).fetchone()
        self.assertEqual(row["status"], "open")
        self.assertEqual(row["priority"], 3)
        last = self._last_audit()
        self.assertEqual(last["event_type"], EventType.CASE_CREATED)
        self.assertEqual(last["target_id"], "100")
        self.assertEqual(seq, self.con.execute(
            "SELECT MAX(seq) AS s FROM audit_log").fetchone()["s"])

    # ------------------------------------------------------------------- B05
    def test_b05_assign(self):
        self.repo.create_case(100, "TestUser")
        self.repo.assign(100, 2)
        row = self.con.execute(
            "SELECT assigned_to FROM cases WHERE user_id = 100"
        ).fetchone()
        self.assertEqual(row["assigned_to"], 2)
        self.assertEqual(self._last_audit()["event_type"], EventType.CASE_ASSIGNED)

    # ------------------------------------------------------------------- B06
    def test_b06_approve_sets_timestamp(self):
        self.repo.create_case(100, "TestUser")
        self.repo.set_status(100, "approved")
        row = self.con.execute(
            "SELECT status, approved_at FROM cases WHERE user_id = 100"
        ).fetchone()
        self.assertEqual(row["status"], "approved")
        self.assertIsNotNone(row["approved_at"])
        self.assertEqual(self._last_audit()["event_type"], EventType.CASE_APPROVED)

    # ------------------------------------------------------------------- B07
    def test_b07_invalid_status_rejected(self):
        self.repo.create_case(100, "TestUser")
        before = self._audit_count()
        with self.assertRaises(sqlite3.Error):
            self.repo.set_status(100, "bogus")
        # Status unverändert, kein zusätzlicher Audit-Eintrag.
        row = self.con.execute(
            "SELECT status FROM cases WHERE user_id = 100"
        ).fetchone()
        self.assertEqual(row["status"], "open")
        self.assertEqual(self._audit_count(), before)

    # ------------------------------------------------------------------- B08
    def test_b08_gateway_rollback_on_failed_write(self):
        before = self._audit_count()
        # assign auf nicht existierenden Fall -> CasesError -> Rollback, kein Audit.
        with self.assertRaises(CasesError):
            self.repo.assign(999, 2)
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) AS c FROM cases").fetchone()["c"], 0
        )
        self.assertEqual(self._audit_count(), before)

    # ------------------------------------------------------------------- B09
    def test_b09_get_case_shape(self):
        self.assertIsNone(self.repo.get_case(100))
        self.repo.create_case(100, "TestUser")
        self.repo.assign(100, 2)
        case = self.repo.get_case(100)
        self.assertEqual(
            set(case.keys()),
            {"user_id", "username", "status", "priority", "assigned_to", "note",
             "approved_at", "total_pages_scraped", "created_at", "updated_at"},
        )
        self.assertEqual(case["assigned_to"], "h002")  # als system_username aufgelöst

    # ------------------------------------------------------------------- B10
    def test_b10_chain_verifies_after_writes(self):
        self.repo.create_case(100, "TestUser")
        self.repo.assign(100, 1)
        self.repo.set_status(100, "in_progress")
        res = self.audit.verify_chain()
        self.assertTrue(res.ok, res.detail)
        # Genesis + M001 + M002 + 3 cases-Writes = 6 Einträge.
        self.assertEqual(self._audit_count(), 6)


if __name__ == "__main__":
    unittest.main()

# =============================================================================
# tests/test_onboarding_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Onboarding/Offboarding (AP-2G)
# =============================================================================
# Testsuite fuer Build 464: OnboardingRepo (auditierter Schreibpfad, M017).
#
# OR01 — set_step('erledigt'): auditiert; audit_seq gesetzt; FREITEXT (note)
#        NICHT im Payload.
# OR02 — 'nicht_zutreffend' ohne Notiz -> Fehler, KEINE Zeile.
# OR03 — checklist(): ALLE Katalog-Schritte; gesetzter Schritt traegt seinen
#        Zustand, der Rest 'offen'.
# OR04 — Reset auf 'offen' loescht die Zeile (auditiert).
# OR05 — unbekannter Schritt/Person -> Fehler.
# OR06 — open_case_load(): zaehlt offen zugewiesene Faelle.
# OR07 — kein unauditierter Schreibpfad (ohne Writer).
#
# Version: v0.7.464 · Build: 464 · 2026-07-20
# =============================================================================

import json
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
from management.cases.cases_repo import CasesRepo
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.onboarding.onboarding_repo import OnboardingError, OnboardingRepo

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


class OnboardingRepoTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        now = int(time.time())
        for pid, un, sup in ((1, "chef", 1), (2, "mueller", 0)):
            con.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?, ?, ?, 1, ?, 0, ?)", (pid, un, un.title(), sup, now))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con
        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.repo = OnboardingRepo(self.con, self.writer)

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

    def _row(self, pid, kind, step):
        return self.con.execute(
            "SELECT * FROM onboarding_item WHERE person_id=? AND kind=? "
            "AND step_code=?", (pid, kind, step)).fetchone()

    # OR01 -------------------------------------------------------------------
    def test_or01_set_step_audited_no_freetext(self):
        res = self.repo.set_step(
            person_id=2, kind="onboarding", step_code="einweisung",
            status="erledigt", note="am 2026-07-20 durch Chefin", actor_id=1)
        self.assertTrue(res["created"])
        self.assertGreater(res["audit_seq"], 0)
        row = self._row(2, "onboarding", "einweisung")
        self.assertEqual(row["status"], "erledigt")
        self.assertEqual(row["audit_seq"], res["audit_seq"])
        self.assertEqual(row["done_by"], 1)

        ev = self.con.execute(
            "SELECT event_type, content FROM audit_log WHERE seq=?",
            (res["audit_seq"],)).fetchone()
        self.assertEqual(ev["event_type"], "onboarding_step_set")
        payload = json.loads(ev["content"])
        self.assertEqual(payload["step_code"], "einweisung")
        self.assertEqual(payload["status"], "erledigt")
        self.assertIn("note_len", payload)
        self.assertNotIn("note", payload)

    # OR02 -------------------------------------------------------------------
    def test_or02_reason_required(self):
        with self.assertRaises(OnboardingError):
            self.repo.set_step(person_id=2, kind="offboarding",
                               step_code="zugang_gesperrt",
                               status="nicht_zutreffend", note="  ", actor_id=1)
        self.assertIsNone(self._row(2, "offboarding", "zugang_gesperrt"))

    # OR03 -------------------------------------------------------------------
    def test_or03_checklist_all_steps(self):
        self.repo.set_step(person_id=2, kind="onboarding",
                           step_code="rolle_zugewiesen", status="erledigt",
                           actor_id=1)
        rows = self.repo.checklist(2, "onboarding")
        self.assertEqual(len(rows), 5)
        by = {r["step_code"]: r for r in rows}
        self.assertEqual(by["rolle_zugewiesen"]["status"], "erledigt")
        self.assertEqual(by["einweisung"]["status"], "offen")

    # OR04 -------------------------------------------------------------------
    def test_or04_reset_to_offen_deletes(self):
        self.repo.set_step(person_id=2, kind="onboarding",
                           step_code="zugang_bestaetigt", status="erledigt",
                           actor_id=1)
        self.assertIsNotNone(self._row(2, "onboarding", "zugang_bestaetigt"))
        res = self.repo.set_step(person_id=2, kind="onboarding",
                                 step_code="zugang_bestaetigt", status="offen",
                                 actor_id=1)
        self.assertTrue(res["removed"])
        self.assertIsNone(self._row(2, "onboarding", "zugang_bestaetigt"))

    # OR05 -------------------------------------------------------------------
    def test_or05_unknown_step_and_person(self):
        with self.assertRaises(OnboardingError):
            self.repo.set_step(person_id=2, kind="onboarding",
                               step_code="quatsch", status="erledigt",
                               actor_id=1)
        with self.assertRaises(OnboardingError):
            self.repo.set_step(person_id=999, kind="onboarding",
                               step_code="einweisung", status="erledigt",
                               actor_id=1)

    # OR06 -------------------------------------------------------------------
    def test_or06_open_case_load(self):
        cases = CasesRepo(self.con, self.writer)
        cases.create_case(18, "boarder18", actor_id=1)
        cases.create_case(19, "boarder19", actor_id=1)
        cases.assign(18, 2, actor_id=1)          # offen, Person 2
        self.assertEqual(self.repo.open_case_load(2), 1)
        self.assertEqual(self.repo.open_case_load(1), 0)

    # OR07 -------------------------------------------------------------------
    def test_or07_no_unaudited_write(self):
        ro = OnboardingRepo(self.con)
        with self.assertRaises(OnboardingError):
            ro.set_step(person_id=2, kind="onboarding", step_code="einweisung",
                        status="erledigt", actor_id=1)


if __name__ == "__main__":
    unittest.main()

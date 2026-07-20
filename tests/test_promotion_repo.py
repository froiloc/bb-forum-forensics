# =============================================================================
# tests/test_promotion_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Betrieb/Governance (AP-2G)
# =============================================================================
# Testsuite fuer Build 460: PromotionRepo (auditierter Schreibpfad, M015).
#
# PR01 — record_decision (erste Entscheidung): Zeile angelegt, audit_seq/
#        created_audit_seq gesetzt; FREITEXT (grund/herkunft) steht NICHT im
#        audit_log-Payload, nur die Textlaenge.
# PR02 — Uebergang wird erzwungen; nach Endzustand schlaegt eine weitere
#        Entscheidung fehl und die Zeile bleibt UNVERAENDERT (Rollback).
# PR03 — Grund-Pflicht: zurueckgestellt/fremdzustaendig ohne Grund -> Fehler,
#        KEINE Zeile.
# PR04 — allowed_uids-Gate: Entscheidung fuer einen Nicht-Kandidaten -> Fehler,
#        KEINE Zeile.
# PR05 — annotate(): Kandidat ohne Zeile ist 'offen'; mit Zeile traegt er seinen
#        Zustand; Wiederaufgriff zurueckgestellt->gesichtet funktioniert.
# PR06 — Kein unauditierter Schreibpfad (Repo ohne Writer verweigert).
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
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
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.ops.promotion_repo import PromotionError, PromotionRepo

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


class PromotionRepoTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        now = int(time.time())
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (1, 'h001', 'Chefin', 1, 1, 0, ?)", (now,))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con
        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.repo = PromotionRepo(self.con, self.writer)

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

    def _row(self, subject_id):
        return self.con.execute(
            "SELECT * FROM forum_promotion WHERE subject_id=?", (subject_id,)
        ).fetchone()

    # PR01 -------------------------------------------------------------------
    def test_pr01_first_decision_audited_no_freetext(self):
        res = self.repo.record_decision(
            subject_id=42, target_status="gesichtet",
            herkunft="Nachbarforum X", actor_id=1)
        self.assertTrue(res["created"])
        self.assertEqual(res["von"], "offen")
        self.assertEqual(res["auf"], "gesichtet")
        self.assertGreater(res["audit_seq"], 0)

        row = self._row(42)
        self.assertEqual(row["status"], "gesichtet")
        self.assertEqual(row["audit_seq"], res["audit_seq"])
        self.assertEqual(row["created_audit_seq"], res["audit_seq"])
        self.assertEqual(row["decided_by"], 1)

        ev = self.con.execute(
            "SELECT event_type, content FROM audit_log WHERE seq=?",
            (res["audit_seq"],)).fetchone()
        self.assertEqual(ev["event_type"], "promotion_decided")
        payload = json.loads(ev["content"])
        # FAKTEN ja, FREITEXT nein (Sensibilitaetsregel).
        self.assertEqual(payload["subject_id"], 42)
        self.assertEqual(payload["auf"], "gesichtet")
        self.assertIn("herkunft_len", payload)
        self.assertNotIn("herkunft", payload)
        self.assertEqual(payload["herkunft_len"], len("Nachbarforum X"))

    # PR02 -------------------------------------------------------------------
    def test_pr02_transition_enforced_rollback(self):
        self.repo.record_decision(subject_id=7, target_status="uebernommen",
                                  actor_id=1)
        row_before = dict(self._row(7))
        # 'uebernommen' ist endgueltig -> jede weitere Entscheidung scheitert.
        with self.assertRaises(PromotionError):
            self.repo.record_decision(subject_id=7, target_status="gesichtet",
                                      actor_id=1)
        row_after = dict(self._row(7))
        self.assertEqual(row_before, row_after)   # nichts veraendert (Rollback)

    # PR03 -------------------------------------------------------------------
    def test_pr03_reason_required(self):
        with self.assertRaises(PromotionError):
            self.repo.record_decision(subject_id=8, target_status="zurueckgestellt",
                                      grund="   ", actor_id=1)
        self.assertIsNone(self._row(8))           # keine Zeile angelegt
        with self.assertRaises(PromotionError):
            self.repo.record_decision(subject_id=8, target_status="fremdzustaendig",
                                      actor_id=1)
        self.assertIsNone(self._row(8))

    # PR04 -------------------------------------------------------------------
    def test_pr04_allowed_uids_gate(self):
        with self.assertRaises(PromotionError):
            self.repo.record_decision(
                subject_id=999, target_status="gesichtet", actor_id=1,
                allowed_uids={1, 2, 3})
        self.assertIsNone(self._row(999))
        # In der Kandidatenmenge -> erlaubt.
        self.repo.record_decision(
            subject_id=2, target_status="gesichtet", actor_id=1,
            allowed_uids={1, 2, 3})
        self.assertIsNotNone(self._row(2))

    # PR05 -------------------------------------------------------------------
    def test_pr05_annotate_and_reopen(self):
        self.repo.record_decision(subject_id=10, target_status="zurueckgestellt",
                                  grund="kein Bezug", actor_id=1)
        rows = self.repo.annotate([10, 11, 12])
        by_uid = {r["subject_id"]: r for r in rows}
        self.assertEqual(by_uid[10]["status"], "zurueckgestellt")
        self.assertEqual(by_uid[11]["status"], "offen")   # ohne Zeile
        self.assertEqual(by_uid[12]["status"], "offen")
        self.assertFalse(by_uid[11]["is_final"])
        # Wiederaufgriff zurueckgestellt -> gesichtet.
        res = self.repo.record_decision(subject_id=10, target_status="gesichtet",
                                        actor_id=1)
        self.assertFalse(res["created"])
        self.assertEqual(res["von"], "zurueckgestellt")
        self.assertEqual(self._row(10)["status"], "gesichtet")

    # PR06 -------------------------------------------------------------------
    def test_pr06_no_unaudited_write(self):
        ro = PromotionRepo(self.con)              # kein Writer
        with self.assertRaises(PromotionError):
            ro.record_decision(subject_id=5, target_status="gesichtet", actor_id=1)


if __name__ == "__main__":
    unittest.main()

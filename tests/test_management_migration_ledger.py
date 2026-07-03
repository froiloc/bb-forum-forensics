# =============================================================================
# tests/test_management_migration_ledger.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 318: MigrationLedger (append-only, hash-verkettet).
# VOLLSTAENDIG automatisiert, isoliert — kein Executor, keine echte Migration,
# keine Evidenz. Betrifft nur die Betriebs-DB migration.db.
#
# L01 — record_start haengt 'started' an; erste Zeile prev_hash == GENESIS, seq=1
# L02 — record_result haengt Terminal an; prev_hash == row_hash der Vorzeile, seq=2
# L03 — verify_chain ok nach mehreren Eintraegen
# L04 — Manipulation eines Inhaltsfelds -> verify_chain meldet Bruch an der Stelle
# L05 — Manipulation von prev_hash -> verify_chain meldet prev_hash-Bruch
# L06 — interrupted_runs: Start ohne Terminal wird erkannt; vollstaendiger Lauf nicht
# L07 — list_runs filtert nach db_kind/uid
# L08 — append-only: fruehere Zeilen (seq, row_hash) bleiben nach weiteren Appends unveraendert
# L09 — Hash deckt Inhaltsfelder ab: Aenderung an post_sha512 bricht die Kette
# L10 — record_result weist ungueltigen Status ab
# L11 — GENESIS aus audit/hashing wiederverwendet (Konsistenz)
# L12 — voller Lebenszyklus start->result('ok'); verify_chain ok; keine unterbrochenen
#
# Version: v0.7.318 · Build: 318 · 2026-07-03
# =============================================================================

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.audit.hashing import GENESIS_PREV_HASH
from management.migration_fleet.ledger import MigrationLedger
from management.migration_fleet.migration_db import MigrationDb


class MigrationLedgerTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.path = os.path.join(self._tmp, "migration.db")
        self.con = sqlite3.connect(self.path)
        self.con.isolation_level = None
        MigrationDb(self.con).ensure_schema()
        self.ledger = MigrationLedger(self.con)

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

    def _row(self, seq):
        self.con.row_factory = sqlite3.Row
        try:
            return self.con.execute(
                "SELECT * FROM migration_runs WHERE seq=?", (seq,)).fetchone()
        finally:
            self.con.row_factory = None

    # L01 -------------------------------------------------------------------
    def test_l01_record_start(self):
        seq = self.ledger.record_start(
            db_kind="evidence", uid=18, from_version=0, to_version=1,
            started_at=1000, pre_sha512="abc", backup_path="/bk/e18.backup.db",
            operator="h001")
        self.assertEqual(seq, 1)
        row = self._row(1)
        self.assertEqual(row["status"], "started")
        self.assertEqual(row["prev_hash"], GENESIS_PREV_HASH)
        self.assertIsNone(row["finished_at"])

    # L02 -------------------------------------------------------------------
    def test_l02_record_result_chains(self):
        self.ledger.record_start(db_kind="evidence", uid=18, from_version=0,
                                 to_version=1, started_at=1000)
        seq2 = self.ledger.record_result(
            db_kind="evidence", uid=18, from_version=0, to_version=1,
            started_at=1000, status="ok", finished_at=1005, post_sha512="def",
            verifier="h002")
        self.assertEqual(seq2, 2)
        self.assertEqual(self._row(2)["prev_hash"], self._row(1)["row_hash"])

    # L03 -------------------------------------------------------------------
    def test_l03_verify_chain_ok(self):
        for uid in (18, 19, 20):
            self.ledger.record_start(db_kind="evidence", uid=uid, from_version=0,
                                     to_version=1, started_at=1000)
            self.ledger.record_result(db_kind="evidence", uid=uid, from_version=0,
                                      to_version=1, started_at=1000, status="ok")
        self.assertTrue(self.ledger.verify_chain().ok)

    # L04 -------------------------------------------------------------------
    def test_l04_tamper_content_detected(self):
        self.ledger.record_start(db_kind="evidence", uid=18, from_version=0,
                                 to_version=1, started_at=1000)
        self.ledger.record_result(db_kind="evidence", uid=18, from_version=0,
                                  to_version=1, started_at=1000, status="ok")
        # Inhaltsfeld nachtraeglich veraendern (status 'ok' -> 'failed').
        self.con.execute("UPDATE migration_runs SET status='failed' WHERE seq=2")
        result = self.ledger.verify_chain()
        self.assertFalse(result.ok)
        self.assertEqual(result.first_bad_seq, 2)

    # L05 -------------------------------------------------------------------
    def test_l05_tamper_prev_hash_detected(self):
        self.ledger.record_start(db_kind="evidence", uid=18, from_version=0,
                                 to_version=1, started_at=1000)
        self.ledger.record_result(db_kind="evidence", uid=18, from_version=0,
                                  to_version=1, started_at=1000, status="ok")
        self.con.execute("UPDATE migration_runs SET prev_hash='0'||substr(prev_hash,2) WHERE seq=2")
        result = self.ledger.verify_chain()
        self.assertFalse(result.ok)
        self.assertEqual(result.first_bad_seq, 2)

    # L06 -------------------------------------------------------------------
    def test_l06_interrupted_runs(self):
        # Lauf A: Start ohne Abschluss -> unterbrochen.
        self.ledger.record_start(db_kind="forensic", uid=18, from_version=0,
                                 to_version=1, started_at=1000)
        # Lauf B: vollstaendig.
        self.ledger.record_start(db_kind="forensic", uid=19, from_version=0,
                                 to_version=1, started_at=2000)
        self.ledger.record_result(db_kind="forensic", uid=19, from_version=0,
                                  to_version=1, started_at=2000, status="ok")
        interrupted = self.ledger.interrupted_runs()
        self.assertEqual(len(interrupted), 1)
        self.assertEqual((interrupted[0].db_kind, interrupted[0].uid,
                          interrupted[0].to_version), ("forensic", 18, 1))

    # L07 -------------------------------------------------------------------
    def test_l07_list_runs_filter(self):
        self.ledger.record_start(db_kind="evidence", uid=18, from_version=0,
                                 to_version=1, started_at=1000)
        self.ledger.record_start(db_kind="assets", uid=18, from_version=0,
                                 to_version=1, started_at=1000)
        self.ledger.record_start(db_kind="evidence", uid=19, from_version=0,
                                 to_version=1, started_at=1000)
        self.assertEqual(len(self.ledger.list_runs(db_kind="evidence")), 2)
        self.assertEqual(len(self.ledger.list_runs(db_kind="evidence", uid=18)), 1)

    # L08 -------------------------------------------------------------------
    def test_l08_append_only_prior_rows_stable(self):
        self.ledger.record_start(db_kind="evidence", uid=18, from_version=0,
                                 to_version=1, started_at=1000)
        seq1_hash = self._row(1)["row_hash"]
        # Weitere Appends.
        for uid in (19, 20):
            self.ledger.record_start(db_kind="evidence", uid=uid, from_version=0,
                                     to_version=1, started_at=1000)
        self.assertEqual(self._row(1)["row_hash"], seq1_hash)
        self.assertTrue(self.ledger.verify_chain().ok)

    # L09 -------------------------------------------------------------------
    def test_l09_hash_covers_post_sha512(self):
        self.ledger.record_start(db_kind="evidence", uid=18, from_version=0,
                                 to_version=1, started_at=1000)
        self.ledger.record_result(db_kind="evidence", uid=18, from_version=0,
                                  to_version=1, started_at=1000, status="ok",
                                  post_sha512="AAA")
        self.con.execute("UPDATE migration_runs SET post_sha512='BBB' WHERE seq=2")
        self.assertFalse(self.ledger.verify_chain().ok)

    # L10 -------------------------------------------------------------------
    def test_l10_invalid_status_rejected(self):
        with self.assertRaises(ValueError):
            self.ledger.record_result(db_kind="evidence", uid=18, from_version=0,
                                      to_version=1, started_at=1000,
                                      status="halbfertig")

    # L11 -------------------------------------------------------------------
    def test_l11_genesis_reused(self):
        self.ledger.record_start(db_kind="evidence", uid=18, from_version=0,
                                 to_version=1, started_at=1000)
        self.assertEqual(self._row(1)["prev_hash"], GENESIS_PREV_HASH)
        self.assertEqual(len(GENESIS_PREV_HASH), 64)

    # L12 -------------------------------------------------------------------
    def test_l12_full_lifecycle(self):
        s = self.ledger.record_start(db_kind="assets", uid=18, from_version=0,
                                     to_version=1, started_at=1000,
                                     pre_sha512="pre")
        self.assertEqual(s, 1)
        self.ledger.record_result(db_kind="assets", uid=18, from_version=0,
                                  to_version=1, started_at=1000, status="ok",
                                  finished_at=1010, post_sha512="post",
                                  verifier="h002")
        self.assertTrue(self.ledger.verify_chain().ok)
        self.assertEqual(self.ledger.interrupted_runs(), [])


if __name__ == "__main__":
    unittest.main()

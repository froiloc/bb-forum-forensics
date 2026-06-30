# =============================================================================
# tests/test_management_audit.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite für das Migrations-Gerüst + Audit-Log + Write-Gateway (Tag 1).
#
# A01 — MigrationRunner legt schema_migrations + audit_log an; 2. Lauf = No-Op
# A02 — Genesis korrekt (prev_hash='0'*64, event_type='genesis');
#       MIGRATION_APPLIED als seq=2 inkl. deployed_by
# A03 — append verkettet korrekt; row_hash == Nachrechnung
# A04 — verify_chain = OK auf intakter Kette
# A05 — manipulierte content-Zeile (Trigger umgangen) -> verify_chain meldet seq
# A06 — UPDATE/DELETE auf audit_log -> RAISE(ABORT) (Trigger aktiv)
# A07 — Gateway: Rollback lässt weder Write noch Audit-Eintrag zurück
# A08 — meta-Reserve: Zeile mit gesetztem meta verifiziert; Formel unverändert
# A09 — zwei sequentielle Appends -> lückenlose, korrekte Kette
#
# Version: v0.7.306 · Build: 306 · 2026-07-01
# =============================================================================

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.audit.audit_log import AuditLog
from management.audit.event_types import EventType
from management.audit.hashing import GENESIS_PREV_HASH, compute_row_hash
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.coordinator import m001_audit_log
from management.migrations.runner import MigrationRunner


def _recompute(row: sqlite3.Row) -> str:
    """Rechnet den row_hash aus den GESPEICHERTEN Feldern nach."""
    return compute_row_hash(
        row["prev_hash"],
        int(row["seq"]),
        int(row["ts"]),
        row["actor_id"],
        row["event_type"],
        row["target_type"],
        row["target_id"],
        row["content"],
        row["meta"],
    )


class ManagementAuditTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        # Frisches, migriertes coordinator.db (M001 angewandt).
        self.audit = AuditLog(self.con)
        self.runner = MigrationRunner(
            self.con, [m001_audit_log], audit=self.audit, deployed_by="tester"
        )
        self.applied = self.runner.run()
        self.writer = CoordinatorWriter(self.con, self.audit)

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

    # ------------------------------------------------------------------- A01
    def test_a01_runner_creates_and_is_idempotent(self):
        self.assertEqual(self.applied, [1])
        tables = {
            r["name"]
            for r in self.con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertIn("schema_migrations", tables)
        self.assertIn("audit_log", tables)
        # Registry: genau M001.
        migs = self.con.execute(
            "SELECT version, kind FROM schema_migrations"
        ).fetchall()
        self.assertEqual([(m["version"], m["kind"]) for m in migs], [(1, "additive")])
        # Zweiter Lauf = No-Op.
        again = self.runner.run()
        self.assertEqual(again, [])
        # audit_log unverändert (genesis + migration_applied).
        cnt = self.con.execute("SELECT COUNT(*) AS c FROM audit_log").fetchone()["c"]
        self.assertEqual(cnt, 2)

    # ------------------------------------------------------------------- A02
    def test_a02_genesis_and_migration_applied(self):
        g = self.con.execute("SELECT * FROM audit_log WHERE seq=1").fetchone()
        self.assertEqual(g["event_type"], EventType.GENESIS)
        self.assertEqual(g["prev_hash"], GENESIS_PREV_HASH)
        m = self.con.execute("SELECT * FROM audit_log WHERE seq=2").fetchone()
        self.assertEqual(m["event_type"], EventType.MIGRATION_APPLIED)
        # Verkettung: m.prev_hash == g.row_hash
        self.assertEqual(m["prev_hash"], g["row_hash"])
        content = json.loads(m["content"])
        self.assertEqual(content["deployed_by"], "tester")
        self.assertEqual(content["kind"], "additive")

    # ------------------------------------------------------------------- A03
    def test_a03_append_chains_and_hash_matches(self):
        seq = self.writer.audited_write(
            do_write=lambda con: {"probe": 1},
            event_type=EventType.CHAIN_VERIFIED,
            actor_id=None,
            target_type="chain",
            target_id="coordinator",
        )
        self.assertEqual(seq, 3)
        row = self.con.execute("SELECT * FROM audit_log WHERE seq=3").fetchone()
        self.assertEqual(row["row_hash"], _recompute(row))
        # Verkettung an seq=2.
        prev = self.con.execute("SELECT row_hash FROM audit_log WHERE seq=2").fetchone()
        self.assertEqual(row["prev_hash"], prev["row_hash"])

    # ------------------------------------------------------------------- A04
    def test_a04_verify_ok(self):
        self.writer.audited_write(
            do_write=lambda con: {"x": "y"},
            event_type=EventType.CHAIN_VERIFIED,
            actor_id=None, target_type=None, target_id=None,
        )
        res = self.audit.verify_chain()
        self.assertTrue(res.ok, res.detail)
        self.assertIsNone(res.first_bad_seq)

    # ------------------------------------------------------------------- A05
    def test_a05_tamper_detected(self):
        # Angreifer mit Roh-Zugriff: Trigger löschen, Inhalt von seq=2 ändern.
        self.con.execute("DROP TRIGGER audit_log_no_update")
        self.con.execute(
            "UPDATE audit_log SET content = ? WHERE seq = 2",
            (json.dumps({"tampered": True}),),
        )
        res = self.audit.verify_chain()
        self.assertFalse(res.ok)
        self.assertEqual(res.first_bad_seq, 2)

    # ------------------------------------------------------------------- A06
    def test_a06_update_delete_blocked(self):
        with self.assertRaises(sqlite3.Error):
            self.con.execute("UPDATE audit_log SET ts = 0 WHERE seq = 1")
        with self.assertRaises(sqlite3.Error):
            self.con.execute("DELETE FROM audit_log WHERE seq = 1")

    # ------------------------------------------------------------------- A07
    def test_a07_atomic_rollback(self):
        self.con.execute("CREATE TABLE t (x INTEGER)")
        before_audit = self.con.execute(
            "SELECT COUNT(*) AS c FROM audit_log"
        ).fetchone()["c"]

        def _bad_write(con):
            con.execute("INSERT INTO t (x) VALUES (42)")
            raise ValueError("absichtlicher Fehler nach Teil-Write")

        with self.assertRaises(ValueError):
            self.writer.audited_write(
                do_write=_bad_write,
                event_type=EventType.CHAIN_VERIFIED,
                actor_id=None, target_type=None, target_id=None,
            )
        # Weder der Write in t noch ein Audit-Eintrag dürfen überlebt haben.
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) AS c FROM t").fetchone()["c"], 0
        )
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) AS c FROM audit_log").fetchone()["c"],
            before_audit,
        )

    # ------------------------------------------------------------------- A08
    def test_a08_meta_reserve(self):
        self.writer.audited_write(
            do_write=lambda con: {"k": "v"},
            event_type=EventType.CHAIN_VERIFIED,
            actor_id=None, target_type=None, target_id=None,
            meta={"future_field": "wert", "n": 7},
        )
        row = self.con.execute(
            "SELECT * FROM audit_log ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        self.assertNotEqual(row["meta"], "")
        self.assertEqual(row["row_hash"], _recompute(row))
        self.assertTrue(self.audit.verify_chain().ok)

    # ------------------------------------------------------------------- A09
    def test_a09_two_sequential_appends(self):
        s1 = self.writer.audited_write(
            do_write=lambda con: {"i": 1},
            event_type=EventType.CHAIN_VERIFIED,
            actor_id=None, target_type=None, target_id=None,
        )
        s2 = self.writer.audited_write(
            do_write=lambda con: {"i": 2},
            event_type=EventType.CHAIN_VERIFIED,
            actor_id=None, target_type=None, target_id=None,
        )
        self.assertEqual((s1, s2), (3, 4))
        res = self.audit.verify_chain()
        self.assertTrue(res.ok, res.detail)
        seqs = [r["seq"] for r in self.con.execute(
            "SELECT seq FROM audit_log ORDER BY seq ASC"
        )]
        self.assertEqual(seqs, [1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()

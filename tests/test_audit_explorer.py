# =============================================================================
# tests/test_audit_explorer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Audit-Explorer (AP-2E)
# =============================================================================
# Testsuite fuer Build 467: AuditExplorer (read-only ueber audit_log).
#
# AE01 — query() ohne Filter: total, Seitengroesse (Default-Limit), has_more.
# AE02 — Filter event_types: nur passende Ereignisse.
# AE03 — Filter actor_id + seq-Bereich.
# AE04 — Paginierung: offset verschiebt; total bleibt.
# AE05 — facets(): vorhandene Event-Typen + Akteure (mit Namen).
# AE06 — get(seq): Einzeleintrag mit content/row_hash; unbekannt -> None.
# AE07 — limit-Clamp (>MAX -> MAX; <1 -> 1); ungueltiger Filter -> Fehler.
#
# Als realistische Datenbasis dient die synthetische Demo-DB (demo_seed).
# Version: v0.7.467 · Build: 467 · 2026-07-20
# =============================================================================

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.audit.audit_explorer import (
    AuditExplorer,
    AuditExplorerError,
    DEFAULT_LIMIT,
    MAX_LIMIT,
)
from management.distribution import demo_seed


class AuditExplorerTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp()
        cls._db = os.path.join(cls._tmp, "coordinator.db")
        demo_seed.seed(cls._db)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def setUp(self):
        self.con = sqlite3.connect("file:%s?mode=ro" % self._db, uri=True)
        self.con.row_factory = sqlite3.Row
        self.ex = AuditExplorer(self.con)
        self.total = int(self.con.execute(
            "SELECT COUNT(*) FROM audit_log").fetchone()[0])

    def tearDown(self):
        self.con.close()

    # AE01 -------------------------------------------------------------------
    def test_ae01_no_filter(self):
        res = self.ex.query()
        self.assertEqual(res["total"], self.total)
        self.assertEqual(res["limit"], DEFAULT_LIMIT)
        self.assertLessEqual(len(res["rows"]), DEFAULT_LIMIT)
        if self.total > DEFAULT_LIMIT:
            self.assertTrue(res["has_more"])
        # Neueste zuerst (seq DESC).
        seqs = [r["seq"] for r in res["rows"]]
        self.assertEqual(seqs, sorted(seqs, reverse=True))
        # Akteursname ist angereichert.
        self.assertIn("actor_name", res["rows"][0])

    # AE02 -------------------------------------------------------------------
    def test_ae02_filter_event_types(self):
        res = self.ex.query(event_types=["case_created"])
        self.assertTrue(res["total"] >= 6)   # 6 Demo-Faelle
        self.assertTrue(all(r["event_type"] == "case_created"
                            for r in res["rows"]))

    # AE03 -------------------------------------------------------------------
    def test_ae03_filter_actor_and_seq(self):
        res = self.ex.query(actor_id=1, seq_from=1, seq_to=self.total)
        self.assertTrue(all(r["actor_id"] == 1 for r in res["rows"]))
        # seq-Obergrenze greift.
        res2 = self.ex.query(seq_to=5)
        self.assertTrue(all(r["seq"] <= 5 for r in res2["rows"]))

    # AE04 -------------------------------------------------------------------
    def test_ae04_pagination(self):
        p1 = self.ex.query(limit=10, offset=0)
        p2 = self.ex.query(limit=10, offset=10)
        self.assertEqual(p1["total"], p2["total"])
        s1 = {r["seq"] for r in p1["rows"]}
        s2 = {r["seq"] for r in p2["rows"]}
        self.assertEqual(s1 & s2, set())   # disjunkte Seiten

    # AE05 -------------------------------------------------------------------
    def test_ae05_facets(self):
        f = self.ex.facets()
        self.assertIn("case_created", f["event_types"])
        self.assertTrue(any(a["actor_id"] == 1 and a["actor_name"]
                            for a in f["actors"]))

    # AE06 -------------------------------------------------------------------
    def test_ae06_get(self):
        row = self.ex.get(1)
        self.assertIsNotNone(row)
        self.assertIn("content", row)
        self.assertIn("row_hash", row)
        self.assertIsNone(self.ex.get(10_000_000))

    # AE07 -------------------------------------------------------------------
    def test_ae07_limit_clamp_and_bad_filter(self):
        self.assertEqual(self.ex.query(limit=99999)["limit"], MAX_LIMIT)
        self.assertEqual(self.ex.query(limit=0)["limit"], 1)
        with self.assertRaises(AuditExplorerError):
            self.ex.query(actor_id="abc")


if __name__ == "__main__":
    unittest.main()

# =============================================================================
# tests/test_demo_seed.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: LKAe-Distribution (AP-2G)
# =============================================================================
# Testsuite fuer Build 466: demo_seed (synthetische Demo-coordinator.db).
#
# DS01 — seed(): DB entsteht; volle Migration; verify_chain().ok; erwartete
#        Grundmengen (Personen, Faelle, RBAC-Faehigkeiten).
# DS02 — AP-2G-Artefakte vorhanden (Promotion, Freigabe, Onboarding, Extern).
# DS03 — rein synthetisch: alle Fall-Benutzernamen tragen das 'demo_'-Praefix.
# DS04 — seed() verweigert eine bereits existierende DB (kein stilles Ueber-
#        schreiben).
#
# Version: v0.7.466 · Build: 466 · 2026-07-20
# =============================================================================

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.audit.audit_log import AuditLog
from management.distribution import demo_seed


class DemoSeedTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db = os.path.join(self._tmp, "data", "coordinator.db")
        self.summary = demo_seed.seed(self.db)
        self.con = sqlite3.connect(self.db)
        self.con.row_factory = sqlite3.Row

    def tearDown(self):
        try:
            self.con.close()
        finally:
            for root, _dirs, files in os.walk(self._tmp, topdown=False):
                for fn in files:
                    try:
                        os.remove(os.path.join(root, fn))
                    except OSError:
                        pass
                try:
                    os.rmdir(root)
                except OSError:
                    pass

    def _count(self, table):
        return int(self.con.execute(
            "SELECT COUNT(*) FROM %s" % table).fetchone()[0])

    # DS01 -------------------------------------------------------------------
    def test_ds01_valid_and_populated(self):
        self.assertTrue(os.path.exists(self.db))
        self.assertTrue(AuditLog(self.con).verify_chain().ok,
                        "Demo-Audit-Kette nicht intakt")
        self.assertEqual(self._count("person"), 4)
        self.assertEqual(self._count("cases"), 6)
        # Alle Migrationen -> voller RBAC-Katalog (30 ab Build 468: +2
        # crossref.view/crossref.edit aus M018; zuvor 28 ab Build 464).
        # +1 ab Build 501: personnel.sync aus M020 -> 31.
        # +2 ab Build 503: personnel.view/personnel.edit aus M021 -> 33.
        # +1 ab Build 515: escalation.view aus M026 -> 34.
        # +1 ab Build 517: escalation.ack aus M027 -> 35.
        # +1 ab Build 519: nextactions.view aus M028 -> 36.
        # +1 ab Build 520: handover.view aus M029 -> 37.
        # +1 ab Build 521: retention.view aus M030 -> 38.
        # +1 ab Build 524: limitation.view aus M031 -> 39.
        # +1 ab Build 533: tatzeit.edit aus M032 -> 40.
        # +1 ab Build 536: matrix.view aus M033 -> 41.
        # +2 ab Build 540: qs.view/qs.edit aus M034 -> 43.
        # +1 ab Build 561: fulltext.release aus M040 (AP-3E, Instanz B)
        #   -> 44. Basis 43 ist der beim Rebase vorgefundene Stand.
        # +1 ab Build 542: metrics.view aus M035 -> 45.
        self.assertEqual(self._count("rbac_capability"), 45)
        # Leitung hat die Supervisor-Rolle + Grants.
        self.assertGreater(self._count("rbac_grant"), 0)
        self.assertEqual(self.summary["demo"], True)

    # DS02 -------------------------------------------------------------------
    def test_ds02_ap2g_artifacts(self):
        self.assertGreaterEqual(self._count("forum_promotion"), 1)
        self.assertGreaterEqual(self._count("case_release"), 1)
        self.assertGreaterEqual(self._count("onboarding_item"), 1)
        self.assertGreaterEqual(self._count("external_matters"), 1)

    # DS03 -------------------------------------------------------------------
    def test_ds03_synthetic_only(self):
        names = [r[0] for r in self.con.execute(
            "SELECT username FROM cases").fetchall()]
        self.assertTrue(all(n.startswith("demo_") for n in names), names)
        # Der Freigabe-Empfaenger ist eine Demo-Kennung.
        rec = self.con.execute(
            "SELECT recipient_kennung FROM case_release LIMIT 1").fetchone()
        self.assertTrue(str(rec[0]).startswith("demo_"))

    # DS04 -------------------------------------------------------------------
    def test_ds04_refuses_existing(self):
        with self.assertRaises(FileExistsError):
            demo_seed.seed(self.db)


if __name__ == "__main__":
    unittest.main()

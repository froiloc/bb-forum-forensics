# =============================================================================
# tests/test_management_migration_companion.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 320: MigrationCompanion (gefuehrte Zustandsmaschine).
# VOLLSTAENDIG automatisiert, NUR synthetische DBs — kein reales Beweismaterial.
#
# J01 — preflight ok: synchronisierter Katalog, intaktes/leeres Ledger
# J02 — Tor KATALOG_DRIFT blockiert (Katalog nicht synchronisiert -> uncataloged)
# J03 — Tor LEDGER_KETTE blockiert (manipulierte Ledger-Zeile)
# J04 — Tor UNTERBROCHENE_LAEUFE blockiert ('started' ohne Abschluss)
# J05 — Tor KEIN_BACKUP_DIR blockiert (require_backup_dir, kein Backup-Ziel)
# J06 — execute verweigert bei confirm=False (executed=False)
# J07 — execute verweigert, wenn Vorpruefung blockiert (Drift) trotz confirm=True
# J08 — execute happy path: alle Tore offen + confirm -> ausgefuehrt, ok
# J09 — execute mit Bad-Migration -> failed_restored geflaggt, reason weist auf
#       menschliche Pruefung hin
# J10 — summary: Ledger-Kette ok, Registry-Status, Vieraugen-Erinnerung
#
# Version: v0.7.320 · Build: 320 · 2026-07-03
# =============================================================================

import importlib
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.migration_fleet.catalog import CatalogReconciler
from management.migration_fleet.companion import MigrationCompanion
from management.migration_fleet.ledger import MigrationLedger
from management.migration_fleet.migration_db import MigrationDb
from management.migration_fleet.planner import TargetDb

_GOOD_M001 = 'VERSION=1\nNAME="baseline"\nKIND="additive"\ndef up(con):\n    pass\n'
_BAD_LOSS_M002 = ('VERSION=2\nNAME="bad-loss"\nKIND="additive"\n'
                  'def up(con):\n    con.execute("DELETE FROM annotations")\n')


class MigrationCompanionTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._pkg_root = os.path.join(self._tmp, "pkgs")
        os.makedirs(self._pkg_root, exist_ok=True)
        sys.path.insert(0, self._pkg_root)
        self.mcon = sqlite3.connect(os.path.join(self._tmp, "migration.db"))
        self.mcon.isolation_level = None
        self.mdb = MigrationDb(self.mcon)
        self.mdb.ensure_schema()
        self.ledger = MigrationLedger(self.mcon)
        self.backup_dir = os.path.join(self._tmp, "backups")

    def tearDown(self):
        try:
            self.mcon.close()
        finally:
            if self._pkg_root in sys.path:
                sys.path.remove(self._pkg_root)
            for root, _d, files in os.walk(self._tmp, topdown=False):
                for fn in files:
                    try:
                        os.remove(os.path.join(root, fn))
                    except OSError:
                        pass
                try:
                    os.rmdir(root)
                except OSError:
                    pass

    # ---- Fixtures ----------------------------------------------------------
    def _evidence_like(self, name, n=30):
        path = os.path.join(self._tmp, name)
        con = sqlite3.connect(path); con.isolation_level = None
        con.execute("CREATE TABLE annotations(id INTEGER PRIMARY KEY, txt TEXT)")
        con.executemany("INSERT INTO annotations(txt) VALUES(?)",
                        [("a%d" % i,) for i in range(n)])
        con.close()
        return path

    def _make_pkg(self, name, files):
        d = os.path.join(self._pkg_root, name)
        os.makedirs(d, exist_ok=True)
        Path(os.path.join(d, "__init__.py")).write_text("", encoding="utf-8")
        for fn, src in files.items():
            Path(os.path.join(d, fn)).write_text(src, encoding="utf-8")
        importlib.invalidate_caches()   # FileFinder-Cache (siehe Build 319-Fix)
        return importlib.import_module(name)

    def _companion(self, packages=None, backup_dir=True):
        return MigrationCompanion(
            self.mdb, self.ledger,
            backup_dir=(self.backup_dir if backup_dir else None),
            operator="h001", packages=packages)

    # J01 -------------------------------------------------------------------
    def test_j01_preflight_ok(self):
        pkg = self._make_pkg("j01", {"m001_base.py": _GOOD_M001})
        CatalogReconciler(self.mdb, {"evidence": pkg}).sync()
        comp = self._companion(packages={"evidence": pkg})
        pf = comp.preflight(require_backup_dir=True)
        self.assertTrue(pf.ok, pf.blockers)

    # J02 -------------------------------------------------------------------
    def test_j02_gate_catalog_drift(self):
        pkg = self._make_pkg("j02", {"m001_base.py": _GOOD_M001})
        # Katalog NICHT synchronisiert -> uncataloged -> Drift.
        comp = self._companion(packages={"evidence": pkg})
        pf = comp.preflight()
        self.assertFalse(pf.ok)
        self.assertIn("KATALOG_DRIFT", [b.code for b in pf.blockers])

    # J03 -------------------------------------------------------------------
    def test_j03_gate_ledger_chain(self):
        pkg = self._make_pkg("j03", {"m001_base.py": _GOOD_M001})
        CatalogReconciler(self.mdb, {"evidence": pkg}).sync()
        self.ledger.record_start(db_kind="evidence", uid=1, from_version=0,
                                 to_version=1, started_at=100)
        self.ledger.record_result(db_kind="evidence", uid=1, from_version=0,
                                  to_version=1, started_at=100, status="ok")
        # Ledger-Zeile manipulieren -> Kette bricht.
        self.mcon.execute("UPDATE migration_runs SET status='failed' WHERE seq=2")
        comp = self._companion(packages={"evidence": pkg})
        pf = comp.preflight()
        self.assertIn("LEDGER_KETTE", [b.code for b in pf.blockers])

    # J04 -------------------------------------------------------------------
    def test_j04_gate_interrupted(self):
        pkg = self._make_pkg("j04", {"m001_base.py": _GOOD_M001})
        CatalogReconciler(self.mdb, {"evidence": pkg}).sync()
        # 'started' ohne Abschluss -> unterbrochen.
        self.ledger.record_start(db_kind="evidence", uid=7, from_version=0,
                                 to_version=1, started_at=100)
        comp = self._companion(packages={"evidence": pkg})
        pf = comp.preflight()
        self.assertIn("UNTERBROCHENE_LAEUFE", [b.code for b in pf.blockers])

    # J05 -------------------------------------------------------------------
    def test_j05_gate_no_backup_dir(self):
        pkg = self._make_pkg("j05", {"m001_base.py": _GOOD_M001})
        CatalogReconciler(self.mdb, {"evidence": pkg}).sync()
        comp = self._companion(packages={"evidence": pkg}, backup_dir=False)
        pf = comp.preflight(require_backup_dir=True)
        self.assertIn("KEIN_BACKUP_DIR", [b.code for b in pf.blockers])
        # Ohne require_backup_dir kein Blocker deswegen.
        self.assertNotIn("KEIN_BACKUP_DIR",
                         [b.code for b in comp.preflight().blockers])

    # J06 -------------------------------------------------------------------
    def test_j06_execute_needs_confirm(self):
        pkg = self._make_pkg("j06", {"m001_base.py": _GOOD_M001})
        CatalogReconciler(self.mdb, {"evidence": pkg}).sync()
        path = self._evidence_like("evidence_1.db")
        comp = self._companion(packages={"evidence": pkg})
        res = comp.execute([TargetDb("evidence", path, uid=1)], confirm=False)
        self.assertFalse(res.executed)
        self.assertIn("Bestaetigung", res.reason)
        self.assertEqual(self.ledger.list_runs(), [])   # nichts ausgefuehrt

    # J07 -------------------------------------------------------------------
    def test_j07_execute_blocked_by_preflight(self):
        pkg = self._make_pkg("j07", {"m001_base.py": _GOOD_M001})
        # Katalog NICHT synchronisiert -> Drift blockiert trotz confirm=True.
        path = self._evidence_like("evidence_1.db")
        comp = self._companion(packages={"evidence": pkg})
        res = comp.execute([TargetDb("evidence", path, uid=1)], confirm=True)
        self.assertFalse(res.executed)
        self.assertIn("Vorpruefung blockiert", res.reason)

    # J08 -------------------------------------------------------------------
    def test_j08_execute_happy_path(self):
        pkg = self._make_pkg("j08", {"m001_base.py": _GOOD_M001})
        CatalogReconciler(self.mdb, {"evidence": pkg}).sync()
        path = self._evidence_like("evidence_1.db")
        comp = self._companion(packages={"evidence": pkg})
        res = comp.execute([TargetDb("evidence", path, uid=1)], confirm=True,
                           verifier="h002")
        self.assertTrue(res.executed)
        self.assertEqual([r.status for r in res.results], ["ok"])
        self.assertEqual([r["status"] for r in self.ledger.list_runs()],
                         ["started", "ok"])

    # J09 -------------------------------------------------------------------
    def test_j09_execute_flags_failure(self):
        pkg = self._make_pkg("j09", {"m001_base.py": _GOOD_M001,
                                     "m002_loss.py": _BAD_LOSS_M002})
        CatalogReconciler(self.mdb, {"evidence": pkg}).sync()
        path = self._evidence_like("evidence_bad.db")
        comp = self._companion(packages={"evidence": pkg})
        res = comp.execute([TargetDb("evidence", path, uid=1)], confirm=True)
        self.assertTrue(res.executed)
        self.assertEqual(res.results[0].status, "failed_restored")
        self.assertIn("menschliche Pruefung", res.reason)

    # J10 -------------------------------------------------------------------
    def test_j10_summary(self):
        pkg = self._make_pkg("j10", {"m001_base.py": _GOOD_M001})
        CatalogReconciler(self.mdb, {"evidence": pkg}).sync()
        path = self._evidence_like("evidence_1.db")
        comp = self._companion(packages={"evidence": pkg})
        comp.execute([TargetDb("evidence", path, uid=1)], confirm=True)
        summ = comp.summary()
        self.assertTrue(summ.chain_ok)
        self.assertEqual(len(summ.registry), 1)
        self.assertTrue(any("Vieraugen" in r for r in summ.reminders))


if __name__ == "__main__":
    unittest.main()

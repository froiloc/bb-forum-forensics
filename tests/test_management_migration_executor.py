# =============================================================================
# tests/test_management_migration_executor.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 319: Baseline-m001 je Beweis-DB-Art + FleetExecutor.
# VOLLSTAENDIG automatisiert, NUR synthetische evidenz-/assets-/forensic-
# foermige DBs — KEIN reales Beweismaterial (Bauplan Build 319 §5).
#
# I01 — Baseline m001 (evidence): stempelt v1, schema_migrations entsteht,
#       keine Datenaenderung; zweiter Lauf idempotent
#       BUILD 532: Die evidence-Kette hat jetzt ZWEI Migrationen (m001 Baseline,
#       m002 annotation_tatzeit). Die Erwartungen sind entsprechend auf [1, 2]
#       bzw. Version 2 angehoben. Dass dieser Test beim Hinzufuegen von m002
#       fehlgeschlagen ist, ist die gewollte Wirkung eines Ankers — er haelt die
#       Kettenlaenge fest, damit eine neue Migration nicht unbemerkt mitlaeuft.
# I02 — Baseline-Guard: leere DB (keine Fachtabelle) -> Abbruch, kein Stempel
# I03 — Katalog deckt evidence/forensic/assets nach sync ab; reconcile ohne Drift
# I04 — Executor happy path: evidence v0->v2 (seit Build 532; vorher v0->v1);
#       Ledger started+ok; db_registry aktualisiert; Instanz integer; Backup
#       erzeugt
# I05 — dry_run: nichts passiert (kein Backup, kein Ledger, Quelle bit-identisch)
# I06 — Backup-Pflicht: dry_run=False ohne backup_dir -> ValueError
# I07 — Verify-Fehler -> Restore: Bad-Migration (loescht Zeilen) erkannt; Instanz
#       zurueckgesetzt (Daten + Version wie vorher); Ledger failed+restored
# I08 — Ausnahme in up() -> Restore + Ledger failed+restored
# I09 — Isolation: Fehler bei Instanz A laesst Instanz B (ok) unberuehrt
# I10 — Ledger-Kette nach allen Laeufen verify_chain() == ok
#
# Version: v0.7.319 · Build: 319 · 2026-07-03
# =============================================================================

import importlib
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.evidence as evidence_pkg
from management.migration_fleet.catalog import CatalogReconciler
from management.migration_fleet.executor import FleetExecutor
from management.migration_fleet.harness.hashing import sha512_file
from management.migration_fleet.harness.rowcount import RowcountVerifier
from management.migration_fleet.ledger import MigrationLedger
from management.migration_fleet.migration_db import MigrationDb
from management.migration_fleet.planner import TargetDb, read_instance_version
from management.migrations.runner import MigrationRunner, discover

_BAD_LOSS_M002 = '''
VERSION = 2
NAME = "bad-loss (loescht Daten)"
KIND = "additive"
def up(con):
    con.execute("DELETE FROM annotations")
'''

_RAISE_M002 = '''
VERSION = 2
NAME = "bad-raise"
KIND = "additive"
def up(con):
    con.execute("DELETE FROM annotations")
    raise RuntimeError("kaputt")
'''

_GOOD_M001 = '''
VERSION = 1
NAME = "baseline test"
KIND = "additive"
def up(con):
    pass
'''


class MigrationExecutorTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._pkg_root = os.path.join(self._tmp, "pkgs")
        os.makedirs(self._pkg_root, exist_ok=True)
        sys.path.insert(0, self._pkg_root)
        # migration.db (Betriebs-DB) + Ledger
        self.mdb_path = os.path.join(self._tmp, "migration.db")
        self.mcon = sqlite3.connect(self.mdb_path)
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
    def _evidence_like(self, name, n=50):
        path = os.path.join(self._tmp, name)
        con = sqlite3.connect(path)
        con.isolation_level = None
        con.execute("CREATE TABLE annotations(id INTEGER PRIMARY KEY, txt TEXT)")
        con.execute("CREATE TABLE reports(id INTEGER PRIMARY KEY, title TEXT)")
        con.executemany("INSERT INTO annotations(txt) VALUES(?)",
                        [("a%d" % i,) for i in range(n)])
        con.close()
        return path

    def _make_pkg(self, name, files):
        """
        Erzeugt ein echtes temporaeres Migrationspaket und importiert es.

        WICHTIG: importlib.invalidate_caches() VOR dem Import. Pythons
        FileFinder cached Verzeichnislisten und liest nur bei geaenderter
        Verzeichnis-mtime neu ein. Werden (wie in I09) zwei Pakete im selben
        Verzeichnis erzeugt, findet der zweite Import das neue Paket sonst
        nicht, wenn die mtime im selben Takt bleibt (grobe mtime-Aufloesung
        z. B. unter Python 3.14 / in der Windows-Cloud-VM). invalidate_caches()
        erzwingt das Neueinlesen. Beleg: reproduziert mit kuenstlich
        zurueckgesetzter Verzeichnis-mtime (Build 319, Regressionskorrektur).
        """
        d = os.path.join(self._pkg_root, name)
        os.makedirs(d, exist_ok=True)
        Path(os.path.join(d, "__init__.py")).write_text("", encoding="utf-8")
        for fn, src in files.items():
            Path(os.path.join(d, fn)).write_text(src, encoding="utf-8")
        importlib.invalidate_caches()
        return importlib.import_module(name)

    # I01 -------------------------------------------------------------------
    def test_i01_baseline_stamps_v1(self):
        path = self._evidence_like("evidence_18.db")
        before = RowcountVerifier.table_rowcounts(path)
        con = sqlite3.connect(path); con.isolation_level = None
        applied = MigrationRunner(con, discover(evidence_pkg), audit=None,
                                  deployed_by="t").run()
        con.close()
        # Build 532: m001 (Baseline) UND m002 (annotation_tatzeit).
        self.assertEqual(applied, [1, 2])
        self.assertEqual(read_instance_version(path), 2)
        # schema_migrations existiert, Fachdaten unveraendert.
        self.assertEqual(RowcountVerifier.table_rowcounts(path)["annotations"],
                         before["annotations"])
        # Idempotenz: zweiter Lauf = nichts.
        con = sqlite3.connect(path); con.isolation_level = None
        again = MigrationRunner(con, discover(evidence_pkg), audit=None,
                                deployed_by="t").run()
        con.close()
        self.assertEqual(again, [])

    # I02 -------------------------------------------------------------------
    def test_i02_baseline_guard_empty_db(self):
        path = os.path.join(self._tmp, "empty.db")
        sqlite3.connect(path).close()  # keine Fachtabelle
        con = sqlite3.connect(path); con.isolation_level = None
        with self.assertRaises(Exception):
            MigrationRunner(con, discover(evidence_pkg), audit=None,
                            deployed_by="t").run()
        con.close()
        # Baseline wurde NICHT gestempelt.
        self.assertEqual(read_instance_version(path), 0)

    # I03 -------------------------------------------------------------------
    def test_i03_catalog_covers_evidence_kinds(self):
        rec = CatalogReconciler(self.mdb)
        rec.sync()
        kinds = {e.db_kind for e in self.mdb.list_catalog()}
        self.assertTrue({"evidence", "forensic", "assets"} <= kinds)
        self.assertFalse(rec.reconcile().has_drift)

    # I04 -------------------------------------------------------------------
    def test_i04_executor_happy_path(self):
        CatalogReconciler(self.mdb).sync()
        path = self._evidence_like("evidence_18.db")
        ex = FleetExecutor(self.mdb, self.ledger, backup_dir=self.backup_dir,
                           operator="h001")
        res = ex.execute_instance(TargetDb("evidence", path, uid=18),
                                  dry_run=False, verifier="h002")
        self.assertEqual(res.status, "ok")
        # Build 532: die evidence-Kette endet bei Version 2.
        self.assertEqual((res.from_version, res.to_version), (0, 2))
        self.assertEqual(read_instance_version(path), 2)
        # Ledger: started + ok
        runs = self.ledger.list_runs(db_kind="evidence", uid=18)
        self.assertEqual([r["status"] for r in runs], ["started", "ok"])
        # db_registry aktualisiert
        reg = self.mdb.list_registry("evidence")
        self.assertEqual(reg[0].current_version, 2)
        self.assertEqual(reg[0].last_status, "ok")
        # Backup existiert
        self.assertTrue(os.path.exists(res.backup_path))

    # I05 -------------------------------------------------------------------
    def test_i05_dry_run_changes_nothing(self):
        CatalogReconciler(self.mdb).sync()
        path = self._evidence_like("evidence_18.db")
        before = sha512_file(path)
        ex = FleetExecutor(self.mdb, self.ledger, backup_dir=self.backup_dir)
        res = ex.execute_instance(TargetDb("evidence", path, uid=18),
                                  dry_run=True)
        self.assertEqual(res.status, "planned")
        self.assertEqual(sha512_file(path), before)          # Quelle unveraendert
        self.assertEqual(self.ledger.list_runs(), [])         # kein Ledger-Eintrag
        self.assertFalse(os.path.isdir(self.backup_dir))      # kein Backup
        self.assertEqual(read_instance_version(path), 0)

    # I06 -------------------------------------------------------------------
    def test_i06_backup_mandatory(self):
        CatalogReconciler(self.mdb).sync()
        path = self._evidence_like("evidence_18.db")
        ex = FleetExecutor(self.mdb, self.ledger, backup_dir=None)  # kein Backup-Dir
        with self.assertRaises(ValueError):
            ex.execute_instance(TargetDb("evidence", path, uid=18), dry_run=False)

    # I07 -------------------------------------------------------------------
    def test_i07_verify_failure_restores(self):
        path = self._evidence_like("evidence_bad.db", n=50)
        before_counts = RowcountVerifier.table_rowcounts(path)
        pkg = self._make_pkg("badloss_pkg",
                             {"m001_base.py": _GOOD_M001,
                              "m002_loss.py": _BAD_LOSS_M002})
        ex = FleetExecutor(self.mdb, self.ledger, backup_dir=self.backup_dir,
                           operator="h001", packages={"evidence": pkg})
        res = ex.execute_instance(TargetDb("evidence", path, uid=18),
                                  dry_run=False)
        self.assertEqual(res.status, "failed_restored")
        # Instanz wiederhergestellt: Daten + Version wie vorher (v0).
        self.assertEqual(RowcountVerifier.table_rowcounts(path)["annotations"],
                         before_counts["annotations"])
        self.assertEqual(read_instance_version(path), 0)
        # Ledger: started, failed, restored
        self.assertEqual([r["status"] for r in self.ledger.list_runs()],
                         ["started", "failed", "restored"])

    # I08 -------------------------------------------------------------------
    def test_i08_exception_restores(self):
        path = self._evidence_like("evidence_raise.db", n=30)
        before = RowcountVerifier.table_rowcounts(path)["annotations"]
        pkg = self._make_pkg("raise_pkg",
                             {"m001_base.py": _GOOD_M001,
                              "m002_raise.py": _RAISE_M002})
        ex = FleetExecutor(self.mdb, self.ledger, backup_dir=self.backup_dir,
                           packages={"evidence": pkg})
        res = ex.execute_instance(TargetDb("evidence", path, uid=18),
                                  dry_run=False)
        self.assertEqual(res.status, "failed_restored")
        self.assertEqual(RowcountVerifier.table_rowcounts(path)["annotations"],
                         before)
        self.assertEqual(read_instance_version(path), 0)

    # I09 -------------------------------------------------------------------
    def test_i09_isolation(self):
        good = self._evidence_like("evidence_good.db", n=20)
        bad = self._evidence_like("evidence_bad.db", n=20)
        good_pkg = self._make_pkg("iso_good", {"m001_base.py": _GOOD_M001})
        bad_pkg = self._make_pkg("iso_bad",
                                 {"m001_base.py": _GOOD_M001,
                                  "m002_loss.py": _BAD_LOSS_M002})
        # Zwei Executoren mit je eigenem Paket, aber gemeinsamem Ledger.
        ex_bad = FleetExecutor(self.mdb, self.ledger, backup_dir=self.backup_dir,
                               packages={"evidence": bad_pkg})
        ex_good = FleetExecutor(self.mdb, self.ledger, backup_dir=self.backup_dir,
                                packages={"evidence": good_pkg})
        r_bad = ex_bad.execute_instance(TargetDb("evidence", bad, uid=1), dry_run=False)
        r_good = ex_good.execute_instance(TargetDb("evidence", good, uid=2), dry_run=False)
        self.assertEqual(r_bad.status, "failed_restored")
        self.assertEqual(r_good.status, "ok")              # B unberuehrt vom Fehler bei A
        self.assertEqual(read_instance_version(good), 1)
        self.assertEqual(read_instance_version(bad), 0)

    # I10 -------------------------------------------------------------------
    def test_i10_ledger_chain_intact(self):
        CatalogReconciler(self.mdb).sync()
        for uid in (18, 19):
            path = self._evidence_like("evidence_%d.db" % uid)
            FleetExecutor(self.mdb, self.ledger, backup_dir=self.backup_dir).\
                execute_instance(TargetDb("evidence", path, uid=uid), dry_run=False)
        self.assertTrue(self.ledger.verify_chain().ok)


if __name__ == "__main__":
    unittest.main()

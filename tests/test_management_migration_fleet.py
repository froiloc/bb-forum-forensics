# =============================================================================
# tests/test_management_migration_fleet.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 316: migration.db-Schema, Katalog/Code-Abgleich,
# Dry-Run-Planner. VOLLSTAENDIG automatisiert — kein Browser, keine Beweis-DB.
#
# F01 — MigrationDb.ensure_schema legt catalog/registry/runs (+Index) an; idempotent
# F02 — catalog-sync (coordinator) fuellt M001..M004 mit korrekter Pruefsumme
#       (== MigrationRunner._module_checksum), kind, geordnet
# F03 — reconcile: kein Drift, wenn Katalog == Code (alle OK)
# F04 — reconcile: MODIFIED, wenn eine Katalog-Pruefsumme abweicht
# F05 — reconcile: UNCATALOGED (Code ohne Katalog) und MISSING_MODULE (Katalog
#       ohne Modul)
# F06 — planner: Instanz auf v0 -> alle Katalog-Migrationen ausstehend, geordnet
# F07 — planner: Instanz auf v2 -> nur v3, v4 ausstehend
# F08 — planner: Instanz auf Hoechstversion -> nichts ausstehend (up_to_date)
# F09 — planner: db_kind ohne Katalog -> leerer Plan mit Hinweis (note)
# F10 — planner: fehlende schema_migrations-Tabelle -> Instanz gilt als v0
# F11 — DRY-RUN: plan() veraendert die Ziel-Instanz NICHT (Schema/Registry
#       identisch vorher==nachher) und schreibt NICHT in migration_runs
# F12 — db_registry: Upsert/Read-Roundtrip inkl. uid=NULL ohne Duplikat
#
# Version: v0.7.316 · Build: 316 · 2026-07-03
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
from management.migration_fleet.catalog import CatalogReconciler, DB_KIND_PACKAGES
from management.migration_fleet.migration_db import (
    CatalogEntry,
    MigrationDb,
    RegistryEntry,
)
from management.migration_fleet.planner import (
    MigrationPlanner,
    TargetDb,
    read_instance_version,
)
from management.migrations.runner import MigrationRunner, discover

_INVESTIGATORS = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0,
    is_support INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
)
"""

_OLD_SCRAPE_JOBS = """
CREATE TABLE scrape_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
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


class MigrationFleetTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        # --- migration.db (Betriebs-DB) ---
        self.mdb_path = os.path.join(self._tmp, "migration.db")
        self.mcon = sqlite3.connect(self.mdb_path)
        self.mcon.isolation_level = None
        self.mcon.row_factory = sqlite3.Row
        self.mdb = MigrationDb(self.mcon)
        self.mdb.ensure_schema()
        self.reconciler = CatalogReconciler(self.mdb)
        self.planner = MigrationPlanner(self.mdb)

        # Anzahl der im Code vorhandenen coordinator-Migrationen (M001..Mn).
        self.coord_mods = discover(coordinator_migrations)
        self.coord_versions = [m.VERSION for m in self.coord_mods]
        # Gesamtzahl der Katalogeintraege ueber ALLE db_kinds (seit Build
        # 319 auch evidence/forensic/assets-Baselines).
        self.total_catalog = sum(
            len(discover(pkg)) for pkg in DB_KIND_PACKAGES.values())

    def tearDown(self):
        try:
            self.mcon.close()
        finally:
            for fn in os.listdir(self._tmp):
                try:
                    os.remove(os.path.join(self._tmp, fn))
                except OSError:
                    pass
            os.rmdir(self._tmp)

    # Helfer: eine coordinator-Instanz bis Zielversion migrieren -----------
    def _make_coordinator_at(self, target_version):
        """
        Legt eine coordinator.db an und wendet M001.. bis target_version an
        (0 = gar keine Migration, dann existiert schema_migrations nicht).
        Gibt den Pfad zurueck.
        """
        path = os.path.join(self._tmp, "coordinator_%d.db" % target_version)
        con = sqlite3.connect(path)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        if target_version > 0:
            now = int(time.time())
            con.execute(_INVESTIGATORS)
            con.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "created_at) VALUES (1, 'h001', 'Alpha', ?)", (now,))
            con.execute(_OLD_SCRAPE_JOBS)
            audit = AuditLog(con)
            subset = [m for m in self.coord_mods if m.VERSION <= target_version]
            MigrationRunner(con, subset, audit=audit, deployed_by="t").run()
        con.close()
        return path

    # F01 --------------------------------------------------------------------
    def test_f01_ensure_schema_idempotent(self):
        names = {r[0] for r in self.mcon.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("migration_catalog", "db_registry", "migration_runs"):
            self.assertIn(t, names)
        idx = {r[0] for r in self.mcon.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertIn("db_registry_key", idx)
        # Zweiter Aufruf: kein Fehler, keine Duplikate.
        self.mdb.ensure_schema()

    # F02 --------------------------------------------------------------------
    def test_f02_catalog_sync_coordinator(self):
        n = self.reconciler.sync()
        # Seit Build 319 deckt der Katalog auch die Beweis-DB-Arten ab.
        self.assertEqual(n, self.total_catalog)
        self.assertGreaterEqual(n, len(self.coord_versions))
        cat = self.mdb.list_catalog("coordinator")
        self.assertEqual([e.version for e in cat], sorted(self.coord_versions))
        # Pruefsumme muss identisch zu MigrationRunner._module_checksum sein.
        by_v = {m.VERSION: m for m in self.coord_mods}
        for e in cat:
            self.assertEqual(
                e.checksum,
                MigrationRunner._module_checksum(by_v[e.version]))
            self.assertIn(e.kind, ("additive", "destructive"))

    # F03 --------------------------------------------------------------------
    def test_f03_reconcile_no_drift(self):
        self.reconciler.sync()
        report = self.reconciler.reconcile()
        self.assertFalse(report.has_drift)
        self.assertEqual(len(report.ok), self.total_catalog)

    # F04 --------------------------------------------------------------------
    def test_f04_reconcile_modified(self):
        self.reconciler.sync()
        v = self.coord_versions[0]
        # Katalog-Pruefsumme manipulieren -> Drift MODIFIED.
        self.mcon.execute(
            "UPDATE migration_catalog SET checksum='DEADBEEF' "
            "WHERE db_kind='coordinator' AND version=?", (v,))
        report = self.reconciler.reconcile()
        self.assertIn("coordinator:%d" % v, report.modified)
        self.assertTrue(report.has_drift)

    # F05 --------------------------------------------------------------------
    def test_f05_reconcile_uncataloged_and_missing(self):
        self.reconciler.sync()
        # UNCATALOGED: einen Code-Eintrag aus dem Katalog loeschen.
        v_missing_in_cat = self.coord_versions[-1]
        self.mcon.execute(
            "DELETE FROM migration_catalog WHERE db_kind='coordinator' AND version=?",
            (v_missing_in_cat,))
        # MISSING_MODULE: einen Katalogeintrag ohne Code-Modul einfuegen.
        phantom = max(self.coord_versions) + 99
        self.mdb.upsert_catalog_entry(CatalogEntry(
            db_kind="coordinator", version=phantom, name="phantom",
            checksum="X", kind="additive", requires_backup=0, depends_on=None))
        report = self.reconciler.reconcile()
        self.assertIn("coordinator:%d" % v_missing_in_cat, report.uncataloged)
        self.assertIn("coordinator:%d" % phantom, report.missing_module)

    # F06 --------------------------------------------------------------------
    def test_f06_plan_from_zero(self):
        self.reconciler.sync()
        path = self._make_coordinator_at(0)
        plan = self.planner.plan_instance(TargetDb("coordinator", path))
        self.assertEqual(plan.current_version, 0)
        self.assertEqual([e.version for e in plan.pending],
                         sorted(self.coord_versions))
        self.assertFalse(plan.up_to_date)

    # F07 --------------------------------------------------------------------
    def test_f07_plan_partial(self):
        self.reconciler.sync()
        # Instanz auf die zweitniedrigste vorhandene Version bringen.
        v2 = sorted(self.coord_versions)[1]
        path = self._make_coordinator_at(v2)
        plan = self.planner.plan_instance(TargetDb("coordinator", path))
        self.assertEqual(plan.current_version, v2)
        expected = [v for v in sorted(self.coord_versions) if v > v2]
        self.assertEqual([e.version for e in plan.pending], expected)

    # F08 --------------------------------------------------------------------
    def test_f08_plan_up_to_date(self):
        self.reconciler.sync()
        vmax = max(self.coord_versions)
        path = self._make_coordinator_at(vmax)
        plan = self.planner.plan_instance(TargetDb("coordinator", path))
        self.assertEqual(plan.current_version, vmax)
        self.assertTrue(plan.up_to_date)
        self.assertEqual(plan.pending, [])

    # F09 --------------------------------------------------------------------
    def test_f09_plan_db_kind_without_catalog(self):
        self.reconciler.sync()
        # Eine db_kind OHNE Migrationspaket (seit Build 319 haben
        # evidence/forensic/assets welche) -> Katalog leer, Hinweis-note.
        path = self._make_coordinator_at(0)  # Datei existiert, Art egal
        plan = self.planner.plan_instance(TargetDb("nichtexistent", path, uid=42))
        self.assertEqual(plan.pending, [])
        self.assertIsNotNone(plan.note)
        self.assertIn("nichtexistent", plan.note)

    # F10 --------------------------------------------------------------------
    def test_f10_missing_schema_migrations_is_v0(self):
        # Frische DB ohne schema_migrations.
        path = os.path.join(self._tmp, "fresh.db")
        sqlite3.connect(path).close()
        self.assertEqual(read_instance_version(path), 0)

    # F11 --------------------------------------------------------------------
    def test_f11_dry_run_changes_nothing(self):
        self.reconciler.sync()
        vmax = max(self.coord_versions)
        path = self._make_coordinator_at(vmax)

        def _snapshot(p):
            con = sqlite3.connect(p)
            try:
                schema = con.execute(
                    "SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
                sm = con.execute(
                    "SELECT version, checksum FROM schema_migrations "
                    "ORDER BY version").fetchall()
                return (schema, sm)
            finally:
                con.close()

        before = _snapshot(path)
        runs_before = len(self.mdb.list_runs())
        _ = self.planner.plan([TargetDb("coordinator", path),
                               TargetDb("coordinator", self._make_coordinator_at(0))])
        after = _snapshot(path)
        self.assertEqual(before, after, "Dry-Run darf die Instanz nicht aendern")
        # Planner schreibt NICHT ins Ledger.
        self.assertEqual(len(self.mdb.list_runs()), runs_before)
        self.assertEqual(runs_before, 0)

    # F12 --------------------------------------------------------------------
    def test_f12_registry_upsert_null_uid(self):
        # coordinator: uid=NULL, zweifacher Upsert -> genau EIN Eintrag.
        self.mdb.upsert_registry_entry(RegistryEntry(
            "coordinator", None, "/data/coordinator.db", 4, None, "ok"))
        self.mdb.upsert_registry_entry(RegistryEntry(
            "coordinator", None, "/data/coordinator.db", 4,
            int(time.time()), "ok"))
        coord = self.mdb.list_registry("coordinator")
        self.assertEqual(len(coord), 1)
        # nutzerbezogen: zwei uids -> zwei Eintraege.
        self.mdb.upsert_registry_entry(RegistryEntry(
            "evidence", 18, "/data/evidence_18.db", 0, None, "pending"))
        self.mdb.upsert_registry_entry(RegistryEntry(
            "evidence", 19, "/data/evidence_19.db", 0, None, "pending"))
        self.assertEqual(len(self.mdb.list_registry("evidence")), 2)


if __name__ == "__main__":
    unittest.main()

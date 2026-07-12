# =============================================================================
# tests/test_migration_status.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 376: Migrationsstand-Pruefung beim Serverstart.
#
# ANLASS: m009 war ausgeliefert, aber in der produktiven coordinator.db nie
# angewandt (Migrationen laufen ueber 'python -m management.migrate', NICHT beim
# Serverstart). Folge: der Berichts-Scan-Cache fiel aus und meldete das nur
# beilaeufig je Fall im Log. Der Server soll das nun beim Start DEUTLICH sagen.
#
# MS01 — Vollstaendig migrierte DB -> ok, keine Warnung.
# MS02 — Fehlende Migration -> pending, Warnung nennt die Migration UND den
#        exakten Befehl.
# MS03 — Fehlende Registry (uninitialisierte DB) -> missing_registry + Warnung.
# MS04 — ManagementApp.migration_status() liefert den Stand.
# MS05 — Fehlender Scan-Cache: /api/reports meldet 'cache_error' SICHTBAR
#        (statt nur zu loggen) und liefert die Berichte trotzdem vollstaendig.
#
# Version: v0.7.376 · Build: 376 · 2026-07-10
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
from management.migrations.runner import MigrationRunner, discover
from management.gateway.coordinator_writer import CoordinatorWriter
from management.rbac.rbac_repo import RbacRepo
from management.cases.cases_repo import CasesRepo
from management.server.management_app import ManagementApp
from management.server.migration_status import (
    MIGRATE_COMMAND,
    MigrationStatus,
    MigrationStatusCheck,
)

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

_EVIDENCE_REPORTS = """
CREATE TABLE "reports" (
    "id" INTEGER,
    "report_type" TEXT NOT NULL CHECK("report_type" IN ('interim','final','addendum')),
    "sequence_nr" INTEGER NOT NULL DEFAULT 1,
    "title" TEXT NOT NULL,
    "created_by" TEXT NOT NULL,
    "created_at" INTEGER NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'draft'
        CHECK("status" IN ('draft','submitted','approved','final')),
    PRIMARY KEY("id" AUTOINCREMENT)
)
"""


class MigrationStatusTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        self._ev = os.path.join(self._tmp, "evidence")
        os.makedirs(self._ev)

        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        for pid, un, disp, sup in ((1, "h0a2898", "Chefin", 1),
                                   (2, "h002", "Mueller", 0)):
            con.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?, ?, ?, 1, ?, 0, ?)", (pid, un, disp, sup,
                                                 int(time.time())))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.con = con

    def tearDown(self):
        try:
            self.con.close()
        except Exception:
            pass
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    # MS01 -------------------------------------------------------------------
    def test_ms01_up_to_date(self):
        st = MigrationStatusCheck(self.con).status()
        self.assertTrue(st.ok)
        self.assertEqual(st.pending, [])
        self.assertFalse(st.missing_registry)
        self.assertEqual(MigrationStatusCheck.warning_lines(st), [])

    # MS02 -------------------------------------------------------------------
    def test_ms02_pending_warning_names_command(self):
        # Genau den Produktionsfall nachstellen: m009 fehlt in der Registry.
        self.con.execute("DELETE FROM schema_migrations WHERE version=9")
        st = MigrationStatusCheck(self.con).status()
        self.assertFalse(st.ok)
        self.assertIn(9, st.pending)

        text = "\n".join(MigrationStatusCheck.warning_lines(st))
        self.assertIn("m009", text)
        self.assertIn("python -m management.migrate", text)
        self.assertIn("ACHTUNG", text)
        # Der Server darf NICHT selbst migrieren -> das muss dastehen.
        self.assertIn("migriert BEWUSST NICHT selbst", text)

    # MS03 -------------------------------------------------------------------
    def test_ms03_missing_registry(self):
        st = MigrationStatus(applied=[], available=[1, 2, 3])
        self.assertTrue(st.missing_registry)
        text = "\n".join(MigrationStatusCheck.warning_lines(st))
        self.assertIn("nicht initialisiert", text)
        self.assertIn(MIGRATE_COMMAND.split()[0], text)  # 'python'

    # MS04 -------------------------------------------------------------------
    def test_ms04_app_exposes_status(self):
        app = ManagementApp(self._db, evidence_dir=self._ev)
        st = app.migration_status()
        self.assertTrue(st.ok)
        self.assertIn(9, st.applied)

    # MS05 -------------------------------------------------------------------
    def test_ms05_missing_cache_table_visible_in_view(self):
        """
        Produktionsfall: Migration m009 fehlt -> evidence_scan_cache existiert
        nicht. Der Scan muss trotzdem VOLLSTAENDIG liefern (der Cache ist nur
        ein Beschleuniger) UND den Zustand SICHTBAR melden (cache_error) —
        statt je Fall eine beilaeufige Logzeile zu erzeugen.
        """
        # Berichte anlegen und die Cache-Tabelle entfernen.
        writer = CoordinatorWriter(self.con, AuditLog(self.con))
        rbac = RbacRepo(self.con, writer)
        cases = CasesRepo(self.con, writer)
        rbac.grant("supervisor", "reports.review", scope="alle", actor_id=1)
        rbac.assign_role(1, "supervisor", actor_id=1)
        cases.create_case(18, "b18", actor_id=1)

        ev = os.path.join(self._ev, "evidence_18.db")
        c = sqlite3.connect(ev)
        c.isolation_level = None
        c.execute("PRAGMA journal_mode=WAL")
        c.execute(_EVIDENCE_REPORTS)
        c.execute('INSERT INTO reports (id, report_type, sequence_nr, title, '
                  'created_by, created_at, status) '
                  "VALUES (1,'interim',1,'Bericht','h002',1783000000,"
                  "'submitted')")
        c.close()

        self.con.execute("DROP TABLE evidence_scan_cache")
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        app = ManagementApp(self._db, evidence_dir=self._ev)
        r = app.dispatch(1, "/api/reports")
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        # Vollstaendig trotz fehlendem Cache ...
        self.assertEqual(d["count"], 1)
        # ... und der Zustand ist SICHTBAR.
        self.assertIsNotNone(d["cache_error"])
        self.assertIn("evidence_scan_cache", d["cache_error"])


if __name__ == "__main__":
    unittest.main()

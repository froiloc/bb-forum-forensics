# =============================================================================
# tests/test_management_rbac_resolver.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 345: RbacResolver (rein lesend) + verify_catalog_present.
#
# S01 — resolve() ohne Rolle -> leere Policy (default-deny); can()=False,
#       scope_for()=None.
# S02 — eine Rolle mit Grants -> Faehigkeiten aufgeloest; can()=True; Scope korrekt.
# S03 — Scope-Widening: dieselbe Faehigkeit ueber zwei Rollen mit eigene+alle
#       -> alle. Und None < eigene.
# S04 — zurueckgenommener Grant / zurueckgenommene Rolle fliessen NICHT ein.
# S05 — Mehrfachrollen: Vereinigung der Faehigkeiten.
# S06 — unbekannte/ungegrantete Faehigkeit -> can()=False, scope_for()=None.
# S07 — verify_catalog_present gruen nach Migration (voller Seed vorhanden).
# S08 — fehlt eine Faehigkeit in der DB -> RbacCatalogError (handlungsleitend).
# S09 — fehlt eine Rolle in der DB -> RbacCatalogError.
# S10 — DB voraus (Extra-Capability in DB, nicht im Code) -> KEIN Fehler.
# S11 — Read-Only-Nachweis: resolve() aendert keine Zeilenzahlen, kein Audit.
#
# Version: v0.7.345 · Build: 345 · 2026-07-10
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
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.rbac import catalog
from management.rbac.rbac_repo import RbacRepo
from management.rbac.rbac_resolver import (
    PersonPolicy,
    RbacCatalogError,
    RbacResolver,
    verify_catalog_present,
)

_PERSON = """
CREATE TABLE person (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    system_username TEXT    NOT NULL UNIQUE,
    display_name    TEXT    NOT NULL,
    is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor   INTEGER NOT NULL DEFAULT 0,
    is_support      INTEGER NOT NULL DEFAULT 0,
    created_at      INTEGER NOT NULL
)
"""

_OLD_SCRAPE_JOBS = """
CREATE TABLE scrape_jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    username      TEXT    NOT NULL,
    priority      INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status        TEXT    NOT NULL DEFAULT 'pending'
                  CHECK(status IN ('pending','running','done','failed')),
    manifest_path TEXT,
    output_path   TEXT,
    worker_id     TEXT,
    created_at    INTEGER NOT NULL,
    started_at    INTEGER,
    finished_at   INTEGER,
    error_message TEXT,
    assigned_to   INTEGER,
    note          TEXT,
    FOREIGN KEY(assigned_to) REFERENCES person(id)
)
"""


class ManagementRbacResolverTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")

        now = int(time.time())
        self.con.execute(_PERSON)
        self.con.executemany(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(1, "h001", "Alpha", 1, 1, 0, now),
             (2, "h002", "Beta", 1, 0, 0, now)],
        )
        self.con.execute(_OLD_SCRAPE_JOBS)

        self.audit = AuditLog(self.con)
        self.mods = discover(coordinator_migrations)
        MigrationRunner(self.con, self.mods, audit=self.audit,
                        deployed_by="tester").run()

        self.writer = CoordinatorWriter(self.con, self.audit)
        self.repo = RbacRepo(self.con, self.writer)
        self.resolver = RbacResolver(self.con)

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

    # S01 --------------------------------------------------------------------
    def test_s01_no_role_default_deny(self):
        pol = self.resolver.resolve(2)
        self.assertIsInstance(pol, PersonPolicy)
        self.assertEqual(pol.roles, frozenset())
        self.assertEqual(pol.capabilities, {})
        self.assertFalse(pol.can("dashboard.view"))
        self.assertIsNone(pol.scope("dashboard.view"))
        self.assertFalse(self.resolver.can(2, "dashboard.view"))

    # S02 --------------------------------------------------------------------
    def test_s02_single_role_grants(self):
        self.repo.grant("supervisor", "dashboard.view", scope="alle", actor_id=1)
        self.repo.grant("supervisor", "reports.approve", actor_id=1)  # scope None
        self.repo.assign_role(2, "supervisor", actor_id=1)
        pol = self.resolver.resolve(2)
        self.assertEqual(pol.roles, frozenset({"supervisor"}))
        self.assertTrue(pol.can("dashboard.view"))
        self.assertEqual(pol.scope("dashboard.view"), "alle")
        self.assertTrue(pol.can("reports.approve"))
        self.assertIsNone(pol.scope("reports.approve"))  # ohne Scope

    # S03 --------------------------------------------------------------------
    def test_s03_scope_widening(self):
        # investigator: mycases.view(eigene); supervisor: mycases.view(alle)
        self.repo.grant("investigator", "mycases.view", scope="eigene",
                        actor_id=1)
        self.repo.grant("supervisor", "mycases.view", scope="alle", actor_id=1)
        self.repo.assign_role(2, "investigator", actor_id=1)
        self.repo.assign_role(2, "supervisor", actor_id=1)
        self.assertEqual(self.resolver.scope_for(2, "mycases.view"), "alle")

        # None < eigene: support mit myhistory.view(None) + investigator
        # myhistory.view(eigene) -> eigene gewinnt.
        self.repo.grant("support", "myhistory.view", actor_id=1)  # None
        self.repo.grant("investigator", "myhistory.view", scope="eigene",
                        actor_id=1)
        self.repo.assign_role(1, "support", actor_id=1)
        self.repo.assign_role(1, "investigator", actor_id=1)
        self.assertEqual(self.resolver.scope_for(1, "myhistory.view"), "eigene")

    # S04 --------------------------------------------------------------------
    def test_s04_revoked_excluded(self):
        # Grant, dann Grant zuruecknehmen -> faellt aus der Aufloesung.
        self.repo.grant("lector", "reports.review", scope="alle", actor_id=1)
        gid = self.con.execute(
            "SELECT id FROM rbac_grant WHERE role_code='lector'").fetchone()[0]
        self.repo.assign_role(2, "lector", actor_id=1)
        self.assertTrue(self.resolver.can(2, "reports.review"))
        self.repo.revoke_grant(gid, actor_id=1)
        self.assertFalse(self.resolver.can(2, "reports.review"))

        # Rolle zuruecknehmen -> deren Faehigkeiten fallen weg.
        self.repo.grant("admin", "feedback.moderate", scope="alle", actor_id=1)
        self.repo.assign_role(2, "admin", actor_id=1)
        prid = self.con.execute(
            "SELECT id FROM person_role WHERE person_id=2 AND role_code='admin'"
        ).fetchone()[0]
        self.assertTrue(self.resolver.can(2, "feedback.moderate"))
        self.repo.revoke_role(prid, actor_id=1)
        self.assertFalse(self.resolver.can(2, "feedback.moderate"))

    # S05 --------------------------------------------------------------------
    def test_s05_multi_role_union(self):
        self.repo.grant("lector", "reports.review", scope="alle", actor_id=1)
        self.repo.grant("searchagent", "evidence.fulltext_search", scope="alle",
                        actor_id=1)
        self.repo.assign_role(1, "lector", actor_id=1)
        self.repo.assign_role(1, "searchagent", actor_id=1)
        pol = self.resolver.resolve(1)
        self.assertEqual(pol.roles, frozenset({"lector", "searchagent"}))
        self.assertTrue(pol.can("reports.review"))
        self.assertTrue(pol.can("evidence.fulltext_search"))

    # S06 --------------------------------------------------------------------
    def test_s06_ungranted_capability(self):
        self.repo.grant("investigator", "mycases.view", scope="eigene",
                        actor_id=1)
        self.repo.assign_role(2, "investigator", actor_id=1)
        pol = self.resolver.resolve(2)
        self.assertFalse(pol.can("reports.approve"))
        self.assertIsNone(pol.scope("reports.approve"))

    # S07 --------------------------------------------------------------------
    def test_s07_catalog_present_ok(self):
        # Nach vollstaendigem Migrationslauf ist der Seed vollstaendig.
        verify_catalog_present(self.con)  # wirft nicht

    # S08 --------------------------------------------------------------------
    def test_s08_missing_capability_raises(self):
        self.con.execute(
            "DELETE FROM rbac_capability WHERE code='dashboard.view'")
        with self.assertRaises(RbacCatalogError) as ctx:
            verify_catalog_present(self.con)
        self.assertIn("dashboard.view", str(ctx.exception))
        self.assertIn("migrate", str(ctx.exception))

    # S09 --------------------------------------------------------------------
    def test_s09_missing_role_raises(self):
        self.con.execute("DELETE FROM rbac_role WHERE code='searchagent'")
        with self.assertRaises(RbacCatalogError) as ctx:
            verify_catalog_present(self.con)
        self.assertIn("searchagent", str(ctx.exception))

    # S10 --------------------------------------------------------------------
    def test_s10_db_ahead_is_ok(self):
        # DB fuehrt eine Faehigkeit, die der Code (catalog.py) nicht kennt.
        self.assertNotIn("future.capability", catalog.CAPABILITY_CODES)
        self.con.execute(
            "INSERT INTO rbac_capability (code, label, description, created_at) "
            "VALUES ('future.capability', 'Zukunft', '', ?)",
            (int(time.time()),))
        verify_catalog_present(self.con)  # Code ⊆ DB gilt weiterhin -> ok

    # S11 --------------------------------------------------------------------
    def test_s11_resolver_is_read_only(self):
        self.repo.grant("supervisor", "dashboard.view", scope="alle", actor_id=1)
        self.repo.assign_role(2, "supervisor", actor_id=1)

        def counts():
            return (
                self.con.execute("SELECT COUNT(*) FROM rbac_grant").fetchone()[0],
                self.con.execute(
                    "SELECT COUNT(*) FROM person_role").fetchone()[0],
                self.con.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0],
            )

        before = counts()
        self.resolver.resolve(2)
        self.resolver.can(2, "dashboard.view")
        self.resolver.scope_for(2, "dashboard.view")
        self.assertEqual(counts(), before)


if __name__ == "__main__":
    unittest.main()

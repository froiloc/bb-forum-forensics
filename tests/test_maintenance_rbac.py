# =============================================================================
# tests/test_maintenance_rbac.py
# IT-Forensisches Ermittlungswerkzeug — Wartungsmodus (Sequenz A-D), Build 439
# =============================================================================
# Prueft die RBAC-Durchsetzung des Wartungsmodus:
#   A) TestM014Seed          — die Migration m014 seedet Rolle 'maintenance' und
#                              Recht 'wartung.durchfuehren'; der auditierte Grant
#                              ueber RbacRepo greift und der Resolver erlaubt.
#   B) TestPruefeBerechtigung — der Werkzeug-Helfer pruefe_wartungsberechtigung
#                              entscheidet korrekt (erlaubt/verweigert; fail-safe
#                              bei enter, Recovery-Vorrang bei exit/kill).
# =============================================================================

import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import management.migrations.coordinator as coordinator_migrations  # noqa: E402
from management.audit.audit_log import AuditLog  # noqa: E402
from management.gateway.coordinator_writer import CoordinatorWriter  # noqa: E402
from management.migrations.runner import MigrationRunner, discover  # noqa: E402
from management.rbac.rbac_repo import RbacRepo  # noqa: E402
from management.rbac.rbac_resolver import RbacResolver  # noqa: E402
from maintenance.cli_support import pruefe_wartungsberechtigung  # noqa: E402

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


# =============================================================================
# A) Migration m014 + auditierter Grant + Resolver
# =============================================================================
class TestM014Seed(unittest.TestCase):

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
            [(1, "chef", "Chefin", 1, 1, 0, now),
             (2, "ermittler", "Ermittler", 1, 0, 0, now)],
        )
        self.con.execute(_OLD_SCRAPE_JOBS)

        self.audit = AuditLog(self.con)
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester").run()
        self.repo = RbacRepo(self.con, CoordinatorWriter(self.con, self.audit))

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

    def test_rolle_und_recht_geseedet(self):
        # m014 hat Rolle + Faehigkeit angelegt (INSERT OR IGNORE).
        self.assertIsNotNone(self.con.execute(
            "SELECT 1 FROM rbac_role WHERE code='maintenance'").fetchone())
        self.assertIsNotNone(self.con.execute(
            "SELECT 1 FROM rbac_capability WHERE code='wartung.durchfuehren'"
        ).fetchone())

    def test_grant_maintenance_dann_resolver_erlaubt(self):
        # Mechanismus B: Grant + Rollenzuweisung ueber den auditierten Pfad.
        seq = self.repo.grant("maintenance", "wartung.durchfuehren", actor_id=1)
        self.assertIsInstance(seq, int)
        self.repo.assign_role(2, "maintenance", actor_id=1)
        # Person 2 (maintenance) darf; Person 1 (ohne Rolle) nicht (default-deny).
        self.assertTrue(RbacResolver(self.con).can(2, "wartung.durchfuehren"))
        self.assertFalse(RbacResolver(self.con).can(1, "wartung.durchfuehren"))
        # Grant traegt die Scope NULL (globale Handlung).
        row = self.con.execute(
            "SELECT scope FROM rbac_grant WHERE role_code='maintenance' AND "
            "capability_code='wartung.durchfuehren'").fetchone()
        self.assertIsNone(row["scope"])

    def test_grant_supervisor_dann_resolver_erlaubt(self):
        # Die Chef-Ermittlerin erhaelt das Recht ueblicherweise ebenfalls.
        self.repo.grant("supervisor", "wartung.durchfuehren", actor_id=1)
        self.repo.assign_role(1, "supervisor", actor_id=1)
        self.assertTrue(RbacResolver(self.con).can(1, "wartung.durchfuehren"))

    def test_migration_ist_idempotent(self):
        # Zweiter Lauf ist ein No-op (kein Fehler, keine Duplikate).
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester2").run()
        n = self.con.execute(
            "SELECT COUNT(*) FROM rbac_role WHERE code='maintenance'"
        ).fetchone()[0]
        self.assertEqual(n, 1)


# =============================================================================
# B) Werkzeug-Helfer pruefe_wartungsberechtigung
# =============================================================================
class TestPruefeBerechtigung(unittest.TestCase):
    """Minimale coordinator.db (nur die vom Helfer gelesenen Tabellen)."""

    _SYSUSER = "ermittler"

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.data_dir = Path(self._tmp)
        self.coord = self.data_dir / "coordinator.db"

    def tearDown(self):
        for fn in os.listdir(self._tmp):
            try:
                os.remove(os.path.join(self._tmp, fn))
            except OSError:
                pass
        os.rmdir(self._tmp)

    def _baue(self, *, mit_grant: bool):
        con = sqlite3.connect(str(self.coord))
        con.executescript(
            "CREATE TABLE person (id INTEGER PRIMARY KEY, "
            "system_username TEXT UNIQUE, display_name TEXT, "
            "is_investigator INT, is_supervisor INT, is_support INT, "
            "created_at INT);"
            "CREATE TABLE person_role (id INTEGER PRIMARY KEY, person_id INT, "
            "role_code TEXT, revoked_at INT);"
            "CREATE TABLE rbac_grant (id INTEGER PRIMARY KEY, role_code TEXT, "
            "capability_code TEXT, scope TEXT, revoked_at INT);"
        )
        con.execute(
            "INSERT INTO person VALUES (5, ?, 'E', 1, 0, 0, 0)",
            (self._SYSUSER,))
        con.execute(
            "INSERT INTO person_role (person_id, role_code, revoked_at) "
            "VALUES (5, 'maintenance', NULL)")
        if mit_grant:
            con.execute(
                "INSERT INTO rbac_grant (role_code, capability_code, scope, "
                "revoked_at) VALUES ('maintenance', 'wartung.durchfuehren', "
                "NULL, NULL)")
        con.commit()
        con.close()

    def test_berechtigt_enter_erlaubt(self):
        self._baue(mit_grant=True)
        ok, meldung = pruefe_wartungsberechtigung(
            self.data_dir, recovery=False, os_user=self._SYSUSER)
        self.assertTrue(ok, meldung)

    def test_nicht_berechtigt_enter_verweigert(self):
        self._baue(mit_grant=False)  # Rolle ohne Grant -> default-deny
        ok, meldung = pruefe_wartungsberechtigung(
            self.data_dir, recovery=False, os_user=self._SYSUSER)
        self.assertFalse(ok, meldung)

    def test_nicht_berechtigt_exit_bei_lesbarer_db_verweigert(self):
        # DB lesbar + nicht berechtigt -> auch bei Recovery verweigern
        # (kein Deadlock-Risiko, weil die DB ja lesbar war).
        self._baue(mit_grant=False)
        ok, _ = pruefe_wartungsberechtigung(
            self.data_dir, recovery=True, os_user=self._SYSUSER)
        self.assertFalse(ok)

    def test_fehlende_db_enter_failsafe_verweigert(self):
        # coordinator.db fehlt: bei enter (recovery=False) hart abbrechen.
        ok, _ = pruefe_wartungsberechtigung(
            self.data_dir, recovery=False, os_user=self._SYSUSER)
        self.assertFalse(ok)

    def test_fehlende_db_exit_recovery_nicht_blockiert(self):
        # coordinator.db fehlt: bei exit/kill (recovery=True) NICHT blockieren.
        ok, _ = pruefe_wartungsberechtigung(
            self.data_dir, recovery=True, os_user=self._SYSUSER)
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()

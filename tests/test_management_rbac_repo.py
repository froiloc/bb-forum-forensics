# =============================================================================
# tests/test_management_rbac_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 344: RbacRepo (auditierter RBAC-Schreibpfad), Schnitt (b).
#
# G01 — grant: rbac_grant-Zeile + RBAC_GRANTED atomar; audit_seq der Zeile ==
#       Rueckgabe-seq; Payload (role/capability/scope).
# G02 — grant ungueltig (Rolle/Faehigkeit/Scope) -> RbacError, kein Row, kein
#       Audit (Rollback).
# G03 — grant Duplikat (aktiv, gleiche role+capability) -> RbacError, kein 2. Row.
# G04 — revoke_grant: Soft-Revoke (revoked_at/by + revoke_audit_seq==seq) +
#       RBAC_REVOKED; Zeile bleibt (kein DELETE, append-only).
# G05 — revoke_grant unbekannt / bereits zurueckgenommen -> RbacError.
# G06 — assign_role: person_role-Zeile + ROLE_ASSIGNED; audit_seq==seq.
# G07 — assign_role Duplikat/unbekannte Person/ungueltige Rolle -> RbacError.
# G08 — revoke_role: Soft-Revoke + ROLE_REVOKED; Zeile bleibt.
# G09 — verify_chain gruen nach allen Writes.
# G10 — list_grants/list_person_roles: active_only schliesst Zurueckgenommene aus;
#       --all zeigt sie.
# G11 — default-deny-Ausgangszustand: frisch keine Grants/Rollen; nach
#       grant+revoke wieder keine AKTIVEN.
# A01 — CLI: grant + list-grants via main(argv) (Ende-zu-Ende ueber die CLI).
#
# Version: v0.7.344 · Build: 344 · 2026-07-10
# =============================================================================

import io
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations
from management.audit.audit_log import AuditLog
from management.audit.event_types import EventType
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.rbac import rbac_admin
from management.rbac.rbac_repo import RbacError, RbacRepo

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


class ManagementRbacRepoTests(unittest.TestCase):

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
        self.runner = MigrationRunner(
            self.con, self.mods, audit=self.audit, deployed_by="tester")
        self.applied = self.runner.run()

        self.writer = CoordinatorWriter(self.con, self.audit)
        self.repo = RbacRepo(self.con, self.writer)

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

    # Helfer -----------------------------------------------------------------
    def _grant_rows(self):
        return self.con.execute(
            "SELECT * FROM rbac_grant ORDER BY id").fetchall()

    def _role_rows(self):
        return self.con.execute(
            "SELECT * FROM person_role ORDER BY id").fetchall()

    def _audit_count(self, event_type):
        return self.con.execute(
            "SELECT COUNT(*) FROM audit_log WHERE event_type=?",
            (event_type,)).fetchone()[0]

    # G01 --------------------------------------------------------------------
    def test_g01_grant_atomic_and_coupled(self):
        seq = self.repo.grant("supervisor", "dashboard.view", scope="alle",
                              actor_id=1)
        rows = self._grant_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["role_code"], "supervisor")
        self.assertEqual(rows[0]["capability_code"], "dashboard.view")
        self.assertEqual(rows[0]["scope"], "alle")
        self.assertEqual(rows[0]["audit_seq"], seq)
        self.assertEqual(rows[0]["granted_by"], 1)
        self.assertEqual(self._audit_count(EventType.RBAC_GRANTED), 1)

    # G02 --------------------------------------------------------------------
    def test_g02_grant_invalid_rolls_back(self):
        for kwargs in (
            dict(role_code="ghost", capability_code="dashboard.view"),
            dict(role_code="supervisor", capability_code="ghost.cap"),
        ):
            with self.assertRaises(RbacError):
                self.repo.grant(kwargs["role_code"], kwargs["capability_code"],
                                actor_id=1)
        with self.assertRaises(RbacError):
            self.repo.grant("supervisor", "dashboard.view", scope="weltweit",
                            actor_id=1)
        # Nichts geschrieben, kein Audit.
        self.assertEqual(len(self._grant_rows()), 0)
        self.assertEqual(self._audit_count(EventType.RBAC_GRANTED), 0)

    # G03 --------------------------------------------------------------------
    def test_g03_grant_duplicate_active_rejected(self):
        self.repo.grant("lector", "reports.review", scope="alle", actor_id=1)
        with self.assertRaises(RbacError):
            self.repo.grant("lector", "reports.review", scope="eigene",
                            actor_id=1)
        self.assertEqual(len(self._grant_rows()), 1)

    # G04 --------------------------------------------------------------------
    def test_g04_revoke_grant_soft_and_coupled(self):
        gseq = self.repo.grant("admin", "feedback.moderate", actor_id=1)
        gid = self._grant_rows()[0]["id"]
        rseq = self.repo.revoke_grant(gid, actor_id=1, note="Umstrukturierung")
        self.assertNotEqual(gseq, rseq)
        row = self.con.execute(
            "SELECT * FROM rbac_grant WHERE id=?", (gid,)).fetchone()
        # Zeile bleibt (kein DELETE), Revoke-Felder gesetzt + gekoppelt.
        self.assertIsNotNone(row)
        self.assertIsNotNone(row["revoked_at"])
        self.assertEqual(row["revoked_by"], 1)
        self.assertEqual(row["revoke_audit_seq"], rseq)
        self.assertEqual(row["note"], "Umstrukturierung")
        self.assertEqual(self._audit_count(EventType.RBAC_REVOKED), 1)

    # G05 --------------------------------------------------------------------
    def test_g05_revoke_grant_errors(self):
        with self.assertRaises(RbacError):
            self.repo.revoke_grant(999, actor_id=1)
        self.repo.grant("searchagent", "evidence.fulltext_search", actor_id=1)
        gid = self._grant_rows()[0]["id"]
        self.repo.revoke_grant(gid, actor_id=1)
        with self.assertRaises(RbacError):
            self.repo.revoke_grant(gid, actor_id=1)  # bereits revoked

    # G06 --------------------------------------------------------------------
    def test_g06_assign_role_atomic_and_coupled(self):
        seq = self.repo.assign_role(2, "investigator", actor_id=1)
        rows = self._role_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["person_id"], 2)
        self.assertEqual(rows[0]["role_code"], "investigator")
        self.assertEqual(rows[0]["audit_seq"], seq)
        self.assertEqual(self._audit_count(EventType.ROLE_ASSIGNED), 1)

    # G07 --------------------------------------------------------------------
    def test_g07_assign_role_errors(self):
        with self.assertRaises(RbacError):
            self.repo.assign_role(999, "investigator", actor_id=1)  # Person?
        with self.assertRaises(RbacError):
            self.repo.assign_role(2, "ghost", actor_id=1)  # Rolle?
        self.repo.assign_role(2, "support", actor_id=1)
        with self.assertRaises(RbacError):
            self.repo.assign_role(2, "support", actor_id=1)  # Duplikat aktiv
        self.assertEqual(len(self._role_rows()), 1)

    # G08 --------------------------------------------------------------------
    def test_g08_revoke_role_soft(self):
        self.repo.assign_role(2, "lector", actor_id=1)
        prid = self._role_rows()[0]["id"]
        rseq = self.repo.revoke_role(prid, actor_id=1)
        row = self.con.execute(
            "SELECT * FROM person_role WHERE id=?", (prid,)).fetchone()
        self.assertIsNotNone(row)  # bleibt
        self.assertIsNotNone(row["revoked_at"])
        self.assertEqual(row["revoke_audit_seq"], rseq)
        self.assertEqual(self._audit_count(EventType.ROLE_REVOKED), 1)
        with self.assertRaises(RbacError):
            self.repo.revoke_role(prid, actor_id=1)  # bereits revoked
        with self.assertRaises(RbacError):
            self.repo.revoke_role(999, actor_id=1)   # unbekannt

    # G09 --------------------------------------------------------------------
    def test_g09_chain_intact(self):
        self.repo.grant("supervisor", "assignment.edit", scope="alle",
                        actor_id=1)
        gid = self._grant_rows()[0]["id"]
        self.repo.revoke_grant(gid, actor_id=1)
        self.repo.assign_role(2, "investigator", actor_id=1)
        prid = self._role_rows()[0]["id"]
        self.repo.revoke_role(prid, actor_id=1)
        self.assertTrue(self.audit.verify_chain().ok)

    # G10 --------------------------------------------------------------------
    def test_g10_list_active_only(self):
        self.repo.grant("supervisor", "dashboard.view", scope="alle",
                        actor_id=1)
        self.repo.grant("supervisor", "workload.view", scope="alle", actor_id=1)
        gid2 = self._grant_rows()[1]["id"]
        self.repo.revoke_grant(gid2, actor_id=1)
        self.assertEqual(len(self.repo.list_grants(active_only=True)), 1)
        self.assertEqual(len(self.repo.list_grants(active_only=False)), 2)

        self.repo.assign_role(2, "investigator", actor_id=1)
        self.repo.assign_role(1, "supervisor", actor_id=1)
        prid = self.repo.list_person_roles(2)[0]["id"]
        self.repo.revoke_role(prid, actor_id=1)
        self.assertEqual(len(self.repo.list_person_roles(active_only=True)), 1)
        self.assertEqual(len(self.repo.list_person_roles(active_only=False)), 2)
        self.assertEqual(
            len(self.repo.list_person_roles(2, active_only=False)), 1)

    # G11 --------------------------------------------------------------------
    def test_g11_default_deny_baseline(self):
        self.assertEqual(self.repo.list_grants(), [])
        self.assertEqual(self.repo.list_person_roles(), [])
        self.repo.grant("support", "mentoring.view", scope="eigene", actor_id=1)
        self.assertEqual(len(self.repo.list_grants()), 1)
        gid = self._grant_rows()[0]["id"]
        self.repo.revoke_grant(gid, actor_id=1)
        self.assertEqual(self.repo.list_grants(), [])  # wieder default-deny

    # A01 --------------------------------------------------------------------
    def test_a01_cli_grant_and_list(self):
        # Verbindung schliessen: die CLI oeffnet ihre eigene.
        self.con.close()
        argv_grant = ["grant", "--coordinator-db", self.db_path,
                      "--role", "supervisor", "--capability", "dashboard.view",
                      "--scope", "alle", "--actor", "h001"]
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = rbac_admin.main(argv_grant)
        self.assertEqual(rc, 0)
        self.assertIn("vergeben", buf.getvalue())

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = rbac_admin.main(
                ["list-grants", "--coordinator-db", self.db_path])
        self.assertEqual(rc2, 0)
        self.assertIn("dashboard.view", buf2.getvalue())

        # Re-open fuer tearDown-Aufraeumen.
        self.con = sqlite3.connect(self.db_path)


if __name__ == "__main__":
    unittest.main()

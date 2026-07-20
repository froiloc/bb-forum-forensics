# =============================================================================
# tests/test_management_rbac_schema.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 343: M006 (RBAC-Schema + Katalog-Seed), Schnitt (a).
#
# R01 — M006 via discover+Runner (M001..M006) angewandt; Tabellen + Indizes
#       existieren; 2. Runner-Lauf No-Op (schema_migrations).
# R02 — Seed == Code-Wahrheitsquelle catalog.py: rbac_role/rbac_capability
#       (Codes UND Label/Description) deckungsgleich mit catalog.ROLES/
#       CAPABILITIES. (Bruecke frozen-Migration <-> Code-Katalog.)
# R03 — rbac_grant UND person_role angelegt und LEER (mc: Grants erst Schnitt b).
# R04 — FK-Integritaet: foreign_key_check aller vier Tabellen sauber; die
#       erwarteten FK-Referenzen (person/audit_log/role/capability) vorhanden.
# R05 — Partial-Indizes vorhanden, jeweils mit 'WHERE revoked_at IS NULL'.
# R06 — MIGRATION_APPLIED-Beleg fuer Version 6 geschrieben; verify_chain gruen.
# R07 — Seed-Idempotenz: 2. up() clobbert bestehende Zeile NICHT (INSERT OR
#       IGNORE) und dupliziert nicht ("green and alive": direkter up()-Aufruf).
#
# Version: v0.7.343 · Build: 343 · 2026-07-10
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
from management.audit.event_types import EventType
from management.migrations.coordinator import m006_rbac_schema
from management.migrations.runner import MigrationRunner, discover
from management.rbac import catalog

# Bootstrap: 'person' direkt (nach M005-Welt) + alte scrape_jobs-Form, damit der
# volle M001..M006-Lauf denselben Weg wie PROD geht (M002-Rebuild, M005-No-Op).
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


class ManagementRbacSchemaTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")

        now = int(time.time())
        self.con.execute(_PERSON)
        self.con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (1, 'h001', 'Alpha', 1, 1, 0, ?)",
            (now,),
        )
        self.con.execute(_OLD_SCRAPE_JOBS)

        # Vollstaendiger Migrationslauf ueber discover() — exakt der PROD-Weg.
        self.audit = AuditLog(self.con)
        self.mods = discover(coordinator_migrations)
        self.runner = MigrationRunner(
            self.con, self.mods, audit=self.audit, deployed_by="tester",
        )
        self.applied = self.runner.run()

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
    def _table(self, name):
        return self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,)).fetchone()

    def _index_sql(self, name):
        row = self.con.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
            (name,)).fetchone()
        return row["sql"] if row else None

    # R01 --------------------------------------------------------------------
    def test_r01_migration_applied_idempotent(self):
        self.assertIn(6, self.applied)
        for table in ("rbac_role", "rbac_capability", "rbac_grant",
                      "person_role"):
            self.assertIsNotNone(self._table(table),
                                 "Tabelle %s fehlt" % table)
        self.assertIsNotNone(self._index_sql("ix_rbac_grant_active"))
        self.assertIsNotNone(self._index_sql("ix_person_role_active"))
        # Zweiter Runner-Lauf: No-Op (per schema_migrations uebersprungen).
        second = MigrationRunner(
            self.con, self.mods, audit=self.audit, deployed_by="tester",
        ).run()
        self.assertEqual(second, [])

    # R02 --------------------------------------------------------------------
    def test_r02_seed_matches_code_catalog(self):
        # Rollen: Codes + Label deckungsgleich mit catalog.ROLES.
        db_roles = {
            r["code"]: r["label"]
            for r in self.con.execute("SELECT code, label FROM rbac_role")
        }
        cat_roles = {r.code: r.label for r in catalog.ROLES}
        self.assertEqual(set(db_roles), catalog.ROLE_CODES)
        self.assertEqual(db_roles, cat_roles)

        # Faehigkeiten: Codes + Label + Description deckungsgleich.
        db_caps = {
            c["code"]: (c["label"], c["description"])
            for c in self.con.execute(
                "SELECT code, label, description FROM rbac_capability")
        }
        cat_caps = {c.code: (c.label, c.description)
                    for c in catalog.CAPABILITIES}
        self.assertEqual(set(db_caps), catalog.CAPABILITY_CODES)
        self.assertEqual(db_caps, cat_caps)
        # §11.3-Aufzaehlung: 15 ab Build 343, +2 ab Build 385, +2 ab Build 387,
        # +2 ab Build 401 ('mentoring_notes.view'/'.edit', geseedet in M012)
        # -> 21; +1 ab Build 420 ('templates.edit', geseedet in M013) -> 22.
        # Der Test prueft oben bereits, dass DB-Seed und Code-Katalog
        # DECKUNGSGLEICH sind — genau daran wuerde eine vergessene
        # Seed-Migration auffallen.
        # +1 ab Build 460 ('ops.promote', geseedet in M015) -> 24.
        self.assertEqual(len(cat_caps), 24)
        self.assertIn("external.view", cat_caps)
        self.assertIn("external.edit", cat_caps)
        self.assertIn("templates.edit", cat_caps)
        # Wartungsmodus (Build 439): 'wartung.durchfuehren' (Seed in M014).
        self.assertIn("wartung.durchfuehren", cat_caps)
        # Fremdforum-Promotion (Build 460): 'ops.promote' (Seed in M015).
        self.assertIn("ops.promote", cat_caps)
        # Build 401: Betreuungs-Notizen (Seed in M012).
        self.assertIn("mentoring_notes.view", cat_caps)
        self.assertIn("mentoring_notes.edit", cat_caps)
        # Build 387: Ergebnisbewertung (Seed in M011).
        self.assertIn("results.view", cat_caps)
        self.assertIn("results.edit", cat_caps)
        # Build 420: Redakteur:in fuer die Authoring-Werkzeuge (Seed in M013).
        self.assertIn("template_editor", cat_roles)
        # Wartungsmodus (Build 439): Rolle 'maintenance' (Seed in M014).
        self.assertIn("maintenance", cat_roles)
        # 6 Rollen ab Build 343, +1 ab Build 420 ('template_editor'),
        # +1 ab Build 439 ('maintenance') -> 8.
        self.assertEqual(len(cat_roles), 8)

    # R03 --------------------------------------------------------------------
    def test_r03_grant_and_person_role_empty(self):
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM rbac_grant").fetchone()[0], 0)
        self.assertEqual(
            self.con.execute(
                "SELECT COUNT(*) FROM person_role").fetchone()[0], 0)

    # R04 --------------------------------------------------------------------
    def test_r04_foreign_key_integrity(self):
        self.con.execute("PRAGMA foreign_keys=ON")
        for table in ("rbac_role", "rbac_capability", "rbac_grant",
                      "person_role"):
            violations = self.con.execute(
                "PRAGMA foreign_key_check(%s)" % table).fetchall()
            self.assertEqual(list(violations), [],
                             "FK-Verletzung in %s" % table)

        # Erwartete FK-Ziele in rbac_grant.
        grant_fks = {
            (r["from"], r["table"])
            for r in self.con.execute("PRAGMA foreign_key_list(rbac_grant)")
        }
        for expect in (("role_code", "rbac_role"),
                       ("capability_code", "rbac_capability"),
                       ("audit_seq", "audit_log"),
                       ("granted_by", "person"),
                       ("revoked_by", "person"),
                       ("revoke_audit_seq", "audit_log")):
            self.assertIn(expect, grant_fks)

        # Erwartete FK-Ziele in person_role.
        pr_fks = {
            (r["from"], r["table"])
            for r in self.con.execute("PRAGMA foreign_key_list(person_role)")
        }
        for expect in (("person_id", "person"),
                       ("role_code", "rbac_role"),
                       ("audit_seq", "audit_log"),
                       ("revoke_audit_seq", "audit_log")):
            self.assertIn(expect, pr_fks)

    # R05 --------------------------------------------------------------------
    def test_r05_partial_indexes(self):
        for name in ("ix_rbac_grant_active", "ix_person_role_active"):
            sql = self._index_sql(name)
            self.assertIsNotNone(sql, "Index %s fehlt" % name)
            self.assertIn("revoked_at IS NULL", sql,
                          "Index %s ist nicht partiell" % name)

    # R06 --------------------------------------------------------------------
    def test_r06_migration_audited_and_chain_intact(self):
        rows = self.con.execute(
            "SELECT target_id FROM audit_log WHERE event_type=? "
            "AND target_type='migration'", (EventType.MIGRATION_APPLIED,)
        ).fetchall()
        applied_targets = {r["target_id"] for r in rows}
        self.assertIn("6", applied_targets)
        self.assertTrue(self.audit.verify_chain().ok,
                        "Audit-Kette nach M006 nicht intakt")

    # R07 --------------------------------------------------------------------
    def test_r07_seed_idempotent_no_clobber(self):
        # Bestehende Zeile veraendern; direkter 2. up() darf NICHT clobbern
        # (INSERT OR IGNORE) und nicht duplizieren ("green and alive").
        self.con.execute(
            "UPDATE rbac_role SET label='HANDGEAENDERT' WHERE code='supervisor'")
        before = self.con.execute(
            "SELECT COUNT(*) FROM rbac_role").fetchone()[0]

        m006_rbac_schema.up(self.con)

        after = self.con.execute(
            "SELECT COUNT(*) FROM rbac_role").fetchone()[0]
        self.assertEqual(before, after, "Seed hat Zeilen dupliziert")
        label = self.con.execute(
            "SELECT label FROM rbac_role WHERE code='supervisor'"
        ).fetchone()["label"]
        self.assertEqual(label, "HANDGEAENDERT",
                         "INSERT OR IGNORE hat bestehende Zeile ueberschrieben")


if __name__ == "__main__":
    unittest.main()

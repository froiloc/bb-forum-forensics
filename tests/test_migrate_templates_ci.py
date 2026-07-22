# =============================================================================
# tests/test_migrate_templates_ci.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: templates.db-Migration
# =============================================================================
# Testsuite fuer management/migrate_templates_ci.py (Build 497):
#   ergaenzt placeholders.validation_ci (INTEGER NOT NULL DEFAULT 0), idempotent.
#
# MC01 — apply_migration fuegt die Spalte hinzu; Bestandszeilen erhalten 0
# MC02 — idempotent: zweiter Lauf ist No-op (already_migrated)
# MC03 — Audit-Zeile (action 'migrate', target_type 'placeholder') geschrieben
# MC04 — integrity_check bleibt 'ok'
# MC05 — fehlende placeholders-Tabelle -> RuntimeError (Hinweis auf 489)
#
# Version: v0.8.497 · Build: 497 · 2026-07-22
# Beleg: mc-Wunsch Case-Insensitivity 2026-07-22.
# =============================================================================

import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.migrate_templates_ci import apply_migration, _column_exists
from management.migrate_templates_placeholders import (
    DDL_PLACEHOLDERS, DDL_INDEXES,
)

_DDL_AUDIT = """
CREATE TABLE templates_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL, target_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('module','query','template','placeholder')),
    changed_by TEXT NOT NULL, changed_at INTEGER NOT NULL,
    old_value TEXT, new_value TEXT
)
"""


def _fresh_db(with_audit=True):
    con = sqlite3.connect(":memory:")
    con.execute(DDL_PLACEHOLDERS)
    for ddl in DDL_INDEXES:
        con.execute(ddl)
    if with_audit:
        con.execute(_DDL_AUDIT)
    # eine Bestandszeile (a-Platzhalter) fuer den Default-Nachweis
    con.execute(
        "INSERT INTO placeholders (id, title, description, type, sql_query, "
        "return_type, is_active, created_by, created_at, updated_at) "
        "VALUES ('user.name', 'Name', '', 'a', 'SELECT 1', 'scalar', 1, "
        "'seed', 0, 0)")
    con.commit()
    return con


class TestMigrateCi(unittest.TestCase):

    def test_MC01_fuegt_spalte_hinzu_default_0(self):
        con = _fresh_db()
        self.assertFalse(_column_exists(con, "placeholders", "validation_ci"))
        res = apply_migration(con, changed_by="tester")
        self.assertFalse(res["already_migrated"])
        self.assertTrue(_column_exists(con, "placeholders", "validation_ci"))
        val = con.execute(
            "SELECT validation_ci FROM placeholders WHERE id='user.name'"
        ).fetchone()[0]
        self.assertEqual(val, 0)
        con.close()

    def test_MC02_idempotent(self):
        con = _fresh_db()
        apply_migration(con, changed_by="tester")
        res2 = apply_migration(con, changed_by="tester")
        self.assertTrue(res2["already_migrated"])
        con.close()

    def test_MC03_audit_zeile(self):
        con = _fresh_db(with_audit=True)
        res = apply_migration(con, changed_by="tester")
        self.assertTrue(res["audited"])
        row = con.execute(
            "SELECT action, target_type, changed_by FROM templates_audit_log "
            "WHERE action='migrate'").fetchone()
        self.assertEqual(tuple(row), ("migrate", "placeholder", "tester"))
        con.close()

    def test_MC04_integrity_ok(self):
        con = _fresh_db()
        apply_migration(con, changed_by="tester")
        integ = con.execute("PRAGMA integrity_check").fetchone()[0]
        self.assertEqual(integ, "ok")
        con.close()

    def test_MC05_ohne_placeholders_tabelle(self):
        con = sqlite3.connect(":memory:")
        with self.assertRaises(RuntimeError):
            apply_migration(con, changed_by="tester")
        con.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

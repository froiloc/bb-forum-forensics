# =============================================================================
# tests/test_templates_writer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — SF-4 (Build 421): TemplatesWriter + Audit-CHECK-Migration
# =============================================================================
# TW01 — migrate_templates_audit_check: CHECK wird um 'template' erweitert;
#        vorhandene Audit-Zeilen bleiben erhalten; idempotent (zweiter Lauf
#        already_widened).
# TW02 — vor der Migration scheitert ein 'template'-Audit an der CHECK; nach
#        der Migration ist es zulaessig.
# TW03 — TemplatesWriter.audited_write: fachlicher Write (report_module) UND
#        Audit-Zeile werden atomar geschrieben.
# TW04 — audited_write mit target_type='template' nach der Migration.
# TW05 — Rollback: wirft do_write, bleibt WEDER Write NOCH Audit-Zeile zurueck.
# TW06 — do_write ohne 'target_id' -> TemplatesWriteError + Rollback.
#
# Version: v0.7.421 · Build: 421 · 2026-07-14
# =============================================================================

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.gateway.templates_writer import (
    TemplatesWriter, TemplatesWriteError,
)
from management.migrate_templates_audit_check import apply_migration

_DDL_MODULES = """
CREATE TABLE report_modules (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT,
    role TEXT NOT NULL CHECK(role IN ('intro','conclusion','body','legal','appendix','closing')),
    topic TEXT NOT NULL, body TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL,
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, module_key TEXT,
    block_type TEXT NOT NULL DEFAULT 'paragraph'
        CHECK (block_type IN ('paragraph','header','list','table','quote','delimiter')),
    block_data TEXT
)
"""
_DDL_AUDIT_OLD = """
CREATE TABLE templates_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, target_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('module','query')),
    changed_by TEXT NOT NULL, changed_at INTEGER NOT NULL, old_value TEXT, new_value TEXT
)
"""


def _mk_templates_db(path: str) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute(_DDL_MODULES)
        con.execute(_DDL_AUDIT_OLD)
        # eine bestehende Audit-Zeile (soll den Rebuild ueberleben).
        con.execute(
            "INSERT INTO templates_audit_log (action, target_id, target_type, "
            "changed_by, changed_at) VALUES ('create','7','module','h001',100)")
        con.commit()
    finally:
        con.close()


def _mk_module(con):
    cur = con.execute(
        "INSERT INTO report_modules (title, description, role, topic, body, "
        "sort_order, is_active, created_by, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("Vorlagen-Baustein", "", "body", "Aktivitaet",
         "Text {{a:user.username}}", 0, 1, "h004", 1000, 1000))
    return {"target_id": str(cur.lastrowid), "new_value": "Vorlagen-Baustein"}


class TemplatesWriterTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "templates.db")
        _mk_templates_db(self._db)

    def tearDown(self):
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    def _audit_ddl(self, con):
        return con.execute(
            "SELECT sql FROM sqlite_master WHERE name='templates_audit_log'"
        ).fetchone()[0]

    # TW01 -------------------------------------------------------------------
    def test_tw01_migration_widens_and_idempotent(self):
        con = sqlite3.connect(self._db)
        try:
            self.assertNotIn("'template'", self._audit_ddl(con))
            r1 = apply_migration(con)
            self.assertTrue(r1["widened"])
            self.assertIn("'template'", self._audit_ddl(con))
            # Bestehende Zeile ueberlebt den Rebuild.
            n = con.execute("SELECT COUNT(*) FROM templates_audit_log "
                            "WHERE target_id='7'").fetchone()[0]
            self.assertEqual(n, 1)
            # Idempotent: zweiter Lauf ist No-op.
            r2 = apply_migration(con)
            self.assertFalse(r2["widened"])
            self.assertTrue(r2["already_widened"])
        finally:
            con.close()

    # TW02 -------------------------------------------------------------------
    def test_tw02_template_check_before_after(self):
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    "INSERT INTO templates_audit_log (action, target_id, "
                    "target_type, changed_by, changed_at) "
                    "VALUES ('create','1','template','h004',1)")
            apply_migration(con)
            # jetzt zulaessig:
            con.execute(
                "INSERT INTO templates_audit_log (action, target_id, "
                "target_type, changed_by, changed_at) "
                "VALUES ('create','1','template','h004',1)")
            n = con.execute("SELECT COUNT(*) FROM templates_audit_log "
                            "WHERE target_type='template'").fetchone()[0]
            self.assertEqual(n, 1)
        finally:
            con.close()

    # TW03 -------------------------------------------------------------------
    def test_tw03_audited_write_module(self):
        con = sqlite3.connect(self._db)
        con.execute("PRAGMA journal_mode=delete")
        try:
            w = TemplatesWriter(con)
            res = w.audited_write(do_write=_mk_module, action="create",
                                  target_type="module", changed_by="h004")
            mid = res["target_id"]
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM report_modules").fetchone()[0], 1)
            row = con.execute(
                "SELECT action, target_id, target_type, changed_by, new_value "
                "FROM templates_audit_log WHERE target_id=? AND action='create'",
                (mid,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[2], "module")
            self.assertEqual(row[3], "h004")
            self.assertEqual(row[4], "Vorlagen-Baustein")
        finally:
            con.close()

    # TW04 -------------------------------------------------------------------
    def test_tw04_audited_write_template_after_migration(self):
        con = sqlite3.connect(self._db)
        con.execute("PRAGMA journal_mode=delete")
        try:
            apply_migration(con)
            w = TemplatesWriter(con)
            res = w.audited_write(
                do_write=lambda c: {"target_id": "spurenvermerk_v1",
                                    "new_value": "{...blocks_json...}"},
                action="create", target_type="template", changed_by="h004")
            self.assertEqual(res["target_id"], "spurenvermerk_v1")
            n = con.execute("SELECT COUNT(*) FROM templates_audit_log "
                            "WHERE target_type='template'").fetchone()[0]
            self.assertEqual(n, 1)
        finally:
            con.close()

    # TW05 -------------------------------------------------------------------
    def test_tw05_rollback_on_error(self):
        con = sqlite3.connect(self._db)
        con.execute("PRAGMA journal_mode=delete")
        try:
            def _boom(c):
                c.execute(
                    "INSERT INTO report_modules (title, description, role, "
                    "topic, body, sort_order, is_active, created_by, "
                    "created_at, updated_at) VALUES "
                    "('X','','body','t','b',0,1,'h004',1,1)")
                raise ValueError("boom")
            w = TemplatesWriter(con)
            with self.assertRaises(ValueError):
                w.audited_write(do_write=_boom, action="create",
                                target_type="module", changed_by="h004")
            # weder Modul noch Audit-Zeile:
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM report_modules").fetchone()[0], 0)
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM templates_audit_log "
                "WHERE action='create' AND target_id!='7'").fetchone()[0], 0)
        finally:
            con.close()

    # TW06 -------------------------------------------------------------------
    def test_tw06_missing_target_id_rolls_back(self):
        con = sqlite3.connect(self._db)
        con.execute("PRAGMA journal_mode=delete")
        try:
            def _no_id(c):
                c.execute(
                    "INSERT INTO report_modules (title, description, role, "
                    "topic, body, sort_order, is_active, created_by, "
                    "created_at, updated_at) VALUES "
                    "('Y','','body','t','b',0,1,'h004',1,1)")
                return {"new_value": "Y"}   # KEIN target_id
            w = TemplatesWriter(con)
            with self.assertRaises(TemplatesWriteError):
                w.audited_write(do_write=_no_id, action="create",
                                target_type="module", changed_by="h004")
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM report_modules").fetchone()[0], 0)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()

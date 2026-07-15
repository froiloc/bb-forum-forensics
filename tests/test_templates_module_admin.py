# =============================================================================
# tests/test_templates_module_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — W1 (Build 426): Baustein-Modul-Authoring (Backend)
# =============================================================================
# TM01 — validate_static: gueltiges Modul -> keine Fehler.
# TM02 — validate_static: module_key-Zeichenraum, Pflichtfelder title/topic/body.
# TM03 — validate_static: role-Pruefung (ROLES).
# TM04 — placeholder_summary: zaehlt auto/mandatory/optional in Auftrittsreihenfolge.
# TM05 — ModuleAuthorRepo.upsert: create + update, je Audit-Zeile (module),
#        module_key gesetzt, genau EINE Zeile.
# TM06 — GET /api/templates/modules: 200 mit Recht, 403 ohne.
# TM07 — POST /api/templates/module: anlegen (200) + Liste + Audit; 400 bei
#        ungueltigen Feldern (nichts geschrieben).
# TM08 — POST /api/templates/module/dryrun: schreibfrei (summary), NICHTS
#        geschrieben; ok=False bei Fehler (200); 403 ohne Recht.
#
# Version: v0.7.426 · Build: 426 · 2026-07-15
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
from management.server.management_app import ManagementApp
from management.templates_admin.module_validator import (
    validate_static, placeholder_summary, ROLES,
)
from management.templates_admin.module_repo import ModuleAuthorRepo

# report_modules (inkl. module_key + partieller UNIQUE-Index) + templates_audit_log.
_DDL_MODULES = """
CREATE TABLE report_modules (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT,
    role TEXT NOT NULL CHECK (role IN ('intro','conclusion','body','legal','appendix','closing')),
    topic TEXT NOT NULL, body TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL,
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, module_key TEXT
);
CREATE UNIQUE INDEX ux_report_modules_key ON report_modules (module_key)
    WHERE module_key IS NOT NULL;
"""
_DDL_AUDIT = """
CREATE TABLE templates_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, target_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('module','query','template')),
    changed_by TEXT NOT NULL, changed_at INTEGER NOT NULL, old_value TEXT, new_value TEXT
)
"""
_GOOD = {"module_key": "intro.standard", "title": "Standard-Einleitung",
         "description": "", "role": "intro", "topic": "Allgemein",
         "body": "Guten Tag {{a:username}}, dies ist {{m:sachbearbeiter}}.",
         "sort_order": 1}

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
    error_message TEXT, assigned_to INTEGER, note TEXT
)
"""


def _mk_templates_db(path):
    con = sqlite3.connect(path)
    try:
        con.executescript(_DDL_MODULES)
        con.executescript(_DDL_AUDIT)
        con.commit()
    finally:
        con.close()


class ValidatorTests(unittest.TestCase):
    def test_tm01_good(self):
        self.assertEqual(validate_static(_GOOD), [])

    def test_tm02_key_and_required(self):
        self.assertTrue(any("module_key" in e for e in validate_static(
            {**_GOOD, "module_key": "hat leer"})))
        self.assertTrue(any("module_key" in e for e in validate_static(
            {**_GOOD, "module_key": ""})))
        self.assertTrue(any("title" in e for e in validate_static(
            {**_GOOD, "title": "  "})))
        self.assertTrue(any("topic" in e for e in validate_static(
            {**_GOOD, "topic": ""})))
        self.assertTrue(any("body" in e for e in validate_static(
            {**_GOOD, "body": "   "})))

    def test_tm03_role(self):
        self.assertTrue(any("role" in e for e in validate_static(
            {**_GOOD, "role": "quatsch"})))
        # alle erlaubten Rollen sind gueltig.
        for r in ROLES:
            self.assertEqual(validate_static({**_GOOD, "role": r}), [])

    def test_tm04_placeholder_summary(self):
        s = placeholder_summary(
            "A {{a:x}} und {{auto:y}} sowie {{m:z}} und {{o:w}}.")
        # Reihenfolge des ersten Auftretens: auto, mandatory, optional.
        self.assertEqual(s[0], {"kind": "auto", "count": 2})
        self.assertEqual(s[1], {"kind": "mandatory", "count": 1})
        self.assertEqual(s[2], {"kind": "optional", "count": 1})
        # kein Platzhalter -> leere Liste.
        self.assertEqual(placeholder_summary("nur Text"), [])


class RepoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "templates.db")
        _mk_templates_db(self._db)

    def tearDown(self):
        for root, _d, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
        os.rmdir(self._tmp)

    def test_tm05_upsert_create_and_update(self):
        con = sqlite3.connect(self._db)
        con.execute("PRAGMA journal_mode=delete")
        try:
            repo = ModuleAuthorRepo(con)
            r1 = repo.upsert(_GOOD, changed_by="h004")
            self.assertTrue(r1["created"])
            self.assertEqual(r1["target_id"], "intro.standard")
            row = con.execute("SELECT title, module_key, role FROM report_modules "
                              "WHERE module_key='intro.standard'").fetchone()
            self.assertEqual(row[1], "intro.standard")
            # Update.
            r2 = repo.upsert({**_GOOD, "title": "Neu", "body": "ohne Platzhalter"},
                             changed_by="h004")
            self.assertFalse(r2["created"])
            row2 = con.execute("SELECT title FROM report_modules "
                               "WHERE module_key='intro.standard'").fetchone()
            self.assertEqual(row2[0], "Neu")
            # Genau EINE Zeile (Update, kein zweiter Datensatz).
            self.assertEqual(con.execute("SELECT COUNT(*) FROM report_modules"
                                         ).fetchone()[0], 1)
            # Zwei Audit-Zeilen (create + update), target_type 'module'.
            n = con.execute("SELECT COUNT(*) FROM templates_audit_log "
                            "WHERE target_id='intro.standard' "
                            "AND target_type='module'").fetchone()[0]
            self.assertEqual(n, 2)
        finally:
            con.close()


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=delete")
        con.execute(_PERSON)
        now = int(time.time())
        for pid, un in ((1, "h001"), (2, "h002")):
            con.execute("INSERT INTO person (id, system_username, display_name,"
                        " is_investigator, is_supervisor, is_support, "
                        "created_at) VALUES (?, ?, ?, 1, 0, 0, ?)",
                        (pid, un, un, now))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con
        self.rbac = RbacRepo(con, CoordinatorWriter(con, AuditLog(con)))
        self.rbac.grant("template_editor", "templates.edit", scope="alle",
                        actor_id=1)
        self.rbac.assign_role(1, "template_editor", actor_id=1)

        self._tdb = os.path.join(self._tmp, "templates.db")
        _mk_templates_db(self._tdb)

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

    def _app(self):
        return ManagementApp(self._db, templates_db=self._tdb)

    def _counts(self):
        con = sqlite3.connect("file:%s?mode=ro" % self._tdb, uri=True)
        try:
            r = con.execute("SELECT COUNT(*) FROM report_modules").fetchone()[0]
            a = con.execute("SELECT COUNT(*) FROM templates_audit_log").fetchone()[0]
        finally:
            con.close()
        return r, a

    def test_tm06_list_gated(self):
        self.assertEqual(self._app().dispatch(1, "/api/templates/modules")
                         .status, 200)
        self.assertEqual(self._app().dispatch(2, "/api/templates/modules")
                         .status, 403)

    def test_tm07_create_and_validation(self):
        r = self._app().dispatch_write(1, "/api/templates/module", dict(_GOOD))
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertTrue(d["created"])
        self.assertEqual(d["target_id"], "intro.standard")
        lst = json.loads(self._app().dispatch(1, "/api/templates/modules")
                         .body.decode("utf-8"))
        self.assertEqual(lst["count"], 1)
        self.assertEqual(self._counts(), (1, 1))
        # ungueltige Rolle -> 400.
        bad = {**_GOOD, "module_key": "x.y", "role": "quatsch"}
        r2 = self._app().dispatch_write(1, "/api/templates/module", bad)
        self.assertEqual(r2.status, 400)
        self.assertEqual(json.loads(r2.body.decode("utf-8"))["error"],
                         "validation")
        self.assertEqual(self._counts(), (1, 1))

    def test_tm08_dryrun_is_write_free(self):
        self.assertEqual(self._counts(), (0, 0))
        r = self._app().dispatch_write(
            1, "/api/templates/module/dryrun", dict(_GOOD))
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertTrue(d["ok"])
        self.assertEqual(d["errors"], [])
        kinds = [s["kind"] for s in d["summary"]]
        self.assertIn("auto", kinds)
        self.assertIn("mandatory", kinds)
        self.assertEqual(self._counts(), (0, 0))
        # Fehlerfall als Daten (ok False, 200), nichts geschrieben.
        bad = {**_GOOD, "body": "   "}
        r2 = self._app().dispatch_write(
            1, "/api/templates/module/dryrun", bad)
        self.assertEqual(r2.status, 200)
        d2 = json.loads(r2.body.decode("utf-8"))
        self.assertFalse(d2["ok"])
        self.assertTrue(len(d2["errors"]) >= 1)
        self.assertEqual(self._counts(), (0, 0))
        # ohne Recht 403.
        self.assertEqual(self._app().dispatch_write(
            2, "/api/templates/module/dryrun", dict(_GOOD)).status, 403)


if __name__ == "__main__":
    unittest.main()

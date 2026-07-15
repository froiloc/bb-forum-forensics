# =============================================================================
# tests/test_templates_document_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — W3 (Build 424): Dokumentvorlagen-Authoring (Backend)
# =============================================================================
# TD01 — validate_static: gueltige Vorlage -> keine Fehler.
# TD02 — validate_static: template_key-Zeichenraum, Pflichtfelder, report_type.
# TD03 — validate_blocks: leer / kein Objekt / unbekannter block_type /
#        block_data kein Objekt -> je EIN Fehler pro Block (kein Uebersprung).
# TD04 — coerce_blocks: 'blocks' (Liste) bzw. 'blocks_json' (String); kaputtes JSON.
# TD05 — block_type_summary: zaehlt in Auftrittsreihenfolge.
# TD06 — TemplateAuthorRepo.upsert: create + update, je Audit-Zeile (template),
#        blocks_json korrekt serialisiert.
# TD07 — GET /api/templates/documents: 200 mit Recht, 403 ohne.
# TD08 — POST /api/templates/document: anlegen (200) + Liste + Audit; 400 bei
#        ungueltiger Struktur.
# TD09 — POST /api/templates/document/dryrun: schreibfrei (summary), NICHTS
#        geschrieben; ok=False bei Fehler (200, Fehler als Daten); 403 ohne Recht.
#
# Version: v0.7.424 · Build: 424 · 2026-07-15
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
from management.templates_admin.template_validator import (
    validate_static, validate_blocks, coerce_blocks, block_type_summary,
)
from management.templates_admin.template_repo import TemplateAuthorRepo

# report_templates + templates_audit_log (CHECK bereits um 'template' erweitert,
# wie nach migrate_templates_audit_check / Build 421).
_DDL_TEMPLATES = """
CREATE TABLE report_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT, template_key TEXT NOT NULL,
    title TEXT NOT NULL, description TEXT,
    report_type TEXT NOT NULL CHECK (report_type IN ('interim','final','addendum')),
    blocks_json TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL,
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE UNIQUE INDEX rt_key_idx ON report_templates (template_key);
"""
_DDL_AUDIT = """
CREATE TABLE templates_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, target_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('module','query','template')),
    changed_by TEXT NOT NULL, changed_at INTEGER NOT NULL, old_value TEXT, new_value TEXT
)
"""
_BLOCKS = [
    {"block_type": "header", "block_data": {"text": "Einleitung", "level": 2}},
    {"block_type": "paragraph", "block_data": {"text": "Text mit {{a:name}}."}},
]
_GOOD = {"template_key": "standard.final", "title": "Standard-Abschluss",
         "description": "", "report_type": "final", "blocks": _BLOCKS,
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
        con.executescript(_DDL_TEMPLATES)
        con.executescript(_DDL_AUDIT)
        con.commit()
    finally:
        con.close()


class ValidatorTests(unittest.TestCase):
    def test_td01_good(self):
        self.assertEqual(validate_static(_GOOD), [])

    def test_td02_key_title_type(self):
        self.assertTrue(any("template_key" in e for e in validate_static(
            {**_GOOD, "template_key": "hat leerzeichen"})))
        self.assertTrue(any("template_key" in e for e in validate_static(
            {**_GOOD, "template_key": ""})))
        self.assertTrue(any("title" in e for e in validate_static(
            {**_GOOD, "title": "  "})))
        self.assertTrue(any("report_type" in e for e in validate_static(
            {**_GOOD, "report_type": "zwischen"})))

    def test_td03_block_structure_reports_each(self):
        # leer
        self.assertTrue(validate_blocks([]))
        # kein Objekt + unbekannter Typ + block_data kein Objekt => 3 Bloecke,
        # jeder mit eigenem Fehler (kein stiller Uebersprung).
        errs = validate_blocks([
            "kaputt",
            {"block_type": "quatsch", "block_data": {}},
            {"block_type": "paragraph", "block_data": "kein-objekt"},
        ])
        self.assertTrue(any("Block 0" in e for e in errs))
        self.assertTrue(any("Block 1" in e and "quatsch" in e for e in errs))
        self.assertTrue(any("Block 2" in e and "block_data" in e for e in errs))
        # gueltige Bloecke -> keine Fehler.
        self.assertEqual(validate_blocks(_BLOCKS), [])

    def test_td04_coerce_blocks(self):
        b, err = coerce_blocks({"blocks": _BLOCKS})
        self.assertIsNone(err)
        self.assertEqual(len(b), 2)
        # aus JSON-String.
        b2, err2 = coerce_blocks({"blocks_json": json.dumps(_BLOCKS)})
        self.assertIsNone(err2)
        self.assertEqual(len(b2), 2)
        # kaputtes JSON -> Fehler, keine Liste.
        b3, err3 = coerce_blocks({"blocks_json": "{nicht json"})
        self.assertIsNone(b3)
        self.assertTrue(err3)
        # gar keine Bloecke -> Fehler.
        b4, err4 = coerce_blocks({})
        self.assertIsNone(b4)
        self.assertTrue(err4)

    def test_td05_summary(self):
        s = block_type_summary(_BLOCKS + [
            {"block_type": "paragraph", "block_data": {"text": "x"}}])
        # Auftrittsreihenfolge: header (1), paragraph (2).
        self.assertEqual(s[0], {"block_type": "header", "count": 1})
        self.assertEqual(s[1], {"block_type": "paragraph", "count": 2})


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

    def test_td06_upsert_create_and_update(self):
        con = sqlite3.connect(self._db)
        con.execute("PRAGMA journal_mode=delete")
        try:
            repo = TemplateAuthorRepo(con)
            r1 = repo.upsert(_GOOD, changed_by="h004")
            self.assertTrue(r1["created"])
            self.assertEqual(r1["target_id"], "standard.final")
            # blocks_json korrekt serialisiert (2 Bloecke).
            row = con.execute("SELECT title, blocks_json FROM report_templates "
                              "WHERE template_key='standard.final'").fetchone()
            self.assertEqual(len(json.loads(row[1])), 2)
            # Update (Titel + ein Block mehr).
            r2 = repo.upsert({**_GOOD, "title": "Neu",
                              "blocks": _BLOCKS + [
                                  {"block_type": "delimiter",
                                   "block_data": {}}]},
                             changed_by="h004")
            self.assertFalse(r2["created"])
            row2 = con.execute("SELECT title, blocks_json FROM report_templates "
                               "WHERE template_key='standard.final'").fetchone()
            self.assertEqual(row2[0], "Neu")
            self.assertEqual(len(json.loads(row2[1])), 3)
            # Genau EINE Zeile (Update, kein zweiter Datensatz).
            n_rows = con.execute("SELECT COUNT(*) FROM report_templates"
                                 ).fetchone()[0]
            self.assertEqual(n_rows, 1)
            # Zwei Audit-Zeilen (create + update), target_type 'template'.
            n = con.execute("SELECT COUNT(*) FROM templates_audit_log "
                            "WHERE target_id='standard.final' "
                            "AND target_type='template'").fetchone()[0]
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
            r = con.execute("SELECT COUNT(*) FROM report_templates").fetchone()[0]
            a = con.execute("SELECT COUNT(*) FROM templates_audit_log").fetchone()[0]
        finally:
            con.close()
        return r, a

    def test_td07_list_gated(self):
        self.assertEqual(self._app().dispatch(1, "/api/templates/documents")
                         .status, 200)
        self.assertEqual(self._app().dispatch(2, "/api/templates/documents")
                         .status, 403)

    def test_td08_create_and_validation(self):
        r = self._app().dispatch_write(1, "/api/templates/document", dict(_GOOD))
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertTrue(d["created"])
        self.assertEqual(d["target_id"], "standard.final")
        # in der Liste sichtbar + genau eine Audit-Zeile (template).
        lst = json.loads(self._app().dispatch(1, "/api/templates/documents")
                         .body.decode("utf-8"))
        self.assertEqual(lst["count"], 1)
        self.assertEqual(self._counts(), (1, 1))
        # ungueltige Struktur -> 400.
        bad = {**_GOOD, "template_key": "kaputt.blocks",
               "blocks": [{"block_type": "quatsch", "block_data": {}}]}
        r2 = self._app().dispatch_write(1, "/api/templates/document", bad)
        self.assertEqual(r2.status, 400)
        self.assertEqual(json.loads(r2.body.decode("utf-8"))["error"],
                         "validation")
        # nichts Neues geschrieben.
        self.assertEqual(self._counts(), (1, 1))

    def test_td09_dryrun_is_write_free(self):
        self.assertEqual(self._counts(), (0, 0))
        r = self._app().dispatch_write(
            1, "/api/templates/document/dryrun", dict(_GOOD))
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertTrue(d["ok"])
        self.assertEqual(d["errors"], [])
        # Blocktyp-Zusammenfassung vorhanden.
        types = [s["block_type"] for s in d["summary"]]
        self.assertEqual(types, ["header", "paragraph"])
        # KEIN Schreibvorgang.
        self.assertEqual(self._counts(), (0, 0))
        # Fehlerfall als DATEN (ok False, 200), nichts geschrieben.
        bad = {**_GOOD, "blocks": [{"block_type": "quatsch", "block_data": {}}]}
        r2 = self._app().dispatch_write(
            1, "/api/templates/document/dryrun", bad)
        self.assertEqual(r2.status, 200)
        d2 = json.loads(r2.body.decode("utf-8"))
        self.assertFalse(d2["ok"])
        self.assertTrue(len(d2["errors"]) >= 1)
        self.assertEqual(self._counts(), (0, 0))
        # ohne Recht 403.
        self.assertEqual(self._app().dispatch_write(
            2, "/api/templates/document/dryrun", dict(_GOOD)).status, 403)


if __name__ == "__main__":
    unittest.main()

# =============================================================================
# tests/test_templates_query_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Platzhalter-Neuordnung (Build 489, Slice 1): Platzhalter-Authoring (Backend)
# =============================================================================
# Nachfolger der Query-Admin-Suite (Build 422): das Authoring verwaltet jetzt
# die einheitliche Tabelle templates.db.placeholders (Typen a/m/o inkl.
# Validierung; placeholder_repo/placeholder_validator statt query_repo/
# query_validator). Der Dateiname bleibt (kein Datei-Delete im Zip-Workflow).
#
# TP01 — validate_static: gueltiger a-Platzhalter -> keine Fehler/Warnungen.
# TP02 — validate_static: id-Zeichenraum, Pflichtfelder, Typ-Pflicht.
# TP03 — validate_static: SQL-Regeln (SELECT-only, ';', :uid, Verbotsliste).
# TP04 — validate_static: Typregeln — a braucht sql_query + verbietet
#        Validierung; m/o verlangen return_type 'scalar'.
# TP05 — validate_static: Validierungsarten — Paarigkeit, regex-Warnung
#        (Python-re scheitert -> WARNUNG, kein Fehler), list-JSON, like.
# TP06 — dry_run: skalar 1 Spalte OK; 2 Spalten -> Fehler; fehlende fdb -> ran False.
# TP07 — PlaceholderAuthorRepo.upsert: create + update (a und m), Audit-Zeilen
#        mit target_type 'placeholder', Normalisierung ''->NULL.
# TP08 — GET /api/templates/placeholders: 200 mit Recht, 403 ohne;
#        LEGACY-Alias /api/templates/queries liefert dieselbe Liste.
# TP09 — POST /api/templates/placeholder: a anlegen + fdb-Dry-Run; m mit
#        Validierung anlegen; LEGACY-Alias /api/templates/query deutet
#        fehlenden type als 'a'.
# TP10 — POST: statische Validierung 400 (inkl. Typregeln); Dry-Run-Fehler 400.
# TP11 — POST /api/templates/placeholder/dryrun: SCHREIBFREI (nichts
#        geschrieben, kein Audit); regex-Warnung erscheint als warnings.
# TP12 — dryrun: ungueltiger Platzhalter -> ok False + errors als Daten.
#
# Beleg: Bauplan management/Bauplan_Platzhalter_DB_v0_1.md (mc 2026-07-21).
# Version: v0.8.489 · Build: 489 · 2026-07-21
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
from management.templates_admin.placeholder_validator import (
    validate_static, dry_run, PlaceholderValidationError,
)
from management.templates_admin.placeholder_repo import PlaceholderAuthorRepo
from management.migrate_templates_placeholders import (
    DDL_PLACEHOLDERS, DDL_INDEXES,
)

_DDL_AUDIT = """
CREATE TABLE templates_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, target_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('module','query','template','placeholder')),
    changed_by TEXT NOT NULL, changed_at INTEGER NOT NULL, old_value TEXT, new_value TEXT
)
"""
_GOOD_A = {"id": "user.name", "title": "Name", "description": "", "type": "a",
           "sql_query": "SELECT username FROM uid_profile WHERE id = :uid",
           "return_type": "scalar"}
_GOOD_M = {"id": "spurennummer", "title": "Spurennummer", "description": "",
           "type": "m", "default_value": "unbekannt",
           "validation": "^[A-Z]{2}-\\d{4}$", "validation_type": "regex",
           "return_type": "scalar"}

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
        con.execute(DDL_PLACEHOLDERS)
        for ddl in DDL_INDEXES:
            con.execute(ddl)
        con.execute(_DDL_AUDIT)
        con.commit()
    finally:
        con.close()


def _mk_forensic_db(path):
    con = sqlite3.connect(path)
    try:
        con.execute("CREATE TABLE uid_profile (id INTEGER, username TEXT, "
                    "registered INTEGER, last_active INTEGER)")
        con.execute("INSERT INTO uid_profile VALUES (700,'bob',1000,2000)")
        con.commit()
    finally:
        con.close()


class ValidatorTests(unittest.TestCase):
    def test_tp01_good_a(self):
        self.assertEqual(validate_static(_GOOD_A), ([], []))

    def test_tp02_id_required_type(self):
        errs, _ = validate_static({**_GOOD_A, "id": "bad id!"})
        self.assertTrue(any("id" in e for e in errs))
        errs, _ = validate_static({**_GOOD_A, "title": "  "})
        self.assertTrue(any("title" in e for e in errs))
        errs, _ = validate_static({**_GOOD_A, "description": None})
        self.assertTrue(any("description" in e for e in errs))
        errs, _ = validate_static({**_GOOD_A, "type": ""})
        self.assertTrue(any("type" in e for e in errs))
        errs, _ = validate_static({**_GOOD_A, "type": "x"})
        self.assertTrue(any("type" in e for e in errs))

    def test_tp03_sql_regeln(self):
        errs, _ = validate_static(
            {**_GOOD_A, "sql_query": "DELETE FROM uid_profile"})
        self.assertTrue(errs)
        errs, _ = validate_static(
            {**_GOOD_A, "sql_query": "SELECT 1; DROP TABLE x"})
        self.assertTrue(errs)
        errs, _ = validate_static(
            {**_GOOD_A, "sql_query": "SELECT username FROM uid_profile "
                                     "WHERE id=?"})
        self.assertTrue(errs)
        errs, _ = validate_static(
            {**_GOOD_A, "sql_query": "SELECT u FROM t WHERE a=:uid AND b=:x"})
        self.assertTrue(errs)
        self.assertEqual(validate_static(
            {**_GOOD_A,
             "sql_query": "WITH t AS (SELECT 1 AS a) SELECT a FROM t"}),
            ([], []))

    def test_tp04_typregeln(self):
        # a ohne sql_query -> Fehler.
        errs, _ = validate_static({**_GOOD_A, "sql_query": ""})
        self.assertTrue(any("Pflicht" in e for e in errs))
        # a mit Validierung -> Fehler (mc: kein Ermittler-Einfluss).
        errs, _ = validate_static({**_GOOD_A, "validation": "^x$",
                                   "validation_type": "regex"})
        self.assertTrue(any("KEINE Validierung" in e for e in errs))
        # m ohne Query ist gueltig; m mit Query verlangt scalar.
        self.assertEqual(validate_static(_GOOD_M)[0], [])
        errs, _ = validate_static({**_GOOD_M, "sql_query": "SELECT 1",
                                   "return_type": "table"})
        self.assertTrue(any("scalar" in e for e in errs))
        # o ohne alles (nur id/title) ist gueltig.
        errs, warns = validate_static({"id": "notiz", "title": "Notiz",
                                       "description": "", "type": "o"})
        self.assertEqual((errs, warns), ([], []))

    def test_tp05_validierungsarten(self):
        # Paarigkeit.
        errs, _ = validate_static({**_GOOD_M, "validation_type": None})
        self.assertTrue(any("PAARWEISE" in e for e in errs))
        errs, _ = validate_static({**_GOOD_M, "validation": None})
        self.assertTrue(any("PAARWEISE" in e for e in errs))
        # regex: kaputtes Muster -> WARNUNG, kein Fehler (JS-Dialekt massgeblich).
        errs, warns = validate_static({**_GOOD_M, "validation": "(["})
        self.assertEqual(errs, [])
        self.assertTrue(any("Python-re" in w for w in warns))
        # list: JSON-Array Pflicht.
        errs, _ = validate_static({**_GOOD_M, "validation": "kein json",
                                   "validation_type": "list"})
        self.assertTrue(any("JSON" in e for e in errs))
        errs, _ = validate_static({**_GOOD_M, "validation": "[]",
                                   "validation_type": "list"})
        self.assertTrue(any("leer" in e.lower() for e in errs))
        self.assertEqual(validate_static(
            {**_GOOD_M, "validation": '["ja","nein"]',
             "validation_type": "list"}), ([], []))
        # like: nicht leer.
        errs, _ = validate_static({**_GOOD_M, "validation": "  ",
                                   "validation_type": "like"})
        self.assertTrue(any("like" in e for e in errs))
        self.assertEqual(validate_static(
            {**_GOOD_M, "validation": "SP-%", "validation_type": "like"}),
            ([], []))
        # unbekannte Art.
        errs, _ = validate_static({**_GOOD_M, "validation_type": "fuzzy"})
        self.assertTrue(any("validation_type" in e for e in errs))

    def test_tp06_dry_run(self):
        tmp = tempfile.mkdtemp()
        try:
            fdb = os.path.join(tmp, "forensic_700.db")
            _mk_forensic_db(fdb)
            r = dry_run(_GOOD_A["sql_query"], 700, fdb)
            self.assertTrue(r["ran"])
            self.assertEqual(r["columns"], 1)
            self.assertEqual(r["sample"], "bob")
            with self.assertRaises(PlaceholderValidationError):
                dry_run("SELECT username, registered FROM uid_profile "
                        "WHERE id=:uid", 700, fdb)
            miss = dry_run(_GOOD_A["sql_query"], 701,
                           os.path.join(tmp, "forensic_701.db"))
            self.assertFalse(miss["ran"])
        finally:
            for root, _d, files in os.walk(tmp, topdown=False):
                for f in files:
                    os.remove(os.path.join(root, f))
            os.rmdir(tmp)


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

    def test_tp07_upsert_create_update_und_normalisierung(self):
        con = sqlite3.connect(self._db)
        con.execute("PRAGMA journal_mode=delete")
        try:
            repo = PlaceholderAuthorRepo(con)
            r1 = repo.upsert(_GOOD_A, changed_by="h004")
            self.assertTrue(r1["created"])
            r2 = repo.upsert({**_GOOD_A, "title": "Neuer Name"},
                             changed_by="h004")
            self.assertFalse(r2["created"])
            row = con.execute("SELECT title, type FROM placeholders "
                              "WHERE id='user.name'").fetchone()
            self.assertEqual(tuple(row), ("Neuer Name", "a"))

            # m-Platzhalter mit Validierung; leere Strings -> NULL
            # (sonst kollidierte '' mit der Paarigkeits-CHECK).
            repo.upsert({**_GOOD_M, "sql_query": "", "tags": ""},
                        changed_by="h004")
            row = con.execute(
                "SELECT type, sql_query, validation, validation_type, tags, "
                "default_value FROM placeholders WHERE id='spurennummer'"
            ).fetchone()
            self.assertEqual(tuple(row),
                             ("m", None, "^[A-Z]{2}-\\d{4}$", "regex", None,
                              "unbekannt"))

            # Drei Audit-Zeilen, alle target_type 'placeholder'.
            n = con.execute(
                "SELECT COUNT(*) FROM templates_audit_log "
                "WHERE target_type='placeholder'").fetchone()[0]
            self.assertEqual(n, 3)
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
        self._fdir = os.path.join(self._tmp, "forensic")
        os.makedirs(self._fdir, exist_ok=True)
        _mk_forensic_db(os.path.join(self._fdir, "forensic_700.db"))

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
        return ManagementApp(self._db, templates_db=self._tdb,
                             forensic_dir=self._fdir)

    def test_tp08_list_gated_und_alias(self):
        self.assertEqual(self._app().dispatch(1, "/api/templates/placeholders")
                         .status, 200)
        self.assertEqual(self._app().dispatch(2, "/api/templates/placeholders")
                         .status, 403)
        # LEGACY-Alias (alte Maske, bis Build 490): gleiche Liste.
        r = self._app().dispatch(1, "/api/templates/queries")
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["placeholders"], d["queries"])

    def test_tp09_create_a_und_m(self):
        # a: mit fdb-Dry-Run ueber den NEUEN Pfad.
        body = {**_GOOD_A, "test_subject_id": 700}
        r = self._app().dispatch_write(1, "/api/templates/placeholder", body)
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertTrue(d["created"])
        self.assertTrue(d["dry_run"]["ran"])
        self.assertEqual(d["dry_run"]["sample"], "bob")

        # m: mit Validierung; ohne sql_query wird der Dry-Run uebersprungen.
        r2 = self._app().dispatch_write(1, "/api/templates/placeholder",
                                        dict(_GOOD_M))
        self.assertEqual(r2.status, 200)
        d2 = json.loads(r2.body.decode("utf-8"))
        self.assertTrue(d2["created"])
        self.assertFalse(d2["dry_run"]["ran"])

        # LEGACY-Alias: fehlender type -> 'a'.
        legacy = {"id": "user.alias", "title": "Alias", "description": "",
                  "sql_query": "SELECT username FROM uid_profile "
                               "WHERE id = :uid",
                  "return_type": "scalar"}
        r3 = self._app().dispatch_write(1, "/api/templates/query", legacy)
        self.assertEqual(r3.status, 200)
        con = sqlite3.connect("file:%s?mode=ro" % self._tdb, uri=True)
        try:
            rows = dict(con.execute(
                "SELECT id, type FROM placeholders").fetchall())
            n_audit = con.execute(
                "SELECT COUNT(*) FROM templates_audit_log "
                "WHERE target_type='placeholder'").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(rows, {"user.name": "a", "spurennummer": "m",
                                "user.alias": "a"})
        self.assertEqual(n_audit, 3)

    def test_tp10_validation_und_dry_run_fehler(self):
        bad = {**_GOOD_A, "sql_query": "DELETE FROM uid_profile"}
        r1 = self._app().dispatch_write(1, "/api/templates/placeholder", bad)
        self.assertEqual(r1.status, 400)
        self.assertEqual(json.loads(r1.body.decode("utf-8"))["error"],
                         "validation")
        # Typregel-Fehler (a mit Validierung).
        bad2 = {**_GOOD_A, "validation": "^x$", "validation_type": "regex"}
        r2 = self._app().dispatch_write(1, "/api/templates/placeholder", bad2)
        self.assertEqual(r2.status, 400)

        two = {**_GOOD_A, "id": "user.two",
               "sql_query": "SELECT username, registered FROM uid_profile "
                            "WHERE id=:uid", "test_subject_id": 700}
        r3 = self._app().dispatch_write(1, "/api/templates/placeholder", two)
        self.assertEqual(r3.status, 400)
        self.assertEqual(json.loads(r3.body.decode("utf-8"))["error"],
                         "dry_run")

    def _counts(self):
        con = sqlite3.connect("file:%s?mode=ro" % self._tdb, uri=True)
        try:
            q = con.execute("SELECT COUNT(*) FROM placeholders").fetchone()[0]
            a = con.execute("SELECT COUNT(*) FROM templates_audit_log"
                            ).fetchone()[0]
        finally:
            con.close()
        return q, a

    def test_tp11_dryrun_schreibfrei_mit_warnung(self):
        self.assertEqual(self._counts(), (0, 0))
        # Kaputte JS-Regex aus Python-Sicht -> ok True, aber warnings gefuellt.
        body = {**_GOOD_M, "validation": "(["}
        r = self._app().dispatch_write(
            1, "/api/templates/placeholder/dryrun", body)
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertTrue(d["ok"])
        self.assertEqual(d["errors"], [])
        self.assertTrue(any("Python-re" in w for w in d["warnings"]))
        # Kern der Zusicherung: KEIN Schreibvorgang, KEIN Audit-Beleg.
        self.assertEqual(self._counts(), (0, 0))
        # Ohne Recht: 403; LEGACY-Alias funktioniert ebenfalls.
        self.assertEqual(self._app().dispatch_write(
            2, "/api/templates/placeholder/dryrun", body).status, 403)
        self.assertEqual(self._app().dispatch_write(
            1, "/api/templates/query/dryrun",
            {**_GOOD_A, "test_subject_id": 700}).status, 200)
        self.assertEqual(self._counts(), (0, 0))

    def test_tp12_dryrun_fehler_als_daten(self):
        bad = {**_GOOD_A, "sql_query": "DELETE FROM uid_profile"}
        r = self._app().dispatch_write(
            1, "/api/templates/placeholder/dryrun", bad)
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertFalse(d["ok"])
        self.assertTrue(len(d["errors"]) >= 1)
        two = {**_GOOD_A, "sql_query": "SELECT username, registered FROM "
               "uid_profile WHERE id=:uid", "test_subject_id": 700}
        r2 = self._app().dispatch_write(
            1, "/api/templates/placeholder/dryrun", two)
        self.assertEqual(r2.status, 200)
        d2 = json.loads(r2.body.decode("utf-8"))
        self.assertFalse(d2["ok"])
        self.assertTrue(any("scalar" in e or "Spalte" in e
                            for e in d2["errors"]))
        self.assertEqual(self._counts(), (0, 0))


if __name__ == "__main__":
    unittest.main()

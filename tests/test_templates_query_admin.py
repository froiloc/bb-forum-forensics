# =============================================================================
# tests/test_templates_query_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — W2 (Build 422): Platzhalter-Query-Authoring (Backend)
# =============================================================================
# TQ01 — validate_static: gueltige Query -> keine Fehler.
# TQ02 — validate_static: id-Zeichenraum, Pflichtfelder.
# TQ03 — validate_static: kein SELECT / verbotenes Schluesselwort / ';' .
# TQ04 — validate_static: nur ':uid' als Parameter (kein '?', kein :fremd).
# TQ05 — validate_static: return_type-Pruefung.
# TQ06 — dry_run: skalar 1 Spalte OK; 2 Spalten -> Fehler; fehlende fdb -> ran False.
# TQ07 — QueryAuthorRepo.upsert: create + update, je mit Audit-Zeile (query).
# TQ08 — GET /api/templates/queries: 200 mit Recht, 403 ohne.
# TQ09 — POST /api/templates/query: anlegen + fdb-Dry-Run (ran True), Audit.
# TQ10 — POST: statische Validierung 400; Dry-Run-Fehler (2 Spalten) 400.
# TQ11 — POST /api/templates/query/dryrun: SCHREIBFREIE Vorschau, ran True,
#        sample; NICHTS geschrieben (keine Query, keine Audit-Zeile).
# TQ12 — dryrun: ungueltige Query -> ok False + errors (kein raise/400); auch
#        hier NICHTS geschrieben.
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
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
from management.templates_admin.query_validator import (
    validate_static, dry_run, QueryValidationError,
)
from management.templates_admin.query_repo import QueryAuthorRepo

_DDL_QUERIES = """
CREATE TABLE placeholder_queries (
    id TEXT NOT NULL PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
    sql_query TEXT NOT NULL, tags TEXT,
    return_type TEXT NOT NULL CHECK (return_type IN ('scalar','list','table')),
    is_active INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL,
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
)
"""
_DDL_AUDIT = """
CREATE TABLE templates_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, target_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('module','query','template')),
    changed_by TEXT NOT NULL, changed_at INTEGER NOT NULL, old_value TEXT, new_value TEXT
)
"""
_GOOD = {"id": "user.name", "title": "Name", "description": "",
         "sql_query": "SELECT username FROM uid_profile WHERE id = :uid",
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
        con.execute(_DDL_QUERIES)
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
    def test_tq01_good(self):
        self.assertEqual(validate_static(_GOOD), [])

    def test_tq02_id_and_required(self):
        self.assertTrue(any("id" in e for e in validate_static(
            {**_GOOD, "id": "bad id!"})))
        self.assertTrue(any("title" in e for e in validate_static(
            {**_GOOD, "title": "  "})))
        self.assertTrue(any("description" in e for e in validate_static(
            {**_GOOD, "description": None})))

    def test_tq03_select_only(self):
        self.assertTrue(validate_static(
            {**_GOOD, "sql_query": "DELETE FROM uid_profile"}))
        self.assertTrue(validate_static(
            {**_GOOD, "sql_query": "UPDATE uid_profile SET x=1"}))
        self.assertTrue(validate_static(
            {**_GOOD, "sql_query": "SELECT 1; DROP TABLE x"}))
        # gueltiges WITH ... SELECT ist erlaubt.
        self.assertEqual(validate_static(
            {**_GOOD, "sql_query": "WITH t AS (SELECT 1 AS a) SELECT a FROM t"}),
            [])

    def test_tq04_only_uid_param(self):
        self.assertTrue(validate_static(
            {**_GOOD, "sql_query": "SELECT username FROM uid_profile WHERE id=?"}))
        self.assertTrue(validate_static(
            {**_GOOD, "sql_query": "SELECT username FROM uid_profile "
                                   "WHERE id=:uid AND x=:other"}))

    def test_tq05_return_type(self):
        self.assertTrue(validate_static({**_GOOD, "return_type": "matrix"}))

    def test_tq06_dry_run(self):
        tmp = tempfile.mkdtemp()
        try:
            fdb = os.path.join(tmp, "forensic_700.db")
            _mk_forensic_db(fdb)
            r = dry_run(_GOOD["sql_query"], 700, fdb)
            self.assertTrue(r["ran"])
            self.assertEqual(r["columns"], 1)
            self.assertEqual(r["sample"], "bob")
            with self.assertRaises(QueryValidationError):
                dry_run("SELECT username, registered FROM uid_profile "
                        "WHERE id=:uid", 700, fdb)
            miss = dry_run(_GOOD["sql_query"], 701,
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

    def test_tq07_upsert_create_and_update(self):
        con = sqlite3.connect(self._db)
        con.execute("PRAGMA journal_mode=delete")
        try:
            repo = QueryAuthorRepo(con)
            r1 = repo.upsert(_GOOD, changed_by="h004")
            self.assertTrue(r1["created"])
            r2 = repo.upsert({**_GOOD, "title": "Neuer Name"}, changed_by="h004")
            self.assertFalse(r2["created"])
            row = con.execute("SELECT title FROM placeholder_queries "
                              "WHERE id='user.name'").fetchone()
            self.assertEqual(row[0], "Neuer Name")
            # Zwei Audit-Zeilen (create + update), target_type 'query'.
            n = con.execute("SELECT COUNT(*) FROM templates_audit_log "
                            "WHERE target_id='user.name' AND target_type='query'"
                            ).fetchone()[0]
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

    def test_tq08_list_gated(self):
        self.assertEqual(self._app().dispatch(1, "/api/templates/queries")
                         .status, 200)
        self.assertEqual(self._app().dispatch(2, "/api/templates/queries")
                         .status, 403)

    def test_tq09_create_with_dry_run(self):
        body = {**_GOOD, "test_subject_id": 700}
        r = self._app().dispatch_write(1, "/api/templates/query", body)
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertTrue(d["created"])
        self.assertTrue(d["dry_run"]["ran"])
        self.assertEqual(d["dry_run"]["sample"], "bob")
        # in der Liste sichtbar + Audit vorhanden.
        lst = json.loads(self._app().dispatch(1, "/api/templates/queries")
                         .body.decode("utf-8"))
        self.assertEqual(lst["count"], 1)
        con = sqlite3.connect("file:%s?mode=ro" % self._tdb, uri=True)
        try:
            n = con.execute("SELECT COUNT(*) FROM templates_audit_log "
                            "WHERE target_type='query'").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(n, 1)

    def test_tq10_validation_and_dry_run_errors(self):
        bad = {**_GOOD, "sql_query": "DELETE FROM uid_profile"}
        r1 = self._app().dispatch_write(1, "/api/templates/query", bad)
        self.assertEqual(r1.status, 400)
        self.assertEqual(json.loads(r1.body.decode("utf-8"))["error"],
                         "validation")

        two = {**_GOOD, "id": "user.two",
               "sql_query": "SELECT username, registered FROM uid_profile "
                            "WHERE id=:uid", "test_subject_id": 700}
        r2 = self._app().dispatch_write(1, "/api/templates/query", two)
        self.assertEqual(r2.status, 400)
        self.assertEqual(json.loads(r2.body.decode("utf-8"))["error"], "dry_run")

    def _query_count(self):
        con = sqlite3.connect("file:%s?mode=ro" % self._tdb, uri=True)
        try:
            q = con.execute("SELECT COUNT(*) FROM placeholder_queries"
                            ).fetchone()[0]
            a = con.execute("SELECT COUNT(*) FROM templates_audit_log"
                            ).fetchone()[0]
        finally:
            con.close()
        return q, a

    def test_tq11_dryrun_is_write_free(self):
        # Vorher: leer. Der Dry-Run darf daran NICHTS aendern.
        self.assertEqual(self._query_count(), (0, 0))
        body = {**_GOOD, "test_subject_id": 700}
        r = self._app().dispatch_write(1, "/api/templates/query/dryrun", body)
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertTrue(d["ok"])
        self.assertEqual(d["errors"], [])
        self.assertTrue(d["dry_run"]["ran"])
        self.assertEqual(d["dry_run"]["sample"], "bob")
        # Kern der Zusicherung: KEIN Schreibvorgang, KEIN Audit-Beleg.
        self.assertEqual(self._query_count(), (0, 0))
        # Ohne Recht: 403 (auch die Vorschau ist gatet).
        self.assertEqual(
            self._app().dispatch_write(2, "/api/templates/query/dryrun", body)
            .status, 403)

    def test_tq12_dryrun_reports_errors_as_data(self):
        # Ungueltige Query (schreibend): ok False + Fehlerliste, HTTP 200,
        # nichts geschrieben.
        bad = {**_GOOD, "sql_query": "DELETE FROM uid_profile"}
        r = self._app().dispatch_write(1, "/api/templates/query/dryrun", bad)
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertFalse(d["ok"])
        self.assertTrue(len(d["errors"]) >= 1)
        # 2-Spalten-'scalar' faellt im Dry-Run auf (als Datenfehler, nicht 400).
        two = {**_GOOD, "sql_query": "SELECT username, registered FROM "
               "uid_profile WHERE id=:uid", "test_subject_id": 700}
        r2 = self._app().dispatch_write(1, "/api/templates/query/dryrun", two)
        self.assertEqual(r2.status, 200)
        d2 = json.loads(r2.body.decode("utf-8"))
        self.assertFalse(d2["ok"])
        self.assertTrue(any("scalar" in e or "Spalte" in e for e in d2["errors"]))
        self.assertEqual(self._query_count(), (0, 0))


if __name__ == "__main__":
    unittest.main()

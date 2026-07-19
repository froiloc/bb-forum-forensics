# =============================================================================
# tests/test_management_annostats_endpoint.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Annotations-Statistik (API)
# =============================================================================
# Testsuite fuer Build 450: /api/annotation-stats (read-only, CAP_STATS,
# scope-bewusst). Der Aggregationskern ist in test_management_annotation_stats.py
# abgedeckt; hier: Rechtegate + Scope-Filter + JSON-Form am Endpunkt.
#
# AE01 — supervisor (scope alle): 200, aggregiert ueber alle Faelle
# AE02 — 403 ohne Rolle
# AE03 — investigator (scope eigene): nur eigene Faelle aggregiert
# AE04 — Fall ohne evidence_<uid>.db -> cases_without_evidence (GR1)
#
# Version: v0.7.450 · Build: 450 · 2026-07-19
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
from management.cases.cases_repo import CasesRepo
from management.server.management_app import ManagementApp

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
    error_message TEXT, assigned_to INTEGER, note TEXT,
    FOREIGN KEY(assigned_to) REFERENCES person(id)
)
"""


def _mk_evidence(path, annos):
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE annotations(id INTEGER PRIMARY KEY AUTOINCREMENT, '
                'category TEXT, tags_json TEXT, deleted_at INTEGER)')
    for cat, tags, dl in annos:
        con.execute("INSERT INTO annotations(category,tags_json,deleted_at) "
                    "VALUES(?,?,?)", (cat, tags, dl))
    con.commit()
    con.close()


class AnnostatsEndpointTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        self._ev = os.path.join(self._tmp, "evidence")
        os.makedirs(self._ev)
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        now = int(time.time())
        for pid, un, disp, sup in ((1, "h0a2898", "Chefin", 1),
                                   (2, "h002", "Mueller", 0),
                                   (3, "h003", "Gamma", 0)):
            con.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?, ?, ?, 1, ?, 0, ?)", (pid, un, disp, sup, now))
        con.execute(_OLD_SCRAPE_JOBS)
        for uid in (18, 19):
            con.execute("INSERT INTO scrape_jobs (user_id, username, "
                        "created_at) VALUES (?, ?, ?)", (uid, "b%d" % uid, now))
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.con = con

        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.rbac = RbacRepo(self.con, self.writer)
        self.cases = CasesRepo(self.con, self.writer)
        self.rbac.grant("supervisor", "stats.export_sta", scope="alle", actor_id=1)
        self.rbac.grant("investigator", "stats.export_sta", scope="eigene", actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)

        # Fall 18 -> person 2 (mit evidence), Fall 19 -> unzugewiesen (OHNE evidence)
        for uid in (18, 19):
            self.cases.create_case(uid, "b%d" % uid, actor_id=1)
        self.cases.assign(18, 2, actor_id=1)
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        _mk_evidence(os.path.join(self._ev, "evidence_18.db"),
                     [("email", '["realname"]', None),
                      ("telefon", None, None),
                      ("email", None, 1699999999)])   # soft-deleted -> zaehlt nicht
        # Fall 19: KEINE evidence_19.db

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
        return ManagementApp(self._db, evidence_dir=self._ev)

    def test_ae01_supervisor_all(self):
        r = self._app().dispatch(1, "/api/annotation-stats")
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["scope"], "alle")
        self.assertEqual(d["cases_total"], 2)
        self.assertEqual(d["annotations_total"], 2)     # soft-deleted ausgeschlossen
        bycat = {e["key"]: e["count"] for e in d["by_category"]}
        self.assertEqual(bycat["email"], 1)
        self.assertEqual(bycat["telefon"], 1)

    def test_ae02_forbidden(self):
        self.assertEqual(self._app().dispatch(3, "/api/annotation-stats").status, 403)

    def test_ae03_investigator_eigene(self):
        r = self._app().dispatch(2, "/api/annotation-stats")
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["scope"], "eigene")
        self.assertEqual(d["cases_total"], 1)           # nur Fall 18 (person 2)
        self.assertEqual(d["annotations_total"], 2)

    def test_ae04_missing_evidence_counted(self):
        d = json.loads(self._app().dispatch(1, "/api/annotation-stats").body.decode("utf-8"))
        self.assertEqual(d["cases_with_evidence"], 1)
        self.assertEqual(d["cases_without_evidence"], 1)   # Fall 19, GR1


if __name__ == "__main__":
    unittest.main()

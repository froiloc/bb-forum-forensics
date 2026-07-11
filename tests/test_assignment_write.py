# =============================================================================
# tests/test_assignment_write.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Zuweisung (Schreibpfad)
# =============================================================================
# Testsuite fuer Build 372: erster auditierter SCHREIBPFAD im Management-Server.
#
# AS01 — /api/assignable (GET): Faelle + Ermittler mit Last; 403 ohne Cap.
# AS02 — assign: schreibt UND erzeugt einen audit_log-Beleg (CASE_ASSIGNED).
# AS03 — assign(null) entzieht die Zuweisung (mit Beleg).
# AS04 — SELBSTZUWEISUNG ist erlaubt (Chefin weist sich selbst zu).
# AS05 — priority/status: schreiben + Belege; ungueltige Werte -> 400.
# AS06 — unbekannter Fall / unbekannte Person / Nicht-Ermittler -> 400.
# AS07 — ohne assignment.edit -> 403; mit Scope 'eigene' -> 403.
# AS08 — HTTP-Haertung (echter Server): POST ohne Token -> 403; falscher
#        Content-Type -> 415; PUT -> 405; korrekter POST -> 200 + Beleg.
#
# Version: v0.7.372 · Build: 372 · 2026-07-10
# =============================================================================

import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations
from management.audit.audit_log import AuditLog
from management.migrations.runner import MigrationRunner, discover
from management.gateway.coordinator_writer import CoordinatorWriter
from management.rbac.rbac_repo import RbacRepo
from management.cases.cases_repo import CasesRepo
from management.server.management_app import ManagementApp
from management.server.management_handler import ManagementRequestHandler

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


class AssignmentWriteTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        # 1 Chefin (Ermittlerin UND Supervisor), 2 Ermittler, 3 Nicht-Ermittler.
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (1,'h0a2898','Chefin',1,1,0,?)", (int(time.time()),))
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (2,'h002','Mueller',1,0,0,?)", (int(time.time()),))
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (3,'h003','Support',0,0,1,?)", (int(time.time()),))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.con = con

        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.rbac = RbacRepo(self.con, self.writer)
        self.cases = CasesRepo(self.con, self.writer)

        self.rbac.grant("supervisor", "assignment.edit", scope="alle",
                        actor_id=1)
        self.rbac.grant("investigator", "assignment.edit", scope="eigene",
                        actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)

        for uid in (18, 19):
            self.cases.create_case(uid, "b%d" % uid, actor_id=1)
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

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

    def _fresh(self):
        return sqlite3.connect(self._db)

    def _assigned_to(self, user_id):
        c = self._fresh()
        try:
            return c.execute("SELECT assigned_to FROM cases WHERE user_id=?",
                             (user_id,)).fetchone()[0]
        finally:
            c.close()

    def _audit(self, event_type, target_id):
        c = self._fresh()
        try:
            return c.execute(
                "SELECT COUNT(*) FROM audit_log WHERE event_type=? "
                "AND target_type='case' AND target_id=?",
                (event_type, str(target_id))).fetchone()[0]
        finally:
            c.close()

    # AS01 -------------------------------------------------------------------
    def test_as01_assignable(self):
        app = ManagementApp(self._db)
        r = app.dispatch(1, "/api/assignable")
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(len(d["cases"]), 2)
        pids = {i["person_id"] for i in d["investigators"]}
        self.assertEqual(pids, {1, 2})      # nur Ermittler, ohne Support (3)
        self.assertIn("open", d["statuses"])
        # person 3 hat keine Rolle -> 403
        self.assertEqual(app.dispatch(3, "/api/assignable").status, 403)

    # AS02 -------------------------------------------------------------------
    def test_as02_assign_with_audit(self):
        app = ManagementApp(self._db)
        r = app.dispatch_write(1, "/api/case/assign",
                               {"user_id": 18, "person_id": 2})
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertTrue(d["ok"])
        self.assertEqual(self._assigned_to(18), 2)
        # Der forensische Kern: die Aenderung hat einen Beleg.
        self.assertGreaterEqual(self._audit("case_assigned", 18), 1)
        self.assertIsInstance(d["audit_seq"], int)

    # AS03 -------------------------------------------------------------------
    def test_as03_unassign(self):
        app = ManagementApp(self._db)
        app.dispatch_write(1, "/api/case/assign",
                           {"user_id": 18, "person_id": 2})
        r = app.dispatch_write(1, "/api/case/assign",
                               {"user_id": 18, "person_id": None})
        self.assertEqual(r.status, 200)
        self.assertIsNone(self._assigned_to(18))
        self.assertGreaterEqual(self._audit("case_assigned", 18), 2)

    # AS04 -------------------------------------------------------------------
    def test_as04_self_assignment_allowed(self):
        # Die Chefin weist sich selbst einen Fall zu — ausdruecklich erlaubt.
        app = ManagementApp(self._db)
        r = app.dispatch_write(1, "/api/case/assign",
                               {"user_id": 19, "person_id": 1})
        self.assertEqual(r.status, 200)
        self.assertEqual(self._assigned_to(19), 1)

    # AS05 -------------------------------------------------------------------
    def test_as05_priority_and_status(self):
        app = ManagementApp(self._db)
        r1 = app.dispatch_write(1, "/api/case/priority",
                                {"user_id": 18, "priority": 1})
        self.assertEqual(r1.status, 200)
        self.assertGreaterEqual(self._audit("case_priority_set", 18), 1)

        r2 = app.dispatch_write(1, "/api/case/status",
                                {"user_id": 18, "status": "in_progress"})
        self.assertEqual(r2.status, 200)
        self.assertGreaterEqual(self._audit("case_status_changed", 18), 1)

        # Ungueltige Werte -> 400, kein Schreibvorgang.
        self.assertEqual(app.dispatch_write(
            1, "/api/case/priority", {"user_id": 18, "priority": 9}).status, 400)
        self.assertEqual(app.dispatch_write(
            1, "/api/case/status", {"user_id": 18, "status": "pfui"}).status, 400)

    # AS06 -------------------------------------------------------------------
    def test_as06_validation(self):
        app = ManagementApp(self._db)
        # unbekannter Fall
        self.assertEqual(app.dispatch_write(
            1, "/api/case/assign", {"user_id": 999, "person_id": 2}).status, 400)
        # unbekannte Person
        self.assertEqual(app.dispatch_write(
            1, "/api/case/assign", {"user_id": 18, "person_id": 99}).status, 400)
        # Person ist kein Ermittler (Support)
        r = app.dispatch_write(1, "/api/case/assign",
                               {"user_id": 18, "person_id": 3})
        self.assertEqual(r.status, 400)
        self.assertIn("not_investigator", r.body.decode("utf-8"))
        # unbekannte Schreibroute
        self.assertEqual(app.dispatch_write(1, "/api/case/pfui", {}).status, 404)

    # AS07 -------------------------------------------------------------------
    def test_as07_rbac(self):
        app = ManagementApp(self._db)
        # person 3: keine Rolle -> 403
        self.assertEqual(app.dispatch_write(
            3, "/api/case/assign", {"user_id": 18, "person_id": 2}).status, 403)
        # person 2: investigator hat assignment.edit nur mit Scope 'eigene' ->
        # 403 (Zuweisen erfordert 'alle').
        r = app.dispatch_write(2, "/api/case/assign",
                               {"user_id": 18, "person_id": 2})
        self.assertEqual(r.status, 403)
        self.assertIsNone(self._assigned_to(18))  # nichts geschrieben

    # AS08 -------------------------------------------------------------------
    def test_as08_http_hardening(self):
        app = ManagementApp(self._db)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), ManagementRequestHandler)
        srv.app = app
        srv.person_id = 1
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        base = "http://127.0.0.1:%d" % srv.server_address[1]
        try:
            # Token via GET /api/whoami beziehen.
            with urllib.request.urlopen(base + "/api/whoami") as r:
                who = json.loads(r.read().decode("utf-8"))
            token = who["write_token"]
            self.assertTrue(token)

            body = json.dumps({"user_id": 18, "person_id": 2}).encode("utf-8")

            def post(headers, method="POST", data=body):
                req = urllib.request.Request(base + "/api/case/assign",
                                             data=data, method=method)
                for k, v in headers.items():
                    req.add_header(k, v)
                try:
                    with urllib.request.urlopen(req) as r:
                        return r.status, r.read()
                except urllib.error.HTTPError as e:
                    return e.code, e.read()

            # 1) ohne Token -> 403
            code, _ = post({"Content-Type": "application/json"})
            self.assertEqual(code, 403)
            # 2) falscher Content-Type -> 415
            code, _ = post({"Content-Type": "text/plain",
                            "X-AIW-Token": token})
            self.assertEqual(code, 415)
            # 3) PUT -> 405
            code, _ = post({"Content-Type": "application/json",
                            "X-AIW-Token": token}, method="PUT")
            self.assertEqual(code, 405)
            # 4) korrekt -> 200 und der Fall ist zugewiesen (mit Beleg)
            code, raw = post({"Content-Type": "application/json",
                              "X-AIW-Token": token})
            self.assertEqual(code, 200)
            self.assertTrue(json.loads(raw.decode("utf-8"))["ok"])
            self.assertEqual(self._assigned_to(18), 2)
            self.assertGreaterEqual(self._audit("case_assigned", 18), 1)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()

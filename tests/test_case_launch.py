# =============================================================================
# tests/test_case_launch.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fallstart aus dem Portal
# =============================================================================
# Testsuite fuer Build 500: POST /api/case/launch startet den FORENSIK-Server
# (main.py) fuer einen dem Aufrufer ZUGEWIESENEN Fall. Zwei Ebenen:
#   A) CaseLauncher (Einheit, ohne echten Prozess-Spawn, ohne DB).
#   B) Endpoint (ManagementApp.dispatch_write mit injiziertem Fake-Launcher).
#
# CL01 — build_command: erwartete argv (mode cli, subject-id, auto-port, browser).
# CL02 — launch(): injizierter spawn wird gerufen, PID + command zurueckgegeben.
# CL03 — launch(): ungueltige subject_id (<=0, nicht-numerisch) -> CaseLaunchError.
# CL04 — launch(): fehlende main.py -> CaseLaunchError (sichtbarer Startzeitfehler).
# CL05 — resolve_python: Override hat Vorrang; Rueckfall auf sys.executable.
# CL06 — launch(): OSError im spawn -> CaseLaunchError (nie stiller Fehlschlag).
#
# EP01 — Eigentuemer startet eigenen Fall -> 200, ok/launched, PID; Fake gerufen.
# EP02 — Fremder Fall (nicht zugewiesen) -> 403 not_owner; Fake NICHT gerufen.
# EP03 — Unbekannter Fall -> 400 unknown_case; Fake NICHT gerufen.
# EP04 — ohne mycases.view -> 403 (Cap ist das Tor); Fake NICHT gerufen.
# EP05 — Startzeitfehler (CaseLaunchError) -> 500 launch_failed.
# EP06 — KEIN DB-Schreibzugriff: audit_log-Spitze unveraendert nach Start.
#
# Version: v0.8.500 · Build: 500 · 2026-07-22
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
from management.cases.case_launcher import CaseLauncher, CaseLaunchError
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


# =============================================================================
# A) CaseLauncher — Einheit (kein echter Prozess, keine DB).
# =============================================================================
class CaseLauncherUnitTests(unittest.TestCase):

    def setUp(self):
        # Projektwurzel mit einer LEEREN main.py, damit is_file() greift, ohne
        # dass ein echter Server startbar sein muesste (spawn ist injiziert).
        self._tmp = tempfile.mkdtemp()
        self._root = Path(self._tmp)
        (self._root / "main.py").write_text("# stub\n", encoding="utf-8")
        self._calls = []

    def tearDown(self):
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    def _fake_spawn(self, command, cwd):
        self._calls.append((command, cwd))
        return 4242

    def _launcher(self, **kw):
        return CaseLauncher(project_root=self._root, python_exe="PY",
                            spawn=self._fake_spawn, **kw)

    def test_cl01_build_command(self):
        cmd = self._launcher().build_command(12345)
        self.assertEqual(cmd[0], "PY")
        self.assertTrue(cmd[1].endswith("main.py"))
        self.assertEqual(cmd[2:], ["--mode", "cli", "--subject-id", "12345",
                                   "--auto-port", "--open-browser"])

    def test_cl02_launch_uses_spawn(self):
        info = self._launcher().launch(18)
        self.assertEqual(info["pid"], 4242)
        self.assertEqual(info["subject_id"], 18)
        self.assertEqual(len(self._calls), 1)
        self.assertEqual(self._calls[0][1], self._root)  # cwd = Projektwurzel

    def test_cl03_invalid_subject_id(self):
        for bad in (0, -5, "x", None):
            with self.assertRaises(CaseLaunchError):
                self._launcher().launch(bad)
        self.assertEqual(self._calls, [])  # nie gespawnt

    def test_cl04_missing_main_py(self):
        empty = tempfile.mkdtemp()
        try:
            l = CaseLauncher(project_root=Path(empty), python_exe="PY",
                             spawn=self._fake_spawn)
            with self.assertRaises(CaseLaunchError):
                l.launch(18)
            self.assertEqual(self._calls, [])
        finally:
            os.rmdir(empty)

    def test_cl05_resolve_python(self):
        # Override hat Vorrang.
        self.assertEqual(self._launcher().resolve_python(), "PY")
        # Ohne Override + ohne portable Laufzeit -> sys.executable (POSIX-CI).
        l = CaseLauncher(project_root=self._root, spawn=self._fake_spawn)
        self.assertEqual(l.resolve_python(), sys.executable)

    def test_cl06_spawn_oserror_wrapped(self):
        def boom(command, cwd):
            raise OSError("interpreter not executable")
        l = CaseLauncher(project_root=self._root, python_exe="PY", spawn=boom)
        with self.assertRaises(CaseLaunchError):
            l.launch(18)


# =============================================================================
# Fake-Launcher fuer die Endpoint-Ebene (kein echter Prozess-Spawn im CI).
# =============================================================================
class _FakeLauncher:
    def __init__(self, raise_error=False):
        self.calls = []
        self._raise = raise_error

    def launch(self, subject_id):
        self.calls.append(subject_id)
        if self._raise:
            raise CaseLaunchError("simulierter Startzeitfehler")
        return {"pid": 4242, "subject_id": subject_id, "command": ["x"],
                "python": "PY", "cwd": "/tmp"}


# =============================================================================
# B) Endpoint — ManagementApp.dispatch_write('/api/case/launch').
# =============================================================================
class CaseLaunchEndpointTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        for pid, un, disp, sup in ((1, "h0a2898", "Chefin", 1),
                                   (2, "h002", "Mueller", 0),
                                   (3, "h003", "Gamma", 0)):
            con.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?, ?, ?, 1, ?, 0, ?)",
                (pid, un, disp, sup, int(time.time())))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.con = con

        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.rbac = RbacRepo(self.con, self.writer)
        self.cases = CasesRepo(self.con, self.writer)

        # investigator -> mycases.view (Tor fuer den Fallstart). Chefin (1) hat
        # die Rolle bewusst NICHT -> kein mycases.view (EP04).
        self.rbac.grant("investigator", "mycases.view", scope="eigene",
                        actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)
        self.rbac.assign_role(3, "investigator", actor_id=1)

        # Fall 18 -> person 2; Fall 19 -> person 3.
        self.cases.create_case(18, "b18", actor_id=1)
        self.cases.create_case(19, "b19", actor_id=1)
        self.cases.assign(18, 2, actor_id=1)
        self.cases.assign(19, 3, actor_id=1)
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

    def _app(self, launcher):
        return ManagementApp(self._db, case_launcher=launcher)

    def _post(self, app, person_id, payload):
        r = app.dispatch_write(person_id, "/api/case/launch", payload)
        return r.status, json.loads(r.body.decode("utf-8"))

    def _audit_tip(self):
        return ManagementApp(self._db).audit_tip_seq()

    def test_ep01_owner_launches(self):
        fake = _FakeLauncher()
        status, body = self._post(self._app(fake), 2, {"subject_id": 18})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertTrue(body["launched"])
        self.assertEqual(body["subject_id"], 18)
        self.assertEqual(body["pid"], 4242)
        self.assertEqual(fake.calls, [18])

    def test_ep02_foreign_case_denied(self):
        fake = _FakeLauncher()
        # person 2 versucht Fall 19 (gehoert person 3) zu starten.
        status, body = self._post(self._app(fake), 2, {"subject_id": 19})
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "not_owner")
        self.assertEqual(fake.calls, [])  # kein Start eines fremden Falls

    def test_ep03_unknown_case(self):
        fake = _FakeLauncher()
        status, body = self._post(self._app(fake), 2, {"subject_id": 99999})
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "unknown_case")
        self.assertEqual(fake.calls, [])

    def test_ep04_without_cap_forbidden(self):
        fake = _FakeLauncher()
        # Chefin (1) hat keine investigator-Rolle -> kein mycases.view.
        status, body = self._post(self._app(fake), 1, {"subject_id": 18})
        self.assertEqual(status, 403)
        self.assertEqual(fake.calls, [])

    def test_ep05_launch_failure_reported(self):
        fake = _FakeLauncher(raise_error=True)
        status, body = self._post(self._app(fake), 2, {"subject_id": 18})
        self.assertEqual(status, 500)
        self.assertEqual(body["error"], "launch_failed")
        self.assertIn("detail", body)

    def test_ep06_no_db_write(self):
        tip_before = self._audit_tip()
        fake = _FakeLauncher()
        self._post(self._app(fake), 2, {"subject_id": 18})
        self.assertEqual(self._audit_tip(), tip_before)  # kein Audit-Beleg


if __name__ == "__main__":
    unittest.main()

# =============================================================================
# tests/test_case_detect.py
# IT-Forensisches Ermittlungswerkzeug — Fall-Autodetektion
# =============================================================================
# Testsuite fuer Build 383: CaseDetector + CaseImporter + Endpunkte + CLI.
#
# EIN FALL EXISTIERT, sobald forensic_<uid>.db vorliegt (mc 2026-07-10) —
# unabhaengig davon, ob schon jemand daran gearbeitet hat.
#
# CD01 — Vier Zustaende: ok / neu / vermisst / unlesbar.
# CD02 — Benutzername kommt autoritativ aus uid_profile.
# CD03 — Arbeitsstand (evidence/assets) wird gemeldet, ist aber KEIN Kriterium.
# CD04 — Import: nimmt 'neu' AUDITIERT auf (Beleg case_created je Fall).
# CD05 — Import ueberspringt nicht-aufnehmbare Faelle und MELDET das.
# CD06 — Endpunkte: detect (200/403) und import (200, auditiert).
# CD07 — CLI: Bericht + Exit 2 bei vermisst/unlesbar; --auto nimmt auf.
#
# Version: v0.7.383 · Build: 383 · 2026-07-10
# =============================================================================

import io
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations
from management.audit.audit_log import AuditLog
from management.migrations.runner import MigrationRunner, discover
from management.gateway.coordinator_writer import CoordinatorWriter
from management.rbac.rbac_repo import RbacRepo
from management.cases.cases_repo import CasesRepo
from management.cases.case_detector import CaseDetector
from management.cases.case_importer import CaseImporter
from management.cases import case_detect
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


def _make_forensic(path, username):
    """Minimale forensic_<uid>.db mit uid_profile (die autoritative Quelle)."""
    con = sqlite3.connect(path)
    con.isolation_level = None
    con.execute("CREATE TABLE uid_profile (id INTEGER PRIMARY KEY, "
                "username TEXT NOT NULL, group_id INTEGER)")
    con.execute("INSERT INTO uid_profile (username, group_id) VALUES (?, 1)",
                (username,))
    con.close()


def _touch_db(path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE x (a INTEGER)")
    con.close()


class CaseDetectTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._fdir = os.path.join(self._tmp, "forensic")
        self._edir = os.path.join(self._tmp, "evidence")
        self._adir = os.path.join(self._tmp, "assets")
        for d in (self._fdir, self._edir, self._adir):
            os.makedirs(d)
        self._db = os.path.join(self._tmp, "coordinator.db")

        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (1, 'h0a2898', 'Chefin', 1, 1, 0, ?)",
            (int(time.time()),))
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (2, 'h002', 'Mueller', 1, 0, 0, ?)", (int(time.time()),))
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
        self.rbac.assign_role(1, "supervisor", actor_id=1)

        # --- Ausgangslage auf der Platte ------------------------------------
        # 18: DB da + in cases        -> ok (mit evidence-DB = Arbeitsstand)
        # 19: DB da, NICHT in cases   -> neu
        # 20: in cases, DB FEHLT      -> vermisst
        # 21: DB da, aber kaputt      -> unlesbar
        _make_forensic(os.path.join(self._fdir, "forensic_18.db"), "boarder18")
        _make_forensic(os.path.join(self._fdir, "forensic_19.db"), "boarder19")
        with open(os.path.join(self._fdir, "forensic_21.db"), "wb") as f:
            f.write(b"kein sqlite")
        _touch_db(os.path.join(self._edir, "evidence_18.db"))
        _touch_db(os.path.join(self._adir, "assets_18.db"))

        self.cases.create_case(18, "boarder18", actor_id=1)
        self.cases.create_case(20, "boarder20", actor_id=1)
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

    def _det(self):
        return CaseDetector(self.con, self._fdir, self._edir, self._adir)

    def _audit_count(self, event_type, target_id):
        c = sqlite3.connect(self._db)
        try:
            return c.execute(
                "SELECT COUNT(*) FROM audit_log WHERE event_type=? "
                "AND target_id=?", (event_type, str(target_id))).fetchone()[0]
        finally:
            c.close()

    # CD01 -------------------------------------------------------------------
    def test_cd01_four_states(self):
        rep = self._det().detect()
        by = {c["user_id"]: c["status"] for c in rep["cases"]}
        self.assertEqual(by[18], "ok")
        self.assertEqual(by[19], "neu")
        self.assertEqual(by[20], "vermisst")
        self.assertEqual(by[21], "unlesbar")
        self.assertEqual(rep["counts"],
                         {"ok": 1, "neu": 1, "vermisst": 1, "unlesbar": 1})

    # CD02 -------------------------------------------------------------------
    def test_cd02_username_from_uid_profile(self):
        rep = self._det().detect()
        by = {c["user_id"]: c for c in rep["cases"]}
        # Der neue Fall traegt den Namen aus uid_profile (nicht erraten).
        self.assertEqual(by[19]["username"], "boarder19")
        # Der vermisste Fall behaelt den Namen aus der Fallakte.
        self.assertEqual(by[20]["username"], "boarder20")
        # Der unlesbare nennt den Grund.
        self.assertIsNotNone(by[21]["detail"])

    # CD03 -------------------------------------------------------------------
    def test_cd03_workstate_is_not_criterion(self):
        rep = self._det().detect()
        by = {c["user_id"]: c for c in rep["cases"]}
        # 18 hat evidence + assets ...
        self.assertTrue(by[18]["has_evidence_db"])
        self.assertTrue(by[18]["has_assets_db"])
        # ... 19 nicht — bleibt aber ein vollwertiger (neuer) Fall.
        self.assertFalse(by[19]["has_evidence_db"])
        self.assertEqual(by[19]["status"], "neu")

    # CD04 -------------------------------------------------------------------
    def test_cd04_import_audited(self):
        imp = CaseImporter(self.con, self._det())
        res = imp.import_cases(actor_id=1, all_new=True)
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["imported"][0]["user_id"], 19)
        self.assertEqual(res["imported"][0]["username"], "boarder19")
        # Der Beleg liegt im audit_log.
        self.assertGreaterEqual(self._audit_count("case_created", 19), 1)
        # Danach ist der Fall 'ok'.
        by = {c["user_id"]: c["status"] for c in self._det().detect()["cases"]}
        self.assertEqual(by[19], "ok")

    # CD05 -------------------------------------------------------------------
    def test_cd05_import_skips_and_reports(self):
        imp = CaseImporter(self.con, self._det())
        # 18 ist bereits erfasst, 20 vermisst, 21 unlesbar, 99 gibt es nicht.
        res = imp.import_cases(actor_id=1, user_ids=[18, 20, 21, 99])
        self.assertEqual(res["count"], 0)
        skipped = {s["user_id"] for s in res["skipped"]}
        self.assertEqual(skipped, {18, 20, 21, 99})   # nichts verschwiegen

    # CD06 -------------------------------------------------------------------
    def test_cd06_endpoints(self):
        app = ManagementApp(self._db, evidence_dir=self._edir,
                            forensic_dir=self._fdir, assets_dir=self._adir)
        r = app.dispatch(1, "/api/cases/detect")
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["counts"]["neu"], 1)

        # person 2 hat keine Rolle -> 403
        self.assertEqual(app.dispatch(2, "/api/cases/detect").status, 403)

        # Aufnehmen (auditiert).
        w = app.dispatch_write(1, "/api/cases/import", {"user_ids": [19]})
        self.assertEqual(w.status, 200)
        dw = json.loads(w.body.decode("utf-8"))
        self.assertEqual(dw["count"], 1)
        self.assertGreaterEqual(self._audit_count("case_created", 19), 1)

        # Leere Auswahl -> 400.
        self.assertEqual(
            app.dispatch_write(1, "/api/cases/import", {}).status, 400)

    # CD07 -------------------------------------------------------------------
    def test_cd07_cli(self):
        argv = ["--coordinator-db", self._db,
                "--forensic-dir", self._fdir,
                "--evidence-dir", self._edir,
                "--assets-dir", self._adir]

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = case_detect.main(argv)
        # 'vermisst' und 'unlesbar' vorhanden -> Pruefbedarf.
        self.assertEqual(rc, 2)
        self.assertIn("NEU", out.getvalue())
        self.assertIn("VERMISST", out.getvalue())
        self.assertIn("NICHT veraendert", err.getvalue())  # kein Eingriff

        # --auto ohne --actor -> Fehler (der Beleg braucht einen Handelnden).
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(case_detect.main(argv + ["--auto"]), 1)

        # --auto mit --actor nimmt den neuen Fall auf.
        out2 = io.StringIO()
        with redirect_stdout(out2), redirect_stderr(io.StringIO()):
            case_detect.main(argv + ["--auto", "--actor", "h0a2898"])
        self.assertIn("AUFNAHME", out2.getvalue())
        self.assertGreaterEqual(self._audit_count("case_created", 19), 1)


if __name__ == "__main__":
    unittest.main()

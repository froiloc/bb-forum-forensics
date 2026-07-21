# =============================================================================
# tests/test_report_as_template_draft_api.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — Build 475: "Bericht als Vorlage uebernehmen"
# =============================================================================
# Deckt GET /api/report/as-template-draft ab (Harness-Paritaet zu
# test_report_render_management.py — echte evidence_<uid>.db, KEIN Mock):
#
#   AD01 — 200, ok=true, Bloecke vorhanden; Platzhalter-TOKEN erhalten.
#   AD02 — ohne reports.review/approve -> 403.
#   AD03 — READ-ONLY-Integritaet: MD5 der evidence_<uid>.db vor == nach.
#   AD04 — unbekannte uid -> 404 (evidence_not_found).
#   AD05 — fehlender subject_id -> 400.
#   AD06 — Scope 'eigene': fremder Fall -> 403; eigener Fall -> 200.
#   AD07 — Leck-Kontrolle: KEINE aufgeloesten Platzhalter-Werte, KEINE
#          evidence_ids in der Antwort; evidence-Wrapper bleibt; Befunde da.
#
# Version: v0.8.475 · Build: 475 · 2026-07-21
# =============================================================================

import hashlib
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
from db.evidence_db import EvidenceDb

# Fallbezogene Nutzlast, die NIE in der Draft-Antwort auftauchen darf.
_SECRET_VALUE = "GEHEIM_Musterstadt_4711"

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


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _seed_evidence(path: Path) -> None:
    """evidence_<uid>.db mit einem Bericht: Platzhalter-Block (mit fallbezogenem
    Wert in placeholder_values_json) + evidence-Block (mit evidence_ids)."""
    con = sqlite3.connect(str(path))
    try:
        EvidenceDb(con, db_path=str(path))
        con.execute(
            "INSERT INTO reports (id, report_type, sequence_nr, title, "
            "created_by, created_at, status) "
            "VALUES (1,'final',1,'Hauptbericht','inv',1000,'submitted')")
        con.execute(
            "INSERT INTO report_blocks (block_id, report_id, author, created_at,"
            " updated_at, block_type, block_data, placeholder_values_json, "
            "module_id) VALUES (?,?,?,?,?,?,?,?,?)",
            ("b1", 1, "inv", 1000, 1000, "paragraph",
             json.dumps({"text": "Ort {{o:ort|}}, Zeit {{a:tatzeit}}."}),
             json.dumps({"ort": _SECRET_VALUE}), None))
        con.execute(
            "INSERT INTO report_blocks (block_id, report_id, author, created_at,"
            " updated_at, block_type, block_data, placeholder_values_json, "
            "module_id) VALUES (?,?,?,?,?,?,?,?,?)",
            ("b2", 1, "inv", 1000, 1000, "evidence",
             json.dumps({"evidence_ids": [10, 11], "text": "Beweislage"}),
             None, None))
        con.execute(
            "INSERT INTO report_block_order (block_id, sort_index, "
            "last_modified_by, last_modified_at) VALUES ('b1', 0, 'inv', 1000)")
        con.execute(
            "INSERT INTO report_block_order (block_id, sort_index, "
            "last_modified_by, last_modified_at) VALUES ('b2', 1, 'inv', 1000)")
        con.commit()
    finally:
        con.close()


class ReportAsTemplateDraftApiTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=delete")
        con.execute(_PERSON)
        now = int(time.time())
        for pid, un, disp in ((1, "h001", "Lektor"),
                              (2, "h002", "Fremd"),
                              (3, "h003", "Ermittler")):
            con.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?, ?, ?, 1, 0, 0, ?)", (pid, un, disp, now))
        con.execute(_OLD_SCRAPE_JOBS)
        con.execute("INSERT INTO scrape_jobs (user_id, username, created_at) "
                    "VALUES (700, 'b700', ?)", (now,))
        con.execute("INSERT INTO scrape_jobs (user_id, username, created_at) "
                    "VALUES (701, 'b701', ?)", (now,))
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con

        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.rbac = RbacRepo(self.con, self.writer)
        self.cases = CasesRepo(self.con, self.writer)

        # Person 1 = Lektor (reports.review, Scope 'alle').
        self.rbac.grant("lector", "reports.review", scope="alle", actor_id=1)
        self.rbac.assign_role(1, "lector", actor_id=1)
        # Person 3 = Ermittler mit reports.review NUR fuer eigene Faelle.
        self.rbac.grant("investigator", "reports.review", scope="eigene",
                        actor_id=1)
        self.rbac.assign_role(3, "investigator", actor_id=1)

        self.cases.create_case(700, "b700", actor_id=1)
        self.cases.create_case(701, "b701", actor_id=1)
        self.cases.assign(700, 3, actor_id=1)

        self._evidence_dir = os.path.join(self._tmp, "evidence")
        os.makedirs(self._evidence_dir, exist_ok=True)
        self._ev700 = Path(self._evidence_dir) / "evidence_700.db"
        _seed_evidence(self._ev700)

        self._forensic_dir = os.path.join(self._tmp, "forensic")
        self._assets_dir = os.path.join(self._tmp, "assets")
        os.makedirs(self._forensic_dir, exist_ok=True)
        os.makedirs(self._assets_dir, exist_ok=True)
        self._templates_db = os.path.join(self._tmp, "templates.db")

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

    def _app(self) -> ManagementApp:
        return ManagementApp(
            self._db,
            evidence_dir=self._evidence_dir,
            forensic_dir=self._forensic_dir,
            assets_dir=self._assets_dir,
            templates_db=self._templates_db,
            default_db=os.path.join(self._tmp, "default.db"))

    _PATH = "/api/report/as-template-draft"

    # AD01 ------------------------------------------------------------------
    def test_ad01_ok(self):
        r = self._app().dispatch(1, self._PATH, {"subject_id": ["700"]})
        self.assertEqual(r.status, 200)
        body = json.loads(r.body.decode("utf-8"))
        self.assertTrue(body["ok"])
        blocks = body["draft"]["blocks"]
        self.assertEqual(len(blocks), 2)
        # Platzhalter-TOKEN muessen erhalten sein (neutraler Struktur-Teil).
        self.assertIn("{{o:ort|}}", blocks[0]["block_data"]["text"])
        self.assertIn("{{a:tatzeit}}", blocks[0]["block_data"]["text"])

    # AD02 ------------------------------------------------------------------
    def test_ad02_forbidden_without_cap(self):
        r = self._app().dispatch(2, self._PATH, {"subject_id": ["700"]})
        self.assertEqual(r.status, 403)

    # AD03 ------------------------------------------------------------------
    def test_ad03_readonly_integrity(self):
        before = _md5(self._ev700)
        r = self._app().dispatch(1, self._PATH, {"subject_id": ["700"]})
        self.assertEqual(r.status, 200)
        after = _md5(self._ev700)
        self.assertEqual(before, after,
                         "evidence_<uid>.db darf durch den Draft NICHT "
                         "veraendert werden (Migrationsvorbehalt).")
        self.assertFalse(
            (Path(self._evidence_dir) / "evidence_700.db-wal").exists())

    # AD04 ------------------------------------------------------------------
    def test_ad04_unknown_uid_404(self):
        r = self._app().dispatch(1, self._PATH, {"subject_id": ["999"]})
        self.assertEqual(r.status, 404)
        self.assertEqual(json.loads(r.body.decode("utf-8"))["error"],
                         "evidence_not_found")

    # AD05 ------------------------------------------------------------------
    def test_ad05_missing_subject_id_400(self):
        r = self._app().dispatch(1, self._PATH, {})
        self.assertEqual(r.status, 400)

    # AD06 ------------------------------------------------------------------
    def test_ad06_scope_eigene(self):
        r_ok = self._app().dispatch(3, self._PATH, {"subject_id": ["700"]})
        self.assertEqual(r_ok.status, 200)
        r_no = self._app().dispatch(3, self._PATH, {"subject_id": ["701"]})
        self.assertEqual(r_no.status, 403)

    # AD07 ------------------------------------------------------------------
    def test_ad07_no_case_data_leak(self):
        r = self._app().dispatch(1, self._PATH, {"subject_id": ["700"]})
        self.assertEqual(r.status, 200)
        raw = r.body.decode("utf-8")
        body = json.loads(raw)
        # Der fallbezogene Platzhalter-WERT darf NIRGENDS in der Antwort sein.
        self.assertNotIn(_SECRET_VALUE, raw)
        # evidence-Wrapper bleibt, aber evidence_ids sind geleert.
        ev = [b for b in body["draft"]["blocks"]
              if b["block_type"] == "evidence"]
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["block_data"]["evidence_ids"], [])
        # Befunde muessen die Entfernungen dokumentieren (GR1).
        actions = [f["action"] for f in body["findings"]]
        self.assertIn("placeholder_values_cleared", actions)
        self.assertIn("evidence_ids_cleared", actions)


if __name__ == "__main__":
    unittest.main()

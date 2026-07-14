# =============================================================================
# tests/test_report_render_management.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — SF-1 (Build 410): read-only Berichts-Vorschau
# =============================================================================
# Deckt GET /api/report/render ab:
#
#   RR01 — 200 text/html, Berichtstext enthalten (echte EvidenceDb-Fixture,
#          KEIN Mock an der Schnittstelle; Bauplan Build 397 §5).
#   RR02 — ohne reports.review/approve -> 403.
#   RR03 — READ-ONLY-Integritaet: MD5 der evidence_<uid>.db vor == nach dem
#          Render (das Management schreibt NICHT in die evidence-DB).
#   RR04 — unbekannte uid -> 404 (evidence_not_found), kein stiller Fehlschlag.
#   RR05 — fehlender user_id -> 400.
#   RR06 — Scope 'eigene': fremder Fall -> 403; eigener Fall -> 200.
#
# Version: v0.7.410 · Build: 410 · 2026-07-14
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

# Distinktiver Text, den wir im gerenderten HTML wiederfinden muessen.
_PROBE = "PARITAETSPROBE_7Q2X"

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


def _seed_evidence(path: Path, uid: int) -> None:
    """Legt eine echte evidence_<uid>.db mit einem einfachen Bericht an."""
    con = sqlite3.connect(str(path))
    try:
        EvidenceDb(con, db_path=str(path))          # setzt das volle Schema auf
        con.execute(
            "INSERT INTO reports (id, report_type, sequence_nr, title, "
            "created_by, created_at, status) "
            "VALUES (1,'final',1,'Hauptbericht','inv',1000,'submitted')"
        )
        con.execute(
            "INSERT INTO report_blocks (block_id, report_id, author, created_at,"
            " updated_at, block_type, block_data, placeholder_values_json, "
            "module_id) VALUES (?,?,?,?,?,?,?,?,?)",
            ("b1", 1, "inv", 1000, 1000, "paragraph",
             json.dumps({"text": _PROBE}), None, None),
        )
        con.execute(
            "INSERT INTO report_block_order (block_id, sort_index, "
            "last_modified_by, last_modified_at) VALUES ('b1', 0, 'inv', 1000)"
        )
        con.commit()
    finally:
        con.close()


class ReportRenderManagementTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=delete")   # Build 408/409: kein WAL
        con.execute(_PERSON)
        now = int(time.time())
        for pid, un, disp, sup in ((1, "h001", "Lektor", 0),
                                   (2, "h002", "Fremd", 0),
                                   (3, "h003", "Ermittler", 0)):
            con.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?, ?, ?, 1, ?, 0, ?)", (pid, un, disp, sup, now))
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

        # Faelle 700 (Person 3 zugewiesen) und 701 (unzugewiesen).
        self.cases.create_case(700, "b700", actor_id=1)
        self.cases.create_case(701, "b701", actor_id=1)
        self.cases.assign(700, 3, actor_id=1)

        # evidence_700.db real anlegen.
        self._evidence_dir = os.path.join(self._tmp, "evidence")
        os.makedirs(self._evidence_dir, exist_ok=True)
        self._ev700 = Path(self._evidence_dir) / "evidence_700.db"
        _seed_evidence(self._ev700, 700)

        # leere (nicht existierende) Verzeichnisse fuer forensic/assets +
        # nicht vorhandene templates.db -> Platzhalter bleiben unaufgeloest,
        # fuer diesen Bericht ohne Platzhalter unerheblich.
        self._forensic_dir = os.path.join(self._tmp, "forensic")
        self._assets_dir = os.path.join(self._tmp, "assets")
        os.makedirs(self._forensic_dir, exist_ok=True)
        os.makedirs(self._assets_dir, exist_ok=True)
        self._templates_db = os.path.join(self._tmp, "templates.db")  # existiert nicht

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
            default_db=os.path.join(self._tmp, "default.db"),  # existiert nicht
        )

    # RR01 -------------------------------------------------------------------
    def test_rr01_render_ok(self):
        r = self._app().dispatch(1, "/api/report/render", {"user_id": ["700"]})
        self.assertEqual(r.status, 200)
        self.assertIn("text/html", r.content_type)
        self.assertIn(_PROBE, r.body.decode("utf-8"))

    # RR02 -------------------------------------------------------------------
    def test_rr02_forbidden_without_cap(self):
        r = self._app().dispatch(2, "/api/report/render", {"user_id": ["700"]})
        self.assertEqual(r.status, 403)

    # RR03 -------------------------------------------------------------------
    def test_rr03_readonly_integrity(self):
        before = _md5(self._ev700)
        r = self._app().dispatch(1, "/api/report/render", {"user_id": ["700"]})
        self.assertEqual(r.status, 200)
        after = _md5(self._ev700)
        self.assertEqual(before, after,
                         "evidence_<uid>.db darf durch die Vorschau NICHT "
                         "veraendert werden (Migrationsvorbehalt).")
        # Es duerfen auch keine -wal/-shm Seitendateien entstanden sein.
        self.assertFalse((Path(self._evidence_dir) / "evidence_700.db-wal").exists())

    # RR04 -------------------------------------------------------------------
    def test_rr04_unknown_uid_404(self):
        r = self._app().dispatch(1, "/api/report/render", {"user_id": ["999"]})
        self.assertEqual(r.status, 404)
        self.assertEqual(json.loads(r.body.decode("utf-8"))["error"],
                         "evidence_not_found")

    # RR05 -------------------------------------------------------------------
    def test_rr05_missing_user_id_400(self):
        r = self._app().dispatch(1, "/api/report/render", {})
        self.assertEqual(r.status, 400)

    # RR06 -------------------------------------------------------------------
    def test_rr06_scope_eigene(self):
        # Person 3 (Scope 'eigene') darf Fall 700 (zugewiesen) -> 200 ...
        r_ok = self._app().dispatch(3, "/api/report/render", {"user_id": ["700"]})
        self.assertEqual(r_ok.status, 200)
        # ... aber NICHT Fall 701 (nicht zugewiesen) -> 403.
        r_no = self._app().dispatch(3, "/api/report/render", {"user_id": ["701"]})
        self.assertEqual(r_no.status, 403)


if __name__ == "__main__":
    unittest.main()

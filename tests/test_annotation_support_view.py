# =============================================================================
# tests/test_annotation_support_view.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — SF-2 (Build 411): Annotations-Support-View
# =============================================================================
# Deckt GET /api/report/annotations ab:
#
#   SA01 — 200 JSON: verankerte Annotation erscheint (category/text/post_id) und
#          der Forenkontext (topic_id/forum_id) wird aus fdb.post_aliases
#          aufgeloest. Echte evidence_/forensic_-Fixtures (kein Mock).
#   SA02 — ohne reports.review/approve -> 403.
#   SA03 — READ-ONLY-Integritaet: MD5 der evidence_<uid>.db vor == nach.
#   SA04 — unbekannte uid -> 404 (evidence_not_found).
#   SA05 — Scope 'eigene': eigener Fall 200, fremder Fall 403.
#   SA06 — flaches Lese-Audit: nach dem Zugriff genau ein
#          'report_annotations_viewed' im coordinator.db-audit_log.
#
# Version: v0.7.411 · Build: 411 · 2026-07-14
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

_BELEG = "Beleg-Text_ABC_7Q2X"

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
    """evidence_<uid>.db mit Bericht + Block + Annotation + Anker (post_id=42)."""
    con = sqlite3.connect(str(path))
    try:
        EvidenceDb(con, db_path=str(path))
        con.execute(
            "INSERT INTO reports (id, report_type, sequence_nr, title, "
            "created_by, created_at, status) "
            "VALUES (1,'final',1,'Hauptbericht','inv',1000,'submitted')"
        )
        con.execute(
            "INSERT INTO report_blocks (block_id, report_id, author, created_at,"
            " updated_at, block_type, block_data, placeholder_values_json, "
            "module_id) VALUES ('b1',1,'inv',1000,1000,'evidence','{}',NULL,NULL)"
        )
        con.execute(
            "INSERT INTO annotations (id, page_url, element_id, category, text, "
            "ts, investigator_id, selection_json, post_id, created_by, "
            "version_nr) VALUES (10,'viewtopic.php?id=99','el1','CAT_PERSON',?,"
            "1500, 7, NULL, 42, 'inv', 1)",
            (_BELEG,),
        )
        con.execute(
            "INSERT INTO report_anchors (block_id, annotation_id, anchor_text, "
            "created_at) VALUES ('b1', 10, 'siehe Beleg', 1500)"
        )
        con.commit()
    finally:
        con.close()


def _seed_forensic(path: Path) -> None:
    """forensic_<uid>.db mit post_aliases: post_id 42 -> topic 7, forum 3."""
    con = sqlite3.connect(str(path))
    try:
        con.execute(
            "CREATE TABLE post_aliases (post_id INTEGER PRIMARY KEY, "
            "topic_id INTEGER NOT NULL, forum_id INTEGER NOT NULL)"
        )
        con.execute("INSERT INTO post_aliases (post_id, topic_id, forum_id) "
                    "VALUES (42, 7, 3)")
        con.commit()
    finally:
        con.close()


class AnnotationSupportViewTests(unittest.TestCase):

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
        for uid in (700, 701):
            con.execute("INSERT INTO scrape_jobs (user_id, username, "
                        "created_at) VALUES (?, ?, ?)", (uid, "b%d" % uid, now))
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con

        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.rbac = RbacRepo(self.con, self.writer)
        self.cases = CasesRepo(self.con, self.writer)

        self.rbac.grant("lector", "reports.review", scope="alle", actor_id=1)
        self.rbac.assign_role(1, "lector", actor_id=1)
        self.rbac.grant("investigator", "reports.review", scope="eigene",
                        actor_id=1)
        self.rbac.assign_role(3, "investigator", actor_id=1)

        self.cases.create_case(700, "b700", actor_id=1)
        self.cases.create_case(701, "b701", actor_id=1)
        self.cases.assign(700, 3, actor_id=1)

        self._evidence_dir = os.path.join(self._tmp, "evidence")
        self._forensic_dir = os.path.join(self._tmp, "forensic")
        self._assets_dir = os.path.join(self._tmp, "assets")
        for d in (self._evidence_dir, self._forensic_dir, self._assets_dir):
            os.makedirs(d, exist_ok=True)
        self._ev700 = Path(self._evidence_dir) / "evidence_700.db"
        _seed_evidence(self._ev700)
        _seed_forensic(Path(self._forensic_dir) / "forensic_700.db")
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
            default_db=os.path.join(self._tmp, "default.db"),
        )

    def _audit_count(self, event_type: str) -> int:
        c = sqlite3.connect("file:%s?mode=ro" % self._db, uri=True)
        try:
            return c.execute("SELECT COUNT(*) FROM audit_log WHERE "
                             "event_type = ?", (event_type,)).fetchone()[0]
        finally:
            c.close()

    # SA01 -------------------------------------------------------------------
    def test_sa01_annotations_with_forum_context(self):
        r = self._app().dispatch(1, "/api/report/annotations",
                                 {"user_id": ["700"]})
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["anchor_count"], 1)
        it = d["items"][0]
        self.assertEqual(it["block_type"], "evidence")
        self.assertEqual(it["category"], "CAT_PERSON")
        self.assertEqual(it["text"], _BELEG)
        self.assertEqual(it["post_id"], 42)
        self.assertEqual(it["topic_id"], 7)     # aus fdb.post_aliases
        self.assertEqual(it["forum_id"], 3)
        self.assertFalse(it["missing"])
        self.assertFalse(it["deleted"])

    # SA02 -------------------------------------------------------------------
    def test_sa02_forbidden_without_cap(self):
        r = self._app().dispatch(2, "/api/report/annotations",
                                 {"user_id": ["700"]})
        self.assertEqual(r.status, 403)

    # SA03 -------------------------------------------------------------------
    def test_sa03_readonly_integrity(self):
        before = _md5(self._ev700)
        r = self._app().dispatch(1, "/api/report/annotations",
                                 {"user_id": ["700"]})
        self.assertEqual(r.status, 200)
        self.assertEqual(before, _md5(self._ev700))
        self.assertFalse((Path(self._evidence_dir) / "evidence_700.db-wal").exists())

    # SA04 -------------------------------------------------------------------
    def test_sa04_unknown_uid_404(self):
        r = self._app().dispatch(1, "/api/report/annotations",
                                 {"user_id": ["999"]})
        self.assertEqual(r.status, 404)
        self.assertEqual(json.loads(r.body.decode("utf-8"))["error"],
                         "evidence_not_found")

    # SA05 -------------------------------------------------------------------
    def test_sa05_scope_eigene(self):
        ok = self._app().dispatch(3, "/api/report/annotations",
                                  {"user_id": ["700"]})
        self.assertEqual(ok.status, 200)
        no = self._app().dispatch(3, "/api/report/annotations",
                                  {"user_id": ["701"]})
        self.assertEqual(no.status, 403)

    # SA06 -------------------------------------------------------------------
    def test_sa06_read_access_audited(self):
        self.assertEqual(self._audit_count("report_annotations_viewed"), 0)
        r = self._app().dispatch(1, "/api/report/annotations",
                                 {"user_id": ["700"]})
        self.assertEqual(r.status, 200)
        self.assertEqual(self._audit_count("report_annotations_viewed"), 1)


if __name__ == "__main__":
    unittest.main()

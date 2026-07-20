# =============================================================================
# tests/test_review_comments.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — SF-3 (Build 412): Kommentar-Bruecke (Addendum-Dateien)
# =============================================================================
# Deckt POST /api/report/comment, POST /api/report/comment/resolve und
# GET /api/report/comments ab:
#
#   RC01 — Kommentar anlegen -> 200 (comment_id, status pending, role 'lector');
#          Addendum-Datei liegt am gebucketeten Pfad; block_sha256 gesetzt.
#   RC02 — GET /comments (Union) zeigt den Kommentar.
#   RC03 — Union ueber ZWEI Prueferinnen (Lektor + Supervisor), Rollen korrekt.
#   RC04 — ohne reports.review/approve -> 403.
#   RC05 — eigenen Kommentar aufloesen -> status 'addressed'; Re-Read bestaetigt.
#   RC06 — READ-ONLY-Integritaet: MD5 der evidence_<uid>.db vor == nach.
#   RC07 — Audit: 'review_comment_added' + 'review_comment_resolved' im audit_log.
#   RC08 — resolve unbekannte comment_id -> 404.
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
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
from db.review_addendum_db import addendum_path

_BLOCK_DATA = '{"text": "Absatz X"}'

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
            "module_id) VALUES ('b1',1,'inv',1000,1000,'paragraph',?,NULL,NULL)",
            (_BLOCK_DATA,),
        )
        con.commit()
    finally:
        con.close()


class ReviewCommentsTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=delete")
        con.execute(_PERSON)
        now = int(time.time())
        # 1 = Lektor, 4 = Supervisor/Chefin, 2 = ohne Recht.
        for pid, un, disp, sup in ((1, "h001", "Lektor", 0),
                                   (2, "h002", "Fremd", 0),
                                   (4, "h004", "Chefin", 1)):
            con.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?, ?, ?, 1, ?, 0, ?)", (pid, un, disp, sup, now))
        con.execute(_OLD_SCRAPE_JOBS)
        con.execute("INSERT INTO scrape_jobs (user_id, username, created_at) "
                    "VALUES (700, 'b700', ?)", (now,))
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con

        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.rbac = RbacRepo(self.con, self.writer)
        self.cases = CasesRepo(self.con, self.writer)
        self.rbac.grant("lector", "reports.review", scope="alle", actor_id=1)
        self.rbac.assign_role(1, "lector", actor_id=1)
        self.rbac.grant("supervisor", "reports.approve", scope="alle",
                        actor_id=1)
        self.rbac.assign_role(4, "supervisor", actor_id=1)
        self.cases.create_case(700, "b700", actor_id=1)

        self._evidence_dir = os.path.join(self._tmp, "evidence")
        os.makedirs(self._evidence_dir, exist_ok=True)
        self._ev700 = Path(self._evidence_dir) / "evidence_700.db"
        _seed_evidence(self._ev700)

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
        return ManagementApp(self._db, evidence_dir=self._evidence_dir,
                             forensic_dir=self._tmp, assets_dir=self._tmp,
                             templates_db=os.path.join(self._tmp, "templates.db"))

    def _create(self, person, **kw):
        body = {"subject_id": 700, "report_id": 1}
        body.update(kw)
        return self._app().dispatch_write(person, "/api/report/comment", body)

    def _audit_count(self, event_type: str) -> int:
        c = sqlite3.connect("file:%s?mode=ro" % self._db, uri=True)
        try:
            return c.execute("SELECT COUNT(*) FROM audit_log WHERE "
                             "event_type = ?", (event_type,)).fetchone()[0]
        finally:
            c.close()

    # RC01 -------------------------------------------------------------------
    def test_rc01_create(self):
        r = self._create(1, block_id="b1", comment_text="Bitte praezisieren")
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertTrue(d["comment_id"])
        self.assertEqual(d["status"], "pending")
        self.assertEqual(d["reviewer_role"], "lector")
        # Addendum-Datei liegt am gebucketeten Pfad.
        p = addendum_path(self._evidence_dir, 700, 1)
        self.assertTrue(p.exists(), "Addendum-Datei muss angelegt sein: %s" % p)
        # block_sha256 wurde erfasst.
        c = sqlite3.connect("file:%s?mode=ro" % p.resolve(), uri=True)
        try:
            row = c.execute("SELECT block_sha256 FROM review_comments "
                            "WHERE comment_id = ?", (d["comment_id"],)).fetchone()
        finally:
            c.close()
        self.assertEqual(row[0],
                         hashlib.sha256(_BLOCK_DATA.encode("utf-8")).hexdigest())

    # RC02 -------------------------------------------------------------------
    def test_rc02_union_read(self):
        self._create(1, block_id="b1", comment_text="Hinweis A")
        r = self._app().dispatch(1, "/api/report/comments", {"subject_id": ["700"]})
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["count"], 1)
        self.assertEqual(d["comments"][0]["comment_text"], "Hinweis A")

    # RC03 -------------------------------------------------------------------
    def test_rc03_union_two_reviewers(self):
        self._create(1, block_id="b1", comment_text="Lektor-Hinweis")
        self._create(4, block_id="b1", comment_text="Chef-Hinweis")
        r = self._app().dispatch(4, "/api/report/comments", {"subject_id": ["700"]})
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["count"], 2)
        roles = {c["reviewer_role"] for c in d["comments"]}
        self.assertEqual(roles, {"lector", "supervisor"})

    # RC04 -------------------------------------------------------------------
    def test_rc04_forbidden(self):
        r = self._create(2, block_id="b1", comment_text="darf nicht")
        self.assertEqual(r.status, 403)

    # RC05 -------------------------------------------------------------------
    def test_rc05_resolve_own(self):
        cid = json.loads(self._create(1, block_id="b1",
                                      comment_text="X").body.decode())["comment_id"]
        r = self._app().dispatch_write(1, "/api/report/comment/resolve",
                                       {"subject_id": 700, "comment_id": cid,
                                        "status": "addressed"})
        self.assertEqual(r.status, 200)
        rd = self._app().dispatch(1, "/api/report/comments", {"subject_id": ["700"]})
        got = json.loads(rd.body.decode("utf-8"))["comments"][0]
        self.assertEqual(got["status"], "addressed")
        self.assertIsNotNone(got["resolved_at"])

    # RC06 -------------------------------------------------------------------
    def test_rc06_evidence_readonly(self):
        before = _md5(self._ev700)
        self._create(1, block_id="b1", comment_text="X")
        self.assertEqual(before, _md5(self._ev700))

    # RC07 -------------------------------------------------------------------
    def test_rc07_audited(self):
        self.assertEqual(self._audit_count("review_comment_added"), 0)
        cid = json.loads(self._create(1, block_id="b1",
                                      comment_text="X").body.decode())["comment_id"]
        self.assertEqual(self._audit_count("review_comment_added"), 1)
        self._app().dispatch_write(1, "/api/report/comment/resolve",
                                   {"subject_id": 700, "comment_id": cid,
                                    "status": "dismissed"})
        self.assertEqual(self._audit_count("review_comment_resolved"), 1)

    # RC08 -------------------------------------------------------------------
    def test_rc08_resolve_unknown_404(self):
        r = self._app().dispatch_write(1, "/api/report/comment/resolve",
                                       {"subject_id": 700, "comment_id": "deadbeef",
                                        "status": "addressed"})
        self.assertEqual(r.status, 404)


if __name__ == "__main__":
    unittest.main()

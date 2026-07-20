# =============================================================================
# tests/test_report_sealing.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Berichts-Versiegelung
# =============================================================================
# Testsuite fuer Build 377: ReportSealer + ApprovedReportsDb + ApprovalService
# + /api/report/approve + /api/report/verify.
#
# SE01 — Hash ist DETERMINISTISCH (zweimal berechnet -> identisch) und haengt
#        NICHT vom Status ab (der aendert sich durch die Freigabe selbst).
# SE02 — Hash aendert sich bei Inhaltsaenderung (Block-Text).
# SE03 — Hash aendert sich bei REIHENFOLGE-Aenderung der Bloecke (die
#        Reihenfolge ist Teil des Berichts).
# SE04 — Freigabe: evidence-Status wird gesetzt, report_approvals geschrieben,
#        zentrales Siegel abgelegt, coordinator-Beleg erzeugt.
# SE05 — Vorbedingung: Freigabe nur aus 'submitted'; 'final' nur aus 'approved'.
# SE06 — MANIPULATIONSNACHWEIS: nach direkter Aenderung der evidence-DB meldet
#        verify() eine ABWEICHUNG. (Der Kern des Siegels.)
# SE07 — Endpunkte: 403 ohne reports.approve; 403 bei Scope 'eigene';
#        Erfolg via dispatch_write; verify via dispatch.
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
from management.cases.cases_repo import CasesRepo
from management.reports.report_sealer import ReportSealer
from management.reports.approved_reports_db import ApprovedReportsDb
from management.reports.approval_service import ApprovalService, ApprovalError
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

# Nachbau der relevanten evidence-Tabellen (db/evidence_db.py).
_EV_DDL = [
    """CREATE TABLE "reports" (
        "id" INTEGER,
        "report_type" TEXT NOT NULL CHECK("report_type" IN ('interim','final','addendum')),
        "sequence_nr" INTEGER NOT NULL DEFAULT 1,
        "title" TEXT NOT NULL,
        "created_by" TEXT NOT NULL,
        "created_at" INTEGER NOT NULL,
        "status" TEXT NOT NULL DEFAULT 'draft'
            CHECK("status" IN ('draft','submitted','approved','final')),
        PRIMARY KEY("id" AUTOINCREMENT))""",
    """CREATE TABLE "report_blocks" (
        "block_id" TEXT NOT NULL, "report_id" INTEGER NOT NULL,
        "author" TEXT NOT NULL, "created_at" INTEGER NOT NULL,
        "updated_at" INTEGER NOT NULL, "block_type" TEXT NOT NULL,
        "block_data" TEXT NOT NULL DEFAULT '{}',
        "placeholder_values_json" TEXT, "module_id" INTEGER,
        PRIMARY KEY("block_id"))""",
    """CREATE TABLE "report_block_order" (
        "block_id" TEXT NOT NULL, "sort_index" INTEGER NOT NULL,
        "last_modified_by" TEXT NOT NULL, "last_modified_at" INTEGER NOT NULL,
        PRIMARY KEY("block_id"))""",
    """CREATE TABLE "report_anchors" (
        "id" INTEGER, "block_id" TEXT NOT NULL, "annotation_id" INTEGER NOT NULL,
        "anchor_text" TEXT NOT NULL, "created_at" INTEGER NOT NULL,
        PRIMARY KEY("id" AUTOINCREMENT))""",
    """CREATE TABLE "report_comments" (
        "id" INTEGER, "block_id" TEXT NOT NULL, "author" TEXT NOT NULL,
        "comment" TEXT NOT NULL, "created_at" INTEGER NOT NULL,
        PRIMARY KEY("id" AUTOINCREMENT))""",
    """CREATE TABLE "report_approvals" (
        "id" INTEGER, "report_id" INTEGER NOT NULL,
        "approved_by" TEXT NOT NULL, "approved_at" INTEGER NOT NULL,
        "note" TEXT DEFAULT NULL, "is_final" INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY("id" AUTOINCREMENT))""",
]


def _make_evidence(path, status="submitted"):
    con = sqlite3.connect(path)
    con.isolation_level = None
    con.execute("PRAGMA journal_mode=WAL")
    for ddl in _EV_DDL:
        con.execute(ddl)
    con.execute(
        'INSERT INTO reports (id, report_type, sequence_nr, title, created_by, '
        'created_at, status) VALUES (1, "interim", 1, "Zwischenbericht", '
        '"h002", 1783000000, ?)', (status,))
    for i, (bid, text) in enumerate((("b1", "Erster Absatz"),
                                     ("b2", "Zweiter Absatz")), start=1):
        con.execute(
            'INSERT INTO report_blocks (block_id, report_id, author, '
            'created_at, updated_at, block_type, block_data) '
            'VALUES (?, 1, "h002", 1783000000, 1783000000, "paragraph", ?)',
            (bid, json.dumps({"text": text})))
        con.execute(
            'INSERT INTO report_block_order (block_id, sort_index, '
            'last_modified_by, last_modified_at) VALUES (?, ?, "h002", ?)',
            (bid, i, 1783000000))
    con.execute(
        'INSERT INTO report_anchors (block_id, annotation_id, anchor_text, '
        'created_at) VALUES ("b1", 42, "Belegstelle", 1783000000)')
    # Kommentar: darf das Siegel NICHT beeinflussen.
    con.execute(
        'INSERT INTO report_comments (block_id, author, comment, created_at) '
        'VALUES ("b1", "h0a2898", "Bitte praezisieren", 1783000000)')
    con.close()


class ReportSealingTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._ev = os.path.join(self._tmp, "evidence")
        os.makedirs(self._ev)
        self._db = os.path.join(self._tmp, "coordinator.db")
        self._approved = os.path.join(self._tmp, "approved_reports.db")
        self._evfile = os.path.join(self._ev, "evidence_18.db")

        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        for pid, un, disp, sup in ((1, "h0a2898", "Chefin", 1),
                                   (2, "h002", "Mueller", 0)):
            con.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?, ?, ?, 1, ?, 0, ?)", (pid, un, disp, sup,
                                                 int(time.time())))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.con = con

        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.rbac = RbacRepo(self.con, self.writer)
        self.cases = CasesRepo(self.con, self.writer)
        self.rbac.grant("supervisor", "reports.approve", scope="alle",
                        actor_id=1)
        self.rbac.grant("investigator", "reports.approve", scope="eigene",
                        actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)
        self.cases.create_case(18, "b18", actor_id=1)
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        _make_evidence(self._evfile, status="submitted")

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

    def _svc(self):
        return ApprovalService(self.con, self._ev, self._approved)

    def _ev_con(self):
        c = sqlite3.connect(self._evfile)
        c.isolation_level = None
        return c

    # SE01 -------------------------------------------------------------------
    def test_se01_hash_deterministic_and_status_independent(self):
        s = ReportSealer(Path(self._evfile))
        h1 = s.content_hash(1)
        h2 = s.content_hash(1)
        self.assertEqual(h1, h2)                 # deterministisch
        self.assertEqual(len(h1), 64)

        # Status aendern -> Hash MUSS gleich bleiben (sonst wuerde das Siegel im
        # Moment des Siegelns ungueltig).
        c = self._ev_con()
        c.execute("UPDATE reports SET status='approved' WHERE id=1")
        c.close()
        self.assertEqual(ReportSealer(Path(self._evfile)).content_hash(1), h1)

        # Kommentar hinzufuegen -> Hash MUSS gleich bleiben (mc: ohne Kommentare).
        c = self._ev_con()
        c.execute('INSERT INTO report_comments (block_id, author, comment, '
                  'created_at) VALUES ("b2", "h0a2898", "noch was", 1783999999)')
        c.close()
        self.assertEqual(ReportSealer(Path(self._evfile)).content_hash(1), h1)

    # SE02 -------------------------------------------------------------------
    def test_se02_hash_detects_content_change(self):
        before = ReportSealer(Path(self._evfile)).content_hash(1)
        c = self._ev_con()
        c.execute("UPDATE report_blocks SET block_data=? WHERE block_id='b1'",
                  (json.dumps({"text": "MANIPULIERT"}),))
        c.close()
        after = ReportSealer(Path(self._evfile)).content_hash(1)
        self.assertNotEqual(before, after)

    # SE03 -------------------------------------------------------------------
    def test_se03_hash_detects_reorder(self):
        before = ReportSealer(Path(self._evfile)).content_hash(1)
        c = self._ev_con()
        c.execute("UPDATE report_block_order SET sort_index=99 "
                  "WHERE block_id='b1'")   # b1 ans Ende
        c.close()
        after = ReportSealer(Path(self._evfile)).content_hash(1)
        self.assertNotEqual(before, after,
                            "Reihenfolge ist Teil des Berichts!")

    # SE04 -------------------------------------------------------------------
    def test_se04_approve_writes_all_three(self):
        res = self._svc().approve(subject_id=18, report_id=1, actor_id=1,
                                  actor_username="h0a2898", note="geprueft")
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "approved")
        self.assertEqual(len(res["content_sha256"]), 64)

        # 1) evidence: Status + report_approvals
        c = sqlite3.connect(self._evfile)
        self.assertEqual(
            c.execute("SELECT status FROM reports WHERE id=1").fetchone()[0],
            "approved")
        self.assertEqual(
            c.execute("SELECT COUNT(*) FROM report_approvals").fetchone()[0], 1)
        c.close()

        # 2) zentrales Siegel
        seal = ApprovedReportsDb(self._approved).latest_seal(18, 1)
        self.assertIsNotNone(seal)
        self.assertEqual(seal["content_sha256"], res["content_sha256"])
        self.assertEqual(seal["approved_by"], "h0a2898")
        self.assertEqual(seal["audit_seq"], res["audit_seq"])
        # Das Abbild ist vollstaendig hinterlegt.
        snap = json.loads(
            ApprovedReportsDb(self._approved).snapshot_json(seal["id"]))
        self.assertEqual(len(snap["blocks"]), 2)

        # 3) coordinator-Beleg
        n = self.con.execute(
            "SELECT COUNT(*) FROM audit_log WHERE event_type='report_approved' "
            "AND target_type='report' AND target_id='18/1'").fetchone()[0]
        self.assertEqual(n, 1)

    # SE05 -------------------------------------------------------------------
    def test_se05_preconditions(self):
        svc = self._svc()
        # 'final' aus 'submitted' -> abgelehnt.
        with self.assertRaises(ApprovalError):
            svc.approve(subject_id=18, report_id=1, actor_id=1,
                        actor_username="h0a2898", is_final=True)
        # Erst freigeben ...
        svc.approve(subject_id=18, report_id=1, actor_id=1,
                    actor_username="h0a2898")
        # ... erneute Freigabe aus 'approved' -> abgelehnt.
        with self.assertRaises(ApprovalError):
            svc.approve(subject_id=18, report_id=1, actor_id=1,
                        actor_username="h0a2898")
        # ... aber 'final' ist jetzt moeglich.
        res = svc.approve(subject_id=18, report_id=1, actor_id=1,
                          actor_username="h0a2898", is_final=True)
        self.assertEqual(res["status"], "final")
        # Unbekannter Bericht.
        with self.assertRaises(ApprovalError):
            svc.approve(subject_id=18, report_id=99, actor_id=1,
                        actor_username="h0a2898")

    # SE06 -------------------------------------------------------------------
    def test_se06_tamper_detection(self):
        """
        DER KERN DES SIEGELS: Die evidence-seitige Statussperre schuetzt gegen
        den normalen Weg (die Anwendung), NICHT gegen eine direkte Manipulation
        der DB mit einem SQLite-Werkzeug. Genau die muss der zentrale Hash
        aufdecken.
        """
        svc = self._svc()
        svc.approve(subject_id=18, report_id=1, actor_id=1,
                    actor_username="h0a2898")

        ok = svc.verify(subject_id=18, report_id=1)
        self.assertTrue(ok["sealed"])
        self.assertTrue(ok["match"])

        # Direkte Manipulation am freigegebenen Bericht (am Werkzeug vorbei).
        c = self._ev_con()
        c.execute("UPDATE report_blocks SET block_data=? WHERE block_id='b2'",
                  (json.dumps({"text": "nachtraeglich geaendert"}),))
        c.close()

        bad = svc.verify(subject_id=18, report_id=1)
        self.assertTrue(bad["sealed"])
        self.assertFalse(bad["match"])          # MANIPULATION nachgewiesen
        self.assertIn("ABWEICHUNG", bad["detail"])
        self.assertNotEqual(bad["current_sha256"], bad["sealed_sha256"])

        # Nicht versiegelter Bericht -> sealed=False, kein Fehlalarm.
        none = svc.verify(subject_id=18, report_id=99)
        self.assertFalse(none["sealed"])
        self.assertIsNone(none["match"])

    # SE07 -------------------------------------------------------------------
    def test_se07_endpoints(self):
        app = ManagementApp(self._db, evidence_dir=self._ev,
                            approved_db=self._approved)

        # person 2 (investigator, Scope 'eigene') -> 403.
        r403 = app.dispatch_write(2, "/api/report/approve",
                                  {"subject_id": 18, "report_id": 1})
        self.assertEqual(r403.status, 403)

        # Supervisor -> Erfolg.
        r = app.dispatch_write(1, "/api/report/approve",
                               {"subject_id": 18, "report_id": 1,
                                "note": "in Ordnung"})
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertTrue(d["ok"])
        self.assertEqual(d["status"], "approved")

        # verify ueber den GET-Pfad.
        v = app.dispatch(1, "/api/report/verify",
                         {"subject_id": ["18"], "report_id": ["1"]})
        self.assertEqual(v.status, 200)
        dv = json.loads(v.body.decode("utf-8"))
        self.assertTrue(dv["sealed"])
        self.assertTrue(dv["match"])

        # Erneute Freigabe (Status ist nun 'approved') -> 409 mit Begruendung.
        again = app.dispatch_write(1, "/api/report/approve",
                                   {"subject_id": 18, "report_id": 1})
        self.assertEqual(again.status, 409)

    # SE08 -------------------------------------------------------------------
    def test_se08_return_to_draft(self):
        """
        Build 380: Rueckgabe zur Nachbesserung (submitted -> draft).
        Nur aus 'submitted'; abgenommene/versandte Berichte NIE.
        """
        svc = self._svc()
        res = svc.return_to_draft(subject_id=18, report_id=1, actor_id=1,
                                  actor_username="h0a2898",
                                  note="Kapitel 3 unvollstaendig")
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "draft")

        # Status in der evidence-DB ist gesetzt.
        c = sqlite3.connect(self._evfile)
        self.assertEqual(
            c.execute("SELECT status FROM reports WHERE id=1").fetchone()[0],
            "draft")
        c.close()

        # Der Beleg liegt im audit_log.
        n = self.con.execute(
            "SELECT COUNT(*) FROM audit_log WHERE event_type='report_returned' "
            "AND target_id='18/1'").fetchone()[0]
        self.assertEqual(n, 1)

        # Aus 'draft' ist keine erneute Rueckgabe moeglich.
        with self.assertRaises(ApprovalError):
            svc.return_to_draft(subject_id=18, report_id=1, actor_id=1,
                                actor_username="h0a2898")

    # SE09 -------------------------------------------------------------------
    def test_se09_no_return_after_approval(self):
        """Abgenommene und versandte Berichte werden NIE zurueckgestuft."""
        svc = self._svc()
        svc.approve(subject_id=18, report_id=1, actor_id=1,
                    actor_username="h0a2898")
        with self.assertRaises(ApprovalError):
            svc.return_to_draft(subject_id=18, report_id=1, actor_id=1,
                                actor_username="h0a2898")
        svc.approve(subject_id=18, report_id=1, actor_id=1,
                    actor_username="h0a2898", is_final=True)
        with self.assertRaises(ApprovalError):
            svc.return_to_draft(subject_id=18, report_id=1, actor_id=1,
                                actor_username="h0a2898")

    # SE10 -------------------------------------------------------------------
    def test_se10_return_endpoint_rbac(self):
        """
        Der LEKTOR (nur reports.review) darf zurueckgeben — die Chefin auch.
        Wer keines von beidem hat, nicht.
        """
        self.rbac.grant("lector", "reports.review", scope="alle", actor_id=1)
        self.rbac.assign_role(2, "lector", actor_id=1)
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        app = ManagementApp(self._db, evidence_dir=self._ev,
                            approved_db=self._approved)
        # person 2 ist jetzt lector (reports.review, alle) -> darf.
        r = app.dispatch_write(2, "/api/report/return",
                               {"subject_id": 18, "report_id": 1})
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["status"], "draft")

        # Zurueck auf 'submitted' (Aufbau), dann Chefin -> darf ebenfalls.
        c = sqlite3.connect(self._evfile)
        c.isolation_level = None
        c.execute("UPDATE reports SET status='submitted' WHERE id=1")
        c.close()
        r2 = app.dispatch_write(1, "/api/report/return",
                                {"subject_id": 18, "report_id": 1})
        self.assertEqual(r2.status, 200)


if __name__ == "__main__":
    unittest.main()

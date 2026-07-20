# =============================================================================
# tests/test_reports_scan.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Berichts-Abnahme
# =============================================================================
# Testsuite fuer Build 374: EvidenceScanner + ReportsRepo + /api/reports.
#
# RS01 — Scanner findet evidence_<uid>.db (und ignoriert Cross-Evidence-DBs).
# RS02 — FINGERABDRUCK ERKENNT WAL-AENDERUNGEN. Der Kern-Test: ein UPDATE im
#        WAL-Modus aendert die .db-Datei NICHT — der Abdruck muss sich trotzdem
#        aendern, sonst wuerde ein geaenderter Bericht still uebersehen.
# RS03 — ReportsRepo liest Berichte + Freigaben; Cache wird gefuellt.
# RS04 — Cache-Treffer: unveraenderte DBs werden NICHT neu eingelesen
#        (rescanned=0); nach einer Aenderung wird genau diese DB neu gelesen.
# RS05 — force=True erzwingt den Vollscan.
# RS06 — Defekte evidence-DB -> Fehlereintrag (NICHT stillschweigend ignoriert).
# RS07 — /api/reports: 200 + Berichte; 403 ohne reports.review.
# RS08 — scope 'eigene': nur Berichte zu eigenen Faellen.
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
from management.reports.evidence_scanner import EvidenceScanner
from management.reports.reports_repo import ReportsRepo
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

_EVIDENCE_REPORTS = """
CREATE TABLE "reports" (
    "id" INTEGER,
    "report_type" TEXT NOT NULL CHECK("report_type" IN ('interim','final','addendum')),
    "sequence_nr" INTEGER NOT NULL DEFAULT 1,
    "title" TEXT NOT NULL,
    "created_by" TEXT NOT NULL,
    "created_at" INTEGER NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'draft'
        CHECK("status" IN ('draft','submitted','approved','final')),
    PRIMARY KEY("id" AUTOINCREMENT)
)
"""

_EVIDENCE_APPROVALS = """
CREATE TABLE "report_approvals" (
    "id" INTEGER,
    "report_id" INTEGER NOT NULL,
    "approved_by" TEXT NOT NULL,
    "approved_at" INTEGER NOT NULL,
    "note" TEXT DEFAULT NULL,
    "is_final" INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY("id" AUTOINCREMENT)
)
"""


def _make_evidence(path, reports):
    """Legt eine evidence-DB im WAL-Modus mit Berichten an."""
    con = sqlite3.connect(path)
    con.isolation_level = None
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(_EVIDENCE_REPORTS)
    con.execute(_EVIDENCE_APPROVALS)
    for rid, rtype, seq, title, status in reports:
        con.execute(
            'INSERT INTO reports (id, report_type, sequence_nr, title, '
            'created_by, created_at, status) VALUES (?,?,?,?,?,?,?)',
            (rid, rtype, seq, title, "h002", int(time.time()), status))
    con.close()


class ReportsScanTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._ev = os.path.join(self._tmp, "evidence")
        os.makedirs(self._ev)
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
        self.rbac.grant("supervisor", "reports.review", scope="alle",
                        actor_id=1)
        self.rbac.grant("investigator", "reports.review", scope="eigene",
                        actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)

        for uid in (18, 19):
            self.cases.create_case(uid, "b%d" % uid, actor_id=1)
        self.cases.assign(18, 2, actor_id=1)   # Fall 18 -> person 2
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        # Zwei evidence-DBs + eine Cross-Evidence-DB (muss ignoriert werden).
        _make_evidence(os.path.join(self._ev, "evidence_18.db"),
                       [(1, "interim", 1, "Zwischenbericht", "submitted")])
        _make_evidence(os.path.join(self._ev, "evidence_19.db"),
                       [(1, "final", 1, "Abschlussbericht", "draft")])
        _make_evidence(os.path.join(self._ev, "evidence_18_7.db"),
                       [(1, "interim", 1, "Querbezug", "draft")])

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

    # RS01 -------------------------------------------------------------------
    def test_rs01_scanner_lists_cases(self):
        sc = EvidenceScanner(self._ev)
        uids = [uid for uid, _ in sc.list_cases()]
        self.assertEqual(uids, [18, 19])   # Cross-Evidence (18_7) ignoriert

    # RS02 -------------------------------------------------------------------
    def test_rs02_fingerprint_detects_wal_change(self):
        """
        KERN-TEST (Grundregel 1): Ein UPDATE im WAL-Modus aendert mtime/Groesse
        der .db-Datei NICHT. Der Fingerabdruck muss die Aenderung dennoch
        erkennen — sonst wuerde ein geaenderter Bericht still uebersehen.
        """
        p = Path(os.path.join(self._ev, "evidence_18.db"))
        st_before = p.stat()
        fp_before = EvidenceScanner.fingerprint(p)

        time.sleep(0.05)
        con = sqlite3.connect(str(p))
        con.isolation_level = None
        con.execute("UPDATE reports SET status='approved' WHERE id=1")
        con.close()

        st_after = p.stat()
        fp_after = EvidenceScanner.fingerprint(p)

        # Die .db-Datei selbst verraet die Aenderung NICHT zwingend ...
        # (nur dokumentierend; auf manchen FS kann sie sich auch aendern)
        # ... der Fingerabdruck ueber ALLE Dateien MUSS sie erkennen:
        self.assertNotEqual(fp_before, fp_after,
                            "Fingerabdruck hat die WAL-Aenderung nicht erkannt!")

    # RS03 -------------------------------------------------------------------
    def test_rs03_reads_reports(self):
        repo = ReportsRepo(self.con, self._ev)
        res = repo.list_reports()
        self.assertEqual(res["case_db_count"], 2)
        self.assertEqual(res["count"], 2)
        by_uid = {r["subject_id"]: r for r in res["reports"]}
        self.assertEqual(by_uid[18]["title"], "Zwischenbericht")
        self.assertEqual(by_uid[18]["status"], "submitted")
        self.assertEqual(by_uid[18]["username"], "b18")
        self.assertEqual(by_uid[18]["assigned_to"], 2)
        self.assertEqual(by_uid[19]["report_type"], "final")
        self.assertIn("approvals", by_uid[18])
        self.assertEqual(res["errors"], [])

    # RS04 -------------------------------------------------------------------
    def test_rs04_cache_hit_and_invalidation(self):
        repo = ReportsRepo(self.con, self._ev)
        first = repo.list_reports()
        self.assertEqual(first["rescanned"], 2)   # beide frisch eingelesen

        second = repo.list_reports()
        self.assertEqual(second["rescanned"], 0)  # Cache-Treffer, nichts gelesen
        self.assertEqual(second["count"], 2)

        # Eine DB aendern (WAL) -> genau diese muss neu gelesen werden.
        time.sleep(0.05)
        con = sqlite3.connect(os.path.join(self._ev, "evidence_19.db"))
        con.isolation_level = None
        con.execute("UPDATE reports SET status='submitted' WHERE id=1")
        con.close()

        third = repo.list_reports()
        self.assertEqual(third["rescanned"], 1)
        by_uid = {r["subject_id"]: r for r in third["reports"]}
        self.assertEqual(by_uid[19]["status"], "submitted")  # neuer Stand

    # RS05 -------------------------------------------------------------------
    def test_rs05_force_rescan(self):
        repo = ReportsRepo(self.con, self._ev)
        repo.list_reports()
        forced = repo.list_reports(force=True)
        self.assertEqual(forced["rescanned"], 2)

    # RS06 -------------------------------------------------------------------
    def test_rs06_broken_db_reported(self):
        # Defekte DB: Datei ohne SQLite-Inhalt.
        with open(os.path.join(self._ev, "evidence_20.db"), "wb") as f:
            f.write(b"kein sqlite")
        repo = ReportsRepo(self.con, self._ev)
        res = repo.list_reports()
        errs = {e["subject_id"] for e in res["errors"]}
        self.assertIn(20, errs)            # gemeldet, nicht verschluckt
        self.assertEqual(res["count"], 2)  # die gesunden Faelle bleiben da

    # RS07 -------------------------------------------------------------------
    def test_rs07_endpoint(self):
        app = ManagementApp(self._db, evidence_dir=self._ev)
        r = app.dispatch(1, "/api/reports")
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["scope"], "alle")
        self.assertEqual(d["count"], 2)
        # person 3: keine Rolle -> 403
        self.assertEqual(app.dispatch(3, "/api/reports").status, 403)

    # RS08 -------------------------------------------------------------------
    def test_rs08_scope_eigene(self):
        app = ManagementApp(self._db, evidence_dir=self._ev)
        d = json.loads(app.dispatch(2, "/api/reports").body.decode("utf-8"))
        self.assertEqual(d["scope"], "eigene")
        # person 2 ist nur Fall 18 zugewiesen.
        self.assertEqual(d["count"], 1)
        self.assertEqual(d["reports"][0]["subject_id"], 18)


    # RS09 -------------------------------------------------------------------
    def test_rs09_approve_implies_review(self):
        """
        Build 375 (Rechte-Korrektur): Wer FREIGEBEN darf (reports.approve),
        muss den Bericht auch LESEN duerfen. Vorher gatete /api/reports allein
        auf reports.review, waehrend die Cockpit-Nav auf reports.approve gatete
        -> der Supervisor sah den Reiter, bekam aber 403.
        """
        # person 3: NUR reports.approve (kein reports.review).
        self.rbac.grant("support", "reports.approve", scope="alle", actor_id=1)
        self.rbac.assign_role(3, "support", actor_id=1)
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        app = ManagementApp(self._db, evidence_dir=self._ev)
        r = app.dispatch(3, "/api/reports")
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["scope"], "alle")
        self.assertEqual(d["count"], 2)


if __name__ == "__main__":
    unittest.main()

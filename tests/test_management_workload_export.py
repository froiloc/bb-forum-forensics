# =============================================================================
# tests/test_management_workload_export.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Lastverteilung (Frontend)
# =============================================================================
# Testsuite fuer Build 335: self-contained HTML-Export der Lastverteilung.
#
# WE01 — build_workload_html bettet die Daten ein (system_username)
# WE02 — self-contained: CSS+JS INLINE, KEINE externen <script src>/<link href>
# WE03 — debug-Flag steuert window.AIW_WORKLOAD_DEBUG (false in PROD)
# WE04 — '</script>' aus Daten wird entschaerft
# WE05 — Render-Ziel #aiw-workload-root + Filterfeld vorhanden
# WE06 — multilinguale UTF-8-Anzeigenamen bleiben erhalten
# WE07 — Integritaets-Banner: ok / gebrochen / ungeprueft
# WE08 — CLI 'export-html' end-to-end gegen synthetische coordinator.db
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

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
from management.cases.cases_repo import CasesRepo
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.workload import workload_admin
from management.workload.html_export import build_workload_html

_INVESTIGATORS = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0,
    is_support INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
)
"""
_OLD_SCRAPE_JOBS = """
CREATE TABLE scrape_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL, username TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','running','done','failed')),
    manifest_path TEXT, output_path TEXT, worker_id TEXT,
    created_at INTEGER NOT NULL, started_at INTEGER, finished_at INTEGER,
    error_message TEXT, assigned_to INTEGER, note TEXT,
    FOREIGN KEY(assigned_to) REFERENCES person(id)
)
"""


class WorkloadExportTests(unittest.TestCase):

    def _sample(self, **over):
        base = {"investigator_id": 1, "system_username": "h001",
                "display_name": "Alpha", "is_investigator": True,
                "is_supervisor": False, "is_support": False, "is_backlog": False,
                "total_cases": 3, "ampel_rot": 1, "ampel_gelb": 1,
                "ampel_gruen": 1, "status_open": 2, "status_in_progress": 1,
                "status_approved": 0, "status_closed": 0, "active_cases": 3,
                "done_cases": 0, "audit_action_count": 5,
                "last_action_at": 1000}
        base.update(over)
        return [base]

    def test_we01_embeds_data(self):
        html = build_workload_html(self._sample(system_username="hXYZ99"),
                                   "CSS", "JS")
        self.assertIn("hXYZ99", html)

    def test_we02_self_contained(self):
        html = build_workload_html(self._sample(), "CSSMARKER", "JSMARKER")
        self.assertIn("CSSMARKER", html)
        self.assertIn("JSMARKER", html)
        self.assertNotIn("<script src", html)
        self.assertNotIn('rel="stylesheet"', html)

    def test_we03_debug_flag(self):
        self.assertIn("AIW_WORKLOAD_DEBUG = false",
                      build_workload_html([], "", "", debug=False))
        self.assertIn("AIW_WORKLOAD_DEBUG = true",
                      build_workload_html([], "", "", debug=True))

    def test_we04_script_break_defused(self):
        html = build_workload_html(
            self._sample(display_name="evil</script><b>x"), "", "")
        self.assertEqual(html.count("</script>"), 2)
        self.assertIn("<\\/script>", html)

    def test_we05_render_root_and_filter(self):
        html = build_workload_html([], "", "")
        self.assertIn('id="aiw-workload-root"', html)
        self.assertIn('id="aiw-filter"', html)

    def test_we06_utf8_preserved(self):
        name = "\u041f\u0435\u0442\u0440\u043e\u0432_\u03a9_\u0645\u062d\u0642\u0642"
        html = build_workload_html(self._sample(display_name=name), "", "")
        self.assertIn(name, html)

    def test_we07_integrity_banner(self):
        ok = build_workload_html([], "", "", verify_result={
            "ok": True, "tip_seq": 9, "tip_hash": "0123456789abcdefff",
            "detail": "ok"})
        self.assertIn("verifiziert bis seq 9", ok)
        bad = build_workload_html([], "", "", verify_result={
            "ok": False, "first_bad_seq": 2, "detail": "prev_hash-Bruch bei seq=2"})
        self.assertIn("GEBROCHEN", bad)
        self.assertIn("nicht geprueft",
                      build_workload_html([], "", "", verify_result=None))

    def _make_coordinator(self, path):
        con = sqlite3.connect(path)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        now = int(time.time())
        con.execute(_INVESTIGATORS)
        con.execute("INSERT INTO person (id, system_username, "
                    "display_name, is_investigator, created_at) "
                    "VALUES (1, 'h001', 'Alpha', 1, ?)", (now,))
        con.execute(_OLD_SCRAPE_JOBS)
        audit = AuditLog(con)
        MigrationRunner(con, discover(coordinator_migrations), audit=audit,
                        deployed_by="t").run()
        writer = CoordinatorWriter(con, audit)
        cases = CasesRepo(con, writer)
        cases.create_case(subject_id=4201, username="tester", actor_id=1)
        cases.assign(4201, 1, actor_id=1)
        con.close()

    def test_we08_cli_export_end_to_end(self):
        tmp = tempfile.mkdtemp()
        try:
            db = os.path.join(tmp, "coordinator.db")
            out = os.path.join(tmp, "workload.html")
            self._make_coordinator(db)
            rc = workload_admin.main(
                ["export-html", "--coordinator-db", db,
                 "--config", "/nonexistent.yaml", "--out", out])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(out))
            html = Path(out).read_text(encoding="utf-8")
            self.assertIn("h001", html)                    # echter Ermittler
            self.assertIn("Alpha", html)
            self.assertIn("AIWWorkload", html)              # JS inline
            self.assertIn("aiw-workload-table", html)       # CSS inline
            self.assertIn("verifiziert bis seq", html)      # Integritaets-Banner
            self.assertIn("nicht zugewiesen", html)         # Rueckstau-Zeile
            self.assertNotIn("<script src", html)
        finally:
            for root, _d, files in os.walk(tmp, topdown=False):
                for fn in files:
                    try:
                        os.remove(os.path.join(root, fn))
                    except OSError:
                        pass
                os.rmdir(root)


if __name__ == "__main__":
    unittest.main()

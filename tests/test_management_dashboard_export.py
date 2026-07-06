# =============================================================================
# tests/test_management_dashboard_export.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Ampel-Dashboard (Frontend)
# =============================================================================
# Testsuite fuer Build 323: self-contained HTML-Export.
#
# E01 — build_dashboard_html bettet die Falldaten ein (user_id im Output)
# E02 — self-contained: CSS+JS INLINE, KEINE externen <script src>/<link href>
# E03 — debug-Flag steuert window.AIW_DASHBOARD_DEBUG (false in PROD)
# E04 — '</script>' aus Daten wird entschaerft (bricht die Seite nicht)
# E05 — Render-Ziel #aiw-dashboard-root vorhanden
# E06 — multilinguale UTF-8-Benutzernamen bleiben erhalten
# E07 — CLI 'export-html' end-to-end gegen synthetische coordinator.db
#
# Version: v0.7.323 · Build: 323 · 2026-07-04
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
from management.dashboard import dashboard_admin
from management.dashboard.html_export import build_dashboard_html
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover

_INVESTIGATORS = """
CREATE TABLE investigators (
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
    FOREIGN KEY(assigned_to) REFERENCES investigators(id)
)
"""


class DashboardExportTests(unittest.TestCase):

    # ---- reine Funktion -----------------------------------------------------
    def _sample(self, **over):
        base = {"user_id": 4201, "username": "u", "status": "open",
                "priority": 3, "ampel": "rot", "ampel_reason": "aktiv",
                "event_count": 0, "support_active": False, "support_count": 0,
                "last_activity_at": 0}
        base.update(over)
        return [base]

    def test_e01_embeds_data(self):
        html = build_dashboard_html(self._sample(user_id=4201), "CSS", "JS")
        self.assertIn("4201", html)

    def test_e02_self_contained(self):
        html = build_dashboard_html(self._sample(), "CSSMARKER", "JSMARKER")
        self.assertIn("CSSMARKER", html)                 # CSS inline
        self.assertIn("JSMARKER", html)                  # JS inline
        self.assertNotIn("<script src", html)            # kein externer Verweis
        self.assertNotIn('rel="stylesheet"', html)

    def test_e03_debug_flag(self):
        self.assertIn("AIW_DASHBOARD_DEBUG = false",
                      build_dashboard_html([], "", "", debug=False))
        self.assertIn("AIW_DASHBOARD_DEBUG = true",
                      build_dashboard_html([], "", "", debug=True))

    def test_e04_script_break_defused(self):
        html = build_dashboard_html(
            self._sample(username="evil</script><b>x"), "", "")
        # Genau die zwei legitimen schliessenden Tags, keiner aus den Daten.
        self.assertEqual(html.count("</script>"), 2)
        self.assertIn("<\\/script>", html)               # entschaerfte Form

    def test_e05_render_root(self):
        self.assertIn('id="aiw-dashboard-root"', build_dashboard_html([], "", ""))

    def test_e06_utf8_preserved(self):
        name = "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c_\u03a9_\u0645\u0633\u062a\u062e\u062f\u0645"
        html = build_dashboard_html(self._sample(username=name), "", "")
        self.assertIn(name, html)

    # ---- CLI-Integration ----------------------------------------------------
    def _make_coordinator_with_case(self, path):
        con = sqlite3.connect(path)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        now = int(time.time())
        con.execute(_INVESTIGATORS)
        con.execute("INSERT INTO investigators (id, system_username, "
                    "display_name, created_at) VALUES (1, 'h001', 'Alpha', ?)",
                    (now,))
        con.execute(_OLD_SCRAPE_JOBS)
        audit = AuditLog(con)
        MigrationRunner(con, discover(coordinator_migrations), audit=audit,
                        deployed_by="t").run()
        cases = CasesRepo(con, CoordinatorWriter(con, audit))
        cases.create_case(user_id=4201, username="tester", actor_id=1)
        con.close()

    def test_e07_cli_export_end_to_end(self):
        tmp = tempfile.mkdtemp()
        try:
            db = os.path.join(tmp, "coordinator.db")
            out = os.path.join(tmp, "dashboard_out.html")
            self._make_coordinator_with_case(db)
            rc = dashboard_admin.main(
                ["export-html", "--coordinator-db", db,
                 "--config", "/nonexistent.yaml", "--out", out])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(out))
            html = Path(out).read_text(encoding="utf-8")
            self.assertIn("4201", html)                       # echter Fall
            self.assertIn("tester", html)
            self.assertIn("AIWDashboard", html)               # dashboard.js inline
            self.assertIn("aiw-dashboard-table", html)        # dashboard.css inline
            self.assertNotIn("<script src", html)             # self-contained
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

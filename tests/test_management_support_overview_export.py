# =============================================================================
# tests/test_management_support_overview_export.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Support-Historie (Frontend)
# =============================================================================
# Testsuite fuer Build 330: self-contained HTML-Export der Support-Historie.
#
# EO01 — build_support_overview_html bettet die Sitzungsdaten ein (session_id)
# EO02 — self-contained: CSS+JS INLINE, KEINE externen <script src>/<link href>
# EO03 — debug-Flag steuert window.AIW_SUPPORT_OVERVIEW_DEBUG (false in PROD)
# EO04 — '</script>' aus Daten wird entschaerft (bricht die Seite nicht)
# EO05 — Render-Ziel #aiw-support-overview-root + Filterfeld vorhanden
# EO06 — multilinguale UTF-8-Benutzernamen bleiben erhalten
# EO07 — Integritaets-Banner: ok / gebrochen / ungeprueft
# EO08 — CLI 'export-html' end-to-end gegen synthetische coordinator.db
#
# Version: v0.7.330 · Build: 330 · 2026-07-07
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
from management.support_overview import support_overview_admin
from management.support_overview.html_export import build_support_overview_html
from management.support_sessions.support_sessions_repo import SupportSessionsRepo

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


class SupportOverviewExportTests(unittest.TestCase):

    def _sample(self, **over):
        base = {"session_id": 42, "user_id": 7001, "username": "u",
                "supporter_id": 1, "supporter_system_username": "h001",
                "supporter_display_name": "Support Eins",
                "started_at": 1000, "ended_at": 1060, "duration_sec": 60,
                "reason": None, "status": "beendet",
                "started_seq": 3, "ended_seq": 4, "started_ts": 1000,
                "ended_ts": 1060, "started_actor_id": 1, "ended_actor_id": 1,
                "anomaly": None}
        base.update(over)
        return [base]

    # ---- reine Funktion -----------------------------------------------------
    def test_eo01_embeds_data(self):
        html = build_support_overview_html(self._sample(session_id=4242),
                                           "CSS", "JS")
        self.assertIn("4242", html)

    def test_eo02_self_contained(self):
        html = build_support_overview_html(self._sample(), "CSSMARKER",
                                           "JSMARKER")
        self.assertIn("CSSMARKER", html)
        self.assertIn("JSMARKER", html)
        self.assertNotIn("<script src", html)
        self.assertNotIn('rel="stylesheet"', html)

    def test_eo03_debug_flag(self):
        self.assertIn("AIW_SUPPORT_OVERVIEW_DEBUG = false",
                      build_support_overview_html([], "", "", debug=False))
        self.assertIn("AIW_SUPPORT_OVERVIEW_DEBUG = true",
                      build_support_overview_html([], "", "", debug=True))

    def test_eo04_script_break_defused(self):
        html = build_support_overview_html(
            self._sample(username="evil</script><b>x"), "", "")
        # Genau die zwei legitimen schliessenden <script>-Tags, keiner aus Daten.
        self.assertEqual(html.count("</script>"), 2)
        self.assertIn("<\\/script>", html)

    def test_eo05_render_root_and_filter(self):
        html = build_support_overview_html([], "", "")
        self.assertIn('id="aiw-support-overview-root"', html)
        self.assertIn('id="aiw-filter"', html)

    def test_eo06_utf8_preserved(self):
        name = "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c_\u03a9_\u0645\u0633\u062a\u062e\u062f\u0645"
        html = build_support_overview_html(self._sample(username=name), "", "")
        self.assertIn(name, html)

    def test_eo07_integrity_banner(self):
        ok = build_support_overview_html([], "", "", verify_result={
            "ok": True, "tip_seq": 7, "tip_hash": "abcdef0123456789aa",
            "detail": "ok"})
        self.assertIn("verifiziert bis seq 7", ok)
        bad = build_support_overview_html([], "", "", verify_result={
            "ok": False, "first_bad_seq": 3, "detail": "prev_hash-Bruch bei seq=3"})
        self.assertIn("GEBROCHEN", bad)
        unknown = build_support_overview_html([], "", "", verify_result=None)
        self.assertIn("nicht geprueft", unknown)

    # ---- CLI-Integration ----------------------------------------------------
    def _make_coordinator_with_session(self, path):
        con = sqlite3.connect(path)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        now = int(time.time())
        con.execute(_INVESTIGATORS)
        con.execute("INSERT INTO person (id, system_username, "
                    "display_name, is_support, created_at) "
                    "VALUES (1, 'h001', 'Support Eins', 1, ?)", (now,))
        con.execute(_OLD_SCRAPE_JOBS)
        audit = AuditLog(con)
        MigrationRunner(con, discover(coordinator_migrations), audit=audit,
                        deployed_by="t").run()
        writer = CoordinatorWriter(con, audit)
        CasesRepo(con, writer).create_case(user_id=4201, username="tester",
                                           actor_id=1)
        support = SupportSessionsRepo(con, writer)
        sid = support.start(4201, supporter_id=1, actor_id=1)
        support.end(sid, actor_id=1)
        con.close()

    def test_eo08_cli_export_end_to_end(self):
        tmp = tempfile.mkdtemp()
        try:
            db = os.path.join(tmp, "coordinator.db")
            out = os.path.join(tmp, "support_history.html")
            self._make_coordinator_with_session(db)
            rc = support_overview_admin.main(
                ["export-html", "--coordinator-db", db,
                 "--config", "/nonexistent.yaml", "--out", out])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(out))
            html = Path(out).read_text(encoding="utf-8")
            self.assertIn("4201", html)                    # echter Fall
            self.assertIn("tester", html)
            self.assertIn("AIWSupportOverview", html)       # JS inline
            self.assertIn("aiw-support-table", html)        # CSS inline
            self.assertIn("verifiziert bis seq", html)      # Integritaets-Banner
            self.assertNotIn("<script src", html)           # self-contained
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

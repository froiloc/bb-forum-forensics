# =============================================================================
# tests/test_export.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# =============================================================================
# Testsuite fuer forensic_api/export.py
#
# T01 -- _html_esc(): escapet <, >, &, "
# T02 -- Format A (html): leere Paragraphenliste -> valides HTML
# T03 -- Format A (html): Paragraph enthalten, Content-Disposition gesetzt
# T04 -- Format A (html): XSS-Schutz in Paragraphentext
# T05 -- Format A (html): Beweisanker erscheinen als Listenelemente
# T06 -- Format B (docx): python-docx fehlt -> HTTP 503 mit Hinweis
# T07 -- Format C (sqlite): leere DB -> valides SQLite mit allen Tabellen
# T08 -- Format C (sqlite): report_paragraphs nur active/approved
# T09 -- Format C (sqlite): README-Tabelle enthaelt Beschreibung
# T10 -- Unbekanntes Format -> HTTP 400
#
# Version: v0.6.097 · Build: 097 · 2026-05-05
# Beleg: Bauplan B6 v0.3 §7.2, Build 097
# =============================================================================

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forensic_api.export import ExportEndpoint
from db.evidence_db import EvidenceDb


def _make_edb():
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con, EvidenceDb(con)


def _make_endpoint(edb):
    bundle = MagicMock()
    bundle.evidence = edb
    bundle.connection = MagicMock()
    bundle.connection.execute = MagicMock(side_effect=sqlite3.OperationalError("no fdb"))

    context = MagicMock()
    context.user_id  = 42
    context.username = "TestNutzer"

    config = MagicMock()
    return ExportEndpoint(bundle, context, config)


def _make_handler():
    responses = []
    handler = MagicMock()
    handler.send_response_body = lambda status, body, **kw: responses.append(
        (status, body, kw)
    )
    return handler, responses


class TestHtmlEsc(unittest.TestCase):

    def test_T01_html_esc(self):
        """T01: _html_esc() escapet <, >, &, Anfuehrungszeichen."""
        ep = _make_endpoint(_make_edb()[1])
        result = ep._html_esc('<b>"Test" & </b>')
        self.assertNotIn('<b>', result)
        self.assertNotIn('"', result)
        self.assertIn('&lt;', result)
        self.assertIn('&quot;', result)
        self.assertIn('&amp;', result)


class TestExportHtml(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_edb()
        self.ep = _make_endpoint(self.edb)

    def tearDown(self):
        self.con.close()

    def test_T02_leere_db_valides_html(self):
        """T02: Leere DB -> valides HTML mit DOCTYPE."""
        handler, responses = _make_handler()
        self.ep.handle_get(handler, {"format": ["html"]})
        self.assertEqual(len(responses), 1)
        status, body, kw = responses[0]
        self.assertEqual(status, 200)
        html = body.decode("utf-8")
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("text/html", kw.get("content_type", ""))

    def test_T03_paragraph_in_export(self):
        """T03: Paragraph mit status=active erscheint im HTML-Export."""
        rid = self.edb.create_report("interim", "Test", "h001")
        self.edb.add_paragraph("blk-1", rid, "h001", content="Absatztext hier.")
        self.edb.set_paragraph_status("blk-1", "active", "h001")

        handler, responses = _make_handler()
        self.ep.handle_get(handler, {"format": ["html"]})
        status, body, kw = responses[0]
        self.assertEqual(status, 200)
        html = body.decode("utf-8")
        self.assertIn("Absatztext hier.", html)
        # Content-Disposition muss gesetzt sein
        cd = kw.get("extra_headers", {}).get("Content-Disposition", "")
        self.assertIn("attachment", cd)
        self.assertIn(".html", cd)

    def test_T04_xss_schutz(self):
        """T04: XSS-Schutz im HTML-Export."""
        rid = self.edb.create_report("interim", "Test", "h001")
        self.edb.add_paragraph("blk-x", rid, "h001",
                                content='<script>alert(1)</script>')
        self.edb.set_paragraph_status("blk-x", "active", "h001")

        handler, responses = _make_handler()
        self.ep.handle_get(handler, {"format": ["html"]})
        html = responses[0][1].decode("utf-8")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_T05_beweisanker_als_liste(self):
        """T05: Beweisanker erscheinen als Listenelemente im HTML-Export."""
        rid = self.edb.create_report("interim", "Test", "h001")
        self.edb.add_paragraph("blk-a", rid, "h001", content="Text mit Beleg.")
        self.edb.set_paragraph_status("blk-a", "active", "h001")
        ann_id = self.edb.save_annotation("/test", "CAT_OTHER", "Beleg")
        self.edb.add_anchor("blk-a", ann_id, "Anker-Text XYZ")

        handler, responses = _make_handler()
        self.ep.handle_get(handler, {"format": ["html"]})
        html = responses[0][1].decode("utf-8")
        self.assertIn("Anker-Text XYZ", html)
        self.assertIn("<ol", html)


class TestExportDocx(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_edb()
        self.ep = _make_endpoint(self.edb)

    def tearDown(self):
        self.con.close()

    @patch.dict("sys.modules", {"docx": None})
    def test_T06_docx_fehlt_gibt_503(self):
        """T06: python-docx nicht installiert -> HTTP 503."""
        handler, responses = _make_handler()
        self.ep.handle_get(handler, {"format": ["docx"]})
        self.assertEqual(len(responses), 1)
        status = responses[0][0]
        self.assertEqual(status, 503)
        body = json.loads(responses[0][1].decode("utf-8"))
        self.assertIn("python-docx", body["error"])


class TestExportSqlite(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_edb()
        self.ep = _make_endpoint(self.edb)

    def tearDown(self):
        self.con.close()

    def _get_sqlite_db(self):
        handler, responses = _make_handler()
        self.ep.handle_get(handler, {"format": ["sqlite"]})
        self.assertEqual(responses[0][0], 200)
        body = responses[0][1]
        con  = sqlite3.connect(":memory:")
        tmp_con = sqlite3.connect(":memory:")
        # Bytes direkt deserializieren
        tmp_con.deserialize(body)
        return tmp_con

    def test_T07_alle_tabellen_vorhanden(self):
        """T07: SQLite-Export enthaelt alle Pflicht-Tabellen."""
        db = self._get_sqlite_db()
        tables = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        for t in ("meta", "profile_summary", "known_aliases", "report_paragraphs",
                  "evidence_annotations", "network_summary", "activity_stats",
                  "timeline_summary", "README"):
            self.assertIn(t, tables, f"Tabelle '{t}' fehlt im SQLite-Export")
        db.close()

    def test_T08_nur_active_und_approved(self):
        """T08: report_paragraphs im Export nur active/approved."""
        rid = self.edb.create_report("interim", "Test", "h001")
        self.edb.add_paragraph("p-draft",  rid, "h001", content="Entwurf")
        self.edb.add_paragraph("p-active", rid, "h001", content="Aktiv")
        self.edb.set_paragraph_status("p-active", "active", "h001")

        db = self._get_sqlite_db()
        rows = db.execute(
            "SELECT block_id, status FROM report_paragraphs"
        ).fetchall()
        block_ids = {r[0] for r in rows}
        self.assertNotIn("p-draft",  block_ids)
        self.assertIn("p-active", block_ids)
        db.close()

    def test_T09_readme_enthaelt_beschreibung(self):
        """T09: README-Tabelle enthaelt Beschreibung und Klassifizierung."""
        db = self._get_sqlite_db()
        rows = {r[0]: r[1] for r in db.execute(
            "SELECT key, value FROM README"
        ).fetchall()}
        self.assertIn("beschreibung", rows)
        self.assertIn("klassifizierung", rows)
        self.assertIn("VERTRAULICH", rows["klassifizierung"])
        db.close()


class TestExportUnbekanntes(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_edb()
        self.ep = _make_endpoint(self.edb)

    def tearDown(self):
        self.con.close()

    def test_T10_unbekanntes_format(self):
        """T10: Unbekanntes Format -> HTTP 400."""
        handler, responses = _make_handler()
        self.ep.handle_get(handler, {"format": ["pdf"]})
        self.assertEqual(responses[0][0], 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)

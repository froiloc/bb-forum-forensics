# =============================================================================
# tests/test_forensic_api.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite für forensic_api/ (alle Endpunkte)
#
# T01 — /_forensic/page: bekannte URL → JSON-Envelope mit in_scope=True
# T02 — /_forensic/page: url-Parameter fehlt → HTTP 400
# T03 — /_forensic/page: unbekannte URL → in_scope=False
# T04 — /_forensic/annotate: gültige Annotation → HTTP 200, id im Response
# T05 — /_forensic/annotate: ungültige Kategorie → HTTP 400
# T06 — /_forensic/annotate: page_url fehlt → HTTP 400
# T07 — /_forensic/annotate: ungültiges JSON → HTTP 400
# T08 — /_forensic/status: liefert JSON mit version, mode, user_id
# T09 — /_forensic/viewport: gültiger Batch → HTTP 200, saved=N
# T10 — /_forensic/viewport: leerer Batch → HTTP 200, saved=0
# T11 — /_forensic/viewport: page_url fehlt → HTTP 400
# T12 — /_forensic/toolbar.js: HTTP 200, Content-Type JavaScript
# T13 — /_forensic/toolbar.css: HTTP 200, Content-Type CSS
# T14 — GET auf /_forensic/annotate (falsche Methode) → HTTP 405
# T15 — POST auf /_forensic/status (falsche Methode) → HTTP 405
# T16 — Unbekannter Endpunkt → HTTP 404
# T17 — AnnotateEndpoint: alle sechs Kategorien werden akzeptiert
# T18 — ViewportEndpoint: ungültige Events im Batch werden übersprungen
#
# Version: v0.1.0 · Build: 026 · 2026-04-15
# =============================================================================

import sys
import os
import json
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import setup_logging, reset_for_testing
from core.config_loader import ConfigLoader
from db.forensic_db import PageRecord
from db.evidence_db import VALID_CATEGORIES
from forensic_api import ForensicApi


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _setup_logging_and_config() -> ConfigLoader:
    reset_for_testing()
    tmp = tempfile.mkdtemp()
    config_path = os.path.join(tmp, "config.yaml")
    logfile     = os.path.join(tmp, "logs", "test.log")
    with open(config_path, "w") as fh:
        fh.write(textwrap.dedent(f"""
            logging:
              level: "debug"
              logfile: "{logfile}"
              max_bytes: 1048576
              backup_count: 2
            paths:
              coordinator_db: "./c.db"
              forensic_db_dir: "./f/"
              default_db: "./d.db"
              evidence_db_dir: "./e/"
            url_patterns:
              asset_prefixes:
                - "/forum/style/"
              alias_patterns:
                post_id_param: "pid"
                notify_param: "notify"
                fragment_post: "p"
        """))
    cfg = ConfigLoader(config_path=config_path)
    setup_logging(cfg)
    return cfg


def _make_page(url="/forum/test", html=b"<html><body><p>X</p></body></html>"):
    return PageRecord(
        page_id=1, url=url, canonical_url=url, html=html,
        fetched_at=1700000000, http_status=200, scrape_context="user"
    )


def _make_bundle(page=None, annotation_id=1, viewport_saved=2):
    bundle = MagicMock()
    bundle.forensic.get_page.return_value        = page
    bundle.forensic.resolve_post_alias.return_value  = None
    bundle.forensic.resolve_notify_alias.return_value = None
    bundle.forensic.get_trace_elements_for_page.return_value = []
    bundle.forensic.get_meta.return_value        = None   # forum_hostname → None
    bundle.forensic.page_count.return_value      = 100
    bundle.evidence.save_annotation.return_value = annotation_id
    bundle.evidence.save_viewport_batch.return_value = viewport_saved
    bundle.evidence.annotation_count.return_value = 5
    bundle.evidence.log_page_visit.return_value  = 1
    return bundle


def _make_context():
    ctx = MagicMock()
    ctx.mode           = "cli"
    ctx.user_id        = 42
    ctx.username       = "testnutzer"
    ctx.investigator_id = 1
    return ctx


def _make_handler(body: bytes = b"") -> MagicMock:
    """Mock-Handler mit rfile und Capture-Mechanismus."""
    import io
    handler = MagicMock()
    handler.command = "GET"
    handler.rfile   = io.BytesIO(body)
    handler.headers = {"Content-Length": str(len(body))}
    captured = {}
    def capture(status, body, content_type=None, extra_headers=None):
        captured["status"]       = status
        captured["body"]         = body
        captured["content_type"] = content_type
    handler.send_response_body.side_effect = capture
    handler._captured = captured
    return handler


def _dispatch(api, method, path, query="", body=b""):
    """Hilfsfunktion: ruft api.dispatch() auf und gibt Response-Dict zurück."""
    handler = _make_handler(body)
    handler.command = method
    handler.headers = {"Content-Length": str(len(body))}
    import io
    handler.rfile = io.BytesIO(body)
    api.dispatch(handler, method, path, query, is_ajax=True)
    return handler._captured


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestForensicApiPage(unittest.TestCase):
    """T01–T03: /_forensic/page"""

    def setUp(self):
        self.cfg = _setup_logging_and_config()
        self.ctx = _make_context()

    def tearDown(self):
        reset_for_testing()

    def test_T01_bekannte_url(self):
        """T01: Bekannte URL → JSON-Envelope mit in_scope=True."""
        bundle = _make_bundle(page=_make_page())
        api    = ForensicApi(bundle, self.ctx, self.cfg)
        resp   = _dispatch(api, "GET", "/_forensic/page",
                           "url=%2Fforum%2Ftest")
        env = json.loads(resp["body"])
        self.assertTrue(env["in_scope"])
        self.assertFalse(env["fetch_failed"])

    def test_T02_url_parameter_fehlt(self):
        """T02: url-Parameter fehlt → HTTP 400."""
        bundle = _make_bundle()
        api    = ForensicApi(bundle, self.ctx, self.cfg)
        resp   = _dispatch(api, "GET", "/_forensic/page", "")
        self.assertEqual(resp["status"], 400)

    def test_T03_unbekannte_url(self):
        """T03: Unbekannte URL → in_scope=False."""
        bundle = _make_bundle(page=None)
        api    = ForensicApi(bundle, self.ctx, self.cfg)
        resp   = _dispatch(api, "GET", "/_forensic/page",
                           "url=%2Fforum%2Funbekannt")
        env = json.loads(resp["body"])
        self.assertFalse(env["in_scope"])


class TestForensicApiAnnotate(unittest.TestCase):
    """T04–T07, T17: /_forensic/annotate"""

    def setUp(self):
        self.cfg = _setup_logging_and_config()
        self.ctx = _make_context()

    def tearDown(self):
        reset_for_testing()

    def _post_annotation(self, data: dict):
        bundle = _make_bundle()
        api    = ForensicApi(bundle, self.ctx, self.cfg)
        body   = json.dumps(data).encode("utf-8")
        return _dispatch(api, "POST", "/_forensic/annotate", "", body)

    def test_T04_gueltige_annotation(self):
        """T04: Gültige Annotation → HTTP 200, id im Response."""
        resp = self._post_annotation({
            "page_url":  "/forum/viewtopic.php?id=42",
            "category":  "CAT_PERSON",
            "text":      "Testnotiz",
        })
        self.assertEqual(resp["status"], 200)
        result = json.loads(resp["body"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("id", result)

    def test_T05_ungueltige_kategorie(self):
        """T05: Ungültige Kategorie → HTTP 400."""
        resp = self._post_annotation({
            "page_url": "/forum/x",
            "category": "CAT_UNGUELTIG",
            "text":     "test",
        })
        self.assertEqual(resp["status"], 400)

    def test_T06_page_url_fehlt(self):
        """T06: page_url fehlt → HTTP 400."""
        resp = self._post_annotation({"category": "CAT_OTHER", "text": "x"})
        self.assertEqual(resp["status"], 400)

    def test_T07_ungültiges_json(self):
        """T07: Ungültiges JSON im Body → HTTP 400."""
        bundle = _make_bundle()
        api    = ForensicApi(bundle, self.ctx, self.cfg)
        resp   = _dispatch(api, "POST", "/_forensic/annotate", "", b"kein json!")
        self.assertEqual(resp["status"], 400)

    def test_T17_alle_kategorien(self):
        """T17: Alle sechs VALID_CATEGORIES werden akzeptiert."""
        for cat in VALID_CATEGORIES:
            resp = self._post_annotation({
                "page_url": "/forum/x",
                "category": cat,
                "text":     f"Test {cat}",
            })
            self.assertEqual(
                resp["status"], 200,
                f"Kategorie {cat} wurde nicht akzeptiert"
            )


class TestForensicApiStatus(unittest.TestCase):
    """T08: /_forensic/status"""

    def setUp(self):
        self.cfg = _setup_logging_and_config()
        self.ctx = _make_context()

    def tearDown(self):
        reset_for_testing()

    def test_T08_status_response(self):
        """T08: /_forensic/status liefert JSON mit version, mode, user_id."""
        bundle = _make_bundle()
        api    = ForensicApi(bundle, self.ctx, self.cfg)
        resp   = _dispatch(api, "GET", "/_forensic/status")
        self.assertEqual(resp["status"], 200)
        data = json.loads(resp["body"])
        self.assertIn("version", data)
        self.assertIn("mode", data)
        self.assertEqual(data["user_id"], 42)
        self.assertEqual(data["username"], "testnutzer")


class TestForensicApiViewport(unittest.TestCase):
    """T09–T11, T18: /_forensic/viewport"""

    def setUp(self):
        self.cfg = _setup_logging_and_config()
        self.ctx = _make_context()

    def tearDown(self):
        reset_for_testing()

    def _post_viewport(self, data: dict):
        bundle = _make_bundle(viewport_saved=len(data.get("events", [])))
        api    = ForensicApi(bundle, self.ctx, self.cfg)
        body   = json.dumps(data).encode("utf-8")
        return _dispatch(api, "POST", "/_forensic/viewport", "", body)

    def test_T09_gueltiger_batch(self):
        """T09: Gültiger Batch → HTTP 200, saved=N."""
        events = [
            {"element_id": "p1", "visible_ms": 1000,
             "ts_enter": 1000, "ts_leave": 2000},
            {"element_id": "p2", "visible_ms": 500,
             "ts_enter": 2000, "ts_leave": 2500},
        ]
        resp = self._post_viewport({"page_url": "/forum/x", "events": events})
        self.assertEqual(resp["status"], 200)
        result = json.loads(resp["body"])
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["saved"], 0)

    def test_T10_leerer_batch(self):
        """T10: Leerer Batch → HTTP 200, saved=0."""
        resp = self._post_viewport({"page_url": "/forum/x", "events": []})
        self.assertEqual(resp["status"], 200)
        self.assertEqual(json.loads(resp["body"])["saved"], 0)

    def test_T11_page_url_fehlt(self):
        """T11: page_url fehlt → HTTP 400."""
        bundle = _make_bundle()
        api    = ForensicApi(bundle, self.ctx, self.cfg)
        body   = json.dumps({"events": []}).encode("utf-8")
        resp   = _dispatch(api, "POST", "/_forensic/viewport", "", body)
        self.assertEqual(resp["status"], 400)


class TestForensicApiStatic(unittest.TestCase):
    """T12–T13: toolbar.js / toolbar.css"""

    def setUp(self):
        self.cfg = _setup_logging_and_config()
        self.ctx = _make_context()

    def tearDown(self):
        reset_for_testing()

    def test_T12_toolbar_js(self):
        """T12: /_forensic/toolbar.js → HTTP 200, JavaScript."""
        bundle = _make_bundle()
        api    = ForensicApi(bundle, self.ctx, self.cfg)
        resp   = _dispatch(api, "GET", "/_forensic/toolbar.js")
        self.assertEqual(resp["status"], 200)
        self.assertIn("javascript", resp.get("content_type", ""))

    def test_T13_toolbar_css(self):
        """T13: /_forensic/toolbar.css → HTTP 200, CSS."""
        bundle = _make_bundle()
        api    = ForensicApi(bundle, self.ctx, self.cfg)
        resp   = _dispatch(api, "GET", "/_forensic/toolbar.css")
        self.assertEqual(resp["status"], 200)
        self.assertIn("css", resp.get("content_type", ""))


class TestForensicApiMethodChecks(unittest.TestCase):
    """T14–T16: Methoden-Validierung und unbekannte Endpunkte"""

    def setUp(self):
        self.cfg = _setup_logging_and_config()
        self.ctx = _make_context()

    def tearDown(self):
        reset_for_testing()

    def test_T14_get_auf_annotate(self):
        """T14: GET auf /_forensic/annotate → HTTP 405."""
        bundle = _make_bundle()
        api    = ForensicApi(bundle, self.ctx, self.cfg)
        resp   = _dispatch(api, "GET", "/_forensic/annotate")
        self.assertEqual(resp["status"], 405)

    def test_T15_post_auf_status(self):
        """T15: POST auf /_forensic/status → HTTP 405."""
        bundle = _make_bundle()
        api    = ForensicApi(bundle, self.ctx, self.cfg)
        resp   = _dispatch(api, "POST", "/_forensic/status")
        self.assertEqual(resp["status"], 405)

    def test_T16_unbekannter_endpunkt(self):
        """T16: Unbekannter /_forensic/-Endpunkt → HTTP 404."""
        bundle = _make_bundle()
        api    = ForensicApi(bundle, self.ctx, self.cfg)
        resp   = _dispatch(api, "GET", "/_forensic/nichtvorhanden")
        self.assertEqual(resp["status"], 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)

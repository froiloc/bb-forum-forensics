# =============================================================================
# tests/test_blob_handler.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite für server/blob_handler.py
#
# T01 — Bekannte URL: JSON-Envelope mit html, scrape_context, in_scope=True
# T02 — Unbekannte URL: in_scope=False im Envelope
# T03 — html IS NULL: fetch_failed=True im Envelope
# T04 — scrape_context='investigator' im Envelope
# T05 — ?pid=<post_id> wird über post_aliases aufgelöst
# T06 — ?notify=<id> wird über notify_aliases aufgelöst
# T07 — Fragment-Anker wird im Envelope zurückgegeben
# T08 — page_visit wird nach erfolgreichem Lookup protokolliert
# T09 — page_visit wird bei NOT_IN_SCOPE NICHT protokolliert
# T10 — _extract_body(): <body>-Inhalt korrekt extrahiert
# T11 — _extract_body(): HTML ohne <body>-Tag wird vollständig zurückgegeben
# T12 — JSON-Envelope ist valides JSON
#
# Version: v0.1.0 · Build: 008 · 2026-04-10
# =============================================================================

import sys
import os
import json
import sqlite3
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import setup_logging, reset_for_testing
from core.config_loader import ConfigLoader
from db.forensic_db import PageRecord
from server.blob_handler import BlobHandler


def _setup_logging_and_config() -> ConfigLoader:
    reset_for_testing()
    tmp = tempfile.mkdtemp()
    config_path = os.path.join(tmp, "config.yaml")
    logfile = os.path.join(tmp, "logs", "test.log")
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


def _make_page(
    url="/forum/viewtopic.php?id=100",
    html=b"<html><body><p>Inhalt</p></body></html>",
    scrape_context="user",
    http_status=200,
) -> PageRecord:
    return PageRecord(
        page_id=1,
        url=url,
        html=html,
        fetched_at=1700000000,
        http_status=http_status,
        scrape_context=scrape_context,
    )


def _make_bundle(page=None, post_alias=None, notify_alias=None):
    bundle = MagicMock()
    bundle.forensic.get_page.return_value = page
    bundle.forensic.resolve_post_alias.return_value = post_alias
    bundle.forensic.resolve_notify_alias.return_value = notify_alias
    bundle.evidence.log_page_visit.return_value = 1
    return bundle


def _make_context():
    ctx = MagicMock()
    ctx.investigator_id = 1
    return ctx


def _make_handler():
    handler = MagicMock()
    handler.command = "GET"
    captured = {}
    def capture_response(status, body, content_type=None, extra_headers=None):
        captured["status"] = status
        captured["body"]   = body
    handler.send_response_body.side_effect = capture_response
    handler._captured = captured
    return handler


class TestBlobHandlerEnvelope(unittest.TestCase):
    """T01–T04: JSON-Envelope-Inhalte"""

    def setUp(self):
        self.cfg = _setup_logging_and_config()
        self.ctx = _make_context()

    def tearDown(self):
        reset_for_testing()

    def _call_handle(self, bundle, url):
        bh = BlobHandler(bundle, self.ctx, self.cfg)
        handler = _make_handler()
        bh.handle(handler, url)
        return json.loads(handler._captured["body"])

    def test_T01_bekannte_url(self):
        """T01: Bekannte URL → in_scope=True, html vorhanden."""
        page   = _make_page()
        bundle = _make_bundle(page=page)
        env    = self._call_handle(bundle, "/forum/viewtopic.php?id=100")
        self.assertTrue(env["in_scope"])
        self.assertFalse(env["fetch_failed"])
        self.assertEqual(env["scrape_context"], "user")
        self.assertEqual(env["http_status"], 200)
        self.assertIsNotNone(env["html"])

    def test_T02_unbekannte_url(self):
        """T02: Unbekannte URL → in_scope=False."""
        bundle = _make_bundle(page=None)
        env    = self._call_handle(bundle, "/forum/viewtopic.php?id=9999")
        self.assertFalse(env["in_scope"])
        self.assertTrue(env["fetch_failed"])

    def test_T03_fetch_failed(self):
        """T03: html IS NULL → fetch_failed=True."""
        page   = _make_page(html=None, http_status=403)
        bundle = _make_bundle(page=page)
        env    = self._call_handle(bundle, "/forum/viewtopic.php?id=200")
        self.assertTrue(env["in_scope"])
        self.assertTrue(env["fetch_failed"])
        self.assertEqual(env["http_status"], 403)
        self.assertIsNone(env["html"])

    def test_T04_scrape_context_investigator(self):
        """T04: scrape_context='investigator' wird im Envelope zurückgegeben."""
        page   = _make_page(scrape_context="investigator")
        bundle = _make_bundle(page=page)
        env    = self._call_handle(bundle, "/forum/viewtopic.php?id=200")
        self.assertEqual(env["scrape_context"], "investigator")


class TestBlobHandlerAliases(unittest.TestCase):
    """T05–T07: Alias-Auflösung"""

    def setUp(self):
        self.cfg = _setup_logging_and_config()
        self.ctx = _make_context()

    def tearDown(self):
        reset_for_testing()

    def test_T05_pid_aufloesen(self):
        """T05: ?pid=12345 wird über post_aliases auf topic aufgelöst."""
        from db.forensic_db import PostAliasRecord
        post_alias = PostAliasRecord(post_id=12345, topic_id=100, forum_id=5)
        page       = _make_page(url="/forum/viewtopic.php?id=100")

        bundle = MagicMock()
        bundle.forensic.resolve_post_alias.return_value = post_alias
        bundle.forensic.get_page.return_value = page
        bundle.evidence.log_page_visit.return_value = 1

        bh      = BlobHandler(bundle, self.ctx, self.cfg)
        handler = _make_handler()
        bh.handle(handler, "/forum/viewtopic.php?pid=12345")
        env = json.loads(handler._captured["body"])

        # get_page sollte mit der aufgelösten Topic-URL aufgerufen worden sein
        bundle.forensic.get_page.assert_called_with("/forum/viewtopic.php?id=100")
        self.assertEqual(env["fragment"], "p12345")

    def test_T06_notify_aufloesen(self):
        """T06: ?notify=9001 wird über notify_aliases aufgelöst."""
        from db.forensic_db import NotifyAliasRecord, PostAliasRecord
        notify_alias = NotifyAliasRecord(notify_id=9001, post_id=12345)
        post_alias   = PostAliasRecord(post_id=12345, topic_id=100, forum_id=5)
        page         = _make_page(url="/forum/viewtopic.php?id=100")

        bundle = MagicMock()
        bundle.forensic.resolve_notify_alias.return_value = notify_alias
        bundle.forensic.resolve_post_alias.return_value   = post_alias
        bundle.forensic.get_page.return_value = page
        bundle.evidence.log_page_visit.return_value = 1

        bh      = BlobHandler(bundle, self.ctx, self.cfg)
        handler = _make_handler()
        bh.handle(handler, "/forum/viewtopic.php?notify=9001")
        env = json.loads(handler._captured["body"])

        self.assertTrue(env["in_scope"])
        self.assertEqual(env["fragment"], "p12345")

    def test_T07_fragment_im_envelope(self):
        """T07: Fragment-Anker wird korrekt im Envelope zurückgegeben."""
        page   = _make_page()
        bundle = _make_bundle(page=page)
        bh     = BlobHandler(bundle, self.ctx, self.cfg)
        handler = _make_handler()
        bh.handle_with_fragment(
            handler, "/forum/viewtopic.php?id=100", fragment="p99"
        )
        env = json.loads(handler._captured["body"])
        self.assertEqual(env["fragment"], "p99")


class TestBlobHandlerPageVisit(unittest.TestCase):
    """T08–T09: page_visit-Protokollierung"""

    def setUp(self):
        self.cfg = _setup_logging_and_config()
        self.ctx = _make_context()

    def tearDown(self):
        reset_for_testing()

    def test_T08_page_visit_bei_treffer(self):
        """T08: page_visit wird nach erfolgreichem Lookup protokolliert."""
        page   = _make_page()
        bundle = _make_bundle(page=page)
        bh     = BlobHandler(bundle, self.ctx, self.cfg)
        bh.handle(_make_handler(), "/forum/viewtopic.php?id=100")
        bundle.evidence.log_page_visit.assert_called_once()

    def test_T09_kein_page_visit_bei_not_in_scope(self):
        """T09: page_visit wird bei NOT_IN_SCOPE nicht protokolliert."""
        bundle = _make_bundle(page=None)
        bh     = BlobHandler(bundle, self.ctx, self.cfg)
        bh.handle(_make_handler(), "/forum/viewtopic.php?id=9999")
        bundle.evidence.log_page_visit.assert_not_called()


class TestBlobHandlerExtractBody(unittest.TestCase):
    """T10–T12: _extract_body() und JSON-Validität"""

    def setUp(self):
        self.cfg = _setup_logging_and_config()

    def tearDown(self):
        reset_for_testing()

    def test_T10_extract_body_normal(self):
        """T10: <body>-Inhalt wird korrekt extrahiert."""
        html = b"<html><head><title>Test</title></head><body><p>Inhalt</p></body></html>"
        result = BlobHandler._extract_body(html)
        self.assertIn("<p>Inhalt</p>", result)
        self.assertNotIn("<head>", result)
        self.assertNotIn("</body>", result)

    def test_T11_extract_body_kein_body_tag(self):
        """T11: HTML ohne <body>-Tag wird vollständig zurückgegeben."""
        html = b"<p>Kein Body-Tag</p>"
        result = BlobHandler._extract_body(html)
        self.assertIn("<p>Kein Body-Tag</p>", result)

    def test_T12_json_valide(self):
        """T12: Der JSON-Envelope ist immer valides JSON."""
        page   = _make_page()
        bundle = _make_bundle(page=page)
        ctx    = _make_context()
        bh     = BlobHandler(bundle, ctx, self.cfg)
        handler = _make_handler()
        bh.handle(handler, "/forum/viewtopic.php?id=100")
        # json.loads wirft bei ungültigem JSON eine Exception
        envelope = json.loads(handler._captured["body"])
        self.assertIn("in_scope", envelope)
        self.assertIn("html", envelope)
        self.assertIn("scrape_context", envelope)


if __name__ == "__main__":
    unittest.main(verbosity=2)

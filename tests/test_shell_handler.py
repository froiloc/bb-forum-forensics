# =============================================================================
# tests/test_shell_handler.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite für server/shell_handler.py
#
# T01 — Bekannte URL mit html: Shell-HTML mit Status 200
# T02 — Unbekannte URL: Status 404 + X-Forensic-Status: NOT_IN_SCOPE
# T03 — html IS NULL: Shell trotzdem ausgeliefert (Status 200)
# T04 — Shell enthält #forensic-toolbar
# T05 — Shell enthält #forensic-viewport
# T06 — Shell enthält toolbar.css-Einbindung
# T07 — Shell enthält toolbar.js-Einbindung
# T08 — Shell enthält extrahierten <title> aus BLOB
# T09 — Shell enthält <base href> aus BLOB
# T10 — Shell enthält Forum-CSS-Link aus BLOB
# T11 — page_visit wird NICHT in shell_handler protokolliert
#
# Version: v0.1.0 · Build: 008 · 2026-04-10
# =============================================================================

import sys
import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import setup_logging, reset_for_testing
from core.config_loader import ConfigLoader
from db.forensic_db import PageRecord
from server.shell_handler import ShellHandler


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
        """))
    cfg = ConfigLoader(config_path=config_path)
    setup_logging(cfg)
    return cfg


_SAMPLE_HTML = b"""<!DOCTYPE html>
<html><head>
<base href="https://forum.example.org/forum/">
<title>Testtopic - Forum</title>
<link rel="stylesheet" href="/forum/style/main.css">
</head><body>
<div id="pun-wrap"><p>Forum-Inhalt hier</p></div>
</body></html>"""


def _make_page(html=_SAMPLE_HTML, scrape_context="user"):
    return PageRecord(
        page_id=1,
        url="/forum/viewtopic.php?id=100",
        html=html,
        fetched_at=1700000000,
        http_status=200,
        scrape_context=scrape_context,
    )


def _make_bundle(page=None):
    bundle = MagicMock()
    bundle.forensic.get_page.return_value = page
    bundle.evidence.log_page_visit.return_value = 1
    return bundle


def _make_context():
    ctx = MagicMock()
    ctx.investigator_id = 1
    return ctx


def _capture_shell(bundle, url, cfg) -> tuple[int, str, dict]:
    """Ruft ShellHandler.handle() auf und gibt (status, html_str, headers) zurück."""
    ctx     = _make_context()
    handler = MagicMock()
    handler.command = "GET"
    captured = {}
    def capture(status, body, content_type=None, extra_headers=None):
        captured["status"]  = status
        captured["body"]    = body
        captured["headers"] = extra_headers or {}
    handler.send_response_body.side_effect = capture

    sh = ShellHandler(bundle, ctx, cfg)
    sh.handle(handler, url)
    return (
        captured.get("status", 0),
        captured.get("body", b"").decode("utf-8", errors="replace"),
        captured.get("headers", {}),
    )


class TestShellHandlerStatus(unittest.TestCase):
    """T01–T03: HTTP-Status"""

    def setUp(self):
        self.cfg = _setup_logging_and_config()

    def tearDown(self):
        reset_for_testing()

    def test_T01_bekannte_url_200(self):
        """T01: Bekannte URL mit html → HTTP 200."""
        status, _, _ = _capture_shell(
            _make_bundle(_make_page()), "/forum/viewtopic.php?id=100", self.cfg
        )
        self.assertEqual(status, 200)

    def test_T02_unbekannte_url_404(self):
        """T02: Unbekannte URL → HTTP 404 + NOT_IN_SCOPE-Header."""
        status, _, headers = _capture_shell(
            _make_bundle(None), "/forum/viewtopic.php?id=9999", self.cfg
        )
        self.assertEqual(status, 404)
        self.assertEqual(headers.get("X-Forensic-Status"), "NOT_IN_SCOPE")

    def test_T03_html_null_trotzdem_200(self):
        """T03: html IS NULL (fetch_failed) → Shell trotzdem mit HTTP 200."""
        status, _, _ = _capture_shell(
            _make_bundle(_make_page(html=None)), "/forum/viewtopic.php?id=200", self.cfg
        )
        self.assertEqual(status, 200)


class TestShellHandlerStructure(unittest.TestCase):
    """T04–T10: Shell-HTML-Struktur"""

    def setUp(self):
        self.cfg = _setup_logging_and_config()
        self.bundle = _make_bundle(_make_page())

    def tearDown(self):
        reset_for_testing()

    def _get_html(self) -> str:
        _, html, _ = _capture_shell(
            self.bundle, "/forum/viewtopic.php?id=100", self.cfg
        )
        return html

    def test_T04_forensic_toolbar(self):
        """T04: Shell enthält #forensic-toolbar."""
        self.assertIn('id="forensic-toolbar"', self._get_html())

    def test_T05_forensic_viewport(self):
        """T05: Shell enthält #forensic-viewport."""
        self.assertIn('id="forensic-viewport"', self._get_html())

    def test_T06_toolbar_css(self):
        """T06: Shell enthält toolbar.css-Einbindung."""
        self.assertIn("/_forensic/toolbar.css", self._get_html())

    def test_T07_toolbar_js(self):
        """T07: Shell enthält toolbar.js-Einbindung."""
        self.assertIn("/_forensic/toolbar.js", self._get_html())

    def test_T08_titel_aus_blob(self):
        """T08: Shell enthält extrahierten <title> aus dem BLOB."""
        html = self._get_html()
        self.assertIn("Testtopic", html)
        self.assertIn("<title>", html)

    def test_T09_base_href_aus_blob(self):
        """T09: Shell enthält <base href> aus dem BLOB."""
        self.assertIn("forum.example.org", self._get_html())

    def test_T10_css_link_aus_blob(self):
        """T10: Shell enthält Forum-CSS-Link aus dem BLOB."""
        self.assertIn("/forum/style/main.css", self._get_html())


class TestShellHandlerNoPageVisit(unittest.TestCase):
    """T11: page_visit nicht in shell_handler"""

    def setUp(self):
        self.cfg = _setup_logging_and_config()

    def tearDown(self):
        reset_for_testing()

    def test_T11_kein_page_visit(self):
        """T11: shell_handler protokolliert keinen page_visit."""
        bundle = _make_bundle(_make_page())
        _capture_shell(bundle, "/forum/viewtopic.php?id=100", self.cfg)
        bundle.evidence.log_page_visit.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)

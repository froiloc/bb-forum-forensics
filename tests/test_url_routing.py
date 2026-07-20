# =============================================================================
# tests/test_url_routing.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite für server/router.py (URL-Routing-Logik)
#
# T01 — POST außerhalb /_forensic/ → 404
# T02 — GET /_forensic/status → Forensik-API dispatch
# T03 — GET /_forensic/page?url=... → Forensik-API dispatch
# T04 — GET Asset-URL → asset_handler
# T05 — GET Forum-URL ohne AJAX-Header → shell_handler
# T06 — GET Forum-URL mit AJAX-Header → blob_handler
# T07 — POST auf /_forensic/annotate → Forensik-API (erlaubt)
# T08 — _build_canonical_url: mit Query-String
# T09 — _build_canonical_url: ohne Query-String
# T10 — _is_asset_url: konfigurierte Präfixe erkannt
# T11 — _is_asset_url: unbekannte URL gibt False zurück
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import sys
import os
import io
import json
import sqlite3
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import setup_logging, reset_for_testing
from core.config_loader import ConfigLoader
from server.router import Router, FORENSIC_API_PREFIX


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
                - "/forum/img/"
              alias_patterns:
                post_id_param: "pid"
                notify_param: "notify"
                fragment_post: "p"
        """))
    cfg = ConfigLoader(config_path=config_path)
    setup_logging(cfg)
    return cfg


def _make_mock_bundle():
    """Erstellt ein Mock-DatabaseBundle für Router-Tests."""
    bundle = MagicMock()
    bundle.forensic.get_page.return_value = None
    bundle.default.get_asset.return_value = None
    bundle.evidence.log_page_visit.return_value = 1
    return bundle


def _make_mock_context():
    context = MagicMock()
    context.mode = "cli"
    context.subject_id = 42
    context.username = "testuser"
    context.investigator_id = 1
    return context


def _make_mock_handler() -> MagicMock:
    """Erstellt einen Mock-ForensicRequestHandler."""
    handler = MagicMock()
    handler.command = "GET"
    return handler


class TestRouterDispatch(unittest.TestCase):
    """T01–T07: dispatch()-Routing-Entscheidungen"""

    def setUp(self):
        self.cfg     = _setup_logging_and_config()
        self.bundle  = _make_mock_bundle()
        self.context = _make_mock_context()
        self.router  = Router(self.bundle, self.context, self.cfg)

    def tearDown(self):
        reset_for_testing()

    def test_T01_post_ausserhalb_forensic_404(self):
        """T01: POST außerhalb /_forensic/ → HTTP 404."""
        handler = _make_mock_handler()
        handler.command = "POST"
        self.router.dispatch(handler, "POST", "/forum/viewtopic.php?id=1", False)
        handler.send_response_body.assert_called_once()
        args, kwargs = handler.send_response_body.call_args
        self.assertEqual(args[0], 404)

    def test_T02_forensic_status(self):
        """T02: GET /_forensic/status → ForensicApi.dispatch() aufgerufen."""
        handler = _make_mock_handler()
        # ForensicApi mocken um dispatch-Aufruf zu prüfen
        mock_api = MagicMock()
        self.router._forensic_api = mock_api
        self.router.dispatch(handler, "GET", "/_forensic/status", False)
        mock_api.dispatch.assert_called_once()
        call_kwargs = mock_api.dispatch.call_args[1]
        self.assertEqual(call_kwargs["url_path"], "/_forensic/status")

    def test_T03_forensic_page(self):
        """T03: GET /_forensic/page?url=... → ForensicApi.dispatch() aufgerufen."""
        handler = _make_mock_handler()
        mock_api = MagicMock()
        self.router._forensic_api = mock_api
        self.router.dispatch(
            handler, "GET", "/_forensic/page?url=/forum/viewtopic.php?id=42", False
        )
        mock_api.dispatch.assert_called_once()

    def test_T04_asset_url(self):
        """T04: GET Asset-URL → asset_handler aufgerufen."""
        handler  = _make_mock_handler()
        mock_ah  = MagicMock()
        self.router._asset_handler = mock_ah
        self.router.dispatch(handler, "GET", "/forum/style/main.css", False)
        mock_ah.handle.assert_called_once_with(handler, "/forum/style/main.css")

    def test_T05_forum_shell_request(self):
        """T05: GET Forum-URL ohne AJAX-Header → shell_handler aufgerufen."""
        handler = _make_mock_handler()
        mock_sh = MagicMock()
        self.router._shell_handler = mock_sh
        self.router.dispatch(
            handler, "GET", "/forum/viewtopic.php?id=100", is_ajax=False
        )
        mock_sh.handle.assert_called_once_with(handler, "/forum/viewtopic.php?id=100")

    def test_T06_forum_ajax_request(self):
        """T06: GET Forum-URL mit AJAX-Header → blob_handler aufgerufen."""
        handler = _make_mock_handler()
        mock_bh = MagicMock()
        self.router._blob_handler = mock_bh
        self.router.dispatch(
            handler, "GET", "/forum/viewtopic.php?id=100", is_ajax=True
        )
        mock_bh.handle.assert_called_once_with(handler, "/forum/viewtopic.php?id=100")

    def test_T07_post_auf_forensic_erlaubt(self):
        """T07: POST auf /_forensic/annotate → ForensicApi.dispatch() (nicht blockiert)."""
        handler  = _make_mock_handler()
        handler.command = "POST"
        mock_api = MagicMock()
        self.router._forensic_api = mock_api
        self.router.dispatch(handler, "POST", "/_forensic/annotate", False)
        mock_api.dispatch.assert_called_once()


class TestRouterHelpers(unittest.TestCase):
    """T08–T11: Hilfsmethoden"""

    def setUp(self):
        self.cfg     = _setup_logging_and_config()
        self.bundle  = _make_mock_bundle()
        self.context = _make_mock_context()
        self.router  = Router(self.bundle, self.context, self.cfg)

    def tearDown(self):
        reset_for_testing()

    def test_T08_canonical_url_mit_query(self):
        """T08: _build_canonical_url() mit Query-String."""
        result = Router._build_canonical_url("/forum/viewtopic.php", "id=42")
        self.assertEqual(result, "/forum/viewtopic.php?id=42")

    def test_T09_canonical_url_ohne_query(self):
        """T09: _build_canonical_url() ohne Query-String."""
        result = Router._build_canonical_url("/forum/index.php", "")
        self.assertEqual(result, "/forum/index.php")

    def test_T10_is_asset_url_bekannt(self):
        """T10: Konfigurierte Asset-Präfixe werden erkannt."""
        self.assertTrue(self.router._is_asset_url("/forum/style/main.css"))
        self.assertTrue(self.router._is_asset_url("/forum/img/logo.png"))
        self.assertFalse(self.router._is_asset_url("/forum/extensions/plugin.php"))

    def test_T11_is_asset_url_unbekannt(self):
        """T11: Unbekannte URL gibt False zurück."""
        self.assertFalse(self.router._is_asset_url("/forum/viewtopic.php"))
        self.assertFalse(self.router._is_asset_url("/forum/profile.php"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

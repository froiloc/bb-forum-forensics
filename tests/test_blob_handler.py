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
# Build 699 (Vorgang f5956e6b) — Beitragsanker in mehrseitigen Themen:
# T23 — ?pid=<id> liefert die GEMESSENE Seite (post_aliases.page), nicht Seite 1
# T24 — ?pid=<id> ohne belegbare Seite → Rueckfall Seite 1, fragment_source
#       'unaufgeloest' (kein stiller Rueckfall, Grundregel 1)
# T25 — ?id=<topic>#p<id>: Anker steht NICHT im ersten Chunk → es wird die
#       Seite ausgeliefert, die ihn traegt
# T26 — ?id=<topic>#p<id>: Anker steht im BLOB → keine Umleitung,
#       fragment_source 'bestaetigt'
# T27 — Anker auf einer Nicht-Themenseite loest KEINE Umleitung aus
# T28 — fehlender BLOB (fetch_failed) → 'unpruefbar', keine Umleitung
# T29 — Envelope ohne Beitragsanker traegt fragment_source=None
# T30 — ?notify=<id> nutzt ebenfalls die Seite des Beitrags
#
# Version: v0.1.1 · Build: 699 · 2026-08-12
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
    canonical_url=None,
    html=b"<html><body><p>Inhalt</p></body></html>",
    scrape_context="user",
    http_status=200,
    method="GET",
) -> PageRecord:
    # Wenn kein canonical_url angegeben, Verzeichnispfad aus url ableiten
    if canonical_url is None:
        canonical_url = url
    return PageRecord(
        page_id=1,
        url=url,
        canonical_url=canonical_url,
        html=html,
        fetched_at=1700000000,
        http_status=http_status,
        scrape_context=scrape_context,
        method=method,
    )


def _make_bundle(page=None, post_alias=None, notify_alias=None,
                 post_page=None):
    bundle = MagicMock()
    bundle.forensic.get_page.return_value = page
    bundle.forensic.resolve_post_alias.return_value = post_alias
    bundle.forensic.resolve_notify_alias.return_value = notify_alias
    # Build 699: MUSS gesetzt werden. Ein MagicMock liefert sonst fuer JEDEN
    # Aufruf ein Mock-Objekt statt None — die Ankerprobe hielte das fuer eine
    # gefundene Seite und der Test pruefte eine Lage, die es nicht gibt.
    bundle.forensic.resolve_post_page.return_value = post_page
    bundle.forensic.get_trace_elements_for_page.return_value = []
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
        """T05: ?pid=12345 wird auf die Seite aufgelöst, die den Beitrag traegt.

        MITGEZOGEN IN BUILD 699 (Vorgang f5956e6b): Bis Build 698 pruefte
        dieser Fall, dass '?pid=' auf '<pfad>?id=<topic_id>' abgebildet wird —
        also auf den ERSTEN Chunk des Themas. Genau das war der gemeldete
        Fehler. Der Fall pruefet weiterhin die pid-Aufloesung, jetzt aber
        gegen die Seite, die den Beitrag traegt. Der einseitige Fall ist
        unveraendert: dort IST die Seite des Beitrags die erste.
        """
        from db.forensic_db import PostPageRecord
        post_page = PostPageRecord(post_id=12345, page_id=1,
                                   url="/forum/viewtopic.php?id=100",
                                   quelle="gemessen")
        page = _make_page(
            url="/forum/viewtopic.php?id=100",
            html=b'<html><body><div id="p12345">Beitrag</div></body></html>',
        )
        bundle = _make_bundle(page=page, post_page=post_page)

        bh      = BlobHandler(bundle, self.ctx, self.cfg)
        handler = _make_handler()
        bh.handle(handler, "/forum/viewtopic.php?pid=12345")
        env = json.loads(handler._captured["body"])

        # get_page mit der Seite des Beitrags und method='GET'.
        # Beleg: Projektgespräch 2026-04-19 — get_page() hat method-Parameter.
        bundle.forensic.get_page.assert_called_with(
            "/forum/viewtopic.php?id=100", method="GET"
        )
        bundle.forensic.resolve_post_page.assert_called_with(12345)
        self.assertEqual(env["fragment"], "p12345")
        self.assertEqual(env["fragment_source"], "gemessen")

    def test_T06_notify_aufloesen(self):
        """T06: ?notify=9001 wird über notify_aliases aufgelöst."""
        from db.forensic_db import NotifyAliasRecord, PostPageRecord
        notify_alias = NotifyAliasRecord(notify_id=9001, post_id=12345)
        post_page    = PostPageRecord(post_id=12345, page_id=1,
                                      url="/forum/viewtopic.php?id=100",
                                      quelle="gemessen")
        page = _make_page(
            url="/forum/viewtopic.php?id=100",
            html=b'<html><body><div id="p12345">Beitrag</div></body></html>',
        )
        bundle = _make_bundle(page=page, notify_alias=notify_alias,
                              post_page=post_page)

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


class TestBlobHandlerHead(unittest.TestCase):
    """T13–T18: head-Feld im JSON-Envelope (Build 019/023)"""

    def setUp(self):
        self.cfg = _setup_logging_and_config()
        self.ctx = _make_context()

    def tearDown(self):
        reset_for_testing()

    def _call(self, bundle, url):
        bh = BlobHandler(bundle, self.ctx, self.cfg)
        handler = _make_handler()
        bh.handle(handler, url)
        return json.loads(handler._captured["body"])

    def test_T13_head_feld_vorhanden(self):
        """T13: Envelope enthält 'head'-Feld bei bekannter Seite."""
        page = _make_page(
            html=b"<html><head><title>Test</title></head><body>x</body></html>"
        )
        env = self._call(_make_bundle(page=page), "/forum/viewtopic.php?id=100")
        self.assertIn("head", env)
        self.assertIsNotNone(env["head"])

    def test_T14_head_title(self):
        """T14: head.title wird korrekt extrahiert."""
        page = _make_page(
            html=b"<html><head><title>Mein Titel</title></head><body>x</body></html>"
        )
        env = self._call(_make_bundle(page=page), "/forum/viewtopic.php?id=100")
        self.assertEqual(env["head"]["title"], "Mein Titel")

    def test_T15_head_stylesheet(self):
        """T15: head.stylesheets enthält CSS-Pfade."""
        page = _make_page(
            html=b'<html><head><link rel="stylesheet" href="/forum/style/test.css"></head><body>x</body></html>'
        )
        env = self._call(_make_bundle(page=page), "/forum/viewtopic.php?id=100")
        self.assertIn("/forum/style/test.css", env["head"]["stylesheets"])

    def test_T16_head_inline_style(self):
        """T16: head.inline_styles enthält <style>-Inhalte."""
        page = _make_page(
            html=b"<html><head><style>body{color:red}</style></head><body>x</body></html>"
        )
        env = self._call(_make_bundle(page=page), "/forum/viewtopic.php?id=100")
        self.assertIn("body{color:red}", env["head"]["inline_styles"])

    def test_T17_head_null_bei_not_in_scope(self):
        """T17: head ist None wenn Seite nicht im Scope."""
        env = self._call(_make_bundle(page=None), "/forum/viewtopic.php?id=9999")
        self.assertIsNone(env["head"])

    def test_T18_base_href_explizit(self):
        """T18a: Explizites <base href> aus BLOB wird in head.base_href übernommen."""
        page = _make_page(
            url="/forum/viewtopic.php?id=100",
            html=b'<html><head><base href="/forum/"></head><body>x</body></html>'
        )
        env = self._call(_make_bundle(page=page), "/forum/viewtopic.php?id=100")
        self.assertEqual(env["head"]["base_href"], "/forum/")

    def test_T18b_base_href_fallback_auf_page_url(self):
        """T18b: Fehlt <base href> im BLOB, wird Pfad aus canonical_url (pages.url_canonical)
        verwendet — Protokoll/Domain werden abgeschnitten."""
        page = _make_page(
            url="/forum/viewtopic.php?id=100",
            canonical_url="http://alice4nonion.onion/forum/viewtopic.php?id=100",
            html=b"<html><head><title>X</title></head><body>x</body></html>"
        )
        env = self._call(_make_bundle(page=page), "/forum/viewtopic.php?id=100")
        self.assertEqual(env["head"]["base_href"], "/forum/")

    def test_T18c_base_href_fallback_alias(self):
        """T18c: Alias-Auflösung: url='/', canonical_url='.../forum/beginner/'
        → base_href='/forum/beginner/'."""
        page = _make_page(
            url="/",
            canonical_url="http://alice4nonion.onion/forum/beginner/",
            html=b"<html><head><title>X</title></head><body>x</body></html>"
        )
        env = self._call(_make_bundle(page=page), "/")
        self.assertEqual(env["head"]["base_href"], "/forum/beginner/")


if __name__ == "__main__":
    unittest.main(verbosity=2)

# ===========================================================================
# Tests: BlobHandler — original_method / Poll-Unterstützung
# Build 042 · Beleg: Projektgespräch 2026-04-19
# ===========================================================================

class TestBlobHandlerOriginalMethod(unittest.TestCase):
    """T19–T22: original_method-Parameter — GET/POST-Routing für Poll-Seiten."""

    def setUp(self):
        self.cfg = _setup_logging_and_config()
        self.ctx = _make_context()

    def tearDown(self):
        reset_for_testing()

    def _call_with_method(self, bundle, url, method="GET"):
        handler  = _make_handler()
        bh = BlobHandler(bundle, self.ctx, self.cfg)
        bh.handle(handler, url, original_method=method)
        return json.loads(handler._captured["body"].decode("utf-8"))

    def test_T19_get_liefert_get_blob(self):
        """T19: handle() mit original_method='GET' ruft get_page(url, method='GET').
        Beleg: Projektgespräch 2026-04-19."""
        page   = _make_page(method="GET")
        bundle = _make_bundle(page=page)
        self._call_with_method(bundle, "/forum/viewtopic.php?id=42", method="GET")
        bundle.forensic.get_page.assert_called_with(
            "/forum/viewtopic.php?id=42", method="GET"
        )

    def test_T20_post_liefert_post_blob(self):
        """T20: handle() mit original_method='POST' ruft get_page(url, method='POST').
        Beleg: Projektgespräch 2026-04-19."""
        page   = _make_page(method="POST")
        bundle = _make_bundle(page=page)
        self._call_with_method(bundle, "/forum/viewtopic.php?id=42", method="POST")
        bundle.forensic.get_page.assert_called_with(
            "/forum/viewtopic.php?id=42", method="POST"
        )

    def test_T21_default_method_ist_get(self):
        """T21: handle() ohne method-Argument → get_page mit method='GET'.
        Beleg: Projektgespräch 2026-04-19."""
        page   = _make_page(method="GET")
        bundle = _make_bundle(page=page)
        handler = _make_handler()
        bh = BlobHandler(bundle, self.ctx, self.cfg)
        bh.handle(handler, "/forum/viewtopic.php?id=42")
        bundle.forensic.get_page.assert_called_with(
            "/forum/viewtopic.php?id=42", method="GET"
        )

    def test_T22_post_not_in_scope_gibt_not_in_scope_envelope(self):
        """T22: POST-Request auf URL ohne POST-BLOB → in_scope=False.
        Beleg: Projektgespräch 2026-04-19."""
        bundle = _make_bundle(page=None)  # kein POST-BLOB vorhanden
        env = self._call_with_method(
            bundle, "/forum/viewtopic.php?id=42", method="POST"
        )
        self.assertFalse(env["in_scope"])


# ===========================================================================
# Tests: BlobHandler — Beitragsanker in mehrseitigen Themen (T23–T30)
# Build 699 · Vorgang f5956e6b
#
# DER GEMELDETE FEHLER: Ein Verweis auf einen Beitrag, der auf Seite 2..n
# eines Themas steht, lieferte stets die erste Seite. Sie enthaelt den
# Beitrag nicht — der Anker lief ins Leere, und die Ermittlerin sah fremde
# Beitraege an der Stelle, an der der belastende stehen sollte.
#
# ZWEI VERWEISFORMEN, BEIDE HIER GEPRUEFT:
#   Form A '?pid=<post_id>'          — Benachrichtigungen, Trefferlisten
#   Form B '?id=<topic>#p<post_id>'  — Verweise innerhalb des Forums
# Form B loest KEINE Aliasaufloesung aus; sie wird allein von der Ankerprobe
# nach dem BLOB-Lookup erfasst. Ohne eigenen Fall waere sie ungeprueft.
# ===========================================================================

class TestBlobHandlerAnkerSeite(unittest.TestCase):
    """T23–T30: Auslieferung der Seite, die den Beitragsanker traegt."""

    # Zwei Chunks EINES Themas. Der gesuchte Beitrag p777 steht nur im
    # zweiten — genau die Lage aus der Fehlermeldung.
    CHUNK1 = b'<html><body><div id="p100">erster</div></body></html>'
    CHUNK2 = b'<html><body><div id="p777">gesuchter Beitrag</div></body></html>'

    def setUp(self):
        self.cfg = _setup_logging_and_config()
        self.ctx = _make_context()

    def tearDown(self):
        reset_for_testing()

    def _bundle_zwei_chunks(self, post_page=None):
        """Bundle, dessen get_page() beide Chunks nach URL unterscheidet."""
        seiten = {
            "/forum/viewtopic.php?id=500":
                _make_page(url="/forum/viewtopic.php?id=500", html=self.CHUNK1),
            "/forum/viewtopic.php?id=500&p=2":
                _make_page(url="/forum/viewtopic.php?id=500&p=2",
                           html=self.CHUNK2),
        }
        bundle = _make_bundle(post_page=post_page)
        bundle.forensic.get_page.side_effect = (
            lambda url, method="GET": seiten.get(url)
        )
        return bundle

    def _call(self, bundle, url, fragment=None):
        bh = BlobHandler(bundle, self.ctx, self.cfg)
        handler = _make_handler()
        if fragment is None:
            bh.handle(handler, url)
        else:
            bh.handle_with_fragment(handler, url, fragment=fragment)
        return json.loads(handler._captured["body"])

    def test_T23_pid_liefert_gemessene_seite(self):
        """T23: '?pid=777' liefert Chunk 2 — die Seite, die den Beitrag traegt.

        Quelle ist fdb.post_aliases.page, vom PostPageMeasurer des Preppers
        per direkter Ankermitgliedschaft gemessen (aiw_sqlite_prepper Build
        098/101). Der Webserver hat diese Messung bis Build 698 nicht gelesen.
        """
        from db.forensic_db import PostPageRecord
        post_page = PostPageRecord(post_id=777, page_id=2,
                                   url="/forum/viewtopic.php?id=500&p=2",
                                   quelle="gemessen")
        bundle = self._bundle_zwei_chunks(post_page=post_page)
        env = self._call(bundle, "/forum/viewtopic.php?pid=777")

        self.assertEqual(env["url_canonical"], "/forum/viewtopic.php?id=500&p=2")
        self.assertIn('id="p777"', env["html"])
        self.assertEqual(env["fragment"], "p777")
        self.assertEqual(env["fragment_source"], "gemessen")

    def test_T24_pid_ohne_belegbare_seite_wird_ausgewiesen(self):
        """T24: Keine erfasste Seite traegt den Beitrag → Rueckfall auf die
        erste Seite, aber AUSGEWIESEN als 'unaufgeloest' (Grundregel 1)."""
        from db.forensic_db import PostAliasRecord
        bundle = self._bundle_zwei_chunks(post_page=None)
        bundle.forensic.resolve_post_alias.return_value = PostAliasRecord(
            post_id=999, topic_id=500, forum_id=5
        )
        env = self._call(bundle, "/forum/viewtopic.php?pid=999")

        self.assertEqual(env["url_canonical"], "/forum/viewtopic.php?id=500")
        self.assertEqual(env["fragment_source"], "unaufgeloest")

    def test_T25_topicanker_wird_auf_richtige_seite_umgeleitet(self):
        """T25: '?id=500#p777' — der erste Chunk traegt den Anker nicht, also
        wird die Seite ausgeliefert, die ihn traegt (Verweisform B)."""
        from db.forensic_db import PostPageRecord
        post_page = PostPageRecord(post_id=777, page_id=2,
                                   url="/forum/viewtopic.php?id=500&p=2",
                                   quelle="blob")
        bundle = self._bundle_zwei_chunks(post_page=post_page)
        env = self._call(bundle, "/forum/viewtopic.php?id=500", fragment="p777")

        self.assertEqual(env["url_canonical"], "/forum/viewtopic.php?id=500&p=2")
        self.assertIn('id="p777"', env["html"])
        # 'blob' = hier nachgemessen, weil die Prepper-Messung fehlte.
        self.assertEqual(env["fragment_source"], "nachgemessen")

    def test_T26_vorhandener_anker_wird_nicht_umgeleitet(self):
        """T26: Steht der Anker im BLOB, bleibt die Seite stehen — und es wird
        gar nicht erst nach einer anderen gesucht."""
        bundle = self._bundle_zwei_chunks(post_page=None)
        env = self._call(bundle, "/forum/viewtopic.php?id=500", fragment="p100")

        self.assertEqual(env["url_canonical"], "/forum/viewtopic.php?id=500")
        self.assertEqual(env["fragment_source"], "bestaetigt")
        bundle.forensic.resolve_post_page.assert_not_called()

    def test_T27_keine_umleitung_ausserhalb_von_themenseiten(self):
        """T27: Ein Anker '#p777' auf einer Nicht-Themenseite meint nicht
        denselben Beitragscontainer — es wird nicht umgeleitet."""
        page = _make_page(url="/forum/search.php?action=show_user_posts",
                          html=b"<html><body>Trefferliste</body></html>")
        bundle = _make_bundle(page=page, post_page=None)
        env = self._call(bundle, "/forum/search.php?action=show_user_posts",
                         fragment="p777")

        self.assertEqual(env["url_canonical"],
                         "/forum/search.php?action=show_user_posts")
        self.assertIsNone(env["fragment_source"])
        bundle.forensic.resolve_post_page.assert_not_called()

    def test_T28_fehlender_blob_ist_unpruefbar(self):
        """T28: html IS NULL (fetch_failed) belegt NICHT, dass der Beitrag
        woanders steht — keine Umleitung, Ausweis 'unpruefbar'."""
        page   = _make_page(url="/forum/viewtopic.php?id=500", html=None,
                            http_status=0)
        bundle = _make_bundle(page=page, post_page=None)
        env = self._call(bundle, "/forum/viewtopic.php?id=500", fragment="p777")

        self.assertTrue(env["fetch_failed"])
        self.assertEqual(env["fragment_source"], "unpruefbar")
        bundle.forensic.resolve_post_page.assert_not_called()

    def test_T29_ohne_beitragsanker_kein_ausweis(self):
        """T29: Seite ohne Beitragsanker → fragment_source ist None."""
        bundle = self._bundle_zwei_chunks(post_page=None)
        env = self._call(bundle, "/forum/viewtopic.php?id=500")
        self.assertIsNone(env["fragment_source"])

    def test_T30_notify_nutzt_seite_des_beitrags(self):
        """T30: '?notify=' fuehrt ueber die post_id auf dieselbe Seitenwahl."""
        from db.forensic_db import NotifyAliasRecord, PostPageRecord
        post_page = PostPageRecord(post_id=777, page_id=2,
                                   url="/forum/viewtopic.php?id=500&p=2",
                                   quelle="gemessen")
        bundle = self._bundle_zwei_chunks(post_page=post_page)
        bundle.forensic.resolve_notify_alias.return_value = NotifyAliasRecord(
            notify_id=9001, post_id=777
        )
        env = self._call(bundle, "/forum/viewtopic.php?notify=9001")

        self.assertEqual(env["url_canonical"], "/forum/viewtopic.php?id=500&p=2")
        self.assertEqual(env["fragment"], "p777")
        self.assertEqual(env["fragment_source"], "gemessen")

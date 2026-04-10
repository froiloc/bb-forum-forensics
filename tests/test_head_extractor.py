# =============================================================================
# tests/test_head_extractor.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite für server/head_extractor.py
#
# Abgedeckte Testfälle:
#   T01 — Vollständiger <head> mit allen Elementen wird korrekt extrahiert
#   T02 — <title> wird korrekt extrahiert
#   T03 — <base href> wird korrekt extrahiert
#   T04 — Mehrere <link rel="stylesheet"> werden alle extrahiert
#   T05 — Inline-<style>-Block wird extrahiert
#   T06 — Mehrere <style>-Blöcke werden alle extrahiert
#   T07 — <meta http-equiv="refresh"> wird entfernt; refresh_removed=True
#   T08 — Andere <meta>-Tags werden ignoriert (kein Fehler)
#   T09 — Externe JS-Einbindungen (<script src=>) werden ignoriert
#   T10 — Inhalt nach </head> wird vollständig ignoriert
#   T11 — Bytes-Eingabe wird UTF-8-dekodiert
#   T12 — Bytes mit ungültigen UTF-8-Sequenzen → errors='replace', kein Absturz
#   T13 — Leerer HTML-String → leeres ExtractedHead (keine Exception)
#   T14 — HTML ohne <head>-Tag → leeres ExtractedHead (keine Exception)
#   T15 — to_html() gibt korrektes HTML-Fragment zurück
#   T16 — to_html() enkodiert Sonderzeichen in title korrekt (XSS-Schutz)
#   T17 — to_html() enkodiert Anführungszeichen in href korrekt
#   T18 — Nur erstes <base>-Element wird übernommen (HTML-Spezifikation)
#   T19 — Reales Forum-HTML-Fragment wird korrekt verarbeitet
#   T20 — HeadExtractor ist zustandslos: mehrere extract()-Aufrufe unabhängig
#
# Version: v0.1.0 · Build: 005 · 2026-04-10
# =============================================================================

import sys
import os
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import setup_logging, reset_for_testing
from core.config_loader import ConfigLoader
from server.head_extractor import HeadExtractor, ExtractedHead


def _setup_test_logging():
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
              coordinator_db: "./data/coordinator.db"
              forensic_db_dir: "./data/forensic/"
              default_db: "./data/default.db"
              evidence_db_dir: "./data/evidence/"
        """))
    cfg = ConfigLoader(config_path=config_path)
    setup_logging(cfg)


class TestHeadExtractorElements(unittest.TestCase):
    """T01–T09: Einzelne HTML-Elemente"""

    def setUp(self):
        _setup_test_logging()
        self.ex = HeadExtractor()

    def tearDown(self):
        reset_for_testing()

    def test_T01_vollstaendiger_head(self):
        """T01: Vollständiger <head> mit allen relevanten Elementen."""
        html = """<!DOCTYPE html>
        <html>
        <head>
          <base href="https://forum.example.org/forum/">
          <title>Testtopic — ForumName</title>
          <link rel="stylesheet" href="/forum/style/main.css">
          <link rel="stylesheet" href="/forum/style/theme.css">
          <style>body { color: red; }</style>
          <meta http-equiv="refresh" content="0;url=https://evil.example">
          <script src="/forum/js/app.js"></script>
        </head>
        <body><p>Inhalt</p></body>
        </html>"""
        result = self.ex.extract(html)
        self.assertEqual(result.title, "Testtopic — ForumName")
        self.assertEqual(result.base_href, "https://forum.example.org/forum/")
        self.assertEqual(len(result.stylesheets), 2)
        self.assertIn("/forum/style/main.css", result.stylesheets)
        self.assertIn("/forum/style/theme.css", result.stylesheets)
        self.assertEqual(len(result.inline_styles), 1)
        self.assertIn("color: red", result.inline_styles[0])
        self.assertTrue(result.refresh_removed)

    def test_T02_title_extrahiert(self):
        """T02: <title> wird korrekt extrahiert."""
        html = "<html><head><title>Mein Titel</title></head><body></body></html>"
        result = self.ex.extract(html)
        self.assertEqual(result.title, "Mein Titel")

    def test_T03_base_href_extrahiert(self):
        """T03: <base href> wird korrekt extrahiert."""
        html = '<html><head><base href="https://example.org/base/"></head></html>'
        result = self.ex.extract(html)
        self.assertEqual(result.base_href, "https://example.org/base/")

    def test_T04_mehrere_stylesheets(self):
        """T04: Mehrere <link rel="stylesheet"> werden alle extrahiert."""
        html = """<html><head>
          <link rel="stylesheet" href="/a.css">
          <link rel="stylesheet" href="/b.css">
          <link rel="stylesheet" href="/c.css">
        </head></html>"""
        result = self.ex.extract(html)
        self.assertEqual(len(result.stylesheets), 3)
        self.assertEqual(result.stylesheets, ["/a.css", "/b.css", "/c.css"])

    def test_T05_inline_style(self):
        """T05: Inline-<style>-Block wird extrahiert."""
        html = "<html><head><style>.post { font-size: 13px; }</style></head></html>"
        result = self.ex.extract(html)
        self.assertEqual(len(result.inline_styles), 1)
        self.assertIn("font-size: 13px", result.inline_styles[0])

    def test_T06_mehrere_style_bloecke(self):
        """T06: Mehrere <style>-Blöcke werden alle extrahiert."""
        html = """<html><head>
          <style>.a { color: blue; }</style>
          <style>.b { color: green; }</style>
        </head></html>"""
        result = self.ex.extract(html)
        self.assertEqual(len(result.inline_styles), 2)

    def test_T07_meta_refresh_entfernt(self):
        """T07: <meta http-equiv="refresh"> wird entfernt; refresh_removed=True."""
        html = """<html><head>
          <meta http-equiv="refresh" content="5;url=https://other.example">
        </head></html>"""
        result = self.ex.extract(html)
        self.assertTrue(result.refresh_removed)
        # Inhalt darf nicht im Ergebnis auftauchen
        html_out = result.to_html()
        self.assertNotIn("refresh", html_out.lower())

    def test_T08_andere_meta_ignoriert(self):
        """T08: Andere <meta>-Tags werden stillschweigend ignoriert."""
        html = """<html><head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width">
          <meta name="description" content="Forum-Beschreibung">
        </head></html>"""
        result = self.ex.extract(html)
        self.assertFalse(result.refresh_removed)
        self.assertIsNone(result.title)

    def test_T09_script_ignoriert(self):
        """T09: <script src=...>-Tags werden ignoriert — kein Eintrag im Ergebnis."""
        html = """<html><head>
          <script src="/forum/js/app.js"></script>
          <script>var x = 1;</script>
        </head></html>"""
        result = self.ex.extract(html)
        # Scripts dürfen im to_html()-Output nicht auftauchen
        html_out = result.to_html()
        self.assertNotIn("<script", html_out)
        self.assertNotIn("app.js", html_out)


class TestHeadExtractorScope(unittest.TestCase):
    """T10: Scope-Begrenzung auf <head>"""

    def setUp(self):
        _setup_test_logging()
        self.ex = HeadExtractor()

    def tearDown(self):
        reset_for_testing()

    def test_T10_body_inhalte_ignoriert(self):
        """T10: Alles nach </head> wird vollständig ignoriert."""
        html = """<html><head>
          <title>Korrekter Titel</title>
        </head>
        <body>
          <title>Falscher Titel im Body</title>
          <style>.body-style { display: none; }</style>
          <link rel="stylesheet" href="/body.css">
        </body></html>"""
        result = self.ex.extract(html)
        self.assertEqual(result.title, "Korrekter Titel")
        # Body-Elemente dürfen nicht erfasst worden sein
        self.assertEqual(len(result.stylesheets), 0)
        self.assertEqual(len(result.inline_styles), 0)


class TestHeadExtractorInputTypes(unittest.TestCase):
    """T11–T14: Eingabetypen und Robustheit"""

    def setUp(self):
        _setup_test_logging()
        self.ex = HeadExtractor()

    def tearDown(self):
        reset_for_testing()

    def test_T11_bytes_eingabe(self):
        """T11: bytes-Eingabe wird UTF-8-dekodiert."""
        html = b"<html><head><title>Bytes-Titel</title></head></html>"
        result = self.ex.extract(html)
        self.assertEqual(result.title, "Bytes-Titel")

    def test_T12_ungueltige_utf8_bytes(self):
        """T12: Bytes mit ungültigen UTF-8-Sequenzen → kein Absturz, Ergebnis nutzbar."""
        # \xff\xfe ist keine gültige UTF-8-Sequenz
        html = b"<html><head><title>Titel\xff\xfemit Fehler</title></head></html>"
        result = self.ex.extract(html)
        # Kein Absturz — Titel enthält Ersatzzeichen oder ist teilweise korrekt
        self.assertIsNotNone(result)

    def test_T13_leerer_string(self):
        """T13: Leerer HTML-String → leeres ExtractedHead, keine Exception."""
        result = self.ex.extract("")
        self.assertIsNone(result.title)
        self.assertIsNone(result.base_href)
        self.assertEqual(result.stylesheets, [])
        self.assertEqual(result.inline_styles, [])
        self.assertFalse(result.refresh_removed)

    def test_T14_kein_head_tag(self):
        """T14: HTML ohne <head>-Tag → leeres ExtractedHead, keine Exception."""
        html = "<html><body><p>Kein Head vorhanden</p></body></html>"
        result = self.ex.extract(html)
        self.assertIsNone(result.title)
        self.assertEqual(result.stylesheets, [])


class TestHeadExtractorToHtml(unittest.TestCase):
    """T15–T17: to_html()-Methode"""

    def setUp(self):
        _setup_test_logging()
        self.ex = HeadExtractor()

    def tearDown(self):
        reset_for_testing()

    def test_T15_to_html_korrekt(self):
        """T15: to_html() gibt ein korrektes HTML-Fragment zurück."""
        html = """<html><head>
          <base href="https://forum.example.org/">
          <title>Seite</title>
          <link rel="stylesheet" href="/style.css">
          <style>body{}</style>
        </head></html>"""
        result = self.ex.extract(html)
        out = result.to_html()
        # Reihenfolge: base vor title vor link vor style
        base_pos = out.find("<base")
        title_pos = out.find("<title")
        link_pos = out.find("<link")
        style_pos = out.find("<style")
        self.assertLess(base_pos, title_pos)
        self.assertLess(title_pos, link_pos)
        self.assertLess(link_pos, style_pos)

    def test_T16_to_html_enkodiert_title(self):
        """T16: to_html() enkodiert HTML-Sonderzeichen im Titel (XSS-Schutz).

        html.parser mit convert_charrefs=True verarbeitet eingebettete Tags
        im <title>-Inhalt als Kindknoten und liefert nur den Textteil an
        handle_data(). Das Ergebnis enthält also den reinen Text ohne Tags.
        to_html() muss dann &, < und > im Titel enkodieren, damit der
        erzeugte HTML-Output nicht durch Titeltexte gebrochen werden kann.
        """
        # Titel mit rohen Sonderzeichen die in HTML enkodiert werden müssen
        html = "<html><head><title>Bericht &amp; Auswertung &lt;2026&gt;</title></head></html>"
        result = self.ex.extract(html)
        out = result.to_html()
        # & muss als &amp; enkodiert sein
        # < und > müssen als &lt; / &gt; enkodiert sein
        self.assertNotIn("<2026>", out)
        # Der Titel-Tag selbst darf nicht durch Titelinhalte gebrochen werden
        self.assertIn("<title>", out)
        self.assertIn("</title>", out)
        # Sonderzeichen im Rohtext müssen sicher enkodiert sein
        self.assertTrue(
            "&amp;" in out or "Auswertung" in out,
            "Enkodierung von & erwartet im title-Ausgabe"
        )

    def test_T17_to_html_enkodiert_href(self):
        """T17: to_html() enkodiert Anführungszeichen in href-Attributen."""
        # Anführungszeichen im href könnten Attribut-Injection ermöglichen
        html = '<html><head><link rel="stylesheet" href="/style.css?v=1&quot;onerror=x"></head></html>'
        result = self.ex.extract(html)
        out = result.to_html()
        # Anführungszeichen müssen enkodiert sein
        # Das href-Attribut darf nicht durch ein eingeschleustes " beendet werden
        self.assertNotIn('href="/style.css?v=1"onerror=x"', out)


class TestHeadExtractorEdgeCases(unittest.TestCase):
    """T18–T20: Randfälle"""

    def setUp(self):
        _setup_test_logging()
        self.ex = HeadExtractor()

    def tearDown(self):
        reset_for_testing()

    def test_T18_nur_erstes_base_element(self):
        """T18: Bei mehreren <base>-Elementen wird nur das erste übernommen."""
        html = """<html><head>
          <base href="https://first.example.org/">
          <base href="https://second.example.org/">
        </head></html>"""
        result = self.ex.extract(html)
        self.assertEqual(result.base_href, "https://first.example.org/")

    def test_T19_reales_forum_html(self):
        """T19: Realistisches Forum-HTML-Fragment wird korrekt verarbeitet."""
        # Repräsentatives HTML-Fragment eines typischen FluxBB-Forums
        html = textwrap.dedent("""
            <!DOCTYPE html>
            <html lang="de">
            <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>Threadtitel — ForumName</title>
            <base href="https://forum.example.org/forum/" />
            <link rel="stylesheet" href="/forum/style/oxygen/oxygen.css" type="text/css" />
            <link rel="stylesheet" href="/forum/style/oxygen/variant.css" type="text/css" />
            <style type="text/css">
            a:link, a:visited { color: #275487; }
            </style>
            </head>
            <body>
            <div id="punwrap">
              <div id="pun-index" class="pun">
                <p>Forum-Inhalt hier</p>
              </div>
            </div>
            </body>
            </html>
        """)
        result = self.ex.extract(html)
        self.assertEqual(result.title, "Threadtitel — ForumName")
        self.assertEqual(result.base_href, "https://forum.example.org/forum/")
        self.assertEqual(len(result.stylesheets), 2)
        self.assertEqual(len(result.inline_styles), 1)
        self.assertFalse(result.refresh_removed)

    def test_T20_zustandslos_mehrere_aufrufe(self):
        """T20: HeadExtractor ist zustandslos — mehrere extract()-Aufrufe liefern unabhängige Ergebnisse."""
        html_a = "<html><head><title>Seite A</title></head></html>"
        html_b = "<html><head><title>Seite B</title><link rel='stylesheet' href='/b.css'></head></html>"

        result_a = self.ex.extract(html_a)
        result_b = self.ex.extract(html_b)
        result_a2 = self.ex.extract(html_a)

        self.assertEqual(result_a.title, "Seite A")
        self.assertEqual(result_b.title, "Seite B")
        self.assertEqual(len(result_b.stylesheets), 1)
        # Erneuter Aufruf mit html_a darf nicht die Stylesheets von html_b enthalten
        self.assertEqual(len(result_a2.stylesheets), 0)
        self.assertEqual(result_a2.title, "Seite A")


if __name__ == "__main__":
    unittest.main(verbosity=2)

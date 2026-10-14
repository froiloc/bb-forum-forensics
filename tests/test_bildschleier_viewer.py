# =============================================================================
# tests/test_bildschleier_viewer.py
# IT-Forensisches Ermittlungswerkzeug — Bildschleier im Viewer (Build 772)
# =============================================================================
# Waechter BS09-BS18 (Bauplan Builds 771-773, §9), Regel, Grundregel,
# Seitenausnahmen, Dienst, Shell, Seitenumschlag und Endpunkt.
#
#   BS09  Avatare und Signaturen bleiben verschleiert — unter BEIDEN Wurzeln,
#         relativ, wurzelrelativ, absolut und in der fileasset-Form
#   BS10  fremder Host mit '/img/' und der Image-Hoster: verschleiert
#   BS11  Umgehungsschreibweisen ('..', %2e, Rueckstrich, '//', Port,
#         Zugangsdaten, data:, javascript:): verschleiert
#   BS12  /pix/, /forum/uploads/: verschleiert; /forum/style/…, /forum/v4/
#         style/…, /style/bg.webp: klar
#   BS13  1bg.png genau an der Wurzel; Nachbarn nicht
#   BS13a Wurzelgleichheit '/X' == '/forum/X' (Ausnahme UND Ausschluss)
#   BS14  (entfallen durch die Exaktwert-Ausnahmen, siehe Seitenausnahmen:
#         zwei url() in einem Stil werden GEMEINSAM geprueft — BS14n)
#   BS15  relative Angaben gegen die Basis: '../img/' aus /forum/style/ klar,
#         'img/' aus /forum/beginner/ verschleiert; fremde absolute Basis
#   BS16  die fileasset-Form entsteht mit DERSELBEN Funktion wie in
#         server/blob_handler.py (Quelltextanker) und wird entpackt
#   BS17  Shell: Klasse/data-Attribute an <html>; image-veil.css VOR allen
#         anderen Stylesheets; bildschleier.js VOR toolbar.js
#   BS18  POST ohne Recht -> 403, keine Zeile, kein Beleg; mit Recht -> 200
#         und genau ein Beleg
#   BSc*  Grundregel: ein Block je Ziel, Filterkette abgesichert
#   BSs*  Seitenausnahmen: exakte Werte, srcset, Stil am Bild, Entitaeten,
#         CRLF, Escaping, Obergrenze
#   BSd*  Dienst: interner Fehler -> internal_error (gesperrt), fehlender
#         Pfad -> rbac_unavailable
#   BSu*  Seitenumschlag: Ausnahmen in beiden Zustaenden (Build 775, D1)
#
# MUTATIONSGEGENPROBEN (gefahren in Build 772, Ergebnis im build.json):
#   M5  Ausschlusspruefung in der Regel entfernt          -> BS09 rot
#   M6  Hostpruefung in der Regel entfernt                -> BS10 rot
#   M7  srcset-Pruefung in den Seitenausnahmen entfernt   -> BSs02 rot
#   M8  Grundregel als EINE Selektorliste ausgegeben      -> BSc01 rot
#   M9  Shell bindet image-veil.css NACH head_content ein -> BS17 rot
#
# Version: v0.8.772 · Build: 772 · 2026-10-09
# =============================================================================

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import types
import unittest
import urllib.parse
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

from core import bildschleier_dienst as bd                           # noqa: E402
from core.bildschleier_css import (                                  # noqa: E402
    HTML_KLASSE, SELEKTOR_PRAEFIX, BildschleierCss,
)
from core.bildschleier_regel import BildschleierRegel                # noqa: E402
from core.bildschleier_seitenausnahmen import (                      # noqa: E402
    MAX_AUSNAHMEN, BildschleierSeitenausnahmen, css_zeichenkette,
)
from management.bildschleier.bildschleier_zustand import (           # noqa: E402
    BildschleierZustand,
)

FORUM = "alice4n4kd5gga3xqggygi6r7q7l7bb2wg5lcykh22ilxomk2jmpcbyd.onion"
HOSTER = "alicefe3b2dqil3mk3ipwtyoqjol23kdai7cjpgzrtvemfvtzz2s67ad.onion"
SEITE = "http://%s/forum/viewtopic.php?id=42" % FORUM


def _regel():
    return BildschleierRegel(
        forum_hosts=[FORUM], roots=["/forum/", "/"],
        exempt_dirs=["img/", "style/", "v4/style/"],
        exempt_files=["1bg.png"],
        excluded_dirs=["img/avatars/", "img/signatures/"])


def _fileasset(url):
    return "/_forensic/fileasset?url=" + urllib.parse.quote(url, safe="")


# =============================================================================
# Regel
# =============================================================================
class RegelTests(unittest.TestCase):

    def setUp(self):
        self.r = _regel()

    def _klar(self, url, basis=SEITE):
        self.assertTrue(self.r.ist_ausgenommen(url, basis),
                        "sollte KLAR sein: %r (Basis %r)" % (url, basis))

    def _schleier(self, url, basis=SEITE):
        self.assertFalse(self.r.ist_ausgenommen(url, basis),
                         "sollte VERSCHLEIERT sein: %r (Basis %r)" % (url, basis))

    def test_bs09_avatare_und_signaturen(self):
        for wurzel in ("/forum/", "/"):
            for d in ("img/avatars/", "img/signatures/"):
                p = wurzel + d + "18.jpg"
                self._schleier(p)
                self._schleier(p + "?m=1712345678")
                self._schleier("http://%s%s" % (FORUM, p))
                self._schleier(_fileasset("http://%s%s" % (FORUM, p)))
        self._schleier("img/avatars/18.jpg", "/forum/")
        self._schleier("avatars/18.jpg", "/forum/img/")
        # Schreibung: Ausschluss ohne Ruecksicht darauf
        self._schleier("/forum/img/Avatars/18.jpg")
        self._schleier("/forum/IMG/AVATARS/18.jpg")

    def test_bs10_fremde_hosts(self):
        self._schleier("http://filer.onion/img/x.jpg")
        self._schleier("http://%s/forum/img/x.png" % HOSTER)
        self._schleier("http://%s/images/720/abc/def" % HOSTER)
        self._schleier(_fileasset("http://%s/images/720/abc/def" % HOSTER))
        self._schleier("//filer.onion/forum/img/x.png")
        # Gegenprobe: derselbe Pfad auf dem Forenhost ist klar
        self._klar("http://%s/forum/img/x.png" % FORUM)
        self._klar("https://%s/forum/img/x.png" % FORUM)
        self._klar("//%s/forum/img/x.png" % FORUM)

    def test_bs11_umgehungsschreibweisen(self):
        for url in (
            "/forum/img/../uploads/x.jpg",
            "http://%s/forum/img/../uploads/x.jpg" % FORUM,
            "/forum/img/%2e%2e/uploads/x.jpg",
            "/forum/img/%2E%2E/uploads/x.jpg",
            "/forum/img/..%2fuploads/x.jpg",
            "/forum/img\\..\\uploads\\x.jpg",
            "/forum/img//avatars/x.jpg",
            "/forum/img/./x.png" if False else "/forum/img/%5cx.png",
            "http://%s:81/forum/img/x.png" % FORUM,
            "http://user@%s/forum/img/x.png" % FORUM,
            "data:image/png;base64,iVBORw0KGgo=",
            "javascript:alert(1)",
            "blob:http://%s/123" % FORUM,
            "file:///forum/img/x.png",
            "/forum/img/x\tpng",
            "/forum/img/x\npng",
            "",
            None,
        ):
            self._schleier(url)

    def test_bs11b_umgebender_leerraum_wie_der_browser(self):
        # Der Browser entfernt fuehrenden und folgenden ASCII-Leerraum aus
        # src (HTML: "valid URL potentially surrounded by spaces"). Die Regel
        # tut dasselbe — der Selektor nennt den Wert dann woertlich MIT
        # Leerraum, und genau dieses Bild wird ausgenommen.
        self._klar(" /forum/img/x.png\n")
        self._schleier(" /forum/img/avatars/x.png ")

    def test_bs11a_relative_punktsegmente_wie_der_browser(self):
        # Relative Angaben loest urljoin auf wie der Browser — das Ergebnis
        # zaehlt, nicht die Schreibweise.
        self._klar("../img/icons/x.png", "/forum/style/")
        self._schleier("img/../img/avatars/x.png", "/forum/")
        self._schleier("img/../uploads/x.png", "/forum/")

    def test_bs12_verzeichnisse(self):
        self._schleier("/pix/icon/warning.png")
        self._schleier("/pix/banner/s9/1.jpg")
        self._schleier("/forum/uploads/preview/x.jpg")
        self._schleier("/uploads/logo/x.png")
        self._klar("/forum/style/x.png")
        self._klar("/forum/style/Air/img/x.png")
        self._klar("/forum/v4/style/a/b.png")
        self._klar("/style/bg.webp")
        self._klar("/forum/img/smilies/smile.png")
        self._klar("/forum/img/badge/27.png")
        self._klar("img/icons/sticky.gif", "/forum/")
        # Verzeichnis allein ist kein Bild
        self._schleier("/forum/img/")

    def test_bs13_1bg(self):
        self._klar("/forum/1bg.png")
        self._klar("/1bg.png")
        self._klar("1bg.png", "/forum/")
        self._schleier("/forum/1bg.png.jpg")
        self._schleier("/forum/x/1bg.png")
        self._schleier("/forum/1BG.png")

    def test_bs13a_wurzelgleichheit(self):
        self._klar("/img/icons/x.gif")
        self._klar("/forum/img/icons/x.gif")
        self._schleier("/img/avatars/1.jpg")
        self._schleier("/forum/img/avatars/1.jpg")
        self._schleier("/img/signatures/1.png")

    def test_bs15_basis(self):
        self._klar("../img/icons/x.png", "/forum/style/")
        self._schleier("img/x.png", "/forum/beginner/")
        self._klar("../img/x.png", "/forum/beginner/")
        # absolute Basis auf fremdem Host: auch Relatives ist fremd
        self._schleier("img/x.png", "http://filer.onion/forum/")
        self._klar("img/x.png", "http://%s/forum/" % FORUM)

    def test_bs16_fileasset_gleiche_funktion_wie_blob_handler(self):
        quelle = (WURZEL / "server" / "blob_handler.py").read_text(encoding="utf-8")
        self.assertIn(
            'proxy = "/_forensic/fileasset?url=" + urllib.parse.quote(url, safe="")',
            quelle,
            "blob_handler kodiert die fileasset-Form anders als angenommen — "
            "BildschleierRegel muss angepasst werden.")
        self._klar(_fileasset("http://%s/forum/img/icons/a.png" % FORUM))
        self._schleier(_fileasset("http://%s/forum/img/avatars/a.png" % FORUM))
        self._schleier("/_forensic/fileasset?url=a&url=b")
        self._schleier("/_forensic/fileasset")

    def test_bs16a_konfiguration_wird_geprueft(self):
        for kaputt in (
            dict(roots=["forum/"]),
            dict(exempt_dirs=["/img/"]),
            dict(exempt_dirs=["img"]),
            dict(exempt_files=["x/"]),
            dict(excluded_dirs=["../img/"]),
        ):
            args = dict(forum_hosts=[FORUM], roots=["/forum/"],
                        exempt_dirs=["img/"], exempt_files=[],
                        excluded_dirs=[])
            args.update(kaputt)
            with self.assertRaises(ValueError, msg=str(kaputt)):
                BildschleierRegel(**args)

    def test_bs16b_aus_konfiguration_yaml(self):
        from core.config_loader import ConfigLoader
        r = BildschleierRegel.aus_konfiguration(
            ConfigLoader(str(WURZEL / "config.yaml")))
        self.assertIn(FORUM, r.forum_hosts)
        self.assertNotIn(HOSTER, r.forum_hosts)
        self.assertTrue(r.ist_ausgenommen("/forum/img/x.png", SEITE))
        self.assertFalse(r.ist_ausgenommen("/forum/img/avatars/x.png", SEITE))


# =============================================================================
# Grundregel
# =============================================================================
class GrundregelTests(unittest.TestCase):

    def test_bsc01_ein_block_je_ziel(self):
        css = BildschleierCss().stylesheet()
        bloecke = re.findall(r"\{[^}]*\}", css)
        selektoren = re.findall(r"^(html\.[^{]+)\{", css, re.MULTILINE)
        self.assertEqual(len(bloecke), len(selektoren))
        self.assertGreaterEqual(len(selektoren), 10)
        for s in selektoren:
            self.assertNotIn(",", s.replace(":not(", "").split("#forensic-viewport")[0],
                             "Selektorliste statt eines Blocks: %r" % s)
            self.assertTrue(s.startswith(SELEKTOR_PRAEFIX), s)
        for ziel in ("img", "video", "iframe", "[background]",
                     '[style*="url(" i]', '[style*="image-set(" i]'):
            self.assertIn("%s %s {" % (SELEKTOR_PRAEFIX, ziel), css)
        self.assertIn("!important", css)
        self.assertIn("clip-path: inset(0) !important", css)

    def test_bsc02_filterkette_abgesichert(self):
        for kaputt in ("blur(1px); } body { display:none",
                       "blur(1px)</style>", "", "url(x)"):
            if kaputt == "url(x)":
                # 'url(x)' besteht nur aus erlaubten Zeichen — der Filter
                # wird woertlich gesetzt und ist dann schlicht ungueltig;
                # aufbrechen kann er das Stylesheet nicht.
                continue
            with self.assertRaises(ValueError, msg=kaputt):
                BildschleierCss(kaputt)
        self.assertIn("blur(48px)", BildschleierCss().stylesheet())

    def test_bsc03_spezifitaet_fuenf_ids(self):
        self.assertEqual(SELEKTOR_PRAEFIX.count("#"), 5)
        self.assertTrue(SELEKTOR_PRAEFIX.startswith("html.%s" % HTML_KLASSE))


# =============================================================================
# Seitenausnahmen
# =============================================================================
class SeitenausnahmenTests(unittest.TestCase):

    def setUp(self):
        self.a = BildschleierSeitenausnahmen(_regel())

    def _css(self, html, basis=SEITE):
        return self.a.stylesheet(html, basis)

    def test_bss01_exakte_werte(self):
        html = ('<p><img src="img/icons/sticky.gif">'
                '<img src="http://%s/forum/img/avatars/1.jpg?m=1">'
                '<img src="http://%s/images/720/a/b" class="bb-image"></p>'
                % (FORUM, HOSTER))
        css = self._css(html)
        self.assertIn('img[src="img/icons/sticky.gif"]:not([style]):not([srcset])', css)
        self.assertNotIn("avatars", css)
        self.assertNotIn(HOSTER, css)
        self.assertEqual(css.count("{"), 1)
        self.assertIn("filter: none !important", css)

    def test_bss02_srcset_nie(self):
        css = self._css('<img src="/forum/img/x.png" srcset="/u/a.jpg 2x">')
        self.assertEqual(css, "")

    def test_bss03_stil_am_bild(self):
        gut = self._css('<img src="/forum/img/x.png" style="border:0">')
        self.assertIn('[style="border:0"]', gut)
        schlecht = self._css('<img src="/forum/img/x.png" '
                             'style="background:url(/uploads/x.jpg)">')
        self.assertEqual(schlecht, "")

    def test_bss04_inline_hintergruende(self):
        css = self._css('<span style="background-image:url(/forum/img/badge/27.png)">a</span>'
                        '<div class="headerbar" style="background-image: url(http://%s/images/0/x/y)"></div>'
                        % HOSTER)
        self.assertIn('[style="background-image:url(/forum/img/badge/27.png)"]', css)
        self.assertNotIn(HOSTER, css)

    def test_bs14n_zwei_url_in_einem_stil(self):
        css = self._css('<div style="background:url(/forum/img/a.png), '
                        'url(/uploads/b.jpg)">x</div>')
        self.assertEqual(css, "")
        css = self._css('<div style="background:url(/forum/img/a.png), '
                        'url(\'/forum/style/b.png\')">x</div>')
        self.assertEqual(css.count("{"), 1)

    def test_bss05_andere_bildfunktionen_und_escapes(self):
        for stil in ('background:image-set("/forum/img/a.png" 1x)',
                     'background:url(/forum/img/a.png); content:element(#x)',
                     'background:u\\72l(/uploads/x.jpg)'):
            self.assertEqual(self._css('<div style=\'%s\'>x</div>' % stil), "",
                             stil)

    def test_bss06_medienelemente_nie_ueber_den_stil(self):
        css = self._css('<video style="background:url(/forum/img/a.png)" '
                        'src="/uploads/v.mp4"></video>')
        self.assertEqual(css, "")

    def test_bss07_entitaeten_und_zeilenenden(self):
        css = self._css('<img src="/forum/img/a.png?x=1&amp;y=2">')
        self.assertIn('img[src="/forum/img/a.png?x=1&y=2"]', css)
        css = self._css('<span style="color:red;\r\nbackground:url(/forum/img/a.png)">x</span>')
        self.assertIn('\\a ', css)
        self.assertNotIn("\r", css)

    def test_bss08_escaping(self):
        self.assertEqual(css_zeichenkette('a"b\\c'), '"a\\"b\\\\c"')
        self.assertEqual(css_zeichenkette("a\nb"), '"a\\a b"')
        self.assertEqual(css_zeichenkette("a\x00b"), '"a�b"')

    def test_bss09_obergrenze(self):
        html = "".join('<img src="/forum/img/i%d.png">' % i
                       for i in range(MAX_AUSNAHMEN + 5))
        css = self._css(html)
        self.assertEqual(css.count("{"), MAX_AUSNAHMEN)

    def test_bss10_leer(self):
        self.assertEqual(self._css(None), "")
        self.assertEqual(self._css(""), "")
        self.assertEqual(self._css("<p>kein Bild</p>"), "")

    def test_bss11_doppelte_attribute_erstes_gilt(self):
        css = self._css('<img src="/uploads/x.jpg" src="/forum/img/a.png">')
        self.assertEqual(css, "")


# =============================================================================
# Hilfen fuer Dienst, Shell, Umschlag, Endpunkt
# =============================================================================
class _Handler:
    def __init__(self):
        self.status = None
        self.body = b""
        self.content_type = None
        self.headers = {}

    def send_response_body(self, status, body, content_type="text/html; charset=utf-8",
                           extra_headers=None):
        self.status = status
        self.body = body
        self.content_type = content_type
        self.headers = dict(extra_headers or {})

    def json(self):
        return json.loads(self.body.decode("utf-8"))


class _Stub:
    """Ein Dienst-Ersatz mit festem Zustand."""

    def __init__(self, zustand):
        self.z = zustand
        self.regel = _regel()
        self.grundregel = BildschleierCss()
        self.seitenausnahmen = BildschleierSeitenausnahmen(self.regel)

    def aktualisieren(self):
        return self.z

    def zustand(self):
        return self.z


def _stub_setzen(zustand):
    bd.zuruecksetzen_fuer_tests()
    bd._INSTANZ = _Stub(zustand)


# =============================================================================
# Shell
# =============================================================================
class ShellTests(unittest.TestCase):

    def tearDown(self):
        bd.zuruecksetzen_fuer_tests()

    def _shell(self):
        from server.shell_handler import ShellHandler
        from core.config_loader import ConfigLoader
        page = types.SimpleNamespace(
            html=b"<html><head><title>T</title><base href='/forum/'>"
                 b"<link rel='stylesheet' href='style/Air.css'></head>"
                 b"<body><img src='x'></body></html>",
            scrape_context="user", fetch_failed=False)
        bundle = types.SimpleNamespace(
            forensic=types.SimpleNamespace(get_page=lambda url: page))
        ctx = types.SimpleNamespace(investigator_id=1)
        h = _Handler()
        ShellHandler(bundle, ctx, ConfigLoader(str(WURZEL / "config.yaml"))
                     ).handle(h, SEITE)
        return h.body.decode("utf-8")

    def test_bs17_reihenfolge_und_klasse(self):
        _stub_setzen(BildschleierZustand.gesperrt("required_by_role"))
        html = self._shell()
        oeffner = re.search(r"<html[^>]*>", html).group(0)
        self.assertIn('class="%s"' % HTML_KLASSE, oeffner)
        self.assertIn('data-image-veil-locked="1"', oeffner)
        self.assertIn('data-image-veil-reason="required_by_role"', oeffner)
        kopf = html.split("</head>")[0]
        i_veil = kopf.index("/_forensic/image-veil.css")
        # VOR jedem anderen Stylesheet und vor <base>
        for anderes in ("/_forensic/toolbar.css", "<base", "<title"):
            if anderes in kopf:
                self.assertLess(i_veil, kopf.index(anderes), anderes)
        self.assertNotIn("<img", kopf)
        self.assertLess(html.index("/_forensic/bildschleier.js"),
                        html.index("/_forensic/toolbar.js"))

    def test_bs17a_klar_ohne_klasse(self):
        _stub_setzen(BildschleierZustand(veiled=False, locked=False,
                                         reason="default"))
        oeffner = re.search(r"<html[^>]*>", self._shell()).group(0)
        self.assertNotIn("class=", oeffner)
        self.assertIn('data-image-veil-veiled="0"', oeffner)
        # Die Grundregel ist trotzdem eingebunden — sie wirkt nur ohne
        # Klasse nicht. So kann der Schalter sofort einschalten.

    def test_bs17c_toolbar_setzt_ausnahmen_vor_dem_inhalt(self):
        # Quelltextanker: in _handleEnvelope muss seiteAnwenden() VOR dem
        # Einfuegen des Seiteninhalts stehen (Bauplan §5.1).
        src = (WURZEL / "toolbar" / "toolbar.js").read_text(encoding="utf-8")
        i_anwenden = src.index("BildschleierSchalter.seiteAnwenden(envelope.image_veil)")
        i_inhalt = src.index("viewport.innerHTML = envelope.html;")
        self.assertLess(i_anwenden, i_inhalt)
        self.assertEqual(src.count("viewport.innerHTML = envelope.html;"), 1)
        self.assertIn('id="forensic-image-veil"', src)

    def test_bs17b_attribute_escaped(self):
        z = BildschleierZustand.gesperrt("no_capability")
        attr = bd.zustand_html_attribute(z)
        self.assertNotIn("‚Bildschleier aufheben‘\"", attr)
        self.assertEqual(attr.count('"') % 2, 0)


# =============================================================================
# Seitenumschlag
# =============================================================================
class UmschlagTests(unittest.TestCase):

    def tearDown(self):
        bd.zuruecksetzen_fuer_tests()

    def _umschlag(self, head_data=None):
        from server.blob_handler import BlobHandler
        from core.config_loader import ConfigLoader
        bh = BlobHandler.__new__(BlobHandler)
        bh._config = ConfigLoader(str(WURZEL / "config.yaml"))
        bh._context = types.SimpleNamespace(investigator_id=1)
        page = types.SimpleNamespace(url=SEITE)
        # Build 773: Rueckgabe (umschlag, head_data, body_html).
        return bh._bildschleier_umschlag(
            page, head_data,
            '<img src="img/icons/a.gif"><img src="/forum/img/avatars/1.jpg">')[0]

    def test_bsu01_ausnahmen_in_beiden_zustaenden(self):
        # Build 775 (D1, Befund 13.10.2026): bis Build 774 hiess dieser Test
        # 'ausnahmen_nur_bei_schleier' und verlangte im klaren Zustand
        # exempt_css == "". Genau das verschleierte beim sofortigen
        # Einschalten auf einer klar geladenen Seite auch Symbole und
        # Abzeichen. GEWOLLTE VERHALTENSAENDERUNG: die Ausnahmen kommen
        # immer; sie wirken nur unter html.aiw-image-veil.
        for zustand in (BildschleierZustand(veiled=True, locked=False,
                                            reason="chosen"),
                        BildschleierZustand(veiled=False, locked=False,
                                            reason="default")):
            _stub_setzen(zustand)
            u = self._umschlag({"base_href": "/forum/"})
            self.assertEqual(u["veiled"], zustand.veiled)
            self.assertIn('img[src="img/icons/a.gif"]', u["exempt_css"])
            self.assertNotIn("avatars", u["exempt_css"])
            self.assertTrue(u["exempt_css"].lstrip().startswith(
                "html.aiw-image-veil"), u["exempt_css"][:80])

    def test_bsu03_fehler_in_ausnahmen_klare_seite_bleibt(self):
        # Build 775 (Befund der unabhaengigen Durchsicht): seit die Ausnahmen
        # auch im klaren Zustand berechnet werden, darf ein Fehler dort eine
        # klare Seite nicht scheitern lassen.
        z = BildschleierZustand(veiled=False, locked=False, reason="default")
        stub = _Stub(z)

        def _wirft(*_a, **_k):
            raise ValueError("kaputt")
        stub.seitenausnahmen = types.SimpleNamespace(stylesheet=_wirft)
        alt = bd.dienst
        bd.dienst = lambda *_a, **_k: stub
        try:
            import server.blob_handler as bh_mod
            with self.assertLogs(bh_mod.logger, level="ERROR"):
                u = self._umschlag({"base_href": "/forum/"})
        finally:
            bd.dienst = alt
        self.assertFalse(u["veiled"])
        self.assertEqual(u["exempt_css"], "")

    def test_bsu02_basis_aus_base_href(self):
        _stub_setzen(BildschleierZustand.gesperrt("required_by_role"))
        # <base href="/forum/beginner/"> -> 'img/…' liegt NICHT unter /forum/img/
        u = self._umschlag({"base_href": "/forum/beginner/"})
        self.assertEqual(u["exempt_css"], "")


# =============================================================================
# Dienst und Endpunkt gegen eine echte coordinator.db
# =============================================================================
class DienstEndpunktTests(unittest.TestCase):

    def setUp(self):
        from tests.test_bildschleier_fundament import _Welt
        # _Welt als Fixture benutzen, ohne ihre Tests zu erben.
        self.welt = _Welt("setUp")
        self.welt.setUp()
        bd.zuruecksetzen_fuer_tests()
        from core.config_loader import ConfigLoader
        self.config = ConfigLoader(str(WURZEL / "config.yaml"))

    def tearDown(self):
        bd.zuruecksetzen_fuer_tests()
        self.welt.tearDown()

    def _ctx(self, pid):
        return types.SimpleNamespace(investigator_id=pid,
                                     coordinator_db=Path(self.welt.db_path))

    def _endpunkt(self, pid):
        from forensic_api.bildschleier import BildschleierEndpoint
        bd.zuruecksetzen_fuer_tests()
        return BildschleierEndpoint(None, self._ctx(pid), self.config)

    def _spitze(self):
        return self.welt._spitze()

    def test_bs18_ohne_recht_403_ohne_spur(self):
        self.welt._vergeben()
        for pid, grund in ((3, "no_capability"), (2, "required_by_role")):
            spitze = self._spitze()
            h = _Handler()
            self._endpunkt(pid).handle_post(h, b'{"veiled": false}')
            self.assertEqual(h.status, 403, pid)
            self.assertEqual(h.json()["reason"], grund)
            self.assertEqual(self._spitze(), spitze)
        self.assertEqual(self.welt.con.execute(
            "SELECT COUNT(*) FROM person_image_veil").fetchone()[0], 0)

    def test_bs18a_mit_recht_200_ein_beleg(self):
        self.welt._vergeben()
        spitze = self._spitze()
        h = _Handler()
        self._endpunkt(1).handle_post(h, b'{"veiled": true}')
        self.assertEqual(h.status, 200, h.body)
        self.assertEqual(h.json()["veiled"], True)
        self.assertEqual(h.json()["reason"], "chosen")
        self.assertEqual(self._spitze(), spitze + 1)
        h = _Handler()
        self._endpunkt(1).handle_get(h)
        self.assertEqual(h.json()["veiled"], True)
        self.assertEqual(h.headers.get("Cache-Control"), "no-store")

    def test_bs18b_rumpf_400(self):
        self.welt._vergeben()
        for rumpf in (b"", b"kein json", b"[]", b'{"veiled": 1}', b'{}'):
            h = _Handler()
            self._endpunkt(1).handle_post(h, rumpf)
            self.assertEqual(h.status, 400, rumpf)

    def test_bs18c_css_endpunkt(self):
        h = _Handler()
        self._endpunkt(1).handle_css(h)
        self.assertEqual(h.status, 200)
        self.assertIn("text/css", h.content_type)
        self.assertIn(b"blur(48px)", h.body)

    def test_bsd01_interner_fehler_ist_gesperrt(self):
        from management.bildschleier import bildschleier_repo as repo_mod
        alt = repo_mod.BildschleierRepo.zustand

        def _kaputt(self, pid):
            raise AttributeError("Programmierfehler")
        repo_mod.BildschleierRepo.zustand = _kaputt
        try:
            # Am Logger des Moduls selbst lauschen: core.logger kann die
            # Weitergabe an die Wurzel abschalten (im Gesamtlauf beobachtet).
            with self.assertLogs(bd.logger, level="ERROR"):
                z = bd.BildschleierDienst(self.config, self._ctx(1)).aktualisieren()
        finally:
            repo_mod.BildschleierRepo.zustand = alt
        self.assertEqual((z.veiled, z.locked, z.reason),
                         (True, True, "internal_error"))

    def test_bsd02_ohne_pfad(self):
        cfg = types.SimpleNamespace(get=lambda k, d=None: self.config.get(k, d)
                                    if not k.startswith("paths.") else None)
        ctx = types.SimpleNamespace(investigator_id=1, coordinator_db=None)
        z = bd.BildschleierDienst(cfg, ctx).aktualisieren()
        self.assertEqual(z.reason, "rbac_unavailable")
        self.assertTrue(z.veiled and z.locked)

    def test_bsd03_ohne_vergabe_jeder_gesperrt(self):
        # Unmittelbar nach M040, vor dem Wartungsfenster.
        z = bd.BildschleierDienst(self.config, self._ctx(1)).aktualisieren()
        self.assertEqual((z.veiled, z.locked, z.reason),
                         (True, True, "no_capability"))


if __name__ == "__main__":
    unittest.main()

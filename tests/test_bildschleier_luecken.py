# =============================================================================
# tests/test_bildschleier_luecken.py
# IT-Forensisches Ermittlungswerkzeug — Bildschleier, Lueckenschluss (Build 773)
# =============================================================================
# Waechter BS23-BS30 (Bauplan Builds 771-773, §9).
#
#   BS23  Stylesheet: '../img/icons/x.png' aus /forum/style/Air.css bleibt,
#         '/pix/banner/s9/1.jpg' wird Platzhalter (asset_handler)
#   BS24  ohne Schleier wird CSS NICHT veraendert; CSS ist nie cachebar
#   BS25  Direktaufruf (Sec-Fetch-Dest: document) eines Bildes -> Huelle
#   BS26  <img>-Abruf (Sec-Fetch-Dest: image) -> unveraenderte Bytes
#   BS27  ohne Sec-Fetch-Dest entscheidet Accept
#   BS28  keine Huelle fuer ausgenommene Bilder und ohne Schleier
#   BS29  jede Bildantwort traegt Vary: Sec-Fetch-Dest, Accept
#   BS30  <style>-Bloecke im Seiteninhalt und im Kopf: url() ersetzt, sonst
#         kein Zeichen des Inhalts veraendert
#   BSw*  CSS-Umschreiber: Schriften/Stylesheets/#-Anker bleiben, data: wird
#         ersetzt, image-set() mit blossen Zeichenketten
#   BSf*  fileasset: Huelle fuer den Image-Hoster, Bytes fuer Forenelemente,
#         CSS-Ersetzung mit der vollen URL als Basis
#   BSp   Platzhalter-Endpunkt
#
# MUTATIONSGEGENPROBEN (gefahren in Build 773, Ergebnis im build.json):
#   M10 Huelle in asset_handler ohne Pruefung des Schleiers -> BS28 rot
#   M11 ist_dokumentanfrage liefert immer False             -> BS25 rot
#   M12 Vary-Kopf entfernt                                  -> BS29 rot
#   M13 Schrift-Ausnahme im Umschreiber entfernt            -> BSw01 rot
#       (im ersten Lauf GRUEN: die Schriften lagen unter /forum/style/ und
#       wurden von der Ausnahmeregel gehalten. BSw01 prueft seither unter
#       einer Basis ausserhalb der Ausnahmen.)
#
# Version: v0.8.773 · Build: 773 · 2026-10-09
# =============================================================================

from __future__ import annotations

import sys
import types
import unittest
import urllib.parse
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

from core import bildschleier_dienst as bd                           # noqa: E402
from core.bildschleier_css_umschreiber import (                      # noqa: E402
    PLATZHALTER, BildschleierCssUmschreiber,
)
from management.bildschleier.bildschleier_zustand import (           # noqa: E402
    BildschleierZustand,
)
from server.bildschleier_huelle import VARY, BildschleierHuelle      # noqa: E402
from tests.test_bildschleier_viewer import (                         # noqa: E402
    FORUM, HOSTER, SEITE, _Handler, _regel, _stub_setzen,
)

VERSCHLEIERT = BildschleierZustand(veiled=True, locked=False, reason="chosen")
KLAR = BildschleierZustand(veiled=False, locked=False, reason="default")

CSS = (".a{background:url(../img/icons/x.png)}\n"
       ".banner1{background-image: url(\"/pix/banner/s9/1.jpg\");}\n"
       "@font-face{src:url(fonts/x.woff2)}\n")
BILD = b"\x89PNG\r\n\x1a\nBILDBYTES"


class _Kopf(dict):
    """headers-Ersatz mit .get() wie http.client.HTTPMessage."""


def _handler(dest=None, accept=None, pfad=None):
    h = _Handler()
    kopf = _Kopf()
    if dest is not None:
        kopf["Sec-Fetch-Dest"] = dest
    if accept is not None:
        kopf["Accept"] = accept
    h.headers_in = kopf
    # http_server.ForensicRequestHandler: 'headers' sind die ANFRAGE-Koepfe,
    # 'path' der Pfad mit Query.
    h.headers = kopf
    h.path = pfad
    return h


def _bundle(assets):
    """assets: {url_path: (bytes, mime)} — Kaskade wie im Bestand."""
    def _get(url):
        if url in assets:
            data, mime = assets[url]
            return types.SimpleNamespace(data=data, mime_type=mime)
        return None
    return types.SimpleNamespace(
        assets=types.SimpleNamespace(get_asset=_get,
                                     get_known_full_urls=lambda c: set()),
        default=types.SimpleNamespace(get_asset=lambda u: None))


def _asset_handler(assets):
    from core.config_loader import ConfigLoader
    from server.asset_handler import AssetHandler
    return AssetHandler(_bundle(assets),
                        ConfigLoader(str(WURZEL / "config.yaml")),
                        types.SimpleNamespace(investigator_id=1))


def _antwort_kopf(h, name):
    # _Handler (test_bildschleier_viewer) legt die ANTWORT-Koepfe in
    # .headers ab — beim Senden ueberschrieben.
    return h.headers.get(name)


class _MitStub(unittest.TestCase):
    def tearDown(self):
        bd.zuruecksetzen_fuer_tests()


# =============================================================================
# CSS-Umschreiber
# =============================================================================
class UmschreiberTests(unittest.TestCase):

    def setUp(self):
        self.u = BildschleierCssUmschreiber(_regel())

    def test_bsw01_schriften_stylesheets_anker_bleiben(self):
        css = ("@font-face{src:url(f/x.woff2) format('woff2'),url('f/x.ttf')}"
               "@import url(\"other.css\");.g{fill:url(#verlauf)}")
        # Basis AUSSERHALB der Ausnahmeverzeichnisse: dann haelt NUR die
        # Endungsregel die Schriften und Stylesheets — unter /forum/style/
        # hielte sie die Ausnahmeregel ohnehin (Lehre aus Mutation M13).
        neu, n = self.u.umschreiben(css, "/forum/extensions/x/a.css")
        self.assertEqual(n, 0)
        self.assertEqual(neu, css)
        # Gegenprobe: ein Bild unter derselben Basis WIRD ersetzt.
        neu, n = self.u.umschreiben(".b{background:url(f/x.png)}",
                                    "/forum/extensions/x/a.css")
        self.assertEqual(n, 1)

    def test_bsw02_data_und_fremde_werden_ersetzt(self):
        css = (".c{background:url(data:image/png;base64,AAAA)}"
               ".d{background:url(http://%s/images/0/a/b)}"
               ".e{background:url(data:font/woff2;base64,AAAA.woff2)}" % HOSTER)
        neu, n = self.u.umschreiben(css, "/forum/style/Air.css")
        self.assertEqual(n, 3)
        self.assertNotIn("base64", neu)
        self.assertNotIn(HOSTER, neu)

    def test_bsw03_image_set(self):
        css = ('.f{background:image-set("/uploads/a.jpg" 1x, '
               'url(/forum/img/b.png) 2x, "/forum/img/c.png" 3x)}')
        neu, n = self.u.umschreiben(css, "/forum/style/Air.css")
        self.assertEqual(n, 1)
        self.assertIn('"%s" 1x' % PLATZHALTER, neu)
        self.assertIn("url(/forum/img/b.png) 2x", neu)
        self.assertIn('"/forum/img/c.png" 3x', neu)

    def test_bsw04_schreibung_und_leerraum(self):
        neu, n = self.u.umschreiben(
            ".x{background:URL( '/forum/img/avatars/1.jpg' )}", "/")
        self.assertEqual(n, 1)
        self.assertIn(PLATZHALTER, neu)


# =============================================================================
# asset_handler
# =============================================================================
class AssetHandlerTests(_MitStub):

    def test_bs23_stylesheet_ersetzt(self):
        _stub_setzen(VERSCHLEIERT)
        h = _handler(dest="style")
        _asset_handler({"/forum/style/Air.css": (CSS.encode(), "text/css")}
                       ).handle(h, "/forum/style/Air.css")
        text = h.body.decode()
        self.assertIn("url(../img/icons/x.png)", text)
        self.assertNotIn("/pix/banner", text)
        self.assertIn(PLATZHALTER, text)
        self.assertIn("url(fonts/x.woff2)", text)
        self.assertEqual(_antwort_kopf(h, "Cache-Control"), "no-store")

    def test_bs24_ohne_schleier_unveraendert(self):
        _stub_setzen(KLAR)
        h = _handler(dest="style")
        _asset_handler({"/forum/style/Air.css": (CSS.encode(), "text/css")}
                       ).handle(h, "/forum/style/Air.css")
        self.assertEqual(h.body.decode(), CSS)
        self.assertEqual(_antwort_kopf(h, "Cache-Control"), "no-store")

    def test_bs25_direktaufruf_huelle(self):
        _stub_setzen(VERSCHLEIERT)
        pfad = "/forum/img/avatars/18.jpg?m=1"
        h = _handler(dest="document", pfad=pfad)
        _asset_handler({"/forum/img/avatars/18.jpg": (BILD, "image/jpeg")}
                       ).handle(h, "/forum/img/avatars/18.jpg")
        self.assertEqual(h.status, 200)
        self.assertIn("text/html", h.content_type)
        seite = h.body.decode()
        self.assertIn('<html class="aiw-image-veil">', seite)
        self.assertIn('src="/forum/img/avatars/18.jpg?m=1"', seite)
        self.assertIn("/_forensic/image-veil.css", seite)
        self.assertIn('id="forensic-viewport"', seite)
        self.assertNotIn(BILD, h.body)
        self.assertEqual(_antwort_kopf(h, "Cache-Control"), "no-store")

    def test_bs26_img_abruf_bytes(self):
        _stub_setzen(VERSCHLEIERT)
        h = _handler(dest="image", accept="image/avif,image/webp,*/*")
        _asset_handler({"/forum/img/avatars/18.jpg": (BILD, "image/jpeg")}
                       ).handle(h, "/forum/img/avatars/18.jpg")
        self.assertEqual(h.body, BILD)
        self.assertEqual(h.content_type, "image/jpeg")

    def test_bs27_accept_als_rueckfall(self):
        _stub_setzen(VERSCHLEIERT)
        h = _handler(accept="text/html,application/xhtml+xml,*/*;q=0.8",
                     pfad="/forum/img/avatars/18.jpg")
        _asset_handler({"/forum/img/avatars/18.jpg": (BILD, "image/jpeg")}
                       ).handle(h, "/forum/img/avatars/18.jpg")
        self.assertIn("text/html", h.content_type)
        h = _handler(accept="image/webp,*/*")
        _asset_handler({"/forum/img/avatars/18.jpg": (BILD, "image/jpeg")}
                       ).handle(h, "/forum/img/avatars/18.jpg")
        self.assertEqual(h.body, BILD)

    def test_bs28_keine_huelle_ausgenommen_oder_klar(self):
        _stub_setzen(VERSCHLEIERT)
        h = _handler(dest="document", pfad="/forum/img/icons/sticky.gif")
        _asset_handler({"/forum/img/icons/sticky.gif": (BILD, "image/gif")}
                       ).handle(h, "/forum/img/icons/sticky.gif")
        self.assertEqual(h.body, BILD)
        _stub_setzen(KLAR)
        h = _handler(dest="document", pfad="/forum/img/avatars/18.jpg")
        _asset_handler({"/forum/img/avatars/18.jpg": (BILD, "image/jpeg")}
                       ).handle(h, "/forum/img/avatars/18.jpg")
        self.assertEqual(h.body, BILD)

    def test_bs29_vary_an_jedem_bild(self):
        for z in (VERSCHLEIERT, KLAR):
            _stub_setzen(z)
            h = _handler(dest="image")
            _asset_handler({"/forum/img/icons/a.gif": (BILD, "image/gif")}
                           ).handle(h, "/forum/img/icons/a.gif")
            self.assertEqual(_antwort_kopf(h, "Vary"), VARY)

    def test_bs29a_ohne_config_alter_aufruf(self):
        # Aeltere Aufrufer (AssetHandler(bundle)) bleiben lauffaehig.
        from server.asset_handler import AssetHandler
        h = _handler(dest="document")
        AssetHandler(_bundle({"/forum/img/a.gif": (BILD, "image/gif")})
                     ).handle(h, "/forum/img/a.gif")
        self.assertEqual(h.body, BILD)


# =============================================================================
# Huelle (rein)
# =============================================================================
class HuelleTests(unittest.TestCase):

    def test_bs25a_erkennung(self):
        H = BildschleierHuelle
        self.assertTrue(H.ist_dokumentanfrage({"Sec-Fetch-Dest": "document"}))
        self.assertTrue(H.ist_dokumentanfrage({"Sec-Fetch-Dest": "iframe"}))
        self.assertFalse(H.ist_dokumentanfrage({"Sec-Fetch-Dest": "image",
                                                "Accept": "text/html"}))
        self.assertFalse(H.ist_dokumentanfrage({"Sec-Fetch-Dest": "style"}))
        self.assertTrue(H.ist_dokumentanfrage({"Accept": "TEXT/HTML"}))
        self.assertFalse(H.ist_dokumentanfrage({}))
        self.assertFalse(H.ist_dokumentanfrage(None))

    def test_bs25b_escaping(self):
        seite = BildschleierHuelle.html('/x.png?a=1&b="><script>').decode()
        self.assertNotIn("<script>", seite)
        self.assertIn("&quot;&gt;&lt;script&gt;", seite)

    def test_bs25c_bildarten(self):
        self.assertTrue(BildschleierHuelle.ist_bild("image/svg+xml"))
        self.assertTrue(BildschleierHuelle.ist_bild("IMAGE/PNG; x=1"))
        self.assertFalse(BildschleierHuelle.ist_bild("text/css"))
        self.assertFalse(BildschleierHuelle.ist_bild(None))


# =============================================================================
# fileasset
# =============================================================================
class FileassetTests(_MitStub):

    def _ep(self, url, data, mime):
        from core.config_loader import ConfigLoader
        from db.assets_db import BEFUND_KEIN_TREFFER, BEFUND_OK
        from forensic_api.fileasset import FileassetEndpoint

        def _befund(u):
            if u == url:
                return types.SimpleNamespace(data=data, mime_type=mime), BEFUND_OK
            return None, BEFUND_KEIN_TREFFER
        bundle = types.SimpleNamespace(assets=types.SimpleNamespace(
            get_asset_by_full_url_befund=_befund))
        return FileassetEndpoint(bundle, ConfigLoader(str(WURZEL / "config.yaml")),
                                 types.SimpleNamespace(investigator_id=1))

    def test_bsf01_image_hoster_huelle(self):
        _stub_setzen(VERSCHLEIERT)
        url = "http://%s/images/0/abc/def" % HOSTER
        pfad = "/_forensic/fileasset?url=" + urllib.parse.quote(url, safe="")
        h = _handler(dest="document", pfad=pfad)
        self._ep(url, BILD, "image/jpeg").handle(h, {"url": [url]})
        self.assertIn("text/html", h.content_type)
        self.assertIn(pfad.replace("&", "&amp;"), h.body.decode())
        h = _handler(dest="image")
        self._ep(url, BILD, "image/jpeg").handle(h, {"url": [url]})
        self.assertEqual(h.body, BILD)
        self.assertEqual(_antwort_kopf(h, "Vary"), VARY)
        self.assertEqual(_antwort_kopf(h, "Cache-Control"), "max-age=3600, immutable")

    def test_bsf02_forenelement_bytes(self):
        _stub_setzen(VERSCHLEIERT)
        url = "http://%s/forum/img/smilies/a.png" % FORUM
        h = _handler(dest="document")
        self._ep(url, BILD, "image/png").handle(h, {"url": [url]})
        self.assertEqual(h.body, BILD)

    def test_bsf03_css_mit_voller_url_als_basis(self):
        _stub_setzen(VERSCHLEIERT)
        url = "http://%s/forum/style/x.css" % FORUM
        h = _handler(dest="style")
        self._ep(url, CSS.encode(), "text/css").handle(h, {"url": [url]})
        text = h.body.decode()
        self.assertIn("url(../img/icons/x.png)", text)
        self.assertIn(PLATZHALTER, text)
        self.assertEqual(_antwort_kopf(h, "Cache-Control"), "no-store")


# =============================================================================
# Seitenumschlag: <style>-Bloecke
# =============================================================================
class StilblockTests(_MitStub):

    def _bh(self):
        from core.config_loader import ConfigLoader
        from server.blob_handler import BlobHandler
        bh = BlobHandler.__new__(BlobHandler)
        bh._config = ConfigLoader(str(WURZEL / "config.yaml"))
        bh._context = types.SimpleNamespace(investigator_id=1)
        return bh

    def test_bs30_stilbloecke(self):
        _stub_setzen(VERSCHLEIERT)
        body = ('<div id="p1"><style type="text/css">.x{background:'
                'url(/uploads/a.jpg)} .y{background:url(img/icons/b.png)}'
                '</style><p>Text</p></div>')
        head = {"base_href": "/forum/",
                "inline_styles": [".z{background:url(/pix/x.png)}"]}
        umschlag, head2, body2 = self._bh()._bildschleier_umschlag(
            types.SimpleNamespace(url=SEITE), head, body)
        self.assertNotIn("/uploads/a.jpg", body2)
        self.assertIn("url(img/icons/b.png)", body2)
        self.assertIn(PLATZHALTER, body2)
        # ausserhalb von <style> unveraendert
        rest = body2.split("</style>")[1]
        self.assertEqual(rest, body.split("</style>")[1])
        self.assertTrue(body2.startswith('<div id="p1"><style type="text/css">'))
        self.assertNotIn("/pix/x.png", head2["inline_styles"][0])
        # der Eingang bleibt unveraendert (kein Seiteneffekt auf head_data)
        self.assertIn("/pix/x.png", head["inline_styles"][0])

    def test_bs30a_ohne_schleier_nichts(self):
        _stub_setzen(KLAR)
        body = '<style>.x{background:url(/uploads/a.jpg)}</style>'
        head = {"inline_styles": [".z{background:url(/pix/x.png)}"]}
        _u, head2, body2 = self._bh()._bildschleier_umschlag(
            types.SimpleNamespace(url=SEITE), head, body)
        self.assertEqual(body2, body)
        self.assertEqual(head2, head)


# =============================================================================
# Platzhalter
# =============================================================================
class PlatzhalterTests(_MitStub):

    def test_bsp_platzhalter(self):
        from forensic_api.bildschleier import BildschleierEndpoint
        h = _Handler()
        BildschleierEndpoint(None, None, None).handle_placeholder(h)
        self.assertEqual(h.status, 200)
        self.assertEqual(h.content_type, "image/svg+xml")
        self.assertTrue(h.body.startswith(b"<svg"))
        self.assertEqual(PLATZHALTER, "/_forensic/image-veil-placeholder.svg")


if __name__ == "__main__":
    unittest.main()

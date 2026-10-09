# =============================================================================
# core/bildschleier_css.py
# IT-Forensisches Ermittlungswerkzeug — Bildschleier (Build 772)
# =============================================================================
# Zweck:
#   Erzeugt die GRUNDREGEL des Bildschleiers: ein Stylesheet, das JEDES Bild
#   im Viewport verschleiert, sobald <html> die Klasse 'aiw-image-veil' traegt.
#   Ausgeliefert unter /_forensic/image-veil.css und von der Shell im <head>
#   VOR jedem Seiteninhalt eingebunden (server/shell_handler.py).
#
# ── DIE REIHENFOLGE-GARANTIE (Bauplan §5.1, Festlegung F1) ─────────────────
#
#   Die Shell setzt die Klasse serverseitig und bindet dieses Stylesheet als
#   blockierendes <link> ein. Der Seiteninhalt (BLOB) kommt erst danach per
#   AJAX. Die Regel existiert also, BEVOR ein einziges <img> im Dokument
#   steht — ein Aufblitzen des Originals ist ausgeschlossen, nicht nur
#   unwahrscheinlich.
#
#   Diese Datei kennt KEINE Ausnahmen. Ausnahmen kommen je Seite mit dem
#   Seitenumschlag (core/bildschleier_seitenausnahmen.py) und koennen nur
#   ENTschleiern. Fehlen sie oder kommen sie zu spaet, wird zu viel
#   verschleiert, nie zu wenig.
#
# ── WARUM DIE KUENSTLICHE SPEZIFITAET ──────────────────────────────────────
#
#   Nach jedem Seitenwechsel bindet toolbar.js die Stylesheets des Forums in
#   den <head> ein (_updateHead). Ein Forenstylesheet mit einer eigenen
#   'filter: ... !important'-Regel und hoeherer Spezifitaet wuerde unsere
#   Regel schlagen. Gemessen im Forenquelltext: es gibt solche Regeln
#   (style/old.css Z. 9, style/light/light.css Z. 77), heute nur auf 'body'.
#   Damit das so bleibt, gleich welche Forenregel kommt, traegt der Selektor
#   vier ':not(#…)'-Glieder; jedes zaehlt wie eine ID (Selectors Level 4).
#   Die Spezifitaet ist damit (5,1,x) — keine Forenregel mit weniger als fuenf
#   IDs kommt darueber.
#
# ── WAS VERSCHLEIERT WIRD ───────────────────────────────────────────────────
#
#   img, picture, input[type=image], video, object, embed, iframe, canvas,
#   'image' in SVG, Elemente mit 'background'-Attribut und Elemente mit
#   'url(' im style-Attribut (Inline-Hintergruende, z. B. das Kopfbanner,
#   forum/html/include/functions.php Z. 992). Bei Inline-Hintergruenden wird
#   das ganze Element verschleiert, auch sein Text — die sichere Richtung.
#
#   Die Filterkette kommt aus config.yaml (image_veil.filter; Festlegung F7,
#   Alex 09.10.2026).
#
# Version: v0.8.772 · Build: 772 · 2026-10-09
# =============================================================================

from __future__ import annotations

import re
from typing import Any

#: Klasse an <html>, die den Schleier einschaltet.
HTML_KLASSE = "aiw-image-veil"

#: Vier ID-Glieder fuer die Spezifitaet (siehe Kopf). Die IDs gibt es nicht.
_SPEZIFITAET = "".join(":not(#aiw-iv-%d)" % i for i in range(1, 5))

#: Der gemeinsame Anfang jedes Schleier-Selektors. Die Seitenausnahmen
#: benutzen DENSELBEN Anfang und sind durch ihr zusaetzliches Attribut
#: spezifischer — sie gewinnen gegen die Grundregel.
SELEKTOR_PRAEFIX = "html.%s%s #forensic-viewport" % (HTML_KLASSE, _SPEZIFITAET)

#: CSS-Funktionen, mit denen ein Inline-Stil eine Bildquelle traegt. Die
#: Seitenausnahmen (core/bildschleier_seitenausnahmen.py) benutzen DIESELBE
#: Liste: ein Stil mit einer dieser Funktionen ausser 'url(' wird nie
#: ausgenommen.
INLINE_BILDFUNKTIONEN = ("url(", "image-set(", "image(", "src(",
                         "element(", "cross-fade(")

#: Was verschleiert wird.
_ZIELE = (
    "img", "picture", "input[type=image]", "video", "object", "embed",
    "iframe", "canvas", "svg image", "svg:has(image)", "[background]",
) + tuple(
    # Inline-Stile mit einer Bildquelle. 'i': ohne Ruecksicht auf die
    # Schreibung — 'URL(' wirkt in CSS genauso. Nicht nur 'url(': auch
    # image-set("a.png" 1x) traegt eine Bildquelle ohne 'url('.
    '[style*="%s" i]' % f for f in INLINE_BILDFUNKTIONEN
) + (
    # Ein Rueckstrich im style-Attribut kann ein CSS-Escape sein
    # ('u\\72l(' == 'url('). Was so geschrieben ist, wird verschleiert.
    '[style*="\\\\"]',
)

#: Vorgabe der Filterkette (F7). Steht zusaetzlich in
#: core/config_loader._DEFAULTS; hier nur als letzte Rueckfallebene, falls
#: der Schluessel fehlt.
VORGABE_FILTER = "blur(48px) grayscale(100%) contrast(35%) brightness(115%)"

#: Erlaubte Zeichen der Filterkette — sie landet woertlich im Stylesheet und
#: darf es nicht aufbrechen koennen (kein '{', '}', ';', '<').
_FILTER_ZEICHEN = re.compile(r"^[a-zA-Z0-9().%\s,-]+$")


class BildschleierCss:
    """Baut das Grundregel-Stylesheet."""

    def __init__(self, filterkette: str = VORGABE_FILTER) -> None:
        if not filterkette or not _FILTER_ZEICHEN.match(filterkette):
            raise ValueError(
                "image_veil.filter enthaelt unzulaessige Zeichen: %r"
                % (filterkette,))
        self._filter = filterkette.strip()

    @classmethod
    def aus_konfiguration(cls, config: Any) -> "BildschleierCss":
        return cls(str(config.get("image_veil.filter", VORGABE_FILTER)))

    @property
    def filterkette(self) -> str:
        return self._filter

    def stylesheet(self) -> str:
        """
        Das vollstaendige Stylesheet als Text.

        JEDES ZIEL BEKOMMT EINEN EIGENEN REGELBLOCK, und das ist Absicht:
        Enthaelt eine Selektorliste ('a, b, c { ... }') auch nur EINEN
        Selektor, den der Browser nicht versteht (etwa ':has()' in einem
        aelteren Browser), verwirft er die GANZE Regel — dann waere kein
        einziges Bild verschleiert. Getrennte Bloecke verlieren im selben
        Fall nur ihr eigenes Ziel.
        """
        bloecke = []
        for ziel in _ZIELE:
            bloecke.append(
                "%s %s {\n"
                "  filter: %s !important;\n"
                "  -webkit-filter: %s !important;\n"
                "  clip-path: inset(0) !important;\n"
                "}\n" % (SELEKTOR_PRAEFIX, ziel, self._filter, self._filter))
        return (
            "/* AiW Bildschleier — Grundregel (core/bildschleier_css.py).\n"
            "   Wirkt nur, wenn <html> die Klasse '%s' traegt.\n"
            "   Ein Block je Ziel: ein unbekannter Selektor verwirft so nur\n"
            "   seinen eigenen Block, nicht die ganze Regel. */\n"
            % HTML_KLASSE) + "".join(bloecke)

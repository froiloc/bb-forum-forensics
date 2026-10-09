# =============================================================================
# core/bildschleier_seitenausnahmen.py
# IT-Forensisches Ermittlungswerkzeug — Bildschleier (Build 772)
# =============================================================================
# Zweck:
#   Erzeugt fuer EINE ausgelieferte Seite die Ausnahmen vom Bildschleier: ein
#   kleines Stylesheet, das genau die Bilder entschleiert, die
#   core/bildschleier_regel.py als Forenelement erkennt (Symbole, Abzeichen,
#   Gestaltung). Es reist im Seitenumschlag (server/blob_handler.py) und wird
#   von toolbar/bildschleier.js VOR dem Einfuegen des Seiteninhalts gesetzt.
#
# ── WARUM EXAKTE WERTE UND KEINE PRAEFIXE (Abweichung vom Bauplan §5.2) ────
#
#   Der Bauplan sah Praefix-Selektoren vor ('img[src^="/forum/img/"]' samt
#   Ausschluessen). Beim Bau zeigte sich, dass ein Praefix-Selektor den
#   Attributwert WOERTLICH vergleicht, der Browser ihn aber AUFLOEST: '..',
#   '%2e%2e', Rueckstriche, doppelte Schraegstriche, Gross-/Kleinschreibung
#   — jede dieser Schreibweisen haette eine eigene Gegenregel gebraucht, und
#   eine vergessene waere ein unverschleiertes Bild gewesen.
#
#   Hier wird deshalb umgekehrt vorgegangen: Python liest JEDES Bild der
#   Seite, die Regel entscheidet mit voller URL-Aufloesung, und ausgenommen
#   wird jedes Bild mit seinem EXAKTEN Attributwert ('img[src="…"]'). Es gibt
#   keine Schreibweise mehr, die an der Regel vorbeikaeme: was nicht exakt
#   genannt ist, bleibt verschleiert. Gleichzeitig entfaellt die im Bauplan
#   dokumentierte Grenze bei zwei url() in einem Inline-Stil — der ganze Stil
#   wird geprueft.
#
# ── WAS AUSGENOMMEN WERDEN KANN ─────────────────────────────────────────────
#
#   * <img> mit ausgenommenem src, OHNE srcset (srcset kann der Browser statt
#     src waehlen) und mit einem style-Attribut, das selbst ausgenommen ist
#     oder fehlt. Der Selektor nennt beides exakt: img[src="…"][style="…"]
#     bzw. img[src="…"]:not([style]).
#   * Elemente, die KEIN Medienelement sind, mit einem style-Attribut, dessen
#     SAEMTLICHE url() ausgenommen sind und das keine andere Bildfunktion und
#     keinen Rueckstrich enthaelt (z. B. die Badges in top.php Z. 124-126).
#
#   Alles andere — video, object, iframe, svg image, [background], srcset —
#   wird NIE ausgenommen.
#
# ── WERTE WIE IM BROWSER ────────────────────────────────────────────────────
#
#   html.parser loest Entitaeten in Attributwerten auf (convert_charrefs),
#   genau wie der Browser beim Aufbau des DOM. Zusaetzlich normalisiert der
#   HTML-Eingabestrom CR LF und CR zu LF (HTML Standard, "preprocessing the
#   input stream") — das macht html.parser nicht, deshalb hier von Hand.
#   Der Selektor vergleicht dann denselben String wie der Browser.
#
#   Jede Ausnahme bekommt einen EIGENEN Regelblock (wie die Grundregel): ein
#   Wert, den der Browser als Selektor verwirft, verliert nur seine eigene
#   Ausnahme — das Bild bleibt dann verschleiert.
#
# Abhaengigkeiten: html.parser, re — Stdlib.
# Version: v0.8.772 · Build: 772 · 2026-10-09
# =============================================================================

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Dict, List, Optional, Set, Tuple

from core.bildschleier_css import INLINE_BILDFUNKTIONEN, SELEKTOR_PRAEFIX
from core.bildschleier_regel import BildschleierRegel
from core.logger import get_logger

logger = get_logger(__name__)

#: Elemente, die selbst Medien zeigen. Ein Inline-Stil an ihnen wird nie
#: allein ausgenommen (das Element koennte ueber src/data dennoch Inhalt
#: zeigen).
_MEDIEN = ("img", "picture", "input", "video", "object", "embed", "iframe",
           "canvas", "image", "svg", "source")

#: url( … ) in einem Inline-Stil, mit oder ohne Anfuehrungszeichen.
_URL_IM_STIL = re.compile(
    r"""url\(\s*(?:"([^"]*)"|'([^']*)'|([^)\s]*))\s*\)""", re.IGNORECASE)

#: Obergrenze, damit eine entartete Seite keinen Riesen-Umschlag erzeugt.
#: Wird sie erreicht, bleiben die uebrigen Bilder verschleiert — und es wird
#: gesagt (Grundregel 1).
MAX_AUSNAHMEN = 2000


def _browserwert(wert: Optional[str]) -> Optional[str]:
    if wert is None:
        return None
    return wert.replace("\r\n", "\n").replace("\r", "\n")


def css_zeichenkette(wert: str) -> str:
    """
    Setzt 'wert' als CSS-Zeichenkette in doppelte Anfuehrungszeichen.
    Escaped: Rueckstrich, Anfuehrungszeichen, alle Steuerzeichen (als
    Hex-Escape mit abschliessendem Leerzeichen), NUL wird U+FFFD (so verfaehrt
    auch der Browser mit NUL im DOM).
    """
    aus = ['"']
    for ch in wert:
        code = ord(ch)
        if ch == "\\":
            aus.append("\\\\")
        elif ch == '"':
            aus.append('\\"')
        elif code == 0:
            aus.append("�")
        elif code < 0x20 or code == 0x7F:
            aus.append("\\%x " % code)
        else:
            aus.append(ch)
    aus.append('"')
    return "".join(aus)


class _Sammler(HTMLParser):
    """Sammelt die fuer den Schleier relevanten Attribute einer Seite."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        #: (src, style|None, hat_srcset) je <img>
        self.bilder: List[Tuple[str, Optional[str], bool]] = []
        #: style-Werte an Nicht-Medienelementen mit einer Bildfunktion
        self.stile: List[str] = []

    def handle_starttag(self, tag, attrs):
        self._element(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._element(tag, attrs)

    def _element(self, tag: str, attrs) -> None:
        tag = tag.lower()
        werte: Dict[str, Optional[str]] = {}
        for name, wert in attrs:
            # Doppelte Attribute: der Browser nimmt das ERSTE.
            werte.setdefault(name.lower(), _browserwert(wert))
        stil = werte.get("style")
        if tag == "img":
            src = werte.get("src")
            if src is not None:
                self.bilder.append((src, stil, "srcset" in werte))
            return
        if tag in _MEDIEN:
            return
        if stil and any(f in stil.lower() for f in INLINE_BILDFUNKTIONEN):
            self.stile.append(stil)


class BildschleierSeitenausnahmen:
    """Baut das Ausnahme-Stylesheet fuer eine Seite."""

    def __init__(self, regel: BildschleierRegel) -> None:
        self._regel = regel

    def stil_ausgenommen(self, stil: str, basis: str) -> bool:
        """True, wenn ALLE Bildquellen des Inline-Stils ausgenommen sind."""
        klein = stil.lower()
        if "\\" in stil:
            return False
        # Jede andere Bildfunktion als url( schliesst aus.
        for f in INLINE_BILDFUNKTIONEN:
            if f != "url(" and f in klein:
                return False
        treffer = list(_URL_IM_STIL.finditer(stil))
        # So viele url( wie gefundene Ausdruecke — sonst steht ein url(, das
        # der Ausdruck nicht verstanden hat, und das wird nicht ausgenommen.
        if len(treffer) != klein.count("url("):
            return False
        if not treffer:
            return False
        for m in treffer:
            url = m.group(1) if m.group(1) is not None else (
                m.group(2) if m.group(2) is not None else m.group(3))
            if not self._regel.ist_ausgenommen(url, basis):
                return False
        return True

    def stylesheet(self, body_html: Optional[str], basis: str) -> str:
        """
        Das Ausnahme-Stylesheet (leer, wenn nichts auszunehmen ist).

        body_html — der Seiteninhalt GENAU so, wie er ausgeliefert wird
                    (nach _rewrite_asset_urls).
        basis     — wogegen relative Angaben aufgeloest werden (volle Seiten-
                    URL bzw. <base href> gegen sie aufgeloest).
        """
        if not body_html:
            return ""
        sammler = _Sammler()
        sammler.feed(body_html)
        sammler.close()

        selektoren: List[str] = []
        gesehen: Set[str] = set()
        verschleiert = 0
        for src, stil, hat_srcset in sammler.bilder:
            if hat_srcset or not self._regel.ist_ausgenommen(src, basis):
                verschleiert += 1
                continue
            if stil is not None and stil.strip() and \
                    any(f in stil.lower() for f in INLINE_BILDFUNKTIONEN) and \
                    not self.stil_ausgenommen(stil, basis):
                verschleiert += 1
                continue
            if stil is None:
                sel = "img[src=%s]:not([style]):not([srcset])" % css_zeichenkette(src)
            else:
                sel = "img[src=%s][style=%s]:not([srcset])" % (
                    css_zeichenkette(src), css_zeichenkette(stil))
            if sel not in gesehen:
                gesehen.add(sel)
                selektoren.append(sel)

        for stil in sammler.stile:
            if not self.stil_ausgenommen(stil, basis):
                continue
            sel = ("[style=%s]:not(img, picture, input, video, object, embed, "
                   "iframe, canvas, image, svg, source):not([background])"
                   % css_zeichenkette(stil))
            if sel not in gesehen:
                gesehen.add(sel)
                selektoren.append(sel)

        if len(selektoren) > MAX_AUSNAHMEN:
            logger.warning(
                "Bildschleier: %d Ausnahmen auf einer Seite, nur die ersten %d "
                "werden ausgeliefert — die uebrigen Forenelemente bleiben "
                "verschleiert.", len(selektoren), MAX_AUSNAHMEN)
            selektoren = selektoren[:MAX_AUSNAHMEN]

        logger.debug(
            "Bildschleier-Ausnahmen: %d Selektor(en), %d Bild(er) verschleiert, "
            "Basis '%s'", len(selektoren), verschleiert, basis)
        return "".join(
            "%s %s { filter: none !important; -webkit-filter: none !important;"
            " clip-path: none !important; }\n" % (SELEKTOR_PRAEFIX, s)
            for s in selektoren)

# =============================================================================
# core/bildschleier_css_umschreiber.py
# IT-Forensisches Ermittlungswerkzeug — Bildschleier (Build 773)
# =============================================================================
# Zweck:
#   Ersetzt in CSS-TEXT jede Bildquelle, die nicht vom Schleier ausgenommen
#   ist, durch einen neutralen grauen Platzhalter. Angewandt NUR bei aktivem
#   Schleier, und nur bei der Auslieferung — gespeicherte BLOBs und Assets
#   bleiben unberuehrt.
#
# ── WARUM DAS SERVERSEITIG GESCHIEHT (Bauplan §5.3) ─────────────────────────
#
#   Kein CSS-Selektor erreicht ein Bild, das eine CSS-REGEL einem Element
#   zuweist ('.banner1 { background-image: url(/pix/banner/s9/1.jpg) }',
#   forum/html/style/index.css Z. 584-587). Die URL steht nicht am Element,
#   sondern im Stylesheet. Der Server sieht sie aber in dem Moment, in dem er
#   das Stylesheet ausliefert — und entscheidet dort mit DERSELBEN Regel
#   (core/bildschleier_regel.py), gegen die Adresse des Stylesheets
#   aufgeloest: '../img/icons/x.png' aus '/forum/style/Air.css' wird zu
#   '/forum/img/icons/x.png' und bleibt.
#
#   Angewandt auf: Stylesheets aus server/asset_handler.py und
#   forensic_api/fileasset.py, <style>-Bloecke im Seitenkopf und im
#   Seiteninhalt (server/blob_handler.py).
#
# ── WAS NICHT ERSETZT WIRD ──────────────────────────────────────────────────
#
#   * Ausgenommene Bilder (die Regel).
#   * Schriften (.woff, .woff2, .ttf, .otf, .eot) und Stylesheets (.css,
#     @import): sie sind keine Bilder, und ein Platzhalter an ihrer Stelle
#     braeche Schrift oder Gestaltung, ohne etwas zu schuetzen. Das
#     Forenstylesheet ist statisch und stammt nicht von Forennutzern.
#   * Anker auf SVG-Fragmente im selben Dokument ('url(#verlauf)').
#
#   Alles andere — auch data:-URIs — wird ersetzt. Im Zweifel: Platzhalter.
#
# ── image-set() OHNE url() ──────────────────────────────────────────────────
#
#   image-set("a.png" 1x) traegt die Quelle als blosse Zeichenkette. Jede
#   Zeichenkette INNERHALB von image-set(…) wird deshalb wie eine url()
#   behandelt.
#
# Abhaengigkeiten: re — Stdlib.
# Version: v0.8.773 · Build: 773 · 2026-10-09
# =============================================================================

from __future__ import annotations

import re
from typing import Tuple

from core.bildschleier_regel import BildschleierRegel
from core.logger import get_logger

logger = get_logger(__name__)

#: Der Platzhalter (forensic_api/bildschleier.py liefert ihn aus).
PLATZHALTER = "/_forensic/image-veil-placeholder.svg"

#: url( … ), Anfuehrungszeichen erhalten. Gruppe 'q' ist das Zeichen,
#: 'u' der Inhalt.
_URL = re.compile(
    r"""url\(\s*(?P<q>["']?)(?P<u>.*?)(?P=q)\s*\)""",
    re.IGNORECASE | re.DOTALL)

#: image-set( … ) / -webkit-image-set( … ) — Inhalt bis zur passenden
#: Klammer auf einer Ebene (verschachtelte url() erledigt _URL).
_IMAGE_SET = re.compile(r"(?P<f>(?:-webkit-)?image-set\()(?P<inhalt>[^()]*(?:\([^()]*\)[^()]*)*)\)",
                        re.IGNORECASE)
_ZEICHENKETTE = re.compile(r"""(?P<q>["'])(?P<u>.*?)(?P=q)""", re.DOTALL)

#: Endungen, die keine Bilder sind (siehe Kopf).
_KEIN_BILD = re.compile(r"\.(?:woff2?|ttf|otf|eot|css)(?:[?#].*)?$", re.IGNORECASE)


class BildschleierCssUmschreiber:
    """Ersetzt nicht ausgenommene Bildquellen in CSS-Text."""

    def __init__(self, regel: BildschleierRegel) -> None:
        self._regel = regel

    def _behalten(self, url: str, basis: str) -> bool:
        roh = url.strip()
        if roh.startswith("#"):
            return True
        if _KEIN_BILD.search(roh) and "\\" not in roh \
                and not roh.lower().startswith("data:"):
            return True
        return self._regel.ist_ausgenommen(roh, basis)

    def umschreiben(self, css: str, basis: str) -> Tuple[str, int]:
        """
        Gibt (neuer_text, anzahl_ersetzt) zurueck.

        basis — Adresse des Stylesheets (Asset-Pfad oder volle URL) bzw. bei
                <style>-Bloecken die Basis der Seite.
        """
        if not css:
            return css, 0
        zaehler = [0]

        def _url(m: "re.Match") -> str:
            if self._behalten(m.group("u"), basis):
                return m.group(0)
            zaehler[0] += 1
            return 'url("%s")' % PLATZHALTER

        def _set(m: "re.Match") -> str:
            def _str(s: "re.Match") -> str:
                if self._behalten(s.group("u"), basis):
                    return s.group(0)
                zaehler[0] += 1
                return '"%s"' % PLATZHALTER
            # url(...) darin hat _URL schon behandelt — diese Stuecke werden
            # unveraendert uebernommen, nur die Abschnitte DAZWISCHEN auf
            # blosse Zeichenketten durchsucht.
            inhalt = m.group("inhalt")
            teile, pos = [], 0
            for u in _URL.finditer(inhalt):
                teile.append(_ZEICHENKETTE.sub(_str, inhalt[pos:u.start()]))
                teile.append(u.group(0))
                pos = u.end()
            teile.append(_ZEICHENKETTE.sub(_str, inhalt[pos:]))
            return m.group("f") + "".join(teile) + ")"

        neu = _URL.sub(_url, css)
        neu = _IMAGE_SET.sub(_set, neu)
        if zaehler[0]:
            logger.debug("Bildschleier: %d Bildquelle(n) in CSS ersetzt "
                         "(Basis '%s')", zaehler[0], basis)
        return neu, zaehler[0]

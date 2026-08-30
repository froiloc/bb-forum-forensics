# =============================================================================
# report_render/html5_zerleger.py
# IT-Forensisches Ermittlungswerkzeug - Zerlegung nach dem HTML5-Standard
# =============================================================================
# Zweck:
#   DEN SEITENABZUG SO ZERLEGEN, WIE EIN BROWSER IHN ZERLEGT - nicht
#   annaehernd, sondern nach demselben Verfahren.
#
# ── WARUM DAS ENTSCHEIDEND IST ───────────────────────────────────────────────
#
#   Der Anker einer Textmarkierung wird IM BROWSER gerechnet (toolbar.js,
#   '_xpathOf') und SERVERSEITIG aufgeloest (report_render/absatz_finder.py).
#   Sehen beide nicht denselben Baum, zeigt ein richtiger Anker ins Leere.
#
#   libxml2 (ueber lxml.html) folgt NICHT dem HTML5-Baumaufbau. Die
#   Unterschiede sind nicht kosmetisch: sie verschieben ganze Zweige.
#
# ── DER BEFUND, DER ZU DIESER DATEI GEFUEHRT HAT (31.08.2026) ────────────────
#
#   Gegenprobe im Browser am echten Abzug (Chromium in der Ermittlungs-VM,
#   Seite /forum/viewtopic.php?id=1989, 1.351.607 Zeichen), Belege #16 und
#   #25 aus evidence_155955.db:
#
#     Alle zwoelf Ankerschritte loesen auf, bis zum Textknoten.
#     '#page-body' haengt unter 'div#wrap' und traegt 500 direkte <article>.
#
#   DER ANKER IST RICHTIG. DER ABZUG IST VOLLSTAENDIG. Was die Auswertung
#   daraus machte, war es nicht:
#
#     Zerlegung                      '#page-body' unter   <article> darin
#     -------------------------------------------------------------------
#     Browser (der Massstab)         div#wrap                  500
#     libxml2 roh                    div#page-header           500
#     libxml2 + Annaeherung 742-746  div#wrap                    2
#
#   DIE ANNAEHERUNG WAR EIN HANDGEBAUTER TEILNACHBAU des HTML5-Baumaufbaus.
#   Sie bildete EINE Regel nach ("pop until X popped"), spaeter zwei. Fuenf
#   Builds lang wurde je ein Konstrukt geheilt und ein neues zerbrochen -
#   zuletzt riss sie '#page-body' nach dem zweiten Beitrag auf und liess 498
#   Beitraege herausfallen. EINE HALB NACHGEBILDETE REGEL IST GEFAEHRLICHER
#   ALS KEINE: sie wirkt an Stellen, an denen nichts kaputt war.
#
#   html5lib fuehrt den GANZEN Algorithmus aus - denselben, den der Browser
#   ausfuehrt. Damit entfaellt der Nachbau ersatzlos; er wird nicht ersetzt,
#   sondern ueberfluessig.
#
# ── GEMESSEN, NICHT ANGENOMMEN (31.08.2026, 17 Konstrukte) ───────────────────
#
#   Gehalten gegen Chromium (Playwright, 'innerHTML' auf einen <div> - genau
#   der Weg des Ermittlungsfensters):
#
#     Verfahren                                   stimmt mit dem Browser
#     ---------------------------------------------------------------------
#     lxml.html roh                                      7 von 17
#     lxml.html + Annaeherung (Build 742-746)           16 von 17
#     html5lib, scripting=True, <template> geleert      17 von 17
#
# ── DIE BEIDEN EINSTELLUNGEN, UND WARUM SIE NOETIG SIND ──────────────────────
#
#   (1) scripting=True
#       HTML5 kennt ein 'scripting flag'. Ist es gesetzt, ist der INHALT von
#       <noscript> ROHTEXT - kein einziges Tag darin wird zu einem Element.
#       Das Ermittlungsfenster IST eine JavaScript-Anwendung (die Toolbar),
#       fuer es gilt die Regel also immer. html5lib setzt das Flag von sich
#       aus NICHT; ohne die Einstellung zerlegt es den Inhalt als Markup,
#       und ein offenes Tag darin verschluckt alles Folgende.
#
#       DAMIT ENTFAELLT DER FRUEHERE EINGRIFF AM <noscript> - die
#       Zeichenkette wird an dieser Stelle nicht mehr angefasst. Ein Eingriff
#       weniger ist ein Eingriff weniger.
#
#   (2) <template> wird geleert
#       HTML5 legt den Inhalt eines <template> in ein eigenes
#       DocumentFragment ('content'). Ueber 'element.children' ist er nicht
#       erreichbar, ein XPath aus dem Browser zaehlt ihn folglich NIE mit.
#       html5lib haengt ihn als gewoehnliche Kinder ein. Das ist der einzige
#       gemessene Unterschied, der bleibt - und er wird hier ausgeraeumt.
#
#       DAS ELEMENT SELBST BLEIBT STEHEN. Es zaehlt im Browser als Element
#       mit; nur seine Kinder gibt es dort nicht. Wer es entfernte,
#       verschoebe die Zaehlung um eins und erzeugte denselben Fehler in der
#       Gegenrichtung.
#
# ── WAS DIESE DATEI NICHT TUT ────────────────────────────────────────────────
#
#   SIE HAT KEINEN RUECKFALL AUF lxml. Ein Werkzeug, das je nach
#   Installationslage anders zerlegt, liefert Ergebnisse, die nicht
#   vergleichbar sind - und in einem Beweismittelverfahren ist ein still
#   abweichendes Verfahren schlimmer als ein Abbruch. Fehlt html5lib, sagt
#   der Aufrufer das im Klartext und arbeitet NICHT weiter.
#
#   DER ABZUG BLEIBT UNBERUEHRT. Hier wird eine Zeichenkette gelesen und ein
#   Baum gebaut; forensic_<uid>.db wird nur gelesen. Was am Text getan wurde
#   (die <template>-Leerung), steht in den Befunden und gehoert in den
#   Vermerk - ein stiller Eingriff waere genau das, was Grundregel 1
#   verbietet.
#
# Version: 0.8.747 - Build 747
# =============================================================================

from __future__ import annotations

import re
from typing import Any, List, Tuple

#: <template>: Inhalt gehoert im Browser NICHT in den Baum.
#: <noscript> steht hier bewusst NICHT mehr - darum kuemmert sich seit
#: Build 747 das scripting-Flag, und zwar an der richtigen Stelle: im
#: Zerleger statt in der Zeichenkette.
_TEMPLATE_MUSTER = re.compile(r"(<template\b[^>]*>)(.*?)(</template\s*>)",
                              re.IGNORECASE | re.DOTALL)

#: Rohtext-Elemente, ueber die M3 der Diagnose berichtet. Beide sind seit
#: Build 747 behandelt - die Angabe bleibt, weil ihr Vorhandensein fuer die
#: Beurteilung eines Abzugs von Belang ist.
ROHTEXT_ELEMENTE = ("noscript", "template")

_ROHTEXT_MUSTER = re.compile(
    r"(<(%s)\b[^>]*>)(.*?)(</\2\s*>)" % "|".join(ROHTEXT_ELEMENTE),
    re.IGNORECASE | re.DOTALL)


class Html5FehltError(RuntimeError):
    """
    html5lib ist nicht installiert.

    EIGENE KLASSE, damit der Aufrufer diesen Fall von einem Fehler IM Abzug
    unterscheiden kann. Das eine ist ein Anlagenproblem und in einer Minute
    behoben, das andere ein Befund ueber das Beweismittel - sie in einer
    Meldung zusammenzuziehen hiesse, den leichten Fall wie den schweren
    aussehen zu lassen und umgekehrt.
    """


class Html5Zerleger:
    """
    Den <body>-Auszug eines Seitenabzugs nach HTML5 zerlegen.

    Verwendung:

        wurzel, befunde = Html5Zerleger().zerlege(body_html)

    'wurzel' ist ein <div>, dessen Kinder die Kinder des <body> sind - es
    bildet '#forensic-viewport' nach, gegen den toolbar.js den Anker
    gerechnet hat. Ohne diesen Behaelter waere der Bezugspunkt bei mehreren
    Wurzelelementen mehrdeutig.
    """

    #: Der Behaeltername. 'div' ist kein beliebiger Wert: html5lib waehlt
    #: seinen Einstiegszustand nach dem Behaelter, und '#forensic-viewport'
    #: IST ein <div>. Ein <body> als Behaelter waere ein anderer Zustand und
    #: damit eine andere Messung.
    BEHAELTER = "div"

    def __init__(self, *, scripting: bool = True) -> None:
        #: NUR fuer die Gegenprobe umstellbar. Im Betrieb ist das Flag
        #: gesetzt, weil das Ermittlungsfenster JavaScript ausfuehrt.
        self._scripting = bool(scripting)

    # ------------------------------------------------------------------
    @staticmethod
    def verfuegbar() -> bool:
        """Ist html5lib da? Fuer eine Auskunft, nicht fuer einen Rueckfall."""
        try:
            import html5lib  # noqa: F401
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    @staticmethod
    def fassung() -> str:
        """Die Version von html5lib - gehoert in den Herkunftsnachweis."""
        try:
            import html5lib
            return str(getattr(html5lib, "__version__", "unbekannt"))
        except ImportError:
            return "nicht installiert"

    # ------------------------------------------------------------------
    def leere_template(self, html: str) -> Tuple[str, List[str]]:
        """
        Den Inhalt von <template> leeren. Das Element bleibt stehen.

        Rueckgabe: (bearbeiteter Text, Befunde im Klartext).
        """
        anzahl = [0]

        def _ersetze(m: "re.Match") -> str:
            if not m.group(2).strip():
                # Nichts drin, nichts zu tun. Ein Eingriff ohne Wirkung soll
                # auch nicht als Eingriff gemeldet werden.
                return m.group(0)
            anzahl[0] += 1
            return m.group(1) + m.group(3)

        neu = _TEMPLATE_MUSTER.sub(_ersetze, html)
        if not anzahl[0]:
            return neu, []
        return neu, [
            "%d <template> mit Inhalt - dieser wurde fuer die Zerlegung "
            "geleert, weil der Browser ihn nicht in den Baum stellt "
            "(HTML5 legt ihn in ein eigenes DocumentFragment). Das Element "
            "selbst bleibt stehen, denn es zaehlt im Browser mit."
            % anzahl[0]]

    # ------------------------------------------------------------------
    def zerlege(self, body_html: str) -> Tuple[Any, List[str]]:
        """
        (Wurzel-<div>, Befunde). Wirft Html5FehltError, wenn html5lib fehlt.
        """
        try:
            from html5lib.html5parser import HTMLParser
            from html5lib.treebuilders import getTreeBuilder
        except ImportError as exc:
            raise Html5FehltError(
                "html5lib ist nicht installiert (%s). Es gibt KEINEN "
                "Rueckfall auf einen anderen Zerleger: ein Werkzeug, das je "
                "nach Installationslage anders zerlegt, liefert Ergebnisse, "
                "die nicht vergleichbar sind. Abhilfe: "
                "'python -m pip install html5lib'." % exc) from exc

        from lxml import etree

        text, befunde = self.leere_template(str(body_html or ""))

        zerleger = HTMLParser(tree=getTreeBuilder("lxml"),
                              namespaceHTMLElements=False)
        teile = zerleger.parseFragment(text, container=self.BEHAELTER,
                                       scripting=self._scripting)

        # -- Den Behaelter bauen ------------------------------------------
        #
        # parseFragment liefert eine LISTE: Elemente als lxml-Knoten,
        # fuehrender Text als Zeichenkette. Nachfolgender Text steht bereits
        # als 'tail' am jeweiligen Element. Diese drei Faelle muessen
        # getrennt behandelt werden, sonst geht Text verloren - und ein
        # verlorener Textknoten verschiebt die Zaehlung von 'text()[n]',
        # also genau die letzte Stufe eines Ankers.
        wurzel = etree.Element(self.BEHAELTER)
        for stueck in teile:
            if isinstance(stueck, str):
                if len(wurzel):
                    letztes = wurzel[-1]
                    letztes.tail = (letztes.tail or "") + stueck
                else:
                    wurzel.text = (wurzel.text or "") + stueck
            else:
                wurzel.append(stueck)
        return wurzel, befunde


def rohtext_stellen(html: str) -> List[Tuple[int, str, bool]]:
    """
    Wo im Abzug stehen <noscript> und <template>, und ist ihr Inhalt
    ausgeglichen? Rueckgabe je Fund: (Zeichenversatz, Tagname, ausgeglichen).

    SEIT BUILD 747 IST DAS EINE AUSKUNFT UND KEINE WARNUNG MEHR: beide Faelle
    sind behandelt (scripting-Flag bzw. Leerung). Die Angabe bleibt, weil das
    Vorhandensein solcher Elemente fuer die Beurteilung eines Abzugs von
    Belang ist - wer eine Auffaelligkeit sucht, will wissen, ob es sie gibt.
    """
    heraus: List[Tuple[int, str, bool]] = []
    for m in _ROHTEXT_MUSTER.finditer(str(html or "")):
        inhalt = m.group(3)
        auf = len(re.findall(r"<(?!/)(?!!)[A-Za-z]", inhalt))
        zu = len(re.findall(r"</[A-Za-z]", inhalt))
        # Leere Elemente (<br>, <img>, ...) zaehlen als oeffnend, haben aber
        # kein schliessendes. Ohne den Abzug gaelte jeder heile Inhalt mit
        # einem <br> als unausgeglichen.
        leere = len(re.findall(
            r"<(br|img|input|hr|meta|link|source|area|base|col|embed|param|"
            r"track|wbr)\b", inhalt, re.IGNORECASE))
        heraus.append((m.start(), m.group(2).lower(), (auf - leere) == zu))
    return heraus

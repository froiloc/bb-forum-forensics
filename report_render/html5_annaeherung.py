# =============================================================================
# report_render/html5_annaeherung.py
# IT-Forensisches Ermittlungswerkzeug - Annaeherung an die Browser-Zerlegung
# =============================================================================
# Zweck:
#   DEN SEITENABZUG SO VORBEREITEN, DASS libxml2 IHN WIE EIN BROWSER ZERLEGT -
#   soweit das ohne Browser geht, und mit einer klaren Aussage darueber, wo
#   die Annaeherung endet.
#
# ── DAS PROBLEM, UND WARUM ES KEIN DATENFEHLER IST ───────────────────────────
#
#   Der Anker einer Textmarkierung wird IM BROWSER gerechnet (toolbar.js,
#   '_xpathOf'), aufgeloest wird er SERVERSEITIG mit libxml2
#   (report_render/absatz_finder.py). Beide muessen denselben Baum sehen,
#   sonst zeigt ein richtiger Anker ins Leere.
#
#   Sie sehen ihn NICHT immer. libxml2 folgt nicht dem HTML5-Baumaufbau, und
#   an zwei Stellen ist der Unterschied nicht kosmetisch, sondern verschiebt
#   ganze Zweige:
#
#   (1) <noscript> — BEI EINGESCHALTETEM JAVASCRIPT IST SEIN INHALT TEXT.
#       Ein Browser mit aktivem JavaScript liest alles zwischen <noscript>
#       und </noscript> als ROHTEXT; kein einziges Tag darin wird zu einem
#       Element. libxml2 kennt diese Regel nicht und zerlegt den Inhalt als
#       Markup. Steht darin ein nicht geschlossenes Tag, verschluckt es
#       ALLES, was nach dem </noscript> folgt - im Browser dagegen nichts.
#
#   (2) <template> — SEIN INHALT GEHOERT NICHT IN DEN BAUM. HTML5 legt ihn
#       in ein eigenes DocumentFragment ('content'); ueber
#       'element.children' ist er nicht erreichbar, und ein XPath aus dem
#       Browser zaehlt ihn folglich nie mit. libxml2 haengt ihn als
#       gewoehnliche Kinder ein.
#
#   (3) AUSSTEHENDE ENDTAGS — DAS IST DER FALL, DER ALEX' ANKER BRICHT.
#       Trifft ein Endtag auf ein Element, das offen ist, aber nicht obenauf
#       liegt, schliesst HTML5 die darueberliegenden Elemente mit
#       ("pop until X popped"). libxml2 meldet die Abweichung und LAESST SIE
#       OFFEN - alles Folgende landet darin. Belegt am echten Bestand
#       (Diagnoselauf 30.08.2026): '#page-body' stand im Abzug INNERHALB von
#       '#page-header'. Nachgestellt mit genau den beiden gemeldeten
#       Fehlern aus einem <li>, in dem ein <div> offen blieb.
#       s. schliesse_offene() weiter unten.
#
#   BEIDES IST GEMESSEN, nicht angenommen. Am 30.08.2026 wurden zehn
#   Konstrukte gegen Chromium gehalten (Playwright, 'innerHTML' auf einen
#   <div> - also genau der Weg, den das Ermittlungsfenster geht) und gegen
#   libxml2. Ergebnis:
#
#     Konstrukt                      Browser   libxml2   nach Annaeherung
#     -------------------------------------------------------------------
#     <noscript> mit offenem <div>       6         2            6
#     <template> mit offenem <div>       6         2            6
#     acht weitere (Kommentar offen,
#     <div> offen, <script> mit "<div>",
#     <td> offen, <noscript> heil, ...)  =         =            =
#
#   Die Zahl ist die der Kinder unter 'div#wrap'. DIE BEIDEN FAELLE ERGEBEN
#   GENAU DAS BILD, DAS ALEX' LAEUFE ZEIGEN: der Browser sieht dort fuenf
#   <div>, der zerlegte Abzug nur zwei.
#
#   DAMIT IST NOCH NICHT GESAGT, DASS ES IM VORLIEGENDEN ABZUG DARAN LIEGT.
#   Bewiesen ist: diese Konstrukte KOENNEN das Bild erzeugen, und die
#   Annaeherung raeumt es aus. Ob sie im Abzug vorkommen, sagt
#   tools/anker_diagnose.py in einem lesenden Lauf.
#
# ── WAS DIE ANNAEHERUNG TUT ──────────────────────────────────────────────────
#
#   Sie LEERT den Inhalt von <noscript> und <template>. Das Element selbst
#   BLEIBT stehen - es zaehlt im Browser als Element mit; nur seine Kinder
#   gibt es dort nicht. Wer es entfernte, verschoebe die Zaehlung um eins und
#   erzeugte damit denselben Fehler in der Gegenrichtung.
#
#   Ersetzt wird durch NICHTS, nicht durch Fuelltext: der Inhalt ist fuer die
#   Auswertung ohne Belang (im Browser steht dort kein Beitragstext), und
#   Fuelltext koennte in einer Wortlautsuche zufaellig treffen.
#
# ── WO DIE ANNAEHERUNG ENDET, UND DAS GEHOERT GESAGT ─────────────────────────
#
#   Sie ist eine ANNAEHERUNG und kein HTML5-Zerleger. In derselben Messung
#   blieb ein Fall abweichend: ein nicht geschlossenes <a> im Seitenkopf.
#   Der Browser wendet darauf die 'adoption agency'-Regel an und zieht das
#   <a> als Geschwister heraus (drei Kinder), libxml2 nicht (sechs Kinder).
#   Dieser Fall erzeugt MEHR Elemente im Abzug als im Browser und damit ein
#   ANDERES Fehlerbild als das beobachtete - er ist bekannt und ungeloest.
#
#   Ein echter HTML5-Zerleger (html5lib) waere der saubere Weg. Er ist auf
#   der Anlage nicht vorhanden und steht nicht in requirements.txt; ihn
#   nachzuruesten ist eine Entscheidung ueber die Abhaengigkeiten des
#   Systems und keine, die nebenbei in einer Fehlersuche faellt.
#
# Version: 0.8.742 - Build 742
# =============================================================================

from __future__ import annotations

import re
from typing import Dict, List, Tuple

#: Elemente, deren Inhalt im Browser NICHT als Markup im Baum landet.
#:
#: <noscript> nur bei eingeschaltetem JavaScript - und das Ermittlungsfenster
#: IST eine JavaScript-Anwendung (die Toolbar). Fuer es gilt die Regel also
#: immer.
#:
#: <script> und <style> stehen bewusst NICHT hier: ihr Inhalt ist in BEIDEN
#: Verfahren Rohtext, sie brauchen keine Annaeherung. Sie hier
#: mitzunehmen hiesse, an einer Stelle einzugreifen, an der nichts kaputt
#: ist - und jeder Eingriff kann etwas kaputt machen.
ROHTEXT_ELEMENTE = ("noscript", "template")

_ROHTEXT_MUSTER = re.compile(
    r"(<(%s)\b[^>]*>)(.*?)(</\2\s*>)" % "|".join(ROHTEXT_ELEMENTE),
    re.IGNORECASE | re.DOTALL)

#: Ein oeffnendes Rohtext-Element ohne zugehoeriges schliessendes wird NICHT
#: angefasst - s. annaehern(). Dieses Muster dient nur der Meldung.
_OFFENES_MUSTER = re.compile(
    r"<(%s)\b[^>]*>" % "|".join(ROHTEXT_ELEMENTE), re.IGNORECASE)


def annaehern(html: str) -> Tuple[str, List[str]]:
    """
    Den Abzug an die Browser-Zerlegung annaehern.

    Rueckgabe: (bearbeiteter Text, Liste der Befunde im Klartext).

    DIE BEFUNDLISTE IST KEIN BEIWERK. Sie sagt, WAS geaendert wurde und wie
    viel - ohne sie waere die Annaeherung ein stiller Eingriff in die
    Beweismittelauswertung, und ein stiller Eingriff ist genau das, was
    Grundregel 1 verbietet. Der Aufrufer traegt sie in den Vermerk.

    DER ABZUG SELBST WIRD NICHT VERAENDERT. Diese Funktion bekommt eine
    Zeichenkette und gibt eine zurueck; sie schreibt nichts. Der gesicherte
    Seitenabzug in forensic_<uid>.db bleibt unberuehrt - was hier geschieht,
    ist eine Lesehilfe und keine Bearbeitung.
    """
    text = str(html or "")
    if not text:
        return text, []

    befunde: List[str] = []
    zaehler = {"noscript": 0, "template": 0}
    geleert = {"noscript": 0, "template": 0}

    for treffer in _OFFENES_MUSTER.finditer(text):
        zaehler[treffer.group(1).lower()] += 1

    def _ersetze(m: "re.Match") -> str:
        marke = m.group(2).lower()
        inhalt = m.group(3)
        if not inhalt.strip():
            # Nichts drin, nichts zu tun. Ein Eingriff ohne Wirkung soll auch
            # nicht als Eingriff gemeldet werden.
            return m.group(0)
        geleert[marke] += 1
        return m.group(1) + m.group(4)

    neu = _ROHTEXT_MUSTER.sub(_ersetze, text)

    # ZWEITER SCHRITT (Build 742): ausstehende Endtags nachziehen. Er steht
    # NACH dem Leeren der Rohtext-Elemente, und die Reihenfolge ist nicht
    # beliebig: was in einem <noscript> steht, ist im Browser Text und darf
    # den Stapel offener Elemente gar nicht erst erreichen. Zuerst leeren,
    # dann zaehlen.
    neu, nachgezogen = schliesse_offene(neu)

    # DREI ZAHLEN, NICHT ZWEI. 'geschlossen und geleert', 'geschlossen und
    # schon leer' und 'ohne schliessendes Gegenstueck' sind drei verschiedene
    # Lagen, und nur die erste ist ein Eingriff. Sie in einer Zahl
    # zusammenzuziehen hiesse, den Eingriff und das Nichtstun ununterscheidbar
    # zu melden.
    for marke in ROHTEXT_ELEMENTE:
        gesamt = zaehler.get(marke, 0)
        if not gesamt:
            continue
        bearbeitet = geleert.get(marke, 0)
        schon_leer = _ohne_inhalt(text, marke)
        ohne_ende = gesamt - bearbeitet - schon_leer
        teile = ["%d <%s> im Abzug" % (gesamt, marke)]
        if bearbeitet:
            teile.append("%d mit Inhalt - dieser wurde fuer die Zerlegung "
                         "geleert, weil der Browser ihn nicht in den Baum "
                         "stellt" % bearbeitet)
        if schon_leer:
            teile.append("%d schon leer - nichts zu tun" % schon_leer)
        if ohne_ende > 0:
            teile.append(
                "%d OHNE schliessendes Gegenstueck - diese werden NICHT "
                "angefasst: wo ein solches Element endet, ist nicht zu "
                "entscheiden, und eine geratene Grenze waere schlimmer als "
                "keine. Bleibt der Anker in diesem Lauf gebrochen, ist HIER "
                "nachzusehen" % ohne_ende)
        befunde.append("; ".join(teile) + ".")

    befunde.extend(nachgezogen)
    return neu, befunde


def _ohne_inhalt(text: str, marke: str) -> int:
    """Wie viele <marke>…</marke> haben leeren Inhalt? Nur fuer die Meldung."""
    muster = re.compile(r"<%s\b[^>]*>(.*?)</%s\s*>" % (marke, marke),
                        re.IGNORECASE | re.DOTALL)
    return sum(1 for m in muster.finditer(text) if not m.group(1).strip())


def rohtext_stellen(html: str) -> List[Tuple[int, str, bool]]:
    """
    Wo im Abzug stehen Rohtext-Elemente, und ist ihr Inhalt ausgeglichen?

    Rueckgabe je Fund: (Zeichenversatz, Tagname, Inhalt ausgeglichen?).

    'ausgeglichen' heisst: gleich viele oeffnende wie schliessende Tags im
    Inhalt. NUR ein UNausgeglichener Inhalt kann die Zerlegung sprengen -
    ein heiles <noscript> ist harmlos, und das zu unterscheiden erspart eine
    Fehlspur.
    """
    heraus: List[Tuple[int, str, bool]] = []
    for m in _ROHTEXT_MUSTER.finditer(str(html or "")):
        inhalt = m.group(3)
        auf = len(re.findall(r"<(?!/)(?!!)[A-Za-z]", inhalt))
        zu = len(re.findall(r"</[A-Za-z]", inhalt))
        # Leere Elemente (<br>, <img>, <input>) zaehlen als oeffnend, haben
        # aber kein schliessendes. Sie werden abgezogen, sonst gaelte jeder
        # heile Inhalt mit einem <br> als unausgeglichen.
        leere = len(re.findall(
            r"<(br|img|input|hr|meta|link|source|area|base|col|embed|param|"
            r"track|wbr)\b", inhalt, re.IGNORECASE))
        heraus.append((m.start(), m.group(2).lower(), (auf - leere) == zu))
    return heraus


# =============================================================================
# Zweite Annaeherung: ausstehende Endtags nachziehen (Build 742)
# =============================================================================
#
# DAS PROBLEM, BEWIESEN UND NACHGESTELLT
#
#   Alex' Diagnoselauf vom 30.08.2026 (Build 741) zeigt am echten Bestand:
#   '#page-body' steht im zerlegten Abzug INNERHALB von '#page-header', und
#   '#page-footer' noch eine Ebene tiefer. Das Fehlerprotokoll nennt:
#
#     ERR_TAG_NAME_MISMATCH: Opening and ending tag mismatch: li and div
#     ERR_TAG_NAME_MISMATCH: Opening and ending tag mismatch: ul and div
#
#   NACHGESTELLT am 30.08.2026 mit genau diesen beiden Meldungen, in dieser
#   Reihenfolge, aus einem einzigen Konstrukt:
#
#     <div id="page-header"><ul><li><div class="a">x</li></ul></div>
#
#   Ein <div> bleibt innerhalb eines <li> offen. Dann kommt das '</li>'.
#
#   WAS DER BROWSER TUT: HTML5 sagt fuer ein Endtag, dessen Element zwar auf
#   dem Stapel steht, aber nicht obenauf liegt: die darueberliegenden
#   Elemente werden GESCHLOSSEN und mitgeschoben ("pop until X popped").
#   Das offene <div> wird also beendet, und alles Folgende steht wieder auf
#   der richtigen Ebene.
#
#   WAS libxml2 TUT: es meldet die Abweichung - und laesst das <div> offen.
#   Alles Folgende landet darin, jedes weitere Geschwister eine Ebene tiefer.
#   Das ist die Kaskade, die Alex' Anker seit Wochen bricht.
#
#   GEMESSEN gegen Chromium (Playwright, innerHTML auf einen <div> - der Weg
#   des Ermittlungsfensters) am 30.08.2026, fuenf Konstrukte:
#
#     Konstrukt                              Browser   libxml2   nach Fix
#     ---------------------------------------------------------------------
#     <li> mit offenem <div>                 direkt      tief      direkt
#     <li> mit zwei offenen <div>            direkt      tief      direkt
#     <dd> mit offenem <div>                 direkt      tief      direkt
#     <td> mit offenem <div>                 direkt      tief      direkt
#     heil (nichts offen)                    direkt      direkt    direkt
#
#   'direkt' heisst: '#page-body' ist unmittelbares Kind von '#wrap' - so,
#   wie der Anker es verlangt.
#
# WAS DIESE FUNKTION TUT UND WAS NICHT
#
#   SIE FUEGT NUR ENDTAGS EIN. Sie entfernt nichts, sie ordnet nichts um,
#   sie beruehrt keinen Text und kein Attribut. Trifft ein Endtag auf ein
#   Element, das zwar offen ist, aber nicht obenauf liegt, werden die
#   darueberliegenden Endtags DAVOR eingesetzt - genau das, was HTML5
#   vorschreibt und libxml2 auslaesst.
#
#   SIE IST KEIN HTML5-ZERLEGER. Sie bildet EINE Regel nach, nicht den
#   ganzen Baumaufbau. Die bekannten Grenzen stehen weiter unten bei
#   BEKANNTE GRENZEN - sie gehoeren gelesen, bevor jemand sich auf diese
#   Funktion mehr verlaesst, als sie traegt.
#
#   DER ABZUG BLEIBT UNBERUEHRT. Hier wird eine Zeichenkette bearbeitet;
#   forensic_<uid>.db wird nur gelesen. Was getan wurde, steht in der
#   Befundliste und gehoert in den Vermerk.
# =============================================================================

#: Elemente ohne Inhalt - sie kommen nie auf den Stapel.
LEERE_ELEMENTE = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})

#: Elemente, deren Inhalt Rohtext ist. Ihr Inneres wird beim Zaehlen
#: uebersprungen - dort steht kein Markup, auch wenn es so aussieht.
#: <noscript> und <template> stehen hier NICHT: um die kuemmert sich
#: annaehern() bereits, und doppelt behandeln waere doppelt riskant.
ROHTEXT_INHALT = frozenset({"script", "style", "textarea", "title"})

#: Welches Element wird durch den Beginn welches Elements implizit beendet?
#: NUR die Faelle, die BEIDE Zerleger ohnehin gleich behandeln - hier steht
#: kein Eingriff, sondern die Nachbildung, damit der Stapel dieser Funktion
#: dasselbe sieht wie libxml2. Waere er anders, saetzte sie Endtags an
#: Stellen ein, an denen libxml2 gar kein offenes Element hat.
IMPLIZIT_BEENDET = {
    "li": {"li"},
    "dd": {"dd", "dt"},
    "dt": {"dd", "dt"},
    "option": {"option"},
    "tr": {"tr", "td", "th"},
    "td": {"td", "th"},
    "th": {"td", "th"},
    "thead": {"tbody", "tfoot", "thead", "tr", "td", "th"},
    "tbody": {"tbody", "tfoot", "thead", "tr", "td", "th"},
    "tfoot": {"tbody", "tfoot", "thead", "tr", "td", "th"},
}

_TOKEN = re.compile(
    r"<!--.*?-->"                                  # Kommentar
    r"|<![^>]*>"                                   # Doctype und Verwandte
    r"|</\s*([A-Za-z][^\s>/]*)\s*>"                # Endtag        -> Gruppe 1
    r"|<\s*([A-Za-z][^\s>/]*)"                     # Starttag      -> Gruppe 2
    r"((?:\"[^\"]*\"|'[^']*'|[^>\"'])*?)(/?)\s*>",  # Attribute, Schraegstrich
    re.DOTALL)

#: Obergrenze fuer den Stapel. Eine Seite mit 500 Beitraegen hat viele
#: Ebenen, aber keine tausend; laeuft der Stapel darueber, stimmt etwas
#: anderes nicht, und dann wird lieber NICHTS getan als etwas Falsches.
STAPEL_GRENZE = 500


def schliesse_offene(html: str) -> Tuple[str, List[str]]:
    """
    Ausstehende Endtags nachziehen - die Regel, die libxml2 auslaesst.

    Rueckgabe: (bearbeiteter Text, Liste der Befunde im Klartext).

    Trifft ein Endtag auf ein Element, das offen ist, aber nicht obenauf
    liegt, werden die Endtags der darueberliegenden Elemente DAVOR
    eingesetzt. Nichts wird entfernt, nichts umgestellt.
    """
    text = str(html or "")
    if not text:
        return text, []

    heraus: List[str] = []
    stapel: List[str] = []
    befunde: List[str] = []
    eingesetzt: Dict[str, int] = {}
    stelle = 0
    laenge = len(text)

    while stelle < laenge:
        treffer = _TOKEN.search(text, stelle)
        if treffer is None:
            heraus.append(text[stelle:])
            break
        heraus.append(text[stelle:treffer.start()])
        marke_zu = treffer.group(1)
        marke_auf = treffer.group(2)
        stelle = treffer.end()

        if marke_zu:
            name = marke_zu.lower()
            if name in stapel:
                # HTML5: alles ueber dem Element schliessen, dann es selbst.
                # GENAU DAS laesst libxml2 aus - und genau daran bricht der
                # Anker.
                while stapel and stapel[-1] != name:
                    offen = stapel.pop()
                    heraus.append("</%s>" % offen)
                    eingesetzt[offen] = eingesetzt.get(offen, 0) + 1
                if stapel:
                    stapel.pop()
            # Steht das Element gar nicht offen, bleibt das Endtag stehen -
            # es zu entfernen waere ein Eingriff ohne Not.
            heraus.append(treffer.group(0))
            continue

        if marke_auf:
            name = marke_auf.lower()
            heraus.append(treffer.group(0))
            if name in LEERE_ELEMENTE or treffer.group(4) == "/":
                continue
            if name in ROHTEXT_INHALT:
                # Inhalt ueberspringen: dort steht kein Markup, auch wenn es
                # danach aussieht. Ein '</div>' in einer Zeichenkette im
                # Skript darf den Stapel nicht anfassen.
                ende = re.search(r"</\s*%s\s*>" % re.escape(name),
                                 text[stelle:], re.IGNORECASE)
                if ende:
                    heraus.append(text[stelle:stelle + ende.end()])
                    stelle += ende.end()
                continue
            # Implizite Beendigung nachbilden, damit der Stapel dasselbe
            # sieht wie libxml2.
            beendet = IMPLIZIT_BEENDET.get(name)
            if beendet and stapel and stapel[-1] in beendet:
                stapel.pop()
            if len(stapel) >= STAPEL_GRENZE:
                befunde.append(
                    "Der Stapel offener Elemente hat %d erreicht - die "
                    "Nachbildung bricht ab und laesst den Rest UNVERAENDERT. "
                    "Lieber nichts tun als etwas Falsches."
                    % STAPEL_GRENZE)
                heraus.append(text[stelle:])
                return "".join(heraus), befunde
            stapel.append(name)
            continue

        heraus.append(treffer.group(0))

    if eingesetzt:
        teile = ", ".join("%d x </%s>" % (n, m)
                          for m, n in sorted(eingesetzt.items()))
        befunde.append(
            "Ausstehende Endtags nachgezogen (%s). Der Browser schliesst "
            "diese Elemente von selbst, der serverseitige Zerleger nicht - "
            "ohne den Nachzug landet alles Folgende INNERHALB des offen "
            "gebliebenen Elements." % teile)
    return "".join(heraus), befunde

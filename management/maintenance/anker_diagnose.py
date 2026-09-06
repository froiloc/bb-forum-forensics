# =============================================================================
# management/maintenance/anker_diagnose.py
# IT-Forensisches Ermittlungswerkzeug - Diagnose des Ankerbruchs
# =============================================================================
# Zweck:
#   HERAUSFINDEN, WARUM DIE ANKER IM SEITENABZUG NICHT AUFLOESEN - durch
#   MESSUNG, nicht durch Vermutung.
#
#   Die Klasse ist der ganze Vorgang; tools/anker_diagnose.py ist nur die
#   Befehlszeile davor (Grundregel 10).
#
#   REIN LESEND. Sie oeffnet beide Datenbanken mit 'mode=ro' und kennt kein
#   UPDATE, kein INSERT und kein '--ausfuehren'. Wartungsstufe C.
#
# ── DER BEFUND, DER ZU DIESER DATEI GEFUEHRT HAT ─────────────────────────────
#
#   tools/postid_nachtragen.py loeste in Alex' Laeufen vom 28.08.2026 KEINEN
#   EINZIGEN Beleg ueber den Anker auf - alle 25 gingen ueber den Wortlaut,
#   den Notfall-Rueckfall. Alex' Urteil dazu: "Das ist inakzeptabel."
#
#   Zwei Dinge sind seither GEMESSEN und stehen fest:
#
#   (1) DIE ANKER SIND RICHTIG. Die Sonde (LAUF D, 29.08.2026) zeigt im
#       Browser unter 'donate > div#wrap' fuenf <div>, und als XPath gezaehlt
#       ist 'div[4]' genau '#page-body' - das, was die Anker verlangen.
#   (2) DER ABZUG HAT AN DERSELBEN STELLE NUR ZWEI <div>. Die Bruchmeldung
#       nennt sie namentlich: 'div#brdleft, div#page-header'.
#
#   ZWEI VERMUTUNGEN SIND DAMIT TOT. Es liegt nicht am <style> im Rumpf: die
#   PN-Seite hat gar keines und bricht identisch. Und es liegt nicht daran,
#   dass zwischen Abzug und Markierung etwas in die Seite geschrieben wurde:
#   dann fehlten die Elemente im Abzug, sie stuenden nicht bloss woanders.
#
#   WAS UEBRIG BLEIBT, IST EINE FRAGE UND KEINE ANTWORT: Stehen die drei
#   fehlenden <div> im Abzug ueberhaupt nicht - oder stehen sie darin, und
#   die ZERLEGUNG legt sie an eine andere Stelle? Das ist der Unterschied
#   zwischen einem Datenschaden und einem Auswertungsfehler, und er ist an
#   einem einzigen Lauf zu entscheiden. Genau dafuer ist diese Datei da.
#
# ── DIE DREI MESSUNGEN ───────────────────────────────────────────────────────
#
#   M1  DER EBENENBERICHT. Fuer jede Stufe des Ankers: was steht dort im
#       zerlegten Abzug? Benannt, nicht nur gezaehlt. Erst am ganzen Weg ist
#       zu sehen, ob der Baum ueberall zu flach ist oder nur an einer Stelle.
#
#   M2  DIE GEGENPROBE MIT DEM HTML5-ZERLEGER. Derselbe Anker, aber der
#       Abzug nach dem HTML5-STANDARD zerlegt (html5lib, s.
#       report_render/html5_zerleger.py) - also mit demselben Algorithmus,
#       den der Browser ausfuehrt, der den Anker erzeugt hat. LOEST DER
#       ANKER DANN AUF, IST DIE FRAGE BEANTWORTET.
#
#       BIS BUILD 746 STAND HIER EIN HANDGEBAUTER TEILNACHBAU der
#       HTML5-Regeln. Er hat ueber fuenf Builds hinweg je ein Konstrukt
#       geheilt und ein anderes zerbrochen; am echten Abzug riss er
#       '#page-body' nach dem zweiten Beitrag auf und liess 498 von 500
#       Beitraegen herausfallen. EINE HALB NACHGEBILDETE REGEL IST
#       GEFAEHRLICHER ALS KEINE.
#
#       DER ERSTE ENTWURF DIESER DATEI STELLTE libxml2 GEGEN html.parser.
#       Das haette nichts beantwortet: die Messung gegen Chromium vom
#       30.08.2026 zeigt, dass html.parser dieselben beiden Regeln ebenso
#       wenig kennt. Beide haetten uebereinstimmend das falsche Ergebnis
#       geliefert - und die Uebereinstimmung waere als Entlastung der
#       Zerlegung gelesen worden. Eine Gegenprobe, die nur bestaetigen kann,
#       ist keine.
#
#   M3  DIE ROHTEXT-ELEMENTE IM ABZUG. Wo stehen <noscript> und <template>?
#       Seit Build 747 ist das eine AUSKUNFT und keine Warnung: beide Faelle
#       sind behandelt (scripting-Flag bzw. Leerung). Die Angabe bleibt, weil
#       ihr Vorhandensein fuer die Beurteilung eines Abzugs von Belang ist.
#
# ── ZUR WEITERGABE DER AUSGABE ───────────────────────────────────────────────
#
#   Ausgegeben werden Geruestangaben: Tag, Kennung, Klasse, Zahlen, Pfade.
#   KEINE Beitragsinhalte. Wo ein Quelltextstueck gezeigt wird, sind die
#   Textknoten verdeckt (Buchstaben -> 'x', Ziffern -> '9') und die
#   Attributwerte bis auf eine schmale Liste ebenfalls - 'id', 'class',
#   'style', 'role', 'type' und 'name' bleiben offen, weil sie der
#   Messgegenstand sind; 'href', 'src', 'title' und 'alt' nicht, weil dort
#   Benutzernamen stehen koennen.
#
#   DIESE ZUSAGE HAT SCHON EINMAL NICHT GEHALTEN: die Sonde gab am 29.08.2026
#   in einem Feld einen Klarnamen aus, weil ich ein Verfahren fuer harmlos
#   hielt, das mehr las als den Zeitstempel. Deshalb ist die Verdeckung hier
#   nicht 'wo noetig', sondern die Vorgabe - offen ist nur, was namentlich
#   freigegeben ist.
#
# Version: 0.8.747 - Build 747 (HTML5-Zerleger; M8 gestrichen)
# =============================================================================

from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# BUILD 763 - der post-Bezug steht in einem eigenen Modul (Grundregel 10).
from management.maintenance.anker_postbezug import (
    FALL_TEXT, KLASSE_SONSTIGE, POSTFREIE_KLASSEN, PostBezugMesser,
    fall_bestimmen, seitenklasse)

logger = logging.getLogger(__name__)


#: Ein XPath-Schritt, wie toolbar.js ihn schreibt: 'div[4]' oder 'text()[1]'.
#: Dasselbe Muster wie in report_render/absatz_finder.py - bewusst dort UND
#: hier, weil ein gemeinsamer Import den Berichtsgenerator an ein
#: Wartungswerkzeug binden wuerde.
SCHRITT_MUSTER = re.compile(r"^([a-zA-Z_][\w.-]*|text\(\))\[(\d+)\]$")

#: Attribute, deren Wert offen bleiben darf. Alles andere wird verdeckt.
#: 'id' und 'class' sind der Messgegenstand; 'style' entscheidet in der
#: Titelzeile ueber den Moderationslink; 'role', 'type' und 'name' sagen
#: etwas ueber den Aufbau. 'href', 'src', 'title' und 'alt' stehen bewusst
#: NICHT hier - dort koennen Benutzernamen stehen.
OFFENE_ATTRIBUTE = frozenset({"id", "class", "style", "role", "type", "name"})

#: Obergrenze fuer die Quelltextsuche in M3. Ein Seitenkopf hat einige
#: Hundert Tags; ohne Grenze liefe die Messung bei einer Seite mit 500
#: Beitraegen aus dem Ruder.
GRENZE_TAGS = 4000


# =============================================================================
# Verdecken
# =============================================================================
def verdecke_text(s: str) -> str:
    """
    Freitext unkenntlich machen, aber die GESTALT erhalten.

    Buchstaben werden zu 'x', Ziffern zu '9'; Leerraum und Satzzeichen
    bleiben. Damit ist an der Ausgabe noch abzulesen, ob an einer Stelle ein
    Wort, eine Zahl oder nichts stand - und das ist alles, was die Messung
    braucht.
    """
    return "".join(
        "9" if z.isdigit() else ("x" if z.isalpha() else z)
        for z in str(s or "")
    )


def verdecke_tag(tag: str) -> str:
    """
    Ein einzelnes Tag verdecken: Tagname und die freigegebenen Attribute
    bleiben, alle uebrigen Attributwerte werden verdeckt.

    Der Tagname selbst bleibt IMMER offen - er ist der Messgegenstand, und
    ein Tagname traegt keinen Fallbezug.
    """
    roh = str(tag or "")
    if not roh.startswith("<"):
        return verdecke_text(roh)

    def _attribut(t):
        name, gleich, wert = t.group(1), t.group(2), t.group(3)
        if name.lower() in OFFENE_ATTRIBUTE:
            return t.group(0)
        # Anfuehrungszeichen erhalten, Inhalt verdecken.
        if len(wert) >= 2 and wert[0] in "\"'" and wert[-1] == wert[0]:
            return "%s%s%s%s%s" % (name, gleich, wert[0],
                                   verdecke_text(wert[1:-1]), wert[0])
        return "%s%s%s" % (name, gleich, verdecke_text(wert))

    return re.sub(r'([A-Za-z_:][-\w:.]*)(\s*=\s*)("[^"]*"|\'[^\']*\'|[^\s>]+)',
                  _attribut, roh)


def verdecke_tag_folge(zeile: str) -> str:
    """
    Eine ganze Quelltextzeile verdecken: jedes Tag durch verdecke_tag(), alles
    dazwischen (Fliesstext) durch verdecke_text().

    BUILD 741. Ohne diese Funktion muesste man entweder die Zeile im Klartext
    zeigen - und damit die Zusage brechen, dass die Ausgabe weitergebbar ist -
    oder auf die Zeile verzichten und weiter raten.
    """
    heraus, stelle = [], 0
    for m in re.finditer(r"<[^>]*>", str(zeile or "")):
        if m.start() > stelle:
            heraus.append(verdecke_text(zeile[stelle:m.start()]))
        heraus.append(verdecke_tag(m.group(0)))
        stelle = m.end()
    if stelle < len(zeile or ""):
        heraus.append(verdecke_text(zeile[stelle:]))
    return "".join(heraus)


# =============================================================================
# Ein Baum, zwei Zerlegungen - eine gemeinsame Sicht darauf
# =============================================================================
#
# WARUM EIN ADAPTER UND NICHT ZWEIMAL DERSELBE CODE: Die Messung soll die
# BEIDEN Zerlegungen mit DEMSELBEN Verfahren abschreiten. Zwei Fassungen des
# Abschreitens waeren zwei Fehlerquellen, und ein Unterschied im Ergebnis
# waere nicht mehr eindeutig der Zerlegung zuzuschreiben.


class Sicht:
    """Gemeinsame Sicht auf einen zerlegten Abzug. Basisklasse."""

    name = "?"

    def kinder(self, knoten) -> List[Any]:
        raise NotImplementedError

    def marke(self, knoten) -> str:
        raise NotImplementedError

    def kennung(self, knoten) -> str:
        raise NotImplementedError

    def klassen(self, knoten) -> str:
        raise NotImplementedError

    def textknoten(self, knoten) -> int:
        raise NotImplementedError

    @property
    def wurzel(self):
        raise NotImplementedError

    # -- gemeinsam, fuer beide Zerlegungen identisch ------------------------
    def benenne(self, knoten) -> str:
        """'div#page-body.wrap' - Geruest, kein Inhalt."""
        s = self.marke(knoten)
        k = self.kennung(knoten)
        if k:
            s += "#" + k
        kl = self.klassen(knoten)
        if kl:
            s += "." + ".".join(kl.split()[:3])
        return s

    def liste(self, knoten, grenze: int = 12) -> str:
        kinder = self.kinder(knoten)
        namen = [self.benenne(k) for k in kinder[:grenze]]
        if len(kinder) > grenze:
            namen.append("... (%d weitere)" % (len(kinder) - grenze))
        return ", ".join(namen) if namen else "nichts"

    def schritt(self, knoten, marke: str, nummer: int):
        """
        Einen XPath-Schritt gehen - mit DEN REGELN VON toolbar.js.

        Gezaehlt wird unter GLEICHNAMIGEN Geschwistern, 1-basiert. Das ist
        genau die Zaehlung, die '_xpathOf' beim Speichern benutzt hat; jede
        andere ergaebe hier eine Bruchstelle, die es im Browser nicht gab.
        """
        gleiche = [k for k in self.kinder(knoten) if self.marke(k) == marke]
        if 1 <= nummer <= len(gleiche):
            return gleiche[nummer - 1]
        return None

    def pfad_von(self, knoten) -> str:
        """
        Der TATSAECHLICHE XPath eines Knotens - dieselbe Schreibweise, in der
        der Anker gespeichert wurde. Damit sind Soll und Ist unmittelbar
        gegeneinander zu halten.
        """
        teile: List[str] = []
        aktuell = knoten
        while aktuell is not None and aktuell is not self.wurzel:
            eltern = self.eltern(aktuell)
            if eltern is None:
                break
            marke = self.marke(aktuell)
            gleiche = [k for k in self.kinder(eltern) if self.marke(k) == marke]
            try:
                nr = gleiche.index(aktuell) + 1
            except ValueError:                    # pragma: no cover - defensiv
                nr = 1
            teile.append("%s[%d]" % (marke, nr))
            aktuell = eltern
        return "./" + "/".join(reversed(teile)) if teile else "."

    def eltern(self, knoten):
        raise NotImplementedError

    def kette_von(self, knoten) -> str:
        """
        Die Vorfahrenkette als BENANNTE Folge: 'div#wrap > div#page-header >
        div.inbox > div#page-body'.

        BUILD 741. Der Pfad ('div[2]/div[2]') sagt, WO ein Element steht; die
        Kette sagt, WER es aufgenommen hat. Erst damit ist die Stelle im
        Quelltext wiederzufinden - und genau danach wird gesucht, wenn ein
        Element tiefer steht als erwartet.
        """
        teile = self.kette_teile(knoten)
        return " > ".join(teile) if teile else "(Wurzel)"

    def kette_teile(self, knoten) -> List[str]:
        """
        Dieselbe Kette, aber als Liste - von aussen nach innen.

        BUILD 744. Getrennt herausgezogen, weil eine Kette bei einer
        Schachtelungskaskade Hunderte Glieder lang werden kann. Eine solche
        Zeile ist nicht mehr zu lesen; gekuerzt werden darf sie aber nur
        dort, wo auch gesagt wird, WIE VIEL weggelassen wurde (s.
        kette_kurz). Deshalb liefert die Grundform die Teile und nicht den
        fertigen Satz.
        """
        teile: List[str] = []
        aktuell = knoten
        # Die Schranke ist eine Notbremse gegen einen Baum, der sich - aus
        # welchem Grund auch immer - im Kreis dreht. Sie ist bewusst hoch:
        # eine echte Kaskade mit 500 Gliedern soll VOLLSTAENDIG gezaehlt
        # werden, denn ihre Laenge ist hier der Messwert.
        schranke = 5000
        while aktuell is not None and aktuell is not self.wurzel and schranke:
            teile.append(self.benenne(aktuell))
            aktuell = self.eltern(aktuell)
            schranke -= 1
        teile.reverse()
        return teile

    def kette_kurz(self, knoten, kopf: int = 3, fuss: int = 3) -> str:
        """
        Die Kette lesbar gekuerzt - mit benannter Auslassung.

        'div#wrap > div#page-body > ... (494 Glieder) ... > article#p665.post'

        WARUM MIT ZAHL: Eine Auslassung ohne Zahl verschweigt genau die
        Angabe, um die es hier geht. Die Laenge der Kette IST der Befund -
        sie unterscheidet 'steht eine Ebene zu tief' von 'steht in einer
        Kaskade'.
        """
        teile = self.kette_teile(knoten)
        if not teile:
            return "(Wurzel)"
        if len(teile) <= kopf + fuss + 1:
            return " > ".join(teile)
        weg = len(teile) - kopf - fuss
        return "%s > ... (%d Glieder) ... > %s" % (
            " > ".join(teile[:kopf]), weg, " > ".join(teile[-fuss:]))

    def alle_mit_marke(self, marke: str) -> List[Any]:
        """
        Alle Elemente mit diesem Tagnamen - in Dokumentreihenfolge.

        BUILD 744. Fuer die Frage 'die Seite traegt 500 <article>, aber nur
        2 stehen an der verlangten Stelle - wo stehen die anderen 498?'.
        """
        gefunden: List[Any] = []
        stapel = [self.wurzel]
        while stapel:
            k = stapel.pop()
            if self.marke(k) == marke:
                gefunden.append(k)
            stapel.extend(reversed(self.kinder(k)))
        return gefunden

    def groesste_tiefe(self) -> int:
        """
        Die groesste Schachtelungstiefe im ganzen Baum.

        BUILD 744. libxml2 bricht bei 'Excessive depth in document: 256' ab
        und laesst den Rest weg - ein Browser tut das nicht. Steht die Tiefe
        in der Naehe dieser Grenze, ist das kein Nebenbefund, sondern die
        Erklaerung dafuer, dass Teile der Seite im Baum fehlen.
        """
        groesste = 0
        stapel = [(self.wurzel, 0)]
        while stapel:
            k, t = stapel.pop()
            if t > groesste:
                groesste = t
            for kind in self.kinder(k):
                stapel.append((kind, t + 1))
        return groesste

    def mit_kennung(self, kennung: str):
        """Den Knoten mit dieser Kennung suchen. None, wenn es ihn nicht gibt."""
        stapel = [self.wurzel]
        while stapel:
            k = stapel.pop()
            if self.kennung(k) == kennung:
                return k
            stapel.extend(reversed(self.kinder(k)))
        return None

    def alle_kennungen(self) -> List[str]:
        gefunden: List[str] = []
        stapel = [self.wurzel]
        while stapel:
            k = stapel.pop()
            kg = self.kennung(k)
            if kg:
                gefunden.append(kg)
            stapel.extend(reversed(self.kinder(k)))
        return gefunden


class SichtLxml(Sicht):
    """Die Zerlegung des AUSLIEFERUNGSPFADS - libxml2 ueber lxml.html."""

    name = "libxml2 (der Weg des Berichts)"

    def __init__(self, body_html: str) -> None:
        from lxml import html as lxml_html
        # GENAU wie AbsatzFinder.__init__: fragment_fromstring mit
        # create_parent='div'. Eine andere Aufbereitung waere eine andere
        # Messung - und damit keine Aussage ueber den Bericht.
        #
        # BUILD 739: MIT EIGENEM ZERLEGER, UM SEIN FEHLERPROTOKOLL ZU LESEN.
        #
        # DAS IST DIE QUELLE, DIE ICH SECHS BUILDS LANG NICHT ANGESEHEN HABE.
        # libxml2 fuehrt Buch darueber, was ihm beim Zerlegen begegnet ist -
        # und es benennt genau die beiden Mechanismen, die das beobachtete
        # Bild erzeugen koennen:
        #
        #   ERR_TAG_NAME_MISMATCH   ein Element wurde nicht geschlossen; alles
        #                           Folgende landet darin
        #   ERR_RESOURCE_LIMIT      "Excessive depth in document: 256, use
        #                           XML_PARSE_HUGE option" - libxml2 bricht die
        #                           Schachtelung ab und LAESST DEN REST WEG
        #
        # Der zweite Fall ist der interessantere, weil ein BROWSER diese
        # Grenze nicht hat: er wuerde die Seite vollstaendig aufbauen, waehrend
        # der Bericht sie abgeschnitten sieht. Genau so sieht Alex' Befund aus.
        #
        # Beide Faelle sind am 30.08.2026 nachgestellt und erzeugen die
        # gemeldete Kinderzahl 2. Sie sind AM PROTOKOLL zu unterscheiden - und
        # zusaetzlich daran, ob '#page-body' im Baum ueberhaupt noch vorkommt:
        # beim ersten Fall steht es tiefer, beim zweiten fehlt es ganz.
        parser = lxml_html.HTMLParser(recover=True)
        self._wurzel = lxml_html.fragment_fromstring(
            body_html, create_parent="div", parser=parser)
        self.fehlerprotokoll = [str(e) for e in parser.error_log]

    @property
    def wurzel(self):
        return self._wurzel

    def kinder(self, knoten) -> List[Any]:
        return [k for k in knoten if isinstance(getattr(k, "tag", None), str)]

    def marke(self, knoten) -> str:
        return str(knoten.tag)

    def kennung(self, knoten) -> str:
        return str(knoten.get("id") or "")

    def klassen(self, knoten) -> str:
        return str(knoten.get("class") or "")

    def textknoten(self, knoten) -> int:
        return len(knoten.xpath("./text()"))

    def eltern(self, knoten):
        return knoten.getparent()


class SichtHtml5(SichtLxml):
    """
    Die Zerlegung NACH DEM HTML5-STANDARD - derselbe Algorithmus wie im
    Browser (report_render/html5_zerleger.py).

    BUILD 747. Bis Build 746 stand hier 'SichtGenaehert': dieselbe
    libxml2-Zerlegung, aber auf einem Text, den ein handgebauter Teilnachbau
    der HTML5-Regeln vorher zurechtgelegt hatte. Der Nachbau hat ueber fuenf
    Builds hinweg je ein Konstrukt geheilt und ein anderes zerbrochen; am
    echten Abzug riss er '#page-body' nach dem zweiten Beitrag auf.

    UMBENANNT UND NICHT UMGEDEUTET: der alte Name beschrieb ein Verfahren,
    das es nicht mehr gibt. Ein Name, dessen Bedeutung sich aendert, ist der
    zuverlaessigste Weg zu einem Auswertungsfehler.

    WARUM DAS EINE ECHTE GEGENPROBE IST: Der erste Entwurf dieser Datei
    stellte libxml2 gegen html.parser. Das haette nichts beantwortet - beide
    kennen den HTML5-Baumaufbau nicht und haetten uebereinstimmend das
    falsche Ergebnis geliefert; die Uebereinstimmung waere als Entlastung
    gelesen worden. html5lib dagegen fuehrt DENSELBEN Algorithmus aus wie
    der Browser, der den Anker erzeugt hat. Gemessen an 17 Konstrukten gegen
    Chromium (31.08.2026): lxml roh 7, lxml + Teilnachbau 16, html5lib 17.
    """

    name = "html5lib (der Weg des Berichts seit Build 747)"

    def __init__(self, body_html: str) -> None:
        from report_render.html5_zerleger import Html5Zerleger
        # Die Basisklasse baut ihren Baum aus Text; hier ist er schon fertig.
        # Deshalb wird ihr __init__ NICHT aufgerufen und der Baum unmittelbar
        # gesetzt - alles Uebrige (kinder, marke, eltern ...) gilt
        # unveraendert, weil html5lib denselben lxml-Baumtyp liefert.
        self._wurzel, self.befunde = Html5Zerleger().zerlege(body_html)
        #: html5lib fuehrt kein Fehlerprotokoll wie libxml2 - es hat keines
        #: zu fuehren, weil der Standard fuer jeden Eingabefehler ein
        #: definiertes Verhalten vorschreibt. Das Feld bleibt, damit die
        #: Auswertung nicht zwei Faelle unterscheiden muss.
        self.fehlerprotokoll = []


# =============================================================================
# M7 - Wo stehen die Elemente, die der Anker verlangt?
# =============================================================================
#
# BUILD 744. DER BEFUND, DER DAZU GEFUEHRT HAT: Nach dem Fix aus Build 742
# loesten 25 von 27 Ankern auf. Bei den zwei uebrigen sagt die Bruchmeldung:
#
#   "Der Anker verlangt den 29. <article>, im Abzug stehen dort 2.
#    Die ganze Seite traegt 500 <article> (Nummern: 136, 151, 161, 350, ...)."
#
# DIE ELEMENTE SIND ALSO DA. Sie sind nur keine Geschwister an der
# verlangten Stelle. Damit ist 'im Abzug fehlt etwas' ausgeschieden, und es
# bleiben zwei Lagen, die VERSCHIEDENES verlangen:
#
#   (a) SIE STEHEN INEINANDER. Dann hat die Zerlegung eine zweite Kaskade
#       gebaut - eine, die der Fix aus Build 742 nicht abraeumt, weil ihr
#       ein anderes Konstrukt zugrunde liegt. Das waere ein AUSWERTUNGS-
#       fehler und hier zu beheben.
#   (b) SIE STEHEN NEBENEINANDER, NUR WOANDERS. Dann ist der verglichene
#       Abzug ein anderer als der gesehene - andere Seite des Themas, oder
#       spaeter neu gezogen. Das waere ein DATEN-Befund und nicht durch
#       Code zu heilen.
#
# EINE ZAHL UNTERSCHEIDET DIE BEIDEN: wie viele der Elemente stehen
# innerhalb eines gleichnamigen? Bei (a) fast alle, bei (b) keines.
#
# DIE AUSGABE IST WEITERGEBBAR: Tagnamen, Kennungen, Klassen, Zahlen. Kein
# Text, keine Attributwerte ausser den namentlich freigegebenen.


#: Elemente, die IN DIESEM FORUM nachweislich FLACH stehen - eines im
#: anderen kommt in der Seitenvorlage nicht vor. Nur bei ihnen ist eine
#: Schachtelung ein Befund ueber die Zerlegung.
#:
#: WARUM NICHT 'ein <article> gehoert nicht in ein <article>': DAS WAERE
#: FALSCH. HTML5 erlaubt beides ausdruecklich (ein Kommentar in einem
#: Beitrag ist ein <article> in einem <article>). Die Aussage stuetzt sich
#: hier NICHT auf den Standard, sondern auf die Vorlage dieses Forums, in
#: der ein Beitrag ein flaches <article class="post"> ist. Das ist ein
#: fallbezogener Beleg und gehoert als solcher benannt.
#:
#: <div> steht bewusst NICHT hier: ein <div> in einem <div> ist voellig
#: gewoehnlich. Eine Schachtelungszahl zu <div> ist beschreibend und kein
#: Vorwurf - sie so zu lesen waere eine Behauptung ohne Beleg.
FLACHE_ELEMENTE = frozenset({"article"})


def _deutung(marke: str) -> str:
    """Die Auslegung der Schachtelungszahl - nur wo sie belegt ist."""
    if marke in FLACHE_ELEMENTE:
        return (" In der Vorlage dieses Forums steht ein Beitrag als flaches "
                "<article class=\"post\">; eines im anderen kommt dort nicht "
                "vor. Die Schachtelung stammt also aus der Zerlegung.")
    return (" ACHTUNG: bei <%s> ist eine Schachtelung gewoehnlich und fuer "
            "sich KEIN Befund. Die Zahl steht hier zum Vergleich der beiden "
            "Zerlegungen, nicht als Vorwurf." % marke)


def verteilung_zeilen(sicht, marke: str, grenze_ketten: int = 6,
                      grenze_kennungen: int = 10) -> List[str]:
    """
    Die Verteilung aller '<marke>' im Baum EINER Zerlegung, als Textzeilen.

    Gruppiert wird nach der Vorfahrenkette des ELTERN-Knotens: alle
    Elemente, die derselbe Knotenzug aufgenommen hat, stehen in einer
    Gruppe. Die Zahl der Gruppen ist damit unmittelbar die Antwort auf
    'stehen sie beieinander oder verstreut'.
    """
    knoten = sicht.alle_mit_marke(marke)
    if not knoten:
        return ["Kein <%s> in dieser Zerlegung." % marke]

    # -- Gruppieren nach der Kette des Elternknotens ----------------------
    # Ein gewoehnliches dict genuegt: seit Python 3.7 haelt es die
    # Einfuegereihenfolge, und die ist hier die Dokumentreihenfolge - die
    # erste Gruppe ist also die oberste Stelle der Seite.
    gruppen: Dict[str, List[Any]] = {}
    for k in knoten:
        eltern = sicht.eltern(k)
        kette = sicht.kette_kurz(eltern) if eltern is not None else "(Wurzel)"
        gruppen.setdefault(kette, []).append(k)

    # -- Wie viele stehen in einem GLEICHNAMIGEN Element? -----------------
    # DAS IST DIE ENTSCHEIDENDE ZAHL (s. Kopf dieses Abschnitts).
    verschachtelt = 0
    tiefste = 0
    for k in knoten:
        n = 0
        e = sicht.eltern(k)
        schranke = 5000
        while e is not None and schranke:
            if sicht.marke(e) == marke:
                n += 1
            e = sicht.eltern(e)
            schranke -= 1
        if n:
            verschachtelt += 1
        if n > tiefste:
            tiefste = n

    heraus: List[str] = [
        "<%s>: %d im Baum, verteilt auf %d Vorfahrenkette(n)"
        % (marke, len(knoten), len(gruppen))]

    for nr, (kette, elemente) in enumerate(list(gruppen.items())
                                           [:grenze_ketten], start=1):
        namen = []
        for e in elemente[:grenze_kennungen]:
            kg = sicht.kennung(e)
            namen.append("#" + kg if kg else "(ohne id)")
        if len(elemente) > grenze_kennungen:
            namen.append("... (%d weitere)" % (len(elemente)
                                               - grenze_kennungen))
        heraus.append("  [%d] %dx unter %s" % (nr, len(elemente), kette))
        heraus.append("      davon: %s" % ", ".join(namen))
    if len(gruppen) > grenze_ketten:
        heraus.append("  ... (%d weitere Ketten)"
                      % (len(gruppen) - grenze_ketten))

    if verschachtelt:
        heraus.append(
            "  %d von %d stehen INNERHALB eines anderen <%s> - tiefste "
            "Schachtelung: %d.%s"
            % (verschachtelt, len(knoten), marke, tiefste, _deutung(marke)))
    else:
        heraus.append(
            "  KEINES steht innerhalb eines anderen <%s>.%s Die Elemente "
            "stehen nebeneinander, nur nicht an der vom Anker verlangten "
            "Stelle." % (marke, " Eine Kaskade scheidet damit aus."
                         if marke in FLACHE_ELEMENTE else ""))

    tiefe = sicht.groesste_tiefe()
    heraus.append("  groesste Schachtelungstiefe im ganzen Baum: %d%s"
                  % (tiefe,
                     "   <-- NAHE AN DER GRENZE VON libxml2 (256); der "
                     "Zerleger laesst ab dort weg" if tiefe >= 200 else ""))
    return heraus


# =============================================================================
# Befunde
# =============================================================================
@dataclass
class Ebene:
    """Eine Stufe des Ankers, in einer Zerlegung."""
    nummer: int
    schritt: str
    aufgeloest: bool
    bisher: str
    inhalt: str
    anzahl_gleiche: int


@dataclass
class Ankerbefund:
    """Das Ergebnis EINER Zerlegung fuer EINEN Anker."""
    sicht: str
    position_vorhanden: bool
    bruch_nummer: int = 0
    bruch_schritt: str = ""
    ebenen: List[Ebene] = field(default_factory=list)
    #: BUILD 763 - der Knoten, bis zu dem der Ausdruck getragen hat.
    #:
    #: Bis Build 762 hat die Messung nur festgehalten, DASS und WO ein
    #: Ausdruck bricht. Fuer die Frage, in welchem post container der
    #: ueberlebende Prefix landet, braucht es den Knoten selbst. Er wird hier
    #: mitgefuehrt und NICHT in die JSON-Ausgabe geschrieben - er ist eine
    #: Baumhuelle, kein Messwert.
    #:
    #: Bei null aufgeloesten Schritten steht hier die Wurzel des Baumes. Das
    #: ist kein Ersatzwert: '.' loest tatsaechlich auf. Damit niemand daraus
    #: mehr liest, als gemessen wurde, steht die Zahl der aufgeloesten
    #: Schritte daneben.
    letzter_knoten: Any = None
    #: Wie viele Schritte des Ausdrucks aufgeloest haben.
    aufgeloeste_schritte: int = 0

    @property
    def kurz(self) -> str:
        if self.position_vorhanden:
            return "alle Schritte loesen auf"
        return "bricht bei Schritt %d (%r)" % (self.bruch_nummer,
                                               self.bruch_schritt)


@dataclass
class Zeilenbefund:
    """Ein Beleg, beide Zerlegungen."""
    beleg_id: int
    page_url: str
    anker: str
    lxml: Optional[Ankerbefund] = None
    zweite: Optional[Ankerbefund] = None
    hinweis: str = ""
    #: BUILD 754 - DIE INHALTSPROBE, und sie ist der eigentliche Zweck.
    #:
    #: Bis Build 753 hat dieses Werkzeug ausschliesslich geprueft, ob die vom
    #: Ausdruck verlangte POSITION existiert. Ob dort auch der markierte
    #: Wortlaut steht, wurde nie gefragt - der Wortlaut kam in der ganzen
    #: Datei nicht vor. Das Feld hiess 'traegt' und ist als 'der Ausdruck
    #: stimmt' gelesen worden; es hiess aber nur 'die Indizes existieren'.
    #: Auf einer Seite mit 500 Beitraegen existiert fast jeder Index - er ist
    #: dann nur der falsche.
    #:
    #: Gemessen am Ermittlungsfenster (M1b, 31.08.2026): auf
    #: '/forum/pmsnew.php?mdl=topic&tid=64200' liefern von 46 Annotationen
    #: SIEBEN einen Bereich mit dem gespeicherten Wortlaut. Die alte Pruefung
    #: haette dort rund 31 als 'traegt' gemeldet.
    pruefung: Optional[Any] = None

    # ---- BUILD 763 -------------------------------------------------------
    #: Der zweite Ausdruck der Markierung. Leer, wenn 'xpathEnd' fehlt.
    anker_end: str = ""
    #: Die Messung des zweiten Ausdrucks, in beiden Zerlegungen.
    lxml_end: Optional[Ankerbefund] = None
    zweite_end: Optional[Ankerbefund] = None
    #: Die Seitenklasse aus der Adresse ('viewtopic', 'search', ...).
    seitenklasse: str = ""
    #: Der post-Bezug beider Endpunkte, gemessen in der HTML5-Zerlegung.
    #:
    #: WARUM IN DER HTML5-ZERLEGUNG UND NICHT IN DER VON libxml2: Der Baum,
    #: in dem der Ausdruck ENTSTANDEN ist, ist der des Browsers. Gemessen an
    #: 17 Konstrukten gegen Chromium (31.08.2026, s. requirements.txt): lxml
    #: roh 7 Treffer, html5lib 17. Den post-Bezug in der libxml2-Zerlegung zu
    #: nehmen hiesse, den Beitrag in einem Baum zu suchen, den es im Browser
    #: nie gegeben hat.
    bezug_start: Optional[Any] = None
    bezug_end: Optional[Any] = None
    spanne: Optional[Any] = None
    #: Die abgeleitete Fallzuordnung 1-6, 0 = unbestimmt.
    fall: int = 0
    fall_typ: str = ""
    fall_posts: List[int] = field(default_factory=list)
    fall_grund: str = ""

    @property
    def anker_end_fehlt(self) -> bool:
        """Die Markierung hat keinen zweiten Ausdruck."""
        return not self.anker_end

    # ------------------------------------------------------------------
    @staticmethod
    def _anker_dict(b: Optional[Ankerbefund],
                    bezug: Optional[Any]) -> Dict[str, Any]:
        """
        Ein Endpunkt als Zuordnung. Der Knoten selbst geht NICHT hinein -
        er ist eine Baumhuelle und kein Messwert.
        """
        aus: Dict[str, Any] = {
            "resolves": bool(b is not None and b.position_vorhanden),
            "steps_resolved": (b.aufgeloeste_schritte if b else 0),
            "break_step_no": (b.bruch_nummer if b else 0),
            "break_step": (b.bruch_schritt if b else ""),
            "resolving_prefix": "",
            "sibling_count": 0,
        }
        if b is not None and b.ebenen:
            #: Der laengste Prefix, der noch aufgeloest hat, und die Zahl der
            #: siblings gleicher Marke an der Stelle, an der es bricht.
            aufgeloeste = [e for e in b.ebenen if e.aufgeloest]
            if aufgeloeste:
                letzte = aufgeloeste[-1]
                aus["resolving_prefix"] = letzte.bisher + "/" + letzte.schritt
            else:
                aus["resolving_prefix"] = b.ebenen[0].bisher
            aus["sibling_count"] = b.ebenen[-1].anzahl_gleiche
        if bezug is not None:
            aus.update(bezug.als_dict())
        return aus

    def als_dict(self) -> Dict[str, Any]:
        """BUILD 763 - eine Zeile je Markierung, Schluessel englisch."""
        return {
            "annotation_id": self.beleg_id,
            "page_url": self.page_url,
            "page_class": self.seitenklasse,
            "xpath_start": self.anker,
            "xpath_end": self.anker_end,
            "xpath_end_missing": self.anker_end_fehlt,
            "note": self.hinweis,
            "start": self._anker_dict(self.zweite, self.bezug_start),
            "end": self._anker_dict(self.zweite_end, self.bezug_end),
            "start_libxml2_resolves": bool(
                self.lxml is not None and self.lxml.position_vorhanden),
            "end_libxml2_resolves": bool(
                self.lxml_end is not None
                and self.lxml_end.position_vorhanden),
            "span": (self.spanne.als_dict() if self.spanne is not None
                     else {"posts_between": [], "measurable": False,
                           "reason": "nicht gemessen"}),
            "case": self.fall,
            "case_text": FALL_TEXT.get(self.fall, ""),
            "proposed_type": self.fall_typ,
            "posts_affected": list(self.fall_posts),
            "case_reason": self.fall_grund,
        }

    @property
    def entscheidend(self) -> bool:
        """
        Traegt die eine Zerlegung und die andere nicht? DAS ist der Befund,
        um dessentwillen dieses Werkzeug gebaut wurde.
        """
        return (self.lxml is not None and self.zweite is not None
                and self.lxml.position_vorhanden
                != self.zweite.position_vorhanden)


@dataclass
class Seitenbefund:
    """Eine Seite: der Vergleich der beiden Zerlegungen, Stufe fuer Stufe."""
    page_url: str
    vorhanden: bool = True
    laenge: int = 0
    zeilen: List[str] = field(default_factory=list)
    abweichung_ab: str = ""
    #: Was die Annaeherung an diesem Abzug getan hat - Klartext, damit der
    #: Eingriff im Vermerk steht und nicht still bleibt (Grundregel 1).
    annaeherung: List[str] = field(default_factory=list)
    #: M3 - die Rohtext-Elemente und ob ihr Inhalt ausgeglichen ist.
    rohtext: str = ""
    #: M4 (Build 739) - was libxml2 selbst beim Zerlegen gemeldet hat.
    fehlerprotokoll: List[str] = field(default_factory=list)
    #: M5 (Build 739) - wo die bekannten Kennungen WIRKLICH stehen.
    verortung: List[str] = field(default_factory=list)
    #: M6 (Build 741) - die Quelltextzeilen, die der Zerleger genannt hat.
    quelltext: List[str] = field(default_factory=list)
    #: M7 (Build 744) - wo die Elemente stehen, die der gebrochene Schritt
    #: verlangt. Leer, wenn auf dieser Seite kein Anker gebrochen ist: dann
    #: gibt es nichts zu verorten, und eine Messung ohne Anlass ist Ballast.
    verteilung_roh: List[str] = field(default_factory=list)
    verteilung_genaehert: List[str] = field(default_factory=list)
    #: Der Tagname des gebrochenen Schritts ('article'), fuer die Ueberschrift.
    verteilung_marke: str = ""

    # ---- BUILD 763 -------------------------------------------------------
    #: Die Seitenklasse aus der Adresse.
    seitenklasse: str = ""
    #: Wie viele post container der Abzug traegt (dedupliziert je Nummer).
    container_zahl: int = 0
    #: Verschachtelte container mit VERSCHIEDENEN Nummern - der Fall, den
    #: verschraenkt geschlossener BB-Code erzeugen kann. Leer ist der
    #: Regelfall.
    verschachtelungen: List[Any] = field(default_factory=list)
    #: Klartext, wenn Seitenklasse und Messung einander widersprechen.
    #: Erwartet wird nichts erzwungen - der Widerspruch wird nur benannt.
    widerspruch: str = ""


@dataclass
class Laufbefund:
    seiten: List[Seitenbefund] = field(default_factory=list)
    belege: List[Zeilenbefund] = field(default_factory=list)
    fehler: str = ""
    #: BUILD 763 - die Kennung des Bestandes, aus dem gelesen wurde. Beim
    #: Lauf ueber alle Bestaende steht in jedem Befund seine eigene.
    uid: str = ""
    #: Wie viele Markierungen mit Anker der Bestand insgesamt haelt, und ob
    #: die Grenze davon etwas abgeschnitten hat.
    gesamtzahl: int = 0
    abgeschnitten: bool = False

    def zaehlung(self) -> Dict[str, int]:
        return {
            "belege": len(self.belege),
            "lxml_traegt": sum(1 for b in self.belege
                               if b.lxml is not None
                               and b.lxml.position_vorhanden),
            "genaehert_traegt": sum(1 for b in self.belege
                                 if b.zweite is not None
                                 and b.zweite.position_vorhanden),
            "entscheidend": sum(1 for b in self.belege if b.entscheidend),
            "seiten": len(self.seiten),
            "seiten_abweichend": sum(1 for s in self.seiten
                                     if s.abweichung_ab),
        }

    # ------------------------------------------------------------------
    def fallzaehlung(self) -> Dict[int, int]:
        """BUILD 763 - wie viele Belege auf welchen der Faelle 0-6 fallen."""
        aus: Dict[int, int] = {n: 0 for n in range(7)}
        for b in self.belege:
            aus[b.fall] = aus.get(b.fall, 0) + 1
        return aus

    # ------------------------------------------------------------------
    def klassenzaehlung(self) -> Dict[str, int]:
        """
        BUILD 763 - die Verteilung der Seitenarten ueber die Belege.

        WOZU: Die Liste der beitragsfreien Seitenarten ist bisher eine
        Erwartung (Alex, 06.09.2026). Erst diese Verteilung sagt, welche
        Seitenarten im Bestand ueberhaupt vorkommen - damit die Liste
        gemessen und nicht angenommen ist.
        """
        aus: Dict[str, int] = {}
        for b in self.belege:
            schluessel = b.seitenklasse or "(ohne Adresse)"
            aus[schluessel] = aus.get(schluessel, 0) + 1
        return aus

    # ------------------------------------------------------------------
    def als_dict(self) -> Dict[str, Any]:
        """
        BUILD 763 - der maschinenlesbare Befund.

        SCHLUESSEL ENGLISCH: Die JSON-Ausgabe ist die Schnittstelle nach
        aussen und wird mit anderen Messreihen zusammengefuehrt (Weisung
        Alex, 04.09.2026: Schluessel englisch, Endnutzerausgaben deutsch).
        Der Klartextbericht bleibt deutsch.
        """
        return {
            "subject_id": self.uid,
            "error": self.fehler,
            "annotations_total": self.gesamtzahl,
            "annotations_read": len(self.belege),
            "truncated": self.abgeschnitten,
            "counts": self.zaehlung(),
            "cases": {str(k): v for k, v in sorted(
                self.fallzaehlung().items())},
            "page_classes": self.klassenzaehlung(),
            "pages": [
                {
                    "page_url": s.page_url,
                    "page_class": s.seitenklasse,
                    "available": s.vorhanden,
                    "post_containers": s.container_zahl,
                    "nested_different_numbers": [
                        v.als_dict() for v in s.verschachtelungen],
                    "contradiction": s.widerspruch,
                }
                for s in self.seiten
            ],
            "annotations": [b.als_dict() for b in self.belege],
        }


# =============================================================================
# Die Diagnose
# =============================================================================
class AnkerDiagnose:
    """
    Den Ankerbruch messen. REIN LESEND.

    Verwendung (s. tools/anker_diagnose.py):

        d = AnkerDiagnose(evidence=Path(...), forensic=Path(...))
        befund = d.lauf(grenze=50)
    """

    def __init__(self, *, evidence: Path, forensic: Path,
                 nur_beleg: Optional[int] = None) -> None:
        self._evidence = Path(evidence)
        self._forensic = Path(forensic)
        self._nur_beleg = nur_beleg
        #: je Adresse: (body_html, SichtLxml, SichtHtml5)
        self._seiten: Dict[str, Tuple[str, Any, Any]] = {}
        #: BUILD 754 - der AbsatzFinder je Adresse, fuer die Inhaltspruefung.
        #: Eigener Zwischenspeicher, weil er einen ANDEREN Baum haelt als die
        #: beiden Sichten: den, gegen den auch der Nachtrag auswertet. Wer
        #: hier eine der Sichten einsetzte, verglichene den Inhalt gegen einen
        #: anderen Baum als die Auswertung - und genau das soll das Werkzeug
        #: ja aufdecken.
        self._finder_je_seite: Dict[str, Any] = {}
        #: BUILD 763 - der PostBezugMesser je Adresse. Eigener
        #: Zwischenspeicher, weil er an der HTML5-Zerlegung haengt und nicht
        #: am Baum des AbsatzFinders.
        self._messer_je_seite: Dict[str, Any] = {}
        self._con_blob: Optional[sqlite3.Connection] = None
        #: BUILD 763 - wie viele Markierungen mit Anker der Bestand haelt,
        #: und ob die Grenze davon etwas abgeschnitten hat.
        self._gesamtzahl: int = 0
        self._abgeschnitten: bool = False

    # ------------------------------------------------------------------
    def lauf(self, *, grenze: int = 50) -> Laufbefund:
        befund = Laufbefund()
        for pfad in (self._evidence, self._forensic):
            if not pfad.exists():
                befund.fehler = "Datei fehlt: %s" % pfad
                return befund
        con = None
        try:
            con = self._oeffnen()
            self._con_blob = con
            zeilen = self._kandidaten(con, grenze)
            if not zeilen:
                befund.fehler = ("Keine Markierung mit XPath-Anker gefunden. "
                                 "Das ist ein Leerbefund, kein Fehler.")
                return befund
            for r in zeilen:
                befund.belege.append(self._eine_zeile(r))
            for url in sorted({b.page_url for b in befund.belege if b.page_url}):
                befund.seiten.append(self._eine_seite(url, befund))
            befund.gesamtzahl = self._gesamtzahl
            befund.abgeschnitten = self._abgeschnitten
        except sqlite3.Error as exc:
            befund.fehler = "Datenbankfehler: %s" % exc
        finally:
            if con is not None:
                con.close()
            self._con_blob = None
        return befund

    # ------------------------------------------------------------------
    def _oeffnen(self) -> sqlite3.Connection:
        """
        BEIDE Datenbanken NUR LESEND. 'mode=ro' ist hier keine Vorsicht,
        sondern die Einstufung: ohne sie waere dieses Werkzeug nach den
        Wartungsstufen ein schreibendes und braeuchte ein Wartungsfenster -
        fuer eine Messung, die nichts anfasst.
        """
        con = sqlite3.connect(
            "file:%s?mode=ro" % self._evidence.as_posix(), uri=True)
        con.row_factory = sqlite3.Row
        con.execute("ATTACH DATABASE ? AS fdb",
                    ("file:%s?mode=ro" % self._forensic.as_posix(),))
        return con

    # ------------------------------------------------------------------
    def _kandidaten(self, con: sqlite3.Connection,
                    grenze: int) -> List[sqlite3.Row]:
        """
        Markierungen MIT Anker. Ohne Anker gibt es nichts zu diagnostizieren -
        die stehen im Nachtrag unter GRUND_OHNE_ANKER und sind ein anderer
        Fall.
        """
        sql = ("SELECT id, page_url, selection_json FROM annotations "
               "WHERE selection_json IS NOT NULL AND selection_json != '' "
               "AND deleted_at IS NULL")
        parameter: List[Any] = []
        if self._nur_beleg is not None:
            sql += " AND id = ?"
            parameter.append(self._nur_beleg)
        sql += " ORDER BY id"
        # BUILD 763: 'grenze <= 0' heisst OHNE GRENZE. Der Lauf ueber alle
        # Bestaende braucht das - eine voreingestellte Obergrenze von 50
        # haette dort still die Haelfte eines Bestandes weggelassen.
        ohne_grenze = int(grenze) <= 0
        if not ohne_grenze:
            sql += " LIMIT ?"
            parameter.append(int(grenze))
        heraus: List[sqlite3.Row] = []
        for r in con.execute(sql, parameter):
            if self._anker_aus(r["selection_json"]):
                heraus.append(r)
        # Grundregel 1: ob die Grenze WIRKLICH abgeschnitten hat, wird
        # gezaehlt und ausgewiesen - nicht daraus geschlossen, dass die Zahl
        # gleich der Grenze ist (das kann Zufall sein).
        if not ohne_grenze:
            self._gesamtzahl = self._zaehle_alle(con)
            self._abgeschnitten = self._gesamtzahl > len(heraus)
        else:
            self._gesamtzahl = len(heraus)
            self._abgeschnitten = False
        return heraus

    # ------------------------------------------------------------------
    def _zaehle_alle(self, con: sqlite3.Connection) -> int:
        """
        Wie viele Markierungen MIT Anker der Bestand insgesamt haelt - ohne
        Grenze. Nur zum Vergleich mit der tatsaechlich gelesenen Zahl.
        """
        sql = ("SELECT selection_json FROM annotations "
               "WHERE selection_json IS NOT NULL AND selection_json != '' "
               "AND deleted_at IS NULL")
        parameter: List[Any] = []
        if self._nur_beleg is not None:
            sql += " AND id = ?"
            parameter.append(self._nur_beleg)
        return sum(1 for r in con.execute(sql, parameter)
                   if self._anker_aus(r["selection_json"]))

    # ------------------------------------------------------------------
    @staticmethod
    def _anker_aus(roh: Any) -> str:
        try:
            sel = json.loads(roh) if isinstance(roh, (str, bytes)) else roh
        except (ValueError, TypeError):
            return ""
        if not isinstance(sel, dict):
            return ""
        if sel.get("target") == "translation":
            # Uebersetzungsmarken haben keinen XPath in den Abzug - sie
            # verankern per Zeichenversatz im uebersetzten Text. Kein Bruch,
            # kein Befund.
            return ""
        return str(sel.get("xpathStart") or "")

    # ------------------------------------------------------------------
    @staticmethod
    def _anker_paar_aus(roh: Any) -> Tuple[str, str]:
        """
        BUILD 763 - BEIDE Ausdruecke einer Markierung.

        Bis Build 762 hat dieses Werkzeug ausschliesslich 'xpathStart'
        angesehen. Fuer die Frage, ob eine Markierung einen ganzen Beitrag
        umfasst, ist das zu wenig: sie wird erst aus dem Verhaeltnis BEIDER
        Endpunkte beantwortbar (Fallzuordnung 1-6, Festlegung 06.09.2026).

        'xpathEnd' darf fehlen. Dann steht hier der Anfang auch als Ende -
        eine Markierung ohne zweiten Ausdruck ist punktfoermig, und das ist
        eine Aussage, kein Fehler. Der Aufrufer sieht es an
        'Zeilenbefund.anker_end_fehlt'.
        """
        anfang = AnkerDiagnose._anker_aus(roh)
        if not anfang:
            return "", ""
        try:
            sel = json.loads(roh) if isinstance(roh, (str, bytes)) else roh
        except (ValueError, TypeError):            # pragma: no cover
            return anfang, ""
        if not isinstance(sel, dict):              # pragma: no cover
            return anfang, ""
        return anfang, str(sel.get("xpathEnd") or "")

    # ------------------------------------------------------------------
    def _eine_zeile(self, r: sqlite3.Row) -> Zeilenbefund:
        url = str(r["page_url"] or "")
        anker, anker_end = self._anker_paar_aus(r["selection_json"])
        z = Zeilenbefund(beleg_id=int(r["id"]), page_url=url, anker=anker)
        z.anker_end = anker_end
        z.seitenklasse = seitenklasse(url)
        sichten = self._sichten(url)
        if sichten is None:
            z.hinweis = ("Zu dieser Adresse gibt es keinen GET-Abzug - der "
                         "Anker ist damit gar nicht pruefbar.")
            return z
        _body, roh_sicht, html5_sicht = sichten
        z.lxml = self._anker_pruefen(roh_sicht, anker)
        z.zweite = self._anker_pruefen(html5_sicht, anker)
        # BUILD 763: derselbe Weg fuer den zweiten Ausdruck. Fehlt er, wird
        # der Anfang auch als Ende gemessen - dann ist die Markierung
        # punktfoermig, und 'anker_end_fehlt' sagt das im Bericht.
        zweiter = anker_end or anker
        z.lxml_end = self._anker_pruefen(roh_sicht, zweiter)
        z.zweite_end = self._anker_pruefen(html5_sicht, zweiter)
        # BUILD 754: die Positionspruefung sagt nur, dass die Indizes
        # existieren. Was dort STEHT, sagt erst die Inhaltspruefung - und die
        # entscheidet, ob der Ausdruck etwas wert ist.
        z.pruefung = self._inhalt_pruefen(url, int(r["id"]),
                                          r["selection_json"])
        self._postbezug_messen(z, html5_sicht)
        return z

    # ------------------------------------------------------------------
    def _postbezug_messen(self, z: Zeilenbefund, sicht) -> None:
        """
        BUILD 763 - der post-Bezug beider Endpunkte und die Spanne dazwischen.

        Gemessen wird in der HTML5-Zerlegung (Begruendung s. Zeilenbefund).
        Ein Fehlschlag beendet die Diagnose NICHT - die Positionsmessung ist
        auch ohne post-Bezug eine Auskunft. Er bleibt aber nicht still
        (Grundregel 1): der Befund traegt dann den Hinweis im Klartext.
        """
        if z.zweite is None or z.zweite_end is None:
            return
        try:
            messer = self._messer(z.page_url, sicht)
            if messer is None:
                return
            z.bezug_start = messer.bezug(z.zweite.letzter_knoten)
            z.bezug_end = messer.bezug(z.zweite_end.letzter_knoten)
            z.spanne = messer.spanne(z.zweite.letzter_knoten,
                                     z.zweite_end.letzter_knoten)
            z.fall, z.fall_typ, z.fall_posts, z.fall_grund = fall_bestimmen(
                z.bezug_start, z.bezug_end, z.spanne,
                z.zweite.position_vorhanden,
                z.zweite_end.position_vorhanden)
        except Exception as exc:                  # pragma: no cover - defensiv
            logger.warning("anker_diagnose: post-Bezug zu Beleg %s "
                           "fehlgeschlagen: %s", z.beleg_id, exc)
            z.hinweis = (z.hinweis + " " if z.hinweis else "") + (
                "post-Bezug nicht messbar: %s" % exc)

    # ------------------------------------------------------------------
    def _messer(self, url: str, sicht):
        """
        Der PostBezugMesser zu einer Adresse - je Adresse EINMAL gebaut.

        Er zaehlt die container der Seite und die Dokumentreihenfolge aller
        Elemente aus. Das je Markierung zu wiederholen waere auf einer Seite
        mit 500 Beitraegen und 46 Markierungen 46-facher Aufwand fuer ein
        Ergebnis, das sich nicht aendert. Ausserdem haelt der Messer die
        Baumhuellen fest - s. dort zur Knotenidentitaet.
        """
        if url in self._messer_je_seite:
            return self._messer_je_seite[url]
        messer = None
        try:
            messer = PostBezugMesser(sicht.wurzel)
        except Exception as exc:                  # pragma: no cover - defensiv
            logger.warning("anker_diagnose: PostBezugMesser zu %s nicht "
                           "baubar: %s", url, exc)
        self._messer_je_seite[url] = messer
        return messer

    # ------------------------------------------------------------------
    def _inhalt_pruefen(self, url: str, beleg_id: int, selection_json):
        """
        Die Inhaltspruefung ueber den gemeinsamen Vorgang.

        WARUM NICHT HIER NACHGEBAUT: Die Verifikation gibt es seit Build 754
        genau einmal, in management/maintenance/annotation_pruefung.py, und
        tools/annotationen_verifizieren.py benutzt dieselbe. Zwei Pruefungen
        derselben Frage waeren binnen zweier Builds auseinandergelaufen -
        dann haette man zwei Antworten und keine.

        Ein Fehlschlag hier beendet die Diagnose NICHT: die Positionsmessung
        ist auch ohne Inhaltsprobe eine Auskunft. Er bleibt aber nicht still
        (Grundregel 1) - der Befund traegt dann die Meldung im Klartext.
        """
        try:
            from management.maintenance.annotation_pruefung import (
                AnnotationPruefer)
            finder = self._finder(url)
            if finder is None:
                return None
            return AnnotationPruefer(finder).pruefe(beleg_id, url,
                                                    selection_json)
        except Exception as exc:                  # pragma: no cover - defensiv
            logger.warning("anker_diagnose: Inhaltspruefung zu Beleg %s "
                           "fehlgeschlagen: %s", beleg_id, exc)
            return None

    # ------------------------------------------------------------------
    def _finder(self, url: str):
        """Der AbsatzFinder zu einer Adresse - je Adresse einmal gebaut."""
        if url in self._finder_je_seite:
            return self._finder_je_seite[url]
        from report_render.absatz_finder import AbsatzFinder
        roh = self._blob(url)
        finder = AbsatzFinder.aus_seiten_html(roh) if roh else None
        if finder is not None and not finder.brauchbar:
            finder = None
        self._finder_je_seite[url] = finder
        return finder

    # ------------------------------------------------------------------
    @staticmethod
    def _anker_pruefen(sicht: Sicht, ausdruck: str) -> Ankerbefund:
        """
        MESSUNG M1 - den Anker Stufe fuer Stufe gehen und JEDE Stufe
        festhalten, nicht nur die, an der es bricht.

        Der Nachtrag meldet bisher nur die Bruchstelle. Fuer die Frage, ob
        die fehlenden Elemente woanders stehen, braucht man den ganzen Weg:
        erst daran ist zu sehen, ob der Baum ueberall zwei Ebenen zu flach
        ist oder nur an einer Stelle.
        """
        b = Ankerbefund(sicht=sicht.name, position_vorhanden=True)
        schritte = [t for t in str(ausdruck or "").split("/")
                    if t and t != "."]
        if not schritte:
            b.position_vorhanden = False
            b.bruch_schritt = "(leer)"
            return b
        knoten = sicht.wurzel
        b.letzter_knoten = knoten
        bisher = "."
        for nr, schritt in enumerate(schritte, 1):
            treffer = SCHRITT_MUSTER.match(schritt)
            if not treffer:
                b.position_vorhanden = False
                b.bruch_nummer, b.bruch_schritt = nr, schritt
                b.ebenen.append(Ebene(nr, schritt, False, bisher,
                                      "kein lesbarer Schritt", 0))
                return b
            marke, wunsch = treffer.group(1), int(treffer.group(2))
            if marke == "text()":
                da = sicht.textknoten(knoten)
                trifft = 1 <= wunsch <= da
                b.ebenen.append(Ebene(
                    nr, schritt, trifft, bisher,
                    "%d Textknoten" % da, da))
                if not trifft:
                    b.position_vorhanden = False
                    b.bruch_nummer, b.bruch_schritt = nr, schritt
                    return b
                # Ein Textknoten ist das Ende des Weges. Der Knoten bleibt
                # das Element, DAS ihn traegt - und genau dieses Element
                # steht im post container, nach dem gefragt wird.
                b.aufgeloeste_schritte = nr
                bisher += "/" + schritt
                continue
            naechster = sicht.schritt(knoten, marke, wunsch)
            gleiche = [k for k in sicht.kinder(knoten)
                       if sicht.marke(k) == marke]
            b.ebenen.append(Ebene(
                nr, schritt, naechster is not None, bisher,
                sicht.liste(knoten), len(gleiche)))
            if naechster is None:
                b.position_vorhanden = False
                b.bruch_nummer, b.bruch_schritt = nr, schritt
                return b
            knoten = naechster
            b.letzter_knoten = knoten
            b.aufgeloeste_schritte = nr
            bisher += "/" + schritt
        return b

    # ------------------------------------------------------------------
    def _eine_seite(self, url: str, befund: Laufbefund) -> Seitenbefund:
        """
        MESSUNG M2 + M3 fuer eine Seite.

        M2 steckt schon in den Zeilenbefunden (jeder Anker wurde gegen BEIDE
        Zerlegungen gehalten); hier wird zusammengezaehlt. M3 sucht die
        Rohtext-Elemente und sagt, welche davon ueberhaupt gefaehrlich sind.
        """
        s = Seitenbefund(page_url=url)
        sichten = self._sichten(url)
        if sichten is None:
            s.vorhanden = False
            return s
        body, roh_sicht, html5_sicht = sichten
        s.laenge = len(body)
        s.annaeherung = list(getattr(html5_sicht, "befunde", []))

        # -- BUILD 763: Seitenklasse, container, Verschachtelung -----------
        #
        # DIE KLASSE IST EINE SPALTE, KEIN SCHALTER. Die Erkennung laeuft auf
        # JEDER Seite, auch auf denen, auf denen nach Erwartung keine
        # Beitraege stehen. Wer sie anhand der Adresse ueberspringt, macht
        # den Widerspruch zwischen Erwartung und Abzug per Konstruktion
        # unsichtbar - und das waere ein stiller Sprung (Grundregel 1).
        s.seitenklasse = seitenklasse(url)
        messer = self._messer(url, html5_sicht)
        if messer is not None:
            s.container_zahl = messer.container_zahl
            s.verschachtelungen = messer.verschachtelungen()
            if s.seitenklasse in POSTFREIE_KLASSEN and s.container_zahl:
                s.widerspruch = (
                    "Seitenart '%s' wird als beitragsfrei gefuehrt, der Abzug "
                    "traegt aber %d post container."
                    % (s.seitenklasse, s.container_zahl))
            elif (s.seitenklasse not in POSTFREIE_KLASSEN
                  and s.seitenklasse != KLASSE_SONSTIGE
                  and not s.container_zahl):
                s.widerspruch = (
                    "Seitenart '%s' sollte Beitraege tragen, der Abzug traegt "
                    "keinen einzigen post container." % s.seitenklasse)

        # -- M4: das Fehlerprotokoll von libxml2 --------------------------
        #
        # DIE QUELLE, DIE SECHS BUILDS LANG UNGELESEN BLIEB. Sie benennt die
        # Ursache oft direkt: 'ERR_TAG_NAME_MISMATCH' heisst, ein Element
        # wurde nicht geschlossen; 'ERR_RESOURCE_LIMIT: Excessive depth in
        # document: 256' heisst, libxml2 hat die Schachtelung ABGEBROCHEN und
        # den Rest der Seite weggelassen - eine Grenze, die ein Browser nicht
        # hat. Ein leeres Protokoll ist ebenfalls ein Befund: dann hat der
        # Zerleger nichts zu beanstanden gehabt, und die Ursache liegt nicht
        # bei ihm.
        s.fehlerprotokoll = list(getattr(roh_sicht, "fehlerprotokoll", []))
        if not s.fehlerprotokoll:
            s.fehlerprotokoll = ["(leer - libxml2 hat beim Zerlegen nichts "
                                 "beanstandet)"]

        # -- M5: wo stehen die bekannten Kennungen WIRKLICH? ---------------
        #
        # DIE ENTSCHEIDENDE UNTERSCHEIDUNG. Ein Element, das im Quelltext
        # steht und im Baum FEHLT, ist vom Zerleger weggelassen worden; eines,
        # das im Baum TIEFER steht als erwartet, ist verschluckt worden.
        # Beides sieht in der Kinderzahl gleich aus und verlangt Verschiedenes.
        for kennung in ("wrap", "brdleft", "page-header", "page-body",
                        "page-footer"):
            im_quelltext = ('id="%s"' % kennung) in body or \
                           ("id='%s'" % kennung) in body
            el = roh_sicht.mit_kennung(kennung)
            if el is not None:
                # BUILD 741: nicht nur der Pfad, sondern die BENANNTE Kette.
                # 'div[2]/div[2]' sagt, WO etwas steht; die Kette sagt, WER
                # es dorthin genommen hat - und das ist die Angabe, mit der
                # sich die Stelle im Quelltext wiederfinden laesst.
                s.verortung.append("#%-12s Baum: %s\n%18s Kette: %s"
                                   % (kennung, roh_sicht.pfad_von(el), "",
                                      roh_sicht.kette_von(el)))
            elif im_quelltext:
                s.verortung.append(
                    "#%-12s STEHT IM QUELLTEXT, FEHLT IM BAUM - der Zerleger "
                    "hat es weggelassen" % kennung)
            else:
                s.verortung.append("#%-12s weder im Quelltext noch im Baum"
                                   % kennung)

        # -- M6: die Quelltextzeilen, die der Zerleger genannt hat ---------
        #
        # BUILD 741. Das Fehlerprotokoll nennt Zeile und Spalte
        # ('<string>:92:8'). Ohne die Zeile SELBST ist das eine Zahl; mit ihr
        # ist es ein Konstrukt, das man nachstellen und pruefen kann.
        #
        # WARUM DAS NOETIG WURDE: Ich habe nach dem ersten Protokoll sechs
        # Konstrukte mit nicht geschlossenem <li> gegen einen Browser und
        # gegen libxml2 gehalten - libxml2 verarbeitet sie ALLE richtig. Die
        # Meldung 'li and div' allein genuegt also nicht, um den Fall
        # nachzustellen. Was fehlt, ist die Zeile.
        #
        # VERDECKT: Textknoten und alle nicht freigegebenen Attributwerte.
        # Tagnamen, 'id', 'class' und 'style' bleiben offen - sie sind der
        # Messgegenstand und tragen keinen Fallbezug.
        s.quelltext = self._quelltextzeilen(body, s.fehlerprotokoll)

        # -- M8 GESTRICHEN (Build 747), und der Grund gehoert hierher ----
        #
        # M8 zeigte, an welcher Quelltextzeile der handgebaute Teilnachbau
        # ein Endtag nachgezogen und dabei ein Geruestelement mitgeschlossen
        # hat. Es hat genau das geleistet, wofuer es gebaut wurde: es hat
        # den Fehler IM WERKZEUG gefunden - '</div> hat article#p151.post
        # mitgeschlossen'.
        #
        # Mit dem Teilnachbau ist auch der Mechanismus fort. html5lib zieht
        # keine Endtags in den Text ein; es baut den Baum nach dem Standard.
        # Eine Messung, die ueber ein nicht mehr vorhandenes Verfahren
        # berichtet, kann nur leer bleiben - und eine leere Rubrik in einem
        # Diagnoselauf wird gelesen, als sei dort nichts gewesen. Deshalb
        # gestrichen und nicht stillgelegt.

        # -- M6-Entwurf GESTRICHEN, und der Grund gehoert hierher -----------
        #
        # Der Entwurf hatte eine dritte Messung: an eine wachsende
        # Anfangsstrecke des Quelltextes eine Sonde anhaengen und suchen, ab
        # wann sie nicht mehr unmittelbar unter '#wrap' sitzt. Sie ist NICHT
        # ausgeliefert worden, weil ihr Ergebnis nicht auszulegen ist: ohne
        # einen zweiten Zerleger als Bezugspunkt sagt die Tiefe der Sonde nur
        # etwas ueber die Stelle im Dokument, an der sie haengt, und nicht
        # ueber einen Fehler. Eine Zahl ohne Auslegung wird ausgelegt - und
        # zwar von dem, der sie zuerst liest.

        # -- M3: die Rohtext-Elemente -------------------------------------
        #
        # BUILD 747: DAS IST JETZT EINE AUSKUNFT UND KEINE WARNUNG MEHR.
        # Beide Faelle sind behandelt - <noscript> durch das scripting-Flag
        # des Zerlegers, <template> durch die Leerung. Die Angabe bleibt,
        # weil das Vorhandensein solcher Elemente fuer die Beurteilung eines
        # Abzugs von Belang ist: wer eine Auffaelligkeit sucht, will wissen,
        # ob es sie gibt.
        from report_render.html5_zerleger import rohtext_stellen
        stellen = rohtext_stellen(body)
        if not stellen:
            s.rohtext = ("Kein <noscript> und kein <template> im Abzug.")
        else:
            unausgeglichen = [x for x in stellen if not x[2]]
            s.rohtext = (
                "%d Rohtext-Element(e) im Abzug: %s. Davon %d mit "
                "unausgeglichenem Inhalt. BEIDE FAELLE SIND SEIT BUILD 747 "
                "BEHANDELT - <noscript> ueber das scripting-Flag, <template> "
                "ueber die Leerung; die Angabe steht hier zur Beurteilung des "
                "Abzugs, nicht als Warnung."
                % (len(stellen),
                   ", ".join("<%s> bei Zeichen %d%s"
                             % (m, v, "" if ok else " (unausgeglichen)")
                             for v, m, ok in stellen[:8]),
                   len(unausgeglichen)))

        # -- M7: wo stehen die Elemente, die der gebrochene Schritt will? --
        #
        # NUR bei einem Bruch, und nur zu DEM Tag, an dem er bricht. Eine
        # Verteilung ueber alle Tagnamen der Seite waere eine Seitenlage und
        # keine Messung - sie beantwortete keine Frage, sondern lieferte
        # Zahlen, aus denen sich jede Vermutung belegen liesse.
        #
        # Genommen wird der Bruch der ANGENAEHERTEN Zerlegung: sie ist seit
        # Build 742 der Weg, auf dem der Bericht laeuft. Der rohe Bruch ist
        # der Rueckfall, falls die Annaeherung durchlaeuft und nur die rohe
        # bricht.
        bruch_schritt = ""
        for b in befund.belege:
            if b.page_url != url:
                continue
            if b.zweite is not None and not b.zweite.position_vorhanden:
                bruch_schritt = b.zweite.bruch_schritt
                break
            if (not bruch_schritt and b.lxml is not None
                    and not b.lxml.position_vorhanden):
                bruch_schritt = b.lxml.bruch_schritt
        if bruch_schritt:
            treffer = SCHRITT_MUSTER.match(bruch_schritt)
            if treffer and treffer.group(1) != "text()":
                s.verteilung_marke = treffer.group(1)
                s.verteilung_roh = verteilung_zeilen(roh_sicht,
                                                     s.verteilung_marke)
                s.verteilung_genaehert = verteilung_zeilen(
                    html5_sicht, s.verteilung_marke)

        # -- Der Ebenenvergleich entlang des ersten Ankers dieser Seite ----
        anker = ""
        for b in befund.belege:
            if b.page_url == url and b.anker:
                anker = b.anker
                break
        if not anker:
            return s

        schritte = [t for t in anker.split("/") if t and t != "."]
        a, c = roh_sicht.wurzel, html5_sicht.wurzel
        bisher = "."
        for schritt in schritte:
            treffer = SCHRITT_MUSTER.match(schritt)
            if not treffer or treffer.group(1) == "text()":
                break
            marke, wunsch = treffer.group(1), int(treffer.group(2))
            za = len([k for k in roh_sicht.kinder(a)
                      if roh_sicht.marke(k) == marke]) if a is not None else -1
            zc = len([k for k in html5_sicht.kinder(c)
                      if html5_sicht.marke(k) == marke]) \
                if c is not None else -1
            # '-' statt einer Zahl, sobald ein Zweig schon abgerissen ist.
            # Eine '-1' waere eine Zahl und laedt zum Vergleichen ein; hier
            # gibt es aber nichts mehr zu vergleichen, weil dieser Zweig gar
            # nicht mehr existiert. Das gehoert sichtbar unterschieden.
            def _z(w):
                return "-" if w < 0 else str(w)
            wirkt = (za != zc and za >= 0 and zc >= 0) or (za < 0 <= zc)
            s.zeilen.append(
                "%-44s <%s>[%d]: roh %s, angenaehert %s%s"
                % (bisher, marke, wunsch, _z(za), _z(zc),
                   "   <-- HIER WIRKT DIE ANNAEHERUNG"
                   if wirkt and not s.abweichung_ab else ""))
            if za != zc and not s.abweichung_ab:
                s.abweichung_ab = bisher
                s.zeilen.append("%-44s roh hat dort:         %s"
                                % ("", roh_sicht.liste(a)
                                   if a is not None else "-"))
                s.zeilen.append("%-44s angenaehert hat dort: %s"
                                % ("", html5_sicht.liste(c)
                                   if c is not None else "-"))
            a = roh_sicht.schritt(a, marke, wunsch) if a is not None else None
            c = html5_sicht.schritt(c, marke, wunsch) \
                if c is not None else None
            bisher += "/" + schritt
            if a is None and c is None:
                break
        return s

    # ------------------------------------------------------------------
    @staticmethod
    def _quelltextzeilen(body: str, protokoll: Sequence[str]) -> List[str]:
        """
        Zu jeder Fehlermeldung mit Zeilenangabe die Zeile selbst - verdeckt.

        Die Zeilenzaehlung stammt vom Zerleger. Er bekommt den Rumpf mit
        einem kuenstlichen <div> davor; die Zaehlung kann deshalb um eine
        Zeile verschoben sein. Deswegen werden ZWEI Zeilen davor und EINE
        danach mitgegeben - und die Verschiebung wird benannt statt
        stillschweigend hingenommen.
        """
        zeilen = body.split("\n")
        heraus: List[str] = []
        gesehen = set()
        for eintrag in protokoll:
            m = re.search(r":(\d+):(\d+):", str(eintrag))
            if not m:
                continue
            nr = int(m.group(1))
            if nr in gesehen:
                continue
            gesehen.add(nr)
            heraus.append("--- Meldung bei Zeile %s, Spalte %s ---"
                          % (m.group(1), m.group(2)))
            for i in range(max(1, nr - 2), min(len(zeilen), nr + 1) + 1):
                heraus.append("%6d | %s" % (i, verdecke_tag_folge(zeilen[i - 1])))
            if len(gesehen) >= 4:
                break
        if not heraus:
            heraus.append("Keine Fehlermeldung mit Zeilenangabe - nichts zu "
                          "zeigen.")
        else:
            heraus.append("(Die Zeilenzaehlung stammt vom Zerleger und kann "
                          "um eine Zeile verschoben sein - er bekommt ein "
                          "kuenstliches <div> vorangestellt.)")
        return heraus

    # ------------------------------------------------------------------
    def _sichten(self, url: str):
        """Beide Zerlegungen zu einer Adresse - je Adresse einmal gebaut."""
        if url in self._seiten:
            return self._seiten[url]
        roh = self._blob(url)
        if not roh:
            self._seiten[url] = None
            return None
        try:
            from server.blob_handler import BlobHandler
            body = BlobHandler._extract_body(roh)
        except Exception as exc:                  # pragma: no cover - defensiv
            logger.warning("anker_diagnose: <body> nicht abgrenzbar: %s", exc)
            self._seiten[url] = None
            return None
        try:
            paar = (body, SichtLxml(body), SichtHtml5(body))
        except Exception as exc:                  # pragma: no cover - defensiv
            logger.warning("anker_diagnose: nicht zerlegbar: %s", exc)
            self._seiten[url] = None
            return None
        self._seiten[url] = paar
        return paar

    # ------------------------------------------------------------------
    def _blob(self, url: str) -> Optional[bytes]:
        """
        Den GET-Abzug zu einer Adresse holen.

        DIESELBEN VIER ABFRAGEN WIE IM NACHTRAG, einschliesslich des Filters
        auf method='GET'. Das ist keine Bequemlichkeit: eine Diagnose, die
        einen ANDEREN Abzug liest als das Werkzeug, dessen Verhalten sie
        erklaeren soll, erklaert nichts. Der Filter ist der Fehler aus Build
        731 - er hat dort schon einmal eine richtige Meldung mit einer
        falschen Diagnose verbunden.
        """
        if not url or self._con_blob is None:
            return None
        for sql, parameter in (
            ("SELECT html FROM fdb.pages WHERE url_canonical = ? "
             "AND method = 'GET' LIMIT 1", (url,)),
            ("SELECT p.html FROM fdb.pages p JOIN fdb.page_aliases a "
             "ON a.page_id = p.id WHERE a.url_raw = ? AND p.method = 'GET' "
             "LIMIT 1", (url,)),
            ("SELECT html FROM fdb.pages WHERE url_canonical LIKE ? "
             "AND method = 'GET' LIMIT 1", ("%" + url,)),
            ("SELECT p.html FROM fdb.pages p JOIN fdb.page_aliases a "
             "ON a.page_id = p.id WHERE a.url_raw LIKE ? "
             "AND p.method = 'GET' LIMIT 1", ("%" + url,)),
        ):
            try:
                zeile = self._con_blob.execute(sql, parameter).fetchone()
            except sqlite3.Error as exc:
                logger.warning("anker_diagnose: Abfrage fehlgeschlagen (%s)",
                               exc)
                continue
            if zeile is not None and zeile[0]:
                return zeile[0]
        return None

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
#   M2  DIE GEGENPROBE MIT DER ANNAEHERUNG. Derselbe Anker, dieselbe
#       Zerlegung - aber auf dem Abzug, der vorher an zwei HTML5-Regeln
#       angenaehert wurde, die libxml2 nicht kennt (Rohtext in <noscript>,
#       eigenes Fragment fuer <template>; s.
#       report_render/html5_annaeherung.py). LOEST DER ANKER DANN AUF, IST
#       DIE FRAGE BEANTWORTET - und zwar mit dem Fix in der Hand.
#
#       DER ERSTE ENTWURF DIESER DATEI STELLTE libxml2 GEGEN html.parser.
#       Das haette nichts beantwortet: die Messung gegen Chromium vom
#       30.08.2026 zeigt, dass html.parser dieselben beiden Regeln ebenso
#       wenig kennt. Beide haetten uebereinstimmend das falsche Ergebnis
#       geliefert - und die Uebereinstimmung waere als Entlastung der
#       Zerlegung gelesen worden. Eine Gegenprobe, die nur bestaetigen kann,
#       ist keine.
#
#   M3  DIE ROHTEXT-ELEMENTE IM ABZUG. Wo stehen <noscript> und <template>,
#       und ist ihr Inhalt ausgeglichen? NUR ein unausgeglichener Inhalt kann
#       die Zerlegung sprengen; ein heiles <noscript> ist harmlos. Die
#       Unterscheidung erspart eine Fehlspur.
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
# Version: 0.8.744 - Build 744 (M7 ergaenzt)
# =============================================================================

from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

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


class SichtGenaehert(SichtLxml):
    """
    DIESELBE Zerlegung wie im Bericht - aber auf dem an die Browser-Regeln
    ANGENAEHERTEN Abzug (report_render/html5_annaeherung.py).

    WARUM NICHT EIN ZWEITER ZERLEGER ALS ZWEITE MEINUNG: Der erste Entwurf
    dieser Datei stellte libxml2 gegen html.parser. Die Messung vom
    30.08.2026 gegen Chromium zeigt, dass das nichts beantwortet haette -
    html.parser kennt die beiden entscheidenden HTML5-Regeln (Rohtext in
    <noscript>, eigenes Fragment fuer <template>) ebenso wenig wie libxml2.
    Beide haetten uebereinstimmend das falsche Ergebnis geliefert, und die
    Uebereinstimmung waere als Entlastung der Zerlegung gelesen worden.

    Die richtige Gegenprobe ist deshalb nicht 'ein anderer Zerleger', sondern
    'derselbe Zerleger auf dem angenaeherten Text'. Loest der Anker DANN auf,
    ist die Frage beantwortet - und zwar mit dem Fix in der Hand.
    """

    name = "libxml2 nach Annaeherung an die Browser-Regeln"

    def __init__(self, body_html: str) -> None:
        from report_render.html5_annaeherung import annaehern
        genaehert, self.befunde = annaehern(body_html)
        super().__init__(genaehert)


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
            "Schachtelung: %d. Das ist eine Kaskade der Zerlegung, kein "
            "Merkmal der Seite: ein <%s> gehoert nicht in ein <%s>."
            % (verschachtelt, len(knoten), marke, tiefste, marke, marke))
    else:
        heraus.append(
            "  KEINES steht innerhalb eines anderen <%s>. Eine Kaskade "
            "scheidet damit aus - die Elemente stehen nebeneinander, nur "
            "nicht an der vom Anker verlangten Stelle." % marke)

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
    traegt: bool
    bruch_nummer: int = 0
    bruch_schritt: str = ""
    ebenen: List[Ebene] = field(default_factory=list)

    @property
    def kurz(self) -> str:
        if self.traegt:
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

    @property
    def entscheidend(self) -> bool:
        """
        Traegt die eine Zerlegung und die andere nicht? DAS ist der Befund,
        um dessentwillen dieses Werkzeug gebaut wurde.
        """
        return (self.lxml is not None and self.zweite is not None
                and self.lxml.traegt != self.zweite.traegt)


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


@dataclass
class Laufbefund:
    seiten: List[Seitenbefund] = field(default_factory=list)
    belege: List[Zeilenbefund] = field(default_factory=list)
    fehler: str = ""

    def zaehlung(self) -> Dict[str, int]:
        return {
            "belege": len(self.belege),
            "lxml_traegt": sum(1 for b in self.belege
                               if b.lxml is not None and b.lxml.traegt),
            "genaehert_traegt": sum(1 for b in self.belege
                                 if b.zweite is not None and b.zweite.traegt),
            "entscheidend": sum(1 for b in self.belege if b.entscheidend),
            "seiten": len(self.seiten),
            "seiten_abweichend": sum(1 for s in self.seiten
                                     if s.abweichung_ab),
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
        #: je Adresse: (body_html, SichtLxml, SichtGenaehert)
        self._seiten: Dict[str, Tuple[str, Any, Any]] = {}
        self._con_blob: Optional[sqlite3.Connection] = None

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
        sql += " ORDER BY id LIMIT ?"
        parameter.append(max(1, int(grenze)))
        heraus: List[sqlite3.Row] = []
        for r in con.execute(sql, parameter):
            if self._anker_aus(r["selection_json"]):
                heraus.append(r)
        return heraus

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
    def _eine_zeile(self, r: sqlite3.Row) -> Zeilenbefund:
        url = str(r["page_url"] or "")
        anker = self._anker_aus(r["selection_json"])
        z = Zeilenbefund(beleg_id=int(r["id"]), page_url=url, anker=anker)
        sichten = self._sichten(url)
        if sichten is None:
            z.hinweis = ("Zu dieser Adresse gibt es keinen GET-Abzug - der "
                         "Anker ist damit gar nicht pruefbar.")
            return z
        _body, roh_sicht, genaehert_sicht = sichten
        z.lxml = self._anker_pruefen(roh_sicht, anker)
        z.zweite = self._anker_pruefen(genaehert_sicht, anker)
        return z

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
        b = Ankerbefund(sicht=sicht.name, traegt=True)
        schritte = [t for t in str(ausdruck or "").split("/")
                    if t and t != "."]
        if not schritte:
            b.traegt = False
            b.bruch_schritt = "(leer)"
            return b
        knoten = sicht.wurzel
        bisher = "."
        for nr, schritt in enumerate(schritte, 1):
            treffer = SCHRITT_MUSTER.match(schritt)
            if not treffer:
                b.traegt = False
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
                    b.traegt = False
                    b.bruch_nummer, b.bruch_schritt = nr, schritt
                    return b
                # Ein Textknoten ist das Ende des Weges.
                bisher += "/" + schritt
                continue
            naechster = sicht.schritt(knoten, marke, wunsch)
            gleiche = [k for k in sicht.kinder(knoten)
                       if sicht.marke(k) == marke]
            b.ebenen.append(Ebene(
                nr, schritt, naechster is not None, bisher,
                sicht.liste(knoten), len(gleiche)))
            if naechster is None:
                b.traegt = False
                b.bruch_nummer, b.bruch_schritt = nr, schritt
                return b
            knoten = naechster
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
        body, roh_sicht, genaehert_sicht = sichten
        s.laenge = len(body)
        s.annaeherung = list(getattr(genaehert_sicht, "befunde", []))

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
        #
        # M4 und M5 beantworten die Frage ohnehin: M4 nennt die Ursache, M5
        # unterscheidet 'verschluckt' von 'weggelassen'.

        # -- M3: die Rohtext-Elemente -------------------------------------
        from report_render.html5_annaeherung import rohtext_stellen
        stellen = rohtext_stellen(body)
        if not stellen:
            s.rohtext = ("Kein <noscript> und kein <template> im Abzug. Die "
                         "beiden bekannten Zerlegungsfallen scheiden damit "
                         "aus - bleibt der Anker gebrochen, liegt es an "
                         "etwas anderem.")
        else:
            unausgeglichen = [x for x in stellen if not x[2]]
            s.rohtext = (
                "%d Rohtext-Element(e) im Abzug: %s. Davon %d mit "
                "UNAUSGEGLICHENEM Inhalt - nur diese koennen die Zerlegung "
                "sprengen; ein heiles <noscript> ist harmlos."
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
            if b.zweite is not None and not b.zweite.traegt:
                bruch_schritt = b.zweite.bruch_schritt
                break
            if not bruch_schritt and b.lxml is not None and not b.lxml.traegt:
                bruch_schritt = b.lxml.bruch_schritt
        if bruch_schritt:
            treffer = SCHRITT_MUSTER.match(bruch_schritt)
            if treffer and treffer.group(1) != "text()":
                s.verteilung_marke = treffer.group(1)
                s.verteilung_roh = verteilung_zeilen(roh_sicht,
                                                     s.verteilung_marke)
                s.verteilung_genaehert = verteilung_zeilen(
                    genaehert_sicht, s.verteilung_marke)

        # -- Der Ebenenvergleich entlang des ersten Ankers dieser Seite ----
        anker = ""
        for b in befund.belege:
            if b.page_url == url and b.anker:
                anker = b.anker
                break
        if not anker:
            return s

        schritte = [t for t in anker.split("/") if t and t != "."]
        a, c = roh_sicht.wurzel, genaehert_sicht.wurzel
        bisher = "."
        for schritt in schritte:
            treffer = SCHRITT_MUSTER.match(schritt)
            if not treffer or treffer.group(1) == "text()":
                break
            marke, wunsch = treffer.group(1), int(treffer.group(2))
            za = len([k for k in roh_sicht.kinder(a)
                      if roh_sicht.marke(k) == marke]) if a is not None else -1
            zc = len([k for k in genaehert_sicht.kinder(c)
                      if genaehert_sicht.marke(k) == marke]) \
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
                                % ("", genaehert_sicht.liste(c)
                                   if c is not None else "-"))
            a = roh_sicht.schritt(a, marke, wunsch) if a is not None else None
            c = genaehert_sicht.schritt(c, marke, wunsch) \
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
            paar = (body, SichtLxml(body), SichtGenaehert(body))
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

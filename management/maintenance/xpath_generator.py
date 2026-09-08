# -*- coding: utf-8 -*-
# =============================================================================
# management/maintenance/xpath_generator.py
# IT-Forensisches Ermittlungswerkzeug - aiw_webserver
# BUILD 766
# =============================================================================
# ZWECK
#   Erzeugt XPath expressions, die einen Knoten im page BLOB bezeichnen -
#   nach der Rangfolge by_id, by_class, by_position (Regelkatalog
#   selection_json 2.0, Abschnitt 3).
#
# WARUM
#   Die bestehenden expressions verwenden ausschliesslich by_position:
#   'div[4]/article[31]/div[1]/p[1]/text()[1]'. Sie haengen damit an der
#   sibling-Zaehlung und brechen, sobald der Tree anders rekonstruiert wird.
#   Gemessen im Lauf zu Build 764: 44 von 455 expressions loesen im
#   gespeicherten Abzug nicht mehr auf.
#
# DIE RANGFOLGE
#   1. by_id       eindeutige id  ->  //*[@id='X']  (ersetzt den GESAMTEN
#                                     bisherigen Praefix)
#   2. by_class    Klasse, tokenweise geprueft, index ueber die GEFILTERTE
#                  Menge neu gezaehlt
#   3. by_position tag[i] ueber die gleichnamigen siblings
#
#   Nach JEDEM Schritt wird der bis dahin gebaute Ausdruck ausgewertet. Trifft
#   er nicht genau den erwarteten Knoten, faellt der Schritt auf den
#   naechstschwaecheren Rang zurueck. Ohne diese Rueckpruefung entstuende ein
#   Ausdruck, der plausibel aussieht und im Zweifel das falsche Element
#   liefert.
#
# WARUM DIE EINDEUTIGKEITSPRUEFUNG BEI by_id ZWINGEND IST
#   Das Forum ist an dieser Stelle nicht normkonform. viewtopic0.php Z. 989
#   schreibt '<div id="progressbar">' INNERHALB der postleft, also je Beitrag
#   einmal - auf einer Seite mit 500 Beitraegen existiert die id 500-mal.
#   include/type4.php schreibt '<div id="contentType4">' ohne Beitragsnummer
#   und wiederholt sie bei jedem Systembeitrag.
#
#   Ohne Pruefung entstuende '//*[@id="progressbar"]/...' - ein Ausdruck, der
#   AUFLOEST und den ersten von 500 Kandidaten liefert. Das ist schlimmer als
#   ein Bruch, weil es unbemerkt bleibt.
#
#   Die Umstellung im Forum-Quelltext von 'id' auf 'name' (08.09.2026) wirkt
#   nicht rueckwirkend: die vorhandenen page BLOBs wurden vorher gesichert.
#
# WARUM KEINE PRUEFUNG AUF VERKLEINERUNG BEI by_class
#   Rang 2 wird verwendet, sobald eine brauchbare Klasse vorhanden ist
#   (Festlegung Alex, 08.09.2026). Verkleinert die Klasse die Kandidatenmenge
#   nicht, ist der Gewinn null - wir bauen einen deterministischen Pfad, jeder
#   Schritt engt auf genau einen Knoten ein, und ein nicht verkleinerndes
#   Praedikat waehlt denselben Knoten. Die Kosten sind dann aber ebenfalls
#   fast null. Einen Zweig einzubauen, der je Schritt Kandidatenmengen
#   vergleicht, erhoeht die Komplexitaet ohne Nutzen.
#
# WAS DER GENERATOR NICHT LEISTET
#   Der letzte Schritt zu einem Textknoten bleibt zwangslaeufig eine
#   Zaehlung - ein Textknoten traegt weder id noch class. Genau dort sind 38
#   der 44 Brueche entstanden. Der Generator macht das ELEMENT robust, nicht
#   die Position im Text; die Stelle im Text wird beim Lesen ueber den
#   gespeicherten Wortlaut bestimmt (Regelkatalog 3.6).
#
# WARTUNGSSTUFE
#   Rein lesend. Keine Datenbank, kein Zustand ueber den Baum hinaus.
# =============================================================================
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from management.maintenance.post_bereiche import ZUSTANDSKLASSEN, _xpath_klasse

#: Die drei Verfahren, in absteigender Rangfolge.
RANG_ID = "by_id"
RANG_KLASSE = "by_class"
RANG_POSITION = "by_position"
RANGFOLGE: Tuple[str, ...] = (RANG_ID, RANG_KLASSE, RANG_POSITION)


@dataclass
class Schritt:
    """Ein Schritt der erzeugten expression."""
    rang: str
    ausdruck: str
    #: Der Tagname des Elements, auf das dieser Schritt zeigt.
    marke: str = ""
    #: True, wenn dieser Schritt den bisherigen Praefix ERSETZT (nur by_id).
    ersetzt_praefix: bool = False
    #: Auf welche Raenge zurueckgefallen wurde, und warum.
    rueckfaelle: List[str] = field(default_factory=list)

    def als_dict(self) -> Dict[str, Any]:
        return {"rank": self.rang, "step": self.ausdruck, "tag": self.marke,
                "replaces_prefix": self.ersetzt_praefix,
                "fallbacks": list(self.rueckfaelle)}


@dataclass
class Erzeugnis:
    """Das Ergebnis einer Erzeugung."""
    ausdruck: str = ""
    schritte: List[Schritt] = field(default_factory=list)
    #: Ob der fertige Ausdruck genau den Zielknoten trifft.
    traegt: bool = False
    #: Klartext, wenn nicht.
    hinweis: str = ""

    @property
    def rangzaehlung(self) -> Dict[str, int]:
        aus = {r: 0 for r in RANGFOLGE}
        for s in self.schritte:
            aus[s.rang] = aus.get(s.rang, 0) + 1
        return aus

    @property
    def bester_rang(self) -> str:
        """
        Der staerkste Rang, der in dieser expression vorkommt.

        Aussagekraeftig, weil ein 'by_id' den GESAMTEN Praefix ersetzt: kommt
        es vor, haengt alles davor nicht mehr an einer Zaehlung.
        """
        for rang in RANGFOLGE:
            if any(s.rang == rang for s in self.schritte):
                return rang
        return ""

    @property
    def haengt_an_zaehlung(self) -> bool:
        """
        Ob nach dem letzten 'by_id' noch ein 'by_position' folgt.

        Das ist die eigentliche Frage: ein by_position VOR einem by_id ist
        bedeutungslos, weil der Praefix ersetzt wurde. Nur was danach kommt,
        haengt noch an der sibling-Zaehlung.
        """
        letzte_id = -1
        for nr, s in enumerate(self.schritte):
            if s.rang == RANG_ID:
                letzte_id = nr
        return any(s.rang == RANG_POSITION
                   for s in self.schritte[letzte_id + 1:])

    def als_dict(self) -> Dict[str, Any]:
        return {"expression": self.ausdruck, "resolves": self.traegt,
                "note": self.hinweis, "ranks": self.rangzaehlung,
                "best_rank": self.bester_rang,
                "depends_on_counting": self.haengt_an_zaehlung,
                "steps": [s.als_dict() for s in self.schritte]}


class XPathGenerator:
    """
    Erzeugt expressions fuer EINEN Baum. Je Baum einmal zu bauen: die
    Aufzaehlung der ids wird einmal ermittelt und dann fuer jeden Aufruf
    benutzt.
    """

    def __init__(self, wurzel) -> None:
        self._wurzel = wurzel
        #: Alle Elemente, FESTGEHALTEN - sonst kann lxml die Python-Huellen
        #: einsammeln und die Identitaetspruefung wird unzuverlaessig
        #: (derselbe Grund wie in anker_postbezug.PostBezugMesser).
        self._alle: List[Any] = [el for el in wurzel.iter()
                                 if isinstance(getattr(el, "tag", None), str)]
        #: id -> Anzahl. Nur Anzahl 1 qualifiziert fuer by_id.
        self._id_zahl: Dict[str, int] = {}
        for el in self._alle:
            kennung = (el.get("id") or "").strip()
            if kennung:
                self._id_zahl[kennung] = self._id_zahl.get(kennung, 0) + 1

    # ------------------------------------------------------------------
    @property
    def mehrfache_ids(self) -> Dict[str, int]:
        """
        Die ids, die mehr als einmal vergeben sind - ein Befund am Forum.

        Sie werden AUSGEWIESEN und nicht nur vermieden: eine mehrfach
        vergebene id verstoesst gegen die HTML-Spezifikation, und welche
        betroffen sind, gehoert in das Protokoll und nicht in eine Annahme.
        Offen war bis Build 766, ob include/poll.php und include/header0.php
        weitere enthalten.
        """
        return {k: n for k, n in sorted(self._id_zahl.items()) if n > 1}

    # ------------------------------------------------------------------
    def fuer(self, knoten) -> Erzeugnis:
        """
        Die expression fuer einen Knoten. Textknoten sind zugelassen: dann
        wird der Weg zum tragenden Element gebaut und '/text()[n]' angehaengt.
        """
        e = Erzeugnis()
        text_nummer = None
        ziel = knoten

        if not isinstance(getattr(knoten, "tag", None), str):
            eltern = self._traegerelement(knoten)
            if eltern is None:
                e.hinweis = "Textknoten ohne Elternelement"
                return e
            text_nummer = self._textnummer(eltern, knoten)
            if text_nummer is None:
                e.hinweis = "Textknoten im Elternelement nicht auffindbar"
                return e
            ziel = eltern

        kette = self._kette(ziel)
        if not kette:
            e.hinweis = "Knoten liegt nicht in diesem Baum"
            return e

        ausdruck = ""
        for element in kette:
            ausdruck, schritt = self._schritt(ausdruck, element)
            if schritt is None:
                e.hinweis = ("kein tragfaehiger Schritt fuer <%s>"
                             % self._marke(element))
                return e
            e.schritte.append(schritt)

        if text_nummer is not None:
            # DER LETZTE SCHRITT BLEIBT EINE ZAEHLUNG. Ein Textknoten traegt
            # weder id noch class - hier ist kein anderer Rang moeglich.
            ausdruck = "%s/text()[%d]" % (ausdruck, text_nummer)

        e.ausdruck = ausdruck
        e.traegt = self._trifft_ziel(ausdruck, knoten)
        if not e.traegt:
            e.hinweis = ("der erzeugte Ausdruck trifft den Zielknoten nicht - "
                         "das darf nicht vorkommen und ist ein Befund")
        return e

    # ------------------------------------------------------------------
    def _kette(self, ziel) -> List[Any]:
        """Von der Wurzel abwaerts bis zum Ziel, die Wurzel selbst ohne."""
        kette: List[Any] = []
        hier = ziel
        while hier is not None and hier is not self._wurzel:
            kette.append(hier)
            hier = hier.getparent()
        if hier is not self._wurzel:
            return []                          # gehoert nicht zu diesem Baum
        kette.reverse()
        return kette

    # ------------------------------------------------------------------
    def _schritt(self, praefix: str, element) -> Tuple[str, Optional[Schritt]]:
        """
        Einen Schritt bilden und ZURUECKPRUEFEN. Bei Misserfolg Rueckfall auf
        den naechstschwaecheren Rang.
        """
        marke = self._marke(element)
        rueckfaelle: List[str] = []

        for rang in RANGFOLGE:
            gebaut = self._bauen(rang, praefix, element, marke)
            if gebaut is None:
                rueckfaelle.append("%s nicht anwendbar" % rang)
                continue
            neuer_ausdruck, ersetzt = gebaut
            # DIE RUECKPRUEFUNG. Sie ist der Grund, warum hier ueberhaupt
            # ausgewertet wird: ein Schritt, der zwei Knoten trifft, sieht
            # gebaut genauso aus wie einer, der einen trifft.
            if self._trifft_ziel(neuer_ausdruck, element):
                teil = (neuer_ausdruck if ersetzt
                        else neuer_ausdruck[len(praefix):].lstrip("/"))
                return neuer_ausdruck, Schritt(
                    rang=rang, ausdruck=teil, marke=marke,
                    ersetzt_praefix=ersetzt, rueckfaelle=rueckfaelle)
            rueckfaelle.append("%s trifft nicht eindeutig" % rang)

        return praefix, None

    # ------------------------------------------------------------------
    def _bauen(self, rang: str, praefix: str, element,
               marke: str) -> Optional[Tuple[str, bool]]:
        """Rueckgabe: (vollstaendiger Ausdruck, ersetzt_praefix) oder None."""
        if rang == RANG_ID:
            kennung = (element.get("id") or "").strip()
            # DIE EINDEUTIGKEITSPRUEFUNG.
            if not kennung or self._id_zahl.get(kennung, 0) != 1:
                return None
            if "'" in kennung:                 # sonst bricht der Ausdruck
                return None
            return "//*[@id='%s']" % kennung, True

        if rang == RANG_KLASSE:
            klasse = self._klasse_waehlen(element)
            if klasse is None:
                return None
            # Der index wird ueber die GEFILTERTE Menge gezaehlt. 'div[20]'
            # und 'div[contains(...)][20]' sind NICHT dasselbe Element: das
            # eine ist das zwanzigste div-Kind, das andere das zwanzigste
            # div-Kind MIT dieser Klasse.
            nummer = self._index(element, marke, klasse)
            if nummer is None:
                return None
            teil = "%s[%s][%d]" % (marke, _xpath_klasse(klasse), nummer)
            return self._anhaengen(praefix, teil), False

        nummer = self._index(element, marke, None)
        if nummer is None:                     # pragma: no cover - defensiv
            return None
        return self._anhaengen(praefix, "%s[%d]" % (marke, nummer)), False

    # ------------------------------------------------------------------
    @staticmethod
    def _anhaengen(praefix: str, teil: str) -> str:
        return teil if not praefix else "%s/%s" % (praefix, teil)

    # ------------------------------------------------------------------
    @staticmethod
    def _klasse_waehlen(element) -> Optional[str]:
        """
        Eine brauchbare Klasse, oder None.

        Zustandsklassen bleiben ausgeschlossen: das Forum verwendet kein
        JavaScript, ein Wechsel findet also nicht statt - aber eine
        Zustandsklasse sagt nichts darueber aus, WO ein Element steht, und
        darum geht es hier.
        """
        for k in str(element.get("class") or "").split():
            if k and k not in ZUSTANDSKLASSEN and "'" not in k:
                return k
        return None

    # ------------------------------------------------------------------
    def _index(self, element, marke: str,
               klasse: Optional[str]) -> Optional[int]:
        """
        Die Position des Elements unter seinen siblings - gefiltert nach
        Tagname und, sofern angegeben, nach Klasse. XPath zaehlt ab 1.
        """
        eltern = element.getparent()
        if eltern is None:                     # pragma: no cover - defensiv
            return None
        nummer = 0
        for kind in eltern:
            if not isinstance(getattr(kind, "tag", None), str):
                continue
            if self._marke(kind) != marke:
                continue
            if klasse is not None:
                if klasse not in str(kind.get("class") or "").split():
                    continue
            nummer += 1
            if kind is element:
                return nummer
        return None

    # ------------------------------------------------------------------
    @staticmethod
    def _traegerelement(textknoten):
        """
        Das Element, in dessen Inhalt der Textknoten steht.

        NICHT dasselbe wie getparent(). lxml unterscheidet zwei Arten von
        Textknoten:

          <p>ERSTER<br/>ZWEITER</p>

          'ERSTER'  ist 'p.text'  -> is_text, getparent() liefert <p>
          'ZWEITER' ist 'br.tail' -> is_tail, getparent() liefert <br>

        Fuer XPath sind BEIDE Kinder von <p>: 'p/text()' liefert sie beide.
        Bei einem tail muss deshalb eine Ebene weiter aufgestiegen werden,
        sonst wird im falschen Element gesucht.

        Das ist kein Randfall: jeder Text nach einem <br> oder <img> im
        Beitrag ist ein tail, und davon stehen im Forum viele. Waechter XG10
        hat diesen Fehler gefunden.
        """
        if not hasattr(textknoten, "getparent"):
            return None
        eltern = textknoten.getparent()
        if eltern is None:
            return None
        if getattr(textknoten, "is_tail", False):
            return eltern.getparent()
        return eltern

    # ------------------------------------------------------------------
    @staticmethod
    def _textnummer(traeger, textknoten) -> Optional[int]:
        """
        Die Nummer eines Textknotens unter den Textknoten seines
        Traegerelements. XPath zaehlt ab 1.

        STRUKTURELL bestimmt, nicht durch Vergleich. Zwei Wege waeren
        naheliegend und beide untauglich:

          - ueber die Identitaet der lxml-Huellen: lxml legt fuer Textknoten
            bei JEDEM Zugriff neue Huellen an. 'kandidat is textknoten' ist
            deshalb praktisch immer falsch.
          - ueber den Inhalt: zwei Textknoten desselben Elements koennen
            denselben Wortlaut tragen. '<p>GLEICH<br/>GLEICH</p>' liefert
            dann fuer beide die Nummer 1.

        Die Reihenfolge der Textknoten eines Elements ist dagegen festgelegt:
        zuerst '.text' des Elements, danach je Kind dessen '.tail'. Daraus
        laesst sich die Nummer abzaehlen, ohne irgendetwas zu vergleichen.

        Waechter XG10 haelt beide Fehlwege fest.
        """
        if traeger is None:
            return None
        hat_eigenen_text = traeger.text is not None
        if getattr(textknoten, "is_text", False):
            return 1 if hat_eigenen_text else None
        if getattr(textknoten, "is_tail", False):
            vorlaeufer = textknoten.getparent()
            nummer = 1 if hat_eigenen_text else 0
            for kind in traeger:
                if not isinstance(getattr(kind, "tag", None), str):
                    continue
                if kind.tail is not None:
                    nummer += 1
                if kind is vorlaeufer:
                    return nummer
            return None
        # Huelle ohne is_text/is_tail - Rueckfall ueber den Inhalt.
        nummer = 0
        for kandidat in traeger.xpath("text()"):
            nummer += 1
            if str(kandidat) == str(textknoten):
                return nummer
        return None

    # ------------------------------------------------------------------
    def _trifft_ziel(self, ausdruck: str, ziel) -> bool:
        """
        Trifft der Ausdruck GENAU EINEN Knoten, und ist es der erwartete?

        Beides muss stimmen. Ein Ausdruck, der zwei Knoten trifft, ist nicht
        'fast richtig' - er ist mehrdeutig, und die Auswertung liefert dann
        stillschweigend den ersten.
        """
        try:
            treffer = self._wurzel.xpath(ausdruck)
        except Exception:                      # pragma: no cover - defensiv
            return False
        if len(treffer) != 1:
            return False
        einziger = treffer[0]
        if einziger is ziel:
            return True
        # Textknoten: die Identitaet der Huellen traegt nicht. Ueber
        # Elternelement und Nummer laesst es sich trotzdem entscheiden.
        if (not isinstance(getattr(ziel, "tag", None), str)
                and not isinstance(getattr(einziger, "tag", None), str)):
            e1 = XPathGenerator._traegerelement(ziel)
            e2 = XPathGenerator._traegerelement(einziger)
            return (e1 is not None and e1 is e2
                    and self._textnummer(e1, ziel)
                    == self._textnummer(e2, einziger))
        return False

    # ------------------------------------------------------------------
    @staticmethod
    def _marke(element) -> str:
        marke = getattr(element, "tag", "")
        if not isinstance(marke, str):         # pragma: no cover - defensiv
            return ""
        return marke.rsplit("}", 1)[-1].lower()

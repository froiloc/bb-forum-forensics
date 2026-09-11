# -*- coding: utf-8 -*-
# =============================================================================
# management/maintenance/wortlaut_abgleich.py
# IT-Forensisches Ermittlungswerkzeug - aiw_webserver
# BUILD 767
# =============================================================================
# ZWECK
#   Den gespeicherten 'selection_json.textContent' im page BLOB wiederfinden
#   und den Fund BELEGEN - nicht behaupten.
#
# WARUM DAS NOETIG IST
#   'AbsatzFinder._ueber_xpath()' (Z. 1075-1122) loest den Ausdruck auf,
#   bestimmt Block und Versaetze und gibt eine Fundstelle zurueck, OHNE den
#   dort stehenden Text je gegen 'textContent' zu halten. Die Wortlautsuche
#   laeuft nur als RUECKFALL, wenn der Ausdruck scheitert.
#
#   Loest ein Ausdruck also zufaellig auf, wird der dort stehende Text
#   uebernommen - ungeprueft. Gemessen im Lauf zu Build 766: 107 der 455
#   Annotationen tragen einen Ausdruck, der aufloest, aber an eine Stelle
#   zeigt, an der der markierte Wortlaut NICHT steht. Nur 6 davon brechen
#   strukturell; bei den uebrigen 101 liefert der Berichtsgenerator heute
#   stillschweigend den falschen Text.
#
# DIE DREI STUFEN (Festlegung Alex, 08.09.2026)
#   1. der BENANNTE Beitrag
#   2. die zehn naechsten - fuenf in jede Richtung in Dokumentreihenfolge
#   3. die ganze Seite
#
#   Begruendung fuer Stufe 2: Der Versatz zwischen dem ueber XPath
#   beschriebenen Beitrag und dem, aus dem das Zitat stammt, war in den
#   bisher von Alex geprueften Faellen gering - gemessen -4, -2, -2 und
#   zweimal -42. Fuenf in jede Richtung decken den haeufigen Fall ab, ohne
#   auf einer Seite mit 500 Beitraegen jedes Mal alles abzusuchen.
#
#   Die Stufe des Treffers ist SELBST EIN BEFUND: Stufe 1 heisst 'der Anker
#   redet ueber den richtigen Beitrag', Stufe 2 'er ist verrutscht', Stufe 3
#   'er zeigt woandershin'.
#
# WAS DIESER BUILD NICHT LEISTET
#   Die Rueckprobe erfolgt auf TEXTEBENE: der gefundene Abschnitt im
#   sichtbaren Text ist zeichengleich mit dem normalisierten 'textContent',
#   und er kommt im Fundbereich genau einmal vor. Die Rueckabbildung auf
#   einen DOM-Bereich - also der Nachweis, dass GENAU DIESE Knoten den
#   Wortlaut erzeugt haetten - gehoert zur Migration und nicht zur Messung.
#   Sie braucht die Versatzabbildung aus browser_wortlaut(), und die setzt
#   voraus, dass der Fundort bereits feststeht.
#
# WARTUNGSSTUFE
#   Rein lesend.
# =============================================================================
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from management.maintenance.post_bereiche import (
    LAGE_CONTENT, LAGE_FRAME, bereich_zu, beschreibung_zu)
from management.maintenance.wortlaut_norm import (
    normalisiere, sichtbarer_text, versteckte_klassen_im_baum)

#: Die Stufen, in der Reihenfolge, in der gesucht wird.
STUFE_BEITRAG = "named_post"
STUFE_NACHBARN = "neighbours"
STUFE_SEITE = "page"
STUFE_KEINE = ""
STUFEN = (STUFE_BEITRAG, STUFE_NACHBARN, STUFE_SEITE)

#: Wie viele Beitraege in JEDE Richtung Stufe 2 absucht.
NACHBARN_JE_RICHTUNG = 5

#: Ab welcher Laenge ein Wortlaut als zu kurz fuer eine verlaessliche Aussage
#: gilt. Kurze Zeichenketten treffen zufaellig - bei Hypothesis ist genau das
#: der dokumentierte Fehlerfall (Ticket 3919: Zitate aus einzelnen Satz- und
#: Leerraumzeichen). Der Wert VERWIRFT NICHTS, er kennzeichnet nur.
KURZ_AB = 12

#: Obergrenze fuer die Editierdistanz. Darueber wird nicht weitergerechnet -
#: die Zahl waere ohnehin ohne Aussage, und die Rechnung ist quadratisch.
DISTANZ_GRENZE = 400


@dataclass
class Fundort:
    """Ein Ort, an dem der Wortlaut steht."""
    post_id: Optional[int] = None
    stufe: str = STUFE_KEINE
    #: 'content', 'frame' oder '' - in welchem Bereich des Beitrags.
    lage: str = ""
    #: Wie oft der Wortlaut in diesem Beitrag vorkommt.
    vorkommen: int = 0

    def als_dict(self) -> Dict[str, Any]:
        return {"post_id": self.post_id, "stage": self.stufe,
                "area": self.lage, "occurrences": self.vorkommen}


@dataclass
class Teilstueck:
    """
    Ein Stueck einer aufgespaltenen Markierung - was aus EINEM Beitrag wuerde.

    'post_id' None heisst: diese Bloecke stehen in keinem Beitrag. Sie
    entfallen bei der Aufspaltung ersatzlos, und genau deshalb werden sie
    ausgewiesen.
    """
    post_id: Optional[int] = None
    block_von: int = 0
    block_bis: int = 0
    lage: str = ""
    zeichen: int = 0

    def als_dict(self) -> Dict[str, Any]:
        return {"post_id": self.post_id, "block_from": self.block_von,
                "block_to": self.block_bis, "area": self.lage,
                "chars": self.zeichen,
                "would_become": ("text range" if self.lage == LAGE_CONTENT
                                 and self.post_id is not None
                                 else ("whole post" if self.post_id is not None
                                       else "entfaellt"))}


@dataclass
class Abgleichbefund:
    """Das Ergebnis fuer EINE Annotation."""
    #: Der Wortlaut, normalisiert - so, wie gesucht wurde.
    wortlaut: str = ""
    #: Die Beitragsnummer, die der Anker benennt.
    benannter_beitrag: Optional[int] = None
    #: Alle Fundorte, in der Reihenfolge der Stufen.
    fundorte: List[Fundort] = field(default_factory=list)
    #: Auf welcher Stufe der ERSTE Treffer lag.
    stufe: str = STUFE_KEINE
    #: Steht der Wortlaut GENAU EINMAL an genau einem Ort?
    eindeutig: bool = False
    #: Kein exakter Treffer: der aehnlichste Beitrag und wie aehnlich.
    beste_aehnlichkeit: float = 0.0
    bester_beitrag: Optional[int] = None
    editierdistanz: Optional[int] = None
    #: Zu kurz fuer eine verlaessliche Aussage?
    zu_kurz: bool = False
    #: Was der Ausschluss der versteckten Elemente bewirkt hat.
    versteckt_wirksam: bool = False
    #: BUILD 768 - der Treffer kam erst blockweise zustande.
    blockweise: bool = False
    #: In wie viele Bloecke der Wortlaut zerfaellt.
    bloecke: int = 0
    #: BUILD 768 - die Aufspaltung ueber mehrere Beitraege.
    teilstuecke: List[Teilstueck] = field(default_factory=list)
    #: BUILD 769 - die Beitraege, die zwischen den Ankerpunkten liegen.
    kandidaten: List[int] = field(default_factory=list)
    hinweis: str = ""

    @property
    def gefunden(self) -> bool:
        return bool(self.fundorte)

    @property
    def im_benannten_beitrag(self) -> bool:
        return self.stufe == STUFE_BEITRAG

    def als_dict(self) -> Dict[str, Any]:
        return {
            "wording_normalised": self.wortlaut[:200],
            "wording_length": len(self.wortlaut),
            "named_post": self.benannter_beitrag,
            "found": self.gefunden,
            "stage": self.stufe,
            "unique": self.eindeutig,
            "locations": [f.als_dict() for f in self.fundorte],
            "best_similarity": round(self.beste_aehnlichkeit, 4),
            "best_post": self.bester_beitrag,
            "edit_distance": self.editierdistanz,
            "too_short": self.zu_kurz,
            "hidden_mattered": self.versteckt_wirksam,
            "blockwise": self.blockweise,
            "blocks": self.bloecke,
            "split": [s.als_dict() for s in self.teilstuecke],
            "split_posts": [s.post_id for s in self.teilstuecke
                            if s.post_id is not None],
            "candidates": list(self.kandidaten),
            "split_post_count": len({s.post_id for s in self.teilstuecke
                                     if s.post_id is not None}),
            "split_sections": len(self.teilstuecke),
            "chars_outside": sum(s.zeichen for s in self.teilstuecke
                                 if s.post_id is None),
            "split_complete": bool(self.teilstuecke) and not any(
                s.post_id is None for s in self.teilstuecke),
            "note": self.hinweis,
        }


def editierdistanz(a: str, b: str,
                   grenze: int = DISTANZ_GRENZE) -> Optional[int]:
    """
    Levenshtein-Distanz, mit Obergrenze.

    Eigene Umsetzung, weil weder 'rapidfuzz' noch 'Levenshtein' im
    Zielsystem liegen und eine neue Abhaengigkeit fuer eine Migration, die
    einmal laeuft, nicht angemessen waere. Zwei Zeilen genuegen: die Rechnung
    braucht nur die vorige Zeile.

    None, wenn eine der Ketten laenger als die Grenze ist - dann waere die
    Zahl ohne Aussage und die Rechnung quadratisch teuer.
    """
    if len(a) > grenze or len(b) > grenze:
        return None
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    vorige = list(range(len(b) + 1))
    for i, za in enumerate(a, 1):
        aktuelle = [i]
        for j, zb in enumerate(b, 1):
            aktuelle.append(min(
                vorige[j] + 1,            # loeschen
                aktuelle[j - 1] + 1,      # einfuegen
                vorige[j - 1] + (za != zb),  # ersetzen
            ))
        vorige = aktuelle
    return vorige[-1]


class WortlautAbgleich:
    """
    Der Abgleich fuer EINE Seite. Je Seite einmal zu bauen: die Beitragstexte
    werden einmal entnommen und normalisiert und dann fuer jede Annotation
    dieser Seite benutzt.
    """

    def __init__(self, wurzel, seitenart: str = "") -> None:
        from report_render.absatz_finder import AbsatzFinder
        self._AF = AbsatzFinder
        self._wurzel = wurzel
        self._seitenart = str(seitenart or "")
        self._beschreibung = beschreibung_zu(self._seitenart)

        #: Die container in Dokumentreihenfolge, dedupliziert je Nummer.
        self._container: List[Any] = AbsatzFinder._container_der_seite(wurzel)
        self._nummern: List[int] = []
        self._text_je_nummer: Dict[int, str] = {}
        self._inhalt_je_nummer: Dict[int, str] = {}
        #: Derselbe Text OHNE Ausschluss der versteckten Elemente - nur zum
        #: Vergleich, damit die Wirkung des Ausschlusses messbar ist.
        self._text_mit_versteckt: Dict[int, str] = {}

        for el in self._container:
            nummer = AbsatzFinder.beitragsnummer(el)
            if nummer is None:
                continue
            self._nummern.append(nummer)
            self._text_je_nummer[nummer] = normalisiere(sichtbarer_text(el))
            self._inhalt_je_nummer[nummer] = normalisiere(
                self._inhaltstext(el))
            roh, _versaetze = AbsatzFinder.browser_wortlaut(el) \
                if hasattr(AbsatzFinder, "browser_wortlaut") \
                else (None, None)
            if roh is None:
                from report_render.absatz_finder import browser_wortlaut
                roh, _versaetze = browser_wortlaut(el)
            self._text_mit_versteckt[nummer] = normalisiere(roh)

        self._platz: Dict[int, int] = {
            n: i for i, n in enumerate(self._nummern)}

        # BUILD 769 - die Dokumentreihenfolge JEDES Knotens. Sie wird
        # gebraucht, um aus zwei Ankerpunkten die Menge der dazwischen
        # liegenden Beitraege zu bestimmen.
        self._ordnung: Dict[Any, int] = {}
        for i, el in enumerate(wurzel.iter()):
            if isinstance(getattr(el, "tag", None), str):
                self._ordnung[el] = i
        #: Je Beitrag der Bereich (erster Index, letzter Index) im Baum.
        self._bereich_je_nummer: Dict[int, Tuple[int, int]] = {}
        for el in self._container:
            nummer = AbsatzFinder.beitragsnummer(el)
            if nummer is None:
                continue
            indizes = [self._ordnung[k] for k in el.iter()
                       if isinstance(getattr(k, "tag", None), str)
                       and k in self._ordnung]
            if indizes:
                self._bereich_je_nummer[nummer] = (min(indizes), max(indizes))

    # ------------------------------------------------------------------
    @property
    def beitragszahl(self) -> int:
        return len(self._nummern)

    @property
    def versteckte_klassen(self) -> Dict[str, int]:
        """Was an versteckten Elementen auf dieser Seite steht - ein Befund."""
        return versteckte_klassen_im_baum(self._wurzel)

    # ------------------------------------------------------------------
    def _inhaltstext(self, container) -> str:
        """
        Nur der INHALTSBEREICH eines Beitrags, ohne Rahmen.

        Leer, wenn die Seitenart keinen Inhaltsbereich kennt - dann ist die
        Lage eines Treffers nicht bestimmbar, und das wird gesagt statt
        geraten.
        """
        bereich = bereich_zu(self._beschreibung, container)
        if bereich is None:
            return ""
        for el in container.iter():
            if not isinstance(getattr(el, "tag", None), str):
                continue
            if bereich.anker.trifft(el) and self._vorfahre_ok(el, bereich,
                                                              container):
                return sichtbarer_text(el)
        return ""

    @staticmethod
    def _vorfahre_ok(anker, bereich, container) -> bool:
        if bereich.vorfahre is None:
            return True
        hier = anker.getparent()
        while hier is not None:
            if bereich.vorfahre.trifft(hier):
                return True
            if hier is container:
                return False
            hier = hier.getparent()
        return False

    # ------------------------------------------------------------------
    def _nachbarn(self, nummer: Optional[int]) -> List[int]:
        """
        Die zehn naechsten Beitraege - fuenf in jede Richtung, in
        Dokumentreihenfolge. Der benannte Beitrag selbst ist nicht dabei.
        """
        if nummer is None or nummer not in self._platz:
            return []
        i = self._platz[nummer]
        von = max(0, i - NACHBARN_JE_RICHTUNG)
        bis = min(len(self._nummern), i + NACHBARN_JE_RICHTUNG + 1)
        return [n for n in self._nummern[von:bis] if n != nummer]

    # ------------------------------------------------------------------
    def _suche_in(self, nummern: List[int], wortlaut: str,
                  stufe: str) -> List[Fundort]:
        aus: List[Fundort] = []
        for nummer in nummern:
            text = self._text_je_nummer.get(nummer, "")
            if not text or wortlaut not in text:
                continue
            inhalt = self._inhalt_je_nummer.get(nummer, "")
            lage = LAGE_CONTENT if (inhalt and wortlaut in inhalt) \
                else (LAGE_FRAME if inhalt else "")
            aus.append(Fundort(post_id=nummer, stufe=stufe, lage=lage,
                               vorkommen=text.count(wortlaut)))
        return aus

    # ------------------------------------------------------------------
    def pruefe(self, text_content: str,
               benannter_beitrag: Optional[int],
               start_knoten=None, end_knoten=None) -> Abgleichbefund:
        """
        Der dreistufige Abgleich fuer EINE Annotation.

        Gesucht wird immer der VOLLSTAENDIGE normalisierte Wortlaut als
        Teilkette. Bleibt er ohne Treffer, wird die Aehnlichkeit zum
        aehnlichsten Beitrag bestimmt - als Zahl, nicht als Entscheidung. Ob
        eine Aehnlichkeit ausreicht, legt Alex nach der Messung fest.
        """
        b = Abgleichbefund(benannter_beitrag=benannter_beitrag)
        b.wortlaut = normalisiere(text_content)
        if not b.wortlaut:
            b.hinweis = "kein Wortlaut gespeichert - nicht pruefbar"
            return b
        b.zu_kurz = len(b.wortlaut) < KURZ_AB

        # ---- Stufe 1: der benannte Beitrag ------------------------------
        if benannter_beitrag is not None and benannter_beitrag in self._platz:
            b.fundorte = self._suche_in([benannter_beitrag], b.wortlaut,
                                        STUFE_BEITRAG)
        elif benannter_beitrag is not None:
            b.hinweis = ("der benannte Beitrag %d steht nicht in diesem Abzug"
                         % benannter_beitrag)

        # ---- Stufe 2: die zehn naechsten --------------------------------
        if not b.fundorte:
            b.fundorte = self._suche_in(self._nachbarn(benannter_beitrag),
                                        b.wortlaut, STUFE_NACHBARN)

        # ---- Stufe 3: die ganze Seite -----------------------------------
        if not b.fundorte:
            schon = set(self._nachbarn(benannter_beitrag))
            if benannter_beitrag is not None:
                schon.add(benannter_beitrag)
            uebrige = [n for n in self._nummern if n not in schon]
            b.fundorte = self._suche_in(uebrige, b.wortlaut, STUFE_SEITE)

        if b.fundorte:
            b.stufe = b.fundorte[0].stufe
            b.eindeutig = (len(b.fundorte) == 1
                           and b.fundorte[0].vorkommen == 1)
            # Hat der Ausschluss der versteckten Elemente den Treffer erst
            # ermoeglicht? Das ist der gemessene Zensurfall.
            for f in b.fundorte:
                mit = self._text_mit_versteckt.get(f.post_id, "")
                ohne = self._text_je_nummer.get(f.post_id, "")
                if mit != ohne:
                    b.versteckt_wirksam = True
                    break
            return b

        # ---- BLOCKWEISE, bevor die Aehnlichkeit bemueht wird ------------
        #
        # Erst hier, nicht vorher: der Treffer als EINE Zeichenkette ist die
        # staerkere Aussage. Wer blockweise trifft, hat den Wortlaut zwar
        # vollstaendig im Beitrag, aber mit Unterbrechungen - das ist der
        # Regelfall bei 'ganzer Post als text-range markiert'.
        bloecke = self._bloecke(text_content)
        if len(bloecke) > 1:
            for nummern, stufe in (
                    ([benannter_beitrag] if benannter_beitrag in self._platz
                     else [], STUFE_BEITRAG),
                    (self._nachbarn(benannter_beitrag), STUFE_NACHBARN),
                    (self._nummern, STUFE_SEITE)):
                if not nummern:
                    continue
                gefunden = self._blockweise_in(nummern, bloecke, stufe)
                if gefunden:
                    b.fundorte = gefunden
                    b.stufe = gefunden[0].stufe
                    b.blockweise = True
                    b.bloecke = len(bloecke)
                    b.eindeutig = len(gefunden) == 1
                    return b

        # ---- AUFSPALTUNG ueber mehrere Beitraege ------------------------
        #
        # Erst wenn kein EINZELNER Beitrag den Wortlaut traegt. Dann ist die
        # Frage nicht mehr 'wo steht er', sondern 'in welche Beitraege
        # zerfaellt er' - und genau das muss belegt sein, bevor die Migration
        # aufspalten darf.
        b.bloecke = len(bloecke)
        if bloecke:
            # DIE SCHRANKE. Ohne beide Ankerpunkte gibt es keine Aufspaltung -
            # sie waere geraten (Festlegung Alex, 08.09.2026).
            kandidaten = self.kandidaten_zwischen(start_knoten, end_knoten)
            b.kandidaten = list(kandidaten)
            if not kandidaten:
                b.hinweis = (
                    "keine Aufspaltung: die Spanne zwischen den Ankerpunkten "
                    "ist nicht bestimmbar%s"
                    % ("" if (start_knoten is not None
                              and end_knoten is not None)
                       else " - ein Ankerpunkt loest nicht auf"))
                self._aehnlichkeit(b)
                return b
            b.teilstuecke = self.aufspalten(bloecke, kandidaten)
            # GEZAEHLT WERDEN BEITRAEGE, NICHT ABSCHNITTE. Ein Beitrag kann
            # mehrfach vorkommen, wenn zwischen seinen Bloecken etwas liegt,
            # das in keinem Kandidaten steht. 'ueber 19 Beitraege verteilt'
            # waere dann falsch - es sind zwei, mit neunzehn Abschnitten.
            beitraege = sorted({s.post_id for s in b.teilstuecke
                                if s.post_id is not None})
            aussen = [s for s in b.teilstuecke if s.post_id is None]
            if beitraege:
                b.hinweis = (
                    "ueber %d %s verteilt, in %d Abschnitten "
                    "(Spanne: %d Kandidaten)%s"
                    % (len(beitraege),
                       "Beitrag" if len(beitraege) == 1 else "Beitraege",
                       len(b.teilstuecke) - len(aussen), len(kandidaten),
                       "" if not aussen
                       else "; dazu %d Abschnitt%s mit %d Zeichen ausserhalb "
                            "jedes Beitrags" % (
                                len(aussen), "" if len(aussen) == 1 else "e",
                                sum(s.zeichen for s in aussen))))
                return b

        self._aehnlichkeit(b)
        return b

    # ------------------------------------------------------------------
    def _bloecke(self, text_content: str) -> List[str]:
        """
        Den gespeicherten Wortlaut in Bloecke zerlegen - an den Umbruechen,
        die der Browser gesetzt hat.

        WARUM DAS NOETIG IST (Befund aus dem Lauf zu Build 767): Von 30 nicht
        gefundenen Wortlauten waren 24 vom Typ 'ganzer Post als text-range
        markiert'. Dort umfasst der Wortlaut RAHMEN UND INHALT - Verfasser,
        Zeitstempel, Betreff, Beitragstext, Funktionsleiste - und zwar in der
        Reihenfolge, in der der Browser sie sichtbar aneinanderreiht. Diese
        Reihenfolge muss NICHT der Dokumentreihenfolge des Abzugs
        entsprechen, und die Umbrueche dazwischen sind vom Browser eingefuegt
        und stehen im Abzug nicht.

        Eine Suche nach dem Wortlaut ALS EINER Zeichenkette kann das nur
        verfehlen. Die Aehnlichkeiten von 0,79 bis 0,99 waren deshalb kein
        Hinweis auf eine Textabweichung, sondern auf eine falsche Suchmenge.

        Zerlegt wird VOR der Normalisierung: diese faltet Umbrueche zu
        Leerzeichen und wuerde die Blockgrenzen gerade tilgen.
        """
        roh = str(text_content or "")
        bloecke = [normalisiere(z) for z in roh.split("\n")]
        return [z for z in bloecke if z]

    # ------------------------------------------------------------------
    def _blockweise_in(self, nummern: List[str], bloecke: List[str],
                       stufe: str) -> List[Fundort]:
        """
        Stehen ALLE Bloecke in einem Beitrag, und zwar in Reihenfolge?

        'in Reihenfolge' heisst: jeder Block kommt im Beitragstext hinter dem
        vorigen vor. Ohne diese Bedingung waere jede Ansammlung derselben
        Woerter ein Treffer - und der Rahmen eines Beitrags wiederholt sich
        auf einer Seite hundertfach.
        """
        aus: List[Fundort] = []
        for nummer in nummern:
            text = self._text_je_nummer.get(nummer, "")
            if not text:
                continue
            stelle = 0
            vollstaendig = True
            for block in bloecke:
                treffer = text.find(block, stelle)
                if treffer < 0:
                    vollstaendig = False
                    break
                stelle = treffer + len(block)
            if not vollstaendig:
                continue
            inhalt = self._inhalt_je_nummer.get(nummer, "")
            # Bei einem blockweisen Treffer sagt die Lage, ob ALLE Bloecke im
            # Inhaltsbereich liegen. Liegt auch nur einer im Rahmen, ist es
            # nach der Regel aus Build 764 ein 'whole post'.
            lage = LAGE_CONTENT if (inhalt and all(bl in inhalt
                                                   for bl in bloecke)) \
                else (LAGE_FRAME if inhalt else "")
            aus.append(Fundort(post_id=nummer, stufe=stufe, lage=lage,
                               vorkommen=1))
        return aus

    # ------------------------------------------------------------------
    def kandidaten_zwischen(self, start_knoten, end_knoten) -> List[int]:
        """
        DIE STRUKTURELLE SCHRANKE. Welche Beitraege koennen von einer
        Markierung ueberhaupt umfasst sein?

        Antwort: genau die, deren Bereich im Baum die Spanne zwischen den
        beiden Ankerpunkten beruehrt. Nicht mehr, nicht weniger.

        WARUM DAS NOETIG IST - der Fall 583231/6, gemessen am 08.09.2026:
        Die Verteilung ohne Schranke sucht JEDEN Block auf der GANZEN Seite
        und wandert dabei vorwaerts. Kurze Bloecke - einer mit einem Zeichen,
        einer mit drei - treffen in spaeteren Beitraegen zufaellig, und jeder
        Zufallstreffer schiebt den Suchzeiger weiter. So wurden aus ZWEI
        Beitraegen neun. Das Verfahren driftete.

        EINE MINDESTLAENGE JE BLOCK WAERE DER FALSCHE WEG (Festlegung Alex,
        08.09.2026): sie daempft die Drift, beseitigt sie nicht, und sie
        waere eine statistische Grenze fuer ein Problem, das STRUKTURELL
        bestimmt ist. Der Endanker zeigt auf 'article[2]' von 70 - die
        Beitraege 3 bis 70 KOENNEN nicht umfasst sein, und das ist keine
        Schaetzung.

        Leere Liste, wenn ein Ankerpunkt fehlt. Dann gibt es KEINE
        Aufspaltung, sondern eine Vorlage: eine Aufspaltung ohne Schranke
        waere geraten, und eine geratene Zuordnung ist schlimmer als keine.
        """
        if start_knoten is None or end_knoten is None:
            return []
        von = self._index_von(start_knoten)
        bis = self._index_von(end_knoten)
        if von is None or bis is None:
            return []
        if von > bis:
            von, bis = bis, von
        aus: List[int] = []
        for nummer in self._nummern:
            bereich = self._bereich_je_nummer.get(nummer)
            if bereich is None:
                continue
            # Beruehrt der Beitrag die Spanne?
            if bereich[0] <= bis and bereich[1] >= von:
                aus.append(nummer)
        return aus

    # ------------------------------------------------------------------
    def _index_von(self, knoten) -> Optional[int]:
        """Die Dokumentreihenfolge eines Knotens - auch eines Textknotens."""
        el = knoten
        if not isinstance(getattr(knoten, "tag", None), str):
            el = knoten.getparent() if hasattr(knoten, "getparent") else None
            if el is not None and getattr(knoten, "is_tail", False):
                el = el.getparent()
        return self._ordnung.get(el)

    # ------------------------------------------------------------------
    def aufspalten(self, bloecke: List[str],
                   kandidaten: Optional[List[int]] = None) -> List[Teilstueck]:
        """
        DIE AUFSPALTUNG. Eine Markierung, die MEHRERE Beitraege umfasst, auf
        die einzelnen Beitraege verteilen - so, wie die Migration sie spaeter
        in je einen eigenen Datensatz zerlegt (Regelkatalog G4 und 1.4).

        DAS IST DER KERN. Festzustellen, dass eine Markierung ueber mehrere
        Beitraege laeuft, ist keine Leistung - das wussten wir. Gebraucht
        wird die Auskunft, WELCHE Beitraege es sind und WAS aus jedem von
        ihnen wuerde. Erst wenn das je Beitrag belegt ist, darf die Migration
        aufspalten.

        Verfahren: Die Bloecke werden in Dokumentreihenfolge ueber die
        Beitraege verteilt. Jeder Beitrag nimmt so viele aufeinanderfolgende
        Bloecke auf, wie er in Reihenfolge traegt; danach geht es beim
        naechsten Beitrag weiter, der den naechsten offenen Block traegt.

        Bloecke, die in KEINEM Beitrag stehen, werden als 'ausserhalb'
        gefuehrt und nicht unterschlagen. Sie sind der Teil der Markierung,
        der zwischen den Beitraegen lag - und der bei der Aufspaltung
        ersatzlos entfaellt (Festlegung Alex, 08.09.2026). Dass er entfaellt,
        ist zu SEHEN und nicht zu erschliessen.
        """
        # JE BLOCK der naechste Beitrag, der ihn traegt - nicht je Beitrag
        # die naechsten Bloecke. Der Unterschied ist wesentlich: liegt der
        # ERSTE Block ausserhalb jedes Beitrags (etwa in der Fusszeile oder
        # zwischen zwei Beitraegen), kaeme eine beitragsweise Schleife gar
        # nicht erst in Gang und wuerde die ganze Markierung als 'ausserhalb'
        # abtun. Gemessen an einer Probe mit vorangestellter Fusszeile.
        # BUILD 769: Gesucht wird NUR in den Kandidaten. Ohne Schranke
        # driftet das Verfahren (siehe kandidaten_zwischen).
        reihe = (list(kandidaten) if kandidaten is not None
                 else list(self._nummern))
        zuordnung: List[Optional[int]] = []
        pos_beitrag = 0          # ab welchem Beitrag weitergesucht wird
        stelle_im_text = 0       # Fundstelle im aktuellen Beitrag
        for block in bloecke:
            gefunden = None
            for k in range(pos_beitrag, len(reihe)):
                nummer = reihe[k]
                text = self._text_je_nummer.get(nummer, "")
                if not text:
                    continue
                ab = stelle_im_text if k == pos_beitrag else 0
                treffer = text.find(block, ab)
                if treffer < 0:
                    continue
                gefunden = nummer
                pos_beitrag = k
                stelle_im_text = treffer + len(block)
                break
            zuordnung.append(gefunden)

        # Aufeinanderfolgende Bloecke mit derselben Zuordnung zusammenfassen.
        aus: List[Teilstueck] = []
        lauf_von = 0
        for i in range(1, len(zuordnung) + 1):
            if i < len(zuordnung) and zuordnung[i] == zuordnung[lauf_von]:
                continue
            nummer = zuordnung[lauf_von]
            indizes = list(range(lauf_von, i))
            if nummer is None:
                lage = "outside"
            else:
                inhalt = self._inhalt_je_nummer.get(nummer, "")
                lage = LAGE_CONTENT if (inhalt and all(
                    bloecke[x] in inhalt for x in indizes)) \
                    else (LAGE_FRAME if inhalt else "")
            aus.append(Teilstueck(
                post_id=nummer, block_von=indizes[0], block_bis=indizes[-1],
                lage=lage,
                zeichen=sum(len(bloecke[x]) for x in indizes)))
            lauf_von = i
        return aus

    # ------------------------------------------------------------------
    def _aehnlichkeit(self, b: Abgleichbefund) -> None:
        """
        Der aehnlichste Beitrag und wie aehnlich - als ZAHL, nicht als
        Entscheidung.

        Verglichen wird der Wortlaut gegen den Abschnitt des Beitragstextes,
        der ihm am naechsten kommt. 'SequenceMatcher' liefert dafuer den
        laengsten gemeinsamen Block; um ihn herum wird ein Fenster von der
        Laenge des Wortlauts genommen. Ohne dieses Fenster verglichen wir
        einen kurzen Wortlaut gegen einen langen Beitrag, und das Ergebnis
        waere nur ein Laengenverhaeltnis.
        """
        bester = 0.0
        beste_nummer = None
        bester_ausschnitt = ""
        for nummer, text in self._text_je_nummer.items():
            if not text:
                continue
            m = difflib.SequenceMatcher(None, text, b.wortlaut)
            block = m.find_longest_match(0, len(text), 0, len(b.wortlaut))
            if block.size == 0:
                continue
            mitte = block.a + block.size // 2
            halb = max(1, len(b.wortlaut) // 2)
            von = max(0, mitte - halb)
            ausschnitt = text[von:von + len(b.wortlaut)]
            wert = difflib.SequenceMatcher(None, ausschnitt,
                                           b.wortlaut).ratio()
            if wert > bester:
                bester, beste_nummer, bester_ausschnitt = (wert, nummer,
                                                           ausschnitt)
        b.beste_aehnlichkeit = bester
        b.bester_beitrag = beste_nummer
        if bester_ausschnitt:
            b.editierdistanz = editierdistanz(bester_ausschnitt, b.wortlaut)
        # Der Befund ueber den Treffer wird IMMER genannt, auch wenn schon
        # ein Hinweis zur Aufspaltung steht. Zwei Aussagen, zwei Saetze -
        # sonst verdeckt die eine die andere.
        kein_treffer = ("kein exakter Treffer auf keiner der drei Stufen"
                        if self._nummern
                        else "die Seite traegt keine Beitraege")
        b.hinweis = ("%s; %s" % (kein_treffer, b.hinweis) if b.hinweis
                     else kein_treffer)

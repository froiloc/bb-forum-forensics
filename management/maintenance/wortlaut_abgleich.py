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
               benannter_beitrag: Optional[int]) -> Abgleichbefund:
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

        # ---- kein Treffer: Aehnlichkeit bestimmen -----------------------
        self._aehnlichkeit(b)
        return b

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
        if not b.hinweis:
            b.hinweis = ("kein exakter Treffer auf keiner der drei Stufen"
                         if self._nummern
                         else "die Seite traegt keine Beitraege")

# -*- coding: utf-8 -*-
# =============================================================================
# management/maintenance/annotation_pruefung.py
# IT-Forensisches Ermittlungswerkzeug - Verifikation einer Annotation
# =============================================================================
# Zweck:
#   FUER EINE ANNOTATION FESTSTELLEN, OB SIE SICH IM GESICHERTEN SEITENABZUG
#   BESTAETIGEN LAESST - und mit welcher BELEGKRAFT.
#
#   Diese Datei ist der Vorgang (Grundregel 10). Sie wird von zwei Stellen
#   benutzt: tools/annotationen_verifizieren.py (Gesamtlauf) und
#   management/maintenance/anker_diagnose.py (Einzelfall). DASS ES NUR EINE
#   GIBT, IST DER ZWECK: zwei Pruefungen derselben Frage waeren binnen zweier
#   Builds auseinandergelaufen, und dann haette man zwei Antworten und keine.
#
# ── DER BEFUND, DER ZU DIESER DATEI GEFUEHRT HAT (31.08.2026) ────────────────
#
#   Alex' Frage: "Sind in der anker_diagnose.py die Anker mit dem Text
#   verglichen worden? Oder war das Skript zufrieden, wenn es die Position
#   gefunden hat?"
#
#   ES WAR ZUFRIEDEN. '_anker_pruefen()' prueft ausschliesslich, ob die
#   verlangte Position existiert - 'gibt es den n-ten Textknoten', 'gibt es
#   das n-te <div>'. Der markierte Wortlaut wird in der ganzen Datei nie
#   gelesen (gemessen: null Vorkommen von 'wortlaut' und 'textContent').
#   Dasselbe gilt fuer den Zweig 'Weg=anker' des Nachtrags. Die Kreuzprobe
#   aus Build 751 lief NUR im Zweig des teilweise aufgeloesten Ausdrucks -
#   also ausgerechnet nur dort, wo der Ausdruck schon gestolpert war.
#
#   Gemessen am Ermittlungsfenster (M1b, Chrome 151, 31.08.2026): auf
#   '/forum/pmsnew.php?mdl=topic&tid=64200' liefern von 46 Annotationen
#   SIEBEN einen Bereich, dessen Text dem gespeicherten Wortlaut entspricht.
#   Die bisherige Pruefung haette dort rund 31 als "traegt" gemeldet.
#
# ── DIE BELEGKRAFT WIRD BENANNT, NICHT VERRECHNET ────────────────────────────
#
#   Es gibt nicht "richtig" und "falsch", sondern sechs unterscheidbare
#   Lagen. Sie zu einer Note zusammenzuziehen hiesse, dem Leser die
#   Unterscheidung abzunehmen, auf die es vor Gericht ankommt:
#
#     BESTAETIGT        Position vorhanden UND der Text an der benannten
#                       Stelle ist der markierte Wortlaut. Position und
#                       Inhalt sagen dasselbe - der starke Fall.
#     BEITRAG_BELEGT    Die Fundstelle laesst sich nicht bestaetigen (Versatz
#                       nicht anwendbar oder Text abweichend), aber der
#                       Wortlaut steht im Abzug in GENAU EINEM Beitrag, und
#                       das ist der benannte. Der Beitrag steht fest, die
#                       Stelle darin nicht.
#     WIDERLEGT         Der Wortlaut steht eindeutig in einem ANDEREN
#                       Beitrag als dem benannten. Hier ist nichts zu retten
#                       und nichts einzutragen.
#     NUR_WORTLAUT      Der Ausdruck traegt nicht, aber der Wortlaut ist auf
#                       der Seite eindeutig. Der Beitrag steht ueber den
#                       Inhalt fest.
#     UNKLAR            Der Wortlaut kommt in mehreren Beitraegen vor oder in
#                       keinem. Nichts ist zu entscheiden - VON HAND ANSEHEN.
#     UNPRUEFBAR        Kein Ausdruck, kein Abzug, kein brauchbarer Wortlaut.
#
#   EIN 'WIDERLEGT' IST KEIN BEWEIS, DASS DER ERMITTLER SICH GEIRRT HAT.
#   Der Wortlaut kann ueber eine Beitragsgrenze hinweg markiert, in einer
#   Uebersetzung erhoben oder anders gefaltet worden sein. 'WIDERLEGT' heisst
#   "die Angabe des Ausdrucks wird vom Inhalt nicht getragen" - nicht mehr.
#
# ── WAS DIESE PRUEFUNG NICHT KANN ────────────────────────────────────────────
#
#   Das lxml-Baummodell kennt KEINE benachbarten Textknoten - Text ist dort
#   '.text' bzw. '.tail' eines Elements. Der Browser kann benachbarte
#   Textknoten haben (nach splitText, nach dem Entfernen eines Elements ohne
#   normalize()). Wo das eintritt, zaehlt 'text()[n]' im Browser anders als
#   hier, und die Textprobe schlaegt fehl, ohne dass am Abzug etwas fehlte.
#   DESHALB IST EIN FEHLSCHLAG DER TEXTPROBE ALLEIN KEIN URTEIL - er fuehrt
#   auf die Wortlautprobe und nicht auf 'WIDERLEGT'.
#
# Version: 0.8.754 - Build 754
# =============================================================================

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

#: Die sechs Lagen. Siehe Kopf - sie werden benannt und nicht verrechnet.
URTEIL_BESTAETIGT = "BESTAETIGT"
URTEIL_BEITRAG_BELEGT = "BEITRAG_BELEGT"
URTEIL_WIDERLEGT = "WIDERLEGT"
URTEIL_NUR_WORTLAUT = "NUR_WORTLAUT"
URTEIL_UNKLAR = "UNKLAR"
URTEIL_UNPRUEFBAR = "UNPRUEFBAR"

#: Reihenfolge fuer Zaehlungen - von der staerksten Lage zur schwaechsten.
URTEILE = (URTEIL_BESTAETIGT, URTEIL_BEITRAG_BELEGT, URTEIL_NUR_WORTLAUT,
           URTEIL_UNKLAR, URTEIL_WIDERLEGT, URTEIL_UNPRUEFBAR)

#: Ergebnis der Textprobe an der benannten Stelle.
TEXT_GLEICH = "gleich"
TEXT_ABWEICHEND = "abweichend"
TEXT_VERSATZ_UNGUELTIG = "versatz_jenseits_der_laenge"
TEXT_VERSATZ_WIDERSINNIG = "versatz_ende_vor_anfang"
TEXT_NICHT_ANWENDBAR = "nicht_anwendbar"

#: Ein Schritt eines XPath-Ausdrucks, wie toolbar.js ihn erzeugt.
_SCHRITT = re.compile(r"^(text\(\)|[A-Za-z][\w:-]*)\[(\d+)\]$")

#: Beitragskennung - aeussere 'p<Nr>' und innere 'pp<Nr>' meinen denselben.
_POST_KENNUNG = re.compile(r"^pp?(\d+)$")


def falte(text: str) -> str:
    """Leerraum vereinheitlichen - Zeilenumbruch und Einruecken der
    Seitenvorlage duerfen eine Textprobe nicht scheitern lassen."""
    return re.sub(r"\s+", " ", str(text or "")).strip()


@dataclass
class Pruefbefund:
    """Das Ergebnis der Verifikation EINER Annotation."""
    annotation_id: Any = None
    seite: str = ""
    urteil: str = URTEIL_UNPRUEFBAR
    #: Loest der Ausdruck bis zum letzten Schritt auf?
    position_vorhanden: bool = False
    #: Wie weit er gekommen ist, und woran er bricht.
    schritte_gegangen: int = 0
    schritte_gesamt: int = 0
    bruch_schritt: str = ""
    #: Der Beitrag, den der Ausdruck benennt (None, wenn keiner).
    beitrag_anker: Optional[int] = None
    #: Die Beitraege, in deren Klartext der markierte Wortlaut steht.
    beitraege_wortlaut: List[int] = field(default_factory=list)
    #: Ergebnis der Textprobe am benannten Textknoten.
    textprobe: str = TEXT_NICHT_ANWENDBAR
    #: Was dort tatsaechlich steht - GEKUERZT, der Wortlaut traegt Fallbezug.
    gefunden_kurz: str = ""
    #: Klartext zur Lage.
    bemerkung: str = ""

    @property
    def beitrag(self) -> Optional[int]:
        """
        Die Beitragsnummer, die nach diesem Befund GILT - oder None.

        NUR bei BESTAETIGT, BEITRAG_BELEGT und NUR_WORTLAUT gibt es eine.
        In allen anderen Lagen ist sie ausdruecklich None: eine Nummer aus
        einer widerlegten oder unklaren Lage saehe genauso aus wie eine gute
        und waere genau deshalb gefaehrlich.
        """
        if self.urteil in (URTEIL_BESTAETIGT, URTEIL_BEITRAG_BELEGT):
            return self.beitrag_anker
        if self.urteil == URTEIL_NUR_WORTLAUT and len(
                self.beitraege_wortlaut) == 1:
            return self.beitraege_wortlaut[0]
        return None


class AnnotationPruefer:
    """
    Prueft die Annotationen EINER Seite gegen deren Abzug.

    Der Finder wird von aussen gereicht und je Seite EINMAL gebaut - eine
    Themenseite kann 500 Beitraege tragen, und die Zerlegung ist der teure
    Teil.
    """

    def __init__(self, finder) -> None:
        from report_render.absatz_finder import AbsatzFinder
        self._finder = finder
        self._AF = AbsatzFinder
        self._reihe = None          # [(nummer, element)] in Dokumentreihenfolge

    # ------------------------------------------------------------------
    @property
    def reihe(self):
        """Die Beitraege der Seite in Dokumentreihenfolge - einmal gebaut."""
        if self._reihe is None:
            self._reihe = []
            for el in self._finder.beitragsreihe():
                m = _POST_KENNUNG.match(str(el.get("id") or "").strip())
                if m:
                    self._reihe.append((int(m.group(1)), el))
        return self._reihe

    def platz(self, nummer: Optional[int]) -> Optional[int]:
        """Der Platz eines Beitrags auf der Seite, 1-basiert."""
        if nummer is None:
            return None
        for i, (nr, _el) in enumerate(self.reihe, 1):
            if nr == nummer:
                return i
        return None

    # ------------------------------------------------------------------
    def _traeger(self, wortlaut: str) -> List[int]:
        """In welchen Beitraegen der Seite steht dieser Wortlaut?"""
        if not falte(wortlaut):
            return []
        heraus = []
        for nr, el in self.reihe:
            if self._AF.wortlaut_im_beitrag(el, wortlaut) is True:
                heraus.append(nr)
        return heraus

    # ------------------------------------------------------------------
    def _gehe(self, ausdruck: str):
        """
        Den Ausdruck Schritt fuer Schritt gehen.

        Rueckgabe: (letzter Elementknoten, Endknoten oder None, gegangen,
        gesamt, Bruchschritt). 'Endknoten' ist der Treffer des LETZTEN
        Schrittes - bei 'text()[n]' also der Textknoten selbst, den
        'anker_teilknoten()' ausdruecklich nicht liefert.
        """
        wurzel = self._finder.wurzel
        schritte = [t for t in str(ausdruck or "").split("/") if t and t != "."]
        if wurzel is None or not schritte:
            return None, None, 0, len(schritte), "(leer)"
        knoten = wurzel
        letztes_element = None
        endknoten = None
        gegangen = 0
        for schritt in schritte:
            if not _SCHRITT.match(schritt):
                return letztes_element, None, gegangen, len(schritte), schritt
            try:
                treffer = knoten.xpath("./" + schritt)
            except Exception:                     # pragma: no cover - defensiv
                return letztes_element, None, gegangen, len(schritte), schritt
            if not treffer:
                return letztes_element, None, gegangen, len(schritte), schritt
            knoten = treffer[0]
            gegangen += 1
            endknoten = knoten
            # NUR ELEMENTE als Ausgangspunkt der Vorfahrensuche: ein
            # Textknoten kommt als 'smart string' zurueck und traegt keine
            # Kinder.
            if isinstance(getattr(knoten, "tag", None), str):
                letztes_element = knoten
        return letztes_element, endknoten, gegangen, len(schritte), ""

    # ------------------------------------------------------------------
    @staticmethod
    def _textprobe(endknoten, sel: Dict[str, Any], wortlaut: str):
        """
        Steht an der benannten Stelle der markierte Wortlaut?

        Anwendbar nur, wenn Start- und Endausdruck DERSELBE sind und auf
        einen Textknoten zeigen - dann ist der Vergleich zeichengenau. Sonst
        traegt der Fall die Wortlautprobe, und das wird gesagt statt
        geschaetzt.

        Rueckgabe: (Ergebnis, gefundener Text gekuerzt).
        """
        if endknoten is None:
            return TEXT_NICHT_ANWENDBAR, ""
        if isinstance(getattr(endknoten, "tag", None), str):
            # Der Ausdruck endet an einem ELEMENT (z. B. '.../p[1]'). Dann
            # sind die Versaetze Kindindizes und keine Zeichenversaetze -
            # eine zeichengenaue Probe ist hier nicht zu machen.
            return TEXT_NICHT_ANWENDBAR, ""
        if str(sel.get("xpathStart") or "") != str(sel.get("xpathEnd") or ""):
            return TEXT_NICHT_ANWENDBAR, ""
        try:
            von = int(sel.get("offsetStart"))
            bis = int(sel.get("offsetEnd"))
        except (TypeError, ValueError):
            return TEXT_NICHT_ANWENDBAR, ""
        if bis < von:
            # GEMESSEN am Bestand (Belege 14 und 50 in evidence_1488): es
            # gibt gespeicherte Auswahlen mit offsetEnd < offsetStart. Eine
            # gueltige Browser-Auswahl kann das nicht erzeugt haben - das ist
            # ein Befund ueber die Speicherung und keine Fundstelle.
            return TEXT_VERSATZ_WIDERSINNIG, ""
        text = str(endknoten)
        if bis > len(text):
            return TEXT_VERSATZ_UNGUELTIG, ""
        ausschnitt = text[von:bis]
        if falte(ausschnitt) == falte(wortlaut):
            return TEXT_GLEICH, falte(ausschnitt)[:60]
        return TEXT_ABWEICHEND, falte(ausschnitt)[:60]

    # ------------------------------------------------------------------
    def pruefe(self, annotation_id, seite: str, selection_json) -> Pruefbefund:
        """Eine Annotation verifizieren. Kein Zweig endet stumm (GR1)."""
        b = Pruefbefund(annotation_id=annotation_id, seite=seite)

        sel = selection_json
        if isinstance(sel, (str, bytes)):
            try:
                sel = json.loads(sel or "{}")
            except (TypeError, ValueError):
                sel = {}
        if not isinstance(sel, dict):
            sel = {}

        if sel.get("target") == "translation":
            b.urteil = URTEIL_UNPRUEFBAR
            b.bemerkung = ("Die Markierung sitzt in einer maschinellen "
                           "Uebersetzung. Sie steht im Abzug nicht; hier ist "
                           "nichts zu vergleichen. Die Beitragsnummer liegt "
                           "in der Auswahl selbst.")
            return b

        wortlaut = str(sel.get("textContent") or "")
        ausdruck = str(sel.get("xpathStart") or "")
        b.beitraege_wortlaut = self._traeger(wortlaut)

        if not ausdruck:
            if len(b.beitraege_wortlaut) == 1:
                b.urteil = URTEIL_NUR_WORTLAUT
                b.bemerkung = ("Die Annotation traegt keinen Ausdruck (Marke "
                               "aus der Zeit vor der Ankerfuehrung oder beim "
                               "Speichern unvollstaendig geblieben). Der "
                               "Wortlaut steht im Abzug in genau einem "
                               "Beitrag - damit steht der Beitrag fest, die "
                               "Stelle darin nicht.")
            else:
                b.urteil = URTEIL_UNPRUEFBAR
                b.bemerkung = ("Kein Ausdruck, und der Wortlaut ist nicht "
                               "eindeutig (%d Traeger). VON HAND ANSEHEN."
                               % len(b.beitraege_wortlaut))
            return b

        element, endknoten, gegangen, gesamt, bruch = self._gehe(ausdruck)
        b.schritte_gegangen, b.schritte_gesamt = gegangen, gesamt
        b.bruch_schritt = bruch
        b.position_vorhanden = (gesamt > 0 and gegangen >= gesamt)

        behaelter = (self._AF.post_behaelter_von(element)
                     if element is not None else None)
        b.beitrag_anker = (self._AF.post_id_von(behaelter)
                           if behaelter is not None else None)

        b.textprobe, b.gefunden_kurz = self._textprobe(endknoten, sel, wortlaut)

        # -- Das Urteil ---------------------------------------------------
        #
        # DIE REIHENFOLGE IST DIE BELEGKRAFT. Zuerst der starke Fall, in dem
        # Position und Inhalt dasselbe sagen; erst danach die Rueckfaelle.
        if b.textprobe == TEXT_GLEICH and b.beitrag_anker is not None:
            b.urteil = URTEIL_BESTAETIGT
            b.bemerkung = ("Der Ausdruck loest vollstaendig auf, und an der "
                           "benannten Stelle steht der markierte Wortlaut. "
                           "Position und Inhalt sagen dasselbe.")
            return b

        eindeutig = len(b.beitraege_wortlaut) == 1
        soll = b.beitraege_wortlaut[0] if eindeutig else None

        if b.beitrag_anker is not None and eindeutig:
            if soll == b.beitrag_anker:
                b.urteil = URTEIL_BEITRAG_BELEGT
                b.bemerkung = (
                    "Die Fundstelle ist nicht zeichengenau zu bestaetigen "
                    "(%s), aber der Wortlaut steht im Abzug in GENAU EINEM "
                    "Beitrag, und das ist der benannte (#%d). Der Beitrag "
                    "steht fest, die Stelle darin nicht."
                    % (b.textprobe, b.beitrag_anker))
            else:
                b.urteil = URTEIL_WIDERLEGT
                b.bemerkung = (
                    "Der Ausdruck benennt Beitrag #%d, der markierte "
                    "Wortlaut steht aber im Abzug in genau einem ANDEREN "
                    "Beitrag: #%d. Textprobe: %s. Die Angabe des Ausdrucks "
                    "wird vom Inhalt nicht getragen."
                    % (b.beitrag_anker, soll, b.textprobe))
            return b

        if b.beitrag_anker is None and eindeutig:
            b.urteil = URTEIL_NUR_WORTLAUT
            b.bemerkung = (
                "Der Ausdruck traegt nicht bis in einen Beitrag (Schritt %d "
                "von %d bricht bei %r), der Wortlaut steht aber im Abzug in "
                "genau einem Beitrag: #%d."
                % (gegangen, gesamt, bruch or "-", soll))
            return b

        if not b.beitraege_wortlaut:
            b.urteil = URTEIL_UNKLAR
            b.bemerkung = (
                "Der markierte Wortlaut kommt im Abzug in KEINEM Beitrag "
                "vor. Das kann an einer Markierung ueber Beitragsgrenzen "
                "hinweg liegen, an anderer Faltung oder daran, dass der "
                "Abzug nicht die gesehene Seite ist. %s VON HAND ANSEHEN."
                % ("Der Ausdruck benennt #%d." % b.beitrag_anker
                   if b.beitrag_anker is not None else
                   "Der Ausdruck benennt keinen Beitrag."))
            return b

        b.urteil = URTEIL_UNKLAR
        b.bemerkung = (
            "Der Wortlaut kommt in %d Beitraegen vor (%s) - wo ein Wortlaut "
            "in vielen Beitraegen vorkommt, kommt er auch im falschen vor. "
            "%s VON HAND ANSEHEN."
            % (len(b.beitraege_wortlaut),
               ", ".join("#%d" % n for n in b.beitraege_wortlaut[:8])
               + (" ..." if len(b.beitraege_wortlaut) > 8 else ""),
               "Der Ausdruck benennt #%d." % b.beitrag_anker
               if b.beitrag_anker is not None else
               "Der Ausdruck benennt keinen Beitrag."))
        return b

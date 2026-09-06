# -*- coding: utf-8 -*-
# =============================================================================
# management/maintenance/anker_postbezug.py
# IT-Forensisches Ermittlungswerkzeug - aiw_webserver
# BUILD 763
# =============================================================================
# ZWECK
#   Zu einem Knoten, an dem ein XPath expression noch aufgeloest hat, die
#   Frage beantworten: IN WELCHEM post container steht er? Und zu einem PAAR
#   solcher Knoten (xpathStart / xpathEnd): welche post container liegen
#   dazwischen?
#
#   Daraus wird die Fallzuordnung 1-6 abgeleitet (Festlegung Alex,
#   06.09.2026), die entscheidet, ob eine Markierung als 'text range' oder
#   als 'whole post' zu fuehren ist.
#
# WARUM DIESES MODUL UND NICHT MEHR CODE IN anker_diagnose.py
#   Grundregel 10 - jede Klasse in eine eigene Datei. anker_diagnose.py hat
#   1284 Zeilen und misst den BRUCH eines Ausdrucks. Der post-Bezug ist eine
#   andere Frage an dasselbe Ergebnis und laesst sich einzeln pruefen.
#
# WAS HIER NICHT NEU GEBAUT WIRD
#   Das Erkennungsmuster fuer post container, der Aufstieg zum container und
#   die Aufzaehlung aller container einer Seite stehen seit Build 728 bzw.
#   751/762 in report_render/absatz_finder.py und werden von dort benutzt:
#
#     AbsatzFinder.post_behaelter_von(knoten)   Aufstieg, gibt das Element
#     AbsatzFinder.beitragsnummer(el)           die Nummer aus 'id'
#     AbsatzFinder._container_der_seite(wurzel) alle container, dedupliziert,
#                                               in Dokumentreihenfolge
#
#   Der letzte Aufruf gilt einem als privat benannten Namen. Das ist Absicht:
#   er haelt die DEDUPLIZIERUNGSREGEL ('nur der aeussere container je
#   Nummer'), und die darf es im Projekt nur einmal geben. Sie hier
#   nachzubauen waere genau die Konstellation, die in Build 762 zum Rueckbau
#   von Block C gefuehrt hat - zwei Wege zu derselben Frage, die binnen
#   weniger Builds auseinanderlaufen.
#
# ZUR VERSCHACHTELUNG - GEMESSEN, NICHT ANGENOMMEN
#   Im Seitenabzug liegen regelmaessig ZWEI Elemente ineinander, auf die das
#   Muster passt: viewtopic0.php Z. 886 oeffnet '<article class="post"
#   id="pN">', Z. 975 darin '<div class="box" id="ppN">', geschlossen wird
#   erst Z. 1212. Beide tragen DIESELBE Nummer und gehoeren zu DEMSELBEN
#   Beitrag. Das ist der Regelfall und wird nicht gemeldet.
#
#   Ein Beitrag INNERHALB eines anderen Beitrags ist damit ausdruecklich
#   NICHT belegt. Er kann nach Auskunft von Alex (06.09.2026) entstehen, wenn
#   BB-Code in 'posts.message' zweigliedrige Elemente verschraenkt schliesst;
#   dann werden nachfolgende Beitraege aus der umschliessenden Ebene
#   gehoben. Dieser Fall ist am Markup unterscheidbar, weil die
#   verschachtelten container dann VERSCHIEDENE Nummern tragen. Genau danach
#   sucht 'verschachtelungen()'.
#
# WARTUNGSSTUFE
#   Rein lesend. Das Modul oeffnet keine Datenbank und beruehrt keinen Baum.
# =============================================================================
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# -----------------------------------------------------------------------------
# Zustaende eines Endpunkts
# -----------------------------------------------------------------------------
#: Der Knoten liegt IN einem post container. Die Nummer ist bekannt.
ZUSTAND_IM_POST = "in_post"
#: Kein Aufstiegstreffer, aber unterhalb des Knotens liegen container. Der
#: Knoten steht also OBERHALB der Beitragsebene. Das ist der Regelfall, wenn
#: der Ausdruck frueh gebrochen ist und nur ein hoher Prefix ueberlebt hat.
ZUSTAND_OBERHALB = "above"
#: Weder oberhalb noch unterhalb ein container.
ZUSTAND_AUSSERHALB = "outside"

# -----------------------------------------------------------------------------
# Seitenklassen
# -----------------------------------------------------------------------------
#: Zuordnung Pfad -> Klasse. Der Pfad wird ohne Abfrageteil und in
#: Kleinschreibung verglichen; die Reihenfolge ist wichtig, weil
#: '/forum/beginner/viewtopic.php' auf '/forum/viewtopic.php' nicht passen
#: darf und umgekehrt.
_KLASSEN: Tuple[Tuple[str, str], ...] = (
    ("/forum/beginner/viewtopic.php", "beginner_viewtopic"),
    ("/forum/viewtopic.php", "viewtopic"),
    ("/forum/pmsnew.php", "pmsnew"),
    ("/forum/search.php", "search"),
    ("/forum/viewforum.php", "viewforum"),
    ("/forum/profile.php", "profile"),
    ("/forum/notifications.php", "notifications"),
)

#: Klassen, auf deren Seiten nach Auskunft von Alex (06.09.2026) KEINE
#: Beitraege stehen.
#:
#: ACHTUNG - DAS IST EINE ERWARTUNG, KEIN SCHALTER. Die Erkennung wird auf
#: diesen Seiten NICHT uebersprungen. Ein Ueberspringen anhand der Adresse
#: waere ein stiller Sprung (Grundregel 1) und machte einen Widerspruch
#: zwischen Erwartung und Abzug per Konstruktion unsichtbar. Die Klasse ist
#: eine Spalte; weicht die Messung von der Erwartung ab, ist das ein Befund.
POSTFREIE_KLASSEN = frozenset({"search", "viewforum", "profile",
                               "notifications"})

KLASSE_SONSTIGE = "sonstige"


def seitenklasse(page_url: str) -> str:
    """
    Die Klasse einer Seite aus ihrer Adresse. Nie leer.

    Der Abfrageteil wird abgeschnitten: '/forum/viewtopic.php?id=1&p=2' und
    '/forum/viewtopic.php' sind dieselbe Seitenart.
    """
    pfad = str(page_url or "").split("?", 1)[0].split("#", 1)[0].lower()
    for anfang, klasse in _KLASSEN:
        if pfad == anfang or pfad.endswith(anfang):
            return klasse
    return KLASSE_SONSTIGE


# -----------------------------------------------------------------------------
# Befunde
# -----------------------------------------------------------------------------
@dataclass
class PostBezug:
    """Der post-Bezug EINES Endpunkts."""
    zustand: str = ZUSTAND_AUSSERHALB
    #: Nur bei ZUSTAND_IM_POST gesetzt.
    post_id: Optional[int] = None
    #: Woher die Nummer stammt. 'ancestor' = Aufstieg. Leer, wenn keine.
    post_id_quelle: str = ""
    #: Nur bei ZUSTAND_OBERHALB: wie viele container unterhalb des Knotens
    #: liegen, und welche Nummern der erste und der letzte traegt.
    nachkommen_zahl: int = 0
    erste_nummer: Optional[int] = None
    letzte_nummer: Optional[int] = None
    #: Klartext, wenn gar nicht gemessen werden konnte (kein Knoten).
    hinweis: str = ""

    def als_dict(self) -> Dict[str, Any]:
        return {
            "state": self.zustand,
            "post_id": self.post_id,
            "post_id_source": self.post_id_quelle,
            "descendant_count": self.nachkommen_zahl,
            "first_post_below": self.erste_nummer,
            "last_post_below": self.letzte_nummer,
            "note": self.hinweis,
        }


@dataclass
class Spanne:
    """Die post container ZWISCHEN zwei Endpunkten."""
    #: Nummern der container, die in Dokumentreihenfolge zwischen den beiden
    #: Knoten liegen - die container der Endpunkte selbst NICHT enthalten.
    posts_dazwischen: List[int] = field(default_factory=list)
    messbar: bool = False
    grund: str = ""

    def als_dict(self) -> Dict[str, Any]:
        return {
            "posts_between": list(self.posts_dazwischen),
            "measurable": self.messbar,
            "reason": self.grund,
        }


@dataclass
class Verschachtelung:
    """Ein container in einem anderen container mit ANDERER Nummer."""
    aussen: int
    innen: int

    def als_dict(self) -> Dict[str, Any]:
        return {"outer": self.aussen, "inner": self.innen}


# -----------------------------------------------------------------------------
# Fallzuordnung 1-6
# -----------------------------------------------------------------------------
FALL_UNBESTIMMT = 0
TYP_TEXT_RANGE = "text range"
TYP_WHOLE_POST = "whole post"
TYP_KEINER = ""

#: Klartext zu jedem Fall - fuer den Bericht und fuer die JSON-Ausgabe.
FALL_TEXT: Dict[int, str] = {
    0: "unbestimmt - mindestens ein Ausdruck loest nicht vollstaendig auf",
    1: "beide Endpunkte in DEMSELBEN post",
    2: "beginnt vor einem post, endet in ihm",
    3: "beginnt in einem post, endet nach ihm",
    4: "umschliesst einen post vollstaendig",
    5: "beruehrt keinen post",
    6: "mehrere posts betroffen",
}


def fall_bestimmen(start: PostBezug, ende: PostBezug, spanne: Spanne,
                   start_loest_auf: bool,
                   ende_loest_auf: bool) -> Tuple[int, str, List[int], str]:
    """
    Die Fallzuordnung nach der Festlegung vom 06.09.2026.

    Rueckgabe: (fall, vorgeschlagener_typ, betroffene_nummern, begruendung)

    ABGELEITET, NICHT GEMESSEN. Die Messung sind 'start', 'ende' und
    'spanne'; dies hier ist die Rechnung darauf. Der Aufrufer weist beides
    getrennt aus, damit im Bericht zu sehen ist, welche Zahl woher kommt.

    WARUM DIE AUFLOESUNG BEDINGUNG IST: Bricht ein Ausdruck, dann sagt sein
    ueberlebender Prefix etwas ueber SICH aus, nicht ueber die Markierung.
    Der gemeinte Zielknoten kann sehr wohl in einem post gelegen haben. Aus
    einem gebrochenen Ausdruck einen Fall abzuleiten hiesse, eine Aussage
    ueber die Markierung auf eine Messung am Prefix zu stuetzen - genau der
    Fehler, der in Build 762 zum Rueckbau von 'anker_inventar' Block C
    gefuehrt hat. Deshalb: Fall 0.
    """
    if not (start_loest_auf and ende_loest_auf):
        offen = []
        if not start_loest_auf:
            offen.append("xpathStart")
        if not ende_loest_auf:
            offen.append("xpathEnd")
        return (FALL_UNBESTIMMT, TYP_KEINER, [],
                "%s bricht - der ueberlebende Prefix sagt nichts ueber die "
                "Lage der Markierung" % " und ".join(offen))

    betroffen: List[int] = []
    for nummer in ([start.post_id] + list(spanne.posts_dazwischen)
                   + [ende.post_id]):
        if nummer is not None and nummer not in betroffen:
            betroffen.append(nummer)

    im_post_start = start.zustand == ZUSTAND_IM_POST
    im_post_ende = ende.zustand == ZUSTAND_IM_POST

    if len(betroffen) >= 2:
        return (6, TYP_WHOLE_POST, betroffen,
                "%d posts betroffen" % len(betroffen))
    if not betroffen:
        return (5, TYP_TEXT_RANGE, [],
                "kein post an den Endpunkten und keiner dazwischen")
    if im_post_start and im_post_ende:
        return (1, TYP_TEXT_RANGE, betroffen, "beide Endpunkte im post %d"
                % betroffen[0])
    if im_post_ende:
        return (2, TYP_WHOLE_POST, betroffen,
                "Anfang ausserhalb, Ende im post %d" % betroffen[0])
    if im_post_start:
        return (3, TYP_WHOLE_POST, betroffen,
                "Anfang im post %d, Ende ausserhalb" % betroffen[0])
    return (4, TYP_WHOLE_POST, betroffen,
            "beide Endpunkte ausserhalb, post %d liegt dazwischen"
            % betroffen[0])


# -----------------------------------------------------------------------------
# Der Messer
# -----------------------------------------------------------------------------
class PostBezugMesser:
    """
    Die Messung an EINEM Baum. Je Seite und Sicht einmal zu bauen, weil die
    Aufzaehlung der container und die Dokumentreihenfolge einmal ermittelt
    und dann mehrfach benutzt werden.

    ZUR KNOTENIDENTITAET: lxml legt seine Python-Huellen erst bei Bedarf an
    und gibt dieselbe Huelle nur so lange zurueck, wie noch eine Referenz auf
    sie lebt. Deshalb haelt dieses Objekt die Liste aller Elemente
    ('_reihenfolge') fest, solange es lebt - ohne sie waere 'id(knoten)' als
    Schluessel unzuverlaessig, und die Spanne koennte still falsch werden.
    Ist ein Knoten trotzdem nicht in der Zuordnung, wird das gesagt und die
    Spanne als nicht messbar gemeldet (Grundregel 1).
    """

    def __init__(self, wurzel) -> None:
        from report_render.absatz_finder import AbsatzFinder
        self._finder_klasse = AbsatzFinder
        self._wurzel = wurzel
        #: Alle Elemente in Dokumentreihenfolge - haelt die Huellen am Leben.
        self._reihenfolge: List[Any] = [
            el for el in wurzel.iter() if hasattr(el, "get")]
        self._platz: Dict[int, int] = {
            id(el): nr for nr, el in enumerate(self._reihenfolge)}
        #: Die container, dedupliziert (nur der aeussere je Nummer), in
        #: Dokumentreihenfolge - aus der einen Quelle im Projekt.
        self._container: List[Any] = AbsatzFinder._container_der_seite(wurzel)
        self._container_platz: List[Tuple[int, int]] = []
        for el in self._container:
            nummer = AbsatzFinder.beitragsnummer(el)
            platz = self._platz.get(id(el))
            if nummer is not None and platz is not None:
                self._container_platz.append((platz, nummer))
        self._container_platz.sort()

    # ------------------------------------------------------------------
    @property
    def container_zahl(self) -> int:
        return len(self._container_platz)

    @property
    def container_nummern(self) -> List[int]:
        return [n for _p, n in self._container_platz]

    # ------------------------------------------------------------------
    def bezug(self, knoten) -> PostBezug:
        """
        Der post-Bezug eines Knotens: erst aufwaerts, dann - nur bei
        Misserfolg - abwaerts.

        Die Reihenfolge ist nicht beliebig. Ein Treffer aufwaerts ist
        eindeutig: der Knoten steht IN diesem Beitrag. Ein Fund abwaerts ist
        es nicht - unter einem hohen Knoten liegen alle Beitraege der Seite,
        und daraus EINE Nummer zu waehlen waere geraten. Deshalb liefert der
        Abstieg auch keine 'post_id', sondern nur die Auskunft, dass der
        Knoten oberhalb der Beitragsebene steht.
        """
        b = PostBezug()
        if knoten is None:
            b.hinweis = ("kein aufloesender Knoten - der Ausdruck bricht "
                         "schon im ersten Schritt")
            return b

        behaelter = self._finder_klasse.post_behaelter_von(knoten)
        if behaelter is not None:
            nummer = self._finder_klasse.beitragsnummer(behaelter)
            if nummer is not None:
                b.zustand = ZUSTAND_IM_POST
                b.post_id = nummer
                b.post_id_quelle = "ancestor"
                return b

        unten = self._container_unterhalb(knoten)
        if unten:
            b.zustand = ZUSTAND_OBERHALB
            b.nachkommen_zahl = len(unten)
            b.erste_nummer = unten[0]
            b.letzte_nummer = unten[-1]
            return b

        b.zustand = ZUSTAND_AUSSERHALB
        return b

    # ------------------------------------------------------------------
    def _container_unterhalb(self, knoten) -> List[int]:
        """
        Die Nummern der container im Teilbaum unter dem Knoten, in
        Dokumentreihenfolge. Der Knoten selbst zaehlt mit, wenn er einer ist
        - dieser Fall ist hier aber schon durch den Aufstieg abgefangen.
        """
        nummern: List[int] = []
        gesehen = set()
        for el in knoten.iter():
            if not hasattr(el, "get"):
                continue
            nummer = self._finder_klasse.beitragsnummer(el)
            if nummer is None or nummer in gesehen:
                continue
            gesehen.add(nummer)
            nummern.append(nummer)
        return nummern

    # ------------------------------------------------------------------
    def spanne(self, knoten_a, knoten_b) -> Spanne:
        """
        Die container, die in Dokumentreihenfolge ZWISCHEN beiden Knoten
        liegen. Die container der Endpunkte selbst sind nicht enthalten -
        die stehen schon in deren 'PostBezug'.

        Die Reihenfolge der beiden Knoten wird nicht vorausgesetzt: liegt
        der zweite vor dem ersten, wird getauscht. Das kommt vor, wenn ein
        Ausdruck falsch abgelegt wurde, und ist kein Grund, die Messung zu
        verweigern.
        """
        s = Spanne()
        if knoten_a is None or knoten_b is None:
            s.grund = "mindestens ein Endpunkt hat keinen aufloesenden Knoten"
            return s
        platz_a = self._platz.get(id(knoten_a))
        platz_b = self._platz.get(id(knoten_b))
        if platz_a is None or platz_b is None:
            s.grund = ("ein Endpunkt liegt nicht in der Dokumentreihenfolge "
                       "dieses Baumes - Spanne nicht bestimmbar")
            return s
        if platz_a > platz_b:
            platz_a, platz_b = platz_b, platz_a
        s.messbar = True

        #: Die container der Endpunkte selbst bleiben draussen.
        eigene = set()
        for knoten in (knoten_a, knoten_b):
            behaelter = self._finder_klasse.post_behaelter_von(knoten)
            nummer = self._finder_klasse.beitragsnummer(behaelter)
            if nummer is not None:
                eigene.add(nummer)

        for platz, nummer in self._container_platz:
            if platz_a < platz < platz_b and nummer not in eigene:
                s.posts_dazwischen.append(nummer)
        return s

    # ------------------------------------------------------------------
    def verschachtelungen(self) -> List[Verschachtelung]:
        """
        Paare (aeusserer container, innerer container) mit VERSCHIEDENEN
        Nummern.

        Gleiche Nummer ist der Regelfall ('pN' aussen, 'ppN' innen, s.
        Modulkopf) und wird nicht gemeldet. Verschiedene Nummern sind der
        Fall, den verschraenkt geschlossener BB-Code erzeugen kann.

        Es wird jedes Paar aus einem container und seinem NAECHSTEN
        container-Vorfahren gemeldet, nicht jede Kombination - sonst zaehlte
        eine dreifache Schachtelung als drei Befunde und nicht als zwei.
        """
        aus: List[Verschachtelung] = []
        gesehen = set()
        for el in self._reihenfolge:
            innen = self._finder_klasse.beitragsnummer(el)
            if innen is None:
                continue
            eltern = el.getparent()
            aussen_el = (self._finder_klasse.post_behaelter_von(eltern)
                         if eltern is not None else None)
            if aussen_el is None:
                continue
            aussen = self._finder_klasse.beitragsnummer(aussen_el)
            if aussen is None or aussen == innen:
                continue
            paar = (aussen, innen)
            if paar in gesehen:
                continue
            gesehen.add(paar)
            aus.append(Verschachtelung(aussen=aussen, innen=innen))
        return aus

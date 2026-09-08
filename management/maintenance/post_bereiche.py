# -*- coding: utf-8 -*-
# =============================================================================
# management/maintenance/post_bereiche.py
# IT-Forensisches Ermittlungswerkzeug - aiw_webserver
# BUILD 765 (Erstfassung Build 764)
# =============================================================================
# ZWECK
#   Die Bereichsdefinition eines Beitrags, je Seitenart. Sie beantwortet zwei
#   Fragen zu einem Knoten im page BLOB:
#
#     1. In welchem post container steht er?
#     2. Steht er im INHALTSBEREICH dieses Beitrags oder im RAHMEN?
#
#   Der Inhaltsbereich ist der vom Verfasser geschriebene Text. Der Rahmen ist
#   alles Uebrige im container: Metadatenspalte, Betreffzeile, Signatur,
#   Hinweise, Funktionsleiste.
#
# WOZU DIE UNTERSCHEIDUNG
#   Sie entscheidet, ob eine Markierung als 'text range' oder als 'whole post'
#   zu fuehren ist (Regelkatalog selection_json 2.0, Abschnitt 2.1):
#
#     Markierung liegt VOLLSTAENDIG im Inhaltsbereich EINES Beitrags
#         -> text range
#     Markierung greift AUCH ausserhalb des Inhaltsbereichs
#         -> whole post
#
#   Gemessen im Lauf zu Build 764: von 53 durchgesehenen Faellen sind 24 von
#   Alex als 'ganzer Post als text-range markiert' eingeordnet worden - alle
#   24 wurden von dieser Regel erkannt, kein Fehltreffer.
#
# WARUM NICHT UEBER DIE INNERE KENNUNG
#   In Build 763 war erwogen worden, den Rahmen als 'im container, aber nicht
#   in der inneren Kennung' zu bestimmen. Das ist FALSCH, aus drei am
#   Quelltext belegten Gruenden:
#
#     1. Die innere Kennung umschliesst den Rahmen mit. viewtopic0.php Z. 977
#        oeffnet darin 'div.postbody', Z. 980 'div.postleft' (Autor, Avatar,
#        Rang), Z. 1161 'div.postfoot' (Funktionen).
#     2. Zwei der 24 Faelle beginnen in 'div.postleft' (Muster dl/dd/strong,
#        viewtopic0.php Z. 981 ff.) und waeren durchgerutscht.
#     3. Im Anfaengerforum gibt es die innere Kennung UEBERHAUPT NICHT.
#        viewtopic1.php Z. 576 schreibt die einfache Kennung. Die Regel haette
#        dort JEDE Markierung als Rahmen gewertet.
#
#   Die innere Kennung wird deshalb nicht ausgewertet.
#
# BUILD 765 - WAS SICH GEAENDERT HAT
#   (a) 'Klassenprobe' heisst jetzt 'Elementprobe' und kann ueber
#       'has_attribute' auch Attribute pruefen, nicht nur Klassen.
#   (b) Eine Seitenart traegt MEHRERE Inhaltsbereiche. Bis 764 galt 'eine
#       Seitenart, ein Anker'; der Systembeitrag hat diese Annahme gebrochen.
#   (c) Das Feld 'ohne_inhalt' ist ERSATZLOS ENTFALLEN. Der Systembeitrag war
#       sein einziger Verwender, und er hat sehr wohl einen Inhaltsbereich -
#       er ist nur anders benannt (Regelkatalog G10, Alex 08.09.2026).
#   (d) 'ZUSTANDSKLASSEN' aufgenommen, fuer den XPath-Generator aus Build 766.
#
# WARUM DIESE DATEI DIE EINZIGE QUELLE IST
#   Dieselbe Tabelle steht als Dokument in documents/Post_Bereiche_Katalog.md,
#   weil sie fuer die Anpassung an ANDERE Foren gebraucht wird. Ein Waechter
#   (AD45) haelt beide gegeneinander. Ohne ihn laufen Dokument und Code binnen
#   weniger Builds auseinander, und dann gilt keins von beidem.
#
# WARTUNGSSTUFE
#   Rein lesend. Reine Beschreibung, kein Zustand, keine Datenbank.
# =============================================================================
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# -----------------------------------------------------------------------------
# Lagen eines Endpunkts
# -----------------------------------------------------------------------------
#: Der Knoten steht im Inhaltsbereich eines Beitrags.
LAGE_CONTENT = "content"
#: Der Knoten steht in einem Beitrag, aber ausserhalb des Inhaltsbereichs.
LAGE_FRAME = "frame"
#: Der Knoten steht in keinem Beitrag.
LAGE_OUTSIDE = "outside"

# -----------------------------------------------------------------------------
# Zustandsklassen
# -----------------------------------------------------------------------------
#: BUILD 765 - Klassen, die einen ZUSTAND ausdruecken und keine Struktur. Sie
#: sind fuer den Rang 'by_class' des XPath-Generators nicht zu verwenden.
#:
#: Das Forum verwendet kein JavaScript; ein Wechsel von Klassennamen findet
#: also nicht statt. Der Ausschluss erfolgt trotzdem - eine Zustandsklasse
#: sagt nichts darueber aus, WO ein Element steht, und darum geht es beim
#: Erzeugen eines Weges.
#:
#: Festlegung Alex, 08.09.2026. Die Liste ist NICHT abschliessend.
ZUSTANDSKLASSEN: Tuple[str, ...] = ("hidden", "censored", "uncensored",
                                    "shadow")


# -----------------------------------------------------------------------------
# Die Proben
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class Elementprobe:
    """
    Eine Probe auf ein Element: Tagname, Klassen, Attribute.

    'hat' nennt Klassen, die ALLE vorhanden sein muessen, 'hat_nicht' solche,
    von denen KEINE vorhanden sein darf.

    'has_attribute' nennt Paare (Name, Wert). Es genuegt, wenn EIN Paar
    zutrifft - die Semantik ist ODER, nicht UND. Das ist Absicht: der
    Systembeitrag traegt seinen Inhaltsbereich in den vorhandenen page BLOBs
    als 'id="contentType4"', in kuenftigen Abzuegen als 'name="contentType4"'
    (Umstellung im Forum-Quelltext am 08.09.2026). Beide Formen muessen
    treffen, ohne dass eine Nachbesserung noetig wird.

    Klassen werden TOKENWEISE verglichen, nicht als Zeichenkette. Ein Test auf
    das Vorkommen von 'contents' in 'class="regular contents"' waere auch bei
    'class="table-of-contents"' wahr - der Vergleich muss an Wortgrenzen
    erfolgen.
    """
    marke: str = ""
    hat: Tuple[str, ...] = ()
    hat_nicht: Tuple[str, ...] = ()
    has_attribute: Tuple[Tuple[str, str], ...] = ()

    def trifft(self, el) -> bool:
        if el is None or not hasattr(el, "get"):
            return False
        if self.marke and _marke_von(el) != self.marke:
            return False
        klassen = _klassen_von(el)
        if any(k not in klassen for k in self.hat):
            return False
        if any(k in klassen for k in self.hat_nicht):
            return False
        if self.has_attribute:
            if not any(str(el.get(name) or "") == wert
                       for name, wert in self.has_attribute):
                return False
        return True

    def als_xpath_pruefung(self) -> str:
        """Diese Probe als XPath-Praedikat, ohne umgebende Klammern."""
        teile: List[str] = []
        for k in self.hat:
            teile.append(_xpath_klasse(k))
        for k in self.hat_nicht:
            teile.append("not(%s)" % _xpath_klasse(k))
        if self.has_attribute:
            oder = " or ".join("@%s='%s'" % (n, w)
                               for n, w in self.has_attribute)
            teile.append("(%s)" % oder if len(self.has_attribute) > 1
                         else oder)
        return " and ".join(teile) if teile else "true()"

    def als_xpath_schritt(self) -> str:
        """Die Probe als vollstaendiger Schrittausdruck."""
        return "%s[%s]" % (self.marke or "*", self.als_xpath_pruefung())


@dataclass(frozen=True)
class Inhaltsbereich:
    """
    Ein Inhaltsbereich innerhalb eines post container.

    'container' engt ein, fuer WELCHE Bauform des containers dieser Bereich
    gilt. None heisst: fuer alle. Damit kann eine Seitenart mehrere Bauformen
    fuehren - der Systembeitrag steht auf derselben Seite wie der regulaere
    Beitrag und hat einen anders benannten Inhaltsbereich.

    'vorfahre' ist ein Element, das zwischen Anker und container liegen muss.
    Es engt die Suche ein und schuetzt gegen ein gleichnamiges Element an
    anderer Stelle des Beitrags.
    """
    anker: Elementprobe
    vorfahre: Optional[Elementprobe] = None
    container: Optional[Elementprobe] = None
    name: str = ""
    beleg: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Seitenartbeschreibung:
    """Container und Inhaltsbereiche einer Seitenart."""
    #: Der Schluessel, den seitenklasse() aus der Adresse ableitet.
    schluessel: str
    #: Klartext fuer Bericht und Dokument.
    beschreibung: str
    #: Das Element, das den Beitrag traegt - 'article' oder 'div'.
    container_marke: str
    #: BUILD 765: MEHRERE Inhaltsbereiche. Der erste, dessen 'container'
    #: passt, gilt. Leer heisst: diese Seitenart traegt keine Beitraege.
    inhaltsbereiche: Tuple[Inhaltsbereich, ...] = ()
    #: Belegzeilen aus dem Forenquelltext.
    beleg: Tuple[str, ...] = ()
    #: Traegt die Seitenart ueberhaupt Beitraege?
    traegt_beitraege: bool = True
    hinweis: str = ""


def _xpath_klasse(name: str) -> str:
    """Ein tokenweiser Klassentest als XPath-Ausdruck."""
    return ("contains(concat(' ',normalize-space(@class),' '),' %s ')" % name)


def _klassen_von(el) -> set:
    roh = el.get("class") if hasattr(el, "get") else None
    return set(str(roh or "").split())


def _marke_von(el) -> str:
    marke = getattr(el, "tag", "")
    if not isinstance(marke, str):            # Kommentare, Verarbeitungsanw.
        return ""
    return marke.rsplit("}", 1)[-1].lower()


# -----------------------------------------------------------------------------
# Wiederkehrende Proben
# -----------------------------------------------------------------------------
_POSTMSG = Elementprobe(
    marke="div", hat=("postmsg",),
    # Die Signatur traegt DIESELBE Klasse 'postmsg' als eigenes Token
    # (viewtopic0.php Z. 1179, pms_new/mdl/topic.php Z. 482:
    # '<div class="postsignature postmsg">'). Ein tokenweiser Test auf
    # 'postmsg' trifft sie deshalb ebenfalls. Sie MUSS ausdruecklich
    # ausgeschlossen werden, sonst waere die Festlegung 'Signatur ist Rahmen'
    # nur auf dem Papier getroffen. Begruendung (Alex, 07.09.2026): die
    # Signatur stammt aus den Metadaten des Benutzers, nicht aus dem Inhalt.
    hat_nicht=("postsignature",))

_POSTRIGHT = Elementprobe(marke="div", hat=("postright",))

#: Der Systembeitrag. viewtopic0.php Z. 330 leitet ihn bei posts.type == 4 ein
#: und verlaesst die Beitragsausgabe danach mit 'return'. Es gibt ZWEI
#: Bauformen: die Tabelle in viewtopic0.php Z. 351 ff. und die aufklappbare
#: aus include/type4.php, eingebunden ueber viewtopic.php Z. 618. Die zweite
#: ist die im Bestand angetroffene (Alex, 07.09.2026, Abzuege zu p1923259 und
#: p993198).
_SYSTEMPOST_CONTAINER = Elementprobe(marke="article", hat=("systempost",))
_SYSTEMPOST_INHALT = Elementprobe(
    marke="div",
    has_attribute=(("id", "contentType4"), ("name", "contentType4")))


# -----------------------------------------------------------------------------
# DER KATALOG
# -----------------------------------------------------------------------------
# ACHTUNG: Diese Liste ist NICHT ABSCHLIESSEND. Sie beschreibt die Seitenarten,
# die im Bestand dieses Verfahrens vorkommen und am Forenquelltext geprueft
# sind. Ein anderes Forum bringt andere Seitenarten mit. Eine Seitenart, die
# hier fehlt, wird als 'sonstige' gefuehrt und NICHT stillschweigend wie eine
# bekannte behandelt.
#
# REIHENFOLGE DER INHALTSBEREICHE: Der erste passende gewinnt. Deshalb stehen
# die spezielleren - mit gesetztem 'container' - VOR den allgemeinen.
KATALOG: Tuple[Seitenartbeschreibung, ...] = (
    Seitenartbeschreibung(
        schluessel="viewtopic",
        beschreibung="Themenansicht des Hauptforums",
        container_marke="article",
        inhaltsbereiche=(
            Inhaltsbereich(
                name="Systembeitrag",
                anker=_SYSTEMPOST_INHALT,
                container=_SYSTEMPOST_CONTAINER,
                beleg=(
                    "viewtopic0.php Z. 330 Verzweigung bei posts.type == 4",
                    "viewtopic.php Z. 618 include('include/type4.php')",
                    "type4.php <div id=\"contentType4\"> - INHALT",
                    "kuenftige Abzuege: name=\"contentType4\" statt id",
                )),
            Inhaltsbereich(
                name="regulaerer Beitrag",
                anker=_POSTMSG, vorfahre=_POSTRIGHT,
                beleg=(
                    "viewtopic0.php Z. 1004 <div class=\"postright\">",
                    "viewtopic0.php Z. 1005 <h3> Themenbetreff - RAHMEN",
                    "viewtopic0.php Z. 1006 <div class=\"postmsg\"> - INHALT",
                    "viewtopic0.php Z. 1142 <div class=\"postwarn\"> - RAHMEN",
                    "viewtopic0.php Z. 1179 "
                    "<div class=\"postsignature postmsg\"> - RAHMEN",
                )),
        ),
        beleg=(
            "viewtopic0.php Z. 886  <article class=\"post\" id=\"p<id>\">",
            "viewtopic0.php Z. 1212 </article>",
        ),
        hinweis=(
            "Der Systembeitrag ist seit Build 765 KEIN Sonderfall mehr: er hat "
            "einen Inhaltsbereich, er ist nur anders benannt. 'text range' ist "
            "dort zulaessig. Sein Anker ist ueber die Beitragsnummer "
            "verankert, weil 'contentType4' selbst NICHT eindeutig ist - sie "
            "wiederholt sich bei jedem Systembeitrag der Seite. Randnotiz: bei "
            "einem Teil dieser Beitraege traegt posts.message ein "
            "serialisiertes PHP-Array, das das Forum selbst nicht sinnvoll "
            "anzeigt; fuer die Bereichsfrage ohne Belang."),
    ),
    Seitenartbeschreibung(
        schluessel="beginner_viewtopic",
        beschreibung="Themenansicht des Anfaengerforums",
        container_marke="div",
        inhaltsbereiche=(
            Inhaltsbereich(
                name="regulaerer Beitrag",
                anker=Elementprobe(marke="div", hat=("regular", "contents")),
                vorfahre=Elementprobe(marke="div", hat=("topic-body",)),
                beleg=(
                    "viewtopic1.php Z. 584 <div class=\"topic-body clearfix\">",
                    "viewtopic1.php Z. 585 <div class=\"topic-meta-data\"> "
                    "- RAHMEN",
                    "viewtopic1.php Z. 604 <div class=\"regular contents\"> "
                    "- INHALT",
                    "viewtopic1.php Z. 629 "
                    "<div class=\"postsignature postmsg\"> - RAHMEN, liegt "
                    "hier ausserhalb des Inhaltsankers",
                )),
        ),
        beleg=(
            "viewtopic1.php Z. 576 <div class=\"box typeN\" id=\"p<id>\"> "
            "- EINFACHE Kennung, keine innere Kennung",
        ),
    ),
    Seitenartbeschreibung(
        schluessel="pmsnew",
        beschreibung="Private Nachrichten",
        container_marke="div",
        inhaltsbereiche=(
            Inhaltsbereich(
                name="regulaerer Beitrag",
                anker=_POSTMSG, vorfahre=_POSTRIGHT,
                beleg=(
                    "pms_new/mdl/topic.php Z. 466 <div class=\"postbody\">",
                    "pms_new/mdl/topic.php Z. 476 <div class=\"postright\">",
                    "pms_new/mdl/topic.php Z. 477 <div class=\"postmsg\"> "
                    "- INHALT",
                    "pms_new/mdl/topic.php Z. 482 "
                    "<div class=\"postsignature postmsg\"> - RAHMEN",
                )),
        ),
        beleg=(
            "pms_new/mdl/topic.php Z. 462 "
            "<div id=\"p<id>\" class=\"blockpost\">",
        ),
        hinweis=(
            "Gleicher Inhaltsanker wie 'viewtopic'. In Build 763 war fuer "
            "diese Seitenart ganz 'postright' als Inhalt vorgeschlagen; das "
            "haette die Signatur eingeschlossen und die Seitenarten ungleich "
            "behandelt, ohne dass ein Beleg das traegt."),
    ),
    # ---- Seitenarten OHNE Beitraege -------------------------------------
    #
    # Auch das ist eine Katalogaussage: 'hier stehen keine Beitraege'. Sie ist
    # eine ERWARTUNG und kein Schalter - die Erkennung laeuft auf diesen Seiten
    # trotzdem, und ein Widerspruch wird gemeldet (Grundregel 1). Im Lauf zu
    # Build 764 fuer 'search' (2 Markierungen) und 'viewforum' (1) bestaetigt:
    # null post container, null Widersprueche. Fuer 'profile' und
    # 'notifications' festgestellt durch Alex, 08.09.2026.
    Seitenartbeschreibung(
        schluessel="search", beschreibung="Suchergebnisse",
        container_marke="", traegt_beitraege=False,
        hinweis="Im Lauf zu Build 764 bestaetigt: 2 Markierungen, 0 container."),
    Seitenartbeschreibung(
        schluessel="viewforum", beschreibung="Themenliste eines Unterforums",
        container_marke="", traegt_beitraege=False,
        hinweis="Im Lauf zu Build 764 bestaetigt: 1 Markierung, 0 container."),
    Seitenartbeschreibung(
        schluessel="profile", beschreibung="Benutzerprofil",
        container_marke="", traegt_beitraege=False,
        hinweis="Festgestellt durch Alex, 08.09.2026."),
    Seitenartbeschreibung(
        schluessel="notifications", beschreibung="Benachrichtigungen",
        container_marke="", traegt_beitraege=False,
        hinweis="Festgestellt durch Alex, 08.09.2026."),
)

#: Zugriff ueber den Schluessel.
NACH_SCHLUESSEL: Dict[str, Seitenartbeschreibung] = {
    b.schluessel: b for b in KATALOG}


def beschreibung_zu(schluessel: str) -> Optional[Seitenartbeschreibung]:
    """
    Die Beschreibung zu einer Seitenart, oder None.

    None ist kein Fehler, sondern die Auskunft 'diese Seitenart steht nicht im
    Katalog'. Der Aufrufer muss sie als solche behandeln und darf sie NICHT wie
    eine bekannte Seitenart auswerten.
    """
    return NACH_SCHLUESSEL.get(str(schluessel or ""))


def bereich_zu(b: Optional[Seitenartbeschreibung],
               container) -> Optional[Inhaltsbereich]:
    """
    Der Inhaltsbereich, der fuer DIESEN container gilt.

    Der erste passende gewinnt: ein Bereich mit gesetztem 'container' nur
    dann, wenn die Probe trifft; ein Bereich ohne 'container' immer. Deshalb
    stehen die spezielleren im Katalog VOR den allgemeinen.
    """
    if b is None:
        return None
    for bereich in b.inhaltsbereiche:
        if bereich.container is None or bereich.container.trifft(container):
            return bereich
    return None


# -----------------------------------------------------------------------------
# Die Lagebestimmung
# -----------------------------------------------------------------------------
def lage_von(knoten, container, schluessel: str) -> str:
    """
    Die Lage eines Knotens: LAGE_CONTENT, LAGE_FRAME oder LAGE_OUTSIDE.

    'container' ist das bereits ermittelte Element mit 'id="p<nummer>"' oder
    None. Der Aufstieg dorthin steht in AbsatzFinder.post_behaelter_von() und
    wird hier NICHT wiederholt.

    Der Weg wird vom Knoten aus nach OBEN gegangen und beim container beendet.
    Damit kann ein gleichnamiges Element ausserhalb des Beitrags die Antwort
    nicht verfaelschen - der Inhaltsanker muss zwischen Knoten und container
    liegen, nicht irgendwo auf der Seite.

    'content' und 'frame' sind per Konstruktion komplementaer: was im container
    liegt und den Anker nicht passiert, ist Rahmen.
    """
    if container is None:
        return LAGE_OUTSIDE
    bereich = bereich_zu(beschreibung_zu(schluessel), container)
    if bereich is None:
        # Keine Beschreibung, oder eine Seitenart ohne Inhaltsbereich: alles
        # im container ist Rahmen. Bei einer unbekannten Seitenart ist das die
        # vorsichtige Antwort - 'whole post' verliert keinen Beleg,
        # 'text range' koennte einen verkuerzen (Grundregel 1).
        return LAGE_FRAME

    hier = knoten
    while hier is not None:
        if (bereich.anker.trifft(hier)
                and _vorfahre_passt(hier, bereich, container)):
            return LAGE_CONTENT
        if hier is container:
            break
        hier = hier.getparent()
    return LAGE_FRAME


def _vorfahre_passt(anker, bereich: Inhaltsbereich, container) -> bool:
    """
    Hat der gefundene Anker den geforderten Vorfahren - innerhalb des
    containers?

    Ohne diese Probe wuerde ein 'div.postmsg' anerkannt, das an anderer Stelle
    des Beitrags steht. Mit ihr ist der Weg vollstaendig beschrieben:
    container -> ... -> Vorfahre -> ... -> Anker -> ... -> Knoten.
    """
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


# -----------------------------------------------------------------------------
# Die XPath-Fassung
# -----------------------------------------------------------------------------
# Sie wird vom Server NICHT benutzt - dort geht der Aufstieg oben. Sie steht
# hier, damit die Bereichsdefinition an EINER Stelle gepflegt wird und die
# Gegenprobe im Browser sowie eine spaetere Fassung in toolbar.js aus derselben
# Quelle kommen. Waechter AD45 haelt Dokument und Code aneinander.
#
#: Der Kennungstest. 'number(substring-after(@id,'p'))' ergibt fuer die innere
#: Kennung einen Rest, der mit 'p' beginnt, und daraus NaN; 'NaN = NaN' ist
#: falsch. Damit faellt sie ohne eigene Regel heraus, ebenso 'id="progressbar"'
#: (viewtopic0.php Z. 989). Der Test stammt von Alex (07.09.2026).
XPATH_KENNUNG = ("starts-with(@id,'p') and "
                 "number(substring-after(@id,'p')) = "
                 "number(substring-after(@id,'p'))")


def xpath_container(schluessel: str) -> str:
    """Alle post container einer Seitenart, dokumentweit."""
    b = beschreibung_zu(schluessel)
    if b is None or not b.container_marke:
        return ""
    return "//%s[%s]" % (b.container_marke, XPATH_KENNUNG)


def xpath_anker(bereich: Inhaltsbereich) -> str:
    """
    Der Inhaltsanker als EIN Schrittausdruck mit Praedikaten.

    WARUM NICHT ALS PFAD 'vorfahre//anker': Ein Pfad beschreibt, WO der Anker
    steht. Gebraucht wird aber eine Aussage UEBER EINEN KNOTEN - 'liegt dieser
    Knoten darin'. Der Ausdruck
    'not(ancestor-or-self::div[postright]//div[postmsg])' fragt, ob IRGENDEIN
    Vorfahre mit Klasse 'postright' IRGENDWO ein 'postmsg' enthaelt - und das
    ist fuer das <h3> mit dem Themenbetreff (viewtopic0.php Z. 1005) wahr,
    obwohl es nicht im Inhalt steht. Genau dieser Fehler steckte in den ersten
    Fassungen, meiner und der von Alex.
    """
    anker = bereich.anker.als_xpath_schritt()
    if bereich.vorfahre is None:
        return anker
    return "%s[ancestor::%s]" % (anker, bereich.vorfahre.als_xpath_schritt())


def xpath_bereiche(schluessel: str, art: str) -> List[Tuple[str, str]]:
    """
    Die Ausdruecke einer Seitenart, JE INHALTSBEREICH.

    'art' ist 'general_post', 'content' oder 'frame'.
    Rueckgabe: Liste von (Name des Inhaltsbereichs, Ausdruck).

    'descendant-or-self::node()' und nicht '//*': der zweite waehlt nur
    Elemente UNTERHALB des Ankers. Der Beitragstext steht aber direkt im Anker,
    sein Textknoten hat den Anker als Elternelement - unter '//*' laege der
    haeufigste Fall ueberhaupt ausserhalb des Inhalts.
    """
    b = beschreibung_zu(schluessel)
    container = xpath_container(schluessel)
    if b is None or not container:
        return []
    if art == "general_post":
        return [("", container + "/descendant-or-self::node()")]

    aus: List[Tuple[str, str]] = []
    for bereich in b.inhaltsbereiche:
        rumpf = container
        if bereich.container is not None:
            # Die Bauform des containers engt ein - beim Systembeitrag ueber
            # 'class="systempost"', waehrend die Beitragsnummer weiterhin ueber
            # XPATH_KENNUNG verankert bleibt. Genau das verlangt der
            # Regelkatalog: 'contentType4' ist nicht eindeutig und darf nicht
            # allein stehen.
            rumpf = "//%s[%s][%s]" % (
                bereich.container.marke or b.container_marke,
                XPATH_KENNUNG, bereich.container.als_xpath_pruefung())
        anker = xpath_anker(bereich)
        if art == "content":
            aus.append((bereich.name,
                        "%s//%s/descendant-or-self::node()" % (rumpf, anker)))
        elif art == "frame":
            aus.append((bereich.name,
                        "%s/descendant-or-self::node()"
                        "[not(ancestor-or-self::%s)]" % (rumpf, anker)))
    return aus


def xpath_bereich(schluessel: str, art: str) -> str:
    """
    Der Ausdruck des ERSTEN Inhaltsbereichs.

    Bequemlichkeit fuer den Regelfall. Wer alle braucht - Dokument, Gegenprobe
    im Browser -, nimmt xpath_bereiche().
    """
    alle = xpath_bereiche(schluessel, art)
    return alle[0][1] if alle else ""


def xpath_relativ(schluessel: str) -> Tuple[str, List[Tuple[str, str]]]:
    """
    Die Fassung fuer toolbar.js: Ausdruecke, die vom Endpunkt der Selection
    AUS ausgewertet werden - auch dann, wenn dieser ein Textknoten ist. Die
    Achse 'ancestor-or-self' arbeitet von einem Textknoten aus.

    Rueckgabe: (container_ausdruck, [(Name, Inhaltspruefung), ...]).

    Warum relativ und nicht dokumentweit: ein '//'-Ausdruck baut die Menge
    ALLER Inhaltselemente der Seite auf; danach muesste die Zugehoerigkeit des
    Knotens darin gesucht werden. Auf einer Seite mit 500 Beitraegen ist das je
    Markierung ein grosser Snapshot. Relativ kostet es die Tiefe des Baums, bei
    gleicher Bestimmtheit.
    """
    b = beschreibung_zu(schluessel)
    if b is None or not b.container_marke:
        return "", []
    container = "ancestor-or-self::*[%s][1]" % XPATH_KENNUNG
    pruefungen = [
        # DERSELBE Ankerausdruck wie in der dokumentweiten Fassung - beide
        # kommen aus xpath_anker(). Zwei Herleitungen waeren zwei Definitionen.
        (bereich.name, "boolean(ancestor-or-self::%s)" % xpath_anker(bereich))
        for bereich in b.inhaltsbereiche
    ]
    return container, pruefungen

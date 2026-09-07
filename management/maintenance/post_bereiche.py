# -*- coding: utf-8 -*-
# =============================================================================
# management/maintenance/post_bereiche.py
# IT-Forensisches Ermittlungswerkzeug - aiw_webserver
# BUILD 764
# =============================================================================
# ZWECK
#   Die Bereichsdefinition eines Beitrags, je Seitenart. Sie beantwortet zwei
#   Fragen zu einem Knoten im Seitenabzug:
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
#   zu fuehren ist (Festlegung Alex, 07.09.2026):
#
#     Markierung liegt VOLLSTAENDIG im Inhaltsbereich EINES Beitrags
#         -> text range
#     Markierung greift AUCH ausserhalb des Inhaltsbereichs
#         -> whole post
#
#   Begruendung: Wer den Rahmen mitfasst, hat nicht eine Textstelle zitiert,
#   sondern den Beitrag als Ganzes gegriffen. Gemessen im Lauf zu Build 763:
#   von 53 durchgesehenen Faellen sind 24 von Alex als 'ganzer Post als
#   text-range markiert' eingeordnet worden - genau diese Menge trennt die
#   Regel ab.
#
# WARUM NICHT UEBER 'ppNNN'
#   In Build 763 hatte ich vorgeschlagen, den Rahmen als 'im container, aber
#   nicht in der inneren Kennung ppNNN' zu bestimmen. Das war FALSCH, aus drei
#   am Quelltext belegten Gruenden:
#
#     1. 'ppNNN' umschliesst den Rahmen mit. viewtopic0.php Z. 977 oeffnet
#        darin 'div.postbody', Z. 980 'div.postleft' (Autor, Avatar, Rang) und
#        Z. 1161 'div.postfoot' (Funktionen). 'In ppNNN' ist also gerade nicht
#        'im Inhalt'.
#     2. Zwei der 24 Faelle beginnen in 'div.postleft' (Muster dl/dd/strong,
#        viewtopic0.php Z. 981 ff.) und waeren durchgerutscht.
#     3. Im Anfaengerforum gibt es 'ppNNN' UEBERHAUPT NICHT. viewtopic1.php
#        Z. 576 schreibt '<div class="box typeN" id="p<post_id>">' mit
#        EINFACHER Kennung. Die Regel haette dort JEDE Markierung als Rahmen
#        gewertet.
#
#   'ppNNN' spielt fuer diese Unterscheidung keine Rolle und wird nicht
#   ausgewertet.
#
# WARUM DIESE DATEI DIE EINZIGE QUELLE IST
#   Dieselbe Tabelle steht als Dokument in documents/Post_Bereiche_Katalog.md,
#   weil sie fuer die Anpassung an ANDERE Foren gebraucht wird. Ein Waechter
#   (AD44) haelt beide gegeneinander. Ohne ihn laufen Dokument und Code binnen
#   weniger Builds auseinander, und dann gilt keins von beidem.
#
# WARTUNGSSTUFE
#   Rein lesend. Reine Beschreibung, kein Zustand, keine Datenbank.
# =============================================================================
from __future__ import annotations

from dataclasses import dataclass, field
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
# Die Beschreibung einer Seitenart
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class Klassenprobe:
    """
    Eine Probe auf das 'class'-Attribut eines Elements.

    'hat' nennt Klassen, die ALLE vorhanden sein muessen, 'hat_nicht' solche,
    von denen KEINE vorhanden sein darf.

    Verglichen wird TOKENWEISE, nicht als Zeichenkette. Ein Test auf das
    Vorkommen von 'contents' in 'class="regular contents"' waere auch bei
    'class="table-of-contents"' wahr - der Vergleich muss deshalb an
    Wortgrenzen erfolgen (in XPath: contains(concat(' ',
    normalize-space(@class), ' '), ' contents ')).
    """
    marke: str = ""
    hat: Tuple[str, ...] = ()
    hat_nicht: Tuple[str, ...] = ()

    def trifft(self, el) -> bool:
        if self.marke and _marke_von(el) != self.marke:
            return False
        klassen = _klassen_von(el)
        if any(k not in klassen for k in self.hat):
            return False
        if any(k in klassen for k in self.hat_nicht):
            return False
        return True

    def als_xpath_pruefung(self) -> str:
        """Diese Probe als XPath-Praedikat, ohne umgebende Klammern."""
        teile: List[str] = []
        for k in self.hat:
            teile.append(_xpath_klasse(k))
        for k in self.hat_nicht:
            teile.append("not(%s)" % _xpath_klasse(k))
        return " and ".join(teile) if teile else "true()"


@dataclass(frozen=True)
class Seitenartbeschreibung:
    """Container und Inhaltsbereich einer Seitenart."""
    #: Der Schluessel, den seitenklasse() aus der Adresse ableitet.
    schluessel: str
    #: Klartext fuer Bericht und Dokument.
    beschreibung: str
    #: Das Element, das den Beitrag traegt - 'article' oder 'div'.
    container_marke: str
    #: Der Inhaltsanker: das Element, das den Verfassertext umschliesst.
    #: None heisst: DIESE SEITENART HAT KEINEN INHALTSBEREICH. Dann ist jeder
    #: Knoten im container Rahmen, und jede Markierung darin wird 'whole post'.
    inhaltsanker: Optional[Klassenprobe] = None
    #: Ein Vorfahre, den der Inhaltsanker haben muss. Er engt die Suche ein und
    #: schuetzt gegen ein gleichnamiges Element an anderer Stelle der Seite.
    anker_vorfahre: Optional[Klassenprobe] = None
    #: Belegzeilen aus dem Forenquelltext.
    beleg: Tuple[str, ...] = ()
    #: Traegt die Seitenart ueberhaupt Beitraege?
    traegt_beitraege: bool = True
    #: Sonderfaelle, die im container liegen, aber keinen Inhaltsanker haben.
    #: Sie werden vollstaendig als Rahmen behandelt.
    ohne_inhalt: Tuple[Klassenprobe, ...] = ()
    hinweis: str = ""


def _xpath_klasse(name: str) -> str:
    """Ein tokenweiser Klassentest als XPath-Ausdruck."""
    return ("contains(concat(' ',normalize-space(@class),' '),' %s ')" % name)


def _klassen_von(el) -> set:
    roh = el.get("class") if hasattr(el, "get") else None
    return set(str(roh or "").split())


def _marke_von(el) -> str:
    marke = getattr(el, "tag", "")
    if not isinstance(marke, str):               # Kommentare, Verarbeitungsanw.
        return ""
    return marke.rsplit("}", 1)[-1].lower()


# -----------------------------------------------------------------------------
# DER KATALOG
# -----------------------------------------------------------------------------
# ACHTUNG: Diese Liste ist NICHT ABSCHLIESSEND. Sie beschreibt die Seitenarten,
# die im Bestand dieses Verfahrens vorkommen und am Forenquelltext geprueft
# sind. Ein anderes Forum bringt andere Seitenarten mit; die Struktur der
# Beschreibung ist dafuer gedacht, ergaenzt zu werden. Eine Seitenart, die hier
# fehlt, wird als 'sonstige' gefuehrt und NICHT stillschweigend wie eine
# bekannte behandelt.
_POSTMSG = Klassenprobe(
    marke="div", hat=("postmsg",),
    # Die Signatur traegt DIESELBE Klasse 'postmsg' als eigenes Token
    # (viewtopic0.php Z. 1179, pms_new/mdl/topic.php Z. 482:
    # '<div class="postsignature postmsg">'). Ein tokenweiser Test auf
    # 'postmsg' trifft sie deshalb ebenfalls. Sie MUSS ausdruecklich
    # ausgeschlossen werden, sonst waere die Festlegung 'Signatur ist Rahmen'
    # nur auf dem Papier getroffen. Begruendung der Festlegung (Alex,
    # 07.09.2026): die Signatur stammt aus den Metadaten des Benutzers, nicht
    # aus dem Inhalt des Beitrags.
    hat_nicht=("postsignature",))

_POSTRIGHT = Klassenprobe(marke="div", hat=("postright",))

KATALOG: Tuple[Seitenartbeschreibung, ...] = (
    Seitenartbeschreibung(
        schluessel="viewtopic",
        beschreibung="Themenansicht des Hauptforums",
        container_marke="article",
        inhaltsanker=_POSTMSG,
        anker_vorfahre=_POSTRIGHT,
        beleg=(
            "viewtopic0.php Z. 886  <article class=\"post\" id=\"p<id>\">",
            "viewtopic0.php Z. 1004 <div class=\"postright\">",
            "viewtopic0.php Z. 1005 <h3> mit dem Themenbetreff - RAHMEN",
            "viewtopic0.php Z. 1006 <div class=\"postmsg\"> - INHALT",
            "viewtopic0.php Z. 1142 <div class=\"postwarn\"> - RAHMEN",
            "viewtopic0.php Z. 1179 <div class=\"postsignature postmsg\"> - RAHMEN",
            "viewtopic0.php Z. 1212 </article>",
        ),
        ohne_inhalt=(
            # Der Systembeitrag. viewtopic0.php Z. 330 leitet ihn bei
            # posts.type == 4 ein und verlaesst die Beitragsausgabe danach mit
            # 'return' - der regulaere Aufbau wird gar nicht durchlaufen. Es
            # gibt ZWEI Bauformen: die Tabelle in viewtopic0.php Z. 351 ff. und
            # die aufklappbare Fassung aus include/type4.php, eingebunden ueber
            # viewtopic.php Z. 618. Beide tragen 'class="systempost"', beide
            # haben KEIN postmsg.
            #
            # Die Bauform aus type4.php ist die im Bestand angetroffene (Alex,
            # 07.09.2026, Abzug zu p1923259 und p993198). Weil beide Bauformen
            # denselben Ausgang nehmen, muss nicht entschieden werden, welche
            # im jeweiligen Abzug steht.
            Klassenprobe(marke="article", hat=("systempost",)),
        ),
        hinweis=(
            "Der Systembeitrag (posts.type = 4) hat keinen Inhaltsbereich; "
            "jede Markierung darin wird 'whole post'. Randnotiz: bei einem "
            "Teil dieser Beitraege traegt posts.message ein serialisiertes "
            "PHP-Array, das das Forum selbst nicht sinnvoll anzeigt. Fuer die "
            "Bereichsfrage ohne Belang."),
    ),
    Seitenartbeschreibung(
        schluessel="beginner_viewtopic",
        beschreibung="Themenansicht des Anfaengerforums",
        container_marke="div",
        inhaltsanker=Klassenprobe(marke="div", hat=("regular", "contents")),
        anker_vorfahre=Klassenprobe(marke="div", hat=("topic-body",)),
        beleg=(
            "viewtopic1.php Z. 576 <div class=\"box typeN\" id=\"p<id>\"> "
            "- EINFACHE Kennung, kein ppNNN",
            "viewtopic1.php Z. 584 <div class=\"topic-body clearfix\">",
            "viewtopic1.php Z. 585 <div class=\"topic-meta-data\"> - RAHMEN",
            "viewtopic1.php Z. 604 <div class=\"regular contents\"> - INHALT",
            "viewtopic1.php Z. 629 <div class=\"postsignature postmsg\"> "
            "- RAHMEN, liegt hier ausserhalb des Inhaltsankers",
        ),
    ),
    Seitenartbeschreibung(
        schluessel="pmsnew",
        beschreibung="Private Nachrichten",
        container_marke="div",
        inhaltsanker=_POSTMSG,
        anker_vorfahre=_POSTRIGHT,
        beleg=(
            "pms_new/mdl/topic.php Z. 462 <div id=\"p<id>\" class=\"blockpost\">",
            "pms_new/mdl/topic.php Z. 466 <div class=\"postbody\">",
            "pms_new/mdl/topic.php Z. 476 <div class=\"postright\">",
            "pms_new/mdl/topic.php Z. 477 <div class=\"postmsg\"> - INHALT",
            "pms_new/mdl/topic.php Z. 482 <div class=\"postsignature postmsg\"> "
            "- RAHMEN",
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
    # Build 763 ist sie fuer 'search' (2 Markierungen) und 'viewforum' (1)
    # bestaetigt worden: null post container, null Widersprueche. Fuer
    # 'profile' und 'notifications' lagen keine Markierungen vor - dort ist die
    # Erwartung UNGEPRUEFT.
    Seitenartbeschreibung(
        schluessel="search", beschreibung="Suchergebnisse",
        container_marke="", traegt_beitraege=False,
        hinweis="Im Lauf zu Build 763 bestaetigt: 2 Markierungen, 0 container."),
    Seitenartbeschreibung(
        schluessel="viewforum", beschreibung="Themenliste eines Unterforums",
        container_marke="", traegt_beitraege=False,
        hinweis="Im Lauf zu Build 763 bestaetigt: 1 Markierung, 0 container."),
    Seitenartbeschreibung(
        schluessel="profile", beschreibung="Benutzerprofil",
        container_marke="", traegt_beitraege=False,
        hinweis="UNGEPRUEFT - im Bestand lagen keine Markierungen vor."),
    Seitenartbeschreibung(
        schluessel="notifications", beschreibung="Benachrichtigungen",
        container_marke="", traegt_beitraege=False,
        hinweis="UNGEPRUEFT - im Bestand lagen keine Markierungen vor."),
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
    liegt und den Anker nicht passiert, ist Rahmen. Eine Luecke zwischen beiden
    kann nicht entstehen.
    """
    if container is None:
        return LAGE_OUTSIDE
    b = beschreibung_zu(schluessel)
    if b is None or b.inhaltsanker is None:
        # Keine Beschreibung, oder eine Seitenart ohne Inhaltsbereich: alles
        # im container ist Rahmen. Bei den Sonderfaellen aus 'ohne_inhalt'
        # (Systembeitrag) ist das die gewollte Antwort; bei einer unbekannten
        # Seitenart ist es die vorsichtige - 'whole post' verliert keinen
        # Beleg, 'text range' koennte einen verkuerzen.
        return LAGE_FRAME
    if _ist_sonderfall_ohne_inhalt(container, b):
        return LAGE_FRAME

    hier = knoten
    while hier is not None:
        if b.inhaltsanker.trifft(hier) and _vorfahre_passt(hier, b, container):
            return LAGE_CONTENT
        if hier is container:
            break
        hier = hier.getparent()
    return LAGE_FRAME


def _ist_sonderfall_ohne_inhalt(container, b: Seitenartbeschreibung) -> bool:
    """Traegt der container selbst eine Marke aus 'ohne_inhalt'?"""
    return any(probe.trifft(container) for probe in b.ohne_inhalt)


def _vorfahre_passt(anker, b: Seitenartbeschreibung, container) -> bool:
    """
    Hat der gefundene Anker den geforderten Vorfahren - innerhalb des
    containers?

    Ohne diese Probe wuerde ein 'div.postmsg' anerkannt, das an anderer Stelle
    des Beitrags steht. Mit ihr ist der Weg vollstaendig beschrieben:
    container -> ... -> Vorfahre -> ... -> Anker -> ... -> Knoten.
    """
    if b.anker_vorfahre is None:
        return True
    hier = anker.getparent()
    while hier is not None:
        if b.anker_vorfahre.trifft(hier):
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
# Quelle kommen. Ein Waechter haelt beide Fassungen an denselben Belegen
# gegeneinander.
#: Der Kennungstest. 'number(substring-after(@id,'p'))' ergibt fuer 'pp1234'
#: den Rest 'p1234' und daraus NaN; 'NaN = NaN' ist falsch. Damit faellt die
#: innere Kennung ohne eigene Regel heraus, ebenso 'id="progressbar"'
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


def xpath_anker(schluessel: str) -> str:
    """
    Der Inhaltsanker als EIN Schrittausdruck mit Praedikaten.

    WARUM NICHT ALS PFAD 'vorfahre//anker': Ein Pfad beschreibt, WO der Anker
    steht. Gebraucht wird aber eine Aussage UEBER EINEN KNOTEN - 'liegt dieser
    Knoten darin'. Aus einem Pfad laesst sich die nicht bilden: der Ausdruck
    'not(ancestor-or-self::div[postright]//div[postmsg])' fragt, ob IRGENDEIN
    Vorfahre mit Klasse 'postright' IRGENDWO ein 'postmsg' enthaelt - und das
    ist fuer das <h3> mit dem Themenbetreff (viewtopic0.php Z. 1005) wahr,
    obwohl es nicht im Inhalt steht. Genau dieser Fehler steckte in der ersten
    Fassung.

    Als Schrittausdruck mit angehaengtem 'ancestor::'-Praedikat ist der Anker
    dagegen ueber 'ancestor-or-self::' pruefbar, und 'content' und 'frame'
    bleiben komplementaer.
    """
    b = beschreibung_zu(schluessel)
    if b is None or b.inhaltsanker is None:
        return ""
    anker = "%s[%s]" % (b.inhaltsanker.marke or "*",
                        b.inhaltsanker.als_xpath_pruefung())
    if b.anker_vorfahre is None:
        return anker
    vorfahre = "%s[%s]" % (b.anker_vorfahre.marke or "*",
                           b.anker_vorfahre.als_xpath_pruefung())
    return "%s[ancestor::%s]" % (anker, vorfahre)


def xpath_bereich(schluessel: str, bereich: str) -> str:
    """
    Ein Bereich als dokumentweiter Ausdruck.

    'bereich' ist 'general_post', 'content' oder 'frame'.

    'descendant-or-self::node()' und nicht '//*': der zweite waehlt nur
    Elemente UNTERHALB des Ankers. Der Beitragstext steht aber direkt im Anker,
    sein Textknoten hat den Anker als Elternelement - unter '//*' laege der
    haeufigste Fall ueberhaupt ausserhalb des Inhalts.
    """
    container = xpath_container(schluessel)
    if not container:
        return ""
    if bereich == "general_post":
        return container + "/descendant-or-self::node()"
    anker = xpath_anker(schluessel)
    if not anker:
        # Seitenart ohne Inhaltsbereich: 'content' ist leer, 'frame' ist alles.
        if bereich == "content":
            return ""
        return container + "/descendant-or-self::node()"
    if bereich == "content":
        return "%s//%s/descendant-or-self::node()" % (container, anker)
    if bereich == "frame":
        return ("%s/descendant-or-self::node()"
                "[not(ancestor-or-self::%s)]" % (container, anker))
    return ""


def xpath_relativ(schluessel: str) -> Tuple[str, str]:
    """
    Die Fassung fuer toolbar.js: zwei Ausdruecke, die vom Endpunkt der
    Selection AUS ausgewertet werden - auch dann, wenn dieser ein Textknoten
    ist. Die Achse 'ancestor-or-self' arbeitet von einem Textknoten aus.

    Rueckgabe: (container_ausdruck, inhalts_pruefung).

    Warum relativ und nicht dokumentweit: ein '//'-Ausdruck baut die Menge
    ALLER Inhaltselemente der Seite auf; danach muesste die Zugehoerigkeit des
    Knotens darin gesucht werden. Auf einer Seite mit 500 Beitraegen ist das je
    Markierung ein grosser Snapshot. Relativ kostet es die Tiefe des Baums, bei
    gleicher Bestimmtheit.
    """
    b = beschreibung_zu(schluessel)
    if b is None or not b.container_marke:
        return "", ""
    container = "ancestor-or-self::*[%s][1]" % XPATH_KENNUNG
    if b.inhaltsanker is None:
        return container, "false()"
    # DERSELBE Ankerausdruck wie in der dokumentweiten Fassung - beide kommen
    # aus xpath_anker(). Zwei getrennte Herleitungen waeren zwei Definitionen.
    return (container,
            "boolean(ancestor-or-self::%s)" % xpath_anker(schluessel))

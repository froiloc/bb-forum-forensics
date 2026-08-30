# =============================================================================
# report_render/absatz_finder.py
# IT-Forensisches Ermittlungswerkzeug - Vollzitat (Beweismittelgruppen)
# =============================================================================
# Zweck:
#   DEN ABSATZ WIEDERFINDEN, IN DEM EINE MARKIERUNG STEHT - im gesicherten
#   Seitenabzug, serverseitig, ohne Browser.
#
# DER AUFTRAG (Chef-Ermittlerin, 27.08.2026, Anforderung 2 und 3):
#   "Fuer die markierte Stelle soll der gesamte Absatz, der die Markierung
#   umschliesst, angegeben werden." und "Die markierte Stelle soll in
#   derselben Farbe wie die Annotation hinterlegt sein."
#
#   Die Annotation selbst traegt nur die markierte Stelle
#   (selection_json.textContent) - nie ihre Umgebung. Der Absatz steht
#   ausschliesslich im Seitenabzug: fdb.pages.html, erreichbar ueber die
#   TEMP-VIEW blob_lookup (db/forensic_db.py, get_page).
#
# WARUM DAS BISHER NIEMAND GETAN HAT: Es gab im ganzen Webserver keine
#   serverseitige Aufloesung von selection_json. Die XPath-Anker werden
#   AUSSCHLIESSLICH im Browser aufgeloest (toolbar/toolbar.js,
#   HighlightModule); der Berichtsgenerator sah bis Build 724 von einer
#   Beweismittelgruppe nur die Beleg-IDs. lxml und beautifulsoup4 stehen seit
#   laengerem in requirements.txt und in den Offline-Radlisten
#   (install.py:51, prepare_deployment.py:59), benutzt hat sie nur das
#   Diagnosewerkzeug debug/html_query.py.
#
# ── DER BEZUGSPUNKT DES XPATH ────────────────────────────────────────────────
#
#   toolbar.js rechnet den Anker RELATIV zu '#forensic-viewport'
#   (_xpathOf, Z. 966-995: Abbruch, wenn der Knoten nicht darin liegt;
#   Praefix './'). In diesen Behaelter schiebt die Toolbar den Wert des
#   Envelope-Feldes 'html' - und das ist genau der <body>-Auszug des BLOBs
#   (server/blob_handler.py, _extract_body, Z. 641-669).
#
#   DESHALB WIRD HIER GENAU DIESE FUNKTION AUFGERUFEN und der Auszug nicht
#   ein zweites Mal geschrieben. Wenn der Ausliefernde und der Auswertende
#   den Rumpf verschieden abgrenzen, zeigen die Anker um eine Ebene daneben -
#   und zwar lautlos, weil ein falscher Absatz genauso aussieht wie ein
#   richtiger. Das ist die gefaehrlichste Art von Fehler in diesem Werkzeug.
#
#   NICHT nachgebildet wird _rewrite_asset_urls (blob_handler Z. 301): das
#   aendert nur Adressen in Attributen, nie die Knotenfolge - und damit
#   keinen Anker. Bilder werden im Bericht ohnehin nicht eingebettet (§4.2).
#
# ── DREI WEGE, UND DER BENUTZTE WIRD IMMER GENANNT ───────────────────────────
#
#   WEG_XPATH   Die Anker loesen auf. Der Absatz ist der naechste
#               Block-Vorfahr, die Hinterlegung sitzt zeichengenau auf der
#               Auswahl. Der Sollweg.
#   WEG_TEXT    Die Anker loesen nicht auf (die Seite wurde spaeter neu
#               abgezogen, der Anker stammt aus einer reduzierten Ansicht,
#               ein Zwischenknoten kam dazu). Dann wird der Absatz ueber den
#               WORTLAUT gesucht: derjenige Block, der textContent enthaelt.
#               Zulaessig, aber schwaecher - bei mehrfach vorkommendem
#               Wortlaut kann er den falschen Treffer waehlen. Deshalb wird
#               er benannt.
#   WEG_KEINER  Beides schlaegt fehl. Es wird KEIN Absatz erfunden; der Beleg
#               erscheint mit der markierten Stelle allein und einer Warnung
#               (GR1: kein Beleg darf still uebersprungen werden).
#
#   Der vierte Fall ist kein Weg, sondern eine andere Quelle:
#   WEG_UEBERSETZUNG - die Markierung sitzt in einer KI-Uebersetzung, nicht im
#   Seitenabzug (selection_json.target == 'translation', erzeugt in
#   toolbar/toolbar.js Z. 1110-1126 mit charStart/charEnd statt XPath). Ein
#   Absatz aus dem Original waere dafuer die falsche Umgebung - er enthaelt
#   den markierten Wortlaut gar nicht. Solche Belege werden als solche
#   ausgewiesen.
#
# ── WARUM DIE MARKIERUNG NICHT ALS TEXTSUCHE EINGEFAERBT WIRD ────────────────
#
#   Naheliegend waere: Absatz nehmen, textContent darin suchen, einfaerben.
#   Das geht schief, sobald der Wortlaut im Absatz zweimal vorkommt - und bei
#   kurzen Markierungen ("Bonn", ein Vorname, eine Zahl) ist das der
#   Regelfall, nicht die Ausnahme. Der Bericht faerbte dann die falsche
#   Stelle ein und saehe dabei vollkommen unauffaellig aus.
#   Auf WEG_XPATH wird deshalb mit den ZEICHENVERSAETZEN gearbeitet, die der
#   Browser mitgeschrieben hat (offsetStart/offsetEnd im Textknoten). Die
#   Textsuche gibt es nur auf WEG_TEXT - dort ist sie das Beste, was es noch
#   gibt, und dort steht sie unter Vorbehalt.
#
# ── ES WIRD NICHTS GESCHRIEBEN ───────────────────────────────────────────────
#
#   Diese Datei liest fdb.pages (read-only) und baut HTML im Speicher. Kein
#   Schema, keine Migration, kein Schreibzugriff - der Migrationsvorbehalt ab
#   01.07.2026 ist nicht beruehrt. Der Seitenabzug wird NICHT veraendert; alle
#   Eingriffe geschehen auf einer tiefen Kopie des gefundenen Absatzes.
#
# Grundregeln: GR1, GR6, GR10.
# Version: v0.8.725 - Build: 725 - 2026-08-27
# =============================================================================

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.logger import get_logger

logger = get_logger(__name__)

#: Die Kennung eines Beitrags im Seitenabzug.
#:
#: BUILD 728: BEIDE Schreibweisen - weil die beiden Ansichten des Forums
#: VERSCHIEDEN gebaut sind. Beleg: zwei Auszuege, uebergeben von Alex am
#: 28.08.2026, und der Forenquelltext viewtopic0.php.
#:
#:   FORENBEITRAG (viewtopic) - ZWEI Kennungen mit derselben Nummer:
#:     <article class="post" id="p1164441">      <- aeussere Kennung
#:       <div class="blockpost">
#:         <div class="box" id="pp1164441">      <- innere Kennung
#:
#:   PRIVATE NACHRICHT (pmsnew) - nur die AEUSSERE:
#:     <div id="p120862" class="blockpost roweven">
#:       <div class="box">                       <- KEINE Kennung!
#:
#: Bis Build 727 wurde nur die aeussere angenommen. Fuer die PN-Ansicht ist
#: das genau richtig; fuer den Forenbeitrag ging es gut, weil post_id_von()
#: aufsteigt, die innere nicht passte und der Aufstieg bis zum <article>
#: weiterlief. Es HING aber daran, dass der <article> da ist - in der
#: reduzierten Ansicht (Build 396) und in gallery.php gibt es nur eine
#: Kennung. Umgekehrt genuegt die innere allein NICHT: die Weisung Alex
#: ("Suche nach <div class='box' id='pp<post_id>'>") woertlich als einzigen
#: Weg genommen, haette die privaten Nachrichten leer gelassen, und dort
#: haengt an der post_id der Gespraechspartner. Der Webserver kennt die
#: Doppelung an anderer Stelle laengst: db/forensic_db.py:291-307
#: (_anker_muster) sucht im BLOB nach BEIDEN, belegt mit 'viewtopic0 Z.975'.
#:
#: Die Ziffern stehen in Gruppe 2. Gruppe 1 haelt nur fest, welche der beiden
#: Kennungen getroffen hat - sie wird nicht ausgewertet, macht den Ausdruck
#: aber lesbar.
#:
#: ACHTUNG, ABSICHTLICHER UNTERSCHIED zu forensic_api/annotations.
#: _ELEMENT_POST_RE: JENES Muster liest 'annotations.element_id', und dort
#: steht, was die Toolbar hineingeschrieben hat - immer die aeussere Form
#: 'p<Nummer>'. Es bleibt deshalb eng. HIER wird der SEITENABZUG gelesen, und
#: der traegt beide. Die beiden Muster beschreiben nicht dasselbe.
_POST_KENNUNG = re.compile(r"^p(p?)(\d+)$")

#: Ein Schritt eines XPath-Ausdrucks: 'div[4]', 'article[29]', 'text()[3]'.
#: Wortgleich zu tools/diag_vollzitat_anker.py - dort ist es seit Build 727
#: dasselbe Muster.
_SCHRITT_MUSTER = re.compile(r"^([a-zA-Z_][\w.-]*|text\(\))\[(\d+)\]$")

#: Die vier moeglichen Herkuenfte eines Absatzes. Sie wandern bis in den
#: Bericht - siehe Kopf, "DREI WEGE".
WEG_XPATH = "xpath"
WEG_TEXT = "text"
WEG_KEINER = "keiner"
WEG_UEBERSETZUNG = "uebersetzung"
#: Build 727: es gibt zu diesem Beleg gar keine Annotation mehr. KEIN Weg im
#: eigentlichen Sinn - deshalb ein eigener Wert und nicht WEG_KEINER. Der
#: Unterschied ist der zwischen "der Absatz wurde nicht gefunden" und "es gibt
#: nichts zu finden", und im Bericht ist das der Unterschied zwischen einem
#: Beleg mit Luecke und gar keinem Beleg.
WEG_FEHLT = "fehlt"

# ---------------------------------------------------------------------------
# WARUM DER ANKERWEG NICHT GETRAGEN HAT - BUILD 729
# ---------------------------------------------------------------------------
#
# BIS BUILD 728 GAB ES DARAUF NUR EINE ANTWORT, und sie war eine BEHAUPTUNG:
# "der Anker %r loest nicht auf". Diese Zeile stand im Bericht auch dann, wenn
# der Anker sehr wohl aufgeloest hatte und der Weg an einer SPAETEREN Stelle
# abgebrochen war - _ueber_xpath() gab in fuenf verschiedenen Lagen 'None'
# zurueck, und alle fuenf bekamen denselben Satz.
#
# DAS WAR MEIN FEHLER, und er ist teuer gewesen: Alex hat einen Lauf ueber 25
# echte Markierungen gefahren, in dem 25-mal derselbe Satz stand, und musste
# daraus schliessen, dass die Anker allesamt kaputt seien. Das kann so sein -
# gemessen war es nicht. Eine Diagnose, die fuenf Ursachen unter einem Namen
# fuehrt, ist keine Diagnose (Grundregel: Ueberpruefbarkeit).
#
# Ab hier nennt jede Fundstelle den TATSAECHLICHEN Grund, und bei
# GRUND_ANKER_BRICHT zusaetzlich den SCHRITT, an dem es bricht.
# ---------------------------------------------------------------------------

#: Die Auswahl traegt gar keinen Anker (alte Marke, oder Uebersetzung).
GRUND_OHNE_ANKER = "ohne_anker"
#: Der Ausdruck loest im Abzug nicht auf - der einzige Fall, fuer den der
#: alte Satz je richtig war.
GRUND_ANKER_BRICHT = "anker_bricht"
#: Der Anker loest auf, zeigt aber auf nichts, woraus sich ein Textpunkt
#: machen laesst.
GRUND_KEIN_PUNKT = "kein_punkt"
#: Ueber der Fundstelle steht kein Absatz-Element und auch kein Ersatz.
GRUND_KEIN_BLOCK = "kein_block"
#: Der Textknoten liegt nicht im Klartext des gefundenen Absatzes.
GRUND_KEIN_VERSATZ = "kein_versatz"

#: Klartext zu jedem Grund - fuer Bericht und Werkzeugprotokoll.
GRUND_TEXT = {
    GRUND_OHNE_ANKER:
        "Die Annotation traegt keinen Anker (weder xpathStart noch "
        "xpathEnd). Sie stammt aus einer Zeit vor der Ankerfuehrung oder ist "
        "beim Speichern unvollstaendig geblieben.",
    GRUND_ANKER_BRICHT:
        "Der Anker loest im gesicherten Seitenabzug nicht auf.",
    GRUND_KEIN_PUNKT:
        "Der Anker loest auf, aber der getroffene Knoten laesst sich nicht "
        "als Textstelle lesen.",
    GRUND_KEIN_BLOCK:
        "Der Anker loest auf, ueber der Fundstelle steht aber kein "
        "Absatz-Element und auch kein Beitragsbehaelter.",
    GRUND_KEIN_VERSATZ:
        "Der Anker loest auf, der getroffene Textknoten gehoert aber nicht "
        "zum Klartext des gefundenen Absatzes.",
}

#: Elemente, die als "Absatz" taugen - in der Reihenfolge der Vorliebe.
#:
#: WARUM NICHT EINFACH <p>: Beitraege im Forum sind mit BBCode verfasst und
#: durch parse_message() zu HTML gemacht worden (Forenquelltext
#: include/parser.php). Dabei entstehen neben <p> auch <li> (Listen),
#: <blockquote> (Zitate anderer Beitraege) und <td>. Eine Markierung in einem
#: Listenpunkt haette mit <p> allein keinen Absatz - der naechste <p>-Vorfahr
#: waere entweder keiner oder viel zu gross.
_ABSATZ_TAGS = (
    "p", "li", "blockquote", "dd", "dt", "td", "th",
    "h1", "h2", "h3", "h4", "h5", "h6", "pre",
)

#: Behaelter, die als Absatz-Ersatz dienen, wenn keiner der obigen greift.
#: '.postmsg' ist der Beitragstext selbst (Forenquelltext topic.php /
#: viewtopic.php); dort landet man bei einem Beitrag, der nur aus einer Zeile
#: ohne <p> besteht. Grosszuegiger als noetig zu sein ist hier richtig: ein zu
#: grosser Absatz ist unschoen, ein fehlender ist ein verlorener Beleg.
_ERSATZ_KLASSEN = ("postmsg", "post-entry", "post-body", "entry", "cooked")


@dataclass
class Markierung:
    """
    Eine einzufaerbende Stelle innerhalb eines Absatzes.

    Felder:
        von, bis     - Zeichenversaetze im Klartext des Absatzes (Halbintervall)
        css_klasse   - z. B. 'vz-cat-CAT_LOCATION' (core/kategorie_farben)
        farbe        - Hinterlegungsfarbe '#rrggbb' (fuer Formate ohne CSS)
        nummer       - laufende Nummer der Fussnote im Unterblock (1, 2, 3 ...)
    """
    von: int
    bis: int
    css_klasse: str
    farbe: str
    nummer: int


@dataclass
class Treffer:
    """Eine einzelne Fundstelle: Absatz-Element plus Zeichenbereich darin."""
    block: Any
    von: int
    bis: int


@dataclass
class Fundstelle:
    """
    Wo eine Markierung im Seitenabzug sitzt.

    Felder:
        weg        - WEG_XPATH | WEG_TEXT | WEG_KEINER | WEG_UEBERSETZUNG
        treffer    - ALLE Fundstellen in Dokumentreihenfolge. Auf WEG_XPATH
                     genau eine (der Anker ist eindeutig); auf WEG_TEXT so
                     viele, wie der Wortlaut auf der Seite vorkommt.
        text       - die markierte Stelle im Wortlaut (immer gefuellt, wenn
                     die Annotation ihn traegt - auch bei WEG_KEINER)
        hinweis    - Klartextbegruendung, wenn weg != WEG_XPATH; sonst ""

    WARUM ALLE TREFFER UND NICHT NUR EINER (Weisung Alex, 28.08.2026):
    Bis Build 726 nahm die Wortlautsuche stillschweigend den LETZTEN Treffer
    der Seite. Kommt der Wortlaut mehrfach vor - und bei kurzen Markierungen
    ist das der Regelfall -, stand damit womoeglich der falsche Absatz in der
    Akte, ohne dass man es ihm ansah. Jetzt werden alle gezeigt und
    ausdruecklich als MOEGLICHE Fundstellen bezeichnet. Lieber drei Absaetze,
    von denen einer der richtige ist, als einer, von dem niemand weiss, ob er
    es ist.
    """
    weg: str
    treffer: List[Treffer] = field(default_factory=list)
    text: str = ""
    hinweis: str = ""
    #: BUILD 729 - der GEMESSENE Grund, warum der Ankerweg nicht getragen
    #: hat (GRUND_*), und bei GRUND_ANKER_BRICHT der Schritt, an dem es
    #: bricht. Sie stehen auch in einer erfolgreichen Wortlaut-Fundstelle:
    #: dort sind sie die Antwort auf die Frage, warum der Sollweg ausfiel.
    anker_grund: str = ""
    anker_bruch: str = ""

    # -- Bequemlichkeit fuer den Regelfall (genau ein Treffer) -------------
    @property
    def block(self):
        return self.treffer[0].block if self.treffer else None

    @property
    def von(self) -> int:
        return self.treffer[0].von if self.treffer else 0

    @property
    def bis(self) -> int:
        return self.treffer[0].bis if self.treffer else 0

    @property
    def mehrdeutig(self) -> bool:
        return len(self.treffer) > 1


# ---------------------------------------------------------------------------
# Auswahl-Daten lesen
# ---------------------------------------------------------------------------

def auswahl_text(selection: Any) -> str:
    """
    Den markierten Wortlaut aus einem selection_json-Objekt holen.

    ES WERDEN BEIDE FELDNAMEN GELESEN, und das ist kein Uebereifer, sondern
    ein gemessener Befund: Der Schreiber (toolbar/toolbar.js, Z. 1129-1135)
    legt 'textContent' ab, die serverseitige Auswertung
    (editor/html_renderer.py Z. 319-325) liest 'textContent' mit Rueckfall auf
    'text' - der BERICHTSEDITOR im Browser dagegen liest ausschliesslich
    'ann.selection.text' (userinfo/report_editor.js Z. 3410, 3421, 3437). Auf
    einem Datenbestand mit 'textContent' zeigt der Editor an dieser Stelle
    also nichts. Der Bericht soll nicht denselben Fehler machen.
    """
    if not isinstance(selection, dict):
        return ""
    for feld in ("textContent", "text"):
        wert = selection.get(feld)
        if isinstance(wert, str) and wert:
            return wert
    return ""


def ist_uebersetzungsauswahl(selection: Any) -> bool:
    """
    True, wenn die Markierung in einer KI-Uebersetzung sitzt.

    Beleg: toolbar/toolbar.js Z. 1110-1126 - solche Auswahlen tragen
    target='translation' und charStart/charEnd statt XPath-Ankern.
    """
    return isinstance(selection, dict) and selection.get("target") == "translation"


# ---------------------------------------------------------------------------
# Textknoten eines Teilbaums
# ---------------------------------------------------------------------------

def _textstuecke(wurzel) -> List[Tuple[Any, str, int]]:
    """
    Alle Textstuecke eines Teilbaums in Dokumentreihenfolge.

    Rueckgabe: Liste von (traeger, art, laenge). 'art' ist 'text' (der Text
    IM Element, vor dem ersten Kind) oder 'tail' (der Text NACH dem Element,
    im Elternteil). Das ist die Zerlegung, die lxml fuehrt - und es ist
    dieselbe Zerlegung, die ein Browser als Textknoten sieht, solange
    innerHTML einmal geparst wurde und niemand daran herumgeschnitten hat.
    """
    stuecke: List[Tuple[Any, str, int]] = []
    if wurzel.text:
        stuecke.append((wurzel, "text", len(wurzel.text)))
    for kind in wurzel:
        stuecke.extend(_textstuecke(kind))
        if kind.tail:
            stuecke.append((kind, "tail", len(kind.tail)))
    return stuecke


def _klartext(wurzel) -> str:
    """Der Klartext eines Teilbaums - genau die Verkettung von _textstuecke."""
    return "".join(
        (t.text if art == "text" else t.tail)
        for t, art, _n in _textstuecke(wurzel)
    )


# ---------------------------------------------------------------------------
# Der Wortlaut, wie der BROWSER ihn gebildet hat
# ---------------------------------------------------------------------------
#
# BUILD 729 - DER BEFUND, DER DIE WORTLAUTSUCHE UNBRAUCHBAR MACHTE
# (Alex, 28.08.2026: "Hast du beruecksichtigt, dass im BLOB \n zu <br>
# aufgeloest wird? Du musst dir ansehen, wie 'textContent' im JSON von
# annotation.selection_json erzeugt wird. Das muss rueckwaerts abgewickelt
# werden.").
#
# Er hat recht, und der Beleg steht in toolbar/toolbar.js Z. 1101:
#
#     var text = sel.toString().trim();
#     ...
#     textContent: text
#
# 'textContent' ist also NICHT die Verkettung der Textknoten, sondern
# 'Range.toString()' - die GERENDERTE Fassung der Auswahl. Sie unterscheidet
# sich vom Quelltext an drei Stellen:
#
#   (1) <br> wird zu '\n'. Im Quelltext steht dort NICHTS.
#   (2) Blockgrenzen (</p><p>, </li><li>, </div>) werden zu '\n'.
#   (3) Fuehrende und schliessende Leerzeichen fallen weg ('.trim()').
#
# GEMESSEN an einem Absatz mit drei <br> (Build 729):
#     Quelltext  : 'Zeile eins.Zeile zwei mit fett und Rest.Zeile drei ...'
#     Browser    : 'Zeile eins.\nZeile zwei mit fett und Rest.\nZeile drei ...'
#     'Browser-Wortlaut kommt im Quelltext vor?' -> False
#
# DAMIT KONNTE DIE WORTLAUTSUCHE JEDE MEHRZEILIGE MARKIERUNG NUR VERFEHLEN.
# Und weil sie im Bestand der EINZIGE noch tragende Weg war, sah es aus, als
# fehle der Beleg. Er fehlte nicht - er wurde mit dem falschen Massstab
# gesucht.
#
# WAS HIER GESCHIEHT: derselbe Text wird ein zweites Mal gebildet, diesmal mit
# den Regeln des Browsers, UND ES WIRD MITGESCHRIEBEN, welcher Versatz im
# QUELLTEXT zu welcher Stelle im Browsertext gehoert. Nur so laesst sich ein
# Treffer im Browsertext wieder in Quelltext-Versaetze zuruecksetzen - und die
# braucht die Einfaerbung, die auf dem Quelltext arbeitet.
# ---------------------------------------------------------------------------

#: Elemente, hinter denen der Browser eine Zeile umbricht. <br> ist der Fall
#: aus Alex' Befund; die uebrigen sind Blockelemente, zwischen denen
#: Range.toString() ebenfalls trennt.
_UMBRUCH_TAGS = frozenset((
    "br", "p", "div", "li", "tr", "blockquote", "pre",
    "h1", "h2", "h3", "h4", "h5", "h6", "dd", "dt", "table", "ul", "ol",
))


def browser_wortlaut(wurzel) -> Tuple[str, List[int]]:
    """
    Den Text eines Teilbaums so bilden, wie 'Range.toString()' ihn bildet.

    Rueckgabe: (text, versaetze). 'versaetze' hat die Laenge len(text)+1 und
    nennt zu jedem Zeichen des Browsertextes den zugehoerigen Versatz im
    Klartext (_klartext). Eingefuegte Umbrueche haben KEINE Entsprechung im
    Quelltext; sie tragen den Versatz der Stelle, an der sie stehen. Der
    Eintrag hinter dem letzten Zeichen ist die Gesamtlaenge - damit laesst
    sich auch das Ende eines Treffers zuruecksetzen.

    KEIN VERSUCH, DEN BROWSER GANZ NACHZUBAUEN. Whitespace-Faltung nach
    CSS-Regeln bleibt aussen vor: sie haengt am Stylesheet, das hier nicht
    vorliegt, und der Vergleich wird ohnehin zusaetzlich mit gefaltetem
    Leerraum versucht (_wortlaut_varianten).
    """
    aus: List[str] = []
    versaetze: List[int] = []
    lauf = [0]          # Liste, damit die innere Funktion schreiben kann

    def umbruch(quelle: int) -> None:
        # Ein Umbruch verbraucht KEIN Zeichen des Quelltextes. Zwei Umbrueche
        # hintereinander (</p></div><div><p>) wuerden den Text mit Leerzeilen
        # fuellen, die der Browser nicht setzt - deshalb wird nur ergaenzt,
        # wenn nicht schon ein Umbruch steht.
        if aus and aus[-1] != "\n":
            aus.append("\n")
            versaetze.append(quelle)

    def stueck(s: str) -> None:
        for z in s:
            aus.append(z)
            versaetze.append(lauf[0])
            lauf[0] += 1

    def gehe(el) -> None:
        if el.text:
            stueck(el.text)
        for kind in el:
            if not isinstance(kind.tag, str):
                # Kommentare und Verarbeitungsanweisungen tragen keinen Text;
                # ihr 'tail' aber schon.
                if kind.tail:
                    stueck(kind.tail)
                continue
            if kind.tag in _UMBRUCH_TAGS:
                umbruch(lauf[0])
            gehe(kind)
            if kind.tag in _UMBRUCH_TAGS:
                umbruch(lauf[0])
            if kind.tail:
                stueck(kind.tail)

    gehe(wurzel)
    versaetze.append(lauf[0])
    return ("".join(aus), versaetze)


def _benenne(elemente, grenze: int = 8) -> str:
    """
    Eine Elementfolge knapp benennen: '<div#brd-head.pun>, <div#brd-main>'.

    NUR GERUEST, NIE INHALT. Kennung und Klassenname stammen aus der
    Forensoftware und beschreiben den Seitenaufbau; ein Beitragstext steht
    nie darin. Die Ausgabe bleibt damit ohne weitere Pruefung weitergebbar -
    dieselbe Zusage wie bei tools/diag_vollzitat_anker.py.
    """
    teile = []
    for el in elemente[:grenze]:
        name = str(getattr(el, "tag", "?"))
        kennung = (el.get("id") or "") if hasattr(el, "get") else ""
        klasse = (el.get("class") or "") if hasattr(el, "get") else ""
        stueck = "<" + name
        if kennung:
            stueck += "#" + kennung
        if klasse:
            stueck += "." + ".".join(klasse.split()[:2])
        teile.append(stueck + ">")
    if len(elemente) > grenze:
        teile.append("... (%d weitere)" % (len(elemente) - grenze))
    return ", ".join(teile)


def _falte(s: str) -> str:
    """Leerraum zu je einem Leerzeichen - die Faltung, die auch CSS macht."""
    return re.sub(r"\s+", " ", s).strip()


def _wortlaut_varianten(text: str) -> List[str]:
    """
    Die Fassungen, in denen ein gespeicherter Wortlaut gesucht wird.

    IN DIESER REIHENFOLGE, und die Reihenfolge ist die Rangfolge: zuerst
    woertlich, dann ohne Rand-Leerraum, zuletzt mit gefaltetem Leerraum. Ein
    Treffer der dritten Fassung ist schwaecher als einer der ersten - deshalb
    wird nicht einfach alles gefaltet, sondern nacheinander versucht.
    """
    aus = [text]
    gestrafft = text.strip()
    if gestrafft and gestrafft != text:
        aus.append(gestrafft)
    gefaltet = _falte(text)
    if gefaltet and gefaltet not in aus:
        aus.append(gefaltet)
    return aus


def _versatz_im_block(block, ziel_traeger, ziel_art: str, ziel_versatz: int) -> Optional[int]:
    """
    Den Versatz eines Punktes (Textknoten + Position darin) im Klartext des
    Blocks bestimmen. None, wenn der Textknoten nicht zum Block gehoert.
    """
    laufend = 0
    for traeger, art, laenge in _textstuecke(block):
        if traeger is ziel_traeger and art == ziel_art:
            return laufend + max(0, min(ziel_versatz, laenge))
        laufend += laenge
    return None


# ---------------------------------------------------------------------------
# Der Finder
# ---------------------------------------------------------------------------

class AbsatzFinder:
    """
    Haelt EINEN geparsten Seitenabzug und beantwortet Fragen dazu.

    Eine Instanz je Seite (nicht je Beleg): das Zerlegen einer Themenseite mit
    bis zu 500 Beitraegen ist der teuerste Einzelschritt des Berichtsaufbaus,
    und eine Beweismittelgruppe enthaelt typischerweise mehrere Belege
    derselben Seite. Der Aufrufer (VollzitatBauer) speichert die Instanzen je
    kanonischer Adresse zwischen.
    """

    def __init__(self, body_html: str) -> None:
        """
        body_html: der <body>-Auszug des Seitenabzugs - also genau das, was
        der Envelope als 'html' ausliefert. Verwende aus_seiten_html(), um
        ihn aus den Roh-Bytes zu gewinnen; dann ist die Abgrenzung dieselbe
        wie im Auslieferungspfad.
        """
        from lxml import html as lxml_html  # spaeter Import: s. Kopf install.py

        self._wurzel = None
        self._fehler = ""
        #: Build 737: was die Annaeherung an diesem Abzug getan hat. Leer,
        #: wenn nichts zu tun war. Der Aufrufer traegt es in den Vermerk.
        self.annaeherungsbefunde = []
        # Build 729: gesetzt von _ueber_xpath, gelesen von finde().
        self._anker_grund = ""
        self._anker_bruch = ""
        if not body_html:
            self._fehler = "Seitenabzug ohne <body>-Inhalt"
            return
        # ---------------------------------------------------------------
        # BUILD 737: DER ABZUG WIRD VOR DEM ZERLEGEN AN ZWEI HTML5-REGELN
        # ANGENAEHERT, DIE libxml2 NICHT KENNT.
        #
        # Der Anker wird IM BROWSER gerechnet und HIER aufgeloest. Beide
        # muessen denselben Baum sehen. An zwei Stellen sehen sie ihn nicht:
        # der Inhalt von <noscript> ist im Browser bei eingeschaltetem
        # JavaScript ROHTEXT, und der Inhalt von <template> steht ueberhaupt
        # nicht im Baum. libxml2 zerlegt beides als gewoehnliches Markup -
        # ein nicht geschlossenes Tag darin verschluckt dann ALLES, was
        # folgt, und ein richtiger Anker zeigt ins Leere.
        #
        # GEMESSEN am 30.08.2026 gegen Chromium (Playwright, innerHTML auf
        # einen <div> - der Weg des Ermittlungsfensters), zehn Konstrukte:
        # die beiden genannten erzeugen genau das Bild aus Alex' Laeufen
        # (Browser fuenf <div>, libxml2 zwei), die Annaeherung raeumt es aus,
        # und an den acht uebrigen aendert sie nichts. Begruendung,
        # Messtabelle und die BEKANNTE GRENZE des Verfahrens stehen in
        # report_render/html5_annaeherung.py.
        #
        # WAS SIE NICHT IST: ein HTML5-Zerleger. Ein nicht geschlossenes <a>
        # im Seitenkopf bleibt abweichend - dieser Fall erzeugt allerdings
        # MEHR Elemente im Abzug als im Browser und damit ein anderes
        # Fehlerbild.
        #
        # DER ABZUG SELBST BLEIBT UNBERUEHRT. Hier wird eine Zeichenkette
        # bearbeitet, nicht die Datenbank; forensic_<uid>.db wird nur
        # gelesen. Was die Annaeherung getan hat, steht in
        # self.annaeherungsbefunde und gehoert in den Vermerk - ein stiller
        # Eingriff in die Auswertung waere genau das, was Grundregel 1
        # verbietet.
        # ---------------------------------------------------------------
        from report_render.html5_annaeherung import annaehern
        body_html, self.annaeherungsbefunde = annaehern(body_html)

        try:
            # create_parent='div' bildet den Behaelter '#forensic-viewport'
            # nach, gegen den toolbar.js den Anker gerechnet hat. Ohne ihn
            # waere der Bezugspunkt bei mehreren Wurzelelementen mehrdeutig.
            self._wurzel = lxml_html.fragment_fromstring(
                body_html, create_parent="div")
        except Exception as exc:  # lxml wirft je nach Eingabe Verschiedenes
            self._fehler = "Seitenabzug nicht zerlegbar: %s" % exc
            logger.warning("AbsatzFinder: %s", self._fehler)

    # ------------------------------------------------------------------
    @staticmethod
    def aus_seiten_html(roh: Optional[bytes]) -> "AbsatzFinder":
        """
        Einen Finder aus den Roh-Bytes von fdb.pages.html bauen.

        Der <body>-Auszug wird mit DERSELBEN Funktion gewonnen, die der
        Webserver beim Ausliefern benutzt (s. Kopf, "DER BEZUGSPUNKT DES
        XPATH"). Der Import steht bewusst hier im Rumpf und nicht oben:
        server/blob_handler zieht den halben Auslieferungspfad nach, und der
        hat im Berichtsgenerator nichts verloren, solange niemand ihn braucht.
        """
        if not roh:
            return AbsatzFinder("")
        from server.blob_handler import BlobHandler
        try:
            return AbsatzFinder(BlobHandler._extract_body(roh))
        except Exception as exc:  # pragma: no cover - defensiv
            logger.warning("AbsatzFinder: <body> nicht abgrenzbar (%s).", exc)
            return AbsatzFinder("")

    # ------------------------------------------------------------------
    @property
    def brauchbar(self) -> bool:
        return self._wurzel is not None

    @property
    def fehler(self) -> str:
        return self._fehler

    # ------------------------------------------------------------------
    def finde(self, selection: Any, element_id: Optional[str] = None) -> Fundstelle:
        """
        Den Absatz zu einer Auswahl bestimmen. Gibt IMMER eine Fundstelle
        zurueck - im schlechtesten Fall mit weg=WEG_KEINER und Begruendung.
        """
        text = auswahl_text(selection)

        if ist_uebersetzungsauswahl(selection):
            return Fundstelle(
                weg=WEG_UEBERSETZUNG, text=text,
                hinweis="Die Markierung sitzt in der maschinellen Uebersetzung "
                        "des Beitrags, nicht im gesicherten Seitenabzug. Ein "
                        "Absatz aus dem Original waere nicht die Umgebung "
                        "dieser Markierung.")

        if not self.brauchbar:
            return Fundstelle(weg=WEG_KEINER, text=text,
                              hinweis=self._fehler or "Kein Seitenabzug.")

        # BUILD 729: Der Grund wird VOR dem Versuch geleert und vom Versuch
        # gesetzt. Er wandert danach in JEDE Fundstelle - auch in die
        # erfolgreiche ueber den Wortlaut, denn dort ist er die Antwort auf
        # die Frage, warum der Sollweg nicht getragen hat.
        self._anker_grund = ""
        self._anker_bruch = ""

        treffer = self._ueber_xpath(selection, text)
        if treffer is not None:
            return treffer

        grund = self._anker_grund
        bruch = self._anker_bruch

        treffer = self._ueber_text(text, element_id)
        if treffer is not None:
            treffer.anker_grund = grund
            treffer.anker_bruch = bruch
            # Der Hinweis nennt jetzt den GEMESSENEN Grund statt der
            # pauschalen Behauptung, der Anker loese nicht auf.
            treffer.hinweis = "%s %s" % (self.grund_klartext(grund, bruch),
                                         treffer.hinweis)
            return treffer

        return Fundstelle(
            weg=WEG_KEINER, text=text, anker_grund=grund, anker_bruch=bruch,
            hinweis="Der umschliessende Absatz wurde im gesicherten "
                    "Seitenabzug nicht wiedergefunden. %s Auch der markierte "
                    "Wortlaut kommt dort nicht vor - weder woertlich noch "
                    "ohne Rand-Leerraum noch mit gefaltetem Leerraum."
                    % self.grund_klartext(grund, bruch))

    # ------------------------------------------------------------------
    @staticmethod
    def grund_klartext(grund: str, bruch: str = "") -> str:
        """Der gemessene Grund als Satz - mit Bruchstelle, wenn es eine gibt."""
        satz = GRUND_TEXT.get(grund, "")
        if not satz:
            return ""
        if grund == GRUND_ANKER_BRICHT and bruch:
            return "%s %s." % (satz, bruch.rstrip("."))
        return satz

    # ------------------------------------------------------------------
    @staticmethod
    def _anker(selection: Any) -> str:
        if not isinstance(selection, dict):
            return ""
        return str(selection.get("xpathStart") or "")

    # ------------------------------------------------------------------
    def _knoten(self, ausdruck: str):
        """
        Einen XPath relativ zur Wurzel aufloesen. None bei Fehlschlag.

        toolbar.js liefert Ausdruecke der Form './div[1]/p[2]/text()[1]'.
        libxml2 kennt sie; ein Treffer auf einen Textknoten kommt als
        'smart string' zurueck, dessen getparent()/is_text/is_tail den
        Traeger nennen - genau die Zerlegung, die _textstuecke fuehrt.
        """
        if not ausdruck:
            return None
        try:
            treffer = self._wurzel.xpath(ausdruck)
        except Exception:
            # Ein unlesbarer Ausdruck ist kein Absturzgrund: er fuehrt auf
            # WEG_TEXT und wird dort benannt.
            return None
        return treffer[0] if treffer else None

    # ------------------------------------------------------------------
    @staticmethod
    def _punkt(knoten, versatz: int):
        """
        Aus einem XPath-Treffer den Punkt (traeger, art, versatz) machen.

        Ein Textknoten-Treffer traegt is_text/is_tail; ein Element-Treffer
        (die Auswahl begann an einer Elementgrenze - der Browser liefert das,
        wenn ganze Knoten ausgewaehlt wurden) wird als Anfang seines eigenen
        Textes gewertet.
        """
        eltern = getattr(knoten, "getparent", None)
        if eltern is None:
            return None
        if getattr(knoten, "is_text", False):
            return (knoten.getparent(), "text", versatz)
        if getattr(knoten, "is_tail", False):
            return (knoten.getparent(), "tail", versatz)
        # Element: Anfang seines Inhalts.
        return (knoten, "text", 0)

    # ------------------------------------------------------------------
    def anker_bruchstelle(self, ausdruck: str) -> str:
        """
        Den Anker Schritt fuer Schritt aufloesen und sagen, WO er bricht.

        BUILD 729. Bis dahin gab es diese Auskunft nur im gesonderten
        Werkzeug tools/diag_vollzitat_anker.py - also genau dort, wo sie
        niemand sah, der einen Bericht las. Sie gehoert an die Stelle, an der
        der Anker gebraucht wird.

        WOZU DER SCHRITT UND NICHT NUR DAS SCHEITERN: Die drei moeglichen
        Bilder verlangen VERSCHIEDENES und sind nur am Bruchpunkt zu
        unterscheiden -
          ganz oben         -> der Bezugspunkt stimmt nicht (der <body>-Auszug)
          an einem Element  -> die Seite hatte im Browser mehr Elemente als
                               der Abzug: es hat etwas hineingeschrieben
          erst bei text()[] -> die Zerlegung des Textes weicht ab
        """
        schritte = [t for t in str(ausdruck or "").split("/") if t and t != "."]
        if not schritte:
            return "der Ausdruck ist leer"
        knoten = self._wurzel
        bisher = "."
        for nr, schritt in enumerate(schritte, 1):
            treffer = _SCHRITT_MUSTER.match(schritt)
            if not treffer:
                return ("Schritt %d (%r) ist kein lesbarer XPath-Schritt"
                        % (nr, schritt))
            marke, wunsch = treffer.group(1), int(treffer.group(2))
            try:
                ergebnis = knoten.xpath("./" + schritt)
            except Exception as exc:              # pragma: no cover - defensiv
                return "Schritt %d (%r) ist nicht auswertbar: %s" % (
                    nr, schritt, exc)
            if ergebnis:
                knoten = ergebnis[0]
                bisher += "/" + schritt
                continue
            # Hier bricht es. Jetzt zaehlen, was statt dessen da ist.
            if marke == "text()":
                da = len(knoten.xpath("./text()"))
                return ("Schritt %d von %d bricht bei %r: der Browser hat %d "
                        "Textknoten gezaehlt, der Abzug hat %d. Aufgeloest "
                        "bis %s. Die Zerlegung des Textes weicht ab."
                        % (nr, len(schritte), schritt, wunsch, da, bisher))
            gleiche = [k for k in knoten
                       if isinstance(getattr(k, "tag", None), str)
                       and k.tag == marke]
            if gleiche:
                # BUILD 731: NICHT NUR ZAEHLEN, SONDERN BENENNEN.
                #
                # Alex' Lauf vom 28.08.2026 ergab 25-mal denselben Bruch an
                # derselben Stelle - und die blosse Zahl ("Browser 4, Abzug
                # 2") liess offen, WELCHE zwei Elemente der Abzug hat. Genau
                # das ist aber die Angabe, mit der sich der Abzug in einem
                # Handgriff gegen das halten laesst, was der Browser zeigt.
                # Kennung und Klasse sind Geruestangaben, keine Inhalte; die
                # Ausgabe bleibt damit ohne weitere Pruefung weitergebbar.
                return ("Schritt %d von %d bricht bei %r: der Anker verlangt "
                        "das %d. <%s>, im Abzug stehen nur %d. Aufgeloest bis "
                        "%s. Im Abzug steht dort: %s. Der Browser hatte an "
                        "dieser Stelle also MEHR <%s> als der Abzug - "
                        "entweder ist zwischen Abzug und Markierung etwas in "
                        "die Seite geschrieben worden, oder der verglichene "
                        "Abzug ist nicht der, den der Ermittler gesehen hat."
                        % (nr, len(schritte), schritt, wunsch, marke,
                           len(gleiche), bisher, _benenne(gleiche), marke))
            alle = [k for k in knoten
                    if isinstance(getattr(k, "tag", None), str)]
            return ("Schritt %d von %d bricht bei %r: an dieser Stelle gibt "
                    "es im Abzug ueberhaupt kein <%s>. Im Abzug steht dort: "
                    "%s. Aufgeloest bis %s.%s"
                    % (nr, len(schritte), schritt, marke,
                       _benenne(alle) or "nichts", bisher,
                       "  BRICHT GANZ OBEN - der Bezugspunkt stimmt nicht."
                       if nr == 1 else ""))
        return "alle Schritte loesen auf"

    # ------------------------------------------------------------------
    def _ueber_xpath(self, selection: Any, text: str) -> Optional[Fundstelle]:
        if not isinstance(selection, dict):
            self._anker_grund = GRUND_OHNE_ANKER
            return None
        ausdruck = str(selection.get("xpathStart") or "")
        if not ausdruck:
            self._anker_grund = GRUND_OHNE_ANKER
            return None
        start = self._knoten(ausdruck)
        if start is None:
            self._anker_grund = GRUND_ANKER_BRICHT
            self._anker_bruch = self.anker_bruchstelle(ausdruck)
            return None
        # KEIN 'or start': ein lxml-Element ohne Kinder ist FALSCH im
        # Wahrheitstest (lxml warnt seit Version 5 ausdruecklich davor). Ein
        # Endanker, der auf ein leeres Element zeigt - etwa ein <br> -, waere
        # damit stillschweigend durch den Startanker ersetzt worden und die
        # Markierung im Bericht zu kurz gewesen.
        ende = self._knoten(str(selection.get("xpathEnd") or ""))
        if ende is None:
            ende = start

        p_start = self._punkt(start, int(selection.get("offsetStart") or 0))
        p_ende = self._punkt(ende, int(selection.get("offsetEnd") or 0))
        if p_start is None or p_ende is None:
            self._anker_grund = GRUND_KEIN_PUNKT
            return None

        block = self._block_vorfahr(p_start[0])
        if block is None:
            self._anker_grund = GRUND_KEIN_BLOCK
            return None

        von = _versatz_im_block(block, *p_start)
        bis = _versatz_im_block(block, *p_ende)

        if von is None:
            self._anker_grund = GRUND_KEIN_VERSATZ
            return None
        if bis is None or bis <= von:
            # Die Auswahl reicht ueber den Absatz hinaus (oder der Endanker
            # sitzt woanders). Dann wird ab 'von' die LAENGE DES WORTLAUTS
            # genommen - der ist bekannt und ist die Aussage der Annotation.
            bis = von + len(text) if text else von
        bis = min(bis, len(_klartext(block)))

        return Fundstelle(weg=WEG_XPATH, text=text,
                          treffer=[Treffer(block=block, von=von, bis=bis)])

    # ------------------------------------------------------------------
    def _ueber_text(self, text: str, element_id: Optional[str]) -> Optional[Fundstelle]:
        if not text:
            return None
        # Suchraum eingrenzen, wenn der Beitrag bekannt ist: element_id ist
        # 'p<post_id>' (forensic_api/annotations.py, _derive_post_id). Damit
        # trifft die Wortlautsuche nicht einen gleichlautenden Satz in einem
        # ANDEREN Beitrag derselben Seite - auf einer Themenseite mit 500
        # Beitraegen ist das ein realer Fall.
        raum = None
        if element_id:
            treffer = self._wurzel.xpath(
                ".//*[@id=$wert]", wert=str(element_id))
            if treffer:
                raum = treffer[0]
        if raum is None:
            raum = self._wurzel

        kandidaten = [
            el for el in raum.iter()
            if isinstance(getattr(el, "tag", None), str)
            and el.tag in _ABSATZ_TAGS
        ]

        # DER KLEINSTE PASSENDE BLOCK IST DER ABSATZ. 'iter()' liefert
        # Dokumentreihenfolge, also den Vorfahren VOR seinem Nachkommen; ein
        # Kandidat, der einen bereits gefundenen enthaelt, waere nur eine
        # groessere Huelle um dieselbe Stelle und wird uebergangen. Ohne diese
        # Pruefung erschiene derselbe Fund mehrfach - einmal als <p>, einmal
        # als umgebendes <td>, <li> oder <blockquote>.
        # BUILD 729: GESUCHT WIRD IM BROWSERTEXT, NICHT IM QUELLTEXT.
        #
        # 'text' stammt aus 'Range.toString().trim()' (toolbar.js Z. 1101) -
        # dort ist jedes <br> ein '\n'. Im Quelltext steht an derselben Stelle
        # nichts. Bis Build 728 wurde der Browsertext im Quelltext gesucht;
        # jede mehrzeilige Markierung konnte damit nur verfehlt werden (s.
        # Kopf von browser_wortlaut). Gesucht wird jetzt im BROWSERTEXT des
        # Blocks, und der Treffer wird ueber die mitgefuehrte Versatztabelle
        # in Quelltext-Versaetze zurueckgesetzt - denn die Einfaerbung
        # arbeitet auf dem Quelltext.
        varianten = _wortlaut_varianten(text)

        def _suche(block):
            """(von, bis, rang) im QUELLTEXT des Blocks - oder None."""
            bild, versaetze = browser_wortlaut(block)
            for rang, fassung in enumerate(varianten):
                if not fassung:
                    continue
                raum = bild if rang < 2 else _falte(bild)
                if rang < 2:
                    pos = raum.find(fassung)
                    if pos < 0:
                        continue
                    ende = pos + len(fassung)
                    return (versaetze[pos],
                            versaetze[min(ende, len(versaetze) - 1)], rang)
                # Gefaltete Fassung: die Versatztabelle passt nicht mehr
                # Zeichen fuer Zeichen. Dann wird nur noch FESTGESTELLT, dass
                # der Wortlaut in diesem Block steht, und der ganze Block
                # markiert - lieber eine zu grosse Hervorhebung als eine
                # falsch gesetzte.
                if fassung in raum:
                    return (0, len(_klartext(block)), rang)
            return None

        treffer: List[Treffer] = []
        vergeben = []
        rang_bestens = None
        for block in kandidaten:
            fund = _suche(block)
            if fund is None:
                continue
            von, bis, rang = fund
            if any(block in vorfahr.iter() for vorfahr in vergeben):
                continue
            # Nur der INNERSTE Block: enthaelt dieser einen weiteren
            # Kandidaten mit demselben Wortlaut, gehoert der Fund dorthin.
            inner = [k for k in kandidaten
                     if k is not block and k in block.iter()
                     and _suche(k) is not None]
            if inner:
                continue
            vergeben.append(block)
            treffer.append(Treffer(block=block, von=von, bis=bis))
            rang_bestens = (rang if rang_bestens is None
                            else min(rang_bestens, rang))

        if not treffer:
            return None

        # BUILD 729: Diese Saetze sagen nicht mehr, WARUM der Ankerweg
        # ausfiel - das tut jetzt finde() mit dem GEMESSENEN Grund, und
        # zweimal dieselbe Aussage in einem Satz war schon einmal zu viel.
        if len(treffer) == 1:
            hinweis = (
                "Der Absatz wurde statt dessen ueber den Wortlaut gefunden. "
                "Er kommt auf der Seite genau einmal vor, die Fundstelle ist "
                "damit eindeutig.")
        else:
            hinweis = (
                "Der Absatz wurde statt dessen ueber den Wortlaut gesucht. "
                "Er kommt auf der Seite %d MAL vor - alle Fundstellen sind "
                "wiedergegeben, welche davon markiert wurde, ist nicht "
                "entscheidbar." % len(treffer))
        if rang_bestens == 2:
            hinweis += (" Gefunden wurde er erst mit GEFALTETEM Leerraum; "
                        "die Hervorhebung umfasst deshalb den ganzen Absatz "
                        "und nicht die genaue Stelle.")
        return Fundstelle(weg=WEG_TEXT, treffer=treffer, text=text,
                          hinweis=hinweis)

    # ------------------------------------------------------------------
    @staticmethod
    def _block_vorfahr(knoten):
        """
        Vom Textknoten-Traeger aufwaerts zum naechsten Absatz-Element.

        Greift keiner der _ABSATZ_TAGS, wird der naechste Beitragsbehaelter
        genommen (_ERSATZ_KLASSEN) - lieber ein zu grosser Absatz als keiner.
        """
        el = knoten
        ersatz = None
        while el is not None:
            tag = getattr(el, "tag", None)
            if isinstance(tag, str):
                if tag in _ABSATZ_TAGS:
                    return el
                klassen = (el.get("class") or "").split()
                if ersatz is None and any(k in _ERSATZ_KLASSEN for k in klassen):
                    ersatz = el
            el = el.getparent()
        return ersatz

    # ------------------------------------------------------------------
    @staticmethod
    def post_id_von(block) -> Optional[int]:
        """
        Die Beitragsnummer zum gefundenen Absatz - aus dem Seitenabzug selbst.

        Jeder Beitrag traegt im Forum die Kennung 'p<Nummer>' am
        umschliessenden Element (Forenquelltext topic.php / viewtopic.php:
        '<div id="p<?php echo $cur_post['id'] ?>" class="blockpost...">'; in
        der Vollansicht ein '<article class="post" id="p...">') - und in der
        Vollansicht ZUSAETZLICH die innere Kennung 'pp<Nummer>' am
        '<div class="box">'. Ab Build 728 trifft beides (s. _POST_KENNUNG);
        die Nummer ist dieselbe, gleich welche zuerst erreicht wird.

        WOZU DAS GEBRAUCHT WIRD: 'annotations.post_id' ist bei
        Textmarkierungen leer - toolbar.js setzt sie dort bewusst nicht
        (Build 336: "XPath-Text-Marken bleiben null, Post-Bezug via XPath").
        Ab Build 727 schreibt die Toolbar sie mit; fuer den BESTAND bleibt
        dieser Weg der einzige. Er wird nur als RUECKFALL benutzt und der
        benutzte Weg wird ausgewiesen.

        None, wenn kein Vorfahr eine solche Kennung traegt.
        """
        el = block
        while el is not None:
            kennung = (el.get("id") or "") if hasattr(el, "get") else ""
            treffer = _POST_KENNUNG.match(kennung.strip())
            if treffer:
                return int(treffer.group(2))
            el = el.getparent()
        return None

    # ------------------------------------------------------------------
    def rendere(self, block, markierungen: Sequence[Markierung]) -> str:
        """
        Den Absatz als HTML ausgeben, mit den Markierungen hinterlegt.

        DER SEITENABZUG WIRD NICHT VERAENDERT: gearbeitet wird auf einer
        tiefen Kopie. Der Aufrufer kann denselben Block spaeter erneut und
        mit anderen Markierungen rendern (mehrere Belege im selben Absatz).

        Die Markierungen werden in UMGEKEHRTER Reihenfolge eingesetzt. Jedes
        Einsetzen verschiebt die Kindindizes im Baum; von hinten nach vorn zu
        arbeiten haelt die noch unbearbeiteten Positionen gueltig. (Derselbe
        Grund, aus dem man eine Liste rueckwaerts durchlaeuft, waehrend man
        daraus loescht.)
        """
        from lxml import etree, html as lxml_html

        if block is None:
            return ""
        kopie = copy.deepcopy(block)

        # Ueberlappungen zusammenfassen: zwei Belege koennen dieselbe Stelle
        # markieren. Ineinander verschachtelte <span> waeren gueltiges HTML,
        # aber die aeussere Farbe verdeckte die innere - im Bericht saehe es
        # aus, als gaebe es nur einen Beleg. Deshalb wird nach Beginn
        # sortiert und ueberlappender Bereich der ZUERST beginnenden
        # Markierung zugeschlagen; die zweite bekommt den Rest. Ihre Nummer
        # steht im Befund darunter ohnehin.
        sortiert = sorted(
            (m for m in markierungen if m.bis > m.von),
            key=lambda m: (m.von, m.bis))
        bereinigt: List[Markierung] = []
        for m in sortiert:
            if bereinigt and m.von < bereinigt[-1].bis:
                m = Markierung(von=bereinigt[-1].bis, bis=m.bis,
                               css_klasse=m.css_klasse, farbe=m.farbe,
                               nummer=m.nummer)
                if m.bis <= m.von:
                    continue
            bereinigt.append(m)

        for m in reversed(bereinigt):
            self._einfaerben(kopie, m)

        roh = lxml_html.tostring(kopie, encoding="unicode", method="html")
        return roh

    # ------------------------------------------------------------------
    @staticmethod
    def _einfaerben(kopie, m: Markierung) -> None:
        """Einen Bereich [von, bis) im Klartext der Kopie mit <span> umgeben."""
        from lxml import etree

        laufend = 0
        # Von hinten nach vorn ueber die Textstuecke: ein eingesetztes <span>
        # aendert die Indizes der FOLGENDEN Geschwister, nicht der
        # vorangehenden.
        stuecke = _textstuecke(kopie)
        grenzen = []
        for traeger, art, laenge in stuecke:
            grenzen.append((laufend, laufend + laenge, traeger, art))
            laufend += laenge

        for beginn, ende, traeger, art in reversed(grenzen):
            von = max(m.von, beginn)
            bis = min(m.bis, ende)
            if bis <= von:
                continue
            lokal_von = von - beginn
            lokal_bis = bis - beginn
            inhalt = traeger.text if art == "text" else traeger.tail
            if inhalt is None:
                continue

            span = etree.Element("span")
            span.set("class", "vz-mark %s" % m.css_klasse)
            # Die Farbe steht ZUSAETZLICH als Stilangabe am Element. Der
            # HTML-Bericht braucht sie nicht (die Klasse traegt sie), aber
            # jede Weiterverarbeitung, die nur das Fragment sieht - eine in
            # ein anderes Dokument kopierte Passage etwa -, verlaere sonst
            # die Farbe. In einer Akte zaehlt, was auf dem Blatt steht.
            span.set("style", "background-color: %s;" % m.farbe)
            span.set("data-beleg", str(m.nummer))
            span.text = inhalt[lokal_von:lokal_bis]

            if art == "text":
                span.tail = inhalt[lokal_bis:]
                traeger.text = inhalt[:lokal_von]
                traeger.insert(0, span)
            else:
                span.tail = inhalt[lokal_bis:]
                traeger.tail = inhalt[:lokal_von]
                eltern = traeger.getparent()
                eltern.insert(eltern.index(traeger) + 1, span)

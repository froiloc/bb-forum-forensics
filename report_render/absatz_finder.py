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
# Version: v0.8.752 - Build: 752 - 2026-08-31
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
        self._wurzel = None
        self._fehler = ""
        #: Build 747: was VOR dem Zerlegen am Text getan wurde - seit
        #: Build 747 nur noch die <template>-Leerung. Leer, wenn nichts zu
        #: tun war. Der Aufrufer traegt es in den Vermerk.
        #:
        #: UMBENANNT von 'annaeherungsbefunde': der alte Name beschrieb ein
        #: Verfahren, das es nicht mehr gibt. Ein Name, dessen Bedeutung sich
        #: aendert, ist der zuverlaessigste Weg zu einem Auswertungsfehler -
        #: deshalb umbenannt und nicht umgedeutet.
        self.zerlegungsbefunde = []
        # Build 729: gesetzt von _ueber_xpath, gelesen von finde().
        self._anker_grund = ""
        self._anker_bruch = ""
        if not body_html:
            self._fehler = "Seitenabzug ohne <body>-Inhalt"
            return
        # ---------------------------------------------------------------
        # BUILD 747: ZERLEGT WIRD NACH DEM HTML5-STANDARD, NICHT MEHR
        # ANNAEHERND.
        #
        # Der Anker wird IM BROWSER gerechnet und HIER aufgeloest. Sehen
        # beide nicht denselben Baum, zeigt ein richtiger Anker ins Leere.
        #
        # Bis Build 746 stand hier lxml.html plus ein HANDGEBAUTER Teilnachbau
        # des HTML5-Baumaufbaus. Er bildete erst eine, dann zwei Regeln nach
        # und zerbrach dabei ueber fuenf Builds hinweg je ein Konstrukt, das
        # vorher heil war - zuletzt riss er '#page-body' nach dem zweiten
        # Beitrag auf und liess 498 Beitraege herausfallen.
        #
        # GEGENPROBE IM BROWSER am echten Abzug (31.08.2026, Chromium in der
        # Ermittlungs-VM, Belege #16 und #25): alle zwoelf Ankerschritte
        # loesen auf, '#page-body' haengt unter 'div#wrap' und traegt 500
        # direkte <article>. DER ANKER WAR RICHTIG, DER ABZUG VOLLSTAENDIG -
        # falsch war allein die Zerlegung.
        #
        # html5lib fuehrt den GANZEN Algorithmus aus, denselben wie der
        # Browser. Gemessen an 17 Konstrukten gegen Chromium: lxml roh 7,
        # lxml + Teilnachbau 16, html5lib 17. Begruendung und Messtabelle
        # stehen in report_render/html5_zerleger.py.
        #
        # KEIN RUECKFALL AUF lxml. Fehlt html5lib, bricht das hier mit einer
        # Klartextmeldung ab. Ein Werkzeug, das je nach Installationslage
        # anders zerlegt, liefert Ergebnisse, die nicht vergleichbar sind.
        #
        # DER ABZUG BLEIBT UNBERUEHRT. Was am Text getan wurde (die
        # <template>-Leerung), steht in self.zerlegungsbefunde und gehoert in
        # den Vermerk - ein stiller Eingriff waere genau das, was Grundregel 1
        # verbietet.
        # ---------------------------------------------------------------
        from report_render.html5_zerleger import Html5FehltError, Html5Zerleger

        try:
            self._wurzel, self.zerlegungsbefunde = \
                Html5Zerleger().zerlege(body_html)
        except Html5FehltError as exc:
            # Eigener Zweig: das ist ein Anlagenproblem, kein Befund ueber
            # das Beweismittel. Die beiden in einer Meldung zusammenzuziehen
            # hiesse, den leichten Fall wie den schweren aussehen zu lassen.
            self._fehler = str(exc)
            logger.error("AbsatzFinder: %s", self._fehler)
        except Exception as exc:
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

    @property
    def wurzel(self):
        """
        Der Wurzelknoten des zerlegten Abzugs - NUR LESEND gedacht.

        BUILD 754. Gebraucht von management/maintenance/annotation_pruefung.py:
        die Verifikation muss den Ausdruck bis auf den TEXTKNOTEN aufloesen,
        um den Zeichenversatz anwenden und den Wortlaut an der benannten
        Stelle vergleichen zu koennen. 'anker_teilknoten()' liefert
        ausdruecklich nur den letzten ELEMENTknoten - fuer die Frage, ob dort
        auch der markierte Wortlaut steht, reicht das nicht.

        WARUM KEIN ZWEITER BAUM: Die Verifikation koennte sich den Abzug
        selbst zerlegen. Dann gaebe es zwei Baeume aus derselben
        Zeichenkette, und jede kuenftige Aenderung am Zerleger muesste an
        zwei Stellen ankommen. Ein Messwerkzeug, das einen ANDEREN Baum misst
        als die Auswertung, misst das Falsche - und zwar unbemerkt.

        ES WIRD NICHT GESCHRIEBEN. lxml-Knoten sind veraenderbar; dass hier
        niemand hineinschreibt, ist eine Verabredung und keine Zusicherung
        des Typs. Wer es doch tut, veraendert die Auswertung aller
        nachfolgenden Fundstellen derselben Seite (der Finder wird je
        Adresse EINMAL gebaut und wiederverwendet).
        """
        return self._wurzel

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
    def anker_teilknoten(self, ausdruck: str):
        """
        Der am weitesten aufgeloeste ELEMENTknoten eines Ankers.

        Rueckgabe: (Knoten oder None, Zahl der aufgeloesten Schritte,
        Gesamtzahl der Schritte). Loest der Anker ganz auf, ist der Knoten
        der Traeger der letzten Elementstufe.

        BUILD 750. DER BEFUND, DER DAZU GEFUEHRT HAT (Alex' Gesamtlauf ueber
        zwoelf Beweismitteldatenbanken, 31.08.2026): Der haeufigste Bruch
        sitzt in der LETZTEN Stufe, bei 'text()[n]' - der Browser zaehlte in
        einem Absatz mehr Textknoten als der Abzug hat. Die Meldung sagt in
        diesen Faellen selbst: "Aufgeloest bis .../div[36]/.../p[1]".
        DER BEITRAG STEHT DAMIT LAENGST FEST. Er ist der naechste Vorfahr
        mit einer Beitragskennung - dafuer braucht es den Textknotenindex
        ueberhaupt nicht.
        Bis Build 749 fiel das Werkzeug an dieser Stelle trotzdem auf die
        WORTLAUTSUCHE zurueck. Die ist schwaecher: sie findet irgendeine
        Fundstelle mit demselben Wortlaut, notfalls in einem anderen
        Beitrag, und bei mehrfach vorkommendem Wortlaut gar keine
        ("mehrdeutig") - obwohl der Anker den Beitrag benennt.
        In Alex' Lauf betraf das 37 Belege ueber den Wortlaut und zwei als
        "von Hand zu klaeren" gemeldete, bei denen der Anker bis in den
        Beitrag hinein aufgeloest hatte.
        WARUM DAS EIN STAERKERER BELEG IST ALS DER WORTLAUT: der Anker ist
        die Positionsangabe des Ermittlers. Loest er bis in den Beitrag
        hinein auf, ist dieser Beitrag benannt - und nicht gesucht.
        """
        schritte = [t for t in str(ausdruck or "").split("/") if t and t != "."]
        if not schritte:
            return None, 0, 0
        knoten = self._wurzel
        letzter = None
        gegangen = 0
        for schritt in schritte:
            treffer = _SCHRITT_MUSTER.match(schritt)
            if not treffer:
                break
            try:
                ergebnis = knoten.xpath("./" + schritt)
            except Exception:                     # pragma: no cover - defensiv
                break
            if not ergebnis:
                break
            knoten = ergebnis[0]
            gegangen += 1
            # NUR ELEMENTE. Ein Textknoten-Treffer kommt als 'smart string'
            # zurueck; er traegt keine Kinder und ist als Ausgangspunkt fuer
            # die Vorfahrensuche unbrauchbar. Sein TRAEGER ist bereits als
            # vorheriger Schritt vermerkt.
            if isinstance(getattr(knoten, "tag", None), str):
                letzter = knoten
        return letzter, gegangen, len(schritte)

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
                # BUILD 743: DIE URSACHENLISTE IST KUERZER GEWORDEN, und das
                # gehoert in die Meldung.
                #
                # Bis Build 742 nannte sie zwei Moeglichkeiten und verschwieg
                # die haeufigste: dass die ZERLEGUNG des Abzugs die Elemente
                # falsch ablegt. Genau daran lagen in Alex' Bestand ALLE 29
                # Brueche - libxml2 zog ausstehende Endtags nicht nach, und
                # jedes folgende Geschwister rutschte eine Ebene tiefer.
                #
                # Seit Build 742 ist das behoben (report_render/
                # html5_zerleger.py). Wer diese Meldung JETZT liest, hat es
                # mit einem anderen Fall zu tun - und die Meldung soll ihn
                # nicht auf die bereits ausgeraeumte Faehrte schicken.
                #
                # WAS UEBRIG BLEIBT, sind zwei Lagen, und sie sind an der
                # Zusatzangabe unten zu unterscheiden: eine FOLGESEITE (der
                # Ermittler war auf Seite 2, verglichen wird Seite 1) und ein
                # SPAETER NEU GEZOGENER Abzug (die Seite hat sich zwischen
                # Markierung und Sicherung geaendert).
                # BUILD 746: DER SCHLUSSSATZ IST JETZT BEDINGT.
                #
                # Bis Build 745 stand 'Die Zerlegung scheidet als Ursache
                # aus' UNBEDINGT da - auch dann, wenn die Zusatzangabe davor
                # gerade eine Schachtelung gemeldet hatte, die nur aus der
                # Zerlegung stammen kann. Die Meldung widersprach sich damit
                # in zwei aufeinanderfolgenden Saetzen.
                #
                # EINE SICH WIDERSPRECHENDE MELDUNG IST SCHLIMMER ALS KEINE:
                # der Leser waehlt die Haelfte, die zu seiner Erwartung
                # passt, und haelt sie fuer belegt.
                lage = self._seitenlage(marke, wunsch, len(gleiche))
                if "INNERHALB eines anderen" in lage:
                    schluss = (" Die Zerlegung ist damit NICHT ausgeraeumt: "
                               "die Schachtelung oben kann nur von ihr "
                               "stammen. Dieser Fall gehoert gemeldet - "
                               "tools/anker_diagnose.py zeigt unter M8, an "
                               "welcher Quelltextzeile zugegriffen wurde.")
                else:
                    schluss = (" Die Zerlegung scheidet als Ursache aus - sie "
                               "ist seit Build 742 an die Browser-Regeln "
                               "angeglichen, und der Anker loest bis hierher "
                               "auf. Bleibt zweierlei: der Ermittler war auf "
                               "einer ANDEREN SEITE des Themas als der "
                               "verglichene Abzug, oder der Abzug ist SPAETER "
                               "neu gezogen worden als die Markierung.")
                return ("Schritt %d von %d bricht bei %r: der Anker verlangt "
                        "das %d. <%s>, im Abzug stehen nur %d. Aufgeloest bis "
                        "%s. Im Abzug steht dort: %s.%s%s"
                        % (nr, len(schritte), schritt, wunsch, marke,
                           len(gleiche), bisher, _benenne(gleiche),
                           lage, schluss))
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
    def _seitenlage(self, marke: str, wunsch: int, da: int) -> str:
        """
        Bei einem Bruch an einem Beitragsschritt: was sagt die SEITE selbst?

        BUILD 743. Bricht der Anker daran, dass er den 29. <article> verlangt
        und der Abzug nur zwei hat, sind zwei Lagen zu unterscheiden - und
        die Seite traegt die Angaben, mit denen das geht:

          * WIE VIELE Beitraege hat die Seite INSGESAMT? Steht die Zahl im
            Bereich des Ankers, ist der Abzug eine andere Seite des Themas;
            deckt sie sich mit dem, was an der Bruchstelle steht, ist es
            dieselbe Seite in anderem Zustand.
          * WELCHE Beitragsnummern stehen darin? Zwei niedrige Nummern in
            einem Thema, dessen Markierungen fuenfstellige tragen, sprechen
            fuer eine andere Seite.

        BUILD 744 - DIE DRITTE ANGABE, UND SIE IST DIE ENTSCHEIDENDE:

          * WIE VIELE der Beitraege stehen INNERHALB eines anderen
            <article>? Ein <article> gehoert nicht in ein <article>; steht
            es dort, hat die ZERLEGUNG sie ineinandergeschoben. Dann ist es
            ein Auswertungsfehler und im Code zu beheben. Steht KEINES in
            einem anderen, scheidet das aus - dann stehen die Beitraege
            nebeneinander, nur nicht dort, wo der Anker sie sucht, und der
            verglichene Abzug ist ein anderer als der gesehene.

        Erst diese Zahl trennt die beiden Lagen. Die ersten beiden Angaben
        allein lassen beide Deutungen zu - und eine Angabe, die jede Deutung
        zulaesst, wird nach der gedeutet, die man ohnehin erwartet hat.

        DIE ANGABE DEUTET NICHT, sie zaehlt. Was daraus folgt, entscheidet
        die Sichtpruefung - hier wird nur zusammengetragen, was ohne
        Vermutung zu haben ist.
        """
        if marke != "article" or self._wurzel is None:
            return ""
        try:
            alle = self._wurzel.xpath("//article")
        except Exception:                     # pragma: no cover - defensiv
            return ""
        nummern = []
        for el in alle:
            treffer = _POST_KENNUNG.match(str(el.get("id") or ""))
            if treffer:
                nummern.append(int(treffer.group(2)))
        if not alle:
            return ""
        auszug = ", ".join(str(n) for n in nummern[:6])
        if len(nummern) > 6:
            auszug += ", ..."

        # -- Die Schachtelungszaehlung ------------------------------------
        # Gezaehlt wird ueber die Vorfahrenkette und nicht mit einem
        # XPath-Ausdruck wie '//article//article': der zaehlte zwar
        # dasselbe, sagte aber nichts ueber die TIEFE - und die Tiefe
        # unterscheidet 'eine Ebene verrutscht' von 'eine Kaskade'.
        verschachtelt = 0
        tiefste = 0
        for el in alle:
            n = 0
            eltern = el.getparent()
            schranke = 5000
            while eltern is not None and schranke:
                if str(getattr(eltern, "tag", "")).lower() == "article":
                    n += 1
                eltern = eltern.getparent()
                schranke -= 1
            if n:
                verschachtelt += 1
            if n > tiefste:
                tiefste = n

        if verschachtelt:
            # BUILD 746 - DIE BEGRUENDUNG BERICHTIGT. Bis Build 745 stand
            # hier 'ein <article> gehoert nicht in ein <article>'. DAS IST
            # FALSCH: HTML5 erlaubt beides ausdruecklich (ein Kommentar in
            # einem Beitrag ist genau das). Die Aussage stuetzt sich nicht
            # auf den Standard, sondern auf die VORLAGE DIESES FORUMS, in
            # der ein Beitrag ein flaches <article class="post"> ist - und
            # ein fallbezogener Beleg gehoert als solcher benannt.
            lage = (" %d davon stehen INNERHALB eines anderen <article> "
                    "(tiefste Schachtelung: %d). In der Vorlage dieses "
                    "Forums steht ein Beitrag als flaches "
                    "<article class=\"post\">; eines im anderen kommt dort "
                    "nicht vor. Die Schachtelung stammt also aus der "
                    "Zerlegung." % (verschachtelt, tiefste))
        else:
            lage = (" KEINES davon steht innerhalb eines anderen <article> - "
                    "eine Kaskade der Zerlegung scheidet damit aus.")

        return (" Die ganze Seite traegt %d <article>%s. Der Anker verlangt "
                "den %d.%s" % (len(alle),
                               (" (Nummern: %s)" % auszug) if auszug else "",
                               wunsch, lage))

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

        BUILD 751: die Suche selbst steht jetzt in 'post_behaelter_von' -
        diese Methode ist nur noch die Nummer dazu. Der Grund ist die
        Kreuzprobe (s. dort): wer pruefen will, OB der markierte Wortlaut in
        dem benannten Beitrag steht, braucht nicht die Nummer, sondern das
        ELEMENT. Beides aus einer Quelle zu nehmen ist die einzige Weise, in
        der die Probe ueber denselben Beitrag redet wie die Eintragung.
        """
        behaelter = AbsatzFinder.post_behaelter_von(block)
        if behaelter is None:
            return None
        treffer = _POST_KENNUNG.match(str(behaelter.get("id") or "").strip())
        return int(treffer.group(2)) if treffer else None

    # ------------------------------------------------------------------
    @staticmethod
    def post_behaelter_von(block):
        """
        Das ELEMENT, das die Beitragskennung traegt - oder None.

        Wortgleiche Suche wie bisher in 'post_id_von' (aufwaerts bis zur
        ersten Kennung 'p<Nummer>' / 'pp<Nummer>'), nur gibt sie den Knoten
        zurueck statt der Zahl.
        """
        el = block
        while el is not None:
            kennung = (el.get("id") or "") if hasattr(el, "get") else ""
            if _POST_KENNUNG.match(kennung.strip()):
                return el
            el = el.getparent()
        return None

    # ------------------------------------------------------------------
    #: Die Stufen der Naehe-Eskalation, von stark nach schwach. Sie sind
    #: zugleich die Rangfolge der Belegkraft und gehoeren in das
    #: 'selection_json' der geheilten Annotation - ohne diese Angabe steht
    #: spaeter eine Fundstelle im Bericht, deren Herkunft niemand kennt.
    NAEHE_ANKER = "anker"          # im Container, den der Ausdruck benannte
    NAEHE_GESCHWISTER = "geschwister"   # in einem Nachbarcontainer
    NAEHE_SEITE = "seite"          # irgendwo sonst auf der Seite
    NAEHE_STUFEN = (NAEHE_ANKER, NAEHE_GESCHWISTER, NAEHE_SEITE)

    @staticmethod
    def fundstellen_nach_naehe(wurzel, behaelter, wortlaut: str,
                               kandidaten=None):
        """
        Wo steht der Wortlaut - und wie weit vom benannten Container entfernt?

        Rueckgabe: (stufe, treffer) mit 'stufe' aus NAEHE_STUFEN und
        'treffer' als Liste von Containern. Findet nichts, kommt
        (None, []).

        ── WARUM NAEHE UND NICHT EINFACH SUCHEN (Weisung Alex, 05.09.2026) ──

        Derselbe Wortlaut kann mehrfach auf einer Seite stehen - am
        haeufigsten, weil ein spaeterer Beitrag einen frueheren ZITIERT.
        Eine flache Suche ueber den ganzen page BLOB liefert dann zwei
        Treffer und muss aufgeben. Die Entfernung im Baum entscheidet:
        stand der Ausdruck auf Container N und findet sich der Wortlaut in
        N und in N+40, ist N gemeint.

        DIE STUFE IST DAS MASS DER BELEGKRAFT:
          'anker'       Der Wortlaut steht in dem Container, den der
                        Ausdruck benannte. Der Ausdruck war also richtig,
                        nur die Position darin stimmte nicht. Starker Fall.
          'geschwister' Der Wortlaut steht in einem benachbarten Container.
                        Passt zu einem Indexversatz, wie ihn eingeschobene
                        Elemente erzeugen - der Ausdruck war um wenige
                        Positionen verschoben.
          'seite'       Der Wortlaut steht irgendwo sonst. Der Ausdruck
                        traegt nichts mehr bei; die Zuordnung haengt allein
                        am Inhalt.

        EINDEUTIGKEIT WIRD NICHT ERZWUNGEN. Die Methode gibt ALLE Treffer
        der ersten Stufe zurueck, die welche hat. Ob ein Treffer genuegt,
        entscheidet der Aufrufer - und nach der Vorgabe vom 05.09.2026 gilt
        ohne Rueckfrage nur, was an genau EINER Stelle steht.
        """
        roh = (wortlaut or "").strip()
        if not roh:
            return None, []
        if kandidaten is None:
            kandidaten = AbsatzFinder._container_der_seite(wurzel)

        nummer = AbsatzFinder.beitragsnummer(behaelter) \
            if behaelter is not None else None

        # Stufe 1: der benannte Container selbst.
        if behaelter is not None:
            if AbsatzFinder.wortlaut_im_beitrag(behaelter, roh) is True:
                return AbsatzFinder.NAEHE_ANKER, [behaelter]

        # Stufe 2: die Nachbarn, von innen nach aussen. Die Reihenfolge
        # ist die Dokumentreihenfolge; 'nah' heisst hier: wenige Positionen
        # entfernt. Ohne einen benannten Container entfaellt diese Stufe -
        # es gibt dann keinen Bezugspunkt, von dem aus 'nah' definiert
        # waere, und alles ist gleich weit weg.
        if behaelter is not None and kandidaten:
            try:
                pos = kandidaten.index(behaelter)
            except ValueError:
                pos = None
            if pos is not None:
                for abstand in range(1, len(kandidaten)):
                    ring = []
                    for k in (pos - abstand, pos + abstand):
                        if 0 <= k < len(kandidaten):
                            ring.append(kandidaten[k])
                    if not ring:
                        break
                    gefunden = [el for el in ring
                                if AbsatzFinder.wortlaut_im_beitrag(el, roh)
                                is True]
                    if gefunden:
                        return AbsatzFinder.NAEHE_GESCHWISTER, gefunden

        # Stufe 3: die ganze Seite. Hier zaehlt keine Naehe mehr, deshalb
        # werden ALLE Treffer gemeldet - die Zahl ist die Aussage.
        alle = [el for el in kandidaten
                if el is not behaelter
                and AbsatzFinder.wortlaut_im_beitrag(el, roh) is True]
        if alle:
            return AbsatzFinder.NAEHE_SEITE, alle
        return None, []

    @staticmethod
    def _container_der_seite(wurzel) -> List[Any]:
        """
        Alle post container einer Seite, in Dokumentreihenfolge.

        Erkannt wird ueber '^p+(\\d+)$' und NICHT ueber '^p(\\d+)$':
        viewtopic0.php Z. 975 schreibt das 'p' doppelt, einmal als Literal
        und einmal in der Ausgabe. Dieselbe Form benutzen db/forensic_db.py
        und toolbar.js (_POST_KENNUNG).

        NUR DER AEUSSERE CONTAINER JE NUMMER. Der innere 'pp<n>' liegt im
        aeusseren 'p<n>'; beide zu fuehren zaehlte jeden Beitrag doppelt und
        machte die Abstandsrechnung der zweiten Stufe unbrauchbar.
        """
        gesehen = set()
        aus: List[Any] = []
        for el in wurzel.iter():
            if not hasattr(el, "get"):
                continue
            nummer = AbsatzFinder.beitragsnummer(el)
            if nummer is None or nummer in gesehen:
                continue
            gesehen.add(nummer)
            aus.append(el)
        return aus

    @staticmethod
    def beitragsnummer(el) -> Optional[int]:
        """Die Beitragsnummer aus 'id=\"p<n>\"' oder 'id=\"pp<n>\"'."""
        if el is None or not hasattr(el, "get"):
            return None
        treffer = _POST_KENNUNG.match(str(el.get("id") or "").strip())
        return int(treffer.group(2)) if treffer else None

    @staticmethod
    def wortlaut_im_beitrag(behaelter, wortlaut: str) -> Optional[bool]:
        """
        KREUZPROBE: steht der markierte Wortlaut IN diesem Beitrag?

        True / False / None (nicht pruefbar - kein Behaelter oder kein
        brauchbarer Wortlaut).

        WARUM ES DIESE PROBE GIBT - und das ist der Kern von Build 751:

          Der Teilanker (Build 750) nimmt die Beitragsnummer aus dem am
          weitesten aufgeloesten Element des Ankers. Das ist richtig, SOLANGE
          die Elementindizes des Ankers und des Abzugs dieselben Elemente
          treffen. Alex' Ankerdiagnose vom 31.08.2026 zeigt, dass genau das
          nicht durchweg gilt: auf '/forum/pmsnew.php?mdl=topic&tid=64200'
          verlangt ein Anker 'div[54]' auf einer Ebene, die im Abzug 53
          Kinder hat; auf '...&tid=57358' verlangen zwei Anker 'div[1010]'
          und 'div[1016]', wo der Abzug 1003 Kinder hat. DER BROWSER HATTE
          DORT ALSO MEHR ZEILEN ALS DER ABZUG. Fehlen die zusaetzlichen
          Zeilen am ENDE, stimmen alle kleineren Indizes weiter; fehlen sie
          davor, zeigt JEDER groessere Index auf den falschen Beitrag - und
          zwar lautlos, weil ein falscher Beitrag genauso aussieht wie ein
          richtiger.

          WELCHE DER BEIDEN LAGEN VORLIEGT, IST NICHT GEMESSEN. Diese Probe
          misst es - nicht am Index, sondern am Inhalt: enthaelt der vom
          Anker benannte Beitrag den Wortlaut, den der Ermittler markiert
          hat, dann redet der Anker ueber diesen Beitrag. Enthaelt er ihn
          nicht, ist die Nummer nicht zu gebrauchen.

        WAS DIE PROBE NICHT KANN, und das gehoert dazu: ein 'False' beweist
        nicht, dass der Anker falsch ist. Der Wortlaut kann ueber eine
        Beitragsgrenze hinweg markiert, in einer Uebersetzung erhoben oder
        durch Sonderzeichen anders gefaltet worden sein. 'False' heisst
        deshalb NICHT 'falscher Beitrag', sondern 'nicht bestaetigt' - und
        was nicht bestaetigt ist, wird nicht eingetragen.

        Gesucht wird in denselben Fassungen wie die Wortlautsuche
        (_wortlaut_varianten): woertlich, gestrafft, gefaltet. Der Text des
        Beitrags wird ebenso gefaltet - sonst schluegen Zeilenumbruch und
        Einrueckung der Seitenvorlage die Probe, ohne dass am Inhalt etwas
        fehlte.

        ── BUILD 761: VERGLICHEN WIRD GEGEN DEN BROWSERTEXT ─────────────────

        Bis Build 760 lief der Vergleich gegen _klartext(behaelter) - die
        Verkettung von '.text' und '.tail', also den QUELLTEXT. Der
        gespeicherte Wortlaut ist aber 'Selection.toString()' aus
        toolbar.js Z. 1101 und damit die GERENDERTE Fassung: jedes <br>
        steht darin als Zeilenumbruch, im Quelltext steht dort nichts.

        GEMESSEN (04.09.2026) an '<p>Zeile eins.<br>Zeile zwei.</p>':
            gespeichert          'Zeile eins.\nZeile zwei.'
            _klartext()          'Zeile eins.Zeile zwei.'
            browser_wortlaut()   'Zeile eins.\nZeile zwei.'
            Probe gegen _klartext        -> False
            Probe gefaltet gegen gefaltet-> False
            Probe gegen Browsertext      -> True

        DIE FALTUNG RETTET NICHTS: sie macht aus dem Zeilenumbruch der
        Suchseite ein Leerzeichen, aber auf der Quelltextseite steht dort
        GAR KEIN Zeichen. 'A B' findet sich nicht in 'AB'.

        Die Rueckabwicklung steht seit Build 729 in derselben Datei,
        unmittelbar unterhalb dieser Methode. Sie wurde hier nicht benutzt.
        Folge: JEDE mehrzeilige Markierung konnte die Kreuzprobe nur
        verfehlen, und die Lagen UNKLAR und WIDERLEGT aus dem Lauf vom
        31.08.2026 (111 und 87 von 477) sind damit nicht belastbar.

        DIE BESTAETIGENDEN LAGEN BLEIBEN GUELTIG: wer den Wortlaut im
        Quelltext gefunden hat, findet ihn im Browsertext erst recht - der
        Browsertext enthaelt den Quelltext und zusaetzlich die Umbrueche.
        """
        if behaelter is None:
            return None
        roh = (wortlaut or "").strip()
        if not roh:
            return None
        inhalt, _versaetze = browser_wortlaut(behaelter)
        gefalteter_inhalt = _falte(inhalt)
        for fassung in _wortlaut_varianten(wortlaut):
            if not fassung.strip():
                continue
            if fassung in inhalt:
                return True
            if _falte(fassung) and _falte(fassung) in gefalteter_inhalt:
                return True
        return False

    # ------------------------------------------------------------------
    def beitragsreihe(self) -> List[Any]:
        """
        Alle Beitragsbehaelter des Abzugs in Dokumentreihenfolge.

        BUILD 752. Gebraucht wird sie fuer die Messung des VERSATZES: wie
        viele Beitraege liegen zwischen dem, den der Anker benennt, und dem,
        in dem der Wortlaut steht? Diese Zahl ist in BEITRAEGEN gerechnet und
        nicht in Beitragsnummern - der Abstand zweier Beitragsnummern haengt
        davon ab, wie viel im Forum dazwischen geschrieben wurde, und sagt
        ueber die Seite gar nichts.

        Die aeussere Kennung 'p<Nr>' und die innere 'pp<Nr>' bezeichnen
        DENSELBEN Beitrag (s. post_id_von). Gezaehlt wird deshalb je Nummer
        nur einmal, und zwar beim ersten Auftreten.
        """
        if self._wurzel is None:
            return []
        aus: List[Any] = []
        gesehen = set()
        for el in self._wurzel.iter():
            if not isinstance(getattr(el, "tag", None), str):
                continue
            treffer = _POST_KENNUNG.match(str(el.get("id") or "").strip())
            if not treffer:
                continue
            nummer = int(treffer.group(2))
            if nummer in gesehen:
                continue
            gesehen.add(nummer)
            aus.append(el)
        return aus

    # ------------------------------------------------------------------
    def beitragsversatz(self, von_nummer: Optional[int],
                        nach_nummer: Optional[int]) -> Optional[int]:
        """
        Wie viele Beitraege liegen zwischen zwei Nummern? None, wenn eine
        der beiden im Abzug nicht vorkommt.

        Vorzeichen: positiv, wenn 'von_nummer' WEITER UNTEN steht als
        'nach_nummer'. Genau dieses Vorzeichen ist der Messgegenstand - bei
        allen bisher gemessenen Faellen benennt der Anker einen Beitrag
        weiter unten als den, in dem der Wortlaut steht (Alex' Lauf vom
        31.08.2026: 34 von 34).

        WOZU: ist der Versatz auf einer Seite fuer alle Belege GLEICH, ist
        die Verschiebung systematisch und in EINER Zahl zu fassen. Ist er
        verschieden, ist sie es nicht. Die Unterscheidung entscheidet, ob
        sich die Anker dieser Altbestaende ueberhaupt heilen lassen - und
        sie ist zu MESSEN und nicht zu schaetzen.
        """
        if von_nummer is None or nach_nummer is None:
            return None
        stellen = {}
        for platz, el in enumerate(self.beitragsreihe()):
            treffer = _POST_KENNUNG.match(str(el.get("id") or "").strip())
            if treffer:
                stellen.setdefault(int(treffer.group(2)), platz)
        if von_nummer not in stellen or nach_nummer not in stellen:
            return None
        return stellen[von_nummer] - stellen[nach_nummer]

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

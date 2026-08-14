# =============================================================================
# report_render/quote_typen.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle 6/7: Berichts-Ausgabe
# =============================================================================
# Zweck:
#   DIE DREI ZITATVARIANTEN AN EINER STELLE. Das gebuendelte Zitatwerkzeug
#   '@cychann/editorjs-quote' laesst den Bearbeiter zwischen drei
#   Darstellungen waehlen und legt die Wahl im Feld 'type' ab. Bis Build 718
#   hat kein Renderer dieses Feld gelesen - die Auswahl hatte auf den Bericht
#   keinerlei Wirkung.
#
# DER ANLASS (Vorgang 9c41a7e6-2b58-4d03-a7f1-6e2b90c85fd4):
#   Der Zitatblock hatte zwei Datenmodelle. Das Werkzeug fuehrt {text, type},
#   die Renderer lasen {text, caption}. Was das eine fuehrt, warf das andere
#   weg. Fuer 'caption' ist der Verlust in Build 704 behoben worden
#   (Blindprobe); fuer 'type' blieb es bei einer BEDIENMOEGLICHKEIT OHNE
#   WIRKUNG - und die ist schlimmer als gar keine, weil sie eine Zusage macht,
#   die niemand einloest. Weg C (Entscheidung Alex, 13.08.2026): die Renderer
#   lesen BEIDES.
#
# WARUM DIESES MODUL UEBERHAUPT EXISTIERT - und nicht drei kleine Helfer in
#   den drei Renderern: Genau daran ist der Zitatblock schon einmal
#   zerbrochen. Zwei Stellen, die dieselbe Frage beantworten, geben irgendwann
#   zwei Antworten. Die Zuordnung steht deshalb EINMAL hier; HTML, PDF und
#   DOCX unterscheiden sich nur noch darin, WIE sie eine Variante malen, nicht
#   darin, WELCHE sie erkennen.
#
# DIE WERTE SIND GEMESSEN, NICHT ABGESCHRIEBEN. Aus dem ausgelieferten Buendel
#   static/editor/editor.bundle.js (Manifest-MD5 der Datei:
#   1d0b16dc7c823d7349170b9fba6b0d93), Stand Build 718:
#
#     var os=(n=>(n.QuotationMark="quotationMark",
#                 n.VerticalLine="verticalLine",
#                 n.Box="box", n))(os||{})
#
#     getTypeClass(e){switch(e){
#         case"quotationMark":return"blockquote_type1";
#         case"verticalLine": return"blockquote_type2";
#         case"box":          return"blockquote_type3";
#         default:            return"blockquote_type1"}}
#
#     static get DEFAULT_TYPE(){return"quotationMark"}
#
#   Und im Konstruktor:
#     type: Object.values(os).includes(e.type) && e.type || t.defaultType || s
#   - ein Wert ausserhalb der drei faellt also schon im Werkzeug auf die
#   Vorgabe zurueck.
#
# DIE VORGABE IST 'quotationMark' UND NICHT 'verticalLine'. Das ist wichtig
#   und ueberrascht: der Bericht sah einen Zitatblock bisher IMMER als
#   linksbuendiges Zitat mit senkrechtem Strich (die eine CSS-Regel in
#   html_renderer.py). Auf dem Bildschirm des Bearbeiters war derselbe Block
#   mittig gesetzt. Ein Zitat OHNE 'type' - also jedes vor dieser Aenderung
#   angelegte - wird ab jetzt als 'quotationMark' dargestellt und aendert
#   damit sein Aussehen im Bericht. DAS IST DIE ANGLEICHUNG AN DEN BILDSCHIRM
#   und keine Nebenwirkung: die Paritaet zwischen Bildschirm und Bericht ist
#   eine ausdrueckliche Zusage der Berichtsausgabe (html_renderer.py Kopf,
#   'Paritaet, §6').
#
# ES WIRD NICHTS GEAENDERT, WAS IN DER DATENBANK STEHT. 'type' wird gelesen,
#   nie geschrieben; ein fehlendes Feld bleibt fehlend. Damit ist kein
#   Migrationsschritt noetig und der Migrationsvorbehalt ab 01.07.2026 nicht
#   beruehrt. Die Berichts-Siegel bleiben ebenfalls gueltig: ReportSealer
#   hasht die ZEILEN aus report_blocks, nicht die gerenderte Ausgabe
#   (report_sealer.py, Kopf 'UMFANG DES SIEGELS').
#
# Grundregeln: GR6 (Intention kommentieren), GR10 (ein Zweck je Datei).
# Version: v0.8.719 - Build: 719 - 2026-08-13
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, Tuple

#: Die drei Werte, die das Werkzeug schreiben kann.
QUOTE_TYP_ANFUEHRUNG = "quotationMark"
QUOTE_TYP_LINIE = "verticalLine"
QUOTE_TYP_KASTEN = "box"

#: Alle gueltigen Werte - in der Reihenfolge, in der das Werkzeug sie
#: anbietet. Als Tupel, damit die Liste nicht versehentlich veraendert wird.
QUOTE_TYPEN: Tuple[str, ...] = (
    QUOTE_TYP_ANFUEHRUNG, QUOTE_TYP_LINIE, QUOTE_TYP_KASTEN,
)

#: Die Vorgabe des Werkzeugs (DEFAULT_TYPE im Buendel). Sie gilt fuer ein
#: fehlendes UND fuer ein unbekanntes 'type' - der 'default'-Zweig von
#: getTypeClass macht keinen Unterschied zwischen beidem, und dieser Spiegel
#: darf es deshalb auch nicht.
QUOTE_TYP_VORGABE = QUOTE_TYP_ANFUEHRUNG

#: Der Feldname, unter dem der normalisierte Wert im RenderedBlock landet.
#: Der Unterstrich am Anfang folgt der Konvention der uebrigen abgeleiteten
#: Felder ('_resolved_caption', '_image_url'): was hier steht, ist NICHT aus
#: der Datenbank, sondern von report_source errechnet.
QUOTE_TYP_FELD = "_quote_typ"

#: Die CSS-Klasse je Variante fuer den HTML-Bericht.
#:
#: SPRECHENDE NAMEN STATT 'blockquote_type1..3'. Der Bericht ist ein Dokument,
#: das Menschen ausserhalb der Entwicklung lesen und im Zweifel im Quelltext
#: nachsehen - eine Akte geht an die Staatsanwaltschaft. 'zitat--kasten' sagt
#: dort etwas, 'blockquote_type3' nicht. Die Zuordnung zu den Klassen des
#: Werkzeugs steht im Kopf dieser Datei, damit der Bezug nicht verlorengeht.
_CSS_KLASSEN: Dict[str, str] = {
    QUOTE_TYP_ANFUEHRUNG: "zitat--anfuehrung",
    QUOTE_TYP_LINIE: "zitat--linie",
    QUOTE_TYP_KASTEN: "zitat--kasten",
}

#: Klartextbezeichnung je Variante - fuer Ausgabeformate, die keine Stile
#: kennen, und fuer Fehlermeldungen.
_BEZEICHNUNGEN: Dict[str, str] = {
    QUOTE_TYP_ANFUEHRUNG: "Anfuehrungszeichen",
    QUOTE_TYP_LINIE: "senkrechter Strich",
    QUOTE_TYP_KASTEN: "Kasten",
}


def normalisiere(wert: Any) -> str:
    """
    Einen rohen 'type'-Wert auf einen der drei gueltigen abbilden.

    SPIEGELT getTypeClass AUS DEM BUENDEL, EINSCHLIESSLICH DES
    'default'-ZWEIGS. Ein fehlender, leerer, falsch geschriebener oder
    nicht-textlicher Wert ergibt die Vorgabe - genau wie im Werkzeug. Der
    Bericht zeigt damit dieselbe Variante wie der Bildschirm, auch im
    Fehlerfall.

    KEINE WARNUNG BEI EINEM UNBEKANNTEN WERT, und das ist eine bewusste
    Abweichung von der sonstigen Strenge dieses Bauteils (R2/R3: nichts
    verschwindet still). DER GRUND: Das Werkzeug faengt einen unbekannten Wert
    BEREITS AB - der Konstruktor prueft 'Object.values(os).includes(e.type)'
    und setzt sonst die Vorgabe. Ein solcher Wert kann den Bearbeiter also gar
    nicht erreichen; er entstuende nur durch Handarbeit im Rohmodus. Eine
    Warnung im Bericht wuerde dann etwas melden, das auf dem Bildschirm
    unsichtbar ist und keine Auswirkung hat - sie wuerde die Liste der
    Hinweise verwaessern, auf die es bei den Platzhaltern ankommt.
    """
    if isinstance(wert, str) and wert in QUOTE_TYPEN:
        return wert
    return QUOTE_TYP_VORGABE


def aus_daten(daten: Any) -> str:
    """
    Den Typ aus dem Datenteil eines Zitatblocks holen.

    Nimmt ausdruecklich ein beliebiges Objekt entgegen und nicht nur ein
    Woerterbuch: report_source legt bei unlesbarem JSON ein Ersatzobjekt an
    ({'_raw': ...}), und ein Renderer soll daran nicht scheitern.
    """
    if isinstance(daten, dict):
        return normalisiere(daten.get("type"))
    return QUOTE_TYP_VORGABE


def css_klasse(typ: Any) -> str:
    """Die CSS-Klasse fuer den HTML-Bericht."""
    return _CSS_KLASSEN[normalisiere(typ)]


def bezeichnung(typ: Any) -> str:
    """Die deutsche Bezeichnung der Variante."""
    return _BEZEICHNUNGEN[normalisiere(typ)]

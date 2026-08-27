# =============================================================================
# core/kategorie_farben.py
# IT-Forensisches Ermittlungswerkzeug - Vollzitat (Beweismittelgruppen)
# =============================================================================
# Zweck:
#   DIE KATEGORIETAFEL AN EINER STELLE. Sechs Annotationskategorien, je mit
#   Kuerzel, Langname, Bildschirmfarbe und Berichtshinterlegung. Vor dieser
#   Datei kannte Python die Kategorien nur als IDs (db/evidence_db.py,
#   VALID_CATEGORIES) und als Beschriftungen (forensic_api/userinfo.py,
#   _CAT_LABELS) - die FARBEN gab es ausschliesslich in JavaScript und CSS.
#
# DER ANLASS (Auftrag Chef-Ermittlerin, 27.08.2026, Anforderung 3):
#   "Die markierte Stelle soll in derselben Farbe wie die Annotation
#   hinterlegt sein." Der Bericht wird in Python gebaut. Ohne diese Datei
#   waere die Farbtafel dafuer ein VIERTES Mal abgeschrieben worden.
#
# SIE WAR NAEMLICH SCHON ZWEIMAL DA, und die beiden Fassungen waren bereits
#   auseinander gelaufen - nicht in den Werten, aber im Bezug:
#     toolbar/toolbar.js            Z. 532-540  (die aeltere, mit 'key')
#     userinfo/annotation_filter.js Z. 40-46    (Abschrift, ohne 'key')
#   Die Abschrift traegt den Kommentar "Beleg: toolbar/toolbar.js:499-506" -
#   eine Zeilenangabe, die um rund 35 Zeilen verrutscht ist. Der Beleg zeigte
#   also schon ins Leere, waehrend die Werte noch stimmten. Genau so faengt
#   es an.
#
# WAS DIESE DATEI DESHALB NICHT TUT: sie loescht die JS-Tafeln NICHT. Der
#   Werkzeugbalken laeuft im Browser ohne Python; ihm die Tafel zur Laufzeit
#   zu liefern hiesse, die Markierungsfarbe von einem geglueckten AJAX-Aufruf
#   abhaengig zu machen. Stattdessen ist diese Datei die FASSUNG, und
#   tests/test_kategorie_farben.py MISST die beiden JS-Tafeln daran. Laeuft
#   eine auseinander, faellt der Test - nicht der Bericht.
#
# DIE WERTE SIND GEMESSEN, NICHT ABGESCHRIEBEN. Aus toolbar/toolbar.js,
#   Stand Build 724 (Commit 9e40c38), Zeilen 532-540:
#
#     CATEGORIES: [
#       { id: "CAT_PERSON",   label: "PER", icon: "...", color: "#f5c842", ... key: "1" },
#       { id: "CAT_LOCATION", label: "LOC", icon: "...", color: "#4f8ef7", ... key: "2" },
#       { id: "CAT_176",      label: "176", icon: "...", color: "#e84040", ... key: "3" },
#       { id: "CAT_184",      label: "184", icon: "...", color: "#c040e8", ... key: "4" },
#       { id: "CAT_VICTIM",   label: "OPF", icon: "...", color: "#e87040", ... key: "5" },
#       { id: "CAT_OTHER",    label: "SON", icon: "...", color: "#40c8a0", ... key: "6" },
#     ]
#
# WARUM ES ZWEI FARBEN JE KATEGORIE GIBT.
#   'farbe' ist die Bildschirmfarbe des Werkzeugbalkens, 'hinterlegung'
#   dieselbe Farbe zu 25 % auf Weiss (s. _aufhellen). Der Grund ist NICHT
#   der Kontrast: schwarzer Text liegt auf ALLEN SECHS Vollfarben ueber dem
#   WCAG-Mindestwert 4.5:1 (gemessen: 5.14 bis 13.22 - der schlechteste ist
#   #c040e8 mit 5.14). Beides waere lesbar.
#
#   Der Grund ist der UMFANG DER MARKIERUNG in dieser Darstellung. Im
#   Werkzeugbalken liegt die Vollfarbe hinter wenigen Woertern auf dem
#   Bildschirm. Im Vollzitat kann sie sich ueber zwei, drei Zeilen laufenden
#   11-pt-Serifentextes ziehen; dort liest sie sich als eingefaerbter Balken
#   mit Text darin und nicht mehr als Text mit einer Markierung. Die
#   aufgehellte Fassung kehrt das Verhaeltnis um - der Absatz bleibt Text,
#   die Markierung bleibt erkennbar.
#
#   Die Hinterlegung ist rechnerisch aus der Bildschirmfarbe abgeleitet und
#   in _KATEGORIEN nur als ERGEBNIS mitgefuehrt, damit sie nachlesbar ist;
#   tests/test_kategorie_farben.py rechnet sie nach (KF04).
#
# DIE FARBE ALLEIN TRAEGT DIE KATEGORIE NICHT, und das ist der Grund, warum
#   im Vollzitat unter jedem Absatz die Kategorie noch einmal AUSGESCHRIEBEN
#   steht. Eine Akte wird kopiert, gefaxt und schwarzweiss gedruckt. In
#   Graustufen liegen CAT_176 (#e84040) und CAT_184 (#c040e8) 0.005
#   Helligkeitseinheiten auseinander, CAT_LOCATION und CAT_VICTIM 0.014 -
#   praktisch ununterscheidbar. Wer nur die Farbe druckt, druckt bei den
#   Kategorien 176 und 184 dasselbe. Die Farbe ordnet dem Auge die Markierung
#   dem Befund darunter zu; WELCHE Kategorie es ist, sagt das Wort.
#
# DIE REIHENFOLGE IST DIE DES WERKZEUGBALKENS (Tastenkuerzel 1-6). Sie ist
#   Teil der Zusage an den Bearbeiter und wird hier nicht umsortiert.
#
# Grundregeln: GR6 (Intention kommentieren), GR10 (ein Zweck je Datei).
# Version: v0.8.725 - Build: 725 - 2026-08-27
# =============================================================================

from __future__ import annotations

from typing import Dict, Optional, Tuple

#: Deckung der Berichtshinterlegung ueber Weiss.
#:
#: Der Wert ist gesetzt, nicht hergeleitet - es ist eine Gestaltungsfrage
#: (s. Kopf, "WARUM ES ZWEI FARBEN JE KATEGORIE GIBT"), und die hat keine
#: Rechnung, die sie beantwortet. Was PRUEFBAR ist, prueft
#: tests/test_kategorie_farben.py: bei 0.25 liegt schwarzer Text auf allen
#: sechs aufgehellten Farben bei Kontrastverhaeltnis 15.0 bis 19.0 (KF05),
#: und die sechs Hinterlegungen bleiben untereinander unterscheidbar (KF06).
#: Wird der Wert geaendert, muessen beide Tests weiter halten - das ist die
#: Schranke, innerhalb derer der Geschmack entscheiden darf.
HINTERLEGUNG_DECKUNG = 0.25


def _aufhellen(hexfarbe: str, deckung: float = HINTERLEGUNG_DECKUNG) -> str:
    """
    Eine Bildschirmfarbe mit der angegebenen Deckung ueber Weiss legen.

    Rechnung je Kanal: ergebnis = rund(farbe * deckung + 255 * (1 - deckung)).
    Das ist dieselbe Rechnung, die ein Browser fuer 'rgba(farbe, deckung)' auf
    weissem Grund ausfuehrt - die Hinterlegung im Bericht sieht damit so aus,
    wie eine halbtransparente Markierung auf dem Bildschirm aussaehe.

    ES WIRD BEWUSST EIN FESTER HEX-WERT ERZEUGT und kein 'rgba(...)': das
    Berichts-HTML muss selbstenthaltend und druckbar sein, und DOCX wie PDF
    kennen keine Transparenz. Eine Farbe, die in drei Ausgabeformaten
    verschieden aussieht, waere in einer Akte eine Falle.
    """
    hexfarbe = hexfarbe.lstrip("#")
    kanaele = (hexfarbe[0:2], hexfarbe[2:4], hexfarbe[4:6])
    werte = [
        round(int(k, 16) * deckung + 255 * (1.0 - deckung)) for k in kanaele
    ]
    return "#" + "".join(f"{w:02x}" for w in werte)


#: Die sechs Kategorien in der Reihenfolge des Werkzeugbalkens.
#: Aufbau je Eintrag:
#:   kuerzel      - dreistellige Anzeige im Werkzeugbalken ("PER")
#:   name         - Langname, wie ihn der Berichtseditor fuehrt
#:                  (userinfo/report_editor.js EVIDENCE_CATEGORY_LABELS)
#:   farbe        - Bildschirmfarbe des Werkzeugbalkens
#:   hinterlegung - dieselbe Farbe, 25 % ueber Weiss (Bericht)
#:   taste        - Tastenkuerzel im Werkzeugbalken (nur Beleg, hier ungenutzt)
_KATEGORIEN: Dict[str, Dict[str, str]] = {
    "CAT_PERSON": {
        "kuerzel": "PER",
        "name": "Persönliche Identifikationsmerkmale",
        "farbe": "#f5c842",
        "hinterlegung": "#fcf1d0",
        "taste": "1",
    },
    "CAT_LOCATION": {
        "kuerzel": "LOC",
        "name": "Ortsangaben, geografische Hinweise",
        "farbe": "#4f8ef7",
        "hinterlegung": "#d3e3fd",
        "taste": "2",
    },
    "CAT_176": {
        "kuerzel": "176",
        "name": "Relevanz §§ 176, 176a StGB",
        "farbe": "#e84040",
        "hinterlegung": "#f9cfcf",
        "taste": "3",
    },
    "CAT_184": {
        "kuerzel": "184",
        "name": "Relevanz §§ 184b, 184c StGB",
        "farbe": "#c040e8",
        "hinterlegung": "#efcff9",
        "taste": "4",
    },
    "CAT_VICTIM": {
        "kuerzel": "OPF",
        "name": "Hinweise auf mögliche Opfer",
        "farbe": "#e87040",
        "hinterlegung": "#f9dbcf",
        "taste": "5",
    },
    "CAT_OTHER": {
        "kuerzel": "SON",
        "name": "Sonstige Ermittlungsrelevanz",
        "farbe": "#40c8a0",
        "hinterlegung": "#cff1e7",
        "taste": "6",
    },
}

#: Die Kategorie-IDs in Werkzeugbalken-Reihenfolge. Als Tupel, damit die
#: Reihenfolge nicht versehentlich veraendert wird.
KATEGORIE_IDS: Tuple[str, ...] = tuple(_KATEGORIEN.keys())

#: Anzeige fuer eine Kategorie, die NICHT in der Tafel steht.
#:
#: SIE KANN VORKOMMEN, auch wenn db/evidence_db.py beim Schreiben gegen
#: VALID_CATEGORIES prueft: eine Datenbank aus einem aelteren Stand, eine
#: Handkorrektur, eine kuenftige siebte Kategorie. GR1 verlangt, dass ein
#: solcher Beleg im Bericht ERSCHEINT und als unbekannt BENANNT wird - nicht,
#: dass er wegfaellt und nicht, dass er sich als eine der sechs ausgibt.
UNBEKANNT_NAME = "Unbekannte Kategorie"
UNBEKANNT_FARBE = "#888888"
UNBEKANNT_HINTERLEGUNG = _aufhellen(UNBEKANNT_FARBE)


def ist_bekannt(kategorie: Optional[str]) -> bool:
    """True, wenn die Kategorie in der Tafel steht."""
    return isinstance(kategorie, str) and kategorie in _KATEGORIEN


def kuerzel(kategorie: Optional[str]) -> str:
    """Das dreistellige Kuerzel ("PER"). Unbekannt -> "???"."""
    eintrag = _KATEGORIEN.get(kategorie or "")
    return eintrag["kuerzel"] if eintrag else "???"


def name(kategorie: Optional[str]) -> str:
    """Der Langname ohne Kuerzel ("Ortsangaben, geografische Hinweise")."""
    eintrag = _KATEGORIEN.get(kategorie or "")
    return eintrag["name"] if eintrag else UNBEKANNT_NAME


def bezeichnung(kategorie: Optional[str]) -> str:
    """
    Kuerzel und Langname, wie sie der Berichtseditor zeigt.

    Die Form "LOC – Ortsangaben, geografische Hinweise" (mit Halbgeviertstrich)
    ist die des Editors (userinfo/report_editor.js, EVIDENCE_CATEGORY_LABELS,
    "Bug 2.66 Fix Build 162"). Bericht und Bildschirm nennen die Kategorie
    damit gleich - Paritaet, §6.

    Eine unbekannte Kategorie wird MIT IHREM ROHWERT genannt
    ("Unbekannte Kategorie 'CAT_XY'"), damit im Bericht steht, was in der
    Datenbank steht.
    """
    if not ist_bekannt(kategorie):
        return f"{UNBEKANNT_NAME} '{kategorie}'" if kategorie else UNBEKANNT_NAME
    return f"{kuerzel(kategorie)} – {name(kategorie)}"


def farbe(kategorie: Optional[str]) -> str:
    """Die Bildschirmfarbe des Werkzeugbalkens (#rrggbb)."""
    eintrag = _KATEGORIEN.get(kategorie or "")
    return eintrag["farbe"] if eintrag else UNBEKANNT_FARBE


def hinterlegung(kategorie: Optional[str]) -> str:
    """Die Berichtshinterlegung - Bildschirmfarbe, 25 % ueber Weiss."""
    eintrag = _KATEGORIEN.get(kategorie or "")
    return eintrag["hinterlegung"] if eintrag else UNBEKANNT_HINTERLEGUNG


def css_klasse(kategorie: Optional[str]) -> str:
    """
    Die CSS-Klasse fuer den HTML-Bericht ("vz-cat-CAT_LOCATION").

    Der Rohwert steckt bewusst IM KLASSENNAMEN und nicht nur in der Farbe:
    wer den Berichtsquelltext liest - und bei einer Akte tut das irgendwann
    jemand -, sieht dort, welche Kategorie gemeint war, ohne Farbwerte
    vergleichen zu muessen. Ein unbekannter Wert wird auf 'vz-cat-unbekannt'
    abgebildet, damit kein Rohwert ungeprueft in ein Attribut wandert.
    """
    return f"vz-cat-{kategorie}" if ist_bekannt(kategorie) else "vz-cat-unbekannt"

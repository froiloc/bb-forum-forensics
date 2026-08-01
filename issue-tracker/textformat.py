#!/usr/bin/env python3
# =============================================================================
# issue-tracker/textformat.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# ZWECK: Aus einem mehrzeiligen Text sicheres HTML machen.
#
# ANLASS: Vorgang d2ade5dc (mc, 2026-08-01, Prioritaet 'critical'):
#   "\n wird durch <br> ersetzt. Gern mit CSS-Unterstuetzung, so dass die
#   nachfolgende Zeile erst nach 1,5 Zeilenhoehen beginnt."
#
#   issue_detail.html gab die Textfelder als '<p>{{ ... }}</p>' aus. HTML
#   fasst jede Folge von Leerraum zu einem Leerzeichen zusammen; Absaetze und
#   Aufzaehlungen verschwanden also in der Anzeige. 13 Vorgaenge und ein
#   Kommentar im Bestand fuehren echte Zeilenumbrueche und standen in der
#   Ansicht als ein Block.
#
# WARUM DIESER BAUSTEIN EINE EIGENE DATEI IST (Grundregel 10):
#   server.py laesst sich in der Regression nicht importieren - es setzt
#   'fastapi' voraus, und das ist keine Abhaengigkeit der Testumgebung
#   (dieselbe Lage wie bei 'jsonschema', vgl. tests/test_issue_tracker_schema.py).
#   Ein Baustein, der MASKIERUNG leistet, muss aber pruefbar sein - er ist die
#   einzige Stelle, an der aus Daten HTML wird. Deshalb steht er hier und
#   kommt mit der Standardbibliothek aus: 'html.escape' statt markupsafe.
#   server.py setzt nur noch ein Markup() darum.
#
# WARUM KEIN <br> HERAUSKOMMT - GEMESSEN, NICHT VERMUTET:
#   Der Wunsch war ausdruecklich '<br> plus CSS'. Genau das habe ich zuerst
#   gebaut und im Browser nachgemessen (Chromium 1194, headless; Abstand der
#   Grundlinien der beiden Zeilen ueber den Umbruch hinweg, bei 16px Schrift
#   und line-height 1.5, also 24px Zeilenhoehe):
#
#     br{content:'';display:block;margin-top:.75em}      24.0px = 1.00 Zeilen
#     dasselbe ohne white-space:pre-line                  24.0px = 1.00
#     br{display:block;margin-top:.75em}                  24.0px = 1.00
#     p{white-space:pre-line;line-height:1.5}             24.0px = 1.00
#     br::after{content:'';display:block;margin-top:...}  24.0px = 1.00
#     Zeile als eigener Block mit margin-top: .75em       36.0px = 1.50  <--
#
#   Ein <br> ist im Layout kein Kasten; Aussenabstaende greifen daran nicht.
#   Der zweite Teil des Wunsches - die 1,5 Zeilenhoehen - ist mit <br> also
#   NICHT zu haben, gleich wie das CSS aussieht. Deshalb bekommt jede Zeile
#   ein eigenes Blockelement. Gemessen ergibt das exakt die gewuenschten
#   36px = 1,5 Zeilenhoehen (CSS in base.html).
#
# Version: v0.8.647 - Build: 647 - 2026-08-01
# =============================================================================

import html
from typing import Any

#: Klasse jeder einzelnen Zeile. Steht hier und in base.html - und nur hier
#: und dort.
ZEILEN_KLASSE = "zeile"


def zeilen_html(text: Any) -> str:
    """
    Macht aus einem mehrzeiligen Text eine Folge von Zeilen-Bloecken.

    ZUERST MASKIEREN, DANN AUSZEICHNEN - das ist die ganze Sicherheitsregel
    dieses Bausteins, und sie steht in dieser Reihenfolge in genau einer
    Zeile Code weiter unten.

    Der naheliegende Weg in der Vorlage waere gewesen:
        {{ text|replace("\\n", "<br>")|safe }}
    DAS WAERE EINE LUECKE. '|safe' schaltet die Maskierung fuer den GANZEN
    Text ab - also auch fuer alles, was jemand eingetippt hat. Ein '<script>'
    in einer Beschreibung liefe danach im Browser des naechsten Ermittlers.
    In einem Werkzeug, dessen Inhalte woertlich aus einem beschlagnahmten
    Forum stammen, ist das keine theoretische Sorge: dort steht Text, den
    Beschuldigte geschrieben haben.

    Args:
        text: beliebiger Wert. None und '' ergeben eine leere Zeichenkette.

    Returns:
        HTML als str. Das gesamte Markup stammt aus DIESER Datei; aus den
        Daten kann keines kommen.
    """
    if text is None:
        return ""

    roh = str(text)
    if roh == "":
        return ""

    # Reihenfolge mit Bedacht: \r\n zuerst, sonst entstuenden zwei Umbrueche.
    # Alle drei Schreibweisen kommen vor - der Bestand ist UTF-8 und stammt
    # aus verschiedenen Betriebssystemen.
    vereinheitlicht = roh.replace("\r\n", "\n").replace("\r", "\n")

    return "".join(
        f'<span class="{ZEILEN_KLASSE}">{html.escape(zeile)}</span>'
        for zeile in vereinheitlicht.split("\n")
    )

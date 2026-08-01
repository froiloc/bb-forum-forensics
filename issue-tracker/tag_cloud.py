#!/usr/bin/env python3
# =============================================================================
# issue-tracker/tag_cloud.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# ZWECK: Aus den Tags aller Vorgaenge eine Wolke bilden - Tag, Anzahl, Groesse.
#
# ANLASS: Vorgang 2d692c67 (mc, 2026-08-01):
#   "Ich pflege zwar Tags im Issue-Tracker, aber weder werden die im Dashboard
#    angezeigt, noch kann ich nach diesen filtern oder suchen. Ich moechte eine
#    Visualisierung der Tags haben. [...] Diese agiert auch gleichzeitig als
#    Filter fuer die Tickets."
#
# EIGENE DATEI, weil server.py 'fastapi' voraussetzt und in der Regression
#   nicht importierbar ist (vgl. textformat.py und die Begruendung in
#   tests/test_issue_tracker_schema.py zu 'jsonschema'). Dieser Baustein
#   kommt mit der Standardbibliothek aus und ist damit unmittelbar pruefbar.
#   Zugleich Grundregel 10.
#
# Version: v0.8.647 - Build: 647 - 2026-08-01
# =============================================================================

import math
from typing import Any, Dict, List

#: Anzahl der Groessenstufen. Fuenf, weil mehr Stufen bei den Haeufigkeiten
#: dieses Bestands (160 Tags, der groesste kommt 39x vor, 89 kommen genau 1x
#: vor) keinen sichtbaren Unterschied mehr machen, sondern nur Rauschen.
STUFEN = 5


def tag_wolke(issues: List[Dict[str, Any]], stufen: int = STUFEN) -> List[Dict[str, Any]]:
    """
    Bildet die Tag-Wolke: jedes Tag mit Anzahl und Groessenstufe.

    DREI ENTSCHEIDUNGEN, die hier getroffen werden und deshalb hier erklaert
    gehoeren:

    (1) ZUSAMMENGEFASST WIRD OHNE RUECKSICHT AUF GROSS- UND KLEINSCHREIBUNG.
        Die Tags sind von Hand gepflegt; im Bestand stehen Schreibweisen
        nebeneinander, die dasselbe Thema meinen. Angezeigt wird die
        HAEUFIGSTE Schreibweise - nicht die erste, nicht die
        kleingeschriebene: die haeufigste ist die, auf die sich die Pflege
        eingependelt hat. Bei Gleichstand entscheidet die alphabetische
        Ordnung, damit dieselbe Datei immer dieselbe Wolke ergibt.

    (2) EIN TAG ZAEHLT JE VORGANG EINMAL, auch wenn es dort doppelt steht -
        sonst waere ein Pflegefehler eine Aussage ueber die Haeufigkeit.

    (3) GESTUFT WIRD LOGARITHMISCH NACH DER ANZAHL - und das ist ein Befund
        aus dem ersten Lauf, kein Lehrbuchzitat. Zuerst hatte ich nach dem
        RANG gestuft (das haeufigste Fuenftel in die oberste Stufe usw.).
        GEMESSEN am Bestand von Build 646 ergab das
        {Stufe 4: 40 Tags, 3: 40, 2: 40, 1: 39, 0: 1} - und darunter Tags mit
        DERSELBEN Anzahl in VERSCHIEDENEN Stufen, je nachdem, wo die Grenze
        zufaellig fiel. Eine Anzeige, die gleiche Daten verschieden
        darstellt, ist eine Falschaussage.

        Logarithmisch, weil eine Stufung proportional zur Anzahl bei dieser
        Verteilung unlesbar waere: ein Riese neben lauter Winzlingen. Der
        Logarithmus spreizt den unteren Bereich, in dem hier fast alles
        liegt. GLEICHE ANZAHL ERGIBT IMMER DIESELBE STUFE - das ist die
        eigentliche Zusage dieser Funktion.

    Returns:
        Liste aus {'tag', 'anzahl', 'stufe'}, alphabetisch sortiert.
        Alphabetisch, weil eine Wolke zum SUCHEN da ist; nach Haeufigkeit
        sortiert muesste man jedes Mal die ganze Wolke absuchen.
    """
    haeufigkeit: Dict[str, int] = {}
    schreibweisen: Dict[str, Dict[str, int]] = {}

    for issue in issues:
        gesehen = set()
        for roh in issue.get("tags") or []:
            tag = str(roh).strip()
            if not tag:
                continue
            schluessel = tag.lower()
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            haeufigkeit[schluessel] = haeufigkeit.get(schluessel, 0) + 1
            schreibweisen.setdefault(schluessel, {})
            schreibweisen[schluessel][tag] = schreibweisen[schluessel].get(tag, 0) + 1

    if not haeufigkeit:
        return []

    stufen = max(1, int(stufen))
    kleinste = min(haeufigkeit.values())
    groesste = max(haeufigkeit.values())

    def _stufe(anzahl: int) -> int:
        # Alle gleich haeufig -> alle gleich gross. Ohne diesen Fall teilte
        # die Rechnung unten durch null.
        if groesste == kleinste or stufen == 1:
            return stufen - 1
        anteil = ((math.log(anzahl) - math.log(kleinste))
                  / (math.log(groesste) - math.log(kleinste)))
        return max(0, min(stufen - 1, round(anteil * (stufen - 1))))

    wolke = []
    for schluessel, anzahl in haeufigkeit.items():
        varianten = schreibweisen[schluessel]
        anzeige = sorted(varianten.items(), key=lambda p: (-p[1], p[0]))[0][0]
        wolke.append({
            "tag": anzeige,
            "anzahl": anzahl,
            "stufe": _stufe(anzahl),
        })

    wolke.sort(key=lambda e: e["tag"].lower())
    return wolke

"""
forensic_api/db_guard.py
IT-Forensisches Ermittlungswerkzeug — Schutzhuelle fuer Datenendpunkte
=============================================================================
Zweck (Build 578):
    Eine gemeinsame Huelle fuer Endpunkte, die eine NEBENDATENBANK oeffnen
    (templates.db, default.db, assets.db ...). Sie verwandelt einen
    Zugriffsfehler in eine BENANNTE Antwort statt in einen Verbindungsabbruch.

ANLASS — ein Vorfall vom 2026-07-30:
    Im Berichtseditor liessen sich Bausteine, Einzelplatzhalter und Vorlagen
    nicht mehr laden. Der Browser meldete ausschliesslich 'Failed to fetch' -
    kein Status, keine Kopfzeilen, kein Hinweis. Die Ursache war schlicht: die
    templates.db lag nicht mehr am erwarteten Ort (ein parallel laufender
    Prepper hatte sie verschoben).

    Der Fehler lag aber nicht dort, sondern HIER: _handle_template_list rief
    list_templates() ohne jede Fehlerbehandlung. Die Ausnahme flog aus dem
    Handler, die Verbindung starb, und der Browser konnte nichts anderes
    melden als 'gescheitert'. Die Fehlersuche kostete eine Gespraechsrunde -
    ein benannter Fehler haette es in einer Sekunde gesagt.

    Genau das verbietet Grundregel 1: kein stiller Fehlschlag. Ein Abbruch
    ohne Antwort ist die stillste Form davon, die ein HTTP-Server hat.

ZWEI ENTSCHEIDUNGEN, DIE BEGRUENDET GEHOEREN:

  1) NUR sqlite3.Error UND OSError WERDEN GEFANGEN - ausdruecklich NICHT
     'Exception'. Eine zu weite Huelle machte aus JEDEM Programmierfehler die
     Meldung 'Datenbank nicht erreichbar', und wir wuerden Phantomen
     nachjagen. Ein Fehler im Code soll weiterhin als Fehler im Code
     erscheinen.

  2) DER PFAD GEHT INS PROTOKOLL, NICHT IN DIE ANTWORT. Die Antwort nennt die
     DATENBANK und die Art des Fehlers - das genuegt, um zu handeln. Der
     vollstaendige Dateipfad steht im Serverprotokoll, wo die Betriebsleitung
     ihn braucht. So ist die Auskunft brauchbar, ohne Dateisystem-Innereien
     an den Browser zu geben.

Status 503 und nicht 500: eine fehlende Nebendatenbank ist ein Zustand der
Anlage, kein Programmfehler - und nicht 404, denn den Endpunkt gibt es sehr
wohl. Der Unterschied ist fuer die Fehlersuche wesentlich.

Version: v0.8.578 · Build: 578 · 2026-07-30
=============================================================================
"""

from __future__ import annotations

import json
import sqlite3
from typing import Callable, Optional

from core.logger import get_logger

logger = get_logger(__name__)

CODE_DB_UNAVAILABLE = "DB_UNAVAILABLE"


def db_fehler_koerper(datenbank: str, ursache: str,
                     massnahme: str = "") -> bytes:
    """
    Der Antwortkoerper. Nennt die Datenbank, die Art des Fehlers und - seit
    Build 582 - die MASSNAHME, aber weiterhin KEINEN Dateipfad der Daten
    (der steht im Protokoll).

    Warum die Massnahme in die Antwort gehoert: mc stand am 2026-07-30 vor
    der Meldung 'no such table: tdb.placeholders', waehrend die Datei da war
    und der Pfad stimmte. Die Meldung klang nach 'Datenbank fehlt' und war
    damit irrefuehrend - die eigentliche Ursache (eine nicht gelaufene
    Migration) stand nirgends. Eine Fehlermeldung, die nicht sagt, was zu
    tun ist, kostet genau so viel Zeit wie gar keine.

    Der Text nennt Tabellen- und Skriptnamen, keine Datenpfade - er ist
    Auskunft ueber die Einrichtung der Anlage, nicht ueber ihren Inhalt.
    """
    koerper = {
        "error": "Datenbank '%s' ist nicht erreichbar." % datenbank,
        "code": CODE_DB_UNAVAILABLE,
        "datenbank": datenbank,
        "ursache": ursache,
        "hinweis": (
            "Der Endpunkt existiert; die zugrundeliegende Datei ist nicht "
            "lesbar. Ein Blick ins Serverprotokoll nennt den Pfad."
        ),
    }
    if massnahme:
        koerper["massnahme"] = massnahme
    return json.dumps(koerper, ensure_ascii=False).encode("utf-8")


def geschuetzt(
    handler,
    datenbank: str,
    arbeit: Callable[[], None],
    pfad: Optional[str] = None,
) -> bool:
    """
    Fuehrt 'arbeit' aus und beantwortet Datenbankfehler BENANNT.

    -> True   wenn 'arbeit' durchgelaufen ist
    -> False  wenn ein Datenbankfehler beantwortet wurde

    'datenbank' ist der sprechende Name fuer die Antwort ('templates.db').
    'pfad' ist optional und geht NUR ins Protokoll.

    Andere Ausnahmen werden ABSICHTLICH nicht gefangen (s. Kopf): ein
    Programmierfehler soll ein Programmierfehler bleiben.
    """
    try:
        arbeit()
        return True
    except (sqlite3.Error, OSError) as exc:
        ursache = type(exc).__name__
        logger.error(
            "Datenendpunkt: Zugriff auf %s fehlgeschlagen (%s: %s)%s",
            datenbank, ursache, exc,
            (" — Pfad: %s" % pfad) if pfad else "",
        )
        handler.send_response_body(
            503,
            db_fehler_koerper(datenbank, ursache),
            content_type="application/json; charset=utf-8",
        )
        return False

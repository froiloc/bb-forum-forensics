#!/usr/bin/env python3
# =============================================================================
# management/templates_db_status.py
# IT-Forensisches Ermittlungswerkzeug — Migrationsstand der templates.db
# =============================================================================
# Zweck (Build 584):
#   Sagt in einem Aufruf, WELCHE Migrationen der templates.db angewandt sind
#   und welche fehlen — samt dem Befehl, der die Luecke schliesst.
#
# ANLASS — ein Vorfall vom 2026-07-30:
#   Die templates.db der Anlage stammte vom 13. Juli. Zwei Migrationen waren
#   nie darauf gelaufen (Build 489 und 497). Die Folge war KEIN Fehler,
#   sondern Stille: Bausteine, Vorlagen und Platzhalter blieben leer, weil die
#   Datenschicht gescheiterte Abfragen abfing und leere Listen zurueckgab.
#   Die Suche danach hat mehrere Anlaeufe gekostet.
#
#   Der Grund, warum es ueberhaupt passieren konnte: templates.db hat KEINEN
#   Migrations-Runner. Anders als die uebrigen Datenbanken (Fleet-Registrierung
#   in migration.db) sind es hier einzeln aufzurufende Skripte, die man sich
#   merken muss. Dieses Werkzeug ersetzt das Merken durch Nachsehen.
#
# ERKENNUNG OHNE REGISTER:
#   Es gibt keine Tabelle, die den Migrationsstand fuehrt. Der Stand wird
#   deshalb an SPUREN abgelesen — je Migration ein Merkmal, das sie und nur sie
#   hinterlaesst (eine Tabelle, eine Spalte, ein CHECK-Wortlaut). Das ist
#   robuster als ein Register, das jemand haendisch pflegen muesste, und es
#   funktioniert auch auf Dateien, die nie ein Register hatten.
#
# Aufruf:
#   python3 management/templates_db_status.py [--templates-db PATH]
#                                             [--config ./config.yaml]
#
# Rueckgabewert: 0 = vollstaendig, 1 = Migration(en) fehlen, 2 = Datei
#   unbrauchbar. So laesst sich der Aufruf in eine Startpruefung haengen.
#
# Version: v0.8.584 · Build: 584 · 2026-07-30
# =============================================================================

import argparse
import os
import sqlite3
import sys
from typing import List, Optional, Tuple

# Direktaufruf als Skript: das Paketverzeichnis muss im Suchpfad liegen,
# sonst findet der Import aus "management/" nichts (Muster aus
# tools/hilfe.py). Build 624 - noetig geworden mit dem Epilog-Import.
_WURZEL = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _WURZEL not in sys.path:
    sys.path.insert(0, _WURZEL)

from management.help import cli_epilog  # noqa: E402
# Build 646: Vorrangregel an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402


# Je Migration: (Bezeichnung, Build, Spur, Befehl)
# 'Spur' ist ein Paar (art, wert):
#   ("tabelle", name)          -> Tabelle muss existieren
#   ("spalte", "tab.spalte")   -> Spalte muss existieren
#   ("check", "tab:wort")      -> Wortlaut muss im CREATE-Text vorkommen
MIGRATIONEN = (
    ("module_key an report_modules", 341,
     ("spalte", "report_modules.module_key"),
     "python3 management/migrate_templates_module_key.py --templates-db {db}"),
    ("Vollstaendige Berichtsvorlagen", 388,
     ("tabelle", "report_templates"),
     "python3 management/migrate_templates_full_templates.py "
     "--templates-db {db}"),
    ("Audit-CHECK um 'query'/'template'", 421,
     ("check", "templates_audit_log:'template'"),
     "python3 management/migrate_templates_audit_check.py --templates-db {db}"),
    ("Platzhalter-Neuordnung", 489,
     ("tabelle", "placeholders"),
     "python3 -m management.migrate_templates_placeholders "
     "--templates-db {db}"),
    ("Gross-/Kleinschreibung bei der Pruefung", 497,
     ("spalte", "placeholders.validation_ci"),
     "python3 management/migrate_templates_ci.py --templates-db {db}"),
)


def _tabellen(con: sqlite3.Connection) -> List[str]:
    return [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]


def _spalten(con: sqlite3.Connection, tabelle: str) -> List[str]:
    try:
        return [r[1] for r in con.execute(
            "PRAGMA table_info(%s)" % tabelle).fetchall()]
    except sqlite3.Error:
        return []


def _create_text(con: sqlite3.Connection, tabelle: str) -> str:
    row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (tabelle,)).fetchone()
    return (row[0] or "") if row else ""


def spur_gefunden(con: sqlite3.Connection, spur: Tuple[str, str]) -> bool:
    art, wert = spur
    if art == "tabelle":
        return wert in _tabellen(con)
    if art == "spalte":
        tab, sp = wert.split(".", 1)
        return sp in _spalten(con, tab)
    if art == "check":
        tab, wort = wert.split(":", 1)
        return wort in _create_text(con, tab)
    raise ValueError("Unbekannte Spurart: %r" % art)


def bericht(con: sqlite3.Connection, db_pfad: str) -> Tuple[int, List[str]]:
    """-> (Anzahl fehlender, Zeilen des Berichts)"""
    zeilen = ["Migrationsstand: %s" % db_pfad, "-" * 62]
    fehlend = []
    for name, build, spur, befehl in MIGRATIONEN:
        da = spur_gefunden(con, spur)
        zeilen.append("  [%s] Build %-4s %s" % ("x" if da else " ", build, name))
        if not da:
            fehlend.append((name, build, befehl.format(db=db_pfad)))
    zeilen.append("-" * 62)
    if not fehlend:
        zeilen.append("Alle bekannten Migrationen sind angewandt.")
    else:
        zeilen.append("FEHLEND: %d. In dieser Reihenfolge ausfuehren "
                      "(Server vorher anhalten):" % len(fehlend))
        for name, build, befehl in fehlend:
            zeilen.append("")
            zeilen.append("  # Build %s — %s" % (build, name))
            zeilen.append("  %s" % befehl)
    return (len(fehlend), zeilen)


def _db_aus_config(pfad: str) -> Optional[str]:
    """
    paths.templates_db aus der config.yaml.

    BUILD 646 - DIE TEXTSUCHE IST WEG. Bis Build 645 hat diese Funktion die
    Datei ZEILENWEISE nach der Zeichenfolge 'templates_db:' durchsucht und
    genommen, was dahinter stand; der Kommentar nannte als Grund, ohne
    YAML-Abhaengigkeit auszukommen.

    ZWEI GRUENDE, DAS ZU BEENDEN:
      1) Der Grund traegt nicht. 'pyyaml' steht als LAUFZEIT-Abhaengigkeit in
         requirements.txt, nicht unter den Test-Abhaengigkeiten - ohne sie
         laeuft die Anlage ohnehin nicht. Und diese Datei importiert seit dem
         Rollout des Epilogs (Build 624) 'management.help.cli_epilog'.
      2) Die Suche kannte KEINE ABSCHNITTE. Sie traf die erste nicht
         auskommentierte Zeile, die 'templates_db:' enthaelt - gleich unter
         welchem Abschnitt und mit welcher Einrueckung sie stand. Fuer eine
         Statusanzeige war das tragbar; richtig war es nie.

    WAS UNVERAENDERT BLEIBT: Es wird nicht abgebrochen. Dieses Werkzeug hat
    als einziges der Vorlagen-Werkzeuge einen Vorgabewert
    ('./data/templates.db'), und dabei bleibt es - es zeigt einen Stand an
    und veraendert nichts.
    """
    return werkzeug_konfig.wert(
        "templates_db_status", _Args(pfad),
        arg_attribut="(nicht ueber ein Argument)", arg_name="--templates-db",
        config_schluessel="paths.templates_db", default=None,
        name="templates_db", wandler=str)


class _Args:
    """
    Traegt den config.yaml-Pfad in der Form, die werkzeug_konfig erwartet.

    Diese Funktion bekommt historisch nur den Pfad und nicht das
    argparse-Ergebnis; die Aufrufstelle bleibt deshalb unangetastet.
    """

    def __init__(self, config: str) -> None:
        self.config = config

def main() -> int:
    p = argparse.ArgumentParser(
        description="Migrationsstand der templates.db anzeigen.",
        epilog=cli_epilog.epilog("templates_db_status"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--templates-db", help="Pfad zur templates.db")
    p.add_argument("--config", default="./config.yaml")
    args = p.parse_args()

    db = args.templates_db or _db_aus_config(args.config) \
        or "./data/templates.db"
    if not os.path.isfile(db):
        print("templates.db nicht gefunden: %s" % db, file=sys.stderr)
        print("Pfad pruefen (config.yaml: paths.templates_db) oder "
              "setup_templates.py ausfuehren.", file=sys.stderr)
        return 2

    # BUILD 629 (Regel PY4, Vorgang 906ede75, bei der Erhebung dazugekommen): Die coordinator.db wird
    # NUR-LESEND geoeffnet. Der Dateikopf sichert das seit jeher zu -
    # durchgesetzt hat es bis Build 628 nichts: die Verbindung war
    # schreibfaehig, und die Zusage stand allein im Kommentar. Ein
    # versehentlicher Schreibversuch scheitert jetzt technisch und nicht
    # erst im Gegenlesen.
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    try:
        anzahl, zeilen = bericht(con, db)
    finally:
        con.close()
    print("\n".join(zeilen))
    return 1 if anzahl else 0


if __name__ == "__main__":
    raise SystemExit(main())

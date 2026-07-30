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
    """Liest paths.templates_db aus der config.yaml — ohne YAML-Abhaengigkeit."""
    try:
        with open(pfad, "r", encoding="utf-8") as fh:
            for zeile in fh:
                if "templates_db:" in zeile and not zeile.strip().startswith("#"):
                    teil = zeile.split(":", 1)[1].strip()
                    teil = teil.split("#", 1)[0].strip().strip('"').strip("'")
                    if teil:
                        return teil
    except OSError:
        return None
    return None


def main() -> int:
    p = argparse.ArgumentParser(
        description="Migrationsstand der templates.db anzeigen.")
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

    con = sqlite3.connect(db)
    try:
        anzahl, zeilen = bericht(con, db)
    finally:
        con.close()
    print("\n".join(zeilen))
    return 1 if anzahl else 0


if __name__ == "__main__":
    raise SystemExit(main())

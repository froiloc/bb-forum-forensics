#!/usr/bin/env python3
# =============================================================================
# management/migrate_templates_blocktyp.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Verwaltung / templates.db
# =============================================================================
# Zweck (Build 655, Ticket 5d81a0c7):
#   Ergaenzt templates.db.report_modules um ZWEI Spalten:
#       block_type TEXT NOT NULL DEFAULT 'paragraph'
#                  CHECK(block_type IN (...sechs Werte...))
#       block_data TEXT                       -- JSON, NULL erlaubt
#
#   Ein Baustein ist heute IMMER ein Absatz: report_modules fuehrt keinen
#   Blocktyp, und 'body' ist Freitext. Fuer Tabellen-Bausteine
#   (Schluessel-Wert-Paare) muss der Baustein Blocktyp UND Blockdaten fuehren.
#
# =============================================================================
# WARUM ADD COLUMN UND KEIN TABELLEN-NEUBAU
# =============================================================================
#   Dasselbe Argument wie in Build 497 (migrate_templates_ci.py:12-17): SQLite
#   fuehrt "ALTER TABLE ... ADD COLUMN ... DEFAULT ..." nicht-destruktiv aus,
#   ohne die vorhandenen CHECK-Constraints der Tabelle anzutasten. Ein Rebuild
#   waere unnoetiges Risiko - und templates.db traegt die REDAKTIONSARBEIT
#   (Bausteine, Vorlagen, Platzhalter), auch wenn sie keine Ermittlerergebnisse
#   enthaelt.
#
#   NACHGEMESSEN, NICHT ANGENOMMEN (2026-08-02, sqlite 3.45.1): ADD COLUMN mit
#   einem CHECK-Constraint ist zulaessig. Die Bestandszeilen bekommen den
#   Default 'paragraph' und erfuellen ihn damit; ein INSERT mit einem
#   unbekannten Typ scheitert danach mit 'CHECK constraint failed';
#   PRAGMA integrity_check meldet 'ok'.
#
# =============================================================================
# DER CHECK IST EINE ENTSCHEIDUNG MIT PREIS - UND DER PREIS STEHT HIER
# =============================================================================
#   mc hat den CHECK am 2026-08-02 ausdruecklich gewaehlt. Er faengt einen
#   Tippfehler im Blocktyp an der Datenbank ab, nicht erst im Browser.
#
#   DER PREIS: SQLite kann einen CHECK-Constraint NICHT aendern. Ein SIEBTER
#   Blocktyp - etwa ein neues Editor.js-Werkzeug - braucht deshalb einen
#   TABELLEN-NEUBAU und damit eine eigene Migration mit voller Zeremonie. Wer
#   das liest, weil er gerade einen Blocktyp ergaenzen will: das ist der
#   Grund, und er war bekannt.
#
#   DER WERTEVORRAT ist der Katalog aus userinfo/module_panel.js:117-122 -
#   die Blocktypen, die der Berichtseditor heute kennt. Er ist damit belegt
#   und nicht geraten.
#
# =============================================================================
# VERLUSTFREIHEIT: ES WIRD KEINE EINZIGE ZEILE ANGEFASST
# =============================================================================
#   block_data bleibt NULL. Das bedeutet ausdruecklich: "Bestandszeile, der
#   Inhalt steht in body". Kein Backfill, kein UPDATE, kein veraendertes
#   updated_at - und damit auch keine Moeglichkeit, dabei etwas zu verlieren.
#
#   Die Vorschau ist darauf vorbereitet: cockpit_baustein_vorschau.js:72-93
#   nimmt block_type/block_data, WENN sie da sind, und faellt sonst auf body
#   zurueck (Pruefkennung BV03). Genau das ist die im Ticket geforderte
#   Verlustfreiheit - ohne einen einzigen Schreibvorgang auf Bestandsdaten.
#
# Eigenschaften:
#   - IDEMPOTENT: existieren die Spalten bereits, ist der Lauf ein No-op.
#   - TEILZUSTAND: fehlt nur EINE der beiden Spalten, wird nur diese ergaenzt.
#   - BACKUP: vor der echten Aenderung nach .pre655.bak (ausser --no-backup).
#   - AUDIT: Protokollzeile action='migrate', target_type='module'.
#   - PRUEFUNG: PRAGMA integrity_check nach der Aenderung.
#
# Aufruf:
#   python management/migrate_templates_blocktyp.py --templates-db /pfad/templates.db
#   python management/migrate_templates_blocktyp.py --config ./config.yaml
#
# WARTUNGSSTUFE B (Einstufung Build 686, Vorgang da6c16d0): Der Lauf ist
#   rein additiv (ADD COLUMN) und fasst nachweislich keine Bestandszeile an;
#   er legt zuvor eine Sicherungskopie an. Deshalb KEIN Wartungsvorbehalt.
#   DIE EINSCHRAENKUNG: Das 'ALTER TABLE' braucht eine Schreibsperre; haelt
#   der Dienst die templates.db, scheitert der Lauf - ohne Schaden, aber er
#   scheitert.
#
# Version: v0.8.655 · Build: 655 · 2026-08-02
# Beleg: Ticket 5d81a0c7; Entscheidung mc 2026-08-02 (CHECK ja);
#        Bauplan_Bausteinmodule_Builds652ff_v0_1.md §6.
# =============================================================================

import argparse
import getpass
import json
import os
import shutil
import sqlite3
import sys
import time
from typing import Any, Dict

# Direktaufruf als Skript: das Paketverzeichnis muss im Suchpfad liegen
# (Muster aus tools/hilfe.py, noetig seit dem Epilog-Import in Build 624).
_WURZEL = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _WURZEL not in sys.path:
    sys.path.insert(0, _WURZEL)

from management.help import cli_epilog  # noqa: E402
# Build 643: die Vorrangregel Argument > config.yaml > Vorgabewert steht seit
# diesem Build an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402

#: Der Wertevorrat des CHECK. Belegt aus userinfo/module_panel.js:117-122.
#: WER HIER ETWAS ERGAENZT, MUSS EINE NEUE MIGRATION MIT TABELLEN-NEUBAU
#: SCHREIBEN - ein CHECK ist in SQLite nicht aenderbar.
BLOCK_TYPEN = ("paragraph", "header", "list", "table", "quote", "delimiter")

TABELLE = "report_modules"
SPALTE_TYP = "block_type"
SPALTE_DATEN = "block_data"

ADD_TYP_SQL = (
    "ALTER TABLE report_modules ADD COLUMN block_type TEXT NOT NULL "
    "DEFAULT 'paragraph' CHECK(block_type IN (%s))"
    % ", ".join("'%s'" % t for t in BLOCK_TYPEN)
)
ADD_DATEN_SQL = "ALTER TABLE report_modules ADD COLUMN block_data TEXT"


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _column_exists(con: sqlite3.Connection, table: str, column: str) -> bool:
    # PRAGMA table_info liefert je Spalte (cid, name, type, notnull, dflt, pk).
    rows = con.execute("PRAGMA table_info(%s)" % table).fetchall()
    return any(str(r[1]) == column for r in rows)


def fehlende_spalten(con: sqlite3.Connection) -> list:
    """
    Welche der beiden Spalten fehlen noch? Eigene Funktion, weil sie an drei
    Stellen gebraucht wird: fuer die Backup-Entscheidung, fuer die Migration
    selbst und fuer die Tests. Ein Teilzustand (nur EINE Spalte da) ist nicht
    vorgesehen, aber moeglich - etwa nach einem Abbruch -, und dann muss der
    zweite Lauf ihn AUFLOESEN und nicht daran scheitern.
    """
    fehlend = []
    for spalte in (SPALTE_TYP, SPALTE_DATEN):
        if not _column_exists(con, TABELLE, spalte):
            fehlend.append(spalte)
    return fehlend


def apply_migration(con: sqlite3.Connection,
                    changed_by: str = "system") -> Dict[str, Any]:
    """
    Fuehrt die Migration aus. Reine Funktion auf einer offenen Connection
    (fuer Tests direkt aufrufbar).

    Die Signatur (con, changed_by=...) ist PFLICHT: tools/migrate-dbs.py:259-262
    ruft sie so auf und faellt bei TypeError auf apply_migration(con) zurueck.

    Returns:
        {"already_migrated": bool, "added": [str, ...], "audited": bool}
    """
    if not _table_exists(con, TABELLE):
        raise RuntimeError(
            "Tabelle 'report_modules' fehlt — die Datei ist keine templates.db "
            "oder aelter als der Migrationspfad; dann ist ein Neuaufbau mit "
            "setup_templates.py der Weg.")

    fehlend = fehlende_spalten(con)
    if not fehlend:
        return {"already_migrated": True, "added": [], "audited": False}

    if SPALTE_TYP in fehlend:
        con.execute(ADD_TYP_SQL)
    if SPALTE_DATEN in fehlend:
        con.execute(ADD_DATEN_SQL)

    audited = False
    if _table_exists(con, "templates_audit_log"):
        now = int(time.time())
        con.execute(
            "INSERT INTO templates_audit_log "
            "(action, target_id, target_type, changed_by, changed_at, "
            " old_value, new_value) "
            "VALUES ('migrate', 'report_modules', 'module', ?, ?, ?, ?)",
            (changed_by, now,
             json.dumps({"schema": "report_modules"}, ensure_ascii=False),
             json.dumps({"schema": "report_modules",
                         "added_columns": fehlend,
                         "block_type_default": "paragraph",
                         "block_type_check": list(BLOCK_TYPEN)},
                        ensure_ascii=False)))
        audited = True

    con.commit()

    integ = con.execute("PRAGMA integrity_check").fetchone()[0]
    if integ != "ok":
        raise RuntimeError("[migrate-blocktyp] integrity_check: %s" % integ)

    return {"already_migrated": False, "added": fehlend, "audited": audited}


def _resolve_db_path(args) -> str:
    """
    templates.db-Pfad: Argument --templates-db > paths.templates_db > Abbruch.
    Kein Vorgabewert: ein erratener Pfad waere schlimmer als ein Abbruch.
    Die Aufloesung steht seit Build 643 in core/werkzeug_konfig.py.
    """
    return werkzeug_konfig.db_pfad(
        "migrate_templates_blocktyp", args, arg_attribut="templates_db",
        arg_name="--templates-db", config_schluessel="paths.templates_db",
        name="templates_db")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Ergaenzt templates.db.report_modules um block_type und "
                    "block_data; additiv, idempotent, mit Backup. Es wird "
                    "KEINE Bestandszeile veraendert.",
        epilog=cli_epilog.epilog("migrate_templates_blocktyp"),
        formatter_class=cli_epilog.HilfeFormat)
    parser.add_argument("--templates-db", help="Pfad zur templates.db")
    parser.add_argument("--config", default="./config.yaml",
                        help="config.yaml (Fallback fuer den Pfad)")
    parser.add_argument("--no-backup", action="store_true",
                        help="keine .pre655.bak-Kopie anlegen")
    parser.add_argument("--changed-by", default=None,
                        help="Urheber-Kennung fuer die Audit-Zeile "
                             "(Default: OS-Benutzer)")
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(args)
    if not os.path.exists(db_path):
        print("[migrate-blocktyp] templates.db nicht gefunden: %s" % db_path,
              file=sys.stderr)
        return 2

    changed_by = args.changed_by or getpass.getuser()

    # Backup nur, wenn wirklich migriert wird (kein Backup-Muell bei No-ops).
    probe = sqlite3.connect(db_path)
    try:
        will_migrate = (_table_exists(probe, TABELLE)
                        and bool(fehlende_spalten(probe)))
    finally:
        probe.close()
    if will_migrate and not args.no_backup:
        bak = db_path + ".pre655.bak"
        shutil.copy2(db_path, bak)
        print("[migrate-blocktyp] Backup: %s" % bak)

    con = sqlite3.connect(db_path)
    try:
        res = apply_migration(con, changed_by=changed_by)
    finally:
        con.close()

    if res["already_migrated"]:
        print("[migrate-blocktyp] block_type und block_data vorhanden — No-op.")
    else:
        print("[migrate-blocktyp] fertig: %s hinzugefuegt "
              "(block_type Default 'paragraph', block_data NULL = Inhalt "
              "steht in body)%s."
              % (" und ".join(res["added"]),
                 ", Audit-Zeile geschrieben" if res["audited"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

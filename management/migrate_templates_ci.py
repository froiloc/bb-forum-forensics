#!/usr/bin/env python3
# =============================================================================
# management/migrate_templates_ci.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Verwaltung / templates.db
# =============================================================================
# Zweck (Build 497):
#   Ergaenzt templates.db.placeholders um die Spalte validation_ci
#   (INTEGER NOT NULL DEFAULT 0) fuer die case-insensitive Validierung
#   (regex/list/like). 0 = Gross-/Kleinschreibung beachten (bisheriges
#   Verhalten, abwaertskompatibel), 1 = ignorieren.
#
# Warum ADD COLUMN und KEIN Tabellen-Neubau (anders als Build 489):
#   Es kommt nur eine neue, nullable-freie Spalte MIT DEFAULT hinzu. SQLite
#   fuehrt "ALTER TABLE ... ADD COLUMN ... DEFAULT 0" nicht-destruktiv aus,
#   ohne die vorhandenen CHECK-Constraints anzutasten. Bestehende Zeilen
#   erhalten automatisch 0 -> exakt das bisherige Verhalten (kein Beleg aendert
#   sich, Grundregel 1). Ein Rebuild waere unnoetiges Risiko.
#
# Eigenschaften:
#   - IDEMPOTENT: existiert die Spalte bereits, ist der Lauf ein No-op.
#   - BACKUP: vor der echten Aenderung wird templates.db nach .pre497.bak
#     kopiert (ausser --no-backup).
#   - AUDIT: schreibt (falls templates_audit_log existiert) eine Protokollzeile
#     action='migrate', target_type='placeholder'.
#   - PRUEFUNG: PRAGMA integrity_check nach der Aenderung.
#
# Aufruf:
#   python management/migrate_templates_ci.py --templates-db /pfad/templates.db
#   python management/migrate_templates_ci.py --config ./config.yaml
#
# Version: v0.8.497 · Build: 497 · 2026-07-22
# Beleg: mc-Wunsch Case-Insensitivity 2026-07-22; Bauplan Platzhalter_DB §2.3.
# =============================================================================

import argparse
import getpass
import json
import os
import shutil
import sqlite3
import sys
import time
from typing import Any, Dict, Optional

# Direktaufruf als Skript: das Paketverzeichnis muss im Suchpfad liegen,
# sonst findet der Import aus "management/" nichts (Muster aus
# tools/hilfe.py). Build 624 - noetig geworden mit dem Epilog-Import.
_WURZEL = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _WURZEL not in sys.path:
    sys.path.insert(0, _WURZEL)

from management.help import cli_epilog  # noqa: E402
# Build 643: die Vorrangregel Argument > config.yaml > Vorgabewert
# steht seit diesem Build an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402

COLUMN_NAME = "validation_ci"
ADD_COLUMN_SQL = (
    "ALTER TABLE placeholders "
    "ADD COLUMN validation_ci INTEGER NOT NULL DEFAULT 0"
)


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _column_exists(con: sqlite3.Connection, table: str, column: str) -> bool:
    # PRAGMA table_info liefert je Spalte (cid, name, type, notnull, dflt, pk).
    rows = con.execute("PRAGMA table_info(%s)" % table).fetchall()
    return any(str(r[1]) == column for r in rows)


def apply_migration(con: sqlite3.Connection,
                    changed_by: str = "system") -> Dict[str, Any]:
    """
    Fuehrt die Migration aus. Reine Funktion auf einer offenen Connection
    (fuer Tests direkt aufrufbar).

    Returns:
        {"already_migrated": bool, "audited": bool}
    """
    if not _table_exists(con, "placeholders"):
        raise RuntimeError(
            "Tabelle 'placeholders' fehlt — zuerst migrate_templates_placeholders.py "
            "(Build 489) ausfuehren.")

    if _column_exists(con, "placeholders", COLUMN_NAME):
        return {"already_migrated": True, "audited": False}

    con.execute(ADD_COLUMN_SQL)

    audited = False
    if _table_exists(con, "templates_audit_log"):
        now = int(time.time())
        con.execute(
            "INSERT INTO templates_audit_log "
            "(action, target_id, target_type, changed_by, changed_at, "
            " old_value, new_value) "
            "VALUES ('migrate', 'placeholders', 'placeholder', ?, ?, ?, ?)",
            (changed_by, now,
             json.dumps({"schema": "placeholders"}, ensure_ascii=False),
             json.dumps({"schema": "placeholders", "added_column": COLUMN_NAME,
                         "default": 0}, ensure_ascii=False)))
        audited = True

    con.commit()

    integ = con.execute("PRAGMA integrity_check").fetchone()[0]
    if integ != "ok":
        raise RuntimeError("[migrate-ci] integrity_check: %s" % integ)

    return {"already_migrated": False, "audited": audited}


def _resolve_db_path(args) -> str:
    """
    templates.db-Pfad: Argument --templates-db > paths.templates_db > Abbruch.

    BUILD 643 - DIE AUFLOESUNG IST UMGEZOGEN, das Verhalten NICHT.
    Bis Build 642 stand hier eine eigene Abschrift derselben zwoelf Zeilen;
    fuenfundzwanzig Werkzeuge trugen sie, und sie waren nicht identisch (die
    Begruendung steht im Kopf von core/werkzeug_konfig.py). Sie steht jetzt an
    EINER Stelle.

    UNVERAENDERT bleiben: die Reihenfolge, das Fehlen eines Vorgabewerts
    (ein erratener Pfad waere schlimmer als ein Abbruch), die Meldung ueber
    eine unlesbare config.yaml auf stderr und der Abbruch mit dem Praefix
    '[migrate_templates_ci]'. Die Abbruchmeldung nennt jetzt BEIDE Wege statt nur einen.
    """
    return werkzeug_konfig.db_pfad(
        "migrate_templates_ci", args, arg_attribut="templates_db", arg_name="--templates-db",
        config_schluessel="paths.templates_db", name="templates_db")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Ergaenzt templates.db.placeholders um validation_ci "
                    "(case-insensitive Validierung); idempotent, mit Backup.",
        epilog=cli_epilog.epilog("migrate_templates_ci"),
        formatter_class=cli_epilog.HilfeFormat)
    parser.add_argument("--templates-db", help="Pfad zur templates.db")
    parser.add_argument("--config", default="./config.yaml",
                        help="config.yaml (Fallback fuer den Pfad)")
    parser.add_argument("--no-backup", action="store_true",
                        help="keine .pre497.bak-Kopie anlegen")
    parser.add_argument("--changed-by", default=None,
                        help="Urheber-Kennung fuer die Audit-Zeile "
                             "(Default: OS-Benutzer)")
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(args)
    if not os.path.exists(db_path):
        print("[migrate-ci] templates.db nicht gefunden: %s" % db_path,
              file=sys.stderr)
        return 2

    changed_by = args.changed_by or getpass.getuser()

    # Backup nur, wenn wirklich migriert wird (kein Backup-Muell bei No-ops).
    probe = sqlite3.connect(db_path)
    try:
        will_migrate = (_table_exists(probe, "placeholders")
                        and not _column_exists(probe, "placeholders", COLUMN_NAME))
    finally:
        probe.close()
    if will_migrate and not args.no_backup:
        bak = db_path + ".pre497.bak"
        shutil.copy2(db_path, bak)
        print("[migrate-ci] Backup: %s" % bak)

    con = sqlite3.connect(db_path)
    try:
        res = apply_migration(con, changed_by=changed_by)
    finally:
        con.close()

    if res["already_migrated"]:
        print("[migrate-ci] Spalte validation_ci vorhanden — No-op.")
    else:
        print("[migrate-ci] fertig: Spalte validation_ci hinzugefuegt "
              "(Default 0)%s." % (", Audit-Zeile geschrieben"
                                  if res["audited"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# =============================================================================
# management/migrate_templates_audit_check.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — SF-4 (Build 421): templates_audit_log-CHECK erweitern
# =============================================================================
# Zweck:
#   Erweitert die CHECK-Constraint von templates_audit_log.target_type von
#   ('module','query') auf ('module','query','template'), damit auch die
#   Auditierung von DOKUMENTVORLAGEN (report_templates, Werkzeug W3) moeglich
#   ist. SQLite kann eine CHECK-Constraint nicht per ALTER aendern -> die
#   Tabelle wird verlustfrei neu aufgebaut (Rebuild: neue Tabelle, Zeilen
#   kopieren, alte droppen, umbenennen), in EINER Transaktion.
#
#   Idempotent: Enthaelt die CHECK bereits 'template', ist der Lauf ein No-op.
#   templates.db hat keinen Migrations-Runner (anders als coordinator/evidence);
#   dieses Skript ist - wie migrate_templates_module_key.py - standalone
#   auszufuehren.
#
# Aufruf:
#   python -m management.migrate_templates_audit_check [--templates-db PATH]
#
# Journal: journal_mode=delete (Build 408/409 — kein WAL, netzlaufwerksicher).
#
# Version: v0.7.421 · Build: 421 · 2026-07-14
# =============================================================================

import argparse
import os
import sqlite3
import sys
from typing import Any, Dict, Optional
from management.help import cli_epilog  # noqa: E402
# Build 643: die Vorrangregel Argument > config.yaml > Vorgabewert
# steht seit diesem Build an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402

# Ziel-DDL der neu aufgebauten Audit-Tabelle (CHECK um 'template' erweitert).
_NEW_DDL = """
CREATE TABLE templates_audit_log__new (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT    NOT NULL,
    target_id   TEXT    NOT NULL,
    target_type TEXT    NOT NULL
                CHECK (target_type IN ('module', 'query', 'template')),
    changed_by  TEXT    NOT NULL,
    changed_at  INTEGER NOT NULL,
    old_value   TEXT,
    new_value   TEXT
)
"""

_COPY_SQL = (
    "INSERT INTO templates_audit_log__new "
    "(id, action, target_id, target_type, changed_by, changed_at, "
    " old_value, new_value) "
    "SELECT id, action, target_id, target_type, changed_by, changed_at, "
    "       old_value, new_value FROM templates_audit_log"
)


def _audit_ddl(con: sqlite3.Connection) -> Optional[str]:
    row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' "
        "AND name='templates_audit_log'").fetchone()
    return row[0] if row is not None else None


def apply_migration(con: sqlite3.Connection) -> Dict[str, Any]:
    """
    Baut templates_audit_log mit erweiterter CHECK neu auf. Idempotent.
    Gibt {present, already_widened, widened} zurueck.
    """
    ddl = _audit_ddl(con)
    if ddl is None:
        raise SystemExit(
            "[migrate-audit] Tabelle 'templates_audit_log' fehlt — ist das die "
            "richtige templates.db?")

    # Idempotenz: die erweiterte CHECK enthaelt den QUOTIERTEN Wert 'template'.
    # (Der Tabellenname enthaelt zwar 'template', aber nicht den quotierten
    # Skalarwert "'template'".)
    if "'template'" in ddl:
        return {"present": True, "already_widened": True, "widened": False}

    # Explizite Transaktionssteuerung; kein WAL.
    con.isolation_level = None
    con.execute("PRAGMA journal_mode=delete")
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("BEGIN IMMEDIATE")
    try:
        con.execute("DROP TABLE IF EXISTS templates_audit_log__new")
        con.execute(_NEW_DDL)
        con.execute(_COPY_SQL)
        con.execute("DROP TABLE templates_audit_log")
        con.execute(
            "ALTER TABLE templates_audit_log__new "
            "RENAME TO templates_audit_log")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    # Inline-Verifikation: neue CHECK vorhanden.
    new_ddl = _audit_ddl(con) or ""
    if "'template'" not in new_ddl:
        raise RuntimeError(
            "[migrate-audit] CHECK-Erweiterung nicht wirksam nach dem Rebuild.")
    return {"present": True, "already_widened": False, "widened": True}


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
    '[migrate_templates_audit_check]'. Die Abbruchmeldung nennt jetzt BEIDE Wege statt nur einen.
    """
    return werkzeug_konfig.db_pfad(
        "migrate_templates_audit_check", args, arg_attribut="templates_db", arg_name="--templates-db",
        config_schluessel="paths.templates_db", name="templates_db")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Erweitert templates_audit_log.target_type-CHECK um "
                    "'template' (idempotent, verlustfreier Rebuild).",
        epilog=cli_epilog.epilog("migrate_templates_audit_check"),
        formatter_class=cli_epilog.HilfeFormat)
    parser.add_argument("--templates-db", help="Pfad zur templates.db")
    parser.add_argument("--config", default="./config.yaml",
                        help="config.yaml (Fallback fuer den Pfad)")
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(args)
    if not os.path.exists(db_path):
        print("[migrate-audit] templates.db nicht gefunden: %s" % db_path,
              file=sys.stderr)
        return 2

    con = sqlite3.connect(db_path)
    try:
        res = apply_migration(con)
    finally:
        con.close()

    if res["already_widened"]:
        print("[migrate-audit] CHECK bereits erweitert ('template') — No-op.")
    else:
        print("[migrate-audit] fertig: templates_audit_log neu aufgebaut, "
              "CHECK um 'template' erweitert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

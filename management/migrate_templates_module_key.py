# =============================================================================
# management/migrate_templates_module_key.py
# IT-Forensisches Ermittlungswerkzeug — Migration der templates.db (Build 341)
# =============================================================================
# Zweck:
#   Fuehrt report_modules.module_key ein (STABILE, reorganisationssichere
#   Kennung statt AUTOINCREMENT-id) und seedet den Rechts-Baustein
#   'legal.ki_uebersetzung' (Rechtshinweis maschinelle Uebersetzung, § 187 GVG).
#
#   IDEMPOTENT: mehrfaches Ausfuehren ist unschaedlich (Spalte/Index/Seed werden
#   nur angelegt, wenn noch nicht vorhanden). templates.db enthaelt KEINE
#   Ermittler-Ergebnisse (read-only im Betrieb) — dennoch VOR dem Ausfuehren ein
#   verifiziertes Backup anlegen (GR: besondere Sorgfalt bei Produktiv-DBs).
#
#   Aufruf:
#     python -m management.migrate_templates_module_key --templates-db PATH
#     python -m management.migrate_templates_module_key --config ./config.yaml
#
# Beleg: Bauplan Build 340/341 §5.1 (stabile Kennung auf Entwickler-Wunsch);
#        templates.db liegt ausserhalb des coordinator-Migrationsframeworks.
# =============================================================================

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from management.help import cli_epilog  # noqa: E402

MODULE_KEY = "legal.ki_uebersetzung"

LEGAL_TITLE = "Rechtshinweis maschinelle \u00dcbersetzung (\u00a7 187 GVG)"

# Wortlaut wie vom Entwickler vorgegeben (Projektgespraech 2026-07-07).
LEGAL_BODY = (
    "Die beigef\u00fcgte \u00dcbersetzung wurde maschinell erstellt und dient "
    "ausschlie\u00dflich der ersten internen Erschlie\u00dfung des "
    "fremdsprachigen Dokuments. Sie stellt keine verbindliche \u00dcbersetzung "
    "im Sinne des \u00a7 187 GVG dar. F\u00fcr eine sp\u00e4tere Verwertung als "
    "Beweismittel ist eine beglaubigte \u00dcbersetzung durch einen vereidigten "
    "Gerichtsdolmetscher einzuholen. Die maschinelle \u00dcbersetzung wird der "
    "Akte lediglich zu Informationszwecken beigef\u00fcgt."
)


def _has_column(con: sqlite3.Connection, table: str, column: str) -> bool:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def apply_migration(con: sqlite3.Connection) -> dict:
    """Wendet die Migration idempotent auf eine offene templates.db-Verbindung an.

    Returns: dict mit den durchgefuehrten Schritten (fuer Log/Test).
    """
    result = {"added_column": False, "created_index": False, "seeded_module": False}

    # 1) Spalte module_key (SQLite kann kein 'ADD COLUMN ... UNIQUE' -> separater
    #    partieller UNIQUE-Index, der mehrere NULL bei Bestandszeilen zulaesst).
    if not _has_column(con, "report_modules", "module_key"):
        con.execute("ALTER TABLE report_modules ADD COLUMN module_key TEXT")
        result["added_column"] = True

    # 2) Partieller UNIQUE-Index (idempotent).
    con.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_report_modules_key "
        "ON report_modules(module_key) WHERE module_key IS NOT NULL"
    )
    # (Ob neu angelegt, ist fuer die Idempotenz unerheblich.)
    result["created_index"] = True

    # 3) Rechts-Baustein seeden, falls noch nicht vorhanden (Kennung als Anker).
    exists = con.execute(
        "SELECT 1 FROM report_modules WHERE module_key = ?", (MODULE_KEY,)
    ).fetchone()
    if not exists:
        now = int(time.time())
        con.execute(
            "INSERT INTO report_modules "
            "(module_key, title, description, role, topic, body, sort_order, "
            " is_active, created_by, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                MODULE_KEY,
                LEGAL_TITLE,
                "Konsolidierter Rechtshinweis fuer KI-uebersetzungsbasierte Funde.",
                "legal",
                "KI-\u00dcbersetzung",
                LEGAL_BODY,
                0,
                1,
                "system",
                now,
                now,
            ),
        )
        result["seeded_module"] = True

    con.commit()
    return result


def _resolve_db_path(args) -> str:
    if args.templates_db:
        return args.templates_db
    try:
        from core.config_loader import ConfigLoader  # lazy, optional
        cfg = ConfigLoader(args.config)
        path = cfg.get("paths.templates_db")
        if path:
            return path
    except Exception:
        pass
    raise SystemExit(
        "[migrate-templates] Kein templates.db-Pfad: --templates-db angeben oder "
        "paths.templates_db in config.yaml setzen."
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Migriert templates.db: module_key + Rechts-Baustein "
                    "legal.ki_uebersetzung (idempotent).",
        epilog=cli_epilog.epilog("migrate_templates_module_key"),
        formatter_class=cli_epilog.HilfeFormat,
    )
    parser.add_argument("--templates-db", help="Pfad zur templates.db")
    parser.add_argument("--config", default="./config.yaml",
                        help="config.yaml (Fallback fuer den Pfad)")
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(args)
    if not os.path.exists(db_path):
        print(f"[migrate-templates] templates.db nicht gefunden: {db_path}",
              file=sys.stderr)
        return 2

    con = sqlite3.connect(db_path)
    try:
        res = apply_migration(con)
    finally:
        con.close()

    print("[migrate-templates] fertig:",
          f"Spalte module_key {'angelegt' if res['added_column'] else 'bereits vorhanden'};",
          f"Index ok;",
          f"Baustein {MODULE_KEY} {'geseedet' if res['seeded_module'] else 'bereits vorhanden'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

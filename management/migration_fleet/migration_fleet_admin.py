# =============================================================================
# management/migration_fleet/migration_fleet_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   CLI fuer die Flotten-Migrationsschicht (Build 316):
#     catalog-sync : migration_catalog aus dem Code (m###-Skripte) fuellen.
#     reconcile    : Katalog/Code-Drift melden (Exit 1 bei Drift; handlungsleitend).
#     plan         : DRY-RUN-Migrationsplan je Instanz ausgeben (fuehrt NICHTS aus).
#
# Aufruf:
#   python -m management.migration_fleet.migration_fleet_admin catalog-sync
#          [--migration-db PATH] [--config ./config.yaml]
#   python -m management.migration_fleet.migration_fleet_admin reconcile
#          [--migration-db PATH] [--config ./config.yaml]
#   python -m management.migration_fleet.migration_fleet_admin plan
#          --target db_kind:PATH[:uid] [--target ...]
#          [--migration-db PATH] [--config ./config.yaml]
#
# migration.db enthaelt keinen Beweisinhalt; Anlegen/Schreiben ist unbedenklich.
#
# Beleg: Datenmigrationsleitfaden_AIW.md v0.2 Paragraph 6/9, mc 2026-07-03.
# Version: v0.7.316 · Build: 316 · 2026-07-03
# =============================================================================

import argparse
import sqlite3
import sys
from pathlib import Path

from management.migration_fleet.catalog import CatalogReconciler
from management.migration_fleet.migration_db import MigrationDb
from management.migration_fleet.planner import MigrationPlanner, TargetDb


def _resolve_migration_db_path(args) -> str:
    """migration.db-Pfad aus --migration-db oder config.yaml (paths.migration_db)."""
    if args.migration_db:
        return args.migration_db
    try:
        from core.config_loader import ConfigLoader
        cfg = ConfigLoader(config_path=args.config)
        path = cfg.get("paths.migration_db")
        if path:
            return str(path)
    except Exception as exc:  # pragma: no cover
        print("[migration_fleet] config.yaml nicht lesbar: %s" % exc,
              file=sys.stderr)
    raise SystemExit(
        "[migration_fleet] Kein migration.db-Pfad: --migration-db angeben oder "
        "paths.migration_db in config.yaml setzen."
    )


def _parse_target(spec: str) -> TargetDb:
    """
    'db_kind:PATH[:uid]' -> TargetDb. PATH darf keine ':' enthalten (Windows-
    Laufwerksbuchstaben werden hier nicht unterstuetzt; in PROD sind es
    UNC-Pfade ohne Doppelpunkt).
    """
    parts = spec.split(":")
    if len(parts) < 2:
        raise SystemExit("[migration_fleet] Ungueltiges --target '%s' "
                         "(erwartet db_kind:PATH[:uid])." % spec)
    db_kind = parts[0]
    if len(parts) == 2:
        return TargetDb(db_kind=db_kind, path=parts[1], uid=None)
    return TargetDb(db_kind=db_kind, path=parts[1], uid=int(parts[2]))


def _open_mdb(db_path: str, create: bool) -> sqlite3.Connection:
    if not create and not Path(db_path).exists():
        raise SystemExit("[migration_fleet] migration.db nicht gefunden: %s "
                         "(zuerst catalog-sync ausfuehren)." % db_path)
    con = sqlite3.connect(db_path)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Flotten-Migration: Katalog, Abgleich, Dry-Run-Plan."
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--migration-db", default=None)
    common.add_argument("--config", default="./config.yaml")

    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("catalog-sync", parents=[common],
                   help="Katalog aus dem Code fuellen")
    sub.add_parser("reconcile", parents=[common],
                   help="Katalog/Code-Drift melden")
    p_plan = sub.add_parser("plan", parents=[common],
                            help="Dry-Run-Migrationsplan je Instanz")
    p_plan.add_argument("--target", action="append", default=[],
                        help="db_kind:PATH[:uid] (wiederholbar)")

    args = parser.parse_args(argv)
    db_path = _resolve_migration_db_path(args)

    if args.action == "catalog-sync":
        con = _open_mdb(db_path, create=True)
        try:
            mdb = MigrationDb(con)
            mdb.ensure_schema()
            n = CatalogReconciler(mdb).sync()
            print("[migration_fleet] Katalog synchronisiert: %d Eintrag/Eintraege."
                  % n)
            for e in mdb.list_catalog():
                print("  %-12s v%03d  %-11s  backup=%d  %s"
                      % (e.db_kind, e.version, e.kind, e.requires_backup, e.name))
            return 0
        finally:
            con.close()

    if args.action == "reconcile":
        con = _open_mdb(db_path, create=False)
        try:
            report = CatalogReconciler(MigrationDb(con)).reconcile()
            print("[migration_fleet] OK: %d" % len(report.ok))
            if report.modified:
                print("  GEAENDERT (Katalog veraltet): %s" % ", ".join(report.modified))
            if report.uncataloged:
                print("  NICHT KATALOGISIERT (im Code): %s" % ", ".join(report.uncataloged))
            if report.missing_module:
                print("  MODUL FEHLT (nur im Katalog): %s" % ", ".join(report.missing_module))
            if report.has_drift:
                print("[migration_fleet] DRIFT erkannt — 'catalog-sync' ausfuehren "
                      "bzw. Code/Katalog pruefen.", file=sys.stderr)
                return 1
            print("[migration_fleet] Kein Drift. Katalog und Code stimmen ueberein.")
            return 0
        finally:
            con.close()

    # action == "plan"
    if not args.target:
        print("[migration_fleet] plan benoetigt mindestens ein --target.",
              file=sys.stderr)
        return 1
    targets = [_parse_target(s) for s in args.target]
    con = _open_mdb(db_path, create=False)
    try:
        plans = MigrationPlanner(MigrationDb(con)).plan(targets)
        for p in plans:
            head = "%s%s @ v%03d -> %s" % (
                p.db_kind,
                ("/uid=%d" % p.uid) if p.uid is not None else "",
                p.current_version, p.path)
            if p.note:
                print("%s : %s" % (head, p.note))
            elif p.up_to_date:
                print("%s : aktuell (nichts ausstehend)" % head)
            else:
                versions = ", ".join("v%03d(%s)" % (e.version, e.kind)
                                     for e in p.pending)
                print("%s : AUSSTEHEND %s" % (head, versions))
        print("\n[migration_fleet] DRY-RUN — es wurde nichts ausgefuehrt.")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())

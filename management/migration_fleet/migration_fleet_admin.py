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
# Version: v0.7.320 · Build: 320 · 2026-07-03 (companion-Subkommando ergaenzt)
# =============================================================================

import argparse
import sqlite3
import sys
from pathlib import Path

from management.migration_fleet.catalog import CatalogReconciler
from management.migration_fleet.companion import MigrationCompanion
from management.migration_fleet.ledger import MigrationLedger
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


def _resolve_backup_dir(args):
    """
    Backup-Zielverzeichnis aus --backup-dir oder config.yaml (paths.backup_dir).
    Rueckgabe None, wenn nicht gesetzt (die Ausfuehrung wird dann vom Companion
    ueber das Tor KEIN_BACKUP_DIR verweigert).
    """
    if getattr(args, "backup_dir", None):
        return args.backup_dir
    try:
        from core.config_loader import ConfigLoader
        cfg = ConfigLoader(config_path=args.config)
        path = cfg.get("paths.backup_dir")
        if path:
            return str(path)
    except Exception:  # pragma: no cover
        pass
    return None


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
    sub.add_parser("ledger-verify", parents=[common],
                   help="Hash-Kette des migration_runs-Ledgers pruefen")
    p_ll = sub.add_parser("ledger-list", parents=[common],
                          help="Ledger-Eintraege auflisten")
    p_ll.add_argument("--db-kind", default=None)
    p_ll.add_argument("--uid", type=int, default=None)
    p_co = sub.add_parser("companion", parents=[common],
                          help="Gefuehrter Migrations-Begleiter (Vorpruefung, "
                               "Plan; mit --confirm auch Ausfuehrung)")
    p_co.add_argument("--target", action="append", default=[],
                      help="db_kind:PATH[:uid] (wiederholbar)")
    p_co.add_argument("--confirm", action="store_true",
                      help="Ausfuehrung ausdruecklich bestaetigen")
    p_co.add_argument("--backup-dir", default=None)
    p_co.add_argument("--operator", default=None)
    p_co.add_argument("--verifier", default=None)

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

    if args.action == "ledger-verify":
        con = _open_mdb(db_path, create=False)
        try:
            result = MigrationLedger(con).verify_chain()
            if result.ok:
                print("[migration_fleet] Ledger-Kette unversehrt (ok).")
                return 0
            print("[migration_fleet] LEDGER-KETTE FEHLERHAFT: %s" % result.detail,
                  file=sys.stderr)
            return 1
        finally:
            con.close()

    if args.action == "ledger-list":
        con = _open_mdb(db_path, create=False)
        try:
            ledger = MigrationLedger(con)
            rows = ledger.list_runs(db_kind=args.db_kind, uid=args.uid)
            if not rows:
                print("[migration_fleet] Keine Ledger-Eintraege.")
                return 0
            for r in rows:
                print("seq=%-4d %-11s%s v%s->v%s  %-9s  started=%s finished=%s"
                      % (r["seq"], r["db_kind"],
                         ("/uid=%s" % r["uid"]) if r["uid"] is not None else "",
                         r["from_version"], r["to_version"], r["status"],
                         r["started_at"], r["finished_at"]))
            interrupted = ledger.interrupted_runs()
            if interrupted:
                print("\n[migration_fleet] UNTERBROCHENE Laeufe (Start ohne "
                      "Abschluss):")
                for it in interrupted:
                    print("  %s%s -> v%d (start_seq=%d)" % (
                        it.db_kind,
                        ("/uid=%s" % it.uid) if it.uid is not None else "",
                        it.to_version, it.start_seq))
            return 0
        finally:
            con.close()

    if args.action == "companion":
        if not args.target:
            print("[migration_fleet] companion benoetigt mindestens ein --target.",
                  file=sys.stderr)
            return 1
        targets = [_parse_target(s) for s in args.target]
        con = _open_mdb(db_path, create=False)
        try:
            comp = MigrationCompanion(
                MigrationDb(con), MigrationLedger(con),
                backup_dir=_resolve_backup_dir(args), operator=args.operator)
            # Vorpruefung
            pf = comp.preflight(require_backup_dir=args.confirm)
            print("== Vorpruefung ==")
            for n in pf.notes:
                print("  - %s" % n)
            for b in pf.blockers:
                print("  [BLOCKER %s] %s" % (b.code, b.message))
            # Plan (Dry-Run)
            print("== Plan (Dry-Run) ==")
            for p in comp.plan(targets):
                print("  %s%s v%s->v%s : %s"
                      % (p.db_kind,
                         ("/uid=%s" % p.uid) if p.uid is not None else "",
                         p.from_version, p.to_version,
                         p.status if not p.detail else p.detail))
            if not args.confirm:
                print("\n[migration_fleet] Kein --confirm — es wurde NICHTS "
                      "ausgefuehrt (nur Vorpruefung + Plan).")
                return 0 if pf.ok else 1
            # Ausfuehrung (gated)
            result = comp.execute(targets, confirm=True, verifier=args.verifier)
            print("== Ausfuehrung ==")
            if not result.executed:
                print("  VERWEIGERT: %s" % result.reason, file=sys.stderr)
                return 1
            for r in result.results:
                print("  %s%s : %s (v%s->v%s)"
                      % (r.db_kind,
                         ("/uid=%s" % r.uid) if r.uid is not None else "",
                         r.status, r.from_version, r.to_version))
            print("  -> %s" % result.reason)
            # Zusammenfassung + Vieraugen-Erinnerung
            summ = comp.summary()
            print("== Zusammenfassung ==")
            print("  Ledger-Kette: %s" % ("ok" if summ.chain_ok else "FEHLERHAFT"))
            for rem in summ.reminders:
                print("  ! %s" % rem)
            has_failed = any(r.status == "failed_restored" for r in result.results)
            return 1 if has_failed else 0
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

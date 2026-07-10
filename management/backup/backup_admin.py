# =============================================================================
# management/backup/backup_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Backup/PITR (Welle 0)
# =============================================================================
# backup_admin — CLI, das Planner + Executor + Registry zusammenfuehrt:
#
#   plan  — Trockenlauf: enumeriert alle DBs aus config.yaml und zeigt die
#           Speicherplatz-Vorabpruefung (schreibt NICHTS).
#   run   — fuehrt die Sicherung aus (verweigert bei fehlgeschlagener
#           Vorabpruefung), registriert den Lauf auditiert (BACKUP_CREATED)
#           in coordinator.db und zeigt eine Zusammenfassung.
#   list  — zeigt die registrierten Backups (Registry), optional je db_label.
#
# Pfade und Rahmenbedingungen kommen aus config.yaml (paths.* / backup.*),
# override per --coordinator-db moeglich. Muster wie rbac_admin.
#
# Beleg: Bauplan B7 v1.1 §11; mc 2026-07-10.
# Version: v0.7.354 · Build: 354 · 2026-07-10
# =============================================================================

import argparse
import getpass
import sqlite3
import sys
from typing import Dict, Optional

from management.audit.audit_log import AuditLog
from management.backup.backup_config import BackupConfig
from management.backup.backup_executor import BackupExecutor
from management.backup.backup_planner import BackupPlanner
from management.backup.backups_repo import BackupsRepo
from management.gateway.coordinator_writer import CoordinatorWriter

_PATH_KEYS = ("coordinator_db", "forensic_db_dir", "evidence_db_dir",
              "assets_db_dir", "default_db", "templates_db", "translations_db")


def _load_cfg(config_path: str):
    from core.config_loader import ConfigLoader
    return ConfigLoader(config_path=config_path)


def _paths_from_cfg(cfg) -> Dict[str, str]:
    return {k: cfg.get("paths." + k) for k in _PATH_KEYS}


def _coordinator_db(args, cfg) -> str:
    if getattr(args, "coordinator_db", None):
        return args.coordinator_db
    path = cfg.get("paths.coordinator_db")
    if path:
        return str(path)
    raise SystemExit("[backup_admin] Kein coordinator.db-Pfad "
                     "(--coordinator-db oder paths.coordinator_db).")


def _open_con(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def _resolve_actor(con: sqlite3.Connection, actor: Optional[str]):
    if actor:
        row = con.execute(
            "SELECT id FROM person WHERE system_username = ?",
            (actor,)).fetchone()
        if row is None:
            raise SystemExit("[backup_admin] Unbekannte Person (--actor %r)."
                             % actor)
        return int(row[0]), None
    return None, {"performed_by": getpass.getuser()}


# ------------------------------------------------------------------ commands
def cmd_plan(args) -> int:
    cfg = _load_cfg(args.config)
    bcfg = BackupConfig.from_loader(cfg)
    plan = BackupPlanner(_paths_from_cfg(cfg), bcfg).plan()

    print("[backup_admin] Backup-Plan (Trockenlauf)")
    print("  Ziel:            %s" % plan.dest_dir)
    print("  Quellen:         %d DB(s)" % len(plan.sources))
    for s in plan.sources:
        print("    - %-16s %12d Bytes  %s" % (s.label, s.size, s.path))
    if plan.missing:
        print("  Fehlend/uebersprungen:")
        for m in plan.missing:
            print("    ! %s" % m)
    print("  Gesamtgroesse:   %d Bytes" % plan.total_size)
    print("  Benoetigt frei:  %d Bytes" % plan.required_free)
    print("  Frei am Ziel:    %d Bytes" % plan.free_at_dest)
    print("  Vorabpruefung:   %s%s" % (
        "OK" if plan.ok else "FEHLGESCHLAGEN",
        "" if plan.ok else " — " + plan.reason))
    return 0 if plan.ok else 2


def cmd_run(args) -> int:
    cfg = _load_cfg(args.config)
    bcfg = BackupConfig.from_loader(cfg)
    plan = BackupPlanner(_paths_from_cfg(cfg), bcfg).plan()

    if not plan.ok:
        print("[backup_admin] Lauf verweigert (Vorabpruefung): %s"
              % plan.reason, file=sys.stderr)
        return 2

    # Erst sichern (kein offener coordinator-Writer waehrend VACUUM INTO), ...
    run = BackupExecutor(bcfg).run(plan)

    # ... dann den Lauf auditiert registrieren.
    db_path = _coordinator_db(args, cfg)
    con = _open_con(db_path)
    try:
        actor_id, _meta = _resolve_actor(con, args.actor)
        writer = CoordinatorWriter(con, AuditLog(con))
        seq = BackupsRepo(con, writer).record_run(run, actor_id)
    finally:
        con.close()

    ok_cnt = sum(1 for r in run.results if r.error is None and r.integrity_ok)
    print("[backup_admin] Lauf %s (Beleg audit_seq=%d)"
          % ("OK" if run.ok else "MIT FEHLERN", seq))
    print("  gesichert: %d/%d DB(s), geloescht (Retention): %d"
          % (ok_cnt, len(run.results), len(run.pruned)))
    for r in run.results:
        status = "ok" if (r.error is None and r.integrity_ok) else \
            ("FEHLER: " + (r.error or "integrity"))
        print("    - %-16s %s" % (r.label, status))
    print("  Manifest: %s" % run.manifest_path)
    return 0 if run.ok else 1


def cmd_list(args) -> int:
    cfg = _load_cfg(args.config)
    db_path = _coordinator_db(args, cfg)
    con = _open_con(db_path)
    try:
        rows = BackupsRepo(con, None).list_backups(
            db_label=args.db_label, limit=args.limit)
    finally:
        con.close()

    if not rows:
        print("[backup_admin] Keine registrierten Backups.")
        return 0
    print("[backup_admin] %d registrierte(s) Backup(s):" % len(rows))
    for r in rows:
        print("  #%d  %s  %-16s  integrity=%s  seq=%s  %s"
              % (r["id"], r["run_ts"], r["db_label"],
                 "ok" if r["integrity_ok"] else "FEHLER",
                 r["audit_seq"], r["backup_path"] or "(kein)"))
    return 0


# ---------------------------------------------------------------- arg parser
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Auditierte Datensicherung (plan/run/list).")
    sub = parser.add_subparsers(dest="action", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--coordinator-db", default=None)
    common.add_argument("--config", default="./config.yaml")

    sub.add_parser("plan", parents=[common],
                   help="Trockenlauf: Quellen + Speicherplatz-Vorabpruefung.")

    p_run = sub.add_parser("run", parents=[common],
                           help="Sicherung ausfuehren + auditiert registrieren.")
    p_run.add_argument("--actor", default=None,
                       help="system_username des Ausfuehrenden (Audit-Akteur).")

    p_list = sub.add_parser("list", parents=[common],
                            help="Registrierte Backups zeigen.")
    p_list.add_argument("--db-label", default=None, dest="db_label")
    p_list.add_argument("--limit", type=int, default=100)

    return parser


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    return {"plan": cmd_plan, "run": cmd_run, "list": cmd_list}[args.action](args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

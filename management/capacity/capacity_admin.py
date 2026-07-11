# =============================================================================
# management/capacity/capacity_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kapazitaet (Welle 0)
# =============================================================================
# capacity_admin — auditierte CLI-Verwaltung der Kapazitaets-Datenbasis.
# Build 356: Regel-Arbeitszeit (person_worktime) + Feiertage (holiday).
#   set-worktime / list-worktime
#   add-holiday / remove-holiday / list-holidays
# Reason + Availability folgen in Build 357.
#
# Pfade aus config.yaml (paths.coordinator_db), override per --coordinator-db.
# Muster wie rbac_admin. main(argv) ist testbar.
#
# Beleg: Bauplan B7 v1.1 §11.4. Version: v0.7.356 · Build: 356 · 2026-07-10
# =============================================================================

import argparse
import getpass
import sqlite3
import sys
from typing import Optional

from management.audit.audit_log import AuditLog
from management.capacity.capacity_errors import CapacityError
from management.capacity.holiday_repo import HolidayRepo
from management.capacity.worktime_repo import WorktimeRepo
from management.gateway.coordinator_writer import CoordinatorWriter


def _resolve_db_path(args) -> str:
    if getattr(args, "coordinator_db", None):
        return args.coordinator_db
    try:
        from core.config_loader import ConfigLoader
        cfg = ConfigLoader(config_path=args.config)
        path = cfg.get("paths.coordinator_db")
        if path:
            return str(path)
    except Exception as exc:  # pragma: no cover
        print("[capacity_admin] config.yaml nicht lesbar: %s" % exc,
              file=sys.stderr)
    raise SystemExit("[capacity_admin] Kein coordinator.db-Pfad "
                     "(--coordinator-db oder paths.coordinator_db).")


def _open_con(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def _lookup_person_id(con: sqlite3.Connection, username: str) -> int:
    row = con.execute("SELECT id FROM person WHERE system_username = ?",
                      (username,)).fetchone()
    if row is None:
        raise SystemExit("[capacity_admin] Unbekannte Person (%r)." % username)
    return int(row[0])


def _resolve_actor(con: sqlite3.Connection, actor: Optional[str]):
    if actor:
        return _lookup_person_id(con, actor), None
    return None, {"performed_by": getpass.getuser()}


def _person_id(con, args) -> int:
    if getattr(args, "person_id", None) is not None:
        return int(args.person_id)
    if getattr(args, "person", None):
        return _lookup_person_id(con, args.person)
    raise SystemExit("[capacity_admin] --person-id oder --person erforderlich.")


# ------------------------------------------------------------------ commands
def cmd_set_worktime(con, args) -> int:
    actor_id, _ = _resolve_actor(con, args.actor)
    pid = _person_id(con, args)
    repo = WorktimeRepo(con, CoordinatorWriter(con, AuditLog(con)))
    try:
        seq = repo.set_worktime(
            pid, effective_from=args.effective_from, effective_to=args.effective_to,
            mon_min=args.mon, tue_min=args.tue, wed_min=args.wed,
            thu_min=args.thu, fri_min=args.fri, sat_min=args.sat,
            sun_min=args.sun, actor_id=actor_id)
    except CapacityError as exc:
        print("[capacity_admin] %s" % exc, file=sys.stderr)
        return 2
    print("[capacity_admin] Arbeitszeit fuer person=%d gesetzt "
          "(ab %s, audit seq=%d)." % (pid, args.effective_from, seq))
    return 0


def cmd_list_worktime(con, args) -> int:
    pid = int(args.person_id) if args.person_id is not None else None
    rows = WorktimeRepo(con, None).list_worktime(pid, include_deleted=args.all)
    if not rows:
        print("[capacity_admin] Keine Arbeitszeit-Regeln.")
        return 0
    for r in rows:
        print("  #%d person=%d ab %s bis %s  Mo-So=%s  seq=%s%s"
              % (r["id"], r["person_id"], r["effective_from"],
                 r["effective_to"] or "offen",
                 [r["mon_min"], r["tue_min"], r["wed_min"], r["thu_min"],
                  r["fri_min"], r["sat_min"], r["sun_min"]],
                 r["audit_seq"], " [geloescht]" if r["deleted_at"] else ""))
    return 0


def cmd_add_holiday(con, args) -> int:
    actor_id, _ = _resolve_actor(con, args.actor)
    repo = HolidayRepo(con, CoordinatorWriter(con, AuditLog(con)))
    try:
        seq = repo.add_holiday(args.day, args.label, region=args.region,
                               actor_id=actor_id)
    except CapacityError as exc:
        print("[capacity_admin] %s" % exc, file=sys.stderr)
        return 2
    print("[capacity_admin] Feiertag %s '%s' hinzugefuegt (audit seq=%d)."
          % (args.day, args.label, seq))
    return 0


def cmd_remove_holiday(con, args) -> int:
    actor_id, _ = _resolve_actor(con, args.actor)
    repo = HolidayRepo(con, CoordinatorWriter(con, AuditLog(con)))
    try:
        seq = repo.remove_holiday(int(args.id), actor_id=actor_id)
    except CapacityError as exc:
        print("[capacity_admin] %s" % exc, file=sys.stderr)
        return 2
    print("[capacity_admin] Feiertag id=%s entfernt (audit seq=%d)."
          % (args.id, seq))
    return 0


def cmd_list_holidays(con, args) -> int:
    rows = HolidayRepo(con, None).list_holidays(
        region=args.region, include_deleted=args.all)
    if not rows:
        print("[capacity_admin] Keine Feiertage.")
        return 0
    for r in rows:
        print("  #%d %s '%s' Region=%s seq=%s%s"
              % (r["id"], r["day"], r["label"],
                 r["region"] or "ueberall", r["audit_seq"],
                 " [geloescht]" if r["deleted_at"] else ""))
    return 0


# ---------------------------------------------------------------- arg parser
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Auditierte Verwaltung der Kapazitaets-Datenbasis "
                    "(Arbeitszeit/Feiertage).")
    sub = parser.add_subparsers(dest="action", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--coordinator-db", default=None)
    common.add_argument("--config", default="./config.yaml")
    actor = argparse.ArgumentParser(add_help=False)
    actor.add_argument("--actor", default=None,
                       help="system_username des Ausfuehrenden (Audit-Akteur).")

    p_sw = sub.add_parser("set-worktime", parents=[common, actor],
                          help="Regel-Arbeitszeit (Minuten je Wochentag) setzen.")
    p_sw.add_argument("--person-id", type=int, default=None)
    p_sw.add_argument("--person", default=None, help="system_username")
    p_sw.add_argument("--from", dest="effective_from", required=True,
                      help="effective_from (ISO-Datum)")
    p_sw.add_argument("--to", dest="effective_to", default=None)
    for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
        p_sw.add_argument("--%s" % d, type=int, default=0,
                          help="Minuten am %s" % d)

    p_lw = sub.add_parser("list-worktime", parents=[common],
                          help="Arbeitszeit-Regeln zeigen.")
    p_lw.add_argument("--person-id", type=int, default=None)
    p_lw.add_argument("--all", action="store_true", help="inkl. geloeschte")

    p_ah = sub.add_parser("add-holiday", parents=[common, actor],
                          help="Feiertag hinzufuegen.")
    p_ah.add_argument("--day", required=True, help="ISO-Datum")
    p_ah.add_argument("--label", required=True)
    p_ah.add_argument("--region", default=None, help="NULL = ueberall")

    p_rh = sub.add_parser("remove-holiday", parents=[common, actor],
                          help="Feiertag entfernen (Soft-Delete).")
    p_rh.add_argument("--id", required=True, type=int)

    p_lh = sub.add_parser("list-holidays", parents=[common],
                          help="Feiertage zeigen.")
    p_lh.add_argument("--region", default=None)
    p_lh.add_argument("--all", action="store_true", help="inkl. geloeschte")

    return parser


_DISPATCH = {
    "set-worktime": cmd_set_worktime,
    "list-worktime": cmd_list_worktime,
    "add-holiday": cmd_add_holiday,
    "remove-holiday": cmd_remove_holiday,
    "list-holidays": cmd_list_holidays,
}


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    con = _open_con(_resolve_db_path(args))
    try:
        return _DISPATCH[args.action](con, args)
    finally:
        con.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

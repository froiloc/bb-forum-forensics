# =============================================================================
# management/capacity/capacity_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kapazitaet (Welle 0)
# =============================================================================
# capacity_admin — auditierte CLI-Verwaltung der Kapazitaets-Datenbasis.
# Build 356: Regel-Arbeitszeit (person_worktime) + Feiertage (holiday).
#   set-worktime / list-worktime
# Build 560: remove-worktime / replace-worktime (Soft-Delete bzw.
#   Ersetzen in EINER Transaktion; noetig seit der Dublettensperre).
#   add-holiday / remove-holiday / list-holidays
# Build 357: Gruende (availability_reason) + Verfuegbarkeit (availability_entry).
#   add-reason / list-reasons
#   set-availability / remove-availability / list-availability
#
# Pfade aus config.yaml (paths.coordinator_db), override per --coordinator-db.
# Muster wie rbac_admin. main(argv) ist testbar.
#
# Beleg: Bauplan B7 v1.1 §11.4. Version: v0.7.357 · Build: 357 · 2026-07-10
# =============================================================================

import argparse
import getpass
import sqlite3
import sys
from typing import Optional

from management.audit.audit_log import AuditLog
from management.capacity.availability_repo import AvailabilityRepo
from management.capacity.capacity_errors import CapacityError
from management.capacity.holiday_repo import HolidayRepo
from management.capacity.reason_repo import ReasonRepo
from management.capacity.worktime_repo import WorktimeRepo
from management.gateway.coordinator_writer import CoordinatorWriter
from db.journal_policy import apply_journal_mode  # NEU Build 408


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
    # Build 408: Journalmodus zentral ueber db/journal_policy.py.
    # 'auto' = WAL bevorzugen, bei Fehlschlag (z.B. Netzlaufwerk: WAL braucht
    # maschinenlokales Shared Memory) protokollierter Rueckfall auf DELETE.
    apply_journal_mode(con, db_path)
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


def cmd_remove_worktime(con, args) -> int:
    """
    Build 560: Arbeitszeit-Regel entfernen (SOFT-DELETE). Die Zeile bleibt in
    der Datenbank und traegt deleted_at; der Beleg WORKTIME_REMOVED enthaelt
    die entfernten Werte.
    """
    actor_id, _ = _resolve_actor(con, args.actor)
    repo = WorktimeRepo(con, CoordinatorWriter(con, AuditLog(con)))
    try:
        seq = repo.remove_worktime(args.worktime_id, actor_id=actor_id)
    except CapacityError as exc:
        print("[capacity_admin] %s" % exc, file=sys.stderr)
        return 2
    print("[capacity_admin] Arbeitszeit-Zeile #%d entfernt (Soft-Delete, "
          "audit seq=%d)." % (args.worktime_id, seq))
    return 0


def cmd_replace_worktime(con, args) -> int:
    """
    Build 560: Regel ERSETZEN - entfernen und neu setzen in EINER Transaktion,
    mit zwei eigenen Belegen. Der Weg, der seit der Dublettensperre noetig ist,
    wenn zum selben Stichtag korrigiert wird.
    """
    actor_id, _ = _resolve_actor(con, args.actor)
    pid = _person_id(con, args)
    repo = WorktimeRepo(con, CoordinatorWriter(con, AuditLog(con)))
    try:
        seqs = repo.replace_worktime(
            args.worktime_id, pid, effective_from=args.effective_from,
            effective_to=args.effective_to,
            mon_min=args.mon, tue_min=args.tue, wed_min=args.wed,
            thu_min=args.thu, fri_min=args.fri, sat_min=args.sat,
            sun_min=args.sun, actor_id=actor_id)
    except CapacityError as exc:
        print("[capacity_admin] %s" % exc, file=sys.stderr)
        return 2
    print("[capacity_admin] Arbeitszeit-Zeile #%d ersetzt (entfernt seq=%d, "
          "gesetzt seq=%d)." % (args.worktime_id, seqs["entfernt_seq"],
                                seqs["gesetzt_seq"]))
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


def cmd_add_reason(con, args) -> int:
    actor_id, _ = _resolve_actor(con, args.actor)
    repo = ReasonRepo(con, CoordinatorWriter(con, AuditLog(con)))
    try:
        seq = repo.add_reason(args.code, args.label, sort=args.sort,
                              actor_id=actor_id)
    except CapacityError as exc:
        print("[capacity_admin] %s" % exc, file=sys.stderr)
        return 2
    print("[capacity_admin] Grund '%s' hinzugefuegt (audit seq=%d)."
          % (args.code, seq))
    return 0


def cmd_list_reasons(con, args) -> int:
    rows = ReasonRepo(con, None).list_reasons(include_deleted=args.all)
    if not rows:
        print("[capacity_admin] Keine Gruende.")
        return 0
    for r in rows:
        print("  %-16s '%s' (sort=%d) seq=%s"
              % (r["code"], r["label"], r["sort"], r["audit_seq"]))
    return 0


def cmd_set_availability(con, args) -> int:
    actor_id, _ = _resolve_actor(con, args.actor)
    pid = _person_id(con, args)
    repo = AvailabilityRepo(con, CoordinatorWriter(con, AuditLog(con)))
    try:
        seq = repo.set_availability(
            pid, period_start=args.start, period_end=args.end, kind=args.kind,
            value_pct=args.pct, value_minutes=args.minutes,
            reason_code=args.reason, note=args.note, actor_id=actor_id)
    except CapacityError as exc:
        print("[capacity_admin] %s" % exc, file=sys.stderr)
        return 2
    print("[capacity_admin] Verfuegbarkeit (%s) fuer person=%d gesetzt "
          "(%s..%s, audit seq=%d)."
          % (args.kind, pid, args.start, args.end, seq))
    return 0


def cmd_remove_availability(con, args) -> int:
    actor_id, _ = _resolve_actor(con, args.actor)
    repo = AvailabilityRepo(con, CoordinatorWriter(con, AuditLog(con)))
    try:
        seq = repo.remove_availability(int(args.id), actor_id=actor_id)
    except CapacityError as exc:
        print("[capacity_admin] %s" % exc, file=sys.stderr)
        return 2
    print("[capacity_admin] Verfuegbarkeit id=%s entfernt (audit seq=%d)."
          % (args.id, seq))
    return 0


def cmd_list_availability(con, args) -> int:
    pid = int(args.person_id) if args.person_id is not None else None
    rows = AvailabilityRepo(con, None).list_availability(
        pid, include_deleted=args.all)
    if not rows:
        print("[capacity_admin] Keine Verfuegbarkeits-Eintraege.")
        return 0
    for r in rows:
        wert = ("%d%%" % r["value_pct"]) if r["value_pct"] is not None \
            else ("%d min" % r["value_minutes"])
        print("  #%d person=%d %s..%s %-14s %s Grund=%s seq=%s%s"
              % (r["id"], r["person_id"], r["period_start"], r["period_end"],
                 r["kind"], wert, r["reason_code"] or "-", r["audit_seq"],
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

    # --- Build 560: Entfernen und Ersetzen -------------------------------
    # Beide Wege gibt es auch in der Oberflaeche. Sie hier NACHZUZIEHEN ist
    # kein Selbstzweck: seit der Dublettensperre laeuft eine Korrektur zum
    # selben Stichtag ueber 'replace-worktime'. Ohne dieses Kommando bekaeme
    # jemand an der Kommandozeile einen Fehler, wo bisher etwas durchlief -
    # ohne zu erfahren, wie es richtig geht.
    p_xw = sub.add_parser("remove-worktime", parents=[common, actor],
                          help="Regel-Arbeitszeit entfernen (Soft-Delete).")
    p_xw.add_argument("--worktime-id", dest="worktime_id", type=int,
                      required=True)

    p_rw = sub.add_parser("replace-worktime", parents=[common, actor],
                          help="Regel-Arbeitszeit ersetzen (entfernen und neu "
                               "setzen in EINER Transaktion).")
    p_rw.add_argument("--worktime-id", dest="worktime_id", type=int,
                      required=True)
    p_rw.add_argument("--person-id", type=int, default=None)
    p_rw.add_argument("--person", default=None, help="system_username")
    p_rw.add_argument("--from", dest="effective_from", required=True,
                      help="effective_from (ISO-Datum)")
    p_rw.add_argument("--to", dest="effective_to", default=None)
    for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
        p_rw.add_argument("--%s" % d, type=int, default=0,
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

    # --- Build 357: Gruende + Verfuegbarkeit ---
    p_ar = sub.add_parser("add-reason", parents=[common, actor],
                          help="Verfuegbarkeits-Grund zum Katalog hinzufuegen.")
    p_ar.add_argument("--code", required=True)
    p_ar.add_argument("--label", required=True)
    p_ar.add_argument("--sort", type=int, default=0)

    p_lr = sub.add_parser("list-reasons", parents=[common],
                          help="Grund-Katalog zeigen.")
    p_lr.add_argument("--all", action="store_true", help="inkl. geloeschte")

    p_sa = sub.add_parser("set-availability", parents=[common, actor],
                          help="Garantie/Einschraenkung fuer einen Zeitraum "
                               "setzen (genau eines von --pct/--minutes).")
    p_sa.add_argument("--person-id", type=int, default=None)
    p_sa.add_argument("--person", default=None, help="system_username")
    p_sa.add_argument("--start", required=True, help="period_start (ISO-Datum)")
    p_sa.add_argument("--end", required=True, help="period_end (ISO-Datum)")
    p_sa.add_argument("--kind", required=True,
                      choices=["garantie", "einschraenkung"])
    p_sa.add_argument("--pct", type=int, default=None, help="value_pct [0..100]")
    p_sa.add_argument("--minutes", type=int, default=None, help="value_minutes")
    p_sa.add_argument("--reason", default=None, help="reason_code (aktiv)")
    p_sa.add_argument("--note", default=None)

    p_ra = sub.add_parser("remove-availability", parents=[common, actor],
                          help="Verfuegbarkeits-Eintrag entfernen (Soft-Delete).")
    p_ra.add_argument("--id", required=True, type=int)

    p_la = sub.add_parser("list-availability", parents=[common],
                          help="Verfuegbarkeits-Eintraege zeigen.")
    p_la.add_argument("--person-id", type=int, default=None)
    p_la.add_argument("--all", action="store_true", help="inkl. geloeschte")

    return parser


_DISPATCH = {
    "set-worktime": cmd_set_worktime,
    "remove-worktime": cmd_remove_worktime,
    "replace-worktime": cmd_replace_worktime,
    "list-worktime": cmd_list_worktime,
    "add-holiday": cmd_add_holiday,
    "remove-holiday": cmd_remove_holiday,
    "list-holidays": cmd_list_holidays,
    "add-reason": cmd_add_reason,
    "list-reasons": cmd_list_reasons,
    "set-availability": cmd_set_availability,
    "remove-availability": cmd_remove_availability,
    "list-availability": cmd_list_availability,
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

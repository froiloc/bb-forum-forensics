# =============================================================================
# management/case_events/case_events_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Auditierte Kommandozeile für den Ereigniszeitstrahl (case_events):
#   Anzeigen des Zeitstrahls eines Falls und Hinzufügen manueller Einträge.
#   Die automatisch gespiegelten Einträge (Anlage/Zuweisung/Status/Freigabe)
#   entstehen NICHT hier, sondern in CasesRepo (Bauplan B7 v0.8 §8.4).
#
# Aufruf (Subkommandos, Muster wie person_admin, B7 §5.4):
#   python -m management.case_events.case_events_admin list --user-id N
#          [--limit K] [--coordinator-db PATH] [--config ./config.yaml]
#   python -m management.case_events.case_events_admin add  --user-id N
#          --text "..." [--actor SYSUSER]
#          [--coordinator-db PATH] [--config ./config.yaml]
#
# Verhalten:
#   - --actor SYSUSER -> audit_log.actor_id (und case_events.created_by);
#     fehlt es, actor_id=NULL (System) und OS-Benutzer in audit_log.meta.
#   - Nicht-fatal, klare Fehlermeldungen; Exit 0 = ok, 1 = Fehler.
#
# Beleg: Bauplan B7 v0.8 §8.5, mc 2026-07-02.
# Version: v0.7.313 · Build: 313 · 2026-07-02
# =============================================================================

import argparse
import getpass
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from management.audit.audit_log import AuditLog
from management.case_events.case_events_repo import CaseEventsError, CaseEventsRepo
from management.gateway.coordinator_writer import CoordinatorWriter
from db.journal_policy import apply_journal_mode  # NEU Build 408


def _resolve_db_path(args) -> str:
    """
    coordinator.db-Pfad aus --coordinator-db oder config.yaml
    (paths.coordinator_db). Identische Auflösungslogik wie cases_admin /
    person_admin — bewusst lokal dupliziert, bis ein gemeinsames
    CLI-Helfermodul eingezogen wird (kleiner, stabiler Codeblock; ein
    Refactoring aller drei CLIs wäre eigener Build-Umfang).
    """
    if args.coordinator_db:
        return args.coordinator_db
    try:
        from core.config_loader import ConfigLoader
        cfg = ConfigLoader(config_path=args.config)
        path = cfg.get("paths.coordinator_db")
        if path:
            return str(path)
    except Exception as exc:  # pragma: no cover
        print("[case_events_admin] config.yaml nicht lesbar: %s" % exc,
              file=sys.stderr)
    raise SystemExit(
        "[case_events_admin] Kein coordinator.db-Pfad: --coordinator-db oder "
        "paths.coordinator_db in config.yaml."
    )


def _lookup_investigator_id(con: sqlite3.Connection, system_username: str) -> int:
    row = con.execute(
        "SELECT id FROM person WHERE system_username = ?",
        (system_username,),
    ).fetchone()
    if row is None:
        raise SystemExit(
            "[case_events_admin] Unbekannter Ermittler (system_username=%r)."
            % system_username
        )
    return int(row[0])


def _fmt_ts(ts: int) -> str:
    """Unix-Sekunden -> lesbares UTC-Datum (Anzeige, kein Beweisformat)."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%SZ"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Ereigniszeitstrahl je Fall (case_events) anzeigen/ergänzen."
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--user-id", type=int, required=True)
    common.add_argument("--coordinator-db", default=None)
    common.add_argument("--config", default="./config.yaml")

    sub = parser.add_subparsers(dest="action", required=True)

    p_list = sub.add_parser("list", parents=[common],
                            help="Zeitstrahl eines Falls anzeigen")
    p_list.add_argument("--limit", type=int, default=None)

    p_add = sub.add_parser("add", parents=[common],
                           help="manuellen Zeitstrahl-Eintrag hinzufügen")
    p_add.add_argument("--text", required=True)
    p_add.add_argument("--actor", default=None,
                       help="system_username des Ausführenden (Audit-Akteur)")

    args = parser.parse_args(argv)

    db_path = _resolve_db_path(args)
    if not Path(db_path).exists():
        print("[case_events_admin] coordinator.db nicht gefunden: %s" % db_path,
              file=sys.stderr)
        return 1

    con = sqlite3.connect(db_path)
    try:
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        # Build 408: siehe db/journal_policy.py (WAL, sonst Rueckfall).
        apply_journal_mode(con, db_path)

        audit = AuditLog(con)
        writer = CoordinatorWriter(con, audit)
        repo = CaseEventsRepo(con, writer)

        if args.action == "list":
            events = repo.list_events(args.user_id, limit=args.limit)
            if not events:
                print("[case_events_admin] Kein Zeitstrahl-Eintrag für "
                      "user_id=%d." % args.user_id)
                return 0
            for e in events:
                who = e["created_by_username"] or "System"
                print("%s  seq=%-5d  %-14s  %-12s  %s" % (
                    _fmt_ts(e["created_at"]), e["audit_seq"],
                    e["event_kind"], who, e["payload"],
                ))
            return 0

        # action == "add"
        actor_id = None
        meta = None
        if args.actor:
            actor_id = _lookup_investigator_id(con, args.actor)
        else:
            meta = {"performed_by": getpass.getuser()}

        seq = repo.add_manual_event(
            args.user_id, args.text, actor_id=actor_id, meta=meta,
        )
        print("[case_events_admin] Eintrag hinzugefügt: user_id=%d "
              "(audit seq=%d)" % (args.user_id, seq))
        return 0
    except CaseEventsError as exc:
        print("[case_events_admin] %s" % exc, file=sys.stderr)
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())

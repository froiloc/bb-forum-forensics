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
#   python -m management.case_events.case_events_admin list --subject-id N
#          [--limit K] [--coordinator-db PATH] [--config ./config.yaml]
#   python -m management.case_events.case_events_admin add  --subject-id N
#          --text "..." [--actor SYSUSER]
#          [--coordinator-db PATH] [--config ./config.yaml]
#
# Verhalten:
#   - --actor SYSUSER -> audit_log.actor_id (und case_events.created_by);
#     fehlt es, actor_id=NULL (System) und OS-Benutzer in audit_log.meta.
#   - Nicht-fatal, klare Fehlermeldungen; Exit 0 = ok, 1 = Fehler.
#
# Beleg: Bauplan B7 v0.8 §8.5, mc 2026-07-02.
# Version: v0.7.469 · Build: 469 · 2026-07-20
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
from management.help import cli_epilog  # noqa: E402
# Build 643: die Vorrangregel Argument > config.yaml > Vorgabewert
# steht seit diesem Build an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402


def _resolve_db_path(args) -> str:
    """
    coordinator.db-Pfad: Argument --coordinator-db > paths.coordinator_db > Abbruch.

    BUILD 643 - DIE AUFLOESUNG IST UMGEZOGEN, das Verhalten NICHT.
    Bis Build 642 stand hier eine eigene Abschrift derselben zwoelf Zeilen;
    fuenfundzwanzig Werkzeuge trugen sie, und sie waren nicht identisch (die
    Begruendung steht im Kopf von core/werkzeug_konfig.py). Sie steht jetzt an
    EINER Stelle.

    UNVERAENDERT bleiben: die Reihenfolge, das Fehlen eines Vorgabewerts
    (ein erratener Pfad waere schlimmer als ein Abbruch), die Meldung ueber
    eine unlesbare config.yaml auf stderr und der Abbruch mit dem Praefix
    '[case_events_admin]'. Die Abbruchmeldung nennt jetzt BEIDE Wege statt nur einen.
    """
    return werkzeug_konfig.db_pfad(
        "case_events_admin", args, arg_attribut="coordinator_db", arg_name="--coordinator-db",
        config_schluessel="paths.coordinator_db", name="coordinator_db")


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
        description="Ereigniszeitstrahl je Fall (case_events) anzeigen/ergänzen.",
        epilog=cli_epilog.epilog("case_events_admin"),
        formatter_class=cli_epilog.HilfeFormat,
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--subject-id", type=int, required=True)
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
            events = repo.list_events(args.subject_id, limit=args.limit)
            if not events:
                print("[case_events_admin] Kein Zeitstrahl-Eintrag für "
                      "subject_id=%d." % args.subject_id)
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
            args.subject_id, args.text, actor_id=actor_id, meta=meta,
        )
        print("[case_events_admin] Eintrag hinzugefügt: subject_id=%d "
              "(audit seq=%d)" % (args.subject_id, seq))
        return 0
    except CaseEventsError as exc:
        print("[case_events_admin] %s" % exc, file=sys.stderr)
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())

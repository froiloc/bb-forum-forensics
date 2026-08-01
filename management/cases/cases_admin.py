# =============================================================================
# management/cases/cases_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Auditierte Kommandozeile zum Anlegen und Pflegen von Fallakten (cases).
#   Ersetzt die bisherige Roh-SQL-Zuweisung: JEDE Änderung läuft über das
#   CoordinatorWriter-Gateway und erzeugt damit einen lückenlosen audit_log-
#   Eintrag. Erster Baustein des Zuweisungs-Interfaces von Baustelle 7.
#
# Aufruf:
#   python -m management.cases.cases_admin --subject-id N --username NAME
#          [--assign SYSUSER] [--status open|in_progress|approved|closed]
#          [--priority 1..5] [--note TEXT] [--actor SYSUSER]
#          [--coordinator-db PATH] [--config ./config.yaml]
#
# Verhalten:
#   - Fehlt der Fall, wird er (bei vorhandenem --username) angelegt.
#   - --assign/--status/--priority/--note werden anschließend angewandt.
#   - --actor SYSUSER -> audit_log.actor_id; fehlt es, actor_id=NULL (System)
#     und OS-Benutzer in audit_log.meta.performed_by.
#   Nicht-fatal, klare Fehlermeldungen; Exit 0 = ok, 1 = Fehler.
#
# Beleg: Bauplan B7 v0.3 §3.5, mc 2026-07-01.
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import argparse
import getpass
import sqlite3
import sys
from pathlib import Path

from management.audit.audit_log import AuditLog
from management.cases.cases_repo import CasesError, CasesRepo
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
    '[cases_admin]'. Die Abbruchmeldung nennt jetzt BEIDE Wege statt nur einen.
    """
    return werkzeug_konfig.db_pfad(
        "cases_admin", args, arg_attribut="coordinator_db", arg_name="--coordinator-db",
        config_schluessel="paths.coordinator_db", name="coordinator_db")


def _lookup_investigator_id(con: sqlite3.Connection, system_username: str):
    row = con.execute(
        "SELECT id FROM person WHERE system_username = ?",
        (system_username,),
    ).fetchone()
    if row is None:
        raise SystemExit(
            "[cases_admin] Unbekannter Ermittler (system_username=%r)."
            % system_username
        )
    return int(row[0])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Auditierte Verwaltung der Fallakten (cases).",
        epilog=cli_epilog.epilog("cases_admin"),
        formatter_class=cli_epilog.HilfeFormat,
    )
    parser.add_argument("--subject-id", type=int, required=True)
    parser.add_argument("--username", default=None,
                        help="Forennutzername (Pflicht beim Anlegen)")
    parser.add_argument("--assign", default=None,
                        help="system_username des zuzuweisenden Ermittlers")
    parser.add_argument("--status", default=None,
                        choices=["open", "in_progress", "approved", "closed"])
    parser.add_argument("--priority", type=int, default=None, choices=range(1, 6))
    parser.add_argument("--note", default=None)
    parser.add_argument("--actor", default=None,
                        help="system_username des Ausführenden (Audit-Akteur)")
    parser.add_argument("--coordinator-db", default=None)
    parser.add_argument("--config", default="./config.yaml")
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(args)
    if not Path(db_path).exists():
        print("[cases_admin] coordinator.db nicht gefunden: %s" % db_path,
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
        repo = CasesRepo(con, writer)

        # Akteur auflösen: entweder person.id oder System + OS-Benutzer in meta.
        actor_id = None
        meta = None
        if args.actor:
            actor_id = _lookup_investigator_id(con, args.actor)
        else:
            meta = {"performed_by": getpass.getuser()}

        uid = args.subject_id

        # Fall ggf. anlegen.
        if repo.get_case(uid) is None:
            if not args.username:
                print("[cases_admin] Fall subject_id=%d fehlt und kein --username "
                      "zum Anlegen angegeben." % uid, file=sys.stderr)
                return 1
            seq = repo.create_case(uid, args.username, actor_id=actor_id, meta=meta)
            print("[cases_admin] Fall angelegt: subject_id=%d (audit seq=%d)" % (uid, seq))

        # Zuweisung.
        if args.assign:
            inv_id = _lookup_investigator_id(con, args.assign)
            seq = repo.assign(uid, inv_id, actor_id=actor_id, meta=meta)
            print("[cases_admin] zugewiesen an %s (audit seq=%d)" % (args.assign, seq))

        # Status.
        if args.status:
            seq = repo.set_status(uid, args.status, actor_id=actor_id, meta=meta)
            print("[cases_admin] Status=%s (audit seq=%d)" % (args.status, seq))

        # Priorität.
        if args.priority is not None:
            seq = repo.set_priority(uid, args.priority, actor_id=actor_id, meta=meta)
            print("[cases_admin] Priorität=%d (audit seq=%d)" % (args.priority, seq))

        # Notiz.
        if args.note is not None:
            seq = repo.set_note(uid, args.note, actor_id=actor_id, meta=meta)
            print("[cases_admin] Notiz gesetzt (audit seq=%d)" % seq)

        return 0
    except CasesError as exc:
        print("[cases_admin] %s" % exc, file=sys.stderr)
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())

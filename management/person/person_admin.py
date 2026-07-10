# =============================================================================
# management/person/person_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Auditierte Kommandozeile zum Anlegen, Ändern und Auflisten von Ermittlern
#   (person). Ersetzt das bisherige Einfügen per SQL-Direktzugriff: JEDE
#   Änderung läuft über das CoordinatorWriter-Gateway und erzeugt einen
#   lückenlosen audit_log-Eintrag. Grundlage für die Zuweisung (cases_admin) und
#   die spätere Support-Sitzungsanzeige — beide setzen sauber angelegte
#   Ermittler voraus. Ein UI ergänzt diese CLI später.
#
# Aufruf:
#   python -m management.person.person_admin list
#          [--coordinator-db PATH] [--config ./config.yaml]
#
#   python -m management.person.person_admin create
#          --system-username h0XXXXX --display-name "Nachname, Vorname"
#          [--supervisor] [--support] [--no-investigator]
#          [--actor SYSUSER] [--coordinator-db PATH] [--config ...]
#
#   python -m management.person.person_admin update
#          (--id N | --system-username h0XXXXX)
#          [--display-name "..."] [--set-investigator 0|1]
#          [--set-supervisor 0|1] [--set-support 0|1]
#          [--actor SYSUSER] [--coordinator-db PATH] [--config ...]
#
# Verhalten:
#   - system_username ist die Identität und wird NIE geändert; kein Löschen
#     (Stilllegen über --set-investigator 0). Beide Regeln schützen Belege und
#     die FK cases.assigned_to.
#   - --actor SYSUSER -> audit_log.actor_id; fehlt es, actor_id=NULL (System)
#     und OS-Benutzer in audit_log.meta.performed_by. Beim allerersten Ermittler
#     (Bootstrap) existiert naturgemäß noch kein Akteur -> --actor entfällt.
#   - Nicht-fatal, klare Fehlermeldungen; Exit 0 = ok, 1 = Fehler.
#
# Beleg: Bauplan B7 v0.4 §5, Projektgespräch 2026-07-01, mc 2026-07-01.
# Build 342 (Welle 0): Modul management.investigators -> management.person;
#   CLI 'python -m management.person.person_admin'; Klassen PersonRepo/
#   PersonError; Tabelle 'investigators' -> 'person'. Audit-Vokabular
#   (target_type='investigator', EventType.INVESTIGATOR_*) unveraendert.
# Version: v0.7.342 · Build: 342 · 2026-07-10
# =============================================================================

import argparse
import getpass
import sqlite3
import sys
from pathlib import Path

from management.audit.audit_log import AuditLog
from management.gateway.coordinator_writer import CoordinatorWriter
from management.person.person_repo import (
    PersonError,
    PersonRepo,
)


def _resolve_db_path(args) -> str:
    """Bestimmt den coordinator.db-Pfad aus --coordinator-db oder config.yaml."""
    if args.coordinator_db:
        return args.coordinator_db
    try:
        from core.config_loader import ConfigLoader
        cfg = ConfigLoader(config_path=args.config)
        path = cfg.get("paths.coordinator_db")
        if path:
            return str(path)
    except Exception as exc:  # pragma: no cover
        print("[person_admin] config.yaml nicht lesbar: %s" % exc,
              file=sys.stderr)
    raise SystemExit(
        "[person_admin] Kein coordinator.db-Pfad: --coordinator-db oder "
        "paths.coordinator_db in config.yaml."
    )


def _open_con(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def _lookup_actor_id(con: sqlite3.Connection, system_username: str) -> int:
    row = con.execute(
        "SELECT id FROM person WHERE system_username = ?",
        (system_username,),
    ).fetchone()
    if row is None:
        raise SystemExit(
            "[person_admin] Unbekannter Akteur (--actor %r)."
            % system_username
        )
    return int(row[0])


def _resolve_actor(con: sqlite3.Connection, actor: str):
    """Gibt (actor_id, meta) zurück: entweder person.id oder System +
    OS-Benutzer in meta.performed_by."""
    if actor:
        return _lookup_actor_id(con, actor), None
    return None, {"performed_by": getpass.getuser()}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Auditierte Verwaltung der Ermittlerstammdaten (person)."
    )
    sub = parser.add_subparsers(dest="action", required=True)

    # Gemeinsame Optionen als Eltern-Parser.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--coordinator-db", default=None)
    common.add_argument("--config", default="./config.yaml")

    # Akteur-Option (nur für schreibende Aktionen).
    actor = argparse.ArgumentParser(add_help=False)
    actor.add_argument("--actor", default=None,
                       help="system_username des Ausführenden (Audit-Akteur)")

    # list
    sub.add_parser("list", parents=[common],
                   help="Alle Ermittler auflisten.")

    # create
    p_create = sub.add_parser("create", parents=[common, actor],
                              help="Neuen Ermittler anlegen.")
    p_create.add_argument("--system-username", required=True,
                          help="Windows-SAMAccountName, z. B. h0XXXXX")
    p_create.add_argument("--display-name", required=True,
                          help='Anzeigename, z. B. "Nachname, Vorname"')
    p_create.add_argument("--supervisor", action="store_true",
                          help="is_supervisor=1")
    p_create.add_argument("--support", action="store_true",
                          help="is_support=1")
    p_create.add_argument("--no-investigator", action="store_true",
                          help="is_investigator=0 (z. B. reine Support-Kraft)")

    # update
    p_update = sub.add_parser("update", parents=[common, actor],
                              help="Vorhandenen Ermittler ändern.")
    g = p_update.add_mutually_exclusive_group(required=True)
    g.add_argument("--id", type=int, default=None)
    g.add_argument("--system-username", default=None)
    p_update.add_argument("--display-name", default=None)
    p_update.add_argument("--set-investigator", type=int, choices=[0, 1],
                          default=None)
    p_update.add_argument("--set-supervisor", type=int, choices=[0, 1],
                          default=None)
    p_update.add_argument("--set-support", type=int, choices=[0, 1], default=None)

    return parser


def _print_row(r) -> None:
    flags = []
    if r["is_investigator"]:
        flags.append("Ermittler")
    if r["is_supervisor"]:
        flags.append("Supervisor")
    if r["is_support"]:
        flags.append("Support")
    print("  #%-4d %-12s %-28s [%s]" % (
        r["id"], r["system_username"], r["display_name"],
        ", ".join(flags) if flags else "—",
    ))


def _cmd_list(repo: PersonRepo) -> int:
    rows = repo.list_persons()
    if not rows:
        print("[person_admin] Keine Ermittler eingetragen.")
        return 0
    print("[person_admin] %d Ermittler:" % len(rows))
    for r in rows:
        _print_row(r)
    return 0


def _cmd_create(repo, args, actor_id, meta) -> int:
    seq = repo.create(
        args.system_username, args.display_name,
        is_investigator=not args.no_investigator,
        is_supervisor=args.supervisor,
        is_support=args.support,
        actor_id=actor_id, meta=meta,
    )
    print("[person_admin] Ermittler angelegt: %s (audit seq=%d)"
          % (args.system_username, seq))
    return 0


def _cmd_update(repo, args, actor_id, meta) -> int:
    kwargs = dict(actor_id=actor_id, meta=meta)
    if args.id is not None:
        kwargs["id"] = args.id
    else:
        kwargs["system_username"] = args.system_username
    if args.display_name is not None:
        kwargs["display_name"] = args.display_name
    if args.set_investigator is not None:
        kwargs["is_investigator"] = bool(args.set_investigator)
    if args.set_supervisor is not None:
        kwargs["is_supervisor"] = bool(args.set_supervisor)
    if args.set_support is not None:
        kwargs["is_support"] = bool(args.set_support)

    seq = repo.update(**kwargs)
    ident = args.system_username if args.system_username is not None else \
        ("#%d" % args.id)
    print("[person_admin] Ermittler %s geändert (audit seq=%d)"
          % (ident, seq))
    return 0


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(args)
    if not Path(db_path).exists():
        print("[person_admin] coordinator.db nicht gefunden: %s" % db_path,
              file=sys.stderr)
        return 1

    con = _open_con(db_path)
    try:
        audit = AuditLog(con)
        writer = CoordinatorWriter(con, audit)
        repo = PersonRepo(con, writer)

        if args.action == "list":
            return _cmd_list(repo)

        # Für schreibende Aktionen den Akteur auflösen.
        actor_id, meta = _resolve_actor(con, args.actor)

        if args.action == "create":
            return _cmd_create(repo, args, actor_id, meta)
        if args.action == "update":
            return _cmd_update(repo, args, actor_id, meta)

        parser.print_help()
        return 1
    except PersonError as exc:
        print("[person_admin] %s" % exc, file=sys.stderr)
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())

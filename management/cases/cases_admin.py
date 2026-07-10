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
#   python -m management.cases.cases_admin --user-id N --username NAME
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
# Version: v0.7.307 · Build: 307 · 2026-07-01
# =============================================================================

import argparse
import getpass
import sqlite3
import sys
from pathlib import Path

from management.audit.audit_log import AuditLog
from management.cases.cases_repo import CasesError, CasesRepo
from management.gateway.coordinator_writer import CoordinatorWriter


def _resolve_db_path(args) -> str:
    if args.coordinator_db:
        return args.coordinator_db
    try:
        from core.config_loader import ConfigLoader
        cfg = ConfigLoader(config_path=args.config)
        path = cfg.get("paths.coordinator_db")
        if path:
            return str(path)
    except Exception as exc:  # pragma: no cover
        print("[cases_admin] config.yaml nicht lesbar: %s" % exc, file=sys.stderr)
    raise SystemExit(
        "[cases_admin] Kein coordinator.db-Pfad: --coordinator-db oder "
        "paths.coordinator_db in config.yaml."
    )


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
        description="Auditierte Verwaltung der Fallakten (cases)."
    )
    parser.add_argument("--user-id", type=int, required=True)
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
        con.execute("PRAGMA journal_mode=WAL")

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

        uid = args.user_id

        # Fall ggf. anlegen.
        if repo.get_case(uid) is None:
            if not args.username:
                print("[cases_admin] Fall user_id=%d fehlt und kein --username "
                      "zum Anlegen angegeben." % uid, file=sys.stderr)
                return 1
            seq = repo.create_case(uid, args.username, actor_id=actor_id, meta=meta)
            print("[cases_admin] Fall angelegt: user_id=%d (audit seq=%d)" % (uid, seq))

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

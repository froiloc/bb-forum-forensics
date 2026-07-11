# =============================================================================
# management/rbac/rbac_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Auditierte Kommandozeile fuer die RBAC-Matrix: Vergabe/Ruecknahme von
#   Faehigkeits-Grants (Rolle -> Faehigkeit [+ Scope]) und Rollenzuweisungen
#   (Person -> Rolle). JEDE Aenderung laeuft ueber das CoordinatorWriter-Gateway
#   und erzeugt einen lueckenlosen audit_log-Eintrag. Die Durchsetzung (Resolver)
#   folgt in Schnitt (c); diese CLII ist der Schreib-/Pflegepfad (Schnitt b).
#
# Aufruf (Auszug):
#   python -m management.rbac.rbac_admin catalog
#          [--coordinator-db PATH] [--config ./config.yaml]
#
#   python -m management.rbac.rbac_admin grant
#          --role ROLE --capability CAP [--scope alle|eigene] [--note "..."]
#          [--actor SYSUSER] [--coordinator-db PATH] [--config ...]
#
#   python -m management.rbac.rbac_admin revoke-grant --id N
#          [--note "..."] [--actor SYSUSER] ...
#
#   python -m management.rbac.rbac_admin assign-role
#          (--person-id N | --person SYSUSER) --role ROLE [--actor SYSUSER] ...
#
#   python -m management.rbac.rbac_admin revoke-role --id N [--actor SYSUSER] ...
#
#   python -m management.rbac.rbac_admin list-grants  [--role R1,R2] [--all]
#   python -m management.rbac.rbac_admin list-roles   [--person SYSUSER] [--id N1,N2] [--role R1,R2] [--all]
#
# Verhalten:
#   - Katalog-Validierung: unbekannte Rolle/Faehigkeit/Scope -> Fehler, kein
#     Schreibvorgang.
#   - Append-only Soft-Revoke: revoke-* setzt revoked_* (kein DELETE).
#   - --actor SYSUSER -> audit_log.actor_id; fehlt es, actor_id=NULL (System)
#     und OS-Benutzer in audit_log.meta.performed_by.
#   - Nicht-fatal, klare Fehlermeldungen; Exit 0 = ok, 1 = Fehler.
#
# Beleg: Bauplan B7 v1.1 §11.1/§11.3/§11.7 (Schnitt b), mc 2026-07-10.
# Build 365 (CLI-Filter): list-grants --role R1,R2,... und list-roles
#   --id N1,N2,... / --role R1,R2,... (jeweils kommagetrennt; --person und --id
#   werden vereinigt). Warnung bei unbekannten Rollen (Grundregel 1).
#
# Version: v0.7.365 · Build: 365 · 2026-07-10
# =============================================================================

import argparse
import getpass
import sqlite3
import sys
from pathlib import Path

from management.audit.audit_log import AuditLog
from management.gateway.coordinator_writer import CoordinatorWriter
from management.rbac import catalog
from management.rbac.rbac_repo import RbacError, RbacRepo


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
        print("[rbac_admin] config.yaml nicht lesbar: %s" % exc,
              file=sys.stderr)
    raise SystemExit(
        "[rbac_admin] Kein coordinator.db-Pfad: --coordinator-db oder "
        "paths.coordinator_db in config.yaml."
    )


def _open_con(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def _lookup_person_id(con: sqlite3.Connection, system_username: str) -> int:
    row = con.execute(
        "SELECT id FROM person WHERE system_username = ?",
        (system_username,),
    ).fetchone()
    if row is None:
        raise SystemExit(
            "[rbac_admin] Unbekannte Person (--person %r)." % system_username)
    return int(row[0])


def _resolve_actor(con: sqlite3.Connection, actor):
    """(actor_id, meta): person.id oder System + OS-Benutzer in meta."""
    if actor:
        return _lookup_person_id(con, actor), None
    return None, {"performed_by": getpass.getuser()}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Auditierte Verwaltung der RBAC-Matrix (Grants/Rollen).")
    sub = parser.add_subparsers(dest="action", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--coordinator-db", default=None)
    common.add_argument("--config", default="./config.yaml")

    actor = argparse.ArgumentParser(add_help=False)
    actor.add_argument("--actor", default=None,
                       help="system_username des Ausfuehrenden (Audit-Akteur)")

    # catalog (rein informativ, kein DB-Write)
    sub.add_parser("catalog", parents=[common],
                   help="Gueltige Rollen und Faehigkeiten (Code-Katalog) zeigen.")

    # grant
    p_grant = sub.add_parser("grant", parents=[common, actor],
                             help="Rolle eine Faehigkeit vergeben.")
    p_grant.add_argument("--role", required=True)
    p_grant.add_argument("--capability", required=True)
    p_grant.add_argument("--scope", choices=["alle", "eigene"], default=None)
    p_grant.add_argument("--note", default=None)

    # revoke-grant
    p_rg = sub.add_parser("revoke-grant", parents=[common, actor],
                          help="Grant zuruecknehmen (Soft-Revoke).")
    p_rg.add_argument("--id", type=int, required=True)
    p_rg.add_argument("--note", default=None)

    # assign-role
    p_ar = sub.add_parser("assign-role", parents=[common, actor],
                          help="Person eine Rolle zuweisen.")
    g = p_ar.add_mutually_exclusive_group(required=True)
    g.add_argument("--person-id", type=int, default=None)
    g.add_argument("--person", default=None, help="system_username der Person")
    p_ar.add_argument("--role", required=True)

    # revoke-role
    p_rr = sub.add_parser("revoke-role", parents=[common, actor],
                          help="Rollenzuweisung zuruecknehmen (Soft-Revoke).")
    p_rr.add_argument("--id", type=int, required=True)

    # list-grants
    p_lg = sub.add_parser("list-grants", parents=[common],
                          help="Grants auflisten.")
    p_lg.add_argument("--role", default=None,
                      help="nur diese Rolle(n), kommagetrennt")
    p_lg.add_argument("--all", action="store_true",
                      help="auch zurueckgenommene Grants")

    # list-roles
    p_lr = sub.add_parser("list-roles", parents=[common],
                          help="Rollenzuweisungen auflisten.")
    p_lr.add_argument("--person", default=None,
                      help="nur diese Person (system_username)")
    p_lr.add_argument("--id", default=None,
                      help="nur diese person_id(s), kommagetrennt")
    p_lr.add_argument("--role", default=None,
                      help="nur diese Rolle(n), kommagetrennt")
    p_lr.add_argument("--all", action="store_true",
                      help="auch zurueckgenommene Zuweisungen")

    return parser


def _cmd_catalog() -> int:
    print("[rbac_admin] Rollen (%d):" % len(catalog.ROLES))
    for r in catalog.ROLES:
        print("  %-14s %s" % (r.code, r.label))
    print("[rbac_admin] Faehigkeiten (%d):" % len(catalog.CAPABILITIES))
    for c in catalog.CAPABILITIES:
        print("  %-26s %s" % (c.code, c.label))
    return 0


def _cmd_grant(repo, args, actor_id, meta) -> int:
    seq = repo.grant(args.role, args.capability, scope=args.scope,
                     actor_id=actor_id, note=args.note, meta=meta)
    print("[rbac_admin] Grant %s -> %s (scope=%s) vergeben (audit seq=%d)"
          % (args.role, args.capability, args.scope or "-", seq))
    return 0


def _cmd_revoke_grant(repo, args, actor_id, meta) -> int:
    seq = repo.revoke_grant(args.id, actor_id=actor_id, note=args.note,
                            meta=meta)
    print("[rbac_admin] Grant id=%d zurueckgenommen (audit seq=%d)"
          % (args.id, seq))
    return 0


def _cmd_assign_role(repo, con, args, actor_id, meta) -> int:
    person_id = args.person_id if args.person_id is not None \
        else _lookup_person_id(con, args.person)
    seq = repo.assign_role(person_id, args.role, actor_id=actor_id, meta=meta)
    print("[rbac_admin] Rolle '%s' -> Person id=%d zugewiesen (audit seq=%d)"
          % (args.role, person_id, seq))
    return 0


def _cmd_revoke_role(repo, args, actor_id, meta) -> int:
    seq = repo.revoke_role(args.id, actor_id=actor_id, meta=meta)
    print("[rbac_admin] Rollenzuweisung id=%d zurueckgenommen (audit seq=%d)"
          % (args.id, seq))
    return 0


def _csv_set(value):
    """Kommagetrennte Zeichenkette -> Menge (None bleibt None). Leere Tokens
    werden verworfen."""
    if value is None:
        return None
    return {tok.strip() for tok in value.split(",") if tok.strip()}


def _csv_int_set(value):
    """Wie _csv_set, aber ganzzahlig. Wirft ValueError bei ungueltigem Token."""
    if value is None:
        return None
    out = set()
    for tok in value.split(","):
        tok = tok.strip()
        if tok:
            out.add(int(tok))
    return out


def _warn_unknown_roles(role_set) -> None:
    """Warnt (stderr), wenn Rollen-Tokens nicht im Katalog stehen — kein stilles
    Verschlucken (Grundregel 1)."""
    if not role_set:
        return
    unknown = sorted(r for r in role_set if r not in catalog.ROLE_CODES)
    if unknown:
        print("[rbac_admin] WARNUNG: unbekannte Rolle(n): %s"
              % ", ".join(unknown), file=sys.stderr)


def _cmd_list_grants(repo, args) -> int:
    rows = repo.list_grants(active_only=not args.all)
    role_filter = _csv_set(getattr(args, "role", None))
    if role_filter is not None:
        _warn_unknown_roles(role_filter)
        rows = [r for r in rows if r["role_code"] in role_filter]
    if not rows:
        print("[rbac_admin] Keine Grants.")
        return 0
    print("[rbac_admin] %d Grant(s):" % len(rows))
    for r in rows:
        state = "zurueckgenommen" if r["revoked_at"] else "aktiv"
        print("  #%-4d %-14s -> %-26s scope=%-7s [%s]" % (
            r["id"], r["role_code"], r["capability_code"],
            r["scope"] or "-", state))
    return 0


def _cmd_list_roles(repo, con, args) -> int:
    # Personen-Filter: --id (kommagetrennte person_id-Liste) und/oder --person
    # (system_username, Einzelperson) werden vereinigt.
    try:
        id_filter = _csv_int_set(getattr(args, "id", None))
    except ValueError:
        print("[rbac_admin] --id erwartet ganzzahlige person_id(s).",
              file=sys.stderr)
        return 1
    if args.person:
        pid = _lookup_person_id(con, args.person)
        id_filter = (id_filter or set()) | {pid}

    role_filter = _csv_set(getattr(args, "role", None))
    if role_filter is not None:
        _warn_unknown_roles(role_filter)

    rows = repo.list_person_roles(None, active_only=not args.all)
    if id_filter is not None:
        rows = [r for r in rows if r["person_id"] in id_filter]
    if role_filter is not None:
        rows = [r for r in rows if r["role_code"] in role_filter]

    if not rows:
        print("[rbac_admin] Keine Rollenzuweisungen.")
        return 0
    print("[rbac_admin] %d Rollenzuweisung(en):" % len(rows))
    for r in rows:
        state = "zurueckgenommen" if r["revoked_at"] else "aktiv"
        print("  #%-4d person=%-4d rolle=%-14s [%s]" % (
            r["id"], r["person_id"], r["role_code"], state))
    return 0


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.action == "catalog":
        return _cmd_catalog()

    db_path = _resolve_db_path(args)
    if not Path(db_path).exists():
        print("[rbac_admin] coordinator.db nicht gefunden: %s" % db_path,
              file=sys.stderr)
        return 1

    con = _open_con(db_path)
    try:
        audit = AuditLog(con)
        writer = CoordinatorWriter(con, audit)
        repo = RbacRepo(con, writer)

        if args.action == "list-grants":
            return _cmd_list_grants(repo, args)
        if args.action == "list-roles":
            return _cmd_list_roles(repo, con, args)

        # Schreibende Aktionen: Akteur aufloesen.
        actor_id, meta = _resolve_actor(con, args.actor)

        if args.action == "grant":
            return _cmd_grant(repo, args, actor_id, meta)
        if args.action == "revoke-grant":
            return _cmd_revoke_grant(repo, args, actor_id, meta)
        if args.action == "assign-role":
            return _cmd_assign_role(repo, con, args, actor_id, meta)
        if args.action == "revoke-role":
            return _cmd_revoke_role(repo, args, actor_id, meta)

        parser.print_help()
        return 1
    except RbacError as exc:
        print("[rbac_admin] %s" % exc, file=sys.stderr)
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())

# =============================================================================
# management/external/case_release_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Externe Fallfreigabe (AP-2G)
# =============================================================================
# Zweck:
#   CLI fuer die externe Fallfreigabe (M016). BETRIEBSWEG (Skripte, Nachpflege);
#   der Normalfall bleibt die Cockpit-Sicht (Build 463).
#
#   Aufruf:  python -m management.external.case_release_admin <befehl> [...]
#
#     recipients                      Berechtigte AD-Empfaenger (aus config)
#     list        [--subject-id N] [--status S ...]
#     grant       --subject-id N --recipient KENNUNG --umfang bericht|akte|auszug
#                 --grundlage TEXT --actor KENNUNG
#     revoke      --id N --grund TEXT --actor KENNUNG
#     umfang                          Katalog der Umfangsarten
#
#   --actor ist bei JEDEM Schreibbefehl Pflicht: ein Beleg ohne Handelnden ist
#   kein Beleg. Der Empfaenger wird ueber die AD-Schicht geprueft (Default-Deny).
#
#   EXIT-CODES: 0 = ok · 1 = Aufruf-/Fachfehler.
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import argparse
import logging
import sqlite3
import sys
from typing import List, Optional

from management.audit.audit_log import AuditLog
from management.external.ad_directory import ADDirectory
from management.external.case_release_repo import (
    CaseReleaseError,
    CaseReleaseRepo,
)
from management.external.release_status import STATUSES, umfang_catalog, UMFANG_ORDER
from management.gateway.coordinator_writer import CoordinatorWriter
from management.help import cli_epilog  # noqa: E402
# Build 643: die Vorrangregel Argument > config.yaml > Vorgabewert
# steht seit diesem Build an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402

logger = logging.getLogger(__name__)


def _resolve_db_path(args) -> str:
    """
    coordinator.db-Pfad: Argument --db > paths.coordinator_db > Abbruch.

    BUILD 643 - DIE AUFLOESUNG IST UMGEZOGEN, das Verhalten NICHT.
    Bis Build 642 stand hier eine eigene Abschrift derselben zwoelf Zeilen;
    fuenfundzwanzig Werkzeuge trugen sie, und sie waren nicht identisch (die
    Begruendung steht im Kopf von core/werkzeug_konfig.py). Sie steht jetzt an
    EINER Stelle.

    UNVERAENDERT bleiben: die Reihenfolge, das Fehlen eines Vorgabewerts
    (ein erratener Pfad waere schlimmer als ein Abbruch), die Meldung ueber
    eine unlesbare config.yaml auf stderr und der Abbruch mit dem Praefix
    '[case_release_admin]'. Die Abbruchmeldung nennt jetzt BEIDE Wege statt nur einen.
    """
    return werkzeug_konfig.db_pfad(
        "case_release_admin", args, arg_attribut="db", arg_name="--db",
        config_schluessel="paths.coordinator_db", name="db")


def _con(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    return con


def _actor_id(con: sqlite3.Connection, kennung: str) -> int:
    row = con.execute(
        "SELECT id FROM person WHERE system_username = ?", (kennung,)
    ).fetchone()
    if row is None:
        raise CaseReleaseError(
            "Unbekannte Kennung '%s' (person.system_username)." % kennung)
    return int(row[0])


def _ad(args) -> ADDirectory:
    try:
        return ADDirectory.from_config(args.config)
    except Exception as exc:  # pragma: no cover
        print("[case_release_admin] AD-Allowlist nicht lesbar: %s" % exc,
              file=sys.stderr)
        return ADDirectory()   # leer -> Default-Deny


def _print_releases(rows: List[dict]) -> None:
    if not rows:
        print("Keine Freigaben.")
        return
    print("%-5s %-7s %-16s %-8s %-12s %s"
          % ("ID", "Fall", "Empfaenger", "Umfang", "Zustand", "Anzeigename"))
    print("-" * 92)
    for r in rows:
        print("%-5s %-7s %-16s %-8s %-12s %s"
              % (r["id"], r["subject_id"], (r["recipient_kennung"] or "")[:16],
                 r["umfang"], r["status"], (r["recipient_display"] or "")[:34]))
    print("-" * 92)


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ap = argparse.ArgumentParser(
        prog="case_release_admin",
        description="Externe Fallfreigabe an NRW-Ermittler (coordinator.db).",
        epilog=cli_epilog.epilog("case_release_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    ap.add_argument("--db", default=None, help="Pfad zur coordinator.db")
    ap.add_argument("--config", default="./config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("recipients", help="Berechtigte AD-Empfaenger (config)")
    sub.add_parser("umfang", help="Katalog der Umfangsarten")

    p = sub.add_parser("list", help="Freigaben auflisten")
    p.add_argument("--subject-id", type=int, default=None)
    p.add_argument("--status", action="append", choices=list(STATUSES))

    p = sub.add_parser("grant", help="Fall freigeben (auditiert)")
    p.add_argument("--subject-id", type=int, required=True)
    p.add_argument("--recipient", required=True, help="AD-Kennung (NRW)")
    p.add_argument("--umfang", required=True, choices=list(UMFANG_ORDER))
    p.add_argument("--grundlage", required=True,
                   help="Unbedenklichkeits-Grundlage (Pflicht)")
    p.add_argument("--actor", required=True)

    p = sub.add_parser("revoke", help="Freigabe widerrufen (Grund Pflicht)")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--grund", required=True)
    p.add_argument("--actor", required=True)

    args = ap.parse_args(argv)

    if args.cmd == "umfang":
        for u in umfang_catalog():
            print("%-10s %s" % (u["code"], u["label"]))
        return 0
    if args.cmd == "recipients":
        members = _ad(args).members()
        if not members:
            print("Keine berechtigten Empfaenger konfiguriert "
                  "(ad.release_recipients) — Default-Deny.")
            return 0
        for m in members:
            print("%-16s %s" % (m["kennung"], m["display_name"]))
        return 0

    db = _resolve_db_path(args)
    con = _con(db)
    try:
        if args.cmd == "list":
            repo = CaseReleaseRepo(con)
            rows = repo.list_releases(
                subject_ids=[args.subject_id] if args.subject_id is not None else None,
                statuses=args.status)
            _print_releases(rows)
            return 0

        actor = _actor_id(con, args.actor)

        if args.cmd == "grant":
            repo = CaseReleaseRepo(
                con, CoordinatorWriter(con, AuditLog(con)), ad=_ad(args))
            res = repo.grant(
                subject_id=args.subject_id, recipient_kennung=args.recipient,
                umfang=args.umfang,
                unbedenklichkeit_grundlage=args.grundlage, actor_id=actor)
            print("Fall %s an %s (%s) freigegeben — Freigabe %s (Beleg #%s)."
                  % (args.subject_id, res["recipient_kennung"],
                     res["recipient_display"], res["release_id"],
                     res["audit_seq"]))
            return 0

        if args.cmd == "revoke":
            repo = CaseReleaseRepo(con, CoordinatorWriter(con, AuditLog(con)))
            seq = repo.revoke(args.id, grund=args.grund, actor_id=actor)
            print("Freigabe %s widerrufen (Beleg #%s)." % (args.id, seq))
            return 0

        ap.error("Unbekannter Befehl.")
        return 1

    except CaseReleaseError as exc:
        print("FEHLER: %s" % exc, file=sys.stderr)
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())

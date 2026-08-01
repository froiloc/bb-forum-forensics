# =============================================================================
# management/onboarding/onboarding_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Onboarding/Offboarding (AP-2G)
# =============================================================================
# Zweck:
#   CLI fuer die Onboarding-/Offboarding-Checkliste (M017). BETRIEBSWEG; der
#   Normalfall bleibt die Cockpit-Sicht (Build 465).
#
#   Aufruf:  python -m management.onboarding.onboarding_admin <befehl> [...]
#
#     steps   --kind onboarding|offboarding      Schritt-Katalog
#     show    --person-id N --kind K             Stand der Checkliste
#     set     --person-id N --kind K --step CODE --status erledigt|nicht_zutreffend|offen
#             [--note TEXT] --actor KENNUNG
#
#   --actor ist bei JEDEM Schreibbefehl Pflicht. 'nicht_zutreffend' verlangt
#   --note (Grund-Pflicht). 'offen' setzt den Schritt zurueck (loescht die Zeile).
#
#   EXIT-CODES: 0 = ok · 1 = Aufruf-/Fachfehler.
#
# Version: v0.7.464 · Build: 464 · 2026-07-20
# =============================================================================

import argparse
import logging
import sqlite3
import sys
from typing import List, Optional

from management.audit.audit_log import AuditLog
from management.gateway.coordinator_writer import CoordinatorWriter
from management.onboarding.checklist_status import (
    ChecklistStatus,
    KINDS,
    STATUS_ORDER,
)
from management.onboarding.onboarding_repo import OnboardingError, OnboardingRepo
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
    '[onboarding_admin]'. Die Abbruchmeldung nennt jetzt BEIDE Wege statt nur einen.
    """
    return werkzeug_konfig.db_pfad(
        "onboarding_admin", args, arg_attribut="db", arg_name="--db",
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
        raise OnboardingError(
            "Unbekannte Kennung '%s' (person.system_username)." % kennung)
    return int(row[0])


def _print_checklist(rows: List[dict], load: Optional[int]) -> None:
    print("%-22s %-16s %s" % ("Schritt", "Zustand", "Notiz/Beschreibung"))
    print("-" * 78)
    for r in rows:
        extra = r.get("note") or r.get("label") or ""
        print("%-22s %-16s %s"
              % (r["step_code"], r["status"], extra[:38]))
    print("-" * 78)
    if load is not None:
        print("Noch offen zugewiesene Faelle dieser Person: %d" % load)


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ap = argparse.ArgumentParser(
        prog="onboarding_admin",
        description="Onboarding-/Offboarding-Checkliste (coordinator.db).",
        epilog=cli_epilog.epilog("onboarding_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    ap.add_argument("--db", default=None, help="Pfad zur coordinator.db")
    ap.add_argument("--config", default="./config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("steps", help="Schritt-Katalog")
    p.add_argument("--kind", required=True, choices=list(KINDS))

    p = sub.add_parser("show", help="Stand der Checkliste")
    p.add_argument("--person-id", type=int, required=True)
    p.add_argument("--kind", required=True, choices=list(KINDS))

    p = sub.add_parser("set", help="Schritt setzen (auditiert)")
    p.add_argument("--person-id", type=int, required=True)
    p.add_argument("--kind", required=True, choices=list(KINDS))
    p.add_argument("--step", required=True)
    p.add_argument("--status", required=True, choices=list(STATUS_ORDER))
    p.add_argument("--note", default="")
    p.add_argument("--actor", required=True)

    args = ap.parse_args(argv)

    if args.cmd == "steps":
        for code, label in ChecklistStatus.steps(args.kind):
            print("%-22s %s" % (code, label))
        return 0

    db = _resolve_db_path(args)
    con = _con(db)
    try:
        if args.cmd == "show":
            repo = OnboardingRepo(con)
            rows = repo.checklist(args.person_id, args.kind)
            load = (repo.open_case_load(args.person_id)
                    if args.kind == "offboarding" else None)
            _print_checklist(rows, load)
            return 0

        if args.cmd == "set":
            actor = _actor_id(con, args.actor)
            repo = OnboardingRepo(con, CoordinatorWriter(con, AuditLog(con)))
            res = repo.set_step(
                person_id=args.person_id, kind=args.kind, step_code=args.step,
                status=args.status, note=args.note, actor_id=actor)
            verb = ("zurueckgesetzt" if res["removed"]
                    else ("angelegt" if res["created"] else "aktualisiert"))
            print("Schritt %s/%s Person %s -> %s (%s, Beleg #%s)."
                  % (args.kind, args.step, args.person_id, res["status"],
                     verb, res["audit_seq"]))
            return 0

        ap.error("Unbekannter Befehl.")
        return 1

    except OnboardingError as exc:
        print("FEHLER: %s" % exc, file=sys.stderr)
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())

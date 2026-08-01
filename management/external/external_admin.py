# =============================================================================
# management/external/external_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   CLI fuer die Wiedervorlage externer Vorgaenge. Sie ist der BETRIEBSWEG
#   (Skripte, Stapel, Nachpflege) — der Normalfall bleibt die Cockpit-Sicht
#   (Build 386).
#
#   Aufruf:  python -m management.external.external_admin <befehl> [...]
#
#     list    [--subject-id N] [--status S ...] [--offen] [--stichtag YYYY-MM-DD]
#     add     --subject-id N --kind K --betreff T --wiedervorlage YYYY-MM-DD
#             [--angefordert YYYY-MM-DD] [--adressat A] [--az AZ]
#             [--vorwarnfrist N] --actor KENNUNG
#     defer   --id N --wiedervorlage YYYY-MM-DD --grund G [--vorwarnfrist N]
#             --actor KENNUNG
#     answer  --id N [--ergebnis E] [--wiedervorlage YYYY-MM-DD] --actor KENNUNG
#     close   --id N --status erledigt|erfolglos [--ergebnis E] --actor KENNUNG
#     kinds   (Katalog der Vorgangsarten)
#
#   --actor ist bei JEDEM Schreibbefehl Pflicht: ein Beleg ohne Handelnden ist
#   kein Beleg (gleiche Regel wie case_detect --auto, Build 383).
#
#   EXIT-CODES:
#     0 = nichts zu beanstanden
#     2 = es gibt UEBERFAELLIGE oder VERWAISTE Vorgaenge (rote Ampel) — der
#         Befund wird umrahmt auf stderr gemeldet, damit ein Skript ihn nicht
#         uebersieht (Grundregel 1).
#     1 = Aufruf-/Fachfehler
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import argparse
import logging
import sqlite3
import sys
from typing import List, Optional

from management.audit.audit_log import AuditLog
from management.calendar import stichtag as stichtag_mod
from management.external import matter_kinds
from management.external.external_matters_repo import (
    ExternalMattersError,
    ExternalMattersRepo,
)
from management.external.matter_status import STATUS_ORDER, OPEN_STATUSES
from management.gateway.coordinator_writer import CoordinatorWriter
from management.help import cli_epilog  # noqa: E402

logger = logging.getLogger(__name__)


def _resolve_db_path(args) -> str:
    """DB-Pfad wie in cases_admin (Build 307): --db > config.yaml > Abbruch."""
    if args.db:
        return args.db
    try:
        from core.config_loader import ConfigLoader
        cfg = ConfigLoader(config_path=args.config)
        path = cfg.get("paths.coordinator_db")
        if path:
            return str(path)
    except Exception as exc:  # pragma: no cover
        print("[external_admin] config.yaml nicht lesbar: %s" % exc,
              file=sys.stderr)
    raise SystemExit(
        "[external_admin] Kein coordinator.db-Pfad: --db oder "
        "paths.coordinator_db in config.yaml.")


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
        raise ExternalMattersError(
            "Unbekannte Kennung '%s' (person.system_username)." % kennung)
    return int(row[0])


def _repo(con: sqlite3.Connection, schreibend: bool) -> ExternalMattersRepo:
    if not schreibend:
        return ExternalMattersRepo(con)
    return ExternalMattersRepo(con, CoordinatorWriter(con, AuditLog(con)))


def _print_list(rows: List[dict], tag: str) -> int:
    """Gibt die Liste aus. Rueckgabe: Anzahl ROTER Vorgaenge."""
    if not rows:
        print("Keine externen Vorgaenge.")
        return 0

    print("%-5s %-7s %-16s %-11s %-14s %-6s %s"
          % ("ID", "Fall", "Art", "Wiedervorl.", "Zustand", "Ampel", "Betreff"))
    print("-" * 100)
    rot = 0
    for r in rows:
        if r["ampel"] == "rot":
            rot += 1
        print("%-5s %-7s %-16s %-11s %-14s %-6s %s"
              % (r["id"], r["subject_id"], r["kind"][:16], r["wiedervorlage_am"],
                 r["status"][:14], r["ampel"], (r["betreff"] or "")[:40]))
    print("-" * 100)
    print(stichtag_mod.stichtag_text({"stichtag": tag,
                                      "zeitzone": "Europe/Berlin"}))
    return rot


def _warn_rot(rows: List[dict]) -> None:
    """Rote Vorgaenge umrahmt auf stderr — ein Skript darf das nicht uebersehen."""
    rot = [r for r in rows if r["ampel"] == "rot"]
    if not rot:
        return
    line = "=" * 78
    print(line, file=sys.stderr)
    print("ACHTUNG: %d Vorgang/Vorgaenge erfordern SOFORT eine Entscheidung."
          % len(rot), file=sys.stderr)
    for r in rot:
        print("  [%s] Fall %s — %s: %s"
              % (r["id"], r["subject_id"], r["kind"], r["ampel_grund"]),
              file=sys.stderr)
    print(line, file=sys.stderr)


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ap = argparse.ArgumentParser(
        prog="external_admin",
        description="Wiedervorlage externer Vorgaenge (coordinator.db).",
        epilog=cli_epilog.epilog("external_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    ap.add_argument("--db", default=None, help="Pfad zur coordinator.db")
    ap.add_argument("--config", default="./config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="Vorgaenge auflisten")
    p.add_argument("--subject-id", type=int, default=None)
    p.add_argument("--status", action="append", choices=list(STATUS_ORDER))
    p.add_argument("--offen", action="store_true",
                   help="nur offene/beantwortete Vorgaenge")
    p.add_argument("--stichtag", default=None)

    p = sub.add_parser("add", help="Vorgang anlegen")
    p.add_argument("--subject-id", type=int, required=True)
    p.add_argument("--kind", required=True, choices=list(matter_kinds.KIND_ORDER))
    p.add_argument("--betreff", required=True)
    p.add_argument("--wiedervorlage", required=True)
    p.add_argument("--angefordert", default=None)
    p.add_argument("--adressat", default="")
    p.add_argument("--az", default=None)
    p.add_argument("--vorwarnfrist", type=int, default=7)
    p.add_argument("--actor", required=True)

    p = sub.add_parser("defer", help="Wiedervorlage verschieben (Grund Pflicht)")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--wiedervorlage", required=True)
    p.add_argument("--grund", required=True)
    p.add_argument("--vorwarnfrist", type=int, default=None)
    p.add_argument("--actor", required=True)

    p = sub.add_parser("answer", help="Antwort eingegangen")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--ergebnis", default="")
    p.add_argument("--wiedervorlage", default=None)
    p.add_argument("--actor", required=True)

    p = sub.add_parser("close", help="ENDGUELTIG abschliessen")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--status", required=True,
                   choices=["erledigt", "erfolglos"])
    p.add_argument("--ergebnis", default="")
    p.add_argument("--actor", required=True)

    sub.add_parser("kinds", help="Katalog der Vorgangsarten")

    args = ap.parse_args(argv)

    if args.cmd == "kinds":
        for k in matter_kinds.catalog():
            print("%-14s %s" % (k["code"], k["label"]))
        return 0

    db = _resolve_db_path(args)
    con = _con(db)
    try:
        if args.cmd == "list":
            tag = args.stichtag or stichtag_mod.heute()["stichtag"]
            statuses = args.status
            if args.offen:
                statuses = list(OPEN_STATUSES)
            repo = _repo(con, schreibend=False)
            rows = repo.list_matters(
                subject_ids=[args.subject_id] if args.subject_id is not None else None,
                statuses=statuses)
            rows = repo.with_ampel(rows, tag)
            _print_list(rows, tag)
            _warn_rot(rows)
            return 2 if any(r["ampel"] == "rot" for r in rows) else 0

        actor = _actor_id(con, args.actor)
        repo = _repo(con, schreibend=True)

        if args.cmd == "add":
            res = repo.create(
                subject_id=args.subject_id, kind=args.kind, betreff=args.betreff,
                angefordert_am=(args.angefordert
                                or stichtag_mod.heute()["stichtag"]),
                wiedervorlage_am=args.wiedervorlage,
                adressat=args.adressat, aktenzeichen=args.az,
                vorwarnfrist_tage=args.vorwarnfrist, actor_id=actor)
            print("Vorgang %s angelegt (Beleg #%s)."
                  % (res["matter_id"], res["audit_seq"]))
            return 0

        if args.cmd == "defer":
            seq = repo.defer(args.id, wiedervorlage_am=args.wiedervorlage,
                             grund=args.grund,
                             vorwarnfrist_tage=args.vorwarnfrist,
                             actor_id=actor)
            print("Vorgang %s auf %s wiedervorgelegt (Beleg #%s)."
                  % (args.id, args.wiedervorlage, seq))
            return 0

        if args.cmd == "answer":
            seq = repo.answer(args.id, ergebnis=args.ergebnis,
                              wiedervorlage_am=args.wiedervorlage,
                              actor_id=actor)
            print("Vorgang %s als beantwortet erfasst (Beleg #%s)."
                  % (args.id, seq))
            return 0

        if args.cmd == "close":
            seq = repo.close(args.id, status=args.status,
                             ergebnis=args.ergebnis, actor_id=actor)
            print("Vorgang %s ENDGUELTIG abgeschlossen: %s (Beleg #%s)."
                  % (args.id, args.status, seq))
            return 0

        ap.error("Unbekannter Befehl.")
        return 1

    except ExternalMattersError as exc:
        print("FEHLER: %s" % exc, file=sys.stderr)
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())

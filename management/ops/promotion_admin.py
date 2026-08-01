# =============================================================================
# management/ops/promotion_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Betrieb/Governance (AP-2G)
# =============================================================================
# Zweck:
#   CLI fuer die Fremdforum-Promotion (M015). Sie ist der BETRIEBSWEG (Skripte,
#   Stapel, Nachpflege) — der Normalfall bleibt die Cockpit-Sicht (Build 461).
#
#   Aufruf:  python -m management.ops.promotion_admin <befehl> [...]
#
#     candidates                     Aktuelle Fremdforum-Kandidaten + Zustand
#                                     (forensic_<uid>.db vorhanden, evidence fehlt)
#     list                           ALLE erfassten Entscheidungen (Belege)
#     decide  --subject-id N --status gesichtet|uebernommen|zurueckgestellt|
#                                    fremdzustaendig
#             [--grund G] [--herkunft H] [--force] --actor KENNUNG
#
#   --actor ist bei JEDEM Schreibbefehl Pflicht: ein Beleg ohne Handelnden ist
#   kein Beleg (gleiche Regel wie external_admin/case_detect --auto).
#
#   Ohne --force prueft 'decide', dass subject_id AKTUELL ein Fremdforum-Kandidat
#   ist (Dateisystem-Scan). --force uebergeht diese Pruefung bewusst (z. B.
#   Nachpflege eines inzwischen uebernommenen Falls) — der Uebergang selbst
#   bleibt durch die Zustandsmaschine geschuetzt.
#
#   EXIT-CODES: 0 = ok · 1 = Aufruf-/Fachfehler.
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import argparse
import logging
import sqlite3
import sys
from typing import List, Optional, Set

from management.audit.audit_log import AuditLog
from management.gateway.coordinator_writer import CoordinatorWriter
from management.ops.promotion_repo import PromotionError, PromotionRepo
from management.ops.promotion_status import STORED_STATUSES
from management.ops.storage_overview import StorageOverview
from management.help import cli_epilog  # noqa: E402
# Build 645: Vorrangregel an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402

logger = logging.getLogger(__name__)


def _konfig(args):
    """
    Der Aufloeser fuer diesen Aufruf - EINMAL gebaut und weitergereicht.

    BEFUND, DER BEI DER UMSTELLUNG AUFGEFALLEN IST (Build 645): Bis hierher
    hat dieses Werkzeug die config.yaml ZWEIMAL geladen - einmal in
    _resolve_db_path und noch einmal in _data_dirs, beide ueber '_cfg'. Wer
    zwischen den beiden Lesevorgaengen speichert, bekommt einen Lauf, dessen
    Fallpfad und dessen Datenverzeichnisse aus verschiedenen Staenden
    derselben Datei stammen. Aufgefallen ist das nicht durch einen Vorfall,
    sondern weil die Umstellung die Frage gestellt hat, wo die Datei gelesen
    wird. Jetzt wird sie einmal gelesen.
    """
    if not hasattr(args, "_aufloeser"):
        args._aufloeser = werkzeug_konfig.resolver(args)
    return args._aufloeser


def _resolve_db_path(args) -> str:
    """
    coordinator.db-Pfad: Argument --db > paths.coordinator_db > Abbruch.

    BUILD 645: Die Aufloesung steht in core/werkzeug_konfig.py. Verhalten
    unveraendert; die Abbruchmeldung nennt jetzt beide Wege.
    """
    return werkzeug_konfig.db_pfad(
        "promotion_admin", args, arg_attribut="db", arg_name="--db",
        config_schluessel="paths.coordinator_db", name="coordinator_db",
        r=_konfig(args))


def _data_dirs(args):
    """
    (forensic_dir, evidence_dir, assets_dir) aus config.yaml, mit
    Vorgabewerten.

    HIER WIRD NICHT ABGEBROCHEN, und das ist der Unterschied zur Funktion
    darueber: Diese drei Verzeichnisse haben Rueckfallwerte. Der Fallpfad hat
    keinen - deshalb 'wert' hier und 'db_pfad' dort. Am Aufruf soll man
    sehen, welcher der beiden Faelle vorliegt.
    """
    r = _konfig(args)
    hole = lambda attr, schluessel, vorgabe: werkzeug_konfig.wert(
        "promotion_admin", args, arg_attribut=attr, arg_name="(kein Argument)",
        config_schluessel=schluessel, default=vorgabe, name=attr,
        wandler=str, r=r)
    return (hole("forensic_dir", "paths.forensic_db_dir", "./data/forensic/"),
            hole("evidence_dir", "paths.evidence_db_dir", "./data/evidence/"),
            hole("assets_dir", "paths.assets_db_dir", "./data/assets/"))

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
        raise PromotionError(
            "Unbekannte Kennung '%s' (person.system_username)." % kennung)
    return int(row[0])


def _candidates(args) -> Set[int]:
    """Aktuelle Fremdforum-Kandidaten (forensic da, evidence fehlt)."""
    fore, evi, ass = _data_dirs(args)
    report = StorageOverview(
        forensic_dir=fore, evidence_dir=evi, assets_dir=ass).scan()
    return set(report.fremdforum_candidates)


def _print_rows(rows: List[dict]) -> None:
    if not rows:
        print("Keine Eintraege.")
        return
    print("%-10s %-16s %-8s %s" % ("subject_id", "Zustand", "final", "Grund/Herkunft"))
    print("-" * 72)
    for r in rows:
        extra = " / ".join(
            x for x in (r.get("grund") or "", r.get("herkunft") or "") if x)
        print("%-10s %-16s %-8s %s"
              % (r["subject_id"], r["status"],
                 "ja" if r.get("is_final") else "-", extra[:34]))
    print("-" * 72)


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ap = argparse.ArgumentParser(
        prog="promotion_admin",
        description="Fremdforum-Promotion (coordinator.db).",
        epilog=cli_epilog.epilog("promotion_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    ap.add_argument("--db", default=None, help="Pfad zur coordinator.db")
    ap.add_argument("--config", default="./config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("candidates", help="Aktuelle Kandidaten + Zustand")
    sub.add_parser("list", help="Alle erfassten Entscheidungen (Belege)")

    p = sub.add_parser("decide", help="Entscheidung erfassen (auditiert)")
    p.add_argument("--subject-id", type=int, required=True)
    p.add_argument("--status", required=True, choices=list(STORED_STATUSES))
    p.add_argument("--grund", default="")
    p.add_argument("--herkunft", default=None)
    p.add_argument("--force", action="store_true",
                   help="Kandidatenpruefung uebergehen (Nachpflege)")
    p.add_argument("--actor", required=True)

    args = ap.parse_args(argv)

    db = _resolve_db_path(args)
    con = _con(db)
    try:
        if args.cmd == "candidates":
            uids = sorted(_candidates(args))
            rows = PromotionRepo(con).annotate(uids)
            _print_rows(rows)
            print("%d Kandidat(en)." % len(uids))
            return 0

        if args.cmd == "list":
            _print_rows(PromotionRepo(con).list_all())
            return 0

        if args.cmd == "decide":
            actor = _actor_id(con, args.actor)
            allowed = None if args.force else _candidates(args)
            repo = PromotionRepo(con, CoordinatorWriter(con, AuditLog(con)))
            res = repo.record_decision(
                subject_id=args.subject_id, target_status=args.status,
                grund=args.grund, herkunft=args.herkunft,
                actor_id=actor, allowed_uids=allowed)
            print("Kandidat %s: %s -> %s (%s, Beleg #%s)."
                  % (res["subject_id"], res["von"], res["auf"],
                     "angelegt" if res["created"] else "aktualisiert",
                     res["audit_seq"]))
            return 0

        ap.error("Unbekannter Befehl.")
        return 1

    except PromotionError as exc:
        print("FEHLER: %s" % exc, file=sys.stderr)
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())

# =============================================================================
# management/results/catalog_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Den Bewertungs-KATALOG weiterentwickeln — OHNE MIGRATION.
#
#   Das ist der ausdrueckliche Zweck der Architektur (mc 2026-07-12): "Wir
#   stehen noch ganz am Anfang der Ermittlungen und uns fehlt noch die
#   Erfahrung, was sich langfristig als sinnvoll erweist." Ein neues Kriterium
#   oder eine nachgetragene Qualitaetsskala ist hier ein auditierter
#   Schreibvorgang, kein Schema-Eingriff an produktiven Ermittlungsdaten.
#
#   python -m management.results.catalog_admin <befehl> [...]
#     add-scale     --code C --label L [--beschreibung B] --actor KENNUNG
#     add-item      --scale S --code C --label L --ordinal N [--sort N] --actor
#     add-criterion --code C --label L [--quality-scale S] [--sort N] --actor
#     set-quality   --criterion C --scale S --actor KENNUNG
#     deprecate     --was scale|item|criterion --code C [--scale S] --actor
#
# ZWEI WARNUNGEN, DIE DAS WERKZEUG SELBST AUSSPRICHT:
#
#   (1) Jede Katalogaenderung erhoeht die KATALOGVERSION. Bereits erfasste
#       Bewertungen behalten ihren damaligen Zahlenwert (eingefroren in der
#       Bewertungszeile) — sie aendern ihre Bedeutung NICHT rueckwirkend. Genau
#       dafuer wurde die Numerik eingefroren.
#
#   (2) Es wird NICHTS geloescht. 'deprecate' stellt ausser Dienst: der Eintrag
#       verschwindet aus den Auswahllisten, bleibt aber lesbar — bestehende
#       Bewertungen zeigen weiter auf ihn. Ein hartes DELETE wuerde
#       Ermittlungsergebnisse unlesbar machen.
#
# Version: v0.7.387 · Build: 387 · 2026-07-12
# =============================================================================

import argparse
import logging
import sqlite3
import sys
from typing import List, Optional

from management.audit.audit_log import AuditLog
from management.gateway.coordinator_writer import CoordinatorWriter
from management.results.assessment_catalog_repo import (
    AssessmentCatalogRepo,
    CatalogError,
)
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
    '[catalog_admin]'. Die Abbruchmeldung nennt jetzt BEIDE Wege statt nur einen.
    """
    return werkzeug_konfig.db_pfad(
        "catalog_admin", args, arg_attribut="db", arg_name="--db",
        config_schluessel="paths.coordinator_db", name="db")


def _con(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    return con


def _actor_id(con: sqlite3.Connection, kennung: str) -> int:
    row = con.execute("SELECT id FROM person WHERE system_username = ?",
                      (kennung,)).fetchone()
    if row is None:
        raise CatalogError("Unbekannte Kennung '%s'." % kennung)
    return int(row[0])


def _hinweis(cat: AssessmentCatalogRepo) -> None:
    print("\n" + "=" * 78)
    print("Katalogversion ist jetzt %d. Bereits erfasste Bewertungen behalten"
          % cat.version())
    print("ihren damaligen Zahlenwert (eingefroren) und aendern ihre Bedeutung")
    print("NICHT rueckwirkend. Auswertungen ueber verschiedene Katalogversionen")
    print("hinweg sind dennoch mit Bedacht zu lesen.")
    print("=" * 78)


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ap = argparse.ArgumentParser(
        prog="catalog_admin",
        description="Bewertungs-Katalog pflegen (auditiert, append-only, "
                    "OHNE Migration).",
        epilog=cli_epilog.epilog("catalog_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    ap.add_argument("--db", default=None)
    ap.add_argument("--config", default="./config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add-scale")
    p.add_argument("--code", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--beschreibung", default="",
                   help="WAS misst das ordinal? (Praezision? Schwere?)")
    p.add_argument("--actor", required=True)

    p = sub.add_parser("add-item")
    p.add_argument("--scale", required=True)
    p.add_argument("--code", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--ordinal", type=int, required=True)
    p.add_argument("--sort", type=int, default=0)
    p.add_argument("--actor", required=True)

    p = sub.add_parser("add-criterion")
    p.add_argument("--code", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--quality-scale", default=None)
    p.add_argument("--sort", type=int, default=0)
    p.add_argument("--actor", required=True)

    p = sub.add_parser("set-quality",
                       help="einem Kriterium NACHTRAEGLICH eine Skala geben")
    p.add_argument("--criterion", required=True)
    p.add_argument("--scale", required=True)
    p.add_argument("--actor", required=True)

    p = sub.add_parser("deprecate", help="ausser Dienst stellen (kein DELETE)")
    p.add_argument("--was", required=True,
                   choices=["scale", "item", "criterion"])
    p.add_argument("--code", required=True)
    p.add_argument("--scale", default=None, help="nur bei --was item")
    p.add_argument("--actor", required=True)

    args = ap.parse_args(argv)
    con = _con(_resolve_db_path(args))
    try:
        actor = _actor_id(con, args.actor)
        cat = AssessmentCatalogRepo(con, CoordinatorWriter(con, AuditLog(con)))

        if args.cmd == "add-scale":
            seq = cat.add_scale(args.code, args.label,
                                beschreibung=args.beschreibung, actor_id=actor)
            print("Skala '%s' angelegt (Beleg #%s)." % (args.code, seq))
        elif args.cmd == "add-item":
            seq = cat.add_item(args.scale, args.code, args.label,
                               ordinal=args.ordinal, sort=args.sort,
                               actor_id=actor)
            print("Skalenpunkt '%s/%s' (ordinal=%d) angelegt (Beleg #%s)."
                  % (args.scale, args.code, args.ordinal, seq))
        elif args.cmd == "add-criterion":
            seq = cat.add_criterion(args.code, args.label,
                                    quality_scale=args.quality_scale,
                                    sort=args.sort, actor_id=actor)
            print("Kriterium '%s' angelegt (Beleg #%s)." % (args.code, seq))
        elif args.cmd == "set-quality":
            seq = cat.set_quality_scale(args.criterion, args.scale,
                                        actor_id=actor)
            print("Kriterium '%s' erhaelt die Qualitaetsskala '%s' (Beleg #%s)."
                  % (args.criterion, args.scale, seq))
        else:
            seq = cat.deprecate(args.was, args.code, scale_code=args.scale,
                                actor_id=actor)
            print("'%s' ausser Dienst gestellt (Beleg #%s). NICHT geloescht — "
                  "bestehende Bewertungen bleiben lesbar." % (args.code, seq))

        _hinweis(cat)
        return 0

    except CatalogError as exc:
        print("FEHLER: %s" % exc, file=sys.stderr)
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())

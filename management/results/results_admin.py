# =============================================================================
# management/results/results_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   CLI fuer die ERGEBNISBEWERTUNG. Betriebsweg (Skripte, Nachpflege); der
#   Normalfall wird die Erfassungsmaske im Nutzerinfo-Tab (Build 389) und die
#   Auswertung im Cockpit (Build 388).
#
#   python -m management.results.results_admin <befehl> [...]
#     catalog                      Katalog anzeigen (Kriterien + Skalen)
#     assess   --user-id N --criterion C --extrem schwerste|beste
#              --confidence CODE [--quality CODE] [--note T] --actor KENNUNG
#     current  --user-id N         aktueller Stand
#     history  --user-id N [--criterion C]   VOLLE Historie (append-only!)
#     score    --user-id N         provisorische Kennzahl (mit Vermerk!)
#     stats                        Auswertung ueber alle Faelle
#
#   --actor ist beim Schreiben Pflicht: ein Beleg ohne Handelnden ist kein Beleg.
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
from management.results.coverage_repo import CoverageRepo
from management.results.priority_scorer import PriorityScorer
from management.results.results_repo import ResultsError, ResultsRepo

logger = logging.getLogger(__name__)


def _resolve_db_path(args) -> str:
    if args.db:
        return args.db
    try:
        from core.config_loader import ConfigLoader
        cfg = ConfigLoader(config_path=args.config)
        path = cfg.get("paths.coordinator_db")
        if path:
            return str(path)
    except Exception as exc:  # pragma: no cover
        print("[results_admin] config.yaml nicht lesbar: %s" % exc,
              file=sys.stderr)
    raise SystemExit(
        "[results_admin] Kein coordinator.db-Pfad: --db oder "
        "paths.coordinator_db in config.yaml.")


def _con(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    return con


def _actor_id(con: sqlite3.Connection, kennung: str) -> int:
    row = con.execute("SELECT id FROM person WHERE system_username = ?",
                      (kennung,)).fetchone()
    if row is None:
        raise ResultsError("Unbekannte Kennung '%s'." % kennung)
    return int(row[0])


def _print_catalog(cat) -> None:
    full = cat.full()
    print("Katalogversion: %d" % full["catalog_version"])
    print("\nKONFIDENZ (fuer ALLE Kriterien):")
    for i in full["confidence_items"]:
        print("  %-16s %-20s ordinal=%d" % (i["code"], i["label"], i["ordinal"]))
    print("\nKRITERIEN (je Fall x 2 Extreme: schwerste | beste):")
    for c in full["criteria"]:
        q = c["quality_scale"] or "-- (nur Konfidenz)"
        print("\n  %-26s %s" % (c["code"], c["label"]))
        print("    Qualitaetsskala: %s" % q)
        if c["quality_beschreibung"]:
            print("    %s" % c["quality_beschreibung"])
        for i in c["quality_items"]:
            print("      %-16s %-20s ordinal=%d"
                  % (i["code"], i["label"], i["ordinal"]))


def _print_rows(rows: List[dict], titel: str) -> None:
    print(titel)
    if not rows:
        print("  (keine Bewertung)")
        return
    print("  %-5s %-26s %-10s %-16s %-3s %-16s %-3s %-4s"
          % ("ID", "Kriterium", "Extrem", "Konfidenz", "#", "Qualitaet", "#",
             "Kat."))
    print("  " + "-" * 100)
    for r in rows:
        print("  %-5s %-26s %-10s %-16s %-3s %-16s %-3s %-4s"
              % (r["id"], r["criterion_code"], r["extrem"],
                 r["confidence_code"], r["confidence_ordinal"],
                 r["quality_code"] or "-", 
                 "-" if r["quality_ordinal"] is None else r["quality_ordinal"],
                 r["catalog_version"]))
        if r.get("note"):
            print("        Vermerk: %s" % r["note"])


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ap = argparse.ArgumentParser(
        prog="results_admin",
        description="Bewertung des Ermittlungsergebnisses (append-only).")
    ap.add_argument("--db", default=None)
    ap.add_argument("--config", default="./config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("catalog", help="Katalog anzeigen")

    p = sub.add_parser("assess", help="Bewertung erfassen (NEUE Zeile)")
    p.add_argument("--user-id", type=int, required=True)
    p.add_argument("--criterion", required=True)
    p.add_argument("--extrem", required=True, choices=["schwerste", "beste"])
    p.add_argument("--confidence", required=True)
    p.add_argument("--quality", default=None)
    p.add_argument("--note", default="")
    p.add_argument("--actor", required=True)

    p = sub.add_parser("current", help="aktueller Stand")
    p.add_argument("--user-id", type=int, required=True)

    p = sub.add_parser("history", help="VOLLE Historie (append-only)")
    p.add_argument("--user-id", type=int, required=True)
    p.add_argument("--criterion", default=None)

    p = sub.add_parser("score", help="provisorische Kennzahl")
    p.add_argument("--user-id", type=int, required=True)

    sub.add_parser("stats", help="Auswertung ueber alle Faelle")
    p = sub.add_parser(
        "coverage",
        help="ABDECKUNG je Fall — inkl. der NIE bewerteten (blinde Flecken)")
    p.add_argument("--nur-luecken", action="store_true",
                   help="nur Faelle mit unvollstaendiger Bewertung")

    args = ap.parse_args(argv)
    con = _con(_resolve_db_path(args))
    try:
        cat = AssessmentCatalogRepo(con)

        if args.cmd == "catalog":
            _print_catalog(cat)
            return 0

        if args.cmd == "current":
            _print_rows(ResultsRepo(con).current(args.user_id),
                        "Aktueller Stand — Fall %s:" % args.user_id)
            return 0

        if args.cmd == "history":
            rows = ResultsRepo(con).history(args.user_id,
                                            criterion_code=args.criterion)
            _print_rows(rows, "Historie (append-only) — Fall %s, %d Eintraege:"
                        % (args.user_id, len(rows)))
            return 0

        if args.cmd == "score":
            repo = ResultsRepo(con)
            alle = [c["code"] for c in cat.criteria()]
            res = PriorityScorer().score_with_gaps(
                repo.current(args.user_id), alle)
            print("Fall %s — provisorische Kennzahl: %s"
                  % (args.user_id, res["score"]))
            print("Basis: %d von %d Kriterien bewertet (Abdeckung %s)"
                  % (res["basis"], len(alle), res["abdeckung"]))
            for b in res["beitraege"]:
                print("  %-26s %-16s (%d) x %.1f = %s"
                      % (b["criterion"], b["confidence"],
                         b["confidence_ordinal"], b["gewicht"], b["beitrag"]))
            if res["unbewertet"]:
                print("\n  NOCH NICHT BEWERTET (hier ist zu ermitteln):")
                for c in res["unbewertet"]:
                    print("    - %s" % c)
            # Der Vermerk steht IMMER dabei — umrahmt, damit ihn niemand
            # ueberliest und die Zahl fuer bare Muenze nimmt.
            print("\n" + "=" * 78)
            print(res["vermerk"])
            print("=" * 78)
            return 0

        if args.cmd == "coverage":
            repo = CoverageRepo(con)
            cov = repo.coverage()
            summ = repo.summary(cov)
            rows = cov["faelle"]
            if args.nur_luecken:
                rows = [r for r in rows
                        if r["n_bewertet"] < r["n_kriterien"]]

            print("%-7s %-16s %-12s %-9s %-6s %-7s %s"
                  % ("Fall", "Benutzername", "Zustand", "Abdeckung", "Score",
                     "beste", "fehlende Kriterien"))
            print("-" * 110)
            for r in rows:
                fehlt = ("ALLE (nie bewertet)" if r["nie_bewertet"]
                         else (", ".join(r["unbewertet"][:3])
                               + (" ..." if len(r["unbewertet"]) > 3 else "")
                               if r["unbewertet"] else "-"))
                print("%-7s %-16s %-12s %-9s %-6s %-7s %s"
                      % (r["user_id"], (r["username"] or "")[:16],
                         r["status"], "%d/%d" % (r["n_bewertet"],
                                                 r["n_kriterien"]),
                         r["score"], r["n_beste"], fehlt))
            print("-" * 110)
            # DIE EIGENTLICHE AUSSAGE steht am Ende und ist umrahmt: eine
            # Statistik ueber nur die bewerteten Faelle beantwortet die
            # falsche Frage.
            print("Faelle gesamt: %d | vollstaendig bewertet: %d | "
                  "mittlere Abdeckung: %s"
                  % (summ["faelle_gesamt"], summ["voll_bewertet"],
                     summ["abdeckung_mittel"]))
            if summ["nie_bewertet"]:
                line = "=" * 78
                print(line, file=sys.stderr)
                print("BLINDE FLECKEN: %d von %d Faellen sind NOCH GAR NICHT "
                      "bewertet." % (summ["nie_bewertet"],
                                     summ["faelle_gesamt"]), file=sys.stderr)
                print("Sie erscheinen in 'stats' UEBERHAUPT NICHT — dort "
                      "zaehlen nur bewertete Faelle.", file=sys.stderr)
                print(line, file=sys.stderr)
                return 2      # Handlungsbedarf, damit ein Skript es sieht
            return 0

        if args.cmd == "stats":
            st = ResultsRepo(con).stats()
            gesamt = con.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
            # Ohne die Gesamtzahl daneben liest sich 'Bewertete Faelle: 19'
            # wie eine Vollerhebung. Die DIFFERENZ ist der Befund.
            print("Bewertete Faelle: %d von %d (%d noch gar nicht bewertet — "
                  "siehe 'coverage')\n"
                  % (st["faelle"], gesamt, max(0, gesamt - st["faelle"])))
            for code in sorted(st["criteria"]):
                c = st["criteria"][code]
                print("%s" % code)
                for e in ("schwerste", "beste"):
                    v = c[e]
                    if not v["n"]:
                        continue
                    print("  %-10s n=%-3d Konfidenz-Mittel=%-5s %s"
                          % (e, v["n"], v["conf_mittel"], v["conf_hist"]))
                    if v["qual_n"]:
                        print("             Qualitaet-Mittel=%-5s %s"
                              % (v["qual_mittel"], v["qual_hist"]))
            return 0

        # --- Schreiben ---
        actor = _actor_id(con, args.actor)
        repo = ResultsRepo(con, CoordinatorWriter(con, AuditLog(con)))
        res = repo.assess(
            user_id=args.user_id, criterion_code=args.criterion,
            extrem=args.extrem, confidence_code=args.confidence,
            quality_code=args.quality, note=args.note, actor_id=actor)
        print("Bewertung %s erfasst (Beleg #%s, Katalogversion %s)."
              % (res["result_id"], res["audit_seq"], res["catalog_version"]))
        return 0

    except (ResultsError, CatalogError) as exc:
        print("FEHLER: %s" % exc, file=sys.stderr)
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())

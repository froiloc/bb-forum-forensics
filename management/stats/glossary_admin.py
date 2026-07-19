# =============================================================================
# management/stats/glossary_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-2C)
# =============================================================================
# Zweck:
#   CLI zum Kennzahlen-Glossar (management.stats.glossary). Drei Aktionen:
#
#     list   — Definitionen in der Konsole ausgeben.
#     check  — Vollstaendigkeit gegen die real erzeugten Kennzahlen pruefen
#              (verify_covers_stats); Exit != 0 bei Luecke (GR1).
#     export-html — self-contained Glossar-HTML mit einheitlichem Rahmen
#              erzeugen. Optional --coordinator-db (NUR LESEND) fuer die
#              Ketten-Spitze im Erzeugungsvermerk (context_builder).
#
#   python -m management.stats.glossary_admin list
#   python -m management.stats.glossary_admin check
#   python -m management.stats.glossary_admin export-html --out glossar.html \
#          [--coordinator-db PATH] [--behoerde ..] [--aktenzeichen ..] [--actor ..]
#
# Version: v0.7.444 · Build: 444 · 2026-07-19
# =============================================================================

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from management.stats.glossary import KpiGlossary, GlossaryIncompleteError
from management.export.export_envelope import ExportContext, DEFAULT_KLASSIFIKATION


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _do_list(args) -> int:
    g = KpiGlossary()
    for e in g.all():
        print("%-22s %s" % (e.key, e.label))
        print("    %s" % e.definition)
        print("    Einheit: %s | Beleg: %s" % (e.einheit, e.quelle))
        if e.hinweis:
            print("    Hinweis: %s" % e.hinweis)
    return 0


def _do_check(args) -> int:
    g = KpiGlossary()
    try:
        g.verify_covers_stats()
    except GlossaryIncompleteError as exc:
        print("[glossary] UNVOLLSTAENDIG: %s" % exc, file=sys.stderr)
        return 1
    print("[glossary] OK — jede erzeugte Kennzahl ist definiert (%d Eintraege)."
          % len(g.all()))
    return 0


def _do_export_html(args) -> int:
    g = KpiGlossary()
    generated = _now_utc()
    context = None
    if args.coordinator_db:
        try:
            con = sqlite3.connect(
                "file:%s?mode=ro" % args.coordinator_db, uri=True)
            con.row_factory = sqlite3.Row
            try:
                from management.export.context_builder import build_export_context
                context = build_export_context(
                    con=con, db_path=args.coordinator_db,
                    behoerde=args.behoerde, aktenzeichen=args.aktenzeichen,
                    actor=args.actor, now_utc=generated)
            finally:
                con.close()
        except Exception as exc:  # pragma: no cover - Randfall
            print("[glossary] coordinator.db nicht lesbar (%s) — Rahmen ohne "
                  "Ketten-Spitze." % exc, file=sys.stderr)
    if context is None:
        context = ExportContext(
            behoerde=args.behoerde or "Polizei NRW",
            aktenzeichen=args.aktenzeichen or "Kennzahlen-Glossar",
            ersteller=args.actor or "unbekannt",
            build_number=0, generated_at=generated,
            klassifikation=DEFAULT_KLASSIFIKATION)
    Path(args.out).write_text(g.to_html(context), encoding="utf-8")
    print("[glossary] %d Definition(en) -> %s (self-contained)"
          % (len(g.all()), args.out))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="glossary_admin",
        description="Kennzahlen-Glossar (list/check/export-html).")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="Definitionen ausgeben").set_defaults(func=_do_list)
    sub.add_parser("check", help="Vollstaendigkeit pruefen").set_defaults(func=_do_check)
    x = sub.add_parser("export-html", help="Self-contained Glossar-HTML erzeugen")
    x.add_argument("--out", required=True)
    x.add_argument("--coordinator-db", default=None)
    x.add_argument("--behoerde", default=None)
    x.add_argument("--aktenzeichen", default=None)
    x.add_argument("--actor", default=None)
    x.set_defaults(func=_do_export_html)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

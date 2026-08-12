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
# BUILD 706 (Vorgang 70641ff9): 'export-html' OHNE --coordinator-db erzeugte
#   ein Dokument mit Buildnummer 0 und Ersteller 'unbekannt', ohne Meldung -
#   und zwar auf dem Regelweg, nicht im Fehlerfall. Die Buildnummer wird jetzt
#   auch ohne Datenbank richtig gefuellt; was ohne sie nicht zu ermitteln ist
#   (Identitaet, Belegkette), steht als Befund im Vermerk und auf der
#   Fehlerausgabe. Naeheres bei _do_export_html().
#
# Version: v0.8.706 · Build: 706 · 2026-08-12
# =============================================================================

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from management.stats.glossary import KpiGlossary, GlossaryIncompleteError
from management.export.export_envelope import DEFAULT_KLASSIFIKATION
# Build 706 (Vorgang 70641ff9): der DB-lose Rahmen und seine Meldung.
from management.export.context_builder import build_export_context_ohne_db
from management.export.rahmen_meldung import melde_rahmen_befunde
from management.help import cli_epilog  # noqa: E402


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
    """
    BUILD 706 (Vorgang 70641ff9) — DER ERSATZRAHMEN STAND HIER AM REGELWEG.

    '--coordinator-db' ist bei diesem Befehl OPTIONAL. Ohne die Angabe wurde
    bis Build 702 ein von Hand gebauter Ersatzkontext benutzt: Buildnummer 0,
    Ersteller 'unbekannt', kein Wort dazu. Gemessen am 12.08.2026:
    'glossary_admin export-html --out x.html' - der dokumentierte Regelweg,
    Rueckgabewert 0 - erzeugte ein Dokument mit 'Werkzeug-Build: 0'.

    Das ist derselbe Befund wie in Vorgang ff7e80ab, nur schwerer: dort lag er
    am Fehlerweg, hier am gewoehnlichen. Und die Buildnummer war die ganze
    Zeit da - sie steht in build.json und braucht keine Datenbank.

    DREI LAGEN, EIN WEG: Datenbank angegeben und lesbar -> voller Rahmen;
    angegeben und nicht lesbar -> DB-loser Rahmen MIT dem Fehlertext als
    Grund; nicht angegeben -> DB-loser Rahmen mit eben diesem Grund. In allen
    dreien meldet melde_rahmen_befunde, was fehlt. Die frueheren
    Einzelmeldungen dieses Werkzeugs entfallen dafuer: derselbe Sachverhalt
    soll nicht an zwei Stellen verschieden klingen (Kopf von
    rahmen_meldung.py).
    """
    g = KpiGlossary()
    generated = _now_utc()
    context = None
    grund = "keine coordinator.db angegeben (--coordinator-db)"
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
        except Exception as exc:  # Randfall: Pfad falsch, Datei kaputt
            grund = "coordinator.db nicht lesbar: %s" % exc
    if context is None:
        context = build_export_context_ohne_db(
            grund=grund,
            behoerde=args.behoerde,
            aktenzeichen=args.aktenzeichen or "Kennzahlen-Glossar",
            actor=args.actor, now_utc=generated,
            klassifikation=DEFAULT_KLASSIFIKATION)

    # Vor dem Schreiben der Datei — faellt das Schreiben aus, ist die Auskunft
    # ueber den Rahmen bereits heraus.
    melde_rahmen_befunde("[glossary]", context)

    Path(args.out).write_text(g.to_html(context), encoding="utf-8")
    print("[glossary] %d Definition(en) -> %s (self-contained)"
          % (len(g.all()), args.out))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="glossary_admin",
        description="Kennzahlen-Glossar (list/check/export-html).",
        epilog=cli_epilog.epilog("glossary_admin"),
        formatter_class=cli_epilog.HilfeFormat)
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

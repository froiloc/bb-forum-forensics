# =============================================================================
# management/stats/status_report_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-2C)
# =============================================================================
# Zweck:
#   NUR-LESENDE CLI: erzeugt den StA-Statusbericht (HTML oder PDF) aus den
#   Kennzahlen von StatsRepo. coordinator.db wird read-only geoeffnet; der
#   einheitliche Rahmen (Aktenkopf/Erzeugungsvermerk/Pruefsumme + Ketten-Spitze)
#   kommt aus context_builder.
#
#   python -m management.stats.status_report_admin --out bericht.pdf \
#          --format pdf [--coordinator-db PATH] [--config ./config.yaml]
#          [--person-id N] [--period "KW 29/2026"]
#          [--behoerde ..] [--aktenzeichen ..] [--actor ..]
#
# BUILD 702 (Vorgang ff7e80ab): Faellt der Erzeugungsrahmen ganz oder in
#   Teilen aus, wird das auf der Fehlerausgabe benannt und im Bericht
#   gekennzeichnet. Der Rueckgabewert bleibt 0 und der Bericht wird
#   geschrieben (Entscheidung Alex, 12.08.2026) — die Begruendung steht im
#   Kopf von management/export/rahmen_meldung.py. Die ausfuehrliche
#   Herleitung steht im Kopf von forecast_report_admin.py; beide Werkzeuge
#   trugen denselben Fehler und sind deshalb gleich behandelt.
#
# Version: v0.8.724 · Build: 724 · 2026-08-14
# =============================================================================

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from management.stats.stats_repo import StatsRepo
from management.stats.status_report import (
    build_status_report_html, build_status_report_pdf, StatusReportUnavailable,
)
from management.export.export_envelope import ExportContext, DEFAULT_KLASSIFIKATION
# Build 702 (Vorgang ff7e80ab): ein ausgefallener Erzeugungsrahmen wird
# benannt, statt still durch Ersatzwerte ersetzt zu werden.
from management.export.rahmen_befund import FELD_RAHMEN, RahmenBefund
from management.export.rahmen_meldung import melde_rahmen_befunde
from management.help import cli_epilog  # noqa: E402
# Build 644: die Vorrangregel Argument > config.yaml > Vorgabewert
# steht seit Build 643 an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _load_config(args):
    """
    Laedt die config.yaml und MELDET ihren Ausfall auf stderr.

    TICKET 6c64daf4 (Build 724): Bis hierher stand hier eine Abschrift
    der immer gleichen sechs Zeilen. Sie MELDETE zwar - dieses Werkzeug
    gehoerte nicht zu den acht stummen aus cf791ef0 -, aber jede Abschrift
    fuehrte ihren eigenen Wortlaut. Hier fehlte er ganz: Die Meldung nannte
    den Ausfall, aber nicht seine FOLGE - und das ist die Frage, die der
    Empfaenger als naechstes hat. Dieses Werkzeug holt aus der
    Konfiguration NUR den Datenbankpfad, fuer den es bewusst keinen
    Vorgabewert gibt; ohne '--coordinator-db' folgt gleich danach der
    Abbruch.

    Die Meldung steht jetzt in core/werkzeug_konfig.konfig_laden(); die
    ausfuehrliche Begruendung fuer die Zusammenfuehrung steht dort. Der
    Rueckgabewert ist unveraendert: der ConfigLoader oder None.
    """
    return werkzeug_konfig.konfig_laden(
        "status_report", args,
        folge="es gelten nur die Angaben von der Befehlszeile")


def _resolve_db_path(args, cfg) -> str:
    """
    coordinator.db-Pfad: Argument --coordinator-db > paths.coordinator_db
    > Abbruch.

    BUILD 644 - DIE AUFLOESUNG IST UMGEZOGEN, das Verhalten NICHT.
    Sie steht jetzt in core/werkzeug_konfig.py; die Begruendung fuer den
    Umzug steht im Kopf jener Datei.

    'cfg' BLEIBT PARAMETER, und das ist der Kern dieser Umstellung: Dieses
    Werkzeug laedt die config.yaml EINMAL (_load_config) und reicht sie
    weiter - fuer den Pfad UND fuer seine uebrigen Werte. Wuerde die
    Aufloesung sich hier ihre eigene Kopie holen, koennten beide im
    Grenzfall aus VERSCHIEDENEN Staenden derselben Datei stammen. Der
    Aufloeser wird deshalb UM den vorhandenen Loader gebaut, nicht neben ihn.

    UNVERAENDERT bleiben: die Reihenfolge, das Fehlen eines Vorgabewerts,
    der Abbruch mit dem Praefix '[status_report_admin]' - nur nennt die Meldung jetzt
    BEIDE Wege statt nur einen. Die Meldung ueber eine unlesbare config.yaml
    gibt weiterhin _load_config aus; cfg ist dann None.
    """
    return werkzeug_konfig.db_pfad(
        "status_report_admin", args, arg_attribut="coordinator_db",
        arg_name="--coordinator-db", config_schluessel="paths.coordinator_db",
        name="coordinator_db", r=werkzeug_konfig.resolver_aus_loader(cfg))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="status_report_admin",
        description="StA-Statusbericht (HTML/PDF) aus den Kennzahlen.",
        epilog=cli_epilog.epilog("status_report_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--out", required=True)
    p.add_argument("--format", choices=["html", "pdf"], default="pdf")
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--person-id", type=int, default=None,
                   help="Umfang 'eigene' fuer eine person_id; sonst 'alle'.")
    p.add_argument("--period", default=None, help="Zeitraum-Label (Anzeige).")
    p.add_argument("--behoerde", default=None)
    p.add_argument("--aktenzeichen", default=None)
    p.add_argument("--actor", default=None)
    args = p.parse_args(argv)

    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)
    generated = _now_utc()

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        stats = StatsRepo(con).compute(person_id=args.person_id)
        # BUILD 702 (Vorgang ff7e80ab) — DER ERSATZRAHMEN IST NICHT MEHR STUMM.
        # Wortgleich zu forecast_report_admin.py, weil beide Werkzeuge
        # denselben Fehler trugen; die ausfuehrliche Begruendung steht dort.
        # Kurz: dieser Zweig fasst praktisch nur einen Fehlschlag des import
        # darunter — build_export_context wirft nie (RF06). Die haeufigen
        # Ausfaelle treten INNERHALB des Builders auf und kommen als
        # rahmen_befunde zurueck; die Meldung unten deckt beide Wege ab.
        try:
            from management.export.context_builder import build_export_context
            context = build_export_context(
                con=con, db_path=db_path, behoerde=args.behoerde,
                aktenzeichen=args.aktenzeichen or "StA-Statusbericht",
                actor=args.actor, now_utc=generated)
        except Exception as exc:  # Rahmen-Fallback
            context = ExportContext(
                behoerde=args.behoerde or "Polizei NRW",
                aktenzeichen=args.aktenzeichen or "StA-Statusbericht",
                ersteller=args.actor or "unbekannt", build_number=0,
                generated_at=generated, klassifikation=DEFAULT_KLASSIFIKATION,
                rahmen_befunde=(RahmenBefund(
                    FELD_RAHMEN,
                    "Erzeugungsrahmen nicht bildbar: %s" % exc),))
    finally:
        con.close()

    # Vor dem Schreiben der Datei — faellt das Schreiben aus, ist die Auskunft
    # ueber den Rahmen bereits heraus.
    melde_rahmen_befunde("[status_report]", context)

    if args.format == "html":
        Path(args.out).write_text(
            build_status_report_html(stats, context, period_label=args.period),
            encoding="utf-8")
    else:
        try:
            data = build_status_report_pdf(stats, context, period_label=args.period)
        except StatusReportUnavailable as exc:
            raise SystemExit("[status_report] PDF nicht moeglich: %s" % exc)
        Path(args.out).write_bytes(data)

    print("[status_report] %s-Bericht -> %s (%d Faelle)"
          % (args.format.upper(), args.out, stats.get("totals", {}).get("cases", 0)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

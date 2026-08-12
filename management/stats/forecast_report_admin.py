# =============================================================================
# management/stats/forecast_report_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-3F)
# =============================================================================
# Zweck (Idee 40, Build 522):
#   NUR-LESENDE CLI: erzeugt den Prognosebericht (HTML oder PDF) aus der
#   Backlog-Abbau-Prognose (Forecaster, Build 446). coordinator.db wird
#   read-only geoeffnet; der einheitliche Rahmen (Aktenkopf, Erzeugungsvermerk,
#   Pruefsumme, Integritaets-Kettenspitze) kommt aus context_builder
#   (Build 442).
#
#   python -m management.stats.forecast_report_admin --out prognose.pdf \
#          --format pdf [--coordinator-db PATH] [--config ./config.yaml]
#          [--lookback-days 30] [--period "KW 30/2026"]
#          [--behoerde ..] [--aktenzeichen ..] [--actor ..]
#
# WARUM ES DIE CLI NEBEN DEM ENDPUNKT GIBT (Muster status_report_admin.py):
#   Der Endpunkt braucht eine angemeldete Person mit dem Recht
#   'stats.export_sta'. Die CLI laeuft im Betrieb (Wartungsfenster,
#   Stapelbetrieb, Sammelabgabe an die StA) ohne Browsersitzung. Beide Wege
#   speisen sich aus DENSELBEN reinen Funktionen — sie koennen nicht
#   auseinanderlaufen.
#
# SCHREIBT NICHT in die Datenbank (kein CoordinatorWriter, keine Migration).
#   Der Migrationsvorbehalt ab 01.07.2026 ist nicht beruehrt.
#
# BUILD 702 (Vorgang ff7e80ab): Faellt der Erzeugungsrahmen ganz oder in
#   Teilen aus, wird das auf der Fehlerausgabe benannt und im Bericht
#   gekennzeichnet. Der Rueckgabewert bleibt 0 und der Bericht wird
#   geschrieben (Entscheidung Alex, 12.08.2026) — die Begruendung steht im
#   Kopf von management/export/rahmen_meldung.py.
#
# Version: v0.8.702 · Build: 702 · 2026-08-12
# =============================================================================

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from management.export.export_envelope import ExportContext, DEFAULT_KLASSIFIKATION
# Build 702 (Vorgang ff7e80ab): ein ausgefallener Erzeugungsrahmen wird
# benannt, statt still durch Ersatzwerte ersetzt zu werden.
from management.export.rahmen_befund import FELD_RAHMEN, RahmenBefund
from management.export.rahmen_meldung import melde_rahmen_befunde
from management.stats.forecast import Forecaster, forecast_to_dict
from management.stats.forecast_report import (
    ForecastReportUnavailable,
    build_forecast_report_html,
    build_forecast_report_pdf,
)
from management.help import cli_epilog  # noqa: E402
# Build 644: die Vorrangregel Argument > config.yaml > Vorgabewert
# steht seit Build 643 an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _load_config(args):
    try:
        from core.config_loader import ConfigLoader
        return ConfigLoader(config_path=args.config)
    except Exception as exc:  # pragma: no cover - Konfig-Ausfall
        print("[forecast_report] config.yaml nicht lesbar: %s" % exc,
              file=sys.stderr)
        return None


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
    der Abbruch mit dem Praefix '[forecast_report_admin]' - nur nennt die Meldung jetzt
    BEIDE Wege statt nur einen. Die Meldung ueber eine unlesbare config.yaml
    gibt weiterhin _load_config aus; cfg ist dann None.
    """
    return werkzeug_konfig.db_pfad(
        "forecast_report_admin", args, arg_attribut="coordinator_db",
        arg_name="--coordinator-db", config_schluessel="paths.coordinator_db",
        name="coordinator_db", r=werkzeug_konfig.resolver_aus_loader(cfg))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="forecast_report_admin",
        description="Prognosebericht (3 Szenarien) als HTML/PDF.",
        epilog=cli_epilog.epilog("forecast_report_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--out", required=True)
    p.add_argument("--format", choices=["html", "pdf"], default="pdf")
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--lookback-days", type=int, default=30,
                   help="Rueckblickfenster fuer die beobachtete Rate.")
    p.add_argument("--period", default=None, help="Zeitraum-Label (Anzeige).")
    p.add_argument("--behoerde", default=None)
    p.add_argument("--aktenzeichen", default=None)
    p.add_argument("--actor", default=None)
    args = p.parse_args(argv)

    if args.lookback_days <= 0:
        raise SystemExit("[forecast_report] --lookback-days muss > 0 sein.")

    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)
    generated = _now_utc()
    now_ts = int(datetime.now(timezone.utc).timestamp())

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        result = Forecaster(con).compute(now_ts=now_ts,
                                        lookback_days=args.lookback_days)
        forecast = forecast_to_dict(result)
        # BUILD 702 (Vorgang ff7e80ab) — DER ERSATZRAHMEN IST NICHT MEHR STUMM.
        # Bis Build 698 fing dieser Zweig den Ausfall wortlos ab und setzte
        # Buildnummer 0 / Ersteller 'unbekannt'; der Bericht entstand danach
        # wie jeder andere. Das ist bei einem Abgabedokument der Ausfall genau
        # der Angabe, ueber die sich seine Herkunft belegen laesst.
        #
        # DIESER ZWEIG IST ENGER, ALS ER AUSSIEHT: build_export_context faengt
        # jede eigene Fehlerquelle selbst ab und wirft nie (Kopf jener Datei,
        # RF06). Was hier ankommen kann, ist praktisch nur ein Fehlschlag des
        # import in der Zeile darunter. Die haeufigen Ausfaelle — unlesbare
        # build.json, nicht aufloesbare Identitaet, fehlendes audit_log —
        # treten INNERHALB des Builders auf und kommen seit Build 702 als
        # rahmen_befunde im Kontext zurueck. Deshalb genuegt es nicht, nur
        # diesen Zweig zu bereinigen; die Meldung unten gilt fuer BEIDE Wege.
        try:
            from management.export.context_builder import build_export_context
            context = build_export_context(
                con=con, db_path=db_path, behoerde=args.behoerde,
                aktenzeichen=args.aktenzeichen or "Prognosebericht",
                actor=args.actor, now_utc=generated)
        except Exception as exc:  # Rahmen-Fallback
            context = ExportContext(
                behoerde=args.behoerde or "Polizei NRW",
                aktenzeichen=args.aktenzeichen or "Prognosebericht",
                ersteller=args.actor or "unbekannt", build_number=0,
                generated_at=generated, klassifikation=DEFAULT_KLASSIFIKATION,
                # FELD_RAHMEN statt drei Einzelbefunde: hier ist nicht EINE
                # Angabe ausgefallen, sondern der Rahmen als Ganzes. Keiner
                # der Ersatzwerte ist belastbar, auch nicht der plausibel
                # aussehende --actor.
                rahmen_befunde=(RahmenBefund(
                    FELD_RAHMEN,
                    "Erzeugungsrahmen nicht bildbar: %s" % exc),))
    finally:
        con.close()

    # Die Meldung steht VOR dem Schreiben der Datei und nicht danach: faellt
    # das Schreiben aus (Pfad, Platte, fehlendes reportlab), ist die Auskunft
    # ueber den Rahmen bereits heraus. Umgekehrt waere sie mit verloren.
    melde_rahmen_befunde("[forecast_report]", context)

    if args.format == "html":
        Path(args.out).write_text(
            build_forecast_report_html(forecast, context,
                                       period_label=args.period),
            encoding="utf-8")
    else:
        try:
            data = build_forecast_report_pdf(forecast, context,
                                             period_label=args.period)
        except ForecastReportUnavailable as exc:
            raise SystemExit("[forecast_report] PDF nicht moeglich: %s" % exc)
        Path(args.out).write_bytes(data)

    # Die Meldung nennt die Datenlage MIT: ein erzeugter Bericht ohne belastbare
    # Prognose darf im Protokoll nicht wie ein erfolgreicher Zeitplan aussehen.
    lage = ("belastbar" if forecast.get("data_sufficient") is True
            else "KEINE belastbare Prognose (keine Abschluesse im Fenster)")
    print("[forecast_report] %s-Bericht -> %s (Backlog %s, %s)"
          % (args.format.upper(), args.out, forecast.get("backlog"), lage))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

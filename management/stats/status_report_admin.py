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
# Version: v0.7.445 · Build: 445 · 2026-07-19
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
from management.help import cli_epilog  # noqa: E402


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _load_config(args):
    try:
        from core.config_loader import ConfigLoader
        return ConfigLoader(config_path=args.config)
    except Exception as exc:  # pragma: no cover
        print("[status_report] config.yaml nicht lesbar: %s" % exc, file=sys.stderr)
        return None


def _resolve_db_path(args, cfg) -> str:
    if args.coordinator_db:
        return args.coordinator_db
    if cfg is not None:
        try:
            p = cfg.get("paths", {}).get("coordinator_db")
            if p:
                return str(p)
        except Exception:  # pragma: no cover
            pass
    raise SystemExit("[status_report] Kein coordinator.db-Pfad (--coordinator-db "
                     "oder paths.coordinator_db in config.yaml).")


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
        try:
            from management.export.context_builder import build_export_context
            context = build_export_context(
                con=con, db_path=db_path, behoerde=args.behoerde,
                aktenzeichen=args.aktenzeichen or "StA-Statusbericht",
                actor=args.actor, now_utc=generated)
        except Exception:  # pragma: no cover - Rahmen-Fallback
            context = ExportContext(
                behoerde=args.behoerde or "Polizei NRW",
                aktenzeichen=args.aktenzeichen or "StA-Statusbericht",
                ersteller=args.actor or "unbekannt", build_number=0,
                generated_at=generated, klassifikation=DEFAULT_KLASSIFIKATION)
    finally:
        con.close()

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

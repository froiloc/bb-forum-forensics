# =============================================================================
# management/stats/forecast_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-2C)
# =============================================================================
# Zweck:
#   NUR-LESENDE CLI fuer die Backlog-Abbau-Prognose (management.stats.forecast).
#   Gibt die drei Szenarien samt OFFENGELEGTER Annahmen aus (Konsole oder JSON).
#   Die Sicht/PDF-Ausgabe folgt in spaeteren AP-2C-Builds.
#
#   python -m management.stats.forecast_admin [--coordinator-db PATH]
#          [--config ./config.yaml] [--lookback-days 30] [--json]
#          [--no-capacity]
#
# Version: v0.7.446 · Build: 446 · 2026-07-19
# =============================================================================

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

from management.stats.forecast import Forecaster, forecast_to_dict
from management.help import cli_epilog  # noqa: E402


def _load_config(args):
    try:
        from core.config_loader import ConfigLoader
        return ConfigLoader(config_path=args.config)
    except Exception:  # pragma: no cover
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
    raise SystemExit("[forecast] Kein coordinator.db-Pfad (--coordinator-db "
                     "oder paths.coordinator_db in config.yaml).")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="forecast_admin",
        description="Backlog-Abbau-Prognose (3 Szenarien, transparent).",
        epilog=cli_epilog.epilog("forecast_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--lookback-days", type=int, default=30)
    p.add_argument("--no-capacity", action="store_true",
                   help="Kapazitaets-Kontext nicht ermitteln.")
    p.add_argument("--json", action="store_true", help="Als JSON ausgeben.")
    args = p.parse_args(argv)

    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)
    now_ts = int(time.time())

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        result = Forecaster(con).compute(
            now_ts=now_ts, lookback_days=args.lookback_days,
            include_capacity=not args.no_capacity)
    finally:
        con.close()

    if args.json:
        print(json.dumps(forecast_to_dict(result), ensure_ascii=False, indent=2))
        return 0

    print("Backlog-Abbau-Prognose (Stand %s)" % result.now_day)
    print("  Backlog: %d offene Faelle | beobachtete Rate: %.4f Faelle/Tag "
          "(%d Abschluesse / %d Tage)"
          % (result.backlog, result.observed_rate_per_day,
             result.completions_observed, result.lookback_days))
    if not result.data_sufficient:
        print("  ! Keine beobachteten Abschluesse — keine belastbare Prognose.")
    print("  Szenarien:")
    for s in result.scenarios:
        dtc = "%d Tage" % s.days_to_clear if s.days_to_clear is not None else "unbestimmt"
        fin = s.finish_day or "-"
        print("    %-14s x%.2f  %.4f/Tag  Restdauer %s  Fertig %s"
              % (s.name, s.factor, s.rate_per_day, dtc, fin))
    print("  Annahmen:")
    for a in result.assumptions:
        print("    - %s" % a)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

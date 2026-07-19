# =============================================================================
# management/workload/overload_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Lastverteilung (AP-2F)
# =============================================================================
# Zweck:
#   NUR-LESENDE CLI fuer die aktive Ueberlastwarnung (management.workload.
#   overload). Gibt je Ermittler die Warnstufe (ok/warn/overload) samt
#   Ausloeser aus und meldet den systemischen Rueckstau-Alarm.
#
#   python -m management.workload.overload_admin
#          [--coordinator-db PATH] [--config ./config.yaml] [--json]
#
# Version: v0.7.451 · Build: 451 · 2026-07-19
# =============================================================================

import argparse
import json
import sqlite3
import sys
import time

from management.workload.overload import (
    OverloadEvaluator, overload_thresholds_from_config, overload_to_dict,
)


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
    raise SystemExit("[overload] Kein coordinator.db-Pfad (--coordinator-db "
                     "oder paths.coordinator_db in config.yaml).")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="overload_admin",
        description="Aktive Ueberlastwarnung je Ermittler (nur lesend).")
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)
    thresholds = overload_thresholds_from_config(cfg)

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        report = OverloadEvaluator(con).evaluate(
            thresholds=thresholds, now=int(time.time()))
    finally:
        con.close()

    if args.json:
        print(json.dumps(overload_to_dict(report), ensure_ascii=False, indent=2))
        return 0

    print("Ueberlastwarnung (Grenzen: aktive<=%d, rote<=%d, Rueckstau-Alarm>=%d)"
          % (report.max_active_cases, report.max_red_cases, report.backlog_alert))
    print("  overload: %d | warn: %d | Rueckstau: %d%s"
          % (report.overloaded_count, report.warned_count, report.backlog_size,
             "  ALARM" if report.backlog_alarm else ""))
    for a in report.assessments:
        mark = {"overload": "!!", "warn": "! ", "ok": "  "}[a.level]
        print("  %s %-24s aktiv=%d rot=%d %s"
              % (mark, a.name, a.active_cases, a.red_cases,
                 ("(" + "; ".join(a.reasons) + ")") if a.reasons else ""))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

# =============================================================================
# management/stats/gantt_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-2C)
# =============================================================================
# Zweck:
#   NUR-LESENDE CLI fuer das Gantt-Read-Model (management.stats.gantt). Gibt die
#   Ermittler-Spuren mit ihren Fall-Balken aus (Konsole oder JSON). Die ECharts-
#   Sicht folgt in einem spaeteren AP-2C-Build.
#
#   python -m management.stats.gantt_admin [--coordinator-db PATH]
#          [--config ./config.yaml] [--json]
#
# Version: v0.7.447 · Build: 447 · 2026-07-19
# =============================================================================

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone

from management.stats.gantt import GanttModel, gantt_to_dict


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
    raise SystemExit("[gantt] Kein coordinator.db-Pfad (--coordinator-db oder "
                     "paths.coordinator_db in config.yaml).")


def _fmt(ts) -> str:
    if ts is None:
        return "-"
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="gantt_admin",
        description="Gantt-Read-Model (Fall-Balken je Ermittler, nur lesend).")
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)
    now_ts = int(time.time())

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        result = GanttModel(con).build(now_ts=now_ts)
    finally:
        con.close()

    if args.json:
        print(json.dumps(gantt_to_dict(result), ensure_ascii=False, indent=2))
        return 0

    print("Gantt-Uebersicht: %d Balken, Zeitraum %s .. %s"
          % (result.total_bars, _fmt(result.range_start), _fmt(result.range_end)))
    for lane in result.lanes:
        print("  Spur: %s (%d)" % (lane.assignee_name, len(lane.bars)))
        for b in lane.bars:
            marker = "…laufend" if b.ongoing else "abgeschlossen"
            print("    Fall %d (%s) [%s] %s .. %s  %s"
                  % (b.user_id, b.username, b.status,
                     _fmt(b.start_ts), _fmt(b.end_ts), marker))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

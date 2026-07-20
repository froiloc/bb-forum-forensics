# =============================================================================
# management/ops/retention_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Betrieb/Governance (AP-2G)
# =============================================================================
# Zweck:
#   NUR-LESENDE CLI fuer die Aufbewahrungs-/Loeschfristen-Uebersicht. Weist
#   Kandidaten zur LOESCHPRUEFUNG aus — loescht NICHTS.
#
#   python -m management.ops.retention_admin
#          [--coordinator-db PATH] [--config ./config.yaml]
#          [--retention-days N] [--json]
#
# Version: v0.7.456 · Build: 456 · 2026-07-19
# =============================================================================

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone

from management.ops.retention import (
    RetentionRepo, RetentionThresholds, retention_thresholds_from_config,
    retention_to_dict,
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
    raise SystemExit("[retention] Kein coordinator.db-Pfad (--coordinator-db "
                     "oder paths.coordinator_db in config.yaml).")


def _fmt(ts) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="retention_admin",
        description="Aufbewahrungs-/Loeschfristen-Uebersicht (nur lesend, "
                    "loescht NICHTS).")
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--retention-days", type=int, default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)
    thresholds = retention_thresholds_from_config(cfg)
    if args.retention_days is not None:
        thresholds = RetentionThresholds(retention_days=args.retention_days)

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        report = RetentionRepo(con).compute(
            thresholds=thresholds, now=int(time.time()))
    finally:
        con.close()

    if args.json:
        print(json.dumps(retention_to_dict(report), ensure_ascii=False, indent=2))
        return 0

    print("Aufbewahrung (Frist %d Tage): %d abgeschlossene Faelle, %d Kandidat(en) "
          "zur Loeschpruefung%s"
          % (report.retention_days, report.closed_cases, report.candidate_count,
             (", %d ohne Fristbezug" % report.without_reference)
             if report.without_reference else ""))
    for c in report.candidates:
        print("  Fall %d (%s) [%s] Abschluss %s (%s) — %d Tage aufbewahrt "
              "(%d ueber Frist)"
              % (c.user_id, c.username, c.status, _fmt(c.reference_ts),
                 c.reference_field, c.days_retained, c.over_by_days))
    if not report.candidates:
        print("  (kein Kandidat)")
    print("  HINWEIS: Dies ist nur ein Pruefvorschlag. Loeschen ist eine "
          "auditierte Governance-Entscheidung.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

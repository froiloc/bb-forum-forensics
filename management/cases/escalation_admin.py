# =============================================================================
# management/cases/escalation_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fallsteuerung (AP-2F)
# =============================================================================
# Zweck:
#   NUR-LESENDE CLI fuer die Eskalationsregel-Auswertung.
#
#   python -m management.cases.escalation_admin
#          [--coordinator-db PATH] [--config ./config.yaml] [--json]
#
# Version: v0.7.453 · Build: 453 · 2026-07-19
# =============================================================================

import argparse
import json
import sqlite3
import sys
import time

from management.cases.escalation import (
    escalation_thresholds_from_config, escalation_to_dict,
)
from management.cases.escalation_repo import EscalationRepo


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
    raise SystemExit("[escalation] Kein coordinator.db-Pfad (--coordinator-db "
                     "oder paths.coordinator_db in config.yaml).")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="escalation_admin",
        description="Eskalationsregel-Auswertung (nur lesend).")
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)
    thresholds = escalation_thresholds_from_config(cfg)

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        report = EscalationRepo(con).compute(
            thresholds=thresholds, now=int(time.time()))
    finally:
        con.close()

    if args.json:
        print(json.dumps(escalation_to_dict(report), ensure_ascii=False, indent=2))
        return 0

    print("Eskalationen: hoch=%d mittel=%d niedrig=%d (von %d Faellen)"
          % (report.count_hoch, report.count_mittel, report.count_niedrig,
             report.total_cases))
    mark = {"hoch": "!!", "mittel": "! ", "niedrig": "  "}
    for i in report.items:
        print("  %s [%s] %s" % (mark.get(i.severity, "  "), i.rule_code, i.message))
    if not report.items:
        print("  (keine Eskalation)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

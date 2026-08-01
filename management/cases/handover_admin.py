# =============================================================================
# management/cases/handover_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fallsteuerung (AP-2G)
# =============================================================================
# Zweck:
#   NUR-LESENDE CLI fuer das Uebergabe-/Umverteilungsprotokoll.
#
#   python -m management.cases.handover_admin
#          [--coordinator-db PATH] [--config ./config.yaml]
#          [--subject-id N] [--reassignments-only] [--json]
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone

from management.cases.handover_log import handover_to_dict
from management.cases.handover_repo import HandoverRepo
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
    raise SystemExit("[handover] Kein coordinator.db-Pfad (--coordinator-db "
                     "oder paths.coordinator_db in config.yaml).")


def _fmt(ts) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%MZ")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="handover_admin",
        description="Uebergabe-/Umverteilungsprotokoll je Fall (nur lesend).",
        epilog=cli_epilog.epilog("handover_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--subject-id", type=int, default=None)
    p.add_argument("--reassignments-only", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        report = HandoverRepo(con).compute(
            subject_id=args.subject_id, now=int(time.time()))
    finally:
        con.close()

    if args.json:
        print(json.dumps(handover_to_dict(report), ensure_ascii=False, indent=2))
        return 0

    print("Uebergabe-Protokoll: %d Umverteilung(en) ueber %d Fall/Faelle."
          % (report.reassignment_count, report.cases_with_handover))
    for e in report.entries:
        if args.reassignments_only and e.kind != "reassignment":
            continue
        arrow = "%s -> %s" % (e.from_name or "(Rueckstau)",
                              e.to_name or "(Rueckstau)")
        print("  [%s] %s Fall %d: %s  durch %s"
              % (_fmt(e.ts), e.kind, e.subject_id, arrow, e.by_name or "System"))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

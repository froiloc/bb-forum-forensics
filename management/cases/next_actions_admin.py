# =============================================================================
# management/cases/next_actions_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fallsteuerung (AP-2F)
# =============================================================================
# Zweck:
#   NUR-LESENDE CLI fuer die "naechstbeste Aktion"-Warteschlange.
#
#   python -m management.cases.next_actions_admin
#          [--coordinator-db PATH] [--config ./config.yaml]
#          [--scope alle|eigene] [--person-id N] [--json]
#
# Version: v0.7.452 · Build: 452 · 2026-07-19
# =============================================================================

import argparse
import json
import sqlite3
import sys
import time

from management.cases.next_actions import queue_to_dict
from management.cases.next_actions_repo import NextActionsRepo


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
    raise SystemExit("[next_actions] Kein coordinator.db-Pfad (--coordinator-db "
                     "oder paths.coordinator_db in config.yaml).")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="next_actions_admin",
        description="Naechstbeste-Aktion-Warteschlange (nur lesend).")
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--scope", choices=["alle", "eigene"], default="alle")
    p.add_argument("--person-id", type=int, default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        result = NextActionsRepo(con).compute(
            scope=args.scope, person_id=args.person_id, now=int(time.time()))
    finally:
        con.close()

    if args.json:
        print(json.dumps(queue_to_dict(result), ensure_ascii=False, indent=2))
        return 0

    print("Naechstbeste Aktionen (scope %s): %d von %d Faellen offen, %d "
          "abgeschlossen." % (result.scope, result.actionable,
                              result.total_cases, result.done_excluded))
    mark = {"dringend": "!!", "bald": "! ", "routine": "  "}
    for a in result.items:
        print("  %s [P%d %s] Fall %d (%s): %s — %s"
              % (mark.get(a.urgency, "  "), a.priority, a.ampel, a.user_id,
                 a.username, a.action, a.reason))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

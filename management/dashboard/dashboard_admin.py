# =============================================================================
# management/dashboard/dashboard_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   NUR-LESENDE Konsolen-Uebersicht des Ampel-Dashboards (Backend-Sicht,
#   Build 314). Gibt je Fall Ampel + Rohsignale aus. Ersetzt NICHT das
#   spaetere Browser-Frontend (Build 315), erlaubt aber schon jetzt eine
#   automatisiert/manuell pruefbare Sicht ohne Browser.
#
# Aufruf:
#   python -m management.dashboard.dashboard_admin list
#          [--coordinator-db PATH] [--config ./config.yaml]
#
# WICHTIG: Die Ampel-Semantik ist PROVISORISCH (mc ausstehend) — siehe
#          dashboard_repo.classify_ampel.
#
# Beleg: Bauplan B7 v0.9 Paragraph 9.5, mc 2026-07-02.
# Version: v0.7.314 · Build: 314 · 2026-07-02
# =============================================================================

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from management.dashboard.dashboard_repo import DashboardRepo


def _resolve_db_path(args) -> str:
    """
    coordinator.db-Pfad aus --coordinator-db oder config.yaml
    (paths.coordinator_db). Gleiche Aufloesungslogik wie cases_admin /
    case_events_admin — bewusst lokal dupliziert, bis ein gemeinsames
    CLI-Helfermodul eingezogen wird (eigener Refactoring-Build).
    """
    if args.coordinator_db:
        return args.coordinator_db
    try:
        from core.config_loader import ConfigLoader
        cfg = ConfigLoader(config_path=args.config)
        path = cfg.get("paths.coordinator_db")
        if path:
            return str(path)
    except Exception as exc:  # pragma: no cover
        print("[dashboard_admin] config.yaml nicht lesbar: %s" % exc,
              file=sys.stderr)
    raise SystemExit(
        "[dashboard_admin] Kein coordinator.db-Pfad: --coordinator-db oder "
        "paths.coordinator_db in config.yaml."
    )


def _fmt_ts(ts) -> str:
    if ts is None:
        return "-"
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%MZ"
    )


# ASCII-Ampel fuer die Konsole (keine Emoji-Abhaengigkeit im Terminal).
_AMPEL_MARK = {"rot": "[ROT ]", "gelb": "[GELB]", "gruen": "[GRUE]"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Ampel-Dashboard (Backend-Sicht, nur lesend)."
    )
    sub = parser.add_subparsers(dest="action", required=True)
    p_list = sub.add_parser("list", help="Fall-Uebersicht ausgeben")
    p_list.add_argument("--coordinator-db", default=None)
    p_list.add_argument("--config", default="./config.yaml")
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(args)
    if not Path(db_path).exists():
        print("[dashboard_admin] coordinator.db nicht gefunden: %s" % db_path,
              file=sys.stderr)
        return 1

    con = sqlite3.connect(db_path)
    try:
        con.row_factory = sqlite3.Row
        repo = DashboardRepo(con)
        rows = repo.list_case_overview()
        if not rows:
            print("[dashboard_admin] Keine Faelle vorhanden.")
            return 0

        print("Ampel  Prio  user_id  Status        Zuweisung     "
              "LetzteAkt.        Ereignis        Support")
        print("-" * 100)
        for o in rows:
            print("%-6s %4d  %7d  %-12s  %-12s  %-16s  %-14s  %s" % (
                _AMPEL_MARK.get(o.ampel, o.ampel),
                o.priority,
                o.user_id,
                o.status,
                (o.assigned_system_username or "-"),
                _fmt_ts(o.last_activity_at),
                (o.last_event_kind or "-"),
                ("aktiv(%d)" % o.support_count) if o.support_active else "-",
            ))
        print("\nHinweis: Ampel-Semantik PROVISORISCH (mc ausstehend).")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())

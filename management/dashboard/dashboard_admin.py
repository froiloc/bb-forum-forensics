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
# Version: v0.7.315 · Build: 315 · 2026-07-03
# =============================================================================

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from management.dashboard.dashboard_repo import (
    DEFAULT_AMPEL_THRESHOLDS,
    DashboardConfigError,
    DashboardRepo,
    DashboardSchemaError,
    ampel_thresholds_from_config,
)


def _load_config(args):
    """
    Laedt config.yaml (best effort) und gibt den ConfigLoader oder None
    zurueck. None -> die CLI arbeitet mit Vorgabe-Schwellen (7/21). Die
    config.yaml ist die Quelle sowohl fuer den coordinator.db-Pfad als auch
    fuer die Ampel-Schwellen (Build 315) — daher EINMAL laden und
    weiterreichen, statt sie mehrfach zu oeffnen.
    """
    try:
        from core.config_loader import ConfigLoader
        return ConfigLoader(config_path=args.config)
    except Exception as exc:  # pragma: no cover - Konfig-Randfall
        print("[dashboard_admin] config.yaml nicht lesbar (Vorgabe-Schwellen "
              "werden verwendet): %s" % exc, file=sys.stderr)
        return None


def _resolve_db_path(args, cfg) -> str:
    """
    coordinator.db-Pfad aus --coordinator-db oder (falls vorhanden) aus dem
    bereits geladenen ConfigLoader (paths.coordinator_db).
    """
    if args.coordinator_db:
        return args.coordinator_db
    if cfg is not None:
        path = cfg.get("paths.coordinator_db")
        if path:
            return str(path)
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


def _do_export_html(rows, out_path) -> int:
    """Serialisiert die Uebersicht und schreibt eine self-contained HTML-Datei."""
    import dataclasses
    from management.dashboard.html_export import build_dashboard_html
    overview = [dataclasses.asdict(o) for o in rows]
    frontend = Path(__file__).resolve().parent / "frontend"
    css = (frontend / "dashboard.css").read_text(encoding="utf-8")
    js = (frontend / "dashboard.js").read_text(encoding="utf-8")
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = build_dashboard_html(overview, css, js, debug=False,
                                generated_at=generated)
    Path(out_path).write_text(html, encoding="utf-8")
    print("[dashboard_admin] %d Fall/Faelle -> %s (self-contained)"
          % (len(overview), out_path))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Ampel-Dashboard (Backend-Sicht, nur lesend)."
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--coordinator-db", default=None)
    common.add_argument("--config", default="./config.yaml")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list", parents=[common], help="Fall-Uebersicht ausgeben")
    p_exp = sub.add_parser("export-html", parents=[common],
                           help="Self-contained Dashboard-HTML erzeugen")
    p_exp.add_argument("--out", required=True,
                       help="Zielpfad der zu erzeugenden HTML-Datei")
    args = parser.parse_args(argv)

    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)
    if not Path(db_path).exists():
        print("[dashboard_admin] coordinator.db nicht gefunden: %s" % db_path,
              file=sys.stderr)
        return 1

    # Schwellen aus config.yaml (dashboard.ampel.*), sonst Vorgabe 7/21.
    try:
        thresholds = (ampel_thresholds_from_config(cfg)
                      if cfg is not None else DEFAULT_AMPEL_THRESHOLDS)
    except DashboardConfigError as exc:
        print("[dashboard_admin] %s" % exc, file=sys.stderr)
        return 1

    con = sqlite3.connect(db_path)
    try:
        con.row_factory = sqlite3.Row
        repo = DashboardRepo(con)
        try:
            rows = repo.list_case_overview(thresholds=thresholds)
        except DashboardSchemaError as exc:
            # Handlungsleitende Meldung statt rohem SQL-Traceback (mc 2026-07-03).
            print("[dashboard_admin] %s" % exc, file=sys.stderr)
            return 1

        if args.action == "export-html":
            return _do_export_html(rows, args.out)

        # action == "list"
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
        print("\nSchwellen: amber=%d Tage, red=%d Tage (config.yaml: "
              "dashboard.ampel.*)." % (thresholds.amber_idle_days,
                                       thresholds.red_idle_days))
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())

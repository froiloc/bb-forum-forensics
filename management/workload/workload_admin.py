# =============================================================================
# management/workload/workload_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   NUR-LESENDE Konsolen-/Export-Sicht der Ermittler-Lastverteilung (Build 335).
#   Gibt je Ermittler die Fall-Last (nach Ampel/Status) + Aktivitaets-Beleg und
#   den unzugewiesenen Rueckstau aus — als Konsolentabelle ('list') oder als
#   self-contained HTML ('export-html'). Spiegelt dashboard_admin/
#   support_overview_admin.
#
# Aufruf:
#   python -m management.workload.workload_admin list
#          [--coordinator-db PATH] [--config ./config.yaml]
#   python -m management.workload.workload_admin export-html --out PFAD
#          [--coordinator-db PATH] [--config ./config.yaml]
#
# Ampel-Schwellen stammen (wie im Dashboard) aus config.yaml
# (dashboard.ampel.*), Vorgabe 7/21 — so ist die Farbsemantik konsistent.
# Vor 'export-html' prueft die CLI die audit_log-Kette (verify_chain).
# coordinator.db wird AUSSCHLIESSLICH gelesen.
#
# Version: v0.7.335 · Build: 335 · 2026-07-07
# =============================================================================

import argparse
import dataclasses
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from management.audit.audit_log import AuditLog
from management.dashboard.dashboard_repo import (
    DEFAULT_AMPEL_THRESHOLDS,
    DashboardConfigError,
    DashboardSchemaError,
    ampel_thresholds_from_config,
)
from management.workload.investigator_load import BACKLOG_LABEL
from management.workload.workload_repo import WorkloadRepo, WorkloadSchemaError
from management.help import cli_epilog  # noqa: E402


def _load_config(args):
    try:
        from core.config_loader import ConfigLoader
        return ConfigLoader(config_path=args.config)
    except Exception as exc:  # pragma: no cover - Konfig-Randfall
        print("[workload_admin] config.yaml nicht lesbar (Vorgabe-Schwellen): "
              "%s" % exc, file=sys.stderr)
        return None


def _resolve_db_path(args, cfg) -> str:
    if args.coordinator_db:
        return args.coordinator_db
    if cfg is not None:
        path = cfg.get("paths.coordinator_db")
        if path:
            return str(path)
    raise SystemExit(
        "[workload_admin] Kein coordinator.db-Pfad: --coordinator-db oder "
        "paths.coordinator_db in config.yaml."
    )


def _fmt_ts(ts) -> str:
    if ts is None:
        return "-"
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%MZ"
    )


def _verify_result_dict(con) -> dict:
    audit = AuditLog(con)
    vr = audit.verify_chain()
    tip_hash, tip_seq = audit.tip()
    return {"ok": bool(vr.ok), "first_bad_seq": vr.first_bad_seq,
            "detail": vr.detail, "tip_seq": tip_seq, "tip_hash": tip_hash}


def _do_export_html(con, rows, out_path, db_path=None,
                    actor=None, behoerde=None, aktenzeichen=None) -> int:
    from management.workload.html_export import build_workload_html
    records = [dataclasses.asdict(r) for r in rows]
    frontend = Path(__file__).resolve().parent / "frontend"
    css = (frontend / "workload.css").read_text(encoding="utf-8")
    js = (frontend / "workload.js").read_text(encoding="utf-8")
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    verify = _verify_result_dict(con)
    if not verify["ok"]:
        print("[workload_admin] WARNUNG: audit_log-Kette gebrochen (%s) — "
              "Export erfolgt, Banner weist darauf hin." % verify["detail"],
              file=sys.stderr)

    # B442: einheitlicher Export-Rahmen (Aktenkopf-Band + Erzeugungsvermerk +
    # Pruefsumme). Kontext-Builder ist voll abgesichert.
    envelope = None
    if db_path is not None:
        from management.export.context_builder import build_export_context
        from management.export.export_envelope import ExportEnvelope
        ctx = build_export_context(
            con=con, db_path=db_path, behoerde=behoerde,
            aktenzeichen=aktenzeichen or "Ermittler-Lastverteilung",
            actor=actor, now_utc=generated)
        envelope = ExportEnvelope(ctx)

    html = build_workload_html(records, css, js, debug=False,
                               generated_at=generated, verify_result=verify,
                               envelope=envelope)
    Path(out_path).write_text(html, encoding="utf-8")
    print("[workload_admin] %d Zeile(n) -> %s (self-contained)"
          % (len(records), out_path))
    return 0


def _do_list(rows) -> int:
    if not rows:
        print("[workload_admin] Keine Ermittler/Faelle vorhanden.")
        return 0
    print("Ermittler          Rollen   Faelle  rot  gelb gruen  aktiv  fertig  "
          "Aktionen  letzte Aktion")
    print("-" * 104)
    for r in rows:
        if r.is_backlog:
            rollen = "----"
        else:
            rollen = "%s%s%s" % ("E" if r.is_investigator else "-",
                                 "C" if r.is_supervisor else "-",
                                 "S" if r.is_support else "-")
        name = (BACKLOG_LABEL if r.is_backlog
                else (r.system_username or "-"))
        print("%-18s %-6s  %6d  %3d  %4d  %4d  %5d  %6d  %8s  %s" % (
            name[:18], rollen, r.total_cases, r.ampel_rot, r.ampel_gelb,
            r.ampel_gruen, r.active_cases, r.done_cases,
            ("-" if r.is_backlog else str(r.audit_action_count)),
            ("-" if r.is_backlog else _fmt_ts(r.last_action_at)),
        ))
    print("\nRollen: E=Ermittler C=Chef/Supervisor S=Support. Ampel-Semantik "
          "wie Dashboard. Rueckstau-Zeile = unzugewiesene Faelle.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Ermittler-Lastverteilung (nur lesend).",
        epilog=cli_epilog.epilog("workload_admin"),
        formatter_class=cli_epilog.HilfeFormat,
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--coordinator-db", default=None)
    common.add_argument("--config", default="./config.yaml")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list", parents=[common],
                   help="Lastverteilung in der Konsole ausgeben")
    p_exp = sub.add_parser("export-html", parents=[common],
                           help="Self-contained Lastverteilungs-HTML erzeugen")
    p_exp.add_argument("--out", required=True,
                       help="Zielpfad der zu erzeugenden HTML-Datei")
    p_exp.add_argument("--behoerde", default=None)
    p_exp.add_argument("--aktenzeichen", default=None)
    p_exp.add_argument("--actor", default=None,
                       help="SAMAccountName der ausfuehrenden Person (Dev/Test).")
    args = parser.parse_args(argv)

    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)
    if not Path(db_path).exists():
        print("[workload_admin] coordinator.db nicht gefunden: %s" % db_path,
              file=sys.stderr)
        return 1

    try:
        thresholds = (ampel_thresholds_from_config(cfg)
                      if cfg is not None else DEFAULT_AMPEL_THRESHOLDS)
    except DashboardConfigError as exc:
        print("[workload_admin] %s" % exc, file=sys.stderr)
        return 1

    con = sqlite3.connect(db_path)
    try:
        con.row_factory = sqlite3.Row
        repo = WorkloadRepo(con)
        try:
            rows = repo.list_workload(thresholds=thresholds)
        except (WorkloadSchemaError, DashboardSchemaError) as exc:
            print("[workload_admin] %s" % exc, file=sys.stderr)
            return 1

        if args.action == "export-html":
            return _do_export_html(
                con, rows, args.out, db_path=db_path,
                actor=getattr(args, "actor", None),
                behoerde=getattr(args, "behoerde", None),
                aktenzeichen=getattr(args, "aktenzeichen", None))
        return _do_list(rows)
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())

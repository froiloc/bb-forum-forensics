# =============================================================================
# management/support_overview/support_overview_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   NUR-LESENDE Konsolen-/Export-Sicht der Support-Sitzungs-Historie (Build 330).
#   Rekonstruiert die permanente 'wer sah wann welchen Fall'-Historie aus dem
#   audit_log und gibt sie als Konsolentabelle ('list') oder als self-contained
#   HTML-Datei ('export-html') aus. Spiegelt bewusst dashboard_admin.
#
# Aufruf:
#   python -m management.support_overview.support_overview_admin list
#          [--coordinator-db PATH] [--config ./config.yaml]
#   python -m management.support_overview.support_overview_admin export-html
#          --out PFAD [--coordinator-db PATH] [--config ./config.yaml]
#
# INTEGRITAET: Vor 'export-html' (und optional bei 'list') wird die audit_log-
#   Hashkette geprueft (verify_chain). Das Ergebnis wandert als Banner in die
#   Export-Datei — die Historie ist nur so vertrauenswuerdig wie ihre Belegkette.
#
# coordinator.db wird AUSSCHLIESSLICH gelesen (Produktivbetrieb-Regel).
#
# Version: v0.7.330 · Build: 330 · 2026-07-07
# =============================================================================

import argparse
import dataclasses
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from management.audit.audit_log import AuditLog
from management.support_overview.support_overview_repo import (
    SupportOverviewRepo,
    SupportOverviewSchemaError,
)
from management.support_overview.support_session_record import (
    STATUS_DANGLING,
    STATUS_ENDED_ORPHAN,
    STATUS_OPEN,
)


def _load_config(args):
    """
    Laedt config.yaml (best effort) und gibt den ConfigLoader oder None zurueck.
    Die config.yaml ist die Quelle des coordinator.db-Pfads (paths.coordinator_db).
    """
    try:
        from core.config_loader import ConfigLoader
        return ConfigLoader(config_path=args.config)
    except Exception as exc:  # pragma: no cover - Konfig-Randfall
        print("[support_overview_admin] config.yaml nicht lesbar: %s" % exc,
              file=sys.stderr)
        return None


def _resolve_db_path(args, cfg) -> str:
    """coordinator.db-Pfad aus --coordinator-db oder paths.coordinator_db."""
    if args.coordinator_db:
        return args.coordinator_db
    if cfg is not None:
        path = cfg.get("paths.coordinator_db")
        if path:
            return str(path)
    raise SystemExit(
        "[support_overview_admin] Kein coordinator.db-Pfad: --coordinator-db "
        "oder paths.coordinator_db in config.yaml."
    )


def _fmt_ts(ts) -> str:
    if ts is None:
        return "-"
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%MZ"
    )


def _fmt_duration(sec) -> str:
    """Menschliche Dauer aus dem geschriebenen duration_sec; None -> '-'."""
    if sec is None:
        return "-"
    s = max(0, int(sec))
    h, rem = divmod(s, 3600)
    m, ss = divmod(rem, 60)
    if h > 0:
        return "%dh%02dm%02ds" % (h, m, ss)
    if m > 0:
        return "%dm%02ds" % (m, ss)
    return "%ds" % ss


# ASCII-Statusmarke fuer die Konsole (keine Farbabhaengigkeit im Terminal).
_STATUS_MARK = {
    "beendet": "[beendet ]",
    STATUS_ENDED_ORPHAN: "[timeout ]",
    STATUS_OPEN: "[offen   ]",
    STATUS_DANGLING: "[herrenl.]",
}


def _verify_result_dict(con) -> dict:
    """
    Prueft die audit_log-Kette und liefert ein serialisierbares dict fuer das
    Export-Banner: {ok, first_bad_seq, detail, tip_seq, tip_hash}.
    """
    audit = AuditLog(con)
    vr = audit.verify_chain()
    tip_hash, tip_seq = audit.tip()
    return {
        "ok": bool(vr.ok),
        "first_bad_seq": vr.first_bad_seq,
        "detail": vr.detail,
        "tip_seq": tip_seq,
        "tip_hash": tip_hash,
    }


def _do_export_html(con, rows, out_path, db_path=None,
                    actor=None, behoerde=None, aktenzeichen=None) -> int:
    """Serialisiert die Historie und schreibt eine self-contained HTML-Datei."""
    from management.support_overview.html_export import (
        build_support_overview_html,
    )
    records = [dataclasses.asdict(r) for r in rows]
    frontend = Path(__file__).resolve().parent / "frontend"
    css = (frontend / "support_overview.css").read_text(encoding="utf-8")
    js = (frontend / "support_overview.js").read_text(encoding="utf-8")
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    verify = _verify_result_dict(con)
    if not verify["ok"]:
        print("[support_overview_admin] WARNUNG: audit_log-Kette gebrochen "
              "(%s) — Export erfolgt, Banner weist darauf hin."
              % verify["detail"], file=sys.stderr)

    # B442: einheitlicher Export-Rahmen (Aktenkopf-Band + Erzeugungsvermerk +
    # Pruefsumme). Kontext-Builder ist voll abgesichert.
    envelope = None
    if db_path is not None:
        from management.export.context_builder import build_export_context
        from management.export.export_envelope import ExportEnvelope
        ctx = build_export_context(
            con=con, db_path=db_path, behoerde=behoerde,
            aktenzeichen=aktenzeichen or "Support-Sitzungs-Historie",
            actor=actor, now_utc=generated)
        envelope = ExportEnvelope(ctx)

    html = build_support_overview_html(records, css, js, debug=False,
                                       generated_at=generated,
                                       verify_result=verify,
                                       envelope=envelope)
    Path(out_path).write_text(html, encoding="utf-8")
    print("[support_overview_admin] %d Sitzung(en) -> %s (self-contained)"
          % (len(records), out_path))
    return 0


def _do_list(rows) -> int:
    if not rows:
        print("[support_overview_admin] Keine Support-Sitzungen im audit_log.")
        return 0
    print("Status      Sitzg  Fall(user_id)  Benutzer          Supporter        "
          "Start             Ende              Dauer     Grund          Beleg(seq)   Anomalie")
    print("-" * 150)
    for r in rows:
        print("%-10s %6s  %13s  %-16s  %-15s  %-16s  %-16s  %-8s  %-13s  %-11s  %s" % (
            _STATUS_MARK.get(r.status, "[%s]" % r.status),
            r.session_id,
            r.user_id,
            (r.username or "(kein cases)")[:16],
            (r.supporter_display_name or r.supporter_system_username
             or (("id %d" % r.supporter_id) if r.supporter_id is not None
                 else "unbekannt"))[:15],
            _fmt_ts(r.started_at),
            _fmt_ts(r.ended_at),
            _fmt_duration(r.duration_sec),
            (r.reason or "-"),
            ("S%s/E%s" % (r.started_seq if r.started_seq is not None else "-",
                         r.ended_seq if r.ended_seq is not None else "-")),
            (r.anomaly or ""),
        ))
    print("\n%d Sitzung(en). Quelle: audit_log (permanent). Ordnung: "
          "chronologisch." % len(rows))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Support-Sitzungs-Historie (nur lesend, aus audit_log)."
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--coordinator-db", default=None)
    common.add_argument("--config", default="./config.yaml")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list", parents=[common],
                   help="Sitzungs-Historie in der Konsole ausgeben")
    p_exp = sub.add_parser("export-html", parents=[common],
                           help="Self-contained Historie-HTML erzeugen")
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
        print("[support_overview_admin] coordinator.db nicht gefunden: %s"
              % db_path, file=sys.stderr)
        return 1

    con = sqlite3.connect(db_path)
    try:
        con.row_factory = sqlite3.Row
        repo = SupportOverviewRepo(con)
        try:
            rows = repo.list_support_sessions()
        except SupportOverviewSchemaError as exc:
            # Handlungsleitende Meldung statt rohem SQL-Traceback.
            print("[support_overview_admin] %s" % exc, file=sys.stderr)
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

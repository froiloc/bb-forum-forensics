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
#
# BUILD 706 (Vorgang 70641ff9): Konnte eine Angabe des Erzeugungsvermerks
#   nicht ermittelt werden, steht das seit Build 702 im erzeugten Dokument.
#   Seit Build 706 wird es zusaetzlich auf der Fehlerausgabe benannt - wer
#   den Lauf beobachtet, erfuhr es sonst erst beim Aufschlagen der Datei.
#
# Version: v0.8.706 · Build: 706 · 2026-08-12
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
from management.help import cli_epilog  # noqa: E402
# Build 644: die Vorrangregel Argument > config.yaml > Vorgabewert
# steht seit Build 643 an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402


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
    coordinator.db-Pfad: Argument --coordinator-db > paths.coordinator_db
    > Abbruch.

    BUILD 644 - DIE AUFLOESUNG IST UMGEZOGEN, das Verhalten NICHT.
    Sie steht jetzt in core/werkzeug_konfig.py; die Begruendung fuer den
    Umzug steht im Kopf jener Datei.

    'cfg' BLEIBT PARAMETER, und das ist der Kern dieser Umstellung: Dieses
    Werkzeug laedt die config.yaml EINMAL (_load_config) und reicht sie
    weiter - fuer den Pfad UND fuer seine uebrigen Werte. Wuerde die
    Aufloesung sich hier ihre eigene Kopie holen, koennten beide im
    Grenzfall aus VERSCHIEDENEN Staenden derselben Datei stammen. Der
    Aufloeser wird deshalb UM den vorhandenen Loader gebaut, nicht neben ihn.

    UNVERAENDERT bleiben: die Reihenfolge, das Fehlen eines Vorgabewerts,
    der Abbruch mit dem Praefix '[dashboard_admin]' - nur nennt die Meldung jetzt
    BEIDE Wege statt nur einen. Die Meldung ueber eine unlesbare config.yaml
    gibt weiterhin _load_config aus; cfg ist dann None.
    """
    return werkzeug_konfig.db_pfad(
        "dashboard_admin", args, arg_attribut="coordinator_db",
        arg_name="--coordinator-db", config_schluessel="paths.coordinator_db",
        name="coordinator_db", r=werkzeug_konfig.resolver_aus_loader(cfg))


def _fmt_ts(ts) -> str:
    if ts is None:
        return "-"
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%MZ"
    )


# ASCII-Ampel fuer die Konsole (keine Emoji-Abhaengigkeit im Terminal).
_AMPEL_MARK = {"rot": "[ROT ]", "gelb": "[GELB]", "gruen": "[GRUE]"}


def _do_export_html(rows, out_path, con=None, db_path=None,
                    actor=None, behoerde=None, aktenzeichen=None) -> int:
    """Serialisiert die Uebersicht und schreibt eine self-contained HTML-Datei.

    Ist con/db_path gesetzt (B442), wird der einheitliche Export-Rahmen
    (Aktenkopf-Band + Erzeugungsvermerk + Pruefsumme) angebracht; der
    Kontext-Builder ist voll abgesichert und laesst den Export nie am Rahmen
    scheitern.
    """
    import dataclasses
    from management.dashboard.html_export import build_dashboard_html
    overview = [dataclasses.asdict(o) for o in rows]
    frontend = Path(__file__).resolve().parent / "frontend"
    css = (frontend / "dashboard.css").read_text(encoding="utf-8")
    js = (frontend / "dashboard.js").read_text(encoding="utf-8")
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    envelope = None
    if con is not None and db_path is not None:
        from management.export.context_builder import build_export_context
        from management.export.export_envelope import ExportEnvelope
        from management.export.rahmen_meldung import melde_rahmen_befunde
        ctx = build_export_context(
            con=con, db_path=db_path, behoerde=behoerde,
            aktenzeichen=aktenzeichen or "Ampel-Dashboard (Fall-Uebersicht)",
            actor=actor, now_utc=generated)
        # BUILD 706 (Vorgang 70641ff9): Konnte eine Angabe des
        # Erzeugungsvermerks nicht ermittelt werden, steht das seit Build 702
        # im Dokument - aber bis hierher nicht auf der Fehlerausgabe. Wer den
        # Lauf beobachtet, erfuhr davon erst beim Aufschlagen der Datei.
        # VOR dem Schreiben: faellt das Schreiben aus, ist die Auskunft
        # bereits heraus.
        melde_rahmen_befunde("[dashboard_admin]", ctx)
        envelope = ExportEnvelope(ctx)

    html = build_dashboard_html(overview, css, js, debug=False,
                                generated_at=generated, envelope=envelope)
    Path(out_path).write_text(html, encoding="utf-8")
    print("[dashboard_admin] %d Fall/Faelle -> %s (self-contained)"
          % (len(overview), out_path))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Ampel-Dashboard (Backend-Sicht, nur lesend).",
        epilog=cli_epilog.epilog("dashboard_admin"),
        formatter_class=cli_epilog.HilfeFormat,
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
    p_exp.add_argument("--behoerde", default=None)
    p_exp.add_argument("--aktenzeichen", default=None)
    p_exp.add_argument("--actor", default=None,
                       help="SAMAccountName der ausfuehrenden Person (Dev/Test).")
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

    # BUILD 629 (Regel PY4, Vorgang 906ede75, bei der Erhebung dazugekommen): Die coordinator.db wird
    # NUR-LESEND geoeffnet. Der Dateikopf sichert das seit jeher zu -
    # durchgesetzt hat es bis Build 628 nichts: die Verbindung war
    # schreibfaehig, und die Zusage stand allein im Kommentar. Ein
    # versehentlicher Schreibversuch scheitert jetzt technisch und nicht
    # erst im Gegenlesen.
    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
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
            return _do_export_html(
                rows, args.out, con=con, db_path=db_path,
                actor=getattr(args, "actor", None),
                behoerde=getattr(args, "behoerde", None),
                aktenzeichen=getattr(args, "aktenzeichen", None))

        # action == "list"
        if not rows:
            print("[dashboard_admin] Keine Faelle vorhanden.")
            return 0

        print("Ampel  Prio  subject_id  Status        Zuweisung     "
              "LetzteAkt.        Ereignis        Support")
        print("-" * 100)
        for o in rows:
            print("%-6s %4d  %7d  %-12s  %-12s  %-16s  %-14s  %s" % (
                _AMPEL_MARK.get(o.ampel, o.ampel),
                o.priority,
                o.subject_id,
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

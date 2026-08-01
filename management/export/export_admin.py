# =============================================================================
# management/export/export_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem (AP-2B)
# =============================================================================
# Zweck:
#   NUR-LESENDE CLI, die konkrete Exporte ueber das gemeinsame Framework
#   (Build 440) erzeugt. Build 441 liefert das erste Format:
#
#     python -m management.export.export_admin case-status-xlsx --out fall.xlsx
#            [--coordinator-db PATH] [--config ./config.yaml]
#            [--behoerde TEXT] [--aktenzeichen TEXT] [--actor SAMACCOUNT]
#
#   Ablauf (nur lesend, kein Schreibpfad -> kein Migrationsvorbehalt):
#     1. config.yaml laden -> coordinator.db-Pfad + optionale Rahmen-Vorgaben.
#     2. coordinator.db read-only oeffnen.
#     3. DashboardRepo.list_case_overview() -> Fallstatus (Beleg dashboard_repo).
#     4. audit_log-Kette pruefen (verify_chain) + Spitze lesen -> Erzeugungs-
#        vermerk zertifiziert die Belegkette (wie die bestehenden html_export).
#     5. ausfuehrende Identitaet aufloesen (IdentityResolver, SAMAccountName =
#        stabile forensische Identitaet; --actor uebersteuert fuer Dev/Test).
#     6. build_case_status_xlsx(...) -> Datei schreiben.
#
#   VOR PRODUKTIVEM LAUF: MD5 der eingesetzten Dateien bestaetigen (GR8).
#
# Version: v0.7.441 · Build: 441 · 2026-07-19
# =============================================================================

import argparse
import dataclasses
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from management.audit.audit_log import AuditLog
from management.dashboard.dashboard_repo import (
    DashboardRepo,
    DashboardSchemaError,
    ampel_thresholds_from_config,
    DEFAULT_AMPEL_THRESHOLDS,
)
from management.export.excel_case_status import (
    build_case_status_xlsx,
    ExcelUnavailable,
)
from management.export.export_envelope import ExportContext, DEFAULT_KLASSIFIKATION
from management.help import cli_epilog  # noqa: E402
# Build 644: die Vorrangregel Argument > config.yaml > Vorgabewert
# steht seit Build 643 an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402

_DEFAULT_BEHOERDE = "Polizei NRW"


def _load_config(args):
    try:
        from core.config_loader import ConfigLoader
        return ConfigLoader(config_path=args.config)
    except Exception as exc:  # pragma: no cover - Konfig-Randfall
        print("[export_admin] config.yaml nicht lesbar (Vorgaben werden "
              "verwendet): %s" % exc, file=sys.stderr)
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
    der Abbruch mit dem Praefix '[export_admin]' - nur nennt die Meldung jetzt
    BEIDE Wege statt nur einen. Die Meldung ueber eine unlesbare config.yaml
    gibt weiterhin _load_config aus; cfg ist dann None.
    """
    return werkzeug_konfig.db_pfad(
        "export_admin", args, arg_attribut="coordinator_db",
        arg_name="--coordinator-db", config_schluessel="paths.coordinator_db",
        name="coordinator_db", r=werkzeug_konfig.resolver_aus_loader(cfg))


def _build_number() -> int:
    """Buildnummer aus der repo-eigenen build.json (GR4); Fallback 0."""
    try:
        p = Path(__file__).resolve().parents[2] / "build.json"
        return int(json.loads(p.read_text(encoding="utf-8"))["build"])
    except Exception:  # pragma: no cover - Randfall
        return 0


def _verify_tip(con):
    """
    (chain_ok, tip_seq, tip_hash, detail) aus dem audit_log.
    chain_ok: True=intakt, False=gebrochen, None=nicht pruefbar (Tabelle fehlt).
    In PROD existiert audit_log immer (M001); fehlt sie dennoch, wird der Export
    NICHT abgebrochen, sondern ehrlich als 'nicht geprueft' vermerkt (GR1).
    """
    try:
        audit = AuditLog(con)
        vr = audit.verify_chain()
        tip_hash, tip_seq = audit.tip()
        return bool(vr.ok), tip_seq, tip_hash, vr.detail
    except sqlite3.OperationalError as exc:
        return None, None, None, "audit_log nicht pruefbar: %s" % exc


def _resolve_actor(db_path, actor):
    """
    (system_username, display_name) der ausfuehrenden Person. --actor
    uebersteuert; sonst OS-Identitaet via IdentityResolver. Scheitert die
    Aufloesung, wird der Rohwert/--actor bzw. 'unbekannt' verwendet (der
    Export bleibt moeglich; der Vermerk bleibt ehrlich).
    """
    try:
        from management.server.identity import IdentityResolver
        resolver = IdentityResolver(db_path)
        person = resolver.resolve(system_username=actor)
        return person.get("system_username") or (actor or "unbekannt"), \
            person.get("display_name")
    except Exception as exc:  # pragma: no cover - Identitaets-Randfall
        print("[export_admin] Identitaet nicht aufloesbar (%s) — "
              "Erzeugungsvermerk nutzt Rohwert." % exc, file=sys.stderr)
        return (actor or "unbekannt"), None


def _do_case_status_xlsx(args) -> int:
    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)

    thresholds = DEFAULT_AMPEL_THRESHOLDS
    if cfg is not None:
        try:
            thresholds = ampel_thresholds_from_config(cfg)
        except Exception:  # pragma: no cover
            thresholds = DEFAULT_AMPEL_THRESHOLDS

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        repo = DashboardRepo(con)
        overviews = repo.list_case_overview(thresholds=thresholds)
        rows = [dataclasses.asdict(o) for o in overviews]
        chain_ok, tip_seq, tip_hash, detail = _verify_tip(con)
    except DashboardSchemaError as exc:
        raise SystemExit("[export_admin] Schema-Fehler: %s" % exc)
    finally:
        con.close()

    if chain_ok is False:
        print("[export_admin] WARNUNG: audit_log-Kette gebrochen (%s) — "
              "Export erfolgt, Erzeugungsvermerk weist es aus." % detail,
              file=sys.stderr)
    elif chain_ok is None:
        print("[export_admin] HINWEIS: audit_log-Kette nicht pruefbar (%s) — "
              "Erzeugungsvermerk vermerkt 'nicht geprueft'." % detail,
              file=sys.stderr)

    actor, display = _resolve_actor(db_path, args.actor)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    context = ExportContext(
        behoerde=args.behoerde or _DEFAULT_BEHOERDE,
        aktenzeichen=args.aktenzeichen or "Alle Faelle",
        ersteller=actor,
        build_number=_build_number(),
        generated_at=generated,
        chain_ok=chain_ok,
        chain_tip_seq=tip_seq,
        chain_tip_hash=tip_hash,
        klassifikation=args.klassifikation or DEFAULT_KLASSIFIKATION,
        anzeigename=display,
    )

    try:
        data = build_case_status_xlsx(
            rows, context, scope_label=args.aktenzeichen or "Alle Faelle")
    except ExcelUnavailable as exc:
        raise SystemExit("[export_admin] %s" % exc)

    Path(args.out).write_bytes(data)
    print("[export_admin] %d Fall/Faelle -> %s (%d Bytes, Datendigest im Blatt)"
          % (len(rows), args.out, len(data)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="export_admin",
        description="Management-Exporte ueber das einheitliche Export-Framework.",
        epilog=cli_epilog.epilog("export_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    sub = p.add_subparsers(dest="cmd", required=True)

    x = sub.add_parser("case-status-xlsx",
                       help="Fallstatus-Uebersicht als .xlsx exportieren.")
    x.add_argument("--out", required=True, help="Zieldatei (.xlsx).")
    x.add_argument("--coordinator-db", default=None)
    x.add_argument("--config", default="./config.yaml")
    x.add_argument("--behoerde", default=None)
    x.add_argument("--aktenzeichen", default=None)
    x.add_argument("--klassifikation", default=None)
    x.add_argument("--actor", default=None,
                   help="SAMAccountName der ausfuehrenden Person (Dev/Test).")
    x.set_defaults(func=_do_case_status_xlsx)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

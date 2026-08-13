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
# BUILD 708 (Vorgang 5001d293) — DIE SCHRITTE 4 UND 5 MACHT JETZT DER
#   CONTEXT_BUILDER. Bis Build 706 hielt dieses Werkzeug eigene Kopien von
#   _build_number, _verify_tip und _resolve_actor und baute den ExportContext
#   von Hand. Es war das einzige, das den in Build 442 eigens dafuer
#   geschaffenen context_builder nicht benutzte - und deshalb auch das
#   einzige, an dem die Rahmenbefunde aus Build 702 vorbeigingen. Naeheres bei
#   _do_case_status_xlsx().
#
# Version: v0.8.708 · Build: 708 · 2026-08-12
# =============================================================================

import argparse
import dataclasses
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

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
from management.export.export_envelope import DEFAULT_KLASSIFIKATION
# Build 708 (Vorgang 5001d293): der gemeinsame Rahmen und seine Meldung -
# dieselbe Quelle wie bei allen uebrigen Export-Werkzeugen.
from management.export.context_builder import build_export_context
from management.export.rahmen_meldung import melde_rahmen_befunde
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


def _do_case_status_xlsx(args) -> int:
    """
    BUILD 708 (Vorgang 5001d293) — DIE DREI EIGENEN KOPIEN SIND ENTFALLEN.

    Bis Build 706 hielt dieses Werkzeug eigene Fassungen von _build_number,
    _verify_tip und _resolve_actor und setzte den ExportContext von Hand
    zusammen. Es war damit das EINZIGE, das den context_builder nicht
    benutzte - und deshalb auch das einzige, an dem die Rahmenbefunde aus
    Build 702 vorbeigingen: sein _build_number gab bei unlesbarer build.json
    still 0 zurueck, und die Fallstatus-XLSX trug dann 'Werkzeug-Build: 0'
    ohne ein Wort. Genau der Zustand, den ff7e80ab fuer die
    Berichtswerkzeuge beanstandet hat.

    DREI UNTERSCHIEDE ZUM ALTEN VERHALTEN, jeder einzeln bedacht:

    (1) DIE WARNUNG ZUR GEBROCHENEN KETTE BLEIBT - sie war der Grund, hier
        nicht blind umzustellen. Der context_builder erzeugt fuer
        chain_ok=False bewusst KEINEN Rahmenbefund (eine gebrochene Kette ist
        eine Aussage ueber den BESTAND, nicht ueber den Vermerk; Build 702,
        note (6)). Ein blosser Austausch haette diese Warnung also lautlos
        entfernt. Sie steht deshalb weiterhin hier, und der Klartext dazu
        kommt seit Build 708 als ctx.chain_detail mit.

    (2) 'KETTE NICHT PRUEFBAR' WANDERT VOM HINWEIS ZUR WARNUNG. Dieser Fall
        ist jetzt ein Rahmenbefund und wird wie jeder andere gemeldet. Der
        Wortlaut aendert sich, die Auskunft nicht - sie wird eher deutlicher.

    (3) DAS WERKZEUG SCHEITERT NICHT MEHR AN DER KETTENPRUEFUNG. Die alte
        Kopie fing NUR sqlite3.OperationalError; ein Attribut- oder
        Importfehler aus AuditLog schlug durch und beendete den Export. Der
        context_builder faengt alles (RF06). Ein Export soll nicht am Rahmen
        scheitern.
    """
    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)

    thresholds = DEFAULT_AMPEL_THRESHOLDS
    if cfg is not None:
        try:
            thresholds = ampel_thresholds_from_config(cfg)
        except Exception:  # pragma: no cover
            thresholds = DEFAULT_AMPEL_THRESHOLDS

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        repo = DashboardRepo(con)
        overviews = repo.list_case_overview(thresholds=thresholds)
        rows = [dataclasses.asdict(o) for o in overviews]
        # Der Rahmen wird JETZT gebildet, nicht mehr nach dem Schliessen:
        # build_export_context braucht die offene Verbindung fuer die
        # Kettenspitze. Es wirft nie, kann also innerhalb dieses try stehen,
        # ohne den Schema-Zweig darunter zu stoeren.
        context = build_export_context(
            con=con, db_path=db_path,
            behoerde=args.behoerde or _DEFAULT_BEHOERDE,
            aktenzeichen=args.aktenzeichen or "Alle Faelle",
            actor=args.actor,
            klassifikation=args.klassifikation or DEFAULT_KLASSIFIKATION,
            now_utc=generated)
    except DashboardSchemaError as exc:
        raise SystemExit("[export_admin] Schema-Fehler: %s" % exc)
    finally:
        con.close()

    # Zuerst die Aussage ueber den BESTAND (siehe (1) oben), danach die ueber
    # den VERMERK. Die Reihenfolge ist die des bisherigen Werkzeugs.
    if context.chain_ok is False:
        print("[export_admin] WARNUNG: audit_log-Kette gebrochen (%s) — "
              "Export erfolgt, Erzeugungsvermerk weist es aus."
              % (context.chain_detail or "ohne naehere Angabe"),
              file=sys.stderr)

    # Vor dem Schreiben der Datei — faellt das Schreiben aus (fehlendes
    # openpyxl, Pfad, Platte), ist die Auskunft ueber den Rahmen bereits
    # heraus.
    melde_rahmen_befunde("[export_admin]", context)

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

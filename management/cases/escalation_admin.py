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
from management.help import cli_epilog  # noqa: E402
# Build 644: die Vorrangregel Argument > config.yaml > Vorgabewert
# steht seit Build 643 an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402


def _load_config(args):
    try:
        from core.config_loader import ConfigLoader
        return ConfigLoader(config_path=args.config)
    except Exception:  # pragma: no cover
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
    der Abbruch mit dem Praefix '[escalation_admin]' - nur nennt die Meldung jetzt
    BEIDE Wege statt nur einen. Die Meldung ueber eine unlesbare config.yaml
    gibt weiterhin _load_config aus; cfg ist dann None.
    """
    return werkzeug_konfig.db_pfad(
        "escalation_admin", args, arg_attribut="coordinator_db",
        arg_name="--coordinator-db", config_schluessel="paths.coordinator_db",
        name="coordinator_db", r=werkzeug_konfig.resolver_aus_loader(cfg))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="escalation_admin",
        description="Eskalationsregel-Auswertung (nur lesend).",
        epilog=cli_epilog.epilog("escalation_admin"),
        formatter_class=cli_epilog.HilfeFormat)
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

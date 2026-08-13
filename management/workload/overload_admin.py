# =============================================================================
# management/workload/overload_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Lastverteilung (AP-2F)
# =============================================================================
# Zweck:
#   NUR-LESENDE CLI fuer die aktive Ueberlastwarnung (management.workload.
#   overload). Gibt je Ermittler die Warnstufe (ok/warn/overload) samt
#   Ausloeser aus und meldet den systemischen Rueckstau-Alarm.
#
#   python -m management.workload.overload_admin
#          [--coordinator-db PATH] [--config ./config.yaml] [--json]
#
# Version: v0.8.718 · Build: 718 · 2026-08-13
# =============================================================================

import argparse
import json
import sqlite3
import sys
import time

from management.workload.overload import (
    OverloadEvaluator, overload_thresholds_from_config, overload_to_dict,
)
from management.help import cli_epilog  # noqa: E402
# Build 644: die Vorrangregel Argument > config.yaml > Vorgabewert
# steht seit Build 643 an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402


def _load_config(args):
    """
    Laedt die config.yaml und MELDET ihren Ausfall auf stderr.

    TICKET cf791ef0 (Build 718): Bis hierher stand an dieser Stelle eine
    Abschrift mit 'except Exception: return None' - OHNE Ausgabe. Faellt
    die Konfiguration aus, gelten die Vorgabeschwellen, und nichts weist
    darauf hin. Das war ein still uebersprungener Beleg (Grundregel 1) -
    und zwar an einer Angabe, die das ERGEBNIS veraendert und nicht nur
    seinen Vermerk: dieselbe Datenbank ergibt mit den Vorgabeschwellen ein
    anderes Bild.

    Die Meldung steht jetzt in core/werkzeug_konfig.konfig_laden(); die
    ausfuehrliche Begruendung fuer die Zusammenfuehrung steht dort. Der
    Rueckgabewert ist unveraendert: der ConfigLoader oder None.
    """
    return werkzeug_konfig.konfig_laden(
        "overload_admin", args, folge="Vorgabe-Schwellen werden verwendet")


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
    der Abbruch mit dem Praefix '[overload_admin]' - nur nennt die Meldung jetzt
    BEIDE Wege statt nur einen. Die Meldung ueber eine unlesbare config.yaml
    gibt weiterhin _load_config aus; cfg ist dann None.
    """
    return werkzeug_konfig.db_pfad(
        "overload_admin", args, arg_attribut="coordinator_db",
        arg_name="--coordinator-db", config_schluessel="paths.coordinator_db",
        name="coordinator_db", r=werkzeug_konfig.resolver_aus_loader(cfg))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="overload_admin",
        description="Aktive Ueberlastwarnung je Ermittler (nur lesend).",
        epilog=cli_epilog.epilog("overload_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)
    thresholds = overload_thresholds_from_config(cfg)

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        report = OverloadEvaluator(con).evaluate(
            thresholds=thresholds, now=int(time.time()))
    finally:
        con.close()

    if args.json:
        print(json.dumps(overload_to_dict(report), ensure_ascii=False, indent=2))
        return 0

    print("Ueberlastwarnung (Grenzen: aktive<=%d, rote<=%d, Rueckstau-Alarm>=%d)"
          % (report.max_active_cases, report.max_red_cases, report.backlog_alert))
    print("  overload: %d | warn: %d | Rueckstau: %d%s"
          % (report.overloaded_count, report.warned_count, report.backlog_size,
             "  ALARM" if report.backlog_alarm else ""))
    for a in report.assessments:
        mark = {"overload": "!!", "warn": "! ", "ok": "  "}[a.level]
        print("  %s %-24s aktiv=%d rot=%d %s"
              % (mark, a.name, a.active_cases, a.red_cases,
                 ("(" + "; ".join(a.reasons) + ")") if a.reasons else ""))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

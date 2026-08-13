# =============================================================================
# management/stats/forecast_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-2C)
# =============================================================================
# Zweck:
#   NUR-LESENDE CLI fuer die Backlog-Abbau-Prognose (management.stats.forecast).
#   Gibt die drei Szenarien samt OFFENGELEGTER Annahmen aus (Konsole oder JSON).
#   Die Sicht/PDF-Ausgabe folgt in spaeteren AP-2C-Builds.
#
#   python -m management.stats.forecast_admin [--coordinator-db PATH]
#          [--config ./config.yaml] [--lookback-days 30] [--json]
#          [--no-capacity]
#
# Version: v0.8.718 · Build: 718 · 2026-08-13
# =============================================================================

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

from management.stats.forecast import Forecaster, forecast_to_dict
from management.help import cli_epilog  # noqa: E402
# Build 644: die Vorrangregel Argument > config.yaml > Vorgabewert
# steht seit Build 643 an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402


def _load_config(args):
    """
    Laedt die config.yaml und MELDET ihren Ausfall auf stderr.

    TICKET cf791ef0 (Build 718): Bis hierher stand an dieser Stelle eine
    Abschrift mit 'except Exception: return None' - OHNE Ausgabe. Faellt
    die Konfiguration aus, bleiben nur die Angaben von der Befehlszeile.
    Das war ein still uebersprungener Beleg (Grundregel 1). Ohne '--
    coordinator-db' folgt gleich danach der Abbruch; die Meldung nennt dann
    die Ursache, die der Abbruch allein nicht nennt.

    Die Meldung steht jetzt in core/werkzeug_konfig.konfig_laden(); die
    ausfuehrliche Begruendung fuer die Zusammenfuehrung steht dort. Der
    Rueckgabewert ist unveraendert: der ConfigLoader oder None.
    """
    return werkzeug_konfig.konfig_laden(
        "forecast_admin", args,
        folge="es gelten nur die Angaben von der Befehlszeile")


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
    der Abbruch mit dem Praefix '[forecast_admin]' - nur nennt die Meldung jetzt
    BEIDE Wege statt nur einen. Die Meldung ueber eine unlesbare config.yaml
    gibt weiterhin _load_config aus; cfg ist dann None.
    """
    return werkzeug_konfig.db_pfad(
        "forecast_admin", args, arg_attribut="coordinator_db",
        arg_name="--coordinator-db", config_schluessel="paths.coordinator_db",
        name="coordinator_db", r=werkzeug_konfig.resolver_aus_loader(cfg))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="forecast_admin",
        description="Backlog-Abbau-Prognose (3 Szenarien, transparent).",
        epilog=cli_epilog.epilog("forecast_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--lookback-days", type=int, default=30)
    p.add_argument("--no-capacity", action="store_true",
                   help="Kapazitaets-Kontext nicht ermitteln.")
    p.add_argument("--json", action="store_true", help="Als JSON ausgeben.")
    args = p.parse_args(argv)

    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)
    now_ts = int(time.time())

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        result = Forecaster(con).compute(
            now_ts=now_ts, lookback_days=args.lookback_days,
            include_capacity=not args.no_capacity)
    finally:
        con.close()

    if args.json:
        print(json.dumps(forecast_to_dict(result), ensure_ascii=False, indent=2))
        return 0

    print("Backlog-Abbau-Prognose (Stand %s)" % result.now_day)
    print("  Backlog: %d offene Faelle | beobachtete Rate: %.4f Faelle/Tag "
          "(%d Abschluesse / %d Tage)"
          % (result.backlog, result.observed_rate_per_day,
             result.completions_observed, result.lookback_days))
    if not result.data_sufficient:
        print("  ! Keine beobachteten Abschluesse — keine belastbare Prognose.")
    print("  Szenarien:")
    for s in result.scenarios:
        dtc = "%d Tage" % s.days_to_clear if s.days_to_clear is not None else "unbestimmt"
        fin = s.finish_day or "-"
        print("    %-14s x%.2f  %.4f/Tag  Restdauer %s  Fertig %s"
              % (s.name, s.factor, s.rate_per_day, dtc, fin))
    print("  Annahmen:")
    for a in result.assumptions:
        print("    - %s" % a)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

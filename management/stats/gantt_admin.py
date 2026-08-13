# =============================================================================
# management/stats/gantt_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-2C)
# =============================================================================
# Zweck:
#   NUR-LESENDE CLI fuer das Gantt-Read-Model (management.stats.gantt). Gibt die
#   Ermittler-Spuren mit ihren Fall-Balken aus (Konsole oder JSON). Die ECharts-
#   Sicht folgt in einem spaeteren AP-2C-Build.
#
#   python -m management.stats.gantt_admin [--coordinator-db PATH]
#          [--config ./config.yaml] [--json]
#
# Version: v0.8.718 · Build: 718 · 2026-08-13
# =============================================================================

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone

from management.stats.gantt import GanttModel, gantt_to_dict
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
        "gantt_admin", args,
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
    der Abbruch mit dem Praefix '[gantt_admin]' - nur nennt die Meldung jetzt
    BEIDE Wege statt nur einen. Die Meldung ueber eine unlesbare config.yaml
    gibt weiterhin _load_config aus; cfg ist dann None.
    """
    return werkzeug_konfig.db_pfad(
        "gantt_admin", args, arg_attribut="coordinator_db",
        arg_name="--coordinator-db", config_schluessel="paths.coordinator_db",
        name="coordinator_db", r=werkzeug_konfig.resolver_aus_loader(cfg))


def _fmt(ts) -> str:
    if ts is None:
        return "-"
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="gantt_admin",
        description="Gantt-Read-Model (Fall-Balken je Ermittler, nur lesend).",
        epilog=cli_epilog.epilog("gantt_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)
    now_ts = int(time.time())

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        result = GanttModel(con).build(now_ts=now_ts)
    finally:
        con.close()

    if args.json:
        print(json.dumps(gantt_to_dict(result), ensure_ascii=False, indent=2))
        return 0

    print("Gantt-Uebersicht: %d Balken, Zeitraum %s .. %s"
          % (result.total_bars, _fmt(result.range_start), _fmt(result.range_end)))
    for lane in result.lanes:
        print("  Spur: %s (%d)" % (lane.assignee_name, len(lane.bars)))
        for b in lane.bars:
            marker = "…laufend" if b.ongoing else "abgeschlossen"
            print("    Fall %d (%s) [%s] %s .. %s  %s"
                  % (b.subject_id, b.username, b.status,
                     _fmt(b.start_ts), _fmt(b.end_ts), marker))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

# =============================================================================
# management/cases/next_actions_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fallsteuerung (AP-2F)
# =============================================================================
# Zweck:
#   NUR-LESENDE CLI fuer die "naechstbeste Aktion"-Warteschlange.
#
#   python -m management.cases.next_actions_admin
#          [--coordinator-db PATH] [--config ./config.yaml]
#          [--scope alle|eigene] [--person-id N] [--json]
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import argparse
import json
import sqlite3
import sys
import time

from management.cases.next_actions import queue_to_dict
from management.cases.next_actions_repo import NextActionsRepo
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
    der Abbruch mit dem Praefix '[next_actions_admin]' - nur nennt die Meldung jetzt
    BEIDE Wege statt nur einen. Die Meldung ueber eine unlesbare config.yaml
    gibt weiterhin _load_config aus; cfg ist dann None.
    """
    return werkzeug_konfig.db_pfad(
        "next_actions_admin", args, arg_attribut="coordinator_db",
        arg_name="--coordinator-db", config_schluessel="paths.coordinator_db",
        name="coordinator_db", r=werkzeug_konfig.resolver_aus_loader(cfg))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="next_actions_admin",
        description="Naechstbeste-Aktion-Warteschlange (nur lesend).",
        epilog=cli_epilog.epilog("next_actions_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--scope", choices=["alle", "eigene"], default="alle")
    p.add_argument("--person-id", type=int, default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        result = NextActionsRepo(con).compute(
            scope=args.scope, person_id=args.person_id, now=int(time.time()))
    finally:
        con.close()

    if args.json:
        print(json.dumps(queue_to_dict(result), ensure_ascii=False, indent=2))
        return 0

    print("Naechstbeste Aktionen (scope %s): %d von %d Faellen offen, %d "
          "abgeschlossen." % (result.scope, result.actionable,
                              result.total_cases, result.done_excluded))
    mark = {"dringend": "!!", "bald": "! ", "routine": "  "}
    for a in result.items:
        print("  %s [P%d %s] Fall %d (%s): %s — %s"
              % (mark.get(a.urgency, "  "), a.priority, a.ampel, a.subject_id,
                 a.username, a.action, a.reason))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

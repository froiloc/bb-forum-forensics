# =============================================================================
# management/ops/retention_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Betrieb/Governance (AP-2G)
# =============================================================================
# Zweck:
#   NUR-LESENDE CLI fuer die Aufbewahrungs-/Loeschfristen-Uebersicht. Weist
#   Kandidaten zur LOESCHPRUEFUNG aus — loescht NICHTS.
#
#   python -m management.ops.retention_admin
#          [--coordinator-db PATH] [--config ./config.yaml]
#          [--retention-days N] [--json]
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone

from management.ops.retention import (
    RetentionRepo, RetentionThresholds, retention_thresholds_from_config,
    retention_to_dict,
)
from management.help import cli_epilog
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
    der Abbruch mit dem Praefix '[retention_admin]' - nur nennt die Meldung jetzt
    BEIDE Wege statt nur einen. Die Meldung ueber eine unlesbare config.yaml
    gibt weiterhin _load_config aus; cfg ist dann None.
    """
    return werkzeug_konfig.db_pfad(
        "retention_admin", args, arg_attribut="coordinator_db",
        arg_name="--coordinator-db", config_schluessel="paths.coordinator_db",
        name="coordinator_db", r=werkzeug_konfig.resolver_aus_loader(cfg))


def _fmt(ts) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="retention_admin",
        description="Aufbewahrungs-/Loeschfristen-Uebersicht (nur lesend, "
                    "loescht NICHTS).",
        epilog=cli_epilog.epilog("retention_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--retention-days", type=int, default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)
    thresholds = retention_thresholds_from_config(cfg)
    if args.retention_days is not None:
        thresholds = RetentionThresholds(retention_days=args.retention_days)

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        report = RetentionRepo(con).compute(
            thresholds=thresholds, now=int(time.time()))
    finally:
        con.close()

    if args.json:
        print(json.dumps(retention_to_dict(report), ensure_ascii=False, indent=2))
        return 0

    print("Aufbewahrung (Frist %d Tage): %d abgeschlossene Faelle, %d Kandidat(en) "
          "zur Loeschpruefung%s"
          % (report.retention_days, report.closed_cases, report.candidate_count,
             (", %d ohne Fristbezug" % report.without_reference)
             if report.without_reference else ""))
    for c in report.candidates:
        print("  Fall %d (%s) [%s] Abschluss %s (%s) — %d Tage aufbewahrt "
              "(%d ueber Frist)"
              % (c.subject_id, c.username, c.status, _fmt(c.reference_ts),
                 c.reference_field, c.days_retained, c.over_by_days))
    if not report.candidates:
        print("  (kein Kandidat)")
    print("  HINWEIS: Dies ist nur ein Pruefvorschlag. Loeschen ist eine "
          "auditierte Governance-Entscheidung.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

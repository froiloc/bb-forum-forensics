# =============================================================================
# management/stats/annotation_stats_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-2D)
# =============================================================================
# Zweck:
#   NUR-LESENDE CLI fuer die Annotations-Tortenstatistik
#   (management.stats.annotation_stats_repo). Aggregiert Annotationen der Faelle
#   nach Kategorie und Tag (Konsole oder JSON). Die ECharts-Torten-Sicht folgt
#   in B450.
#
#   python -m management.stats.annotation_stats_admin
#          [--coordinator-db PATH] [--evidence-dir DIR] [--config ./config.yaml]
#          [--scope alle|eigene] [--person-id N] [--json]
#
# Version: v0.7.449 · Build: 449 · 2026-07-19
# =============================================================================

import argparse
import json
import sqlite3
import sys
import time

from management.stats.annotation_stats_repo import AnnotationStatsRepo
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
    der Abbruch mit dem Praefix '[annotation_stats_admin]' - nur nennt die Meldung jetzt
    BEIDE Wege statt nur einen. Die Meldung ueber eine unlesbare config.yaml
    gibt weiterhin _load_config aus; cfg ist dann None.
    """
    return werkzeug_konfig.db_pfad(
        "annotation_stats_admin", args, arg_attribut="coordinator_db",
        arg_name="--coordinator-db", config_schluessel="paths.coordinator_db",
        name="coordinator_db", r=werkzeug_konfig.resolver_aus_loader(cfg))


def _resolve_evidence_dir(args, cfg) -> str:
    """
    Verzeichnis der evidence_<uid>.db: Argument --evidence-dir >
    paths.evidence_db_dir > './data/evidence/'.

    BUILD 644: dieselbe Aufloesung wie oben, aber ueber 'wert' statt
    'db_pfad' - und der Unterschied ist betrieblich und nicht kosmetisch:
    Hier GIBT es einen Vorgabewert, hier wird also NICHT abgebrochen. Wer
    beide Faelle durch dieselbe Funktion schickte, saehe am Aufruf nicht
    mehr, welcher von beiden vorliegt.
    """
    return werkzeug_konfig.wert(
        "annotation_stats_admin", args, arg_attribut="evidence_dir",
        arg_name="--evidence-dir", config_schluessel="paths.evidence_db_dir",
        default="./data/evidence/", name="evidence_dir", wandler=str,
        r=werkzeug_konfig.resolver_aus_loader(cfg))

def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="annotation_stats_admin",
        description="Annotations-Tortenstatistik (Kategorie/Tag, nur lesend).",
        epilog=cli_epilog.epilog("annotation_stats_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--evidence-dir", default=None)
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--scope", choices=["alle", "eigene"], default="alle")
    p.add_argument("--person-id", type=int, default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)
    evidence_dir = _resolve_evidence_dir(args, cfg)

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        result = AnnotationStatsRepo(con, evidence_dir).compute(
            scope=args.scope, person_id=args.person_id, now=int(time.time()))
    finally:
        con.close()

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print("Annotations-Statistik (scope %s)" % result["scope"])
    print("  Faelle: %d (mit evidence: %d, ohne: %d) | Annotationen: %d"
          % (result["cases_total"], result["cases_with_evidence"],
             result["cases_without_evidence"], result["annotations_total"]))
    print("  Nach Kategorie:")
    for e in result["by_category"]:
        print("    %-24s %d" % (e["key"], e["count"]))
    print("  Nach Tag:")
    for e in result["by_tag"]:
        print("    %-24s %d" % (e["key"], e["count"]))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

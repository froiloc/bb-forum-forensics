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


def _load_config(args):
    try:
        from core.config_loader import ConfigLoader
        return ConfigLoader(config_path=args.config)
    except Exception:  # pragma: no cover
        return None


def _resolve_db_path(args, cfg) -> str:
    if args.coordinator_db:
        return args.coordinator_db
    if cfg is not None:
        try:
            p = cfg.get("paths", {}).get("coordinator_db")
            if p:
                return str(p)
        except Exception:  # pragma: no cover
            pass
    raise SystemExit("[annotation_stats] Kein coordinator.db-Pfad "
                     "(--coordinator-db oder paths.coordinator_db).")


def _resolve_evidence_dir(args, cfg) -> str:
    if args.evidence_dir:
        return args.evidence_dir
    if cfg is not None:
        try:
            p = cfg.get("paths", {}).get("evidence_db_dir")
            if p:
                return str(p)
        except Exception:  # pragma: no cover
            pass
    return "./data/evidence/"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="annotation_stats_admin",
        description="Annotations-Tortenstatistik (Kategorie/Tag, nur lesend).")
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

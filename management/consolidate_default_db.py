# =============================================================================
# management/consolidate_default_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management/Wartung
# =============================================================================
# Zweck:
#   Produktiver CLI-Einstiegspunkt zur VERLUSTFREIEN Konsolidierung mehrerer
#   (versehentlich pro Beschuldigtem angelegter) default.db-Dateien in EINE
#   zentrale default.db. Kern-Logik: management.maintenance.DefaultDbMerger.
#
# Aufruf:
#   python -m management.consolidate_default_db \
#       --target ./data/default.db \
#       --source /pfad/a/default.db --source /pfad/b/default.db \
#       [--sources-glob "outputs/*/default.db"] \
#       [--overwrite] [--allow-host-mismatch] \
#       [--report ./data/default.merge-report.txt] \
#       [--config ./config.yaml]
#
#   --target fehlt -> Fallback aus config.yaml (paths.default_db).
#   Der Abgleichbericht wird auf die Konsole und (append-only) in die
#   Report-Datei geschrieben; Herkunft zusätzlich in default_meta.merge_provenance.
#
# Exit-Codes: 0 = ok (auch mit aufgelösten Konflikten), 1 = harter Fehler.
#
# Beleg: Projektgespräch 2026-07-01 (mc), Analyse default.db-Konsolidierung.
# Version: v0.7.309 · Build: 309 · 2026-07-01
# =============================================================================

import argparse
import glob as _glob
import sys
import time
from pathlib import Path

from core.logger import get_logger
from management.maintenance.default_db_merger import DefaultDbMerger, MergeError

logger = get_logger(__name__)


def _resolve_target(args) -> str:
    if args.target:
        return args.target
    try:
        from core.config_loader import ConfigLoader
        cfg = ConfigLoader(config_path=args.config)
        path = cfg.get("paths.default_db")
        if path:
            return str(path)
    except Exception as exc:  # pragma: no cover — Konfig-Randfall
        print(f"[consolidate] config.yaml nicht lesbar: {exc}", file=sys.stderr)
    raise SystemExit(
        "[consolidate] Kein Ziel: --target angeben oder paths.default_db "
        "in config.yaml setzen."
    )


def _collect_sources(args) -> list:
    sources: list = list(args.source or [])
    for pattern in (args.sources_glob or []):
        sources.extend(sorted(_glob.glob(pattern)))
    # Reihenfolge egal (Merger sortiert nach recency), aber Duplikate raus.
    seen: set = set()
    unique: list = []
    for s in sources:
        rp = str(Path(s).resolve())
        if rp not in seen:
            seen.add(rp)
            unique.append(s)
    return unique


def _write_report_file(report_path: Path, text: str) -> None:
    """Append-only: bestehende Berichte bleiben erhalten (Nachvollziehbarkeit)."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    header = f"\n\n### Lauf {time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime())} ###\n"
    with report_path.open("a", encoding="utf-8") as fh:
        fh.write(header)
        fh.write(text)
        fh.write("\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Konsolidiert mehrere default.db verlustfrei in eine zentrale."
    )
    parser.add_argument("--target", help="Ziel-default.db (Fallback: config.yaml)")
    parser.add_argument("--source", action="append", metavar="PATH",
                        help="Quell-default.db (mehrfach angebbar)")
    parser.add_argument("--sources-glob", action="append", metavar="GLOB",
                        help="Glob-Muster für Quellen (mehrfach angebbar)")
    parser.add_argument("--overwrite", action="store_true",
                        help="Bestehendes Ziel neu aufbauen")
    parser.add_argument("--allow-host-mismatch", action="store_true",
                        help="Divergierende protocol/domainname bewusst zulassen")
    parser.add_argument("--report", help="Pfad für den Abgleichbericht (append-only)")
    parser.add_argument("--config", default="./config.yaml",
                        help="config.yaml (Fallback für --target)")
    args = parser.parse_args(argv)

    target = _resolve_target(args)
    sources = _collect_sources(args)
    if not sources:
        print("[consolidate] Keine Quellen angegeben (--source/--sources-glob).",
              file=sys.stderr)
        return 1

    print(f"[consolidate] Ziel:    {target}")
    print(f"[consolidate] Quellen: {len(sources)}")

    try:
        merger = DefaultDbMerger(
            target_path=Path(target),
            source_paths=[Path(s) for s in sources],
            overwrite=args.overwrite,
            allow_host_mismatch=args.allow_host_mismatch,
        )
        report = merger.run()
    except MergeError as exc:
        print(f"[consolidate] ABBRUCH: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover — unerwarteter Randfall
        logger.exception("Unerwarteter Fehler bei der Konsolidierung")
        print(f"[consolidate] Unerwarteter Fehler: {exc}", file=sys.stderr)
        return 1

    text = report.as_text()
    print(text)
    if args.report:
        _write_report_file(Path(args.report), text)
        print(f"[consolidate] Bericht angehängt: {args.report}")

    if report.conflicts:
        print(f"[consolidate] Hinweis: {len(report.conflicts)} Konflikt(e) "
              "aufgelöst (neueste Quelle gewinnt) — siehe Bericht/Log.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

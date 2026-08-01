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
# WARTUNGSVORBEHALT — STUFE A (Build 612):
#   Mit --overwrite wird die vorhandene Ziel-Datei GELOESCHT, BEVOR die
#   Transaktion beginnt; ein Abbruch danach laesst gar keine default.db
#   zurueck, und ein Backup legt das Werkzeug nicht an. Es prueft deshalb vor
#   dem Lauf Ziel UND Quellen auf Ruhe und faehrt ohne aktives
#   Wartungsfenster nur nach Eingabe eines vollstaendigen Wortes fort
#   (maintenance/wartungsvorbehalt.py). Einstufung:
#   Vermerk_Wartungsvorbehalt_Analyse_K1_K8_v1_0.md, von mc bestaetigt am
#   2026-07-31.
#
# Exit-Codes: 0 = ok (auch mit aufgelösten Konflikten) · 1 = harter Fehler
#             3 = Wartungsvorbehalt, es wurde NICHTS geschrieben.
#
# Beleg: Projektgespräch 2026-07-01 (mc), Analyse default.db-Konsolidierung.
# Version: v0.8.612 · Build: 612 · 2026-07-31
# =============================================================================

import argparse
import glob as _glob
import sys
import time
from pathlib import Path

from core.logger import get_logger
from management.maintenance.default_db_merger import DefaultDbMerger, MergeError
from maintenance.wartungsvorbehalt import (            # NEU Build 612
    datenwurzel, wartungsvorbehalt,
)
from management.help import cli_epilog  # noqa: E402
# Build 646: Vorrangregel an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402

logger = get_logger(__name__)


def _resolve_target(args) -> str:
    """
    Ziel-default.db: Argument --target > paths.default_db > Abbruch.

    BUILD 646: Aufloesung in core/werkzeug_konfig.py, Verhalten unveraendert.
    Kein Vorgabewert - dieses Werkzeug FUEHRT ZUSAMMEN, und ein erratenes
    Ziel waere hier besonders teuer.
    """
    return werkzeug_konfig.db_pfad(
        "consolidate", args, arg_attribut="target", arg_name="--target",
        config_schluessel="paths.default_db", name="default_db")

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
        description="Konsolidiert mehrere default.db verlustfrei in eine zentrale.",
        epilog=cli_epilog.epilog("consolidate_default_db"),
        formatter_class=cli_epilog.HilfeFormat,
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

    # --- WARTUNGSVORBEHALT (Stufe A, Build 612) --------------------------
    # Zwei Gruende, und der erste allein genuegt: Mit --overwrite wird die
    # vorhandene Ziel-Datei GELOESCHT, BEVOR die Transaktion beginnt. Bricht
    # der Lauf danach ab, holt das Zurueckrollen sie nicht wieder — es bleibt
    # gar keine default.db (Befund 2 des Vermerks, eigener Vorgang).
    #
    # GEPRUEFT WIRD AUCH AUF DIE QUELLEN, obwohl sie nur gelesen werden: Eine
    # Quelle, die waehrend des Lesens beschrieben wird, ergibt eine
    # zusammengefuehrte Datei, die niemandem auffaellt und trotzdem falsch
    # ist. Ein Fehlalarm kostet einen zweiten Anlauf; ein stiller Fehlgriff
    # kostet Vertrauen in die Vorlagen, die die Ermittelnden sehen.
    befund = wartungsvorbehalt(
        datenwurzel(target), [target] + list(sources),
        werkzeug="consolidate_default_db",
        was_geschieht=("fuehrt %d Quell-default.db in %s zusammen%s"
                       % (len(sources), target,
                          "; die vorhandene Ziel-Datei wird dabei ZUVOR "
                          "geloescht (--overwrite) und es gibt kein Backup"
                          if args.overwrite else "")))
    print(befund.text)
    if not befund.erlaubt:
        return befund.rueckgabewert

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

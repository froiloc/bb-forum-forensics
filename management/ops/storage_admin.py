# =============================================================================
# management/ops/storage_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Betrieb/Systemzustand (AP-2G)
# =============================================================================
# Zweck:
#   NUR-LESENDE CLI fuer die Speicher-/data/-Uebersicht. Pfade aus config.yaml
#   (paths.*), sonst Vorgaben. Zeigt Kategorien, Fremdforum-Kandidaten und den
#   freien Plattenplatz (inkl. Low-Disk-Alarm).
#
#   python -m management.ops.storage_admin [--config ./config.yaml]
#          [--forensic-dir D] [--evidence-dir D] [--assets-dir D] [--json]
#
# Version: v0.7.454 · Build: 454 · 2026-07-19
# =============================================================================

import argparse
import json
import sys
import time

from management.ops.storage_overview import StorageOverview, storage_to_dict
from management.help import cli_epilog
# Build 645: Vorrangregel an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402


def _pfad(args, r, key, default):
    """
    Ein Verzeichnis bzw. eine Datei aus 'paths.<key>' - mit Vorgabewert.

    BUILD 645: Frueher '_cfg_get(cfg, key, default)'. Es las
    cfg.get("paths", {}).get(key, default) und griff damit auch auf die Coded
    Defaults des ConfigLoaders durch. GEPRUEFT: Fuer alle sechs hier
    verwendeten Schluessel sind die Coded Defaults ZEICHENGLEICH mit den
    Vorgabewerten, die dieses Werkzeug selbst mitbringt - das Ergebnis ist
    also dasselbe. Die Herkunftsangabe ist es NICHT: 'aus config.yaml' waere
    dort falsch gewesen, wo nur ein fest verdrahteter Wert gegriffen hat.

    DIESES WERKZEUG BRICHT NIE AB. Es soll sagen, was der Bestand belegt;
    ein fehlender Eintrag ist dafuer kein Grund aufzuhoeren.
    """
    return werkzeug_konfig.wert(
        "storage_admin", args, arg_attribut="(nicht ueber ein Argument)",
        arg_name="(kein Argument)", config_schluessel="paths." + key,
        default=default, name=key, wandler=str, r=r)

def _human(n):
    if n is None:
        return "-"
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    f = float(n)
    for u in units:
        if f < 1024 or u == units[-1]:
            return "%.1f %s" % (f, u)
        f /= 1024


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="storage_admin",
        description="Speicher-/data/-Uebersicht (Systemzustand, nur lesend).",
        epilog=cli_epilog.epilog("storage_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--forensic-dir", default=None)
    p.add_argument("--evidence-dir", default=None)
    p.add_argument("--assets-dir", default=None)
    p.add_argument("--low-disk-pct", type=float, default=10.0)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    # Build 645: EIN Aufloeser fuer alle sechs Pfade - eine Lesung der Datei.
    r = werkzeug_konfig.resolver(args)

    forensic = args.forensic_dir or _pfad(args, r, "forensic_db_dir", "./data/forensic/")
    evidence = args.evidence_dir or _pfad(args, r, "evidence_db_dir", "./data/evidence/")
    assets = args.assets_dir or _pfad(args, r, "assets_db_dir", "./data/assets/")
    extra = [
        _pfad(args, r, "coordinator_db", "./data/coordinator.db"),
        _pfad(args, r, "default_db", "./data/default.db"),
        _pfad(args, r, "templates_db", "./data/templates.db"),
    ]

    ov = StorageOverview(forensic_dir=forensic, evidence_dir=evidence,
                         assets_dir=assets, extra_files=extra,
                         low_disk_pct=args.low_disk_pct)
    report = ov.scan(now=int(time.time()))

    if args.json:
        print(json.dumps(storage_to_dict(report), ensure_ascii=False, indent=2))
        return 0

    print("Speicheruebersicht (gesamt %s)" % _human(report.total_bytes))
    for c in report.categories:
        print("  %-14s %-40s %s (%d Dateien)%s"
              % (c.name, c.path, _human(c.total_bytes), c.file_count,
                 "" if c.exists else "  [fehlt]"))
    print("  Faelle: %d | Fremdforum-Kandidaten (forensic ohne evidence): %d%s"
          % (len(report.per_case), len(report.fremdforum_candidates),
             (" -> " + ", ".join(map(str, report.fremdforum_candidates)))
             if report.fremdforum_candidates else ""))
    print("  Platte: frei %s von %s (%.2f%%)%s"
          % (_human(report.disk_free), _human(report.disk_total),
             report.disk_free_pct if report.disk_free_pct is not None else 0.0,
             "  LOW-DISK-ALARM" if report.low_disk_alert else ""))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

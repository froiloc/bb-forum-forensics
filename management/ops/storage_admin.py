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


def _cfg_get(cfg, key, default):
    if cfg is None:
        return default
    try:
        node = cfg.get("paths", {}) or {}
        return str(node.get(key, default))
    except Exception:  # pragma: no cover
        return default


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
        description="Speicher-/data/-Uebersicht (Systemzustand, nur lesend).")
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--forensic-dir", default=None)
    p.add_argument("--evidence-dir", default=None)
    p.add_argument("--assets-dir", default=None)
    p.add_argument("--low-disk-pct", type=float, default=10.0)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    try:
        from core.config_loader import ConfigLoader
        cfg = ConfigLoader(config_path=args.config)
    except Exception:
        cfg = None

    forensic = args.forensic_dir or _cfg_get(cfg, "forensic_db_dir", "./data/forensic/")
    evidence = args.evidence_dir or _cfg_get(cfg, "evidence_db_dir", "./data/evidence/")
    assets = args.assets_dir or _cfg_get(cfg, "assets_db_dir", "./data/assets/")
    extra = [
        _cfg_get(cfg, "coordinator_db", "./data/coordinator.db"),
        _cfg_get(cfg, "default_db", "./data/default.db"),
        _cfg_get(cfg, "templates_db", "./data/templates.db"),
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

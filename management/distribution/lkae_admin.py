# =============================================================================
# management/distribution/lkae_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: LKAe-Distribution (AP-2G)
# =============================================================================
# Zweck:
#   CLI fuer das LKAe-Demo-Paket (Idee 27). BETRIEBSWEG (kein Cockpit-Feature —
#   das Paket wird ausserhalb des Live-Systems gebaut, NICHT PROD).
#
#   Aufruf:  python -m management.distribution.lkae_admin <befehl> [...]
#
#     build   --target DIR --freigabe "<Name/Az>" [--actor KENNUNG]
#             [--config ./config.yaml] [--no-docker]
#     verify  --target DIR
#
#   'build' liest die PROD-Datenpfade aus config.yaml (paths.*) und VERWEIGERT,
#   wenn das Ziel eine PROD-Ablage ueberlappt (NICHT PROD). Ohne --freigabe kein
#   Bau (default-deny). EXIT: 0 = ok · 1 = Fehler · 2 = verify: Abweichung.
#
# Version: v0.7.466 · Build: 466 · 2026-07-20
# =============================================================================

import argparse
import logging
import sys
from typing import List, Optional

from management.distribution import lkae_dist
from management.distribution.lkae_dist import LkaeDistributionError
from management.help import cli_epilog  # noqa: E402

logger = logging.getLogger(__name__)


def _prod_paths(config_path: str) -> List[str]:
    """PROD-Datenpfade aus config.yaml (best effort; leer bei Ausfall)."""
    keys = ("paths.coordinator_db", "paths.evidence_db_dir",
            "paths.forensic_db_dir", "paths.assets_db_dir",
            "paths.templates_db", "paths.default_db")
    out: List[str] = []
    try:
        from core.config_loader import ConfigLoader
        cfg = ConfigLoader(config_path=config_path)
        for k in keys:
            v = cfg.get(k)
            if v:
                out.append(str(v))
    except Exception as exc:  # pragma: no cover
        print("[lkae_admin] config.yaml nicht lesbar (%s) — PROD-Pfad-Schutz "
              "nur ueber Standardpfade." % exc, file=sys.stderr)
        out.extend(["./data/coordinator.db", "./data/"])
    return out


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ap = argparse.ArgumentParser(
        prog="lkae_admin",
        description="LKAe-Demo-Paket bauen/pruefen (NICHT PROD).",
        epilog=cli_epilog.epilog("lkae_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("build", help="Demo-Paket bauen")
    p.add_argument("--target", required=True, help="frisches Zielverzeichnis")
    p.add_argument("--freigabe", required=True,
                   help="Freigabe-Vermerk (Pflicht, Name/Az)")
    p.add_argument("--actor", default=None)
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--no-docker", action="store_true",
                   help="ohne Dockerfile im Paket")

    p = sub.add_parser("verify", help="Demo-Paket gegen Manifest pruefen")
    p.add_argument("--target", required=True)

    args = ap.parse_args(argv)

    try:
        if args.cmd == "build":
            res = lkae_dist.build(
                target_dir=args.target, freigabe=args.freigabe,
                actor=args.actor,
                prod_data_paths=_prod_paths(args.config),
                include_docker=not args.no_docker)
            print("Demo-Paket gebaut: %s (%d Dateien, Manifest-Digest %s)."
                  % (res["target"], res["file_count"],
                     res["manifest_digest"][:16]))
            print("Demo-Inhalt:", res["seed_summary"])
            return 0

        if args.cmd == "verify":
            res = lkae_dist.verify(args.target)
            if res["ok"]:
                print("OK — %d Dateien stimmen mit dem Manifest ueberein."
                      % res["file_count"])
                return 0
            print("ABWEICHUNG:", file=sys.stderr)
            for rel in res["mismatch"]:
                print("  geaendert: %s" % rel, file=sys.stderr)
            for rel in res["missing"]:
                print("  fehlt:     %s" % rel, file=sys.stderr)
            for rel in res["extra"]:
                print("  zusaetzl.: %s" % rel, file=sys.stderr)
            return 2

        ap.error("Unbekannter Befehl.")
        return 1

    except LkaeDistributionError as exc:
        print("FEHLER: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

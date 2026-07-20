# =============================================================================
# management/reports/seal_check.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Berichts-Versiegelung
# =============================================================================
# seal_check — prueft ALLE zentral hinterlegten Siegel (approved_reports.db)
# gegen den aktuellen Inhalt der jeweiligen evidence_<uid>.db.
#
# ZWECK: Das Siegel (Build 377) weist eine Manipulation NACHTRAEGLICH nach. Die
#   Schreibsperre (Build 379) verhindert sie kuenftig ueber den normalen Weg.
#   Fuer BESTEHENDE Daten — und als wiederkehrende Kontrolle — braucht es einen
#   Befehl, der die Siegel in einem Durchgang nachrechnet. Genau das ist dies.
#
#   Eine ABWEICHUNG bedeutet: der Berichtsinhalt hat sich nach der Freigabe
#   geaendert. Das ist ein Manipulationsverdacht und muss geprueft werden.
#
# Aufruf:
#   python -m management.reports.seal_check [--config ./config.yaml]
#                                           [--evidence-dir DIR]
#                                           [--approved-db PATH]
#
# Exit-Codes: 0 = alle Siegel in Ordnung (oder keine Siegel vorhanden)
#             2 = mindestens eine ABWEICHUNG oder ein nicht pruefbarer Bericht
#             1 = Aufruf-/Konfigurationsfehler
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from management.reports.approved_reports_db import ApprovedReportsDb
from management.reports.report_sealer import ReportSealer, ReportSealError


def _resolve(args) -> tuple:
    if args.evidence_dir and args.approved_db:
        return args.evidence_dir, args.approved_db
    try:
        from core.config_loader import ConfigLoader
        cfg = ConfigLoader(config_path=args.config)
        ev = args.evidence_dir or str(cfg.get("paths.evidence_db_dir"))
        ap = args.approved_db or str(cfg.get("paths.approved_reports_db"))
        return ev, ap
    except Exception as exc:
        print("[seal_check] config.yaml nicht lesbar: %s" % exc,
              file=sys.stderr)
        raise


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m management.reports.seal_check",
        description="Prueft alle Berichts-Siegel gegen die evidence-DBs.")
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--evidence-dir", default=None)
    p.add_argument("--approved-db", default=None)
    args = p.parse_args(argv)

    try:
        evidence_dir, approved_db = _resolve(args)
    except Exception:
        return 1

    seals = ApprovedReportsDb(approved_db).list_seals()
    if not seals:
        print("[seal_check] Keine Siegel vorhanden (kein Bericht freigegeben).")
        print("[seal_check] Siegel-DB: %s" % approved_db)
        return 0

    ok = 0
    bad: List[str] = []
    unreadable: List[str] = []

    print("[seal_check] Pruefe %d Siegel gegen %s ..."
          % (len(seals), evidence_dir))
    for s in seals:
        uid, rid = s["subject_id"], s["report_id"]
        ev = Path(evidence_dir) / ("evidence_%d.db" % uid)
        label = "Fall %s / Bericht %s (%s)" % (uid, rid, s["title"])
        try:
            current = ReportSealer(ev).content_hash(rid)
        except ReportSealError as exc:
            unreadable.append("%s: %s" % (label, exc))
            print("  ?  %s — NICHT PRUEFBAR: %s" % (label, exc))
            continue

        if current == s["content_sha256"]:
            ok += 1
            print("  OK %s — Siegel in Ordnung (%s...)"
                  % (label, s["content_sha256"][:12]))
        else:
            bad.append(label)
            print("  !! %s — ABWEICHUNG!" % label)
            print("       Siegel  : %s" % s["content_sha256"])
            print("       Aktuell : %s" % current)
            print("       Freigabe: %s, Beleg #%s"
                  % (s["approved_by"], s["audit_seq"]))

    print("")
    print("[seal_check] %d in Ordnung, %d ABWEICHUNG(EN), %d nicht pruefbar."
          % (ok, len(bad), len(unreadable)))

    if bad or unreadable:
        bar = "!" * 72
        print(bar, file=sys.stderr)
        if bad:
            print("!! MANIPULATIONSVERDACHT: %d Bericht(e) weichen vom "
                  "versiegelten Stand ab." % len(bad), file=sys.stderr)
            for b in bad:
                print("!!   - %s" % b, file=sys.stderr)
        if unreadable:
            print("!! %d Bericht(e) NICHT PRUEFBAR (Datenbank fehlt/defekt):"
                  % len(unreadable), file=sys.stderr)
            for u in unreadable:
                print("!!   - %s" % u, file=sys.stderr)
        print("!! Das versiegelte Abbild liegt vollstaendig in der Siegel-DB "
              "vor und", file=sys.stderr)
        print("!! kann zum Vergleich herangezogen werden.", file=sys.stderr)
        print(bar, file=sys.stderr)
        return 2

    print("[seal_check] Alle Siegel in Ordnung.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

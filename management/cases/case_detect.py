# =============================================================================
# management/cases/case_detect.py
# IT-Forensisches Ermittlungswerkzeug — Fall-Autodetektion (CLI)
# =============================================================================
# Gleicht die auf der Platte liegenden Faelle (forensic_<uid>.db) mit der
# Fallakte (coordinator.db -> cases) ab und meldet vier Zustaende:
#
#   ok         Fall erfasst und Datenbank vorhanden.
#   neu        Datenbank da, aber NICHT erfasst  -> aufnehmbar.
#   vermisst   erfasst, aber Datenbank FEHLT      -> pruefen!
#   unlesbar   Datenbank da, aber nicht lesbar    -> pruefen!
#
# Aufruf:
#   python -m management.cases.case_detect [--config ./config.yaml]
#                                          [--auto] [--actor KENNUNG]
#
#   Ohne --auto wird NUR berichtet (rein lesend). Mit --auto werden alle als
#   'neu' erkannten Faelle AUDITIERT aufgenommen (Beleg case_created je Fall) —
#   gedacht fuer Skripte; der Normalfall ist der Knopf im Cockpit (mc).
#
# Exit-Codes: 0 = nichts zu beanstanden
#             2 = 'vermisst' oder 'unlesbar' vorhanden (Pruefbedarf)
#             1 = Aufruf-/Konfigurationsfehler
#
# Version: v0.7.383 · Build: 383 · 2026-07-10
# =============================================================================

import argparse
import sqlite3
import sys
from typing import List, Optional

from management.cases.case_detector import (
    CaseDetector,
    STATUS_NEU,
    STATUS_OK,
    STATUS_UNLESBAR,
    STATUS_VERMISST,
)
from management.cases.case_importer import CaseImporter

_LABEL = {
    STATUS_OK: "OK      ",
    STATUS_NEU: "NEU     ",
    STATUS_VERMISST: "VERMISST",
    STATUS_UNLESBAR: "UNLESBAR",
}


def _resolve(args):
    from core.config_loader import ConfigLoader
    cfg = ConfigLoader(config_path=args.config)
    return (
        args.coordinator_db or str(cfg.get("paths.coordinator_db")),
        args.forensic_dir or str(cfg.get("paths.forensic_db_dir")),
        args.evidence_dir or str(cfg.get("paths.evidence_db_dir")),
        args.assets_dir or str(cfg.get("paths.assets_db_dir")),
    )


def _actor_id(con: sqlite3.Connection, username: str) -> Optional[int]:
    row = con.execute("SELECT id FROM person WHERE system_username = ?",
                      (username,)).fetchone()
    return int(row[0]) if row else None


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m management.cases.case_detect",
        description="Gleicht die Faelle auf der Platte mit der Fallakte ab.")
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--forensic-dir", default=None)
    p.add_argument("--evidence-dir", default=None)
    p.add_argument("--assets-dir", default=None)
    p.add_argument("--auto", action="store_true",
                   help="alle als 'neu' erkannten Faelle AUDITIERT aufnehmen")
    p.add_argument("--actor", default=None,
                   help="Kennung des Handelnden (Pflicht bei --auto)")
    args = p.parse_args(argv)

    try:
        coord, fdir, edir, adir = _resolve(args)
    except Exception as exc:
        print("[case_detect] config.yaml nicht lesbar: %s" % exc,
              file=sys.stderr)
        return 1

    if args.auto and not args.actor:
        print("[case_detect] --auto erfordert --actor <KENNUNG> "
              "(der Beleg braucht einen Handelnden).", file=sys.stderr)
        return 1

    # Ohne --auto genuegt eine Leseverbindung; mit --auto wird geschrieben.
    if args.auto:
        con = sqlite3.connect(coord)
        con.isolation_level = None
    else:
        con = sqlite3.connect("file:%s?mode=ro" % coord, uri=True)
    con.row_factory = sqlite3.Row

    try:
        detector = CaseDetector(con, fdir, edir, adir)
        report = detector.detect()

        print("[case_detect] Verzeichnis: %s" % report["forensic_dir"])
        print("[case_detect] %d Fall/Faelle abgeglichen."
              % report["count"])
        print("")
        for c in report["cases"]:
            arbeits = "".join([
                "E" if c["has_evidence_db"] else "-",
                "A" if c["has_assets_db"] else "-",
            ])
            line = "  %s uid=%-8s %-24s [%s]" % (
                _LABEL.get(c["status"], c["status"]), c["user_id"],
                (c["username"] or "(kein Benutzername)"), arbeits)
            if c["detail"]:
                line += "  -- %s" % c["detail"]
            print(line)

        cn = report["counts"]
        print("")
        print("[case_detect] ok=%d  neu=%d  vermisst=%d  unlesbar=%d"
              % (cn[STATUS_OK], cn[STATUS_NEU], cn[STATUS_VERMISST],
                 cn[STATUS_UNLESBAR]))
        print("[case_detect] (E = evidence-DB vorhanden, A = assets-DB "
              "vorhanden — reiner Arbeitsstand, kein Existenzkriterium.)")

        # --- optionales Aufnehmen -------------------------------------------
        if args.auto:
            actor_id = _actor_id(con, args.actor)
            if actor_id is None:
                print("[case_detect] Unbekannte Kennung: %s" % args.actor,
                      file=sys.stderr)
                return 1
            res = CaseImporter(con, detector).import_cases(
                actor_id=actor_id, all_new=True)
            print("")
            print("[case_detect] AUFNAHME (--auto): %d Fall/Faelle aufgenommen."
                  % res["count"])
            for i in res["imported"]:
                print("  + uid=%-8s %-24s Beleg #%s"
                      % (i["user_id"], i["username"], i["audit_seq"]))
            for sk in res["skipped"]:
                print("  ! uid=%-8s uebersprungen: %s"
                      % (sk["user_id"], sk["reason"]), file=sys.stderr)
        elif cn[STATUS_NEU]:
            print("")
            print("[case_detect] %d neue(r) Fall/Faelle koennen aufgenommen "
                  "werden — im Cockpit ('Fall-Erkennung') oder mit --auto "
                  "--actor <KENNUNG>." % cn[STATUS_NEU])

        # --- Pruefbedarf melden ---------------------------------------------
        if cn[STATUS_VERMISST] or cn[STATUS_UNLESBAR]:
            bar = "!" * 72
            print(bar, file=sys.stderr)
            if cn[STATUS_VERMISST]:
                print("!! %d Fall/Faelle sind in der Fallakte erfasst, aber "
                      "ihre forensic-Datenbank" % cn[STATUS_VERMISST],
                      file=sys.stderr)
                print("!! FEHLT auf der Platte. Die Fallakte wurde NICHT "
                      "veraendert (kein stiller", file=sys.stderr)
                print("!! Eingriff in Ermittlungsdaten) — bitte pruefen.",
                      file=sys.stderr)
            if cn[STATUS_UNLESBAR]:
                print("!! %d Datenbank(en) sind vorhanden, aber nicht lesbar "
                      "— bitte pruefen." % cn[STATUS_UNLESBAR],
                      file=sys.stderr)
            print(bar, file=sys.stderr)
            return 2

        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())

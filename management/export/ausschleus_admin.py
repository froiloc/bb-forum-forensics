# =============================================================================
# management/export/ausschleus_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem (AP-2B)
# =============================================================================
# Zweck:
#   CLI zum StA-Ausschleus-Verzeichnis (staging.StagingArea). Drei Aktionen:
#
#     add      — gepruefte Datei aufnehmen. --unbedenklich ist ein AUSDRUECK-
#                LICHER Schalter; fehlt er, wird abgewiesen (default-deny,
#                Fallregel 3). --cleared-by benennt den/die Pruefer:in.
#     finalize — Kopfdaten + Erzeugungsvermerk stempeln, UEBERGABE.txt schreiben.
#                Optional --coordinator-db (nur LESEND) -> Ketten-Spitze im
#                Erzeugungsvermerk (context_builder, voll abgesichert).
#     verify   — Paket gegen das Manifest nachrechnen (Manipulation/Fehlen/
#                Zusatz erkennen).
#
#   python -m management.export.ausschleus_admin add --dir D --file F \
#          --kind report_pdf --source-ref "uid=4711" --cleared-by h012345 \
#          --unbedenklich [--note TEXT]
#   python -m management.export.ausschleus_admin finalize --dir D \
#          [--coordinator-db PATH] [--behoerde ..] [--aktenzeichen ..] [--actor ..]
#   python -m management.export.ausschleus_admin verify --dir D
#
# BUILD 706 (Vorgang 70641ff9): 'finalize' OHNE --coordinator-db stempelte
#   Buildnummer 0 und Ersteller 'unbekannt' in die UEBERGABE.txt - das
#   Dokument, das mit dem Paket an die Staatsanwaltschaft geht - und sagte
#   dazu nichts. Die Buildnummer wird jetzt auch ohne Datenbank richtig
#   gefuellt; Identitaet und Belegkette stehen als Befund im Vermerk und auf
#   der Fehlerausgabe. Die Angabe bleibt optional (Entscheidung Alex,
#   12.08.2026), der Ausfall ist aber nicht mehr stumm.
#
# Version: v0.8.706 · Build: 706 · 2026-08-12
# =============================================================================

import argparse
import sqlite3
import sys
from datetime import datetime, timezone

from management.export.staging import (
    StagingArea, StagingError, UnbedenklichkeitError,
)
from management.export.export_envelope import DEFAULT_KLASSIFIKATION
# Build 706 (Vorgang 70641ff9): der DB-lose Rahmen und seine Meldung.
from management.export.context_builder import build_export_context_ohne_db
from management.export.rahmen_meldung import melde_rahmen_befunde
from management.help import cli_epilog  # noqa: E402


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _do_add(args) -> int:
    area = StagingArea(args.dir)
    try:
        entry = area.add_artifact(
            args.file, kind=args.kind, source_ref=args.source_ref,
            unbedenklich=bool(args.unbedenklich), cleared_by=args.cleared_by or "",
            added_at=_now_utc(), note=args.note or "")
    except UnbedenklichkeitError as exc:
        print("[ausschleus] %s" % exc, file=sys.stderr)
        return 2
    except StagingError as exc:
        print("[ausschleus] %s" % exc, file=sys.stderr)
        return 1
    print("[ausschleus] aufgenommen: %s (sha256=%s, %d Bytes)"
          % (entry["filename"], entry["sha256"], entry["size"]))
    return 0


def _do_finalize(args) -> int:
    area = StagingArea(args.dir)
    generated = _now_utc()
    context = None
    grund = "keine coordinator.db angegeben (--coordinator-db)"
    if args.coordinator_db:
        # Nur LESEND fuer die Ketten-Spitze; context_builder wirft nie.
        try:
            con = sqlite3.connect(
                "file:%s?mode=ro" % args.coordinator_db, uri=True)
            con.row_factory = sqlite3.Row
            try:
                from management.export.context_builder import build_export_context
                context = build_export_context(
                    con=con, db_path=args.coordinator_db,
                    behoerde=args.behoerde, aktenzeichen=args.aktenzeichen,
                    actor=args.actor, now_utc=generated)
            finally:
                con.close()
        except Exception as exc:  # Randfall: Pfad falsch, Datei kaputt
            grund = "coordinator.db nicht lesbar: %s" % exc
    if context is None:
        context = build_export_context_ohne_db(
            grund=grund,
            behoerde=args.behoerde,
            aktenzeichen=args.aktenzeichen or "StA-Uebergabe",
            actor=args.actor, now_utc=generated,
            klassifikation=DEFAULT_KLASSIFIKATION)

    # BUILD 706 (Vorgang 70641ff9) — HIER WIEGT ES AM SCHWERSTEN.
    # Der Erzeugungsvermerk dieses Laufs wird in UEBERGABE.txt gestempelt und
    # geht mit dem Paket an die Staatsanwaltschaft. Bis Build 702 trug er ohne
    # '--coordinator-db' Buildnummer 0 und Ersteller 'unbekannt', und der Lauf
    # sagte dazu nichts (gemessen am 12.08.2026). Die Meldung steht VOR
    # area.finalize(): faellt das Schreiben aus, ist die Auskunft schon heraus.
    melde_rahmen_befunde("[ausschleus]", context)

    area.finalize(context)
    n = len(area.load()["artifacts"])
    print("[ausschleus] finalisiert: %d Artefakt(e), UEBERGABE.txt + manifest.json"
          % n)
    return 0


def _do_verify(args) -> int:
    """
    Prueft ein Ausschleusungspaket gegen sein Manifest.

    BUILD 647 (Vorgang d30b3d95) - DREI RUECKGABEWERTE STATT ZWEI:
      0  Manifest vorhanden, alles stimmt.
      1  Manifest vorhanden, Abweichung - sie wird namentlich genannt.
      2  KEIN Manifest. In diesem Verzeichnis liegt kein Ausschleusungspaket.

    WARUM DIE 2 EIGENS: Bis Build 646 lieferte dieser Fall eine 0 mit der
    Meldung "OK - alle Artefakte stimmen mit dem Manifest ueberein" (gemessen
    auf einem leeren Verzeichnis). Wer ein Paket ausschleust, das nie erzeugt
    wurde, bekam eine Bestaetigung dafuer. Die 2 unterscheidet den Leerbefund
    vom Befund, ohne dass jemand die Ausgabe lesen muss.
    """
    area = StagingArea(args.dir)
    res = area.verify()
    if res.get("kein_manifest"):
        print("[ausschleus] KEIN PAKET — in '%s' liegt kein manifest.json. "
              "Hier ist nichts ausgeschleust worden; es gibt nichts zu "
              "pruefen. (Ein LEERES Paket mit Manifest waere etwas anderes "
              "und wuerde mit 0 bestaetigt.)" % args.dir, file=sys.stderr)
        return 2
    if res["ok"]:
        print("[ausschleus] OK — alle Artefakte stimmen mit dem Manifest ueberein.")
        return 0
    print("[ausschleus] BEFUND — Paket weicht vom Manifest ab:", file=sys.stderr)
    if res["mismatched"]:
        print("  veraendert: %s" % ", ".join(res["mismatched"]), file=sys.stderr)
    if res["missing"]:
        print("  fehlend:    %s" % ", ".join(res["missing"]), file=sys.stderr)
    if res["extra"]:
        print("  zusaetzlich: %s" % ", ".join(res["extra"]), file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ausschleus_admin",
        description="StA-Ausschleus-Verzeichnis (Sammeln/Finalisieren/Verifizieren).",
        epilog=cli_epilog.epilog("ausschleus_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="Gepruefte Datei aufnehmen (Fallregel 3).")
    a.add_argument("--dir", required=True)
    a.add_argument("--file", required=True)
    a.add_argument("--kind", required=True,
                   help="Art, z. B. report_pdf | case_status_xlsx | view_html.")
    a.add_argument("--source-ref", required=True,
                   help="Herkunft, z. B. 'uid=4711' oder 'dashboard'.")
    a.add_argument("--cleared-by", default=None,
                   help="Pruefer:in der Unbedenklichkeit (SAMAccountName).")
    a.add_argument("--unbedenklich", action="store_true",
                   help="AUSDRUECKLICHE Bestaetigung der Unbedenklichkeit.")
    a.add_argument("--note", default=None)
    a.set_defaults(func=_do_add)

    f = sub.add_parser("finalize", help="Kopfdaten stempeln + UEBERGABE.txt.")
    f.add_argument("--dir", required=True)
    f.add_argument("--coordinator-db", default=None)
    f.add_argument("--behoerde", default=None)
    f.add_argument("--aktenzeichen", default=None)
    f.add_argument("--actor", default=None)
    f.set_defaults(func=_do_finalize)

    v = sub.add_parser("verify", help="Paket gegen das Manifest nachrechnen.")
    v.add_argument("--dir", required=True)
    v.set_defaults(func=_do_verify)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

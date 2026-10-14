#!/usr/bin/env python3
# =============================================================================
# tools/integritaetssonde.py
# IT-Forensisches Ermittlungswerkzeug — Integritaetspruefung auf KOPIEN
# =============================================================================
# Zweck:
#   Feststellen, WELCHE Datenbank beschaedigt ist ('database disk image is
#   malformed'), ohne ein Original zu oeffnen. Je Datei:
#     1. SHA-256 des Originals (nur Bytes lesen, kein SQLite),
#     2. Kopie samt Begleitdateien (-journal, -wal, -shm) in ein eigenes
#        Arbeitsverzeichnis,
#     3. SHA-256 des Originals erneut — weicht er ab, hat waehrend des
#        Kopierens jemand geschrieben, und die Kopie ist nicht aussagekraeftig,
#     4. auf der KOPIE: Kopfbytes 18/19 (WAL-Stempel), Seitengroesse,
#        Seitenzahl, quick_check und integrity_check; 'Tree N' in den
#        Meldungen wird der Tabelle bzw. dem Index zugeordnet.
#
# BEFUND 14.10.2026 (Grund fuer die Staffelung): Die erste Fassung rief
#   integrity_check ohne Grenze auf — SQLite bricht dann nach 100 Meldungen
#   ab. In PROD fehlten dadurch drei beschaedigte Tabellen im Befund. Jetzt:
#   Grenze 1000000, bei Selbstabbruch gestaffelt kleiner; die Meldungszahl
#   und die verwendete Grenze stehen im Protokoll.
#
# Herkunft: am 13./14.10.2026 ausserhalb der Buildkette geliefert und in PROD
#   eingesetzt; ab Build 776 im Bestand.
#
# Aufruf (im Verzeichnis aiw_webserver; Webserver des Falls BEENDET, sonst
#   kann die Kopie mitten in einem Schreibvorgang entstehen — Schritt 3
#   meldet das):
#   python tools/integritaetssonde.py --uid <subject_id>
#   python tools/integritaetssonde.py <datei.db> [<datei.db> ...]
#   python tools/integritaetssonde.py <verzeichnis>      (alle *.db darin)
#   Protokoll zusaetzlich in integritaetssonde_<zeitstempel>.txt im
#   Arbeitsverzeichnis (oder --protokoll-dir).
#
# Rueckgabewerte: 0 alle geprueften Dateien ok; 1 mindestens ein Befund oder
#   eine nicht pruefbare Datei; 2 Aufruffehler.
#
# Version: v0.8.776 · Build: 776 · 2026-10-14
# =============================================================================
from __future__ import annotations

import argparse
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.help import cli_epilog  # noqa: E402
from db.reparatur.hilfen import BEGLEIT, sha256  # noqa: E402


def pfade_aus_konfiguration(uid: int):
    from core.config_loader import ConfigLoader
    c = ConfigLoader("config.yaml")
    j = os.path.join
    return [
        ("main  evidence", j(str(c.get("paths.evidence_db_dir")), "evidence_%d.db" % uid)),
        ("fdb   forensic", j(str(c.get("paths.forensic_db_dir")), "forensic_%d.db" % uid)),
        ("adb   assets", j(str(c.get("paths.assets_db_dir")), "assets_%d.db" % uid)),
        ("cdb   coordinator", str(c.get("paths.coordinator_db"))),
        ("ddb   default", str(c.get("paths.default_db"))),
        ("tdb   templates", str(c.get("paths.templates_db"))),
        ("trdb  translations", str(c.get("paths.translations_db"))),
    ]


def integritaet(con):
    """integrity_check gestaffelt -> (zeilen, grenze) oder (None, None)."""
    for grenze in (1000000, 1000, 100, 10):
        try:
            return ([t for r in con.execute("PRAGMA integrity_check(%d)" % grenze)
                     for t in str(r[0]).splitlines()], grenze)
        except sqlite3.DatabaseError:
            continue
    return None, None


def pruefe(rolle, original, arbeit, aus) -> str:
    """-> 'ok' | 'befund' | 'fehlt' | 'unbrauchbar'"""
    aus("")
    aus("=== %s: %s" % (rolle, original))
    if not os.path.exists(original):
        aus("    nicht vorhanden")
        return "fehlt"
    begleit = [s for s in BEGLEIT if os.path.exists(original + s)]
    aus("    Groesse %d Byte, Begleitdateien: %s"
        % (os.path.getsize(original), ", ".join(begleit) or "keine"))
    vorher = sha256(original)
    kopie = os.path.join(arbeit, "%d_%s" % (len(os.listdir(arbeit)),
                                            os.path.basename(original)))
    shutil.copy2(original, kopie)
    for s in begleit:
        shutil.copy2(original + s, kopie + s)
    nachher = sha256(original)
    aus("    SHA-256 Original vorher : %s" % vorher)
    aus("    SHA-256 Original nachher: %s%s" % (
        nachher, "" if nachher == vorher else
        "   <-- ABWEICHUNG: waehrend des Kopierens geaendert, Kopie unbrauchbar"))
    if nachher != vorher:
        return "unbrauchbar"
    with open(kopie, "rb") as fh:
        kopf = fh.read(100)
    if kopf[:16] != b"SQLite format 3\x00":
        aus("    KEIN SQLite-Kopf: %r" % kopf[:16])
        return "befund"
    seiten = int.from_bytes(kopf[16:18], "big")
    aus("    Kopf: Seitengroesse=%d  Bytes18/19=%d/%d (2/2 = WAL-gestempelt)  "
        "Seiten laut Kopf=%d" % (65536 if seiten == 1 else seiten, kopf[18],
                                 kopf[19], int.from_bytes(kopf[28:32], "big")))
    befund = False
    try:
        con = sqlite3.connect(kopie, timeout=1)
        try:
            try:
                baeume = {r[0]: "%s %s" % (r[1], r[2]) for r in con.execute(
                    "SELECT rootpage, type, name FROM sqlite_schema WHERE rootpage > 0")}
            except sqlite3.Error as exc:
                baeume = {}
                aus("    sqlite_schema nicht lesbar: %s" % exc)
                befund = True
            try:
                q = [r[0] for r in con.execute("PRAGMA quick_check").fetchall()]
                aus("    quick_check: %s" % ("ok" if q == ["ok"] else "%d Meldung(en)" % len(q)))
                befund = befund or q != ["ok"]
            except sqlite3.DatabaseError as exc:
                aus("    quick_check bricht ab: %s" % exc)
                befund = True
            zeilen, grenze = integritaet(con)
            if zeilen is None:
                aus("    integrity_check: bricht bei jeder Grenze selbst ab")
                befund = True
            else:
                aus("    integrity_check: %d Zeile(n) (Grenze %d)" % (len(zeilen), grenze))
                for z in zeilen[:30]:
                    aus("      %s" % z)
                if len(zeilen) > 30:
                    aus("      ... (%d weitere Zeilen)" % (len(zeilen) - 30))
                for n in sorted({int(n) for n in re.findall(r"Tree (\d+)", "\n".join(zeilen))}):
                    aus("      Tree %d = %s" % (n, baeume.get(n, "unbekannt")))
                befund = befund or zeilen != ["ok"]
        finally:
            con.close()
    except sqlite3.Error as exc:
        aus("    SQLite-Fehler auf der Kopie: %s: %s" % (type(exc).__name__, exc))
        befund = True
    return "befund" if befund else "ok"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Prueft SQLite-Dateien auf KOPIEN (quick_check, "
                    "integrity_check) und ordnet Meldungen Tabellen zu. "
                    "Oeffnet kein Original.",
        epilog=cli_epilog.epilog("integritaetssonde"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--uid", type=int, metavar="SUBJECT_ID",
                   help="alle Datenbanken dieses Falls laut config.yaml")
    p.add_argument("pfade", nargs="*",
                   help="Dateien oder Verzeichnisse (alle *.db darin)")
    p.add_argument("--protokoll-dir", default=".", metavar="VERZEICHNIS",
                   help="wohin das Protokoll geschrieben wird (Vorgabe: .)")
    args = p.parse_args(argv)
    if args.uid is None and not args.pfade:
        p.error("--uid oder mindestens ein Pfad")
    if args.uid is not None:
        ziele = pfade_aus_konfiguration(args.uid)
    else:
        ziele = []
        for pf in args.pfade:
            if os.path.isdir(pf):
                ziele += [("datei", os.path.join(pf, f))
                          for f in sorted(os.listdir(pf)) if f.endswith(".db")]
            else:
                ziele.append(("datei", pf))
    stempel = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs(args.protokoll_dir, exist_ok=True)
    pfad_prot = os.path.join(args.protokoll_dir, "integritaetssonde_%s.txt" % stempel)
    ergebnisse = []
    with open(pfad_prot, "w", encoding="utf-8") as prot:
        def aus(text):
            print(text)
            prot.write(text + "\n")
        aus("integritaetssonde (Build 776) %s  Python %s  SQLite %s" % (
            stempel, sys.version.split()[0], sqlite3.sqlite_version))
        arbeit = tempfile.mkdtemp(prefix="aiw_integritaet_")
        aus("Arbeitskopien in: %s" % arbeit)
        try:
            for rolle, pfad in ziele:
                ergebnisse.append(pruefe(rolle, os.path.abspath(pfad), arbeit, aus))
        finally:
            shutil.rmtree(arbeit, ignore_errors=True)
        aus("")
        aus("Zusammenfassung: %d ok, %d mit Befund, %d nicht vorhanden, "
            "%d Kopie unbrauchbar" % (ergebnisse.count("ok"), ergebnisse.count("befund"),
                                      ergebnisse.count("fehlt"), ergebnisse.count("unbrauchbar")))
        aus("Protokoll: %s" % pfad_prot)
    return 0 if all(e in ("ok", "fehlt") for e in ergebnisse) else 1


if __name__ == "__main__":
    sys.exit(main())

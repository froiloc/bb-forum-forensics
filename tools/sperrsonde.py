#!/usr/bin/env python3
# =============================================================================
# tools/sperrsonde.py
# IT-Forensisches Ermittlungswerkzeug — Wer sperrt eine SQLite-Datei?
# =============================================================================
# Zweck:
#   Feststellen, OB und WIE eine Datei gesperrt ist, wenn ein Schreiben mit
#   'database is locked' scheitert. Mehrere Durchgaenge im Abstand:
#     1. Gibt es '<datei>-journal'? Im Journalmodus DELETE existiert sie NUR,
#        solange eine Verbindung eine Schreibtransaktion offen haelt.
#     2. BEGIN IMMEDIATE mit Wartezeit 0 — scheitert es sofort, haelt jemand
#        eine SCHREIBsperre (RESERVED/PENDING/EXCLUSIVE).
#     3. BEGIN EXCLUSIVE mit Wartezeit 0 — scheitert NUR dieses (2. gelang),
#        haelt jemand eine LESEsperre (SHARED), d. h. eine offene
#        Lesetransaktion.
#   Danach ROLLBACK: es wird NICHTS geschrieben; die Probe haelt die Sperre
#   nur fuer die Dauer eines BEGIN/ROLLBACK.
#
# Herkunft: als sperrsonde_coordinator.py am 13.10.2026 ausserhalb der
#   Buildkette geliefert (Befund 'Umschalten fehlgeschlagen: database is
#   locked' beim Bildschleier: eine offene Transaktion der geteilten
#   Verbindung hielt eine SHARED-Sperre auf coordinator.db). Ab Build 776
#   im Bestand, fuer jede Datei verwendbar.
#
# Aufruf (WAEHREND der Webserver laeuft — darum geht es):
#   python tools/sperrsonde.py                     (coordinator.db laut config.yaml)
#   python tools/sperrsonde.py --db <pfad.db> [--durchgaenge N] [--abstand S]
#
# Rueckgabewerte: 0 in keinem Durchgang gesperrt; 1 mindestens einmal
#   gesperrt; 2 Aufruffehler.
#
# Version: v0.8.776 · Build: 776 · 2026-10-14
# =============================================================================
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.help import cli_epilog  # noqa: E402


def probe(pfad: str, art: str) -> str:
    con = sqlite3.connect(pfad, timeout=0, isolation_level=None)
    try:
        con.execute("BEGIN %s" % art)
        con.execute("ROLLBACK")
        return "frei"
    except sqlite3.OperationalError as exc:
        return "GESPERRT (%s)" % exc
    finally:
        con.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Prueft wiederholt, ob eine SQLite-Datei schreib- oder "
                    "lesegesperrt ist. Schreibt nichts.",
        epilog=cli_epilog.epilog("sperrsonde"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--db", default=None, metavar="PFAD",
                   help="die Datei (Vorgabe: paths.coordinator_db aus config.yaml)")
    p.add_argument("--durchgaenge", type=int, default=10, metavar="N",
                   help="Zahl der Durchgaenge (Vorgabe 10)")
    p.add_argument("--abstand", type=float, default=1.0, metavar="S",
                   help="Sekunden zwischen den Durchgaengen (Vorgabe 1)")
    args = p.parse_args(argv)
    if args.db is None:
        if not os.path.isfile("config.yaml"):
            print("FEHLER: ohne --db wird config.yaml im Arbeitsverzeichnis "
                  "gebraucht.", file=sys.stderr)
            return 2
        from core.config_loader import ConfigLoader
        args.db = str(ConfigLoader("config.yaml").get("paths.coordinator_db"))
    pfad = os.path.abspath(args.db)
    if not os.path.isfile(pfad):
        print("FEHLER: Datei nicht gefunden: %s" % pfad, file=sys.stderr)
        return 2
    print("Datei          :", pfad)
    # Nur lesend (PY4): die Abfrage des Journalmodus braucht kein Schreibrecht.
    uri = "file:" + pfad.replace("?", "%3f") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        print("journal_mode   :", con.execute("PRAGMA journal_mode").fetchone()[0])
    finally:
        con.close()
    gesperrt = False
    for i in range(1, args.durchgaenge + 1):
        journal = os.path.exists(pfad + "-journal")
        imm, exk = probe(pfad, "IMMEDIATE"), probe(pfad, "EXCLUSIVE")
        gesperrt = gesperrt or imm != "frei" or exk != "frei"
        print("[%2d] %s  -journal=%s  IMMEDIATE=%s  EXCLUSIVE=%s" % (
            i, time.strftime("%H:%M:%S"), "JA" if journal else "nein", imm, exk))
        if i < args.durchgaenge:
            time.sleep(args.abstand)
    return 1 if gesperrt else 0


if __name__ == "__main__":
    sys.exit(main())

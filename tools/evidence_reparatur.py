#!/usr/bin/env python3
# =============================================================================
# tools/evidence_reparatur.py
# IT-Forensisches Ermittlungswerkzeug — Neuaufbau einer beschaedigten
#                                       evidence_<uid>.db (Kommandozeile)
# =============================================================================
# Zweck:
#   Aus einer beschaedigten Ermittler-Datenbank eine NEUE Datei aufbauen —
#   mit allem, was sich lesen laesst — und ein Protokoll schreiben, das jede
#   nicht geborgene Zeile zaehlt. Die Logik steht in db/reparatur/
#   (EvidenceReparierer); dieses Werkzeug ist ihre Kommandozeile.
#
#   DAS ORIGINAL WIRD NIE VERAENDERT. Der Austausch ist hier ein eigener
#   Schritt von Hand; die Befehle stehen am Ende des Protokolls, wenn die
#   neue Datei freigegeben ist. (Die Startpruefung des Webservers tauscht ab
#   Build 778 selbst aus — Festlegung Alex 14.10.2026.)
#
# Herkunft: am 14.10.2026 ausserhalb der Buildkette als Fassungen 1.0-1.2
#   geliefert; mit 1.2 wurde evidence_2948078.db in PROD neu aufgebaut.
#   Ab Build 776 im Bestand. Unterschiede zu 1.2:
#     * Aufruf ueber argparse (einheitliche Hilfe mit Beispielen);
#     * eine Sicherung mit identischer SHA-256 wird wiederverwendet statt
#       erneut angelegt;
#     * Rueckgabewert 3 fuer 'neue Datei in Ordnung, aber nicht freigegeben'
#       (1.2 lieferte dafuer 0).
#
# Aufruf (im Verzeichnis aiw_webserver, Webserver des Falls BEENDET):
#   python tools/evidence_reparatur.py --uid <subject_id> [--ziel <verzeichnis>]
#   python tools/evidence_reparatur.py <datei.db>          [--ziel <verzeichnis>]
#   Ohne --ziel: <backup.dest_dir aus config.yaml>/defekt
#
# WARTUNGSSTUFE B (maintenance/wartungsstufen.py): schreibt nur in den Ordner
#   fuer beschaedigte Dateien; das Original wird nur kopiert. Einschraenkung:
#   Laeuft der Webserver des Falls, kann die Sicherung mitten in einem
#   Schreibvorgang entstehen; der SHA-256-Abgleich erkennt das, dann wird
#   NICHTS repariert (Rueckgabewert 1).
#
# Rueckgabewerte:
#   0 neue Datei freigegeben (Austauschbefehle im Protokoll)
#   1 nichts brauchbares erzeugt (Sicherung nicht stimmig, Arbeitskopie nicht
#     lesbar oder neue Datei verworfen)
#   2 Aufruffehler (vor jedem Schreiben erkannt)
#   3 neue Datei in Ordnung, aber NICHT freigegeben: eine Tabelle mit
#     Ermittlungsergebnissen war beschaedigt — ein Mensch entscheidet
#
# Version: v0.8.776 · Build: 776 · 2026-10-14
# =============================================================================
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.help import cli_epilog  # noqa: E402
from db.reparatur.evidence_reparierer import EvidenceReparierer  # noqa: E402
from db.reparatur.reparatur_ziel import (  # noqa: E402
    ReparaturZiel, ReparaturZielFehler)


def _konfiguration():
    """config.yaml aus dem Arbeitsverzeichnis, wie der Webserver sie liest."""
    if not os.path.isfile("config.yaml"):
        raise ReparaturZielFehler(
            "config.yaml nicht im Arbeitsverzeichnis %s gefunden. Bitte im "
            "Verzeichnis aiw_webserver aufrufen oder --ziel angeben." % os.getcwd())
    from core.config_loader import ConfigLoader
    return ConfigLoader("config.yaml")


def _pfade(args):
    """-> (original, ziel, herkunft)."""
    cfg = None
    if args.uid is not None:
        cfg = _konfiguration()
        ev_dir = cfg.get("paths.evidence_db_dir")
        if not ev_dir:
            raise ReparaturZielFehler("paths.evidence_db_dir fehlt in config.yaml.")
        original = os.path.join(str(ev_dir), "evidence_%d.db" % args.uid)
    else:
        original = args.datei
    if args.ziel is not None:
        ziel, herkunft = os.path.abspath(args.ziel), "--ziel %r" % args.ziel
    else:
        ziel, herkunft = ReparaturZiel.aus_konfiguration(cfg or _konfiguration())
    return os.path.abspath(original), ziel, herkunft


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Baut aus einer beschaedigten evidence_<uid>.db eine neue "
                    "Datei auf und protokolliert jede nicht geborgene Zeile. "
                    "Das Original wird nicht veraendert.",
        epilog=cli_epilog.epilog("evidence_reparatur"),
        formatter_class=cli_epilog.HilfeFormat)
    wahl = p.add_mutually_exclusive_group(required=True)
    wahl.add_argument("--uid", type=int, metavar="SUBJECT_ID",
                      help="Datei aus config.yaml: "
                           "paths.evidence_db_dir/evidence_<uid>.db")
    wahl.add_argument("datei", nargs="?", default=None,
                      help="Pfad der Datei (statt --uid)")
    p.add_argument("--ziel", default=None, metavar="VERZEICHNIS",
                   help="Ordner fuer Sicherung, neue Datei und Protokoll "
                        "(Vorgabe: <backup.dest_dir>/defekt; nicht der Ordner "
                        "des Originals)")
    args = p.parse_args(argv)

    try:
        original, ziel, herkunft = _pfade(args)
        ReparaturZiel.pruefen(original, ziel, herkunft)
    except ReparaturZielFehler as exc:
        print("FEHLER: %s" % exc, file=sys.stderr)
        return 2

    erg = EvidenceReparierer(
        original, ziel, ausgabe=print,
        kennung="evidence_reparatur (Build 776)",
        kopfzeilen=["  Herkunft: %s" % herkunft]).ausfuehren()

    def nachwort(text=""):
        print(text)
        erg.protokoll_anhaengen(text)

    if erg.status == "freigegeben":
        nachwort("")
        nachwort("AUSTAUSCH (von Hand, Webserver beendet) — erst nach Durchsicht")
        nachwort("dieses Protokolls:")
        nachwort('  move "%s" "%s.ersetzt_%s"' % (original, original, erg.zeitstempel))
        nachwort('  copy "%s" "%s"' % (erg.neu, original))
        nachwort('Danach zur Kontrolle: python tools/integritaetssonde.py "%s"'
                 % original)
    elif erg.status == "nicht_freigegeben":
        nachwort("Hier entscheidet ein Mensch. Bitte dieses Protokoll zurueckmelden.")
    nachwort("Protokoll: %s" % erg.protokoll_txt)
    return {"freigegeben": 0, "nicht_freigegeben": 3}.get(erg.status, 1)


if __name__ == "__main__":
    sys.exit(main())

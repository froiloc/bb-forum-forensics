#!/usr/bin/env python3
# =============================================================================
# issue-tracker/repair_related_ids.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# ZWECK: Kommandozeile fuer related_id_repair.RelatedIdRepair.
#
#   python repair_related_ids.py                 # Trockenlauf (Vorgabe)
#   python repair_related_ids.py --apply         # aendert die Datei
#   python repair_related_ids.py -t <pfad>       # anderes Ziel
#
# EXIT-CODES (fuer die Verwendung in Skripten):
#   0 - keine Maengel, oder: alle Maengel wurden mit '--apply' behoben
#   1 - Maengel vorhanden (Trockenlauf), oder: es bleiben Maengel uebrig,
#       die das Werkzeug NICHT entscheiden kann (mehrdeutig/unbekannt)
#   2 - technischer Fehler (Datei fehlt, kein JSON, ...)
#
#   Die 1 heisst also 'schau hin', nicht 'kaputt'. Das ist Absicht: der
#   Trockenlauf soll in einer Pruefkette auffallen.
#
# WARUM DIE VORGABE DER TROCKENLAUF IST: Das Werkzeug fasst die einzige
#   Datei an, in der die Vorgangsverwaltung dieses Projekts steht. Ein
#   Werkzeug, das beim ersten unbedachten Aufruf schreibt, ist an dieser
#   Datei nicht zu verantworten. Wer aendern will, sagt es ausdruecklich.
#
# Version: v0.8.642 - Build: 642 - 2026-08-01
# =============================================================================

import argparse
import sys
from pathlib import Path

from related_id_repair import (
    BEFUND_AUFLOESBAR,
    BEFUND_MEHRDEUTIG,
    BEFUND_UNBEKANNT,
    RelatedIdRepair,
    Reparaturbericht,
)


def _bericht_ausgeben(bericht: Reparaturbericht, ziel: Path, angewendet: bool) -> None:
    """Gibt den Befund aus - vollstaendig, nicht als Zusammenfassung."""
    print("=" * 70)
    print("🔗 VERWEISE IN 'related_to'")
    print("=" * 70)
    print(f"\n📂 Datei:    {ziel}")
    print(f"🔍 Geprüft:  {bericht.geprueft} Verweise")

    aufloesbar = bericht.aufloesbar
    mehrdeutig = bericht.nach_befund(BEFUND_MEHRDEUTIG)
    unbekannt = bericht.nach_befund(BEFUND_UNBEKANNT)

    if not (aufloesbar or mehrdeutig or unbekannt):
        print("\n✅ Kein Mangel. Alle Verweise sind volle, vorhandene UUIDs.")
        return

    if aufloesbar:
        kopf = "BEHOBEN" if angewendet else "AUFLÖSBAR (Trockenlauf - nichts geändert)"
        print(f"\n🔧 {kopf}: {len(aufloesbar)}")
        for b in aufloesbar:
            print(f"   • in {b.quelle_id[:8]}...: {b.verweis!r} → {b.ziel_id}")

    # Diese beiden Listen werden EINZELN und VOLLSTAENDIG ausgegeben, nicht
    # als Zahl: sie sind das, was ein Mensch entscheiden muss.
    if mehrdeutig:
        print(f"\n❓ MEHRDEUTIG - nicht angetastet: {len(mehrdeutig)}")
        for b in mehrdeutig:
            print(f"   • in {b.quelle_id[:8]}...: {b.verweis!r} passt auf:")
            for k in b.kandidaten:
                print(f"       - {k}")

    if unbekannt:
        print(f"\n⚠️  UNBEKANNT - kein passender Vorgang, nicht angetastet: {len(unbekannt)}")
        for b in unbekannt:
            print(f"   • in {b.quelle_id[:8]}...: {b.verweis!r}")

    if bericht.sicherung:
        print(f"\n💾 Sicherung: {bericht.sicherung}")
    if bericht.geschrieben:
        print(f"✅ Geschrieben: {bericht.geschrieben}")
    if aufloesbar and not angewendet:
        print("\n👉 Zum Anwenden:  python repair_related_ids.py --apply")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="🔗 Repariert verkürzte Verweise in 'related_to'",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ohne --apply wird NICHTS geändert.\n"
            "Exit: 0 = sauber bzw. behoben, 1 = Mängel offen, 2 = Fehler.\n"
        ),
    )
    parser.add_argument(
        "--target", "-t",
        default="data/issues.json",
        help="Pfad zur Issue-Datei (Standard: data/issues.json)",
    )
    parser.add_argument(
        "--backup-dir",
        default=None,
        help="Verzeichnis für die Sicherung (Standard: 'backups' neben dem Datenverzeichnis)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Änderungen tatsächlich schreiben (ohne dieses Flag: Trockenlauf)",
    )
    args = parser.parse_args(argv)

    ziel = Path(args.target)
    if not ziel.exists():
        print(f"❌ Datei nicht gefunden: {ziel}")
        return 2

    reparatur = RelatedIdRepair(ziel, args.backup_dir)

    try:
        if args.apply:
            bericht = reparatur.anwenden()
        else:
            bericht = reparatur.pruefen()
    except (ValueError, OSError) as fehler:
        print(f"❌ {fehler}")
        return 2

    _bericht_ausgeben(bericht, ziel, args.apply)

    # Offen bleibt, was das Werkzeug nicht entscheiden darf - und im
    # Trockenlauf zusaetzlich alles, was es entscheiden KOENNTE, aber
    # (noch) nicht durfte.
    offen = len(bericht.offen)
    if not args.apply:
        offen += len(bericht.nach_befund(BEFUND_AUFLOESBAR))

    return 1 if offen else 0


if __name__ == "__main__":
    sys.exit(main())

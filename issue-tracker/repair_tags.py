#!/usr/bin/env python3
# =============================================================================
# issue-tracker/repair_tags.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# ZWECK: Kommandozeile fuer tag_repair.TagRepair (Vorgang 6e96ae4a).
#
#   python repair_tags.py               # Trockenlauf (Vorgabe)
#   python repair_tags.py --liste       # zeigt nur die Zuordnung
#   python repair_tags.py --apply       # aendert die Datei
#
# EXIT-CODES: 0 = nichts zu tun bzw. erledigt, 1 = es gibt etwas zu tun
#             (Trockenlauf), 2 = technischer Fehler.
#
# DIE ZUORDNUNG STEHT IN tag_repair.py und stammt von mc, nicht von mir.
# Welche Begriffe dasselbe meinen, ist eine fachliche Frage - ein Werkzeug,
# das sie sich selbst errechnet, haette die Grundregel-Nummern zusammengelegt
# und damit den Bezug zerstoert.
#
# Version: v0.8.650 - Build: 650 - 2026-08-02
# =============================================================================

import argparse
import sys
from collections import Counter
from pathlib import Path

from tag_repair import ZUORDNUNG, TagRepair


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="🏷  Legt Tags nach der vorgegebenen Zuordnung zusammen",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Ohne --apply wird NICHTS geändert.\n",
    )
    parser.add_argument("--target", "-t", default="data/issues.json",
                        help="Pfad zur Issue-Datei (Standard: data/issues.json)")
    parser.add_argument("--backup-dir", default=None,
                        help="Verzeichnis für die Sicherung")
    parser.add_argument("--apply", action="store_true",
                        help="Änderungen tatsächlich schreiben")
    parser.add_argument("--liste", action="store_true",
                        help="Nur die hinterlegte Zuordnung ausgeben")
    args = parser.parse_args(argv)

    if args.liste:
        print("Hinterlegte Zuordnung (Festlegung mc, 2026-08-02):")
        for alt, neu in sorted(ZUORDNUNG.items()):
            print(f"   {alt:20} → {neu}")
        return 0

    ziel = Path(args.target)
    if not ziel.exists():
        print(f"❌ Datei nicht gefunden: {ziel}")
        return 2

    reparatur = TagRepair(ziel, sicherungsverzeichnis=args.backup_dir)
    try:
        bericht = reparatur.anwenden() if args.apply else reparatur.pruefen()
    except (ValueError, OSError) as fehler:
        print(f"❌ {fehler}")
        return 2

    print("=" * 66)
    print("🏷  TAG-ZUSAMMENLEGUNG")
    print("=" * 66)
    print(f"\n📂 Datei: {ziel}")

    if not bericht.befunde:
        print("\n✅ Nichts zu tun - kein Tag aus der Zuordnung kommt noch vor.")
        return 0

    kopf = "ERSETZT" if args.apply else "ZU ERSETZEN (Trockenlauf - nichts geändert)"
    print(f"\n🔧 {kopf}: {len(bericht.befunde)} in {bericht.betroffene_vorgaenge} Vorgängen")
    je_paar = Counter((b.alt, b.neu) for b in bericht.befunde)
    for (alt, neu), anzahl in sorted(je_paar.items()):
        print(f"   • {alt:20} → {neu:20} {anzahl:>3}x")
    for befund in bericht.befunde:
        print(f"       {befund.vorgang_id[:8]}  {befund.alt} → {befund.neu}")

    if bericht.sicherung:
        print(f"\n💾 Sicherung: {bericht.sicherung}")
    if bericht.geschrieben:
        print(f"✅ Geschrieben: {bericht.geschrieben}")
    if not args.apply:
        print("\n👉 Zum Anwenden:  python repair_tags.py --apply")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

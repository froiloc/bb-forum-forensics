#!/usr/bin/env python3
# =============================================================================
# issue-tracker/repair_literal_newlines.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# ZWECK: Kommandozeile fuer literal_newline_repair.LiteralNewlineRepair.
#
#   python repair_literal_newlines.py                    # Trockenlauf
#   python repair_literal_newlines.py --apply            # aendert die Datei
#   python repair_literal_newlines.py --nur 651e6d84     # nur EIN Vorgang
#   python repair_literal_newlines.py --alle-zeigen      # auch Erwaehnungen
#
# EXIT-CODES:
#   0 - nichts zu tun, oder: mit '--apply' erledigt
#   1 - es gibt Umbrueche zu reparieren (Trockenlauf)
#   2 - technischer Fehler (Datei fehlt, kein JSON, ...)
#
# WARUM DIE VORGABE DER TROCKENLAUF IST: Das Werkzeug fasst die einzige Datei
#   an, in der die Vorgangsverwaltung dieses Projekts steht. Wer aendern will,
#   sagt es ausdruecklich. Dieselbe Regel wie bei repair_related_ids.py.
#
# Version: v0.8.648 - Build: 648 - 2026-08-01
# =============================================================================

import argparse
import sys
from collections import Counter
from pathlib import Path

from literal_newline_repair import LiteralNewlineRepair, Reparaturbericht


def _ausgeben(bericht: Reparaturbericht, ziel: Path, angewendet: bool,
              alle_zeigen: bool) -> None:
    print("=" * 72)
    print("↵ ZEILENUMBRUECHE, DIE ALS ZEICHENFOLGE IM TEXT STEHEN")
    print("=" * 72)
    print(f"\n📂 Datei: {ziel}")

    umbrueche = bericht.umbrueche
    erwaehnungen = bericht.erwaehnungen

    if not umbrueche and not erwaehnungen:
        print("\n✅ Kein Vorkommen. Nichts zu tun.")
        return

    print(f"🔍 Gefunden: {len(umbrueche) + len(erwaehnungen)} Vorkommen "
          f"in {len({f.vorgang_id for f in bericht.fundstellen})} Vorgängen")

    if umbrueche:
        kopf = "ERSETZT" if angewendet else "ZU ERSETZEN (Trockenlauf - nichts geändert)"
        print(f"\n🔧 {kopf}: {len(umbrueche)} in {bericht.betroffene_vorgaenge} Vorgängen")
        je_vorgang = Counter((f.vorgang_id, f.feld) for f in umbrueche)
        for (kennung, feld), anzahl in sorted(je_vorgang.items()):
            print(f"   • {kennung[:8]}  {feld:<20} {anzahl:>3}x")

    # DIE ERWAEHNUNGEN WERDEN IMMER EINZELN UND VOLLSTAENDIG GEZEIGT.
    # Sie sind das, was das Werkzeug NICHT anfasst - und genau das muss ein
    # Mensch nachsehen koennen, ohne ein zweites Mal zu suchen (Grundregel 1).
    if erwaehnungen:
        print(f"\n📌 WÖRTLICH GEMEINT - nicht angetastet: {len(erwaehnungen)}")
        for f in erwaehnungen:
            print(f"   • {f.vorgang_id[:8]}  {f.feld}")
            print(f"       …{f.umgebung}…")

    if alle_zeigen and umbrueche:
        print(f"\n📄 Alle {len(umbrueche)} Umbrüche im Einzelnen:")
        for f in umbrueche:
            print(f"   • {f.vorgang_id[:8]}  {f.feld}")
            print(f"       …{f.umgebung}…")

    if bericht.sicherung:
        print(f"\n💾 Sicherung: {bericht.sicherung}")
    if bericht.geschrieben:
        print(f"✅ Geschrieben: {bericht.geschrieben}")
    if umbrueche and not angewendet:
        print("\n👉 Erst ansehen:   python repair_literal_newlines.py --alle-zeigen")
        print("   Dann anwenden:  python repair_literal_newlines.py --apply")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="↵ Macht aus literalen Backslash-n wieder Zeilenumbrüche",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ohne --apply wird NICHTS geändert.\n"
            "Wörtlich gemeinte Vorkommen ('wird als \\n gespeichert') bleiben\n"
            "stehen und werden einzeln aufgelistet.\n"
            "Exit: 0 = sauber bzw. erledigt, 1 = offen, 2 = Fehler.\n"
        ),
    )
    parser.add_argument("--target", "-t", default="data/issues.json",
                        help="Pfad zur Issue-Datei (Standard: data/issues.json)")
    parser.add_argument("--backup-dir", default=None,
                        help="Verzeichnis für die Sicherung (Standard: 'backups' "
                             "neben dem Datenverzeichnis)")
    parser.add_argument("--apply", action="store_true",
                        help="Änderungen tatsächlich schreiben (sonst Trockenlauf)")
    parser.add_argument("--nur", default=None, metavar="ID",
                        help="Nur diesen Vorgang anfassen (Präfix der ID genügt)")
    parser.add_argument("--alle-zeigen", action="store_true",
                        help="Jede einzelne Fundstelle mit ihrer Umgebung ausgeben")
    args = parser.parse_args(argv)

    ziel = Path(args.target)
    if not ziel.exists():
        print(f"❌ Datei nicht gefunden: {ziel}")
        return 2

    reparatur = LiteralNewlineRepair(ziel, args.backup_dir)
    try:
        bericht = reparatur.anwenden(args.nur) if args.apply else reparatur.pruefen()
    except (ValueError, OSError) as fehler:
        print(f"❌ {fehler}")
        return 2

    _ausgeben(bericht, ziel, args.apply, args.alle_zeigen)

    if args.apply:
        # Nach dem Lauf noch einmal nachsehen - die Zusage lautet 'erledigt',
        # und die prueft man nicht am Vorsatz, sondern an der Datei.
        return 0 if not reparatur.pruefen().umbrueche else 1
    return 1 if bericht.umbrueche else 0


if __name__ == "__main__":
    sys.exit(main())

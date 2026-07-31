#!/usr/bin/env python3
# =============================================================================
# tools/forensic_index_upgrade.py
# IT-Forensisches Ermittlungswerkzeug — Wartungswerkzeug (Build 531)
# =============================================================================
# Zweck:
#   Legt auf den BESTEHENDEN forensic_<uid>.db die Zeitindizes an, die der
#   Fristenmonitor braucht — ohne die Dateien neu erzeugen zu muessen.
#   Die ganze Fachlogik liegt in
#   management/maintenance/forensic_index_upgrade.py; hier steht nur die
#   Bedienung und die Ausgabe.
#
# AUFRUF (in der VM, aus dem Verzeichnis des Webservers, z. B. S:\):
#
#   1) ERST SEHEN, WAS PASSIEREN WUERDE (Vorgabe, schreibt NICHTS):
#        python tools/forensic_index_upgrade.py --forensic-dir D:\pfad\forensic
#
#   2) DANN AN WENIGEN DATEIEN AUSPROBIEREN:
#        python tools/forensic_index_upgrade.py --forensic-dir D:\pfad\forensic \
#               --ausfuehren --grenze 3
#
#   3) DANN DER GANZE BESTAND:
#        python tools/forensic_index_upgrade.py --forensic-dir D:\pfad\forensic \
#               --ausfuehren --protokoll index_upgrade.json
#
#   Fuer den vollstaendigen Inhaltsbeleg (liest jede Datei GANZ — auf einem
#   Netzlaufwerk eine Entscheidung, keine Nebensache):
#        ... --prueftiefe voll
#
# WAS DU BEOBACHTEN MUSST:
#   * Der Block 'ERGEBNIS ZUM ZURUECKMELDEN' am Ende. Genau den bitte
#     zurueckschicken — er enthaelt KEINE Kontonamen und KEINE Inhalte, nur
#     Zahlen, Dateinamen-Muster und Pruefsummen (Fallregel 3).
#   * Die Spalte 'Inhalt': sie muss bei JEDER geaenderten Datei 'gleich' sagen.
#     Sagt sie 'ABWEICHUNG', ist die betreffende Datei gesondert zu betrachten
#     — das Werkzeug nimmt NICHTS zurueck und repariert NICHTS.
#   * Die Zeile 'uebersprungen': WAL-gestempelte Dateien werden nicht
#     angefasst. Sie brauchen zuerst tools/convert_journal_mode.py.
#
# WARTUNGSVORBEHALT — STUFE A (Build 612), NUR BEI --ausfuehren:
#   Das Werkzeug schreibt in die VERSIEGELTEN forensic_<uid>.db und legt kein
#   Backup an. Vor dem scharfen Lauf wird deshalb geprueft, ob der Bestand
#   ruhig ist (maintenance/wartungsvorbehalt.py).
#
#   HIER WIRD VORAUSSICHTLICH IMMER NACHGEFRAGT, und das ist Absicht: Auf
#   einer schreibgeschuetzten Datei ist die Sperrprobe blind — sie meldet dort
#   auch dann Erfolg, wenn jemand die Datei geoeffnet haelt. Solche Dateien
#   gelten deshalb als 'nicht pruefbar' und verlangen die Eingabe eines
#   vollstaendigen Wortes, auch bei gesetztem Wartungsfenster. Ueber eine
#   Datei, deren Ruhe niemand messen kann, muss ein Mensch entscheiden.
#
#   DER TROCKENLAUF IST NICHT BETROFFEN. Er schreibt nichts, und eine
#   unbequeme Vorschau wird uebersprungen — das waere der falsche Preis.
#
# RUECKGABEWERTE (fuer Skripte):
#   0 — Lauf sauber (auch der Trockenlauf).
#   1 — mindestens eine Datei mit Zustand 'fehler'.
#   2 — der Lauf war als Ganzes undurchfuehrbar (z. B. Verzeichnis fehlt).
#   3 — Wartungsvorbehalt: es wurde NICHTS geschrieben.
#
# Version: v0.8.612 · Build: 612 · 2026-07-31 · Wartung, kein Serverbestandteil
# =============================================================================

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.maintenance.forensic_index_upgrade import (      # noqa: E402
    PRUEFTIEFEN,
    ForensicIndexUpgrade,
    ForensicIndexUpgradeError,
)
from maintenance.wartungsvorbehalt import (                      # noqa: E402
    datenwurzel, wartungsvorbehalt,
)

#: Klartext je Zustand — damit die Ausgabe ohne Handbuch lesbar ist.
ZUSTAND_TEXT = {
    "aktuell": "bereits indiziert",
    "geplant": "wuerde geaendert (Trockenlauf)",
    "geaendert": "Index angelegt",
    "uebersprungen": "uebersprungen",
    "fehler": "FEHLER",
}


def _tabelle(protokoll) -> None:
    """Eine Zeile je Datei. Kurz genug, um 162 Zeilen zu ueberblicken."""
    print("")
    print("%-22s %-30s %-10s %s"
          % ("Datei", "Zustand", "Inhalt", "Anmerkung"))
    print("-" * 100)
    for b in protokoll.befunde:
        name = Path(b.pfad).name
        if b.zustand == "geaendert":
            inhalt = "gleich" if b.unveraendert else "ABWEICHUNG"
        elif b.zustand == "geplant":
            inhalt = "gemessen"
        else:
            inhalt = "—"
        anmerkung = b.grund
        if len(anmerkung) > 44:
            anmerkung = anmerkung[:41] + "..."
        print("%-22s %-30s %-10s %s"
              % (name, ZUSTAND_TEXT.get(b.zustand, b.zustand), inhalt,
                 anmerkung))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="forensic_index_upgrade",
        description="Legt fehlende Zeitindizes auf forensic_<uid>.db an. "
                    "TROCKENLAUF ist die Vorgabe.")
    ap.add_argument("--forensic-dir", required=True,
                    help="Verzeichnis mit den forensic_<uid>.db")
    ap.add_argument("--ausfuehren", action="store_true",
                    help="TATSAECHLICH schreiben. Ohne diese Angabe wird nur "
                         "berichtet, was geschehen wuerde.")
    ap.add_argument("--grenze", type=int, default=None,
                    help="Hoechstens so viele Dateien behandeln (erster "
                         "vorsichtiger Lauf). Die Zahl der ausgelassenen "
                         "Dateien wird ausgewiesen.")
    ap.add_argument("--prueftiefe", default="fingerabdruck",
                    choices=list(PRUEFTIEFEN),
                    help="'fingerabdruck' (Vorgabe): je betroffener Tabelle "
                         "ein Durchlauf. 'voll': Hash ueber alle Zeilen aller "
                         "Tabellen — vollstaendiger Beleg, liest jede Datei "
                         "ganz.")
    ap.add_argument("--protokoll", default=None,
                    help="Pfad fuer das vollstaendige Protokoll als JSON. "
                         "DAS ist das Beweisstueck, nicht die "
                         "Bildschirmausgabe.")
    args = ap.parse_args(argv)

    # --- WARTUNGSVORBEHALT (Stufe A, Build 612) --------------------------
    # Nur beim scharfen Lauf. Der Trockenlauf schreibt nichts und braucht
    # keinen Vorbehalt — ihn zu verzoegern haette den Preis, dass die
    # Vorschau unbequem wird, und eine unbequeme Vorschau wird uebersprungen.
    #
    # DIESES WERKZEUG IST DER GRUND, WARUM ES DEN ZUSTAND 'unpruefbar' GIBT.
    # Es schreibt in die VERSIEGELTEN forensic_<uid>.db, und auf genau solchen
    # Dateien ist die Sperrprobe blind (Befund aus mcs Regressionslauf zu
    # Build 610; Issue 96f2b18f-a4a1-41af-871c-ae7a10087130). Es ist deshalb
    # damit zu rechnen, dass hier IMMER nachgefragt wird — das ist kein
    # Fehler, sondern die Aussage: ueber diese Dateien kann niemand messen,
    # ob sie ruhig sind, also muss ein Mensch entscheiden.
    #
    # GEPRUEFT WIRD DER GANZE BESTAND des Verzeichnisses, nicht die von
    # --grenze getroffene Auswahl: welche Dateien die Auswahl trifft, steht
    # erst im Lauf fest, und bis dahin ist die Frage schon zu beantworten.
    # Die Ausgabe fuehrt die ersten zwoelf namentlich auf und zaehlt den Rest
    # nach Befund ab.
    if args.ausfuehren:
        kandidaten = sorted(Path(args.forensic_dir).glob("forensic_*.db"))
        befund = wartungsvorbehalt(
            datenwurzel(args.forensic_dir), kandidaten or [args.forensic_dir],
            werkzeug="forensic_index_upgrade",
            was_geschieht="legt Zeitindizes auf den forensic_<uid>.db an. Das "
                          "sind versiegelte Beweismittel-Datenbanken; ein "
                          "Backup legt dieses Werkzeug NICHT an.")
        print(befund.text)
        if not befund.erlaubt:
            return befund.rueckgabewert

    try:
        werk = ForensicIndexUpgrade(args.forensic_dir,
                                    prueftiefe=args.prueftiefe)
        protokoll = werk.lauf(ausfuehren=bool(args.ausfuehren),
                              grenze=args.grenze)
    except ForensicIndexUpgradeError as exc:
        print("[index-upgrade] LAUF UNDURCHFUEHRBAR: %s" % exc,
              file=sys.stderr)
        return 2

    _tabelle(protokoll)

    if args.protokoll:
        Path(args.protokoll).write_text(
            json.dumps(protokoll.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8")

    z = protokoll.zaehler
    fehler = z.get("fehler", 0)
    print("")
    print("=" * 72)
    print("ERGEBNIS ZUM ZURUECKMELDEN")
    print("=" * 72)
    print("Modus:            %s"
          % ("AUSGEFUEHRT (geschrieben)" if protokoll.ausgefuehrt
             else "TROCKENLAUF (nichts geschrieben)"))
    print("Prueftiefe:       %s" % protokoll.prueftiefe)
    print("Kandidatenspalten: %s"
          % ", ".join("%s.%s" % k for k in protokoll.kandidaten))
    print("Dateien gefunden: %d" % protokoll.dateien_gesamt)
    for schluessel in ("aktuell", "geplant", "geaendert", "uebersprungen",
                       "fehler", "nicht_betrachtet"):
        if schluessel in z:
            print("  %-16s %d" % (schluessel + ":", z[schluessel]))
    geaendert = [b for b in protokoll.befunde if b.zustand == "geaendert"]
    if geaendert:
        gleich = sum(1 for b in geaendert if b.unveraendert)
        print("Inhalt unveraendert: %d von %d geaenderten Dateien"
              % (gleich, len(geaendert)))
        schnitt = sum(b.dauer_ms for b in geaendert) / len(geaendert)
        print("Dauer je geaenderter Datei: %.1f ms (Mittel)" % schnitt)
    print("Gesamtdauer:      %.1f ms" % protokoll.dauer_ms)
    if args.protokoll:
        print("Protokoll:        %s" % args.protokoll)
    if fehler:
        print("")
        print("ACHTUNG: %d Datei(en) mit Zustand 'fehler'. Sie sind gesondert "
              "zu betrachten; es wurde NICHTS zurueckgenommen." % fehler)
    print("=" * 72)
    return 1 if fehler else 0


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())

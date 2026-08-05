#!/usr/bin/env python3
# =============================================================================
# issue-tracker/pruefe_einmischung.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# Zweck (Vorgang 7d3c1a95, Baustein b):
#   GEGENPROBE NACH DEM EINMISCHEN. Prueft, ob wirklich alles aus einer
#   Eintragsdatei im Bestand angekommen ist - BEVOR die Quelldatei geloescht
#   wird.
#
# WARUM ES DAS BRAUCHT - der Vorfall vom 05.08.2026:
#   Eine Eintragsdatei trug zu zwei vorhandenen Vorgaengen je eine Update-Zeile
#   nach. merge.py meldete Erfolg, merge-new-tickets.sh loeschte die Datei -
#   und im Bestand stand nichts davon. Der Nachtrag war weder eingemischt noch
#   noch vorhanden. Weg ist weg.
#
#   Der Ausloeser (ein fehlender Zweig in merge.py) ist in Build 673 behoben.
#   DIESE DATEI BEHEBT ETWAS ANDERES, und das ist wichtiger: sie macht die
#   ERFOLGSMELDUNG DES WERKZEUGS UEBERPRUEFBAR. Bisher war die Meldung der
#   einzige Beleg dafuer, dass etwas angekommen ist - und eine Meldung ist
#   kein Beleg, sie ist eine Behauptung. Kommt die naechste Luecke in merge.py
#   (und irgendwann kommt sie), kostet sie mit dieser Gegenprobe keine Daten
#   mehr, sondern nur einen Abbruch.
#
#   Dasselbe Verhaeltnis wie zwischen bundle_bauen.sh und pruefe_lieferung.sh:
#   nicht das Werkzeug sagt, dass es geklappt hat, sondern der Bestand.
#
# Was geprueft wird - je Vorgang der Quelldatei:
#   1. Die Kennung steht im Bestand.
#   2. JEDER Update-Zeitstempel der Quelle steht im Bestand.
#   3. Die acht Vergleichsfelder von merge.py stimmen ueberein.
#      (Bei '--auto-resolve source' muessen sie das; weichen sie ab, ist der
#      Vorgang nicht uebernommen worden.)
#
# Was NICHT geprueft wird, und das gehoert gesagt:
#   Ob der Bestand darueber hinaus stimmt. Diese Probe beantwortet genau eine
#   Frage - 'ist alles aus DIESER Datei angekommen?'. Sie ist keine
#   Bestandspruefung.
#
# Aufruf:
#   python pruefe_einmischung.py <quelldatei.json> [--bestand data/issues.json]
#
# Rueckgabewerte:
#   0 = alles angekommen, die Quelldatei darf geloescht werden
#   1 = etwas fehlt - die Quelldatei MUSS erhalten bleiben
#   2 = Aufruf- oder Lesefehler
#
# Version: v0.8.673 - Build: 673 - 2026-08-05
# =============================================================================

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# WORTGLEICHE ABSCHRIFT aus merge.py, detect_conflicts(). Wird sie dort
# geaendert, gehoert sie hier nachgezogen - der Testfall PE05 wacht darueber.
VERGLEICHSFELDER = ("title", "description", "status", "priority", "severity",
                    "assigned_to", "target_version", "affected_version")


def lade(pfad: Path) -> dict:
    with open(pfad, encoding="utf-8") as fh:
        return json.load(fh)


def pruefe(quelle: dict, bestand: dict) -> list[str]:
    """
    Vergleicht die Quelldatei gegen den Bestand.

    Rueckgabe: Liste der Beanstandungen. Leer heisst: alles angekommen.
    """
    im_bestand = {i.get("id"): i for i in bestand.get("issues", [])}
    maengel: list[str] = []

    for e in quelle.get("issues", []):
        kennung = e.get("id")
        kurz = (kennung or "?")[:8]

        alt = im_bestand.get(kennung)
        if alt is None:
            maengel.append(
                "%s: steht NICHT im Bestand - der Vorgang ist nicht "
                "angekommen" % kurz)
            continue

        vorhandene = {u.get("timestamp") for u in (alt.get("updates") or [])}
        for u in (e.get("updates") or []):
            if u.get("timestamp") not in vorhandene:
                maengel.append(
                    "%s: Update-Zeile vom %s (%s) fehlt im Bestand"
                    % (kurz, u.get("timestamp"), u.get("author")))

        for feld in VERGLEICHSFELDER:
            if alt.get(feld) != e.get(feld):
                maengel.append(
                    "%s: Feld '%s' weicht ab - geliefert %r, im Bestand %r"
                    % (kurz, feld, e.get(feld), alt.get(feld)))

    return maengel


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Gegenprobe: ist alles aus einer Eintragsdatei im "
                    "Bestand angekommen? (nur lesend)")
    ap.add_argument("quelldatei", help="die eingemischte Eintragsdatei")
    ap.add_argument("--bestand", default="data/issues.json",
                    help="Pfad zum Bestand (Vorgabe: data/issues.json)")
    args = ap.parse_args()

    quelle_pfad = Path(args.quelldatei)
    bestand_pfad = Path(args.bestand)

    try:
        quelle = lade(quelle_pfad)
        bestand = lade(bestand_pfad)
    except (OSError, json.JSONDecodeError) as exc:
        print("FEHLER beim Lesen: %s" % exc, file=sys.stderr)
        return 2

    maengel = pruefe(quelle, bestand)
    anzahl = len(quelle.get("issues", []))

    if not maengel:
        print("   Gegenprobe: alle %d Vorgang/Vorgaenge aus %s stehen "
              "vollstaendig im Bestand." % (anzahl, quelle_pfad.name))
        return 0

    print("", file=sys.stderr)
    print("GEGENPROBE FEHLGESCHLAGEN fuer %s" % quelle_pfad.name,
          file=sys.stderr)
    print("Das Einmischen hat Erfolg gemeldet, aber im Bestand fehlt:",
          file=sys.stderr)
    for m in maengel:
        print("  - %s" % m, file=sys.stderr)
    print("", file=sys.stderr)
    print("DIE QUELLDATEI WIRD NICHT GELOESCHT. Sie ist der einzige "
          "verbliebene Traeger", file=sys.stderr)
    print("dieser Angaben. Ursache klaeren, dann erneut einmischen.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

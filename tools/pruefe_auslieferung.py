#!/usr/bin/env python3
# =============================================================================
# tools/pruefe_auslieferung.py
# IT-Forensisches Ermittlungswerkzeug
# =============================================================================
# Zweck (Grundregel 8):
#   Prueft eine MD5SUMS_Build<N>.txt gegen den Bestand - und zwar VOM
#   REPOSITORY-WURZELVERZEICHNIS AUS. Genau daran hing der Befund vom
#   2026-07-31.
#
# DER BEFUND, DEN DIESES WERKZEUG KUENFTIG ABFAENGT:
#   Zwei Auslieferungsarchive wurden EINE EBENE ZU TIEF entpackt. Alles landete
#   unter 'management/' statt in der Wurzel:
#       management/build.json                        (statt build.json)
#       management/management/help/inhalt/...        (statt management/help/...)
#       management/tests/...                         (statt tests/...)
#   Der Regressionslauf meldete daraufhin einen scheinbaren Codefehler
#   (AP07: "Kacheln ohne Text im Register") - in Wahrheit las der Test das
#   ALTE Register in der Wurzel, waehrend die neuen Texte eine Ebene tiefer
#   lagen.
#
#   WARUM DIE VORHANDENE MD5-PRUEFUNG DAS NICHT GEFANGEN HAT: Die Pfade in
#   MD5SUMS sind RELATIV. Ist der ganze Baum gleichmaessig verschoben, ist er
#   in sich stimmig - eine Pruefung, die im verschobenen Verzeichnis laeuft,
#   sagt "alles in Ordnung". Der Fehler ist nur von der WURZEL aus sichtbar.
#
#   DESHALB prueft dieses Werkzeug ZUERST, ob es ueberhaupt an der Wurzel
#   steht (Merkmale: build.json, run_tests.py und das Verzeichnis management/
#   liegen NEBENEINANDER), und weigert sich sonst. Erst danach vergleicht es
#   die Pruefsummen.
#
# Aufruf (aus dem Wurzelverzeichnis):
#   python tools/pruefe_auslieferung.py               -> der AKTUELLE Build
#   python tools/pruefe_auslieferung.py MD5SUMS_Build597.txt
#
# OHNE ARGUMENT wird die Liste zum Build aus build.json geprueft - und NUR
# diese. Das ist Absicht: Eine MD5SUMS-Liste beschreibt den Zustand ZUM
# ZEITPUNKT IHRES BUILDS. Eine Datei, die seither in einem spaeteren Build
# geaendert wurde, weicht von der aelteren Liste zwangslaeufig ab. Alle Listen
# gegen den heutigen Bestand zu pruefen erzeugte also lauter richtige
# Abweichungen und damit ein Rauschen, in dem der eine echte Befund untergeht.
#
# Exit-Codes:
#   0 = alle geprueften Dateien stimmen
#   1 = mindestens eine Datei fehlt oder weicht ab
#   2 = falsches Arbeitsverzeichnis / Aufrufproblem
#
# Version: v0.8.597 - Build: 597 - 2026-07-31
# =============================================================================

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

#: Merkmale, an denen die Wurzel erkannt wird. Alle drei muessen NEBENEINANDER
#: liegen - ein einzelnes waere zu wenig: 'management/' gibt es auch eine
#: Ebene tiefer, wenn falsch entpackt wurde.
WURZEL_MERKMALE: Tuple[str, ...] = ("build.json", "run_tests.py", "management")


class AuslieferungsFehler(Exception):
    """Das Arbeitsverzeichnis ist nicht die Wurzel des Bestands."""


def ist_wurzel(pfad: Path) -> bool:
    """Reine Pruefung: liegen alle Merkmale nebeneinander in diesem Pfad?"""
    return all((pfad / m).exists() for m in WURZEL_MERKMALE)


def finde_wurzel(start: Path) -> Optional[Path]:
    """
    Sucht die Wurzel ab 'start' aufwaerts (hoechstens vier Ebenen). Gibt sie
    zurueck oder None. Aufwaerts und nicht abwaerts: eine falsch entpackte
    Kopie liegt UNTERHALB und darf gerade nicht gefunden werden.
    """
    p = start.resolve()
    for _ in range(4):
        if ist_wurzel(p):
            return p
        if p.parent == p:
            break
        p = p.parent
    return None


def md5_datei(pfad: Path) -> str:
    h = hashlib.md5()
    with pfad.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def lies_liste(pfad: Path) -> List[Tuple[str, str]]:
    """
    Liest eine MD5SUMS-Datei: '<summe>  <pfad>' je Zeile. Leerzeilen und
    Kommentare werden uebergangen; eine unlesbare Zeile ist ein Fehler und
    wird NICHT still verworfen (Grundregel 1).
    """
    eintraege: List[Tuple[str, str]] = []
    for nr, zeile in enumerate(pfad.read_text(encoding="utf-8").splitlines(), 1):
        roh = zeile.strip()
        if not roh or roh.startswith("#"):
            continue
        teile = roh.split(None, 1)
        if len(teile) != 2 or len(teile[0]) != 32:
            raise AuslieferungsFehler(
                "%s Zeile %d ist keine Pruefsummenzeile: %r"
                % (pfad.name, nr, zeile))
        eintraege.append((teile[0].lower(), teile[1].strip()))
    if not eintraege:
        raise AuslieferungsFehler("%s enthaelt keine Eintraege." % pfad.name)
    return eintraege


def pruefe(wurzel: Path, liste: Path) -> Tuple[int, int, List[str]]:
    """
    Vergleicht eine Liste gegen den Bestand.
    Rueckgabe: (geprueft, in Ordnung, Befunde).
    """
    befunde: List[str] = []
    eintraege = lies_liste(liste)
    ok = 0
    for summe, rel in eintraege:
        ziel = wurzel / rel
        if not ziel.is_file():
            befunde.append("FEHLT      %s" % rel)
            continue
        ist = md5_datei(ziel)
        if ist != summe:
            befunde.append("ABWEICHUNG %s (erwartet %s, gefunden %s)"
                           % (rel, summe, ist))
            continue
        ok += 1
    return len(eintraege), ok, befunde


def _aktueller_build(wurzel: Path) -> Optional[int]:
    """Die Buildnummer aus build.json - oder None, wenn sie nicht lesbar ist."""
    import json
    try:
        return int(json.loads(
            (wurzel / "build.json").read_text(encoding="utf-8"))["build"])
    except Exception:
        return None


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Prueft MD5SUMS_Build<N>.txt gegen den Bestand "
                    "(nur vom Wurzelverzeichnis aus).")
    p.add_argument("listen", nargs="*", help="MD5SUMS-Dateien")
    p.add_argument("--alle", action="store_true",
                   help="ALLE Listen pruefen. Nur zur Spurensuche: aeltere "
                        "Listen weichen naturgemaess ab, weil ihre Dateien "
                        "seither weitergebaut wurden.")
    args = p.parse_args(argv)

    wurzel = finde_wurzel(Path.cwd())
    if wurzel is None:
        print("FEHLER: Kein Wurzelverzeichnis gefunden.", file=sys.stderr)
        print("        Erwartet werden NEBENEINANDER: %s"
              % ", ".join(WURZEL_MERKMALE), file=sys.stderr)
        print("        Haeufigste Ursache: das Archiv wurde eine Ebene zu "
              "tief entpackt.", file=sys.stderr)
        return 2
    if wurzel != Path.cwd().resolve():
        print("Hinweis: Wurzel ist %s (Aufruf erfolgte aus %s)."
              % (wurzel, Path.cwd()))

    # Ein zweiter, verschobener Bestand ist der eigentliche Befund - er faellt
    # sonst niemandem auf, weil in sich alles stimmt.
    verschoben = [d for d in wurzel.iterdir()
                  if d.is_dir() and ist_wurzel(d)]
    if verschoben:
        print("BEFUND: Unterhalb der Wurzel liegt ein ZWEITER vollstaendiger "
              "Bestand:", file=sys.stderr)
        for d in verschoben:
            print("        %s" % d.relative_to(wurzel), file=sys.stderr)
        print("        Das ist fast immer ein zu tief entpacktes Archiv. "
              "Bitte zuerst aufloesen.", file=sys.stderr)
        return 1

    listen = [Path(x) for x in args.listen]
    if args.alle:
        listen = sorted(wurzel.glob("MD5SUMS_Build*.txt"))
        print("Hinweis: --alle prueft auch ALTE Listen. Abweichungen dort "
              "sind normal (die Dateien wurden seither weitergebaut).")
    elif not listen:
        aktuell = _aktueller_build(wurzel)
        if aktuell is None:
            print("build.json nicht lesbar - bitte die Liste angeben.",
                  file=sys.stderr)
            return 2
        kandidat = wurzel / ("MD5SUMS_Build%d.txt" % aktuell)
        if not kandidat.is_file():
            print("Zu Build %d gibt es keine Liste (%s)."
                  % (aktuell, kandidat.name), file=sys.stderr)
            return 2
        listen = [kandidat]
    if not listen:
        print("Keine MD5SUMS-Dateien gefunden.", file=sys.stderr)
        return 2

    gesamt = ok_gesamt = 0
    alle_befunde: List[str] = []
    for liste in listen:
        pfad = liste if liste.is_absolute() else (wurzel / liste)
        if not pfad.is_file():
            alle_befunde.append("FEHLT      %s (Pruefliste selbst)" % liste)
            continue
        anzahl, ok, befunde = pruefe(wurzel, pfad)
        gesamt += anzahl
        ok_gesamt += ok
        zustand = "OK" if not befunde else "BEFUND"
        print("%-28s %2d/%2d  %s" % (pfad.name, ok, anzahl, zustand))
        alle_befunde.extend("  " + b for b in befunde)

    if alle_befunde:
        print("\nBefunde:", file=sys.stderr)
        for b in alle_befunde:
            print(b, file=sys.stderr)
        print("\n%d von %d Dateien in Ordnung." % (ok_gesamt, gesamt))
        return 1

    print("\nAlle %d Dateien in Ordnung." % gesamt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

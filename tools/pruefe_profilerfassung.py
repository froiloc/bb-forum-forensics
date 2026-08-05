#!/usr/bin/env python3
# =============================================================================
# tools/pruefe_profilerfassung.py
# IT-Forensisches Ermittlungswerkzeug — PRUEFUNG (kein Produktivcode)
# =============================================================================
# Zweck (Vorgang 90e7c214):
#   Prueft fuer JEDEN vorhandenen Fall, ob die Profilseiten der erfassten
#   Benutzer tatsaechlich im Bestand liegen - und nennt am Ende die Faelle,
#   die neu erfasst werden muessen, mit subject_id und Benutzername.
#
# DER BEFUND, DER DAZU GEFUEHRT HAT (gemessen 05.08.2026, forensic_1488.db):
#   1.000 Erfassungsziele der Profil-Typen ('other_profile' 982, 'profile' 17,
#   'pgp_probe' 1) stehen im Bestand. Profilseiten liegen dort 12 - und alle
#   zwoelf gehoeren DEMSELBEN Benutzer, naemlich dem Beschuldigten selbst
#   (id=1488, verschiedene Unterseiten). Die Profilseiten der 982 anderen
#   Benutzer, mit denen er zu tun hatte, fehlen vollstaendig.
#
# WARUM DAS SCHWER WIEGT: Die Profilseite ist die Seitenart, die fuer die
#   Zuordnung eines Kontos zu einer natuerlichen Person am meisten hergibt -
#   Registrierungsdatum, Signatur, Kontaktangaben, Selbstbeschreibung, PGP.
#   Fehlt sie, fehlt sie genau dort, wo ermittelt wird. Das ist keine Luecke
#   der Navigation, sondern der Erfassung: die Belege sind nicht da.
#
# WAS DIESES WERKZEUG TUT:
#   Es geht alle 'forensic_*.db' eines Verzeichnisses durch und stellt je Fall
#   gegenueber:
#     (a) welche Benutzerkennungen als Profil-Erfassungsziel vorgemerkt sind,
#     (b) zu welchen Kennungen tatsaechlich eine Profilseite im Bestand liegt.
#   Die Differenz ist die Fehlmenge. Am Ende steht eine Liste zum Uebernehmen.
#
# WAS ES NICHT TUT:
#   Es aendert nichts, es erfasst nichts nach und es beurteilt nicht, ob eine
#   Nacherfassung noch moeglich ist - das Forum ist beschlagnahmt, nicht
#   erreichbar. Es sagt nur, WO etwas fehlt.
#
#   Zugriff ausschliesslich lesend ueber die URI-Form 'mode=ro'. Kein PRAGMA,
#   keine TEMP-Sicht, keine Kopie. Die evidence_<uid>.db wird nicht geoeffnet.
#
# Aufruf:
#   python tools/pruefe_profilerfassung.py --verzeichnis ./data/forensic
#   python tools/pruefe_profilerfassung.py --verzeichnis ./data/forensic --fehlende 20
#   python tools/pruefe_profilerfassung.py --forensic-db ./data/forensic/forensic_1488.db
#
# Rueckgabewerte:
#   0 = kein Fall betroffen
#   1 = mindestens ein Fall betroffen (BEFUND, kein Fehler)
#   2 = Aufruf- oder Zugriffsfehler
#
# Ausgabe: Konsole und 'pruefe_profilerfassung.log'; mit '--csv' zusaetzlich
#          eine Liste (subject_id, Benutzername, Fehlmenge) zum Weiterreichen.
#
# Abhaengigkeiten: nur Stdlib.
# Version: v0.8.675 · Build: 675 · 2026-08-05
# =============================================================================

from __future__ import annotations

import argparse
import csv
import os
import re
import sqlite3
import sys
from pathlib import Path

# Direktaufruf als Skript: das Paketverzeichnis muss im Suchpfad liegen,
# sonst findet der Import aus "management/" nichts (Muster aus tools/hilfe.py).
_WURZEL = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _WURZEL not in sys.path:
    sys.path.insert(0, _WURZEL)

try:
    from management.help import cli_epilog  # noqa: E402
    _EPILOG = cli_epilog.epilog("pruefe_profilerfassung")
    _FORMAT = cli_epilog.HilfeFormat
except Exception:                                    # pragma: no cover
    # Eine fehlende Hilfe darf eine Pruefung nicht verhindern.
    _EPILOG = None
    _FORMAT = argparse.HelpFormatter

AUSGABEDATEI = "pruefe_profilerfassung.log"
LOGLINES: list[str] = []

# Die url_type-Werte, die auf eine Profilseite zielen.
# Beleg: TYPE_MAP in db/forensic_db.py, get_trace_sequence() - alle drei
# bilden auf das Fragment 'profile.php?id=' ab.
PROFIL_TYPEN = ("profile", "other_profile", "pgp_probe")

# Aus einer URL die Benutzerkennung ziehen. BEWUSST NICHT nur 'id=' direkt
# hinter 'profile.php?': im Bestand kommen beide Formen vor -
#   /forum/profile.php?id=1488
#   /forum/profile.php?section=essentials&edit&id=1488
# Wer nur die erste Form sucht, haelt die zweite fuer nicht vorhanden und
# meldet eine Fehlmenge, die es nicht gibt.
_KENNUNG = re.compile(r"profile\.php\?[^\s]*?\bid=(\d+)")


def log(msg: str = "") -> None:
    print(msg)
    LOGLINES.append(msg)


def oeffne_lesend(pfad: Path) -> sqlite3.Connection:
    """Oeffnet die Datenbank ueber die URI-Form mit 'mode=ro'."""
    uri = "file:" + str(pfad).replace("?", "%3f").replace("#", "%23") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def meta(con: sqlite3.Connection) -> dict:
    """Liest forensic_meta als einfaches Woerterbuch."""
    try:
        return {r["key"]: r["value"]
                for r in con.execute("SELECT key, value FROM forensic_meta")}
    except sqlite3.Error:
        return {}


def pruefe_fall(pfad: Path) -> dict:
    """
    Untersucht EINEN Fall.

    Rueckgabe: dict mit subject_id, benutzername, ziele, vorhanden, fehlend,
    fehlende_kennungen, fehler.
    """
    ergebnis = {
        "datei": pfad.name, "subject_id": None, "benutzername": None,
        "ziele": 0, "vorhanden": 0, "fehlend": 0,
        "fehlende_kennungen": [], "fehler": None,
    }
    try:
        con = oeffne_lesend(pfad)
    except sqlite3.Error as exc:
        ergebnis["fehler"] = str(exc)
        return ergebnis

    try:
        m = meta(con)
        # subject_id: bevorzugt aus forensic_meta, sonst aus dem Dateinamen.
        # Der Dateiname ist ein Rueckfall und keine Quelle - er wird nur
        # benutzt, wenn die Datenbank selbst nichts sagt, und das steht dann
        # auch so in der Ausgabe.
        for schluessel in ("user_id", "subject_id", "uid"):
            if m.get(schluessel):
                ergebnis["subject_id"] = str(m[schluessel])
                break
        if ergebnis["subject_id"] is None:
            treffer = re.search(r"forensic_(\d+)\.db$", pfad.name)
            ergebnis["subject_id"] = (treffer.group(1) + " (aus dem Dateinamen)"
                                      if treffer else "unbekannt")
        ergebnis["benutzername"] = m.get("username") or "(nicht hinterlegt)"

        # (a) Welche Benutzerkennungen sind als Profilziel vorgemerkt?
        platzhalter = ", ".join("?" for _ in PROFIL_TYPEN)
        ziel_kennungen = set()
        for row in con.execute(
                "SELECT actor_user_id FROM scrape_targets "
                "WHERE url_type IN (%s) AND actor_user_id IS NOT NULL"
                % platzhalter, PROFIL_TYPEN):
            ziel_kennungen.add(str(row["actor_user_id"]))

        # (b) Zu welchen Kennungen liegt tatsaechlich eine Profilseite vor?
        vorhandene = set()
        for row in con.execute(
                "SELECT url_canonical FROM pages "
                "WHERE url_canonical LIKE '%profile.php%'"):
            treffer = _KENNUNG.search(str(row["url_canonical"] or ""))
            if treffer:
                vorhandene.add(treffer.group(1))
        try:
            for row in con.execute(
                    "SELECT url_raw FROM page_aliases "
                    "WHERE url_raw LIKE '%profile.php%'"):
                treffer = _KENNUNG.search(str(row["url_raw"] or ""))
                if treffer:
                    vorhandene.add(treffer.group(1))
        except sqlite3.Error:
            log("   HINWEIS (%s): 'page_aliases' nicht lesbar - Zweitadressen "
                "fehlen in dieser Zaehlung." % pfad.name)

        fehlend = sorted(ziel_kennungen - vorhandene, key=lambda s: int(s))
        ergebnis["ziele"] = len(ziel_kennungen)
        ergebnis["vorhanden"] = len(ziel_kennungen & vorhandene)
        ergebnis["fehlend"] = len(fehlend)
        ergebnis["fehlende_kennungen"] = fehlend
    except sqlite3.Error as exc:
        ergebnis["fehler"] = str(exc)
    finally:
        con.close()
    return ergebnis


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Prueft, ob die Profilseiten der erfassten Benutzer im "
                    "Bestand liegen (nur lesend).",
        epilog=_EPILOG,
        formatter_class=_FORMAT)
    quelle = ap.add_mutually_exclusive_group(required=True)
    quelle.add_argument("--verzeichnis",
                        help="Verzeichnis mit den forensic_<uid>.db")
    quelle.add_argument("--forensic-db",
                        help="EINE einzelne forensic_<uid>.db")
    ap.add_argument("--fehlende", type=int, default=10,
                    help="wie viele fehlende Kennungen je Fall nennen "
                         "(Vorgabe 10, 0 = keine)")
    ap.add_argument("--csv", default=None,
                    help="Liste der betroffenen Faelle zusaetzlich als CSV")
    args = ap.parse_args()

    if args.forensic_db:
        dateien = [Path(args.forensic_db)]
        if not dateien[0].is_file():
            print("FEHLER: '%s' ist keine Datei." % args.forensic_db,
                  file=sys.stderr)
            return 2
    else:
        verz = Path(args.verzeichnis)
        if not verz.is_dir():
            print("FEHLER: '%s' ist kein Verzeichnis." % args.verzeichnis,
                  file=sys.stderr)
            return 2
        dateien = sorted(verz.glob("forensic_*.db"))
        if not dateien:
            print("FEHLER: in '%s' liegt keine 'forensic_*.db'."
                  % args.verzeichnis, file=sys.stderr)
            return 2

    log("=" * 78)
    log("PRUEFUNG: Sind die Profilseiten der erfassten Benutzer vorhanden?")
    log("Vorgang 90e7c214")
    log("=" * 78)
    log("Python      : %s" % sys.version.split()[0])
    log("Zugriff     : ausschliesslich lesend (URI mode=ro)")
    log("Zu pruefen  : %d Fall/Faelle" % len(dateien))
    log()

    ergebnisse = [pruefe_fall(p) for p in dateien]

    kopf = ("%-28s %-12s %-18s %7s %7s %8s  %s"
            % ("Datei", "subject_id", "Benutzer", "Ziele", "da", "fehlt",
               "Befund"))
    log(kopf)
    log("-" * len(kopf))
    betroffen = []
    for e in ergebnisse:
        if e["fehler"]:
            log("%-28s %s" % (e["datei"], "NICHT LESBAR: " + e["fehler"]))
            continue
        if e["ziele"] == 0:
            befund = "keine Profilziele"
        elif e["fehlend"] == 0:
            befund = "vollstaendig"
        else:
            befund = "BETROFFEN"
            betroffen.append(e)
        log("%-28s %-12s %-18s %7d %7d %8d  %s"
            % (e["datei"], str(e["subject_id"])[:12],
               str(e["benutzername"])[:18], e["ziele"], e["vorhanden"],
               e["fehlend"], befund))
    log()

    if args.fehlende and betroffen:
        for e in betroffen:
            log("Fehlende Profilseiten in %s (erste %d von %d):"
                % (e["datei"], min(args.fehlende, e["fehlend"]), e["fehlend"]))
            log("   " + ", ".join(e["fehlende_kennungen"][:args.fehlende]))
            log()

    if betroffen:
        log("=" * 78)
        log("ZUM NEUERFASSEN - subject_id und Benutzername der betroffenen "
            "Faelle:")
        log("=" * 78)
        for e in betroffen:
            log("  %-12s %-24s (%d von %d Profilseiten fehlen)"
                % (e["subject_id"], e["benutzername"], e["fehlend"],
                   e["ziele"]))
        log()
        log("Diese Faelle sind ohne die Profilseiten der Gegenueber nur "
            "eingeschraenkt")
        log("auswertbar. Ob eine Nacherfassung moeglich ist, sagt dieses "
            "Werkzeug NICHT -")
        log("das Forum ist beschlagnahmt. Es sagt nur, wo etwas fehlt.")
    else:
        log("Kein Fall betroffen.")
    log()

    if args.csv:
        try:
            with open(args.csv, "w", encoding="utf-8", newline="") as fh:
                schreiber = csv.writer(fh, delimiter=";")
                schreiber.writerow(["subject_id", "benutzername", "ziele",
                                    "vorhanden", "fehlend", "datei"])
                for e in betroffen:
                    schreiber.writerow([e["subject_id"], e["benutzername"],
                                        e["ziele"], e["vorhanden"],
                                        e["fehlend"], e["datei"]])
            log("Liste geschrieben: %s" % args.csv)
        except OSError as exc:
            log("WARNUNG: '%s' nicht schreibbar: %s" % (args.csv, exc))

    try:
        Path(AUSGABEDATEI).write_text("\n".join(LOGLINES) + "\n",
                                      encoding="utf-8")
        print("\nProtokoll: %s" % Path(AUSGABEDATEI).resolve())
    except OSError as exc:                            # pragma: no cover
        print("\nWARNUNG: Protokoll nicht schreibbar: %s" % exc)

    return 1 if betroffen else 0


if __name__ == "__main__":
    sys.exit(main())

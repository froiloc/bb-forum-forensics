#!/usr/bin/env python3
# =============================================================================
# tools/schadensanalyse.py
# IT-Forensisches Ermittlungswerkzeug — Schadensbild einer beschaedigten
#                                       SQLite-Datei (auf einer KOPIE)
# =============================================================================
# Zweck:
#   Fuer eine Datei, die tools/integritaetssonde.py als beschaedigt meldet,
#   feststellen, WAS verloren oder gefaehrdet ist — ohne einen einzigen
#   Feldinhalt auszugeben. Ausgegeben werden nur Zahlen: Zeilenanzahlen,
#   Zeilennummern (rowid), Seitennummern, Seitenarten.
#
#   1. Kopie der Datei (SHA-256 des Originals vorher/nachher).
#   2. integrity_check vollstaendig (gestaffelt, siehe integritaetssonde),
#      ungekuerzt ins Protokoll; Meldungen je Tabelle/Index gezaehlt.
#   3. Je Tabelle: Vollscan — lesbare Zeilen, rowid-Bereich, doppelte rowids;
#      bei AUTOINCREMENT der Zaehler aus sqlite_sequence und die fehlenden
#      Nummern darunter.
#   4. Verwaiste Seiten ('never used'): Seitenart und Eintragszahl.
#   5. JE TABELLE: Datensaetze auf ALLEN Tabellenblattseiten, die per
#      SIGNATUR passen (SeitenScanner.passt_zur_tabelle: Spaltenzahl UND
#      Speicherklassen je Spalte) und ueber den Baum NICHT gelesen wurden —
#      davon wie viele an fehlenden Zeilennummern liegen. Unabhaengig davon,
#      ob integrity_check laeuft (bricht er bei jeder Grenze ab, gibt es
#      keine Liste verwaister Seiten — gemessen an einer Testdatei, Build 776).
#
# BEFUND 14.10.2026 (Grund fuer Schritt 5): Die erste Fassung ordnete
#   verwaiste Datensaetze nur ueber Zeilennummern zu und meldete
#   'report_anchors: 2 von 2 fehlenden Nummern liegen auf verwaisten Seiten'.
#   Die Datensaetze hatten 2 Spalten — alte Fassungen von sqlite_sequence;
#   report_anchors hat 5. Der Treffer war falsch.
#
# Herkunft: am 14.10.2026 ausserhalb der Buildkette geliefert; ab Build 776
#   im Bestand, mit Schritt 5 statt des Zeilennummern-Abgleichs.
#
# Aufruf (Webserver des Falls BEENDET):
#   python tools/schadensanalyse.py <datei.db> [--protokoll-dir VERZ]
#
# Rueckgabewerte: 0 Analyse gelaufen (auch mit Befund — das IST das
#   Ergebnis); 1 Kopie unbrauchbar (Original waehrend des Kopierens
#   veraendert) oder nicht als SQLite lesbar; 2 Aufruffehler.
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
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.help import cli_epilog  # noqa: E402
from db.reparatur.hilfen import BEGLEIT, q, sha256  # noqa: E402
from db.reparatur.seitenscanner import SeitenScanner  # noqa: E402

SEITENART = {0x02: "Index innen", 0x05: "Tabelle innen",
             0x0A: "Index Blatt", 0x0D: "Tabelle Blatt"}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Schadensbild einer beschaedigten SQLite-Datei auf einer "
                    "KOPIE: nur Zahlen, keine Feldinhalte.",
        epilog=cli_epilog.epilog("schadensanalyse"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("datei", help="die zu untersuchende Datei")
    p.add_argument("--protokoll-dir", default=".", metavar="VERZEICHNIS",
                   help="wohin das Protokoll geschrieben wird (Vorgabe: .)")
    args = p.parse_args(argv)
    original = os.path.abspath(args.datei)
    if not os.path.isfile(original):
        print("FEHLER: Datei nicht gefunden: %s" % original, file=sys.stderr)
        return 2
    stempel = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs(args.protokoll_dir, exist_ok=True)
    pfad_prot = os.path.join(args.protokoll_dir, "schadensanalyse_%s.txt" % stempel)
    arbeit = tempfile.mkdtemp(prefix="aiw_schaden_")
    with open(pfad_prot, "w", encoding="utf-8") as prot:
        def aus(text="", nur_datei=False):
            if not nur_datei:
                print(text)
            prot.write(text + "\n")
        try:
            return _analyse(original, arbeit, aus, stempel, pfad_prot)
        finally:
            shutil.rmtree(arbeit, ignore_errors=True)


def _analyse(original, arbeit, aus, stempel, pfad_prot) -> int:
    aus("schadensanalyse (Build 776) %s  Python %s  SQLite %s" % (
        stempel, sys.version.split()[0], sqlite3.sqlite_version))
    aus("Datei: %s" % original)
    vorher = sha256(original)
    kopie = os.path.join(arbeit, os.path.basename(original))
    shutil.copy2(original, kopie)
    for s in BEGLEIT:
        if os.path.exists(original + s):
            shutil.copy2(original + s, kopie + s)
            aus("Begleitdatei mitkopiert: %s" % s)
    nachher = sha256(original)
    aus("SHA-256 Original vorher : %s" % vorher)
    aus("SHA-256 Original nachher: %s%s" % (nachher, "" if vorher == nachher
                                            else "   <-- ABWEICHUNG, Kopie unbrauchbar"))
    if vorher != nachher:
        return 1
    try:
        con = sqlite3.connect(kopie)
        groesse = con.execute("PRAGMA page_size").fetchone()[0]
        seiten = con.execute("PRAGMA page_count").fetchone()[0]
        frei = con.execute("PRAGMA freelist_count").fetchone()[0]
        tabellen, wurzeln = {}, {}
        for typ, name, wurzel in con.execute(
                "SELECT type, name, rootpage FROM sqlite_schema WHERE rootpage > 0"):
            wurzeln[wurzel] = "%s %s" % (typ, name)
            if typ == "table":
                info = con.execute("PRAGMA table_info(%s)" % q(name)).fetchall()
                tabellen[name] = [(r[1], r[2], r[3], r[5]) for r in info]
    except sqlite3.DatabaseError as exc:
        aus("Die Kopie ist nicht als SQLite lesbar: %s" % exc)
        return 1
    aus("Seitengroesse %d, Seiten %d, davon auf der Freiliste %d" % (groesse, seiten, frei))

    # --- integrity_check, ungekuerzt -----------------------------------------
    zeilen, grenze = None, None
    for g in (1000000, 1000, 100, 10):
        try:
            zeilen = [t for r in con.execute("PRAGMA integrity_check(%d)" % g).fetchall()
                      for t in str(r[0]).splitlines()]
            grenze = g
            break
        except sqlite3.DatabaseError as exc:
            aus("integrity_check(%d) bricht selbst ab: %s" % (g, exc))
    zeilen = zeilen or []
    aus("")
    aus("=== integrity_check: %d Zeilen%s (vollstaendig in der Protokolldatei)"
        % (len(zeilen), " (Grenze %d)" % grenze if grenze else ", nicht ausfuehrbar"))
    for z in zeilen:
        aus("  " + z, nur_datei=True)
    nie = sorted(int(n) for n in re.findall(r"Page (\d+): never used", "\n".join(zeilen)))
    for n, anzahl in sorted(Counter(int(n) for n in re.findall(
            r"Tree (\d+)", "\n".join(zeilen))).items()):
        aus("  Tree %d (%s): %d Meldung(en)" % (n, wurzeln.get(n, "unbekannt"), anzahl))
    aus("  Seiten 'never used': %d" % len(nie))

    # --- je Tabelle: Vollscan -------------------------------------------------
    aus("")
    aus("=== Tabellen (Vollscan der Kopie)")
    seq = {}
    try:
        seq = dict(con.execute("SELECT name, seq FROM sqlite_sequence"))
    except sqlite3.Error:
        pass
    fehlend_je, gelesen_je = {}, {}
    for name in sorted(tabellen):
        ids, fehler = [], None
        try:
            cur = con.execute("SELECT rowid FROM %s NOT INDEXED" % q(name))
            while True:
                try:
                    z = cur.fetchone()
                except sqlite3.DatabaseError as exc:
                    fehler = exc
                    break
                if z is None:
                    break
                ids.append(z[0])
        except sqlite3.DatabaseError as exc:
            fehler = exc
        gelesen_je[name] = set(ids)
        if fehler is not None:
            aus("  %-28s NICHT VOLLSTAENDIG LESBAR: %s (bis dahin %d Zeilen)"
                % (name, fehler, len(ids)))
            continue
        try:
            verschieden = set(ids)
            text = ("%-28s gelesen %7d, verschiedene rowids %7d, doppelt %d, "
                    "rowid %s..%s" % (name, len(ids), len(verschieden),
                                      len(ids) - len(verschieden),
                                      min(ids) if ids else "-", max(ids) if ids else "-"))
            if name in seq:
                fehlend = set(range(1, int(seq[name]) + 1)) - verschieden
                fehlend_je[name] = fehlend
                text += ", Zaehler %s, fehlende Nummern %d" % (seq[name], len(fehlend))
            aus("  " + text)
        except sqlite3.Error as exc:
            aus("  %-28s NICHT LESBAR: %s" % (name, exc))
    con.close()

    # --- verwaiste Seiten -----------------------------------------------------
    aus("")
    aus("=== Verwaiste Seiten ('never used'), je Seite")
    nie_set = set(nie)
    with open(kopie, "rb") as fh:
        for n in nie:
            fh.seek((n - 1) * groesse)
            seite = fh.read(groesse)
            k = 100 if n == 1 else 0
            art = seite[k]
            zellen = int.from_bytes(seite[k + 3:k + 5], "big")
            aus("  Seite %5d: %s, %d Eintraege" % (
                n, SEITENART.get(art, "keine B-Baum-Seite (0x%02x)" % art), zellen))

    # --- Zuordnung per Signatur -----------------------------------------------
    aus("")
    aus("=== Datensaetze auf den Datenseiten, per Signatur zugeordnet "
        "(Spaltenzahl und Speicherklassen), die im Vollscan NICHT "
        "gelesen wurden")
    funde, ueberlauf, unlesbar = SeitenScanner.datensaetze(kopie)
    aus("  %d Datensaetze dekodiert, %d mit Ueberlauf uebersprungen, %d nicht "
        "dekodierbar; %d davon auf verwaisten Seiten"
        % (len(funde), ueberlauf, unlesbar,
           sum(1 for f in funde if f[0] in nie_set)))
    ohne_tabelle = 0
    je_tabelle = {name: set() for name in tabellen}
    for _seite, rowid, typen, werte in funde:
        passende = [name for name, sp in tabellen.items()
                    if SeitenScanner.passt_zur_tabelle(typen, werte, sp)]
        if not passende:
            ohne_tabelle += 1
        for name in passende:
            if rowid not in gelesen_je.get(name, set()):
                je_tabelle[name].add(rowid)
    gemeldet = False
    for name in sorted(tabellen):
        ids = je_tabelle[name]
        if not ids:
            continue
        gemeldet = True
        text = "  %-28s %d passende Datensaetze nicht im Vollscan gelesen, " \
               "rowid %d..%d" % (name, len(ids), min(ids), max(ids))
        if name in fehlend_je:
            text += "; davon %d an fehlenden Nummern unter dem Zaehler" % len(
                ids & fehlend_je[name])
        aus(text)
    if not gemeldet:
        aus("  keine")
    aus("  %d Datensaetze passen zu keiner Tabelle des Schemas (z. B. alte "
        "Fassungen von sqlite_sequence)" % ohne_tabelle)
    aus("  HINWEIS: Ein passender Datensatz ist ein moeglicher Fund, kein "
        "Beleg — er kann auch eine alte Fassung einer spaeter geaenderten oder "
        "geloeschten Zeile sein (vgl. tools/evidence_reparatur.py).")
    aus("")
    aus("Protokoll: %s" % pfad_prot)
    return 0


if __name__ == "__main__":
    sys.exit(main())

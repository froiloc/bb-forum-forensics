# =============================================================================
# db/reparatur/tabellen_bergung.py
# IT-Forensisches Ermittlungswerkzeug — Bergung je Tabelle
# =============================================================================
# Zweck:
#   Liest eine Tabelle einer (moeglicherweise beschaedigten) SQLite-Datei auf
#   zwei Wegen:
#     a) Vollscan (alle Zeilen der Reihe nach) bis zum ersten Fehler,
#     b) Einzelzugriff je Zeilennummer (rowid) von 1 bis zur Obergrenze.
#        SQLite sucht dabei jede Zeile ueber den Baum von oben — ein
#        beschaedigter Ast versperrt so nur die Zeilen darunter, nicht den
#        Rest. Dieses Ergebnis gilt, wenn der Vollscan fuer dieselbe Nummer
#        etwas anderes lieferte.
#   'vollstaendig' heisst: beide Wege fehlerfrei und deckungsgleich, keine
#   Zeilennummer doppelt.
#
# Herkunft: tools/evidence_reparatur.py 1.2 (14.10.2026), Logik unveraendert.
# Version: v0.8.776 · Build: 776 · 2026-10-14
# =============================================================================
from __future__ import annotations

import sqlite3
from typing import Dict, List, Tuple

from db.reparatur.hilfen import q


class TabellenBergung:
    """Vollscan und Einzelzugriff einer Tabelle."""

    @staticmethod
    def bergen(con: sqlite3.Connection, name: str,
               oberste: int) -> Tuple[Dict[int, tuple], bool, List[str]]:
        """
        Rueckgabe: zeilen {rowid: tuple}, vollstaendig_lesbar, meldungen.
        """
        meldungen: List[str] = []
        scan, scan_fehler, doppelt_anders = {}, None, 0
        try:
            cur = con.execute("SELECT rowid, * FROM %s NOT INDEXED" % q(name))
            while True:
                try:
                    z = cur.fetchone()
                except sqlite3.DatabaseError as exc:
                    scan_fehler = str(exc)
                    break
                if z is None:
                    break
                if z[0] in scan:
                    # Eine Zeilennummer zweimal im Vollscan heisst: eine Seite
                    # haengt an zwei Stellen im Baum — und an ihrer eigenen
                    # Stelle fehlt dafuer eine andere. Auch bei gleichem Inhalt.
                    doppelt_anders += 1
                scan.setdefault(z[0], tuple(z[1:]))
        except sqlite3.DatabaseError as exc:
            scan_fehler = str(exc)
        if scan_fehler:
            meldungen.append("Vollscan bricht ab: %s (bis dahin %d Zeilen)"
                             % (scan_fehler, len(scan)))
        if doppelt_anders:
            meldungen.append("Vollscan liefert %d Zeilennummern doppelt (eine "
                             "Seite haengt doppelt im Baum)" % doppelt_anders)

        oberste = max([oberste] + list(scan.keys()) + [0])
        zeilen, seek_fehler = {}, 0
        for rowid in range(1, oberste + 1):
            try:
                z = con.execute("SELECT rowid, * FROM %s WHERE rowid = ?" % q(name),
                                (rowid,)).fetchone()
            except sqlite3.DatabaseError:
                seek_fehler += 1
                continue
            if z is not None:
                zeilen[rowid] = tuple(z[1:])
        # Was nur der Vollscan fand (Zeilennummern ausserhalb 1..oberste,
        # z. B. negative), wird uebernommen.
        for rowid, z in scan.items():
            zeilen.setdefault(rowid, z)
        if seek_fehler:
            meldungen.append("Einzelzugriff scheitert fuer %d Zeilennummern"
                             % seek_fehler)
        nur_scan_anders = sum(1 for r, z in scan.items() if zeilen.get(r) != z)
        if nur_scan_anders:
            meldungen.append("%d Zeilen lieferte der Vollscan anders als der "
                             "Einzelzugriff — der Einzelzugriff gilt" % nur_scan_anders)
        vollstaendig = (not scan_fehler and not doppelt_anders and not seek_fehler
                        and not nur_scan_anders and set(scan) == set(zeilen))
        return zeilen, vollstaendig, meldungen

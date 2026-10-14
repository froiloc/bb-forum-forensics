# =============================================================================
# tests/_reparatur_testdateien.py
# IT-Forensisches Ermittlungswerkzeug — kuenstlich beschaedigte Testdateien
# =============================================================================
# Baut evidence_<uid>.db mit dem ECHTEN Schema (EvidenceDb legt es an) und
# beschaedigt sie gezielt auf Byte-Ebene. Gebraucht von
# tests/test_evidence_reparatur.py (Build 776) und
# tests/test_evidence_startpruefung.py (Build 778).
#
# Beschaedigungen (SQLite-Dateiformat, sqlite.org/fileformat2.html):
#   abschneiden()  — der rechteste Kindzeiger der Wurzel einer Tabelle wird
#                    auf eine Indexseite umgebogen: das letzte Blatt ist vom
#                    Baum abgeschnitten (seine Zeilen nur noch per Seitenscan
#                    erreichbar); Lesen ueber den Baum endet mit
#                    'database disk image is malformed'. Optional wird der
#                    Zaehler in sqlite_sequence unter die abgeschnittenen
#                    Nummern gesenkt (Befund PROD 14.10.2026).
#   heisses_journal() — erzeugt eine Kopie MIT -journal einer unterbrochenen
#                    Transaktion (Seiten bereits in die Datei geschrieben).
#
# Version: v0.8.776 · Build: 776 · 2026-10-14
# =============================================================================
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.evidence_db import EvidenceDb  # noqa: E402


def bau_evidence(pfad, annotationen: int = 85, besuche: int = 2500,
                 sichtungen: int = 3000) -> None:
    """Datei mit echtem Schema und Testdaten (keine Falldaten)."""
    con = sqlite3.connect(str(pfad))
    EvidenceDb(con)
    for i in range(annotationen):
        con.execute(
            "INSERT INTO annotations (page_url, element_id, category, text, ts, "
            "investigator_id, selection_json, tags_json, local_id, post_id, "
            "created_by, deleted_at, version_nr, prev_id, actual_uid) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("http://f/forum/viewtopic.php?id=%d" % i, "p%d" % i, "CAT_TEST",
             "Notiz %d " % i * 6, 1000 + i, 1, "{}", "[]", "L%d" % i, i, "h0",
             None, 1, None, 4711))
    con.executemany(
        "INSERT INTO page_visits (page_url, scrape_context, ts, investigator_id) "
        "VALUES (?,?,?,?)",
        [("http://f/forum/viewtopic.php?id=%d" % (i % 300), "user", 2000 + i, 1)
         for i in range(besuche)])
    con.executemany(
        "INSERT INTO viewport_events (page_url, element_id, visible_ms, ts_enter, "
        "ts_leave, investigator_id) VALUES (?,?,?,?,?,?)",
        [("http://f/forum/viewtopic.php?id=%d" % (i % 50), "p%d" % i, 100 + i, i,
          i + 1, 1) for i in range(sichtungen)])
    con.commit()
    con.close()


def _varint(b, p):
    v = 0
    for i in range(9):
        x = b[p]
        p += 1
        if i == 8:
            return (v << 8) | x, p
        v = (v << 7) | (x & 0x7F)
        if not x & 0x80:
            return v, p
    return v, p


def abschneiden(pfad, tabelle: str, zaehler_senken: bool = False) -> dict:
    """
    Schneidet das rechteste Blatt der Tabelle vom Baum ab. Rueckgabe:
    {'abgeschnitten': [rowids], 'zaehler': neuer Zaehler oder None}.
    Voraussetzung: die Wurzel der Tabelle ist ein Innenknoten (0x05).
    """
    con = sqlite3.connect(str(pfad))
    wurzel = con.execute("SELECT rootpage FROM sqlite_schema WHERE name=?",
                         (tabelle,)).fetchone()[0]
    index = con.execute("SELECT rootpage FROM sqlite_schema WHERE type='index' "
                        "AND rootpage > 0 ORDER BY rootpage LIMIT 1").fetchone()[0]
    groesse = con.execute("PRAGMA page_size").fetchone()[0]
    con.close()
    daten = Path(pfad).read_bytes()

    def seite(n):
        return daten[(n - 1) * groesse:n * groesse]

    w = seite(wurzel)
    assert w[0] == 0x05, "Wurzel von %s ist kein Innenknoten" % tabelle
    rechts = int.from_bytes(w[8:12], "big")
    blatt = seite(rechts)
    assert blatt[0] == 0x0D, "rechtestes Kind ist kein Blatt"
    ids = []
    for i in range(int.from_bytes(blatt[3:5], "big")):
        off = int.from_bytes(blatt[8 + 2 * i:10 + 2 * i], "big")
        _, p = _varint(blatt, off)
        r, _ = _varint(blatt, p)
        ids.append(r)
    zaehler = None
    if zaehler_senken:
        zaehler = min(ids) - 1
        con = sqlite3.connect(str(pfad))
        con.execute("UPDATE sqlite_sequence SET seq=? WHERE name=?", (zaehler, tabelle))
        con.commit()
        con.close()
    with open(pfad, "r+b") as fh:
        fh.seek((wurzel - 1) * groesse + 8)
        fh.write(index.to_bytes(4, "big"))
    return {"abgeschnitten": sorted(ids), "zaehler": zaehler}


def erstes_blatt_zerstoeren(pfad, tabelle: str, zaehler_auf: int = None) -> dict:
    """
    Macht das ERSTE Blatt der Tabelle unlesbar (Seitentyp 0x0D -> 0x0A,
    Indexblatt): der Vollscan bricht gleich am Anfang ab, die Zeilen der
    uebrigen Blaetter bleiben per Einzelzugriff erreichbar. Optional wird der
    Zaehler auf 'zaehler_auf' gesenkt. Rueckgabe: {'zerstoert': [rowids]}.
    """
    con = sqlite3.connect(str(pfad))
    wurzel = con.execute("SELECT rootpage FROM sqlite_schema WHERE name=?",
                         (tabelle,)).fetchone()[0]
    groesse = con.execute("PRAGMA page_size").fetchone()[0]
    if zaehler_auf is not None:
        con.execute("UPDATE sqlite_sequence SET seq=? WHERE name=?", (zaehler_auf, tabelle))
        con.commit()
    con.close()
    daten = Path(pfad).read_bytes()
    w = daten[(wurzel - 1) * groesse:wurzel * groesse]
    assert w[0] == 0x05, "Wurzel von %s ist kein Innenknoten" % tabelle
    off = int.from_bytes(w[12:14], "big")          # erste Zelle des Innenknotens
    links = int.from_bytes(w[off:off + 4], "big")  # linker Kindzeiger
    blatt = daten[(links - 1) * groesse:links * groesse]
    assert blatt[0] == 0x0D
    ids = []
    for i in range(int.from_bytes(blatt[3:5], "big")):
        o = int.from_bytes(blatt[8 + 2 * i:10 + 2 * i], "big")
        _, p = _varint(blatt, o)
        r, _ = _varint(blatt, p)
        ids.append(r)
    with open(pfad, "r+b") as fh:
        fh.seek((links - 1) * groesse)
        fh.write(b"\x0a")
    return {"zerstoert": sorted(ids)}


def heisses_journal(quelle, ziel) -> None:
    """
    Kopie von 'quelle' nach 'ziel' MIT dem -journal einer unterbrochenen
    Transaktion: cache_size=1 zwingt SQLite, geaenderte Seiten schon VOR dem
    commit in die Datei zu schreiben; kopiert wird in diesem Zustand.
    Beim Oeffnen der Kopie rollt SQLite zurueck -> Inhalt wie 'quelle'.
    """
    con = sqlite3.connect(str(quelle))
    con.execute("PRAGMA cache_size=1")
    con.execute("BEGIN")
    con.execute("UPDATE viewport_events SET visible_ms = visible_ms + 1")
    shutil.copy2(str(quelle), str(ziel))
    shutil.copy2(str(quelle) + "-journal", str(ziel) + "-journal")
    con.rollback()
    con.close()


def inhalt(pfad) -> dict:
    """{Tabelle: [Zeilen nach rowid]} — zum Vergleich mit der Vorlage."""
    con = sqlite3.connect(str(pfad))
    try:
        aus = {}
        for (t,) in con.execute("SELECT name FROM sqlite_schema WHERE type='table' "
                                "AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            aus[t] = con.execute('SELECT rowid, * FROM "%s" ORDER BY rowid' % t).fetchall()
        return aus
    finally:
        con.close()

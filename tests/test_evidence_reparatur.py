# =============================================================================
# tests/test_evidence_reparatur.py
# IT-Forensisches Ermittlungswerkzeug — Reparatur und Sonden (Build 776)
# =============================================================================
# Prueft db/reparatur/ (EvidenceReparierer und Bausteine) und die Werkzeuge
# tools/evidence_reparatur.py, integritaetssonde.py, schadensanalyse.py,
# sperrsonde.py an kuenstlich beschaedigten Testdateien mit ECHTEM Schema
# (tests/_reparatur_testdateien.py).
#
#   ER01  abgeschnittenes Blatt in page_visits, Zaehler zu niedrig:
#         freigegeben, ALLE Zeilen zeilengleich mit der Vorlage, Zaehler
#         der neuen Datei = hoechste Nummer
#   ER02  abgeschnittenes Blatt in annotations: nicht_freigegeben,
#         sperren = ['annotations']; jede geborgene Annotation
#         zeilengleich, die abgeschnittenen fehlen und sind gezaehlt
#   ER03  unversehrte Datei: freigegeben, inhaltsgleich, nichts verloren
#   ER04  SHA-256-Abgleich: zweiter Lauf auf unveraenderter Datei legt
#         KEINE weitere Sicherung an; nach Aenderung wieder eine neue
#   ER05  das Original bleibt bytegleich
#   ER06  nicht als SQLite lesbar: status nicht_lesbar, keine neue Datei,
#         Protokoll vorhanden
#   ER07  Zielpruefung: Ordner des Originals abgewiesen; Laufwerkshinweis
#   ER08  Kommandozeile: Rueckgabewerte 0/3/2, Austauschbefehle nur bei
#         Freigabe
#   ER09  heisses Journal: wird mitgesichert und in der Arbeitskopie
#         zurueckgerollt — die neue Datei entspricht dem Stand VOR der
#         unterbrochenen Transaktion
#   ER10  Sonden: integritaetssonde (1/0), schadensanalyse (Funde per
#         Signatur), sperrsonde (Lesesperre erkannt / frei)
#   ER11  Einzelzugriff bis zur Obergrenze aus dem Seitenscan: Vollscan
#         bricht am ersten Blatt ab, Zaehler zu niedrig — die Zeilen UEBER
#         dem Zaehler in einer Nicht-Anhaengetabelle werden trotzdem ueber
#         den Baum geborgen (Gegenprobe M4 blieb ohne diesen Fall gruen)
#   ER12  Signaturpruefung SeitenScanner.passt_zur_tabelle unmittelbar
#         (Gegenprobe M7 blieb ohne diesen Fall gruen)
#
# Version: v0.8.776 · Build: 776 · 2026-10-14
# =============================================================================
from __future__ import annotations

import glob
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
sys.path.insert(0, str(WURZEL / "tests"))

import _reparatur_testdateien as T                           # noqa: E402
from db.reparatur import EvidenceReparierer                  # noqa: E402
from db.reparatur.hilfen import sha256                       # noqa: E402
from db.reparatur.reparatur_ziel import (                    # noqa: E402
    ReparaturZiel, ReparaturZielFehler)


def _werkzeug(name, *args, cwd=None):
    return subprocess.run([sys.executable, str(WURZEL / "tools" / name), *args],
                          capture_output=True, text=True, cwd=cwd or str(WURZEL),
                          timeout=300)


class _Basis(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="aiw_er_"))
        self.ziel = self.dir / "defekt"
        self.vorlage = self.dir / "vorlage.db"
        T.bau_evidence(self.vorlage)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _kaputt(self, tabelle, senken=False):
        p = self.dir / "evidence_7.db"
        shutil.copy2(self.vorlage, p)
        info = T.abschneiden(p, tabelle, zaehler_senken=senken)
        return p, info

    def _reparieren(self, p):
        return EvidenceReparierer(str(p), str(self.ziel)).ausfuehren()


class TestReparatur(_Basis):

    def test_er01_abgeschnitten_freigegeben_zeilengleich(self):
        p, info = self._kaputt("page_visits", senken=True)
        # Die Vorlage mit gesenktem Zaehler ist die Wahrheit (der Zaehler
        # selbst wird in der neuen Datei richtig gestellt).
        erg = self._reparieren(p)
        self.assertEqual(erg.status, "freigegeben")
        self.assertEqual(T.inhalt(erg.neu), T.inhalt(self.vorlage))
        con = sqlite3.connect(erg.neu)
        seq = dict(con.execute("SELECT name, seq FROM sqlite_sequence"))
        con.close()
        self.assertEqual(seq["page_visits"], max(info["abgeschnitten"]))
        # Die abgeschnittenen Zeilen kamen aus dem Seitenscan (der Baum
        # erreicht sie nicht mehr) — gemessen: alle.
        self.assertEqual(
            erg.daten["tabellen"]["page_visits"]["aus_seitenscan_uebernommen"],
            info["abgeschnitten"])

    def test_er02_annotations_beschaedigt_nicht_freigegeben(self):
        p, info = self._kaputt("annotations")
        erg = self._reparieren(p)
        self.assertEqual(erg.status, "nicht_freigegeben")
        self.assertEqual(erg.sperren, ["annotations"])
        wahr = {r[0]: r for r in T.inhalt(self.vorlage)["annotations"]}
        neu = {r[0]: r for r in T.inhalt(erg.neu)["annotations"]}
        for rowid, zeile in neu.items():
            self.assertEqual(zeile, wahr[rowid])
        fehlend = sorted(set(wahr) - set(neu))
        # Abgeschnitten = nicht ueber den Baum erreichbar; der Einzelzugriff
        # kann die erste Nummer des Blatts noch erreichen (Grenzschluessel im
        # Innenknoten). Jede fehlende Nummer ist abgeschnitten UND gezaehlt.
        self.assertTrue(fehlend)
        self.assertTrue(set(fehlend) <= set(info["abgeschnitten"]))
        self.assertEqual(erg.verloren["annotations"], len(fehlend))

    def test_er03_unversehrt(self):
        p = self.dir / "evidence_8.db"
        shutil.copy2(self.vorlage, p)
        erg = self._reparieren(p)
        self.assertEqual(erg.status, "freigegeben")
        self.assertEqual(T.inhalt(erg.neu), T.inhalt(self.vorlage))
        self.assertEqual(erg.verloren, {})
        self.assertEqual(erg.sperren, [])

    def test_er04_sha_abgleich_keine_doppelte_sicherung(self):
        p, _ = self._kaputt("page_visits")
        e1 = EvidenceReparierer(str(p), str(self.ziel), zeitstempel="20261014_100000").ausfuehren()
        e2 = EvidenceReparierer(str(p), str(self.ziel), zeitstempel="20261014_100001").ausfuehren()
        self.assertTrue(e1.sicherung.neu_angelegt)
        self.assertFalse(e2.sicherung.neu_angelegt)
        self.assertEqual(e2.sicherung.pfad, e1.sicherung.pfad)
        self.assertEqual(len(glob.glob(str(self.ziel / "*_defekt_*.db"))), 1)
        # Datei geaendert -> neue Sicherung
        with open(p, "ab") as fh:
            fh.write(b"\0" * 4096)
        e3 = EvidenceReparierer(str(p), str(self.ziel), zeitstempel="20261014_100002").ausfuehren()
        self.assertTrue(e3.sicherung.neu_angelegt)
        self.assertEqual(len(glob.glob(str(self.ziel / "*_defekt_*.db"))), 2)

    def test_er04b_manipulierte_sicherung_wird_nicht_wiederverwendet(self):
        p, _ = self._kaputt("page_visits")
        e1 = EvidenceReparierer(str(p), str(self.ziel), zeitstempel="20261014_100000").ausfuehren()
        with open(e1.sicherung.pfad, "r+b") as fh:       # Sicherung verfaelscht
            fh.seek(200)
            fh.write(b"XX")
        e2 = EvidenceReparierer(str(p), str(self.ziel), zeitstempel="20261014_100001").ausfuehren()
        self.assertTrue(e2.sicherung.neu_angelegt)

    def test_er05_original_bytegleich(self):
        p, _ = self._kaputt("annotations")
        vorher = sha256(p)
        self._reparieren(p)
        self.assertEqual(sha256(p), vorher)

    def test_er06_nicht_lesbar(self):
        p = self.dir / "evidence_9.db"
        shutil.copy2(self.vorlage, p)
        with open(p, "r+b") as fh:                       # sqlite_schema zerstoert
            fh.seek(100)
            fh.write(b"\xff" * 400)
        erg = self._reparieren(p)
        self.assertEqual(erg.status, "nicht_lesbar")
        self.assertIsNone(erg.neu)
        self.assertEqual(glob.glob(str(self.ziel / "*_repariert_*.db")), [])
        self.assertIn("ABBRUCH", Path(erg.protokoll_txt).read_text(encoding="utf-8"))

    def test_er07_zielpruefung(self):
        p = self.dir / "evidence_8.db"
        shutil.copy2(self.vorlage, p)
        with self.assertRaises(ReparaturZielFehler):
            ReparaturZiel.pruefen(str(p), str(self.dir), "test")
        ReparaturZiel.pruefen(str(p), str(self.ziel), "test")
        self.assertIsNotNone(ReparaturZiel.laufwerksbezug("/data/x", windows=True))
        self.assertIsNone(ReparaturZiel.laufwerksbezug("\\\\srv\\x", windows=True))
        self.assertIsNone(ReparaturZiel.laufwerksbezug("./data", windows=True))
        self.assertIsNone(ReparaturZiel.laufwerksbezug("/data/x", windows=False))

    def test_er11_einzelzugriff_ueber_den_zaehler(self):
        p = self.dir / "evidence_11.db"
        shutil.copy2(self.vorlage, p)
        info = T.erstes_blatt_zerstoeren(p, "annotations", zaehler_auf=40)
        erg = self._reparieren(p)
        self.assertEqual(erg.status, "nicht_freigegeben")
        neu = {r[0] for r in T.inhalt(erg.neu)["annotations"]}
        wahr = {r[0] for r in T.inhalt(self.vorlage)["annotations"]}
        # Alles ausser dem zerstoerten ersten Blatt ist da — AUCH 41..85,
        # die ueber dem gesenkten Zaehler liegen.
        self.assertEqual(neu, wahr - set(info["zerstoert"]))
        self.assertTrue({r for r in neu if r > 40})

    def test_er12_signatur(self):
        from db.reparatur.seitenscanner import SeitenScanner as S
        sp = [("id", "INTEGER", 0, 1), ("page_url", "TEXT", 1, 0),
              ("ts", "INTEGER", 1, 0), ("notiz", "TEXT", 0, 0)]
        ok = ([0, 33, 1, 0], [None, "http://f/x", 5, None])
        self.assertTrue(S.passt_zur_tabelle(*ok, sp))
        # INTEGER PRIMARY KEY muss als NULL im Datensatz stehen
        self.assertFalse(S.passt_zur_tabelle([1, 33, 1, 0], [7, "http://f/x", 5, None], sp))
        # TEXT-Spalte mit Ganzzahl
        self.assertFalse(S.passt_zur_tabelle([0, 33, 1, 1], [None, "http://f/x", 5, 3], sp))
        # NOT NULL mit NULL
        self.assertFalse(S.passt_zur_tabelle([0, 33, 0, 0], [None, "http://f/x", None, None], sp))
        # page_url muss mit http oder / beginnen
        self.assertFalse(S.passt_zur_tabelle([0, 25, 1, 0], [None, "abcdef", 5, None], sp))
        # Spaltenzahl (alte sqlite_sequence-Fassung: 2 Spalten)
        self.assertFalse(S.passt_zur_tabelle([23, 1], ["page_visits", 7], sp))

    def test_er09_heisses_journal(self):
        p = self.dir / "evidence_10.db"
        T.heisses_journal(self.vorlage, p)
        self.assertTrue(os.path.exists(str(p) + "-journal"))
        erg = self._reparieren(p)
        self.assertIn("-journal", erg.sicherung.begleit)
        self.assertTrue(os.path.exists(erg.sicherung.pfad + "-journal"))
        self.assertEqual(erg.status, "freigegeben")
        self.assertEqual(T.inhalt(erg.neu), T.inhalt(self.vorlage))


class TestKommandozeile(_Basis):

    def test_er08_rueckgabewerte_und_austausch(self):
        p, _ = self._kaputt("page_visits")
        r = _werkzeug("evidence_reparatur.py", str(p), "--ziel", str(self.ziel))
        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr)
        self.assertIn("AUSTAUSCH (von Hand", r.stdout)
        q, _ = self._kaputt("annotations")
        r = _werkzeug("evidence_reparatur.py", str(q), "--ziel", str(self.dir / "z2"))
        self.assertEqual(r.returncode, 3, r.stdout[-800:])
        self.assertNotIn("AUSTAUSCH (von Hand", r.stdout)
        r = _werkzeug("evidence_reparatur.py", str(q), "--ziel", str(self.dir))
        self.assertEqual(r.returncode, 2)
        self.assertIn("Ordner des Originals", r.stderr)
        r = _werkzeug("evidence_reparatur.py", "--uid", "1", str(q))
        self.assertEqual(r.returncode, 2)          # argparse: beides zugleich


class TestSonden(_Basis):

    def test_er10a_integritaetssonde(self):
        p, _ = self._kaputt("page_visits")
        r = _werkzeug("integritaetssonde.py", str(p), "--protokoll-dir", str(self.dir))
        self.assertEqual(r.returncode, 1, r.stdout[-600:])
        self.assertIn("1 mit Befund", r.stdout)
        r = _werkzeug("integritaetssonde.py", str(self.vorlage),
                      "--protokoll-dir", str(self.dir))
        self.assertEqual(r.returncode, 0, r.stdout[-600:])
        self.assertIn("1 ok, 0 mit Befund", r.stdout)

    def test_er10b_schadensanalyse_signatur(self):
        p, info = self._kaputt("page_visits")
        r = _werkzeug("schadensanalyse.py", str(p), "--protokoll-dir", str(self.dir))
        self.assertEqual(r.returncode, 0, r.stdout[-600:])
        zeile = [z for z in r.stdout.splitlines()
                 if z.strip().startswith("page_visits") and "passende" in z]
        self.assertEqual(len(zeile), 1, r.stdout[-1500:])
        self.assertIn("rowid", zeile[0])
        self.assertIn(str(max(info["abgeschnitten"])), zeile[0])
        # Kein Feldinhalt in der Ausgabe
        self.assertNotIn("viewtopic", r.stdout)

    def test_er10c_sperrsonde(self):
        db = self.dir / "coordinator.db"
        con = sqlite3.connect(str(db))
        con.execute("CREATE TABLE t (a)")
        con.execute("INSERT INTO t VALUES (1)")
        con.commit()
        con.close()
        r = _werkzeug("sperrsonde.py", "--db", str(db), "--durchgaenge", "1")
        self.assertEqual(r.returncode, 0, r.stdout)
        halter = sqlite3.connect(str(db), isolation_level=None, check_same_thread=False)
        halter.execute("BEGIN")
        halter.execute("SELECT * FROM t").fetchall()       # SHARED-Sperre
        try:
            r = _werkzeug("sperrsonde.py", "--db", str(db), "--durchgaenge", "1")
        finally:
            halter.execute("COMMIT")
            halter.close()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("IMMEDIATE=frei", r.stdout)
        self.assertIn("EXCLUSIVE=GESPERRT", r.stdout)


if __name__ == "__main__":
    unittest.main()

# =============================================================================
# tests/test_backup_pruefer.py
# IT-Forensisches Ermittlungswerkzeug - Datensicherung
# =============================================================================
# Testsuite fuer Build 626: die Nachschau im Sicherungsordner.
#
# WAS HIER AUF DEM SPIEL STEHT: Dieses Bauteil beantwortet die einzige Frage,
# auf die es im Ernstfall ankommt - liegt von dieser Datenbank ueberhaupt noch
# eine brauchbare Sicherung da? Eine Pruefung, die das zu optimistisch
# beantwortet, ist schlimmer als keine: sie erzeugt Vertrauen, das nicht
# gedeckt ist.
#
# SP01 - eine gute Sicherung wird als brauchbar erkannt
# SP02 - eine 0-Byte-Datei nicht (sie besteht integrity_check - das wird hier
#        zuerst BELEGT und dann widerlegt)
# SP03 - eine Teildatei mit heissem Journal wird als Abbruch erkannt UND
#        NICHT GEOEFFNET: sie liegt danach unveraendert da
# SP04 - eine beiseitegelegte Datei ('.defekt') zaehlt nicht als Generation
# SP05 - kein Wort ueber Dateien, die nicht der Namenskonvention folgen
# SP06 - 'ohne brauchbare Sicherung' ist der Ernstfall und faerbt den
#        Rueckgabewert auf 2
# SP07 - Rueckgabewerte in der Ordnung ihrer Schwere: 0 / 1 / 2 / 3
# SP08 - Pruefsummen: nur auf Wunsch; eine abweichende Summe macht die
#        Sicherung UNBRAUCHBAR; nicht geprueft ist von 'stimmt' zu
#        unterscheiden
# SP09 - registriert, aber nicht da - die Gegenrichtung
# SP10 - der Bericht nennt, was er NICHT geprueft hat (Grundregel 1)
# SP11 - der Bericht ist ASCII und haelt 78 Zeichen
# SP12 - das JSON traegt dieselben Aussagen wie der Text
# SP13 - REIN LESEND: nach einer vollstaendigen Pruefung ist keine Datei im
#        Ordner veraendert
#
# Version: v0.8.626 - Build: 626 - 2026-08-01
# =============================================================================

import hashlib
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.backup.backup_executor import DEFEKT_ENDUNG
from management.backup.backup_pruefer import (
    RC_BEFUND, RC_OHNE_SICHERUNG, RC_OK, RC_UNLESBAR,
    SicherungsPruefer, bericht_json, bericht_text,
)
from management.migration_fleet.harness.hashing import sha512_file


def _mkdb(path, user_version=5, rows=50):
    con = sqlite3.connect(str(path))
    try:
        con.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
        con.executemany("INSERT INTO t(v) VALUES(?)",
                        [("x" * 40,) for _ in range(rows)])
        con.execute("PRAGMA user_version=%d" % user_version)
        con.commit()
    finally:
        con.close()


def _fingerabdruck(verzeichnis):
    """Name -> (Groesse, Inhaltssumme). Fuer SP13."""
    raus = {}
    for n in sorted(os.listdir(verzeichnis)):
        p = os.path.join(verzeichnis, n)
        with open(p, "rb") as fh:
            raus[n] = (os.path.getsize(p), hashlib.sha256(fh.read()).hexdigest())
    return raus


class SicherungsPrueferTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.dir = os.path.join(self._tmp, "backups")
        os.mkdir(self.dir)

    def tearDown(self):
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    # ---------------------------------------------------------- Vorrichtung
    def _gut(self, label="coordinator", ts="20260101T000000Z", version=5):
        p = Path(self.dir) / ("%s_v%d_%s_host.backup.db" % (label, version, ts))
        _mkdb(p, user_version=version)
        return str(p)

    def _leer(self, label="coordinator", ts="20260102T000000Z", version=5):
        p = Path(self.dir) / ("%s_v%d_%s_host.backup.db" % (label, version, ts))
        p.write_bytes(b"")
        return str(p)

    def _teildatei_mit_journal(self, label="coordinator",
                               ts="20260103T000000Z", version=5):
        """
        Der Abbruchrest, so wie er auf der Platte aussieht: eine Datei plus
        ein heisses Journal daneben. Der Inhalt ist hier eine gueltige
        Datenbank - gerade DAS macht den Fall gefaehrlich: ohne das Journal
        anzusehen wuerde sie als brauchbar durchgehen.
        """
        p = Path(self.dir) / ("%s_v%d_%s_host.backup.db" % (label, version, ts))
        _mkdb(p, user_version=version)
        (Path(str(p) + "-journal")).write_bytes(b"\x00" * 1024)
        return str(p)

    # --- SP01 ---------------------------------------------------------------
    def test_sp01_gute_sicherung_ist_brauchbar(self):
        self._gut()
        b = SicherungsPruefer(self.dir).pruefen()
        self.assertTrue(b.lesbar)
        self.assertEqual(1, len(b.labels))
        l = b.labels[0]
        self.assertEqual("coordinator", l.label)
        self.assertEqual(1, len(l.brauchbar))
        self.assertFalse(l.ohne_sicherung)
        self.assertEqual("20260101T000000Z", l.juengste.ts)
        self.assertEqual(RC_OK, b.rueckgabewert())

    # --- SP02 ---------------------------------------------------------------
    def test_sp02_leere_datei_besteht_integrity_check_zaehlt_aber_nicht(self):
        """
        ZUERST BELEGEN, DANN WIDERLEGEN. Ohne den ersten Teil waere die
        Aussage 'integrity_check genuegt nicht' nur eine Behauptung.
        """
        pfad = self._leer()
        con = sqlite3.connect(pfad)
        try:
            self.assertEqual([("ok",)],
                             con.execute("PRAGMA integrity_check").fetchall())
        finally:
            con.close()

        self._gut()
        b = SicherungsPruefer(self.dir).pruefen()
        l = b.labels[0]
        self.assertEqual(1, len(l.brauchbar))
        self.assertEqual(1, len(l.unbrauchbar))
        self.assertIn("0 Byte", l.unbrauchbar[0].grund)

    # --- SP03 ---------------------------------------------------------------
    def test_sp03_heisses_journal_wird_erkannt_und_die_datei_nicht_geoeffnet(self):
        """
        DER WICHTIGSTE EINZELFALL. Gemessen am 2026-08-01: wird eine
        Teildatei mit heissem Journal gewoehnlich geoeffnet, spielt SQLite
        das Journal zurueck und verkuerzt sie - aus 34 MB werden 0 Byte. Eine
        Pruefung, die den Beleg vernichtet, den sie beurteilen soll, ist
        keine.
        """
        pfad = self._teildatei_mit_journal()
        vorher = _fingerabdruck(self.dir)

        b = SicherungsPruefer(self.dir).pruefen()

        l = b.labels[0]
        self.assertEqual(0, len(l.brauchbar))
        self.assertEqual(1, len(l.unbrauchbar))
        self.assertIn("heisses Journal", l.unbrauchbar[0].grund)
        self.assertEqual(vorher, _fingerabdruck(self.dir),
                         "die Pruefung hat den Beleg veraendert")

    # --- SP04 ---------------------------------------------------------------
    def test_sp04_beiseitegelegte_datei_zaehlt_nicht(self):
        self._gut()
        p = Path(self.dir) / ("coordinator_v5_20260104T000000Z_host.backup.db"
                              + DEFEKT_ENDUNG)
        _mkdb(p)
        b = SicherungsPruefer(self.dir).pruefen()
        l = b.labels[0]
        self.assertEqual(1, len(l.brauchbar))
        self.assertEqual(1, len(l.beiseite))
        self.assertIn("beiseitegelegt", l.beiseite[0].grund)
        self.assertEqual(RC_BEFUND, b.rueckgabewert())

    # --- SP05 ---------------------------------------------------------------
    def test_sp05_fremde_dateien_bleiben_unerwaehnt(self):
        self._gut()
        (Path(self.dir) / "manifest_20260101T000000Z_host.json").write_text("{}")
        (Path(self.dir) / "notiz.txt").write_text("nichts")
        b = SicherungsPruefer(self.dir).pruefen()
        namen = [d.name for l in b.labels
                 for d in list(l.brauchbar) + list(l.unbrauchbar)]
        self.assertEqual(1, len(namen))
        self.assertTrue(namen[0].endswith(".backup.db"))

    # --- SP06 ---------------------------------------------------------------
    def test_sp06_ohne_brauchbare_sicherung_ist_der_ernstfall(self):
        self._leer(label="evidence_18", ts="20260101T000000Z", version=3)
        self._gut()
        b = SicherungsPruefer(self.dir).pruefen()
        self.assertEqual(("evidence_18",), b.ohne_sicherung)
        self.assertEqual(RC_OHNE_SICHERUNG, b.rueckgabewert())
        # Und er steht ganz oben im Bericht, nicht am Ende einer langen Liste.
        text = bericht_text(b)
        self.assertIn("OHNE BRAUCHBARE SICHERUNG", text)
        self.assertLess(text.index("OHNE BRAUCHBARE SICHERUNG"),
                        text.index("Datenbank "))

    # --- SP07 ---------------------------------------------------------------
    def test_sp07_rueckgabewerte_nach_schwere(self):
        leer_dir = os.path.join(self._tmp, "gibtsnicht")
        self.assertEqual(RC_UNLESBAR,
                         SicherungsPruefer(leer_dir).pruefen().rueckgabewert())

        self._gut()
        self.assertEqual(RC_OK,
                         SicherungsPruefer(self.dir).pruefen().rueckgabewert())

        self._leer()
        self.assertEqual(RC_BEFUND,
                         SicherungsPruefer(self.dir).pruefen().rueckgabewert())

        self._leer(label="evidence_18", ts="20260101T000000Z", version=3)
        self.assertEqual(RC_OHNE_SICHERUNG,
                         SicherungsPruefer(self.dir).pruefen().rueckgabewert())

    # --- SP08 ---------------------------------------------------------------
    def test_sp08_pruefsummen_nur_auf_wunsch(self):
        pfad = self._gut()
        summen = {pfad: sha512_file(pfad)}

        ohne = SicherungsPruefer(self.dir).pruefen(registrierte=summen)
        self.assertFalse(ohne.pruefsummen_geprueft)
        self.assertIsNone(ohne.labels[0].brauchbar[0].pruefsumme_stimmt,
                          "'nicht geprueft' darf nicht wie 'stimmt' aussehen")

        mit = SicherungsPruefer(self.dir).pruefen(registrierte=summen,
                                                  mit_pruefsummen=True)
        self.assertTrue(mit.pruefsummen_geprueft)
        self.assertTrue(mit.labels[0].brauchbar[0].pruefsumme_stimmt)

    def test_sp08b_abweichende_pruefsumme_macht_unbrauchbar(self):
        """
        Streng, und mit Absicht: eine Sicherung, die nicht mehr die ist, die
        zertifiziert wurde, ist keine. Im Ernstfall gibt es keine
        Gelegenheit mehr, das zu klaeren.
        """
        pfad = self._gut()
        b = SicherungsPruefer(self.dir).pruefen(
            registrierte={pfad: "00" * 64}, mit_pruefsummen=True)
        l = b.labels[0]
        self.assertEqual(0, len(l.brauchbar))
        self.assertEqual(1, len(l.unbrauchbar))
        self.assertFalse(l.unbrauchbar[0].pruefsumme_stimmt)
        self.assertIn("Pruefsumme", l.unbrauchbar[0].grund)
        self.assertEqual(RC_OHNE_SICHERUNG, b.rueckgabewert())

    # --- SP09 ---------------------------------------------------------------
    def test_sp09_registriert_aber_nicht_da(self):
        self._gut()
        weg = os.path.join(self.dir,
                           "coordinator_v5_20251231T000000Z_host.backup.db")
        b = SicherungsPruefer(self.dir).pruefen(registrierte={weg: "abc"})
        self.assertIn(weg, b.fehlende_dateien)
        self.assertEqual(RC_BEFUND, b.rueckgabewert())
        self.assertIn("NICHT vorhanden", bericht_text(b))

    # --- SP10 ---------------------------------------------------------------
    def test_sp10_der_bericht_nennt_seine_grenzen(self):
        """
        Ohne diesen Abschnitt liest sich ein '0 Befunde' als Zusicherung, die
        diese Pruefung nicht geben kann.
        """
        self._gut()
        text = bericht_text(SicherungsPruefer(self.dir).pruefen())
        self.assertIn("Was hier NICHT geprueft ist", text)
        self.assertIn("--pruefsummen", text)
        self.assertIn("2785556a", text)          # kein erprobter Rueckweg

    def test_sp10b_mit_pruefsummen_entfaellt_der_passende_vorbehalt(self):
        pfad = self._gut()
        text = bericht_text(SicherungsPruefer(self.dir).pruefen(
            registrierte={pfad: sha512_file(pfad)}, mit_pruefsummen=True))
        self.assertIn("Pruefsummen gegengerechnet: ja", text)
        self.assertNotIn("Dafuer '--pruefsummen' setzen", text)

    # --- SP11 ---------------------------------------------------------------
    def test_sp11_ascii_und_78_zeichen(self):
        self._gut()
        self._leer()
        self._teildatei_mit_journal()
        self._gut(label="evidence_18", ts="20260105T000000Z", version=3)
        text = bericht_text(SicherungsPruefer(self.dir).pruefen())
        for zeile in text.split("\n"):
            self.assertTrue(zeile.isascii(), zeile)
            self.assertLessEqual(len(zeile), 78, zeile)

    # --- SP12 ---------------------------------------------------------------
    def test_sp12_json_traegt_dieselben_aussagen(self):
        self._gut()
        self._leer(label="evidence_18", ts="20260101T000000Z", version=3)
        b = SicherungsPruefer(self.dir).pruefen()
        d = bericht_json(b)
        self.assertEqual(b.rueckgabewert(), d["rueckgabewert"])
        self.assertEqual(list(b.ohne_sicherung),
                         d["ohne_brauchbare_sicherung"])
        self.assertEqual(len(b.labels), len(d["labels"]))
        self.assertFalse(d["pruefsummen_geprueft"])

    # --- SP13 ---------------------------------------------------------------
    def test_sp13_rein_lesend(self):
        """
        DIE ZUSAGE DES MODULKOPFES, GEMESSEN. Ein Werkzeug, das eine Lage
        beurteilen soll, darf sie nicht veraendern - und bei SQLite ist das
        keine Selbstverstaendlichkeit: das blosse Oeffnen einer Datei mit
        heissem Journal schreibt.
        """
        self._gut()
        self._leer()
        self._teildatei_mit_journal()
        self._gut(label="evidence_18", ts="20260105T000000Z", version=3)
        p = Path(self.dir) / ("assets_9_v2_20260106T000000Z_host.backup.db"
                              + DEFEKT_ENDUNG)
        _mkdb(p, user_version=2)

        vorher = _fingerabdruck(self.dir)
        SicherungsPruefer(self.dir).pruefen(
            registrierte={}, mit_pruefsummen=True)
        self.assertEqual(vorher, _fingerabdruck(self.dir))


if __name__ == "__main__":
    unittest.main()

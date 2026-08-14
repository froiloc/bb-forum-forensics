# =============================================================================
# tests/test_migration_rueckweg.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite zum Vorgang 69ede1c7 — "Rueckweg der Flottenmigration prueft die
# Exklusivitaet nicht".
#
# WAS HIER FESTGEHALTEN WIRD, UND WARUM ES EINE SPERRE IST:
#   Der Rueckweg ist der Pfad, der im FEHLERFALL laeuft. Er wird im Betrieb
#   also fast nie beobachtet — und genau deshalb konnte eine ungepruefte
#   Voraussetzung dort zwei Jahre unbemerkt stehen. Ein Test ist hier nicht
#   Beiwerk, sondern das einzige Auge, das diesen Pfad regelmaessig ansieht.
#
#   RW01  Ruhige Zieldatei -> zurueckgespielt; Inhalt entspricht der Sicherung.
#   RW02  BELEGTE Zieldatei -> NICHT kopiert; Zieldatei bytegleich wie vorher.
#   RW03  NICHT MESSBAR -> ebenfalls verweigert (nicht messbar ist keine Ruhe),
#         und mit einem ANDEREN Handlungshinweis als bei 'belegt'.
#   RW04  Sicherung fehlt -> verweigert statt Ausnahme (die Ausnahme waere im
#         except-Block des Ausfuehrers geflogen und haette die Flotte gerissen).
#   RW05  Sicherung veraendert (SHA512 stimmt nicht) -> verweigert.
#   RW06  Seitendateien: bei Ausfuehrung entfernt, bei Verweigerung NICHT.
#   RW07  Kopierfehler -> 'kopierfehler', Zustand ausdruecklich UNBESTIMMT.
#   RW08  ECHTE MESSUNG gegen einen echten Halter — ohne injizierten Pruefer.
#   RW09  Der Befund weist unstimmige Eingaben zurueck.
#   RW10  Ausfuehrer: Rueckweg verweigert -> Status 'failed_not_restored',
#         Laufbuch traegt 'failed' + 'restore_refused' und NICHT 'restored'.
#   RW11  Ausfuehrer: Rueckweg laeuft -> unveraenderte Wirkung wie bisher
#         ('failed_restored', 'restored'), damit die Behebung den Normalfall
#         nicht verschiebt.
#   RW12  Laufbuch: 'restore_refused' ist ein TERMINAL-Status — ein solcher
#         Lauf gilt nicht als unterbrochen, und die Kette bleibt heil.
#   RW13  Companion/CLI: der Rueckstand wird beim Namen genannt und faellt
#         nicht als Erfolg durch.
#
# Beleg: Vorgang 69ede1c7-3fe1-47eb-9d9a-f0cf6468f7dc; management/migration_
#        fleet/rueckweg.py; maintenance/cli_support.py (exklusiv_beurteilen).
# Version: v0.8.723 · Build: 723 · 2026-08-14
# =============================================================================

import importlib
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maintenance.exklusiv_befund import (BELEGT, ExklusivBefund,
                                         NICHT_MESSBAR, RUHIG)
from management.migration_fleet.catalog import CatalogReconciler
from management.migration_fleet.companion import MigrationCompanion
from management.migration_fleet.executor import FEHLERSTATUS, FleetExecutor
from management.migration_fleet.harness.hashing import sha512_file
from management.migration_fleet.ledger import MigrationLedger
from management.migration_fleet.migration_db import MigrationDb
from management.migration_fleet.planner import TargetDb
from management.migration_fleet.rueckweg import Rueckweg
from management.migration_fleet.rueckweg_befund import (
    KOPIERFEHLER, RueckwegBefund, RueckwegBefundError, VERWEIGERT,
    ZURUECKGESPIELT,
)

# Eine Migration, die Daten loescht: der Lossless-Verify des Harness schlaegt
# an, der Ausfuehrer geht in den Fehlerpfad — und damit in den Rueckweg.
_BAD_LOSS_M002 = '''
VERSION = 2
NAME = "bad-loss (loescht Daten)"
KIND = "additive"
def up(con):
    con.execute("DELETE FROM annotations")
'''


def _pruefer(zustand, grund="Testmessung"):
    """
    Ein injizierbarer Pruefer mit festem Ausgang.

    Er ist bewusst so klein: Was hier geprueft wird, ist NICHT die Sperrprobe
    (die hat ihre eigene Suite in tests/test_maintenance_*), sondern die
    Frage, was der Rueckweg AUS ihrem Ergebnis macht.
    """
    return lambda pfad: ExklusivBefund(str(pfad), zustand, grund)


class RueckwegTests(unittest.TestCase):
    """Der Rueckweg-Baustein fuer sich genommen."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.ziel = os.path.join(self._tmp, "evidence_4711.db")
        self.sicherung = os.path.join(self._tmp, "evidence_4711.backup.db")
        Path(self.ziel).write_bytes(b"NEUER STAND (nach der Migration)")
        Path(self.sicherung).write_bytes(b"ALTER STAND (die Sicherung)")
        self.sicherung_sha = sha512_file(self.sicherung)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    # RW01 ------------------------------------------------------------------
    def test_rw01_ruhige_zieldatei_wird_zurueckgespielt(self):
        b = Rueckweg(pruefer=_pruefer(RUHIG, "exklusiv erhalten")).zurueckspielen(
            self.ziel, self.sicherung, sicherung_sha512=self.sicherung_sha)
        self.assertTrue(b.ausgefuehrt)
        self.assertEqual(b.zustand, ZURUECKGESPIELT)
        self.assertEqual(Path(self.ziel).read_bytes(),
                         b"ALTER STAND (die Sicherung)")
        # Die Sicherung wird NIE angefasst.
        self.assertEqual(sha512_file(self.sicherung), self.sicherung_sha)

    # RW02 ------------------------------------------------------------------
    def test_rw02_belegte_zieldatei_wird_nicht_ueberschrieben(self):
        vorher = Path(self.ziel).read_bytes()
        b = Rueckweg(pruefer=_pruefer(BELEGT, "database is locked")
                     ).zurueckspielen(self.ziel, self.sicherung,
                                      sicherung_sha512=self.sicherung_sha)
        self.assertFalse(b.ausgefuehrt)
        self.assertEqual(b.zustand, VERWEIGERT)
        self.assertTrue(b.zieldatei_unberuehrt)
        # DER KERN DES VORGANGS: nichts kopiert.
        self.assertEqual(Path(self.ziel).read_bytes(), vorher)
        self.assertTrue(os.path.exists(self.sicherung))
        self.assertEqual(sha512_file(self.sicherung), self.sicherung_sha)
        # Die Ansage muss beide Pfade und die Messung nennen — ohne sie
        # wuesste niemand, was von Hand zu tun ist.
        self.assertIn(self.ziel, b.klartext)
        self.assertIn(self.sicherung, b.klartext)
        self.assertIn("database is locked", b.klartext)
        self.assertIn("NICHTS kopiert", b.klartext)

    # RW03 ------------------------------------------------------------------
    def test_rw03_nicht_messbar_ist_keine_ruhe(self):
        b = Rueckweg(pruefer=_pruefer(NICHT_MESSBAR, "kein Schreibrecht")
                     ).zurueckspielen(self.ziel, self.sicherung,
                                      sicherung_sha512=self.sicherung_sha)
        self.assertFalse(b.ausgefuehrt)
        self.assertEqual(b.zustand, VERWEIGERT)
        # Der Handlungshinweis unterscheidet sich vom Fall 'belegt': dort ist
        # ein Prozess zu beenden, hier ist ein Recht zu klaeren. Beides als
        # "nicht frei" zu melden waere weniger, als wir wissen.
        self.assertIn("NICHT MESSBAR", b.klartext)
        self.assertNotIn("Den Prozess beenden", b.klartext)

    # RW04 ------------------------------------------------------------------
    def test_rw04_fehlende_sicherung_verweigert_statt_ausnahme(self):
        os.remove(self.sicherung)
        vorher = Path(self.ziel).read_bytes()
        b = Rueckweg(pruefer=_pruefer(RUHIG)).zurueckspielen(
            self.ziel, self.sicherung, sicherung_sha512=self.sicherung_sha)
        self.assertEqual(b.zustand, VERWEIGERT)
        self.assertTrue(b.zieldatei_unberuehrt)
        self.assertEqual(Path(self.ziel).read_bytes(), vorher)

    # RW05 ------------------------------------------------------------------
    def test_rw05_veraenderte_sicherung_wird_nicht_zurueckgespielt(self):
        Path(self.sicherung).write_bytes(b"etwas ganz anderes")
        vorher = Path(self.ziel).read_bytes()
        b = Rueckweg(pruefer=_pruefer(RUHIG)).zurueckspielen(
            self.ziel, self.sicherung, sicherung_sha512=self.sicherung_sha)
        self.assertEqual(b.zustand, VERWEIGERT)
        self.assertEqual(Path(self.ziel).read_bytes(), vorher)
        self.assertIn("SHA512", b.grund)

    # RW06 ------------------------------------------------------------------
    def test_rw06_seitendateien(self):
        for suffix in ("-wal", "-shm"):
            Path(self.ziel + suffix).write_bytes(b"x")
        # (a) Verweigerung: die Seitendateien bleiben, wo sie sind — sie
        #     gehoeren zum Stand der Zieldatei, und der wird nicht angefasst.
        Rueckweg(pruefer=_pruefer(BELEGT, "gehalten")).zurueckspielen(
            self.ziel, self.sicherung, sicherung_sha512=self.sicherung_sha)
        for suffix in ("-wal", "-shm"):
            self.assertTrue(os.path.exists(self.ziel + suffix),
                            "Seitendatei %s wurde bei einer VERWEIGERUNG "
                            "entfernt — das waere ein angefangener Rueckweg."
                            % suffix)
        # (b) Ausfuehrung: sie muessen weg, sonst liest SQLite ein Journal,
        #     das nicht mehr zur zurueckgespielten Datei passt.
        b = Rueckweg(pruefer=_pruefer(RUHIG)).zurueckspielen(
            self.ziel, self.sicherung, sicherung_sha512=self.sicherung_sha)
        self.assertTrue(b.ausgefuehrt)
        for suffix in ("-wal", "-shm"):
            self.assertFalse(os.path.exists(self.ziel + suffix))

    # RW07 ------------------------------------------------------------------
    def test_rw07_kopierfehler_meldet_unbestimmten_zustand(self):
        """
        Der Kopiervorgang scheitert MITTEN im Lauf.

        Nachgestellt wird das ueber shutil.copyfile — und zwar bewusst hier
        und nicht ueber entzogene Rechte: Als root laufende Testlaeufe (in
        der Bauumgebung der Normalfall) ignorieren Dateirechte, ein solcher
        Test waere je nach Konto gruen oder rot. Ein Test, dessen Ergebnis
        vom ausfuehrenden Konto abhaengt, belegt nichts.
        """
        rw = Rueckweg(pruefer=_pruefer(RUHIG))
        echt = shutil.copyfile

        def _bricht_ab(src, dst, **kw):
            Path(dst).write_bytes(b"halb ")     # so weit kam die Kopie
            raise OSError(28, "No space left on device")

        shutil.copyfile = _bricht_ab
        try:
            b = rw.zurueckspielen(self.ziel, self.sicherung,
                                  sicherung_sha512=self.sicherung_sha)
        finally:
            shutil.copyfile = echt
        self.assertEqual(b.zustand, KOPIERFEHLER)
        self.assertFalse(b.ausgefuehrt)
        # UNBESTIMMT darf nicht als UNBERUEHRT durchgehen.
        self.assertFalse(b.zieldatei_unberuehrt)
        self.assertIn("UNBESTIMMTEN", b.klartext)
        self.assertEqual(sha512_file(self.sicherung), self.sicherung_sha)

    # RW07b -----------------------------------------------------------------
    def test_rw07b_stille_teilkopie_faellt_bei_tor_4_auf(self):
        """
        Die Kopie meldet ERFOLG und hat trotzdem nicht das Richtige
        hinterlassen. Ohne Tor 4 (Nachrechnen der Zieldatei) waere das ein
        stiller Fehlschlag — genau die Sorte, die dieser Vorgang beseitigen
        soll.
        """
        rw = Rueckweg(pruefer=_pruefer(RUHIG))
        echt = shutil.copyfile

        def _luegt(src, dst, **kw):
            Path(dst).write_bytes(b"halb kopiert")
            return dst

        shutil.copyfile = _luegt
        try:
            b = rw.zurueckspielen(self.ziel, self.sicherung,
                                  sicherung_sha512=self.sicherung_sha)
        finally:
            shutil.copyfile = echt
        self.assertEqual(b.zustand, KOPIERFEHLER)
        self.assertIn("SHA512", b.grund)

    # RW08 ------------------------------------------------------------------
    def test_rw08_echte_messung_gegen_einen_echten_halter(self):
        """
        OHNE injizierten Pruefer. Ein echter Halter, eine echte Sperrprobe.

        Zwei Verbindungen im selben Prozess reichen dafuer aus: SQLite fuehrt
        Sperren je VERBINDUNG und nicht je Prozess. Damit ist der Fall ohne
        zweiten Prozess und ohne Plattformabhaengigkeit nachstellbar.
        """
        db = os.path.join(self._tmp, "echt.db")
        con = sqlite3.connect(db)
        con.isolation_level = None
        con.execute("CREATE TABLE t(x)")
        halter = sqlite3.connect(db)
        halter.isolation_level = None
        halter.execute("BEGIN EXCLUSIVE")          # ab hier haelt jemand sie
        vorher = Path(db).read_bytes()
        try:
            b = Rueckweg(timeout_s=0.2).zurueckspielen(
                db, self.sicherung, sicherung_sha512=self.sicherung_sha)
        finally:
            halter.execute("ROLLBACK")
            halter.close()
            con.close()
        self.assertEqual(b.zustand, VERWEIGERT)
        self.assertEqual(Path(db).read_bytes(), vorher)
        # ... und ohne Halter laeuft derselbe Aufruf durch. Ohne diese
        # Gegenprobe waere nicht belegt, dass die Verweigerung am HALTER lag
        # und nicht an irgendetwas anderem.
        b2 = Rueckweg(timeout_s=0.2).zurueckspielen(
            db, self.sicherung, sicherung_sha512=self.sicherung_sha)
        self.assertTrue(b2.ausgefuehrt, b2.grund)
        self.assertEqual(Path(db).read_bytes(),
                         Path(self.sicherung).read_bytes())

    # RW09 ------------------------------------------------------------------
    def test_rw09_befund_weist_unstimmiges_zurueck(self):
        with self.assertRaises(RueckwegBefundError):
            RueckwegBefund(pfad="p", sicherung="s", zustand="erfunden",
                           grund="g", klartext="k")
        with self.assertRaises(RueckwegBefundError):
            RueckwegBefund(pfad="p", sicherung="s", zustand=VERWEIGERT,
                           grund="   ", klartext="k")
        with self.assertRaises(RueckwegBefundError):
            RueckwegBefund(pfad="p", sicherung="s", zustand=VERWEIGERT,
                           grund="g", klartext="")


class RueckwegImAusfuehrerTests(unittest.TestCase):
    """Der Rueckweg im Zusammenspiel mit FleetExecutor, Ledger und Companion."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._pkg_root = os.path.join(self._tmp, "pkgs")
        os.makedirs(self._pkg_root, exist_ok=True)
        sys.path.insert(0, self._pkg_root)
        self.mdb_path = os.path.join(self._tmp, "migration.db")
        self.mcon = sqlite3.connect(self.mdb_path)
        self.mcon.isolation_level = None
        self.mdb = MigrationDb(self.mcon)
        self.mdb.ensure_schema()
        self.ledger = MigrationLedger(self.mcon)
        self.backup_dir = os.path.join(self._tmp, "backups")

    def tearDown(self):
        try:
            self.mcon.close()
        finally:
            if self._pkg_root in sys.path:
                sys.path.remove(self._pkg_root)
            shutil.rmtree(self._tmp, ignore_errors=True)

    # ---- Fixtures ---------------------------------------------------------
    def _evidence_like(self, name="evidence_18.db", n=25):
        path = os.path.join(self._tmp, name)
        con = sqlite3.connect(path)
        con.isolation_level = None
        con.execute("CREATE TABLE annotations(id INTEGER PRIMARY KEY, txt TEXT)")
        con.executemany("INSERT INTO annotations(txt) VALUES(?)",
                        [("a%d" % i,) for i in range(n)])
        con.close()
        return path

    def _bad_pkg(self, name):
        d = os.path.join(self._pkg_root, name)
        os.makedirs(d, exist_ok=True)
        Path(os.path.join(d, "__init__.py")).write_text("", encoding="utf-8")
        Path(os.path.join(d, "m001_baseline.py")).write_text(
            'VERSION = 1\nNAME = "baseline"\nKIND = "additive"\n'
            'def up(con):\n    pass\n', encoding="utf-8")
        Path(os.path.join(d, "m002_bad.py")).write_text(
            _BAD_LOSS_M002, encoding="utf-8")
        importlib.invalidate_caches()
        return importlib.import_module(name)

    def _executor(self, pkg, rueckweg):
        return FleetExecutor(self.mdb, self.ledger,
                             backup_dir=self.backup_dir, operator="test",
                             packages={"evidence": pkg}, rueckweg=rueckweg)

    def _status_folge(self):
        return [r["status"] for r in self.ledger.list_runs()]

    # RW10 ------------------------------------------------------------------
    def test_rw10_verweigerter_rueckweg_im_ausfuehrer(self):
        pkg = self._bad_pkg("rwpkg_a")
        path = self._evidence_like()
        vorher_zeilen = sqlite3.connect(path).execute(
            "SELECT COUNT(*) FROM annotations").fetchone()[0]
        ex = self._executor(pkg, Rueckweg(pruefer=_pruefer(
            BELEGT, "database is locked — noch von jemandem gehalten")))
        res = ex.execute_instance(TargetDb("evidence", path, 18), dry_run=False)

        self.assertEqual(res.status, "failed_not_restored")
        self.assertIn(res.status, FEHLERSTATUS)
        # Das Laufbuch darf NICHT behaupten, wiederhergestellt worden zu sein.
        folge = self._status_folge()
        self.assertIn("failed", folge)
        self.assertIn("restore_refused", folge)
        self.assertNotIn("restored", folge)
        # Die Kette bleibt heil, und der Lauf gilt als ABGESCHLOSSEN.
        self.assertTrue(self.ledger.verify_chain().ok)
        self.assertEqual(self.ledger.interrupted_runs(), [])
        # Die Instanz traegt den Stand der gescheiterten Migration — genau
        # das ist der Preis, und er ist benannt statt verschleiert.
        nachher_zeilen = sqlite3.connect(path).execute(
            "SELECT COUNT(*) FROM annotations").fetchone()[0]
        self.assertEqual(nachher_zeilen, 0)
        self.assertNotEqual(nachher_zeilen, vorher_zeilen)
        # Die Sicherung liegt unveraendert und wird im Klartext genannt.
        self.assertTrue(os.path.exists(res.backup_path))
        self.assertIn(res.backup_path, res.rueckweg_klartext)
        self.assertIn("RUECKWEG NICHT AUSGEFUEHRT", res.detail)
        # Die Registry weist den Rueckstand aus, statt eine Version zu
        # behaupten, die niemand gemessen hat.
        eintrag = [e for e in self.mdb.list_registry()
                   if e.db_kind == "evidence"][0]
        self.assertEqual(eintrag.last_status, "failed_not_restored")

    # RW11 ------------------------------------------------------------------
    def test_rw11_gelaufener_rueckweg_bleibt_wie_bisher(self):
        pkg = self._bad_pkg("rwpkg_b")
        path = self._evidence_like()
        vorher = sqlite3.connect(path).execute(
            "SELECT COUNT(*) FROM annotations").fetchone()[0]
        ex = self._executor(pkg, Rueckweg(pruefer=_pruefer(RUHIG)))
        res = ex.execute_instance(TargetDb("evidence", path, 18), dry_run=False)

        self.assertEqual(res.status, "failed_restored")
        self.assertEqual(res.rueckweg_klartext, "")
        folge = self._status_folge()
        self.assertIn("failed", folge)
        self.assertIn("restored", folge)
        self.assertNotIn("restore_refused", folge)
        nachher = sqlite3.connect(path).execute(
            "SELECT COUNT(*) FROM annotations").fetchone()[0]
        self.assertEqual(nachher, vorher)
        self.assertTrue(self.ledger.verify_chain().ok)

    # RW12 ------------------------------------------------------------------
    def test_rw12_restore_refused_ist_terminal(self):
        self.ledger.record_start(db_kind="evidence", uid=7, from_version=1,
                                 to_version=2, started_at=100)
        self.ledger.record_result(db_kind="evidence", uid=7, from_version=1,
                                  to_version=2, started_at=100,
                                  status="restore_refused")
        self.assertEqual(self.ledger.interrupted_runs(), [])
        self.assertTrue(self.ledger.verify_chain().ok)
        # Ein erfundener Status bleibt weiterhin unzulaessig — die Liste ist
        # erweitert worden und nicht geoeffnet.
        with self.assertRaises(ValueError):
            self.ledger.record_result(db_kind="evidence", uid=7,
                                      from_version=1, to_version=2,
                                      started_at=100, status="halb_ok")

    # RW13 ------------------------------------------------------------------
    def test_rw13_companion_nennt_den_rueckstand(self):
        pkg = self._bad_pkg("rwpkg_c")
        path = self._evidence_like()
        # Ohne synchronisierten Katalog blockiert das Tor KATALOG_DRIFT, und
        # der Lauf kaeme gar nicht bis zum Rueckweg.
        CatalogReconciler(self.mdb, {"evidence": pkg}).sync()
        comp = MigrationCompanion(
            self.mdb, self.ledger, backup_dir=self.backup_dir,
            operator="test", packages={"evidence": pkg},
            rueckweg=Rueckweg(pruefer=_pruefer(BELEGT, "gehalten")))
        erg = comp.execute([TargetDb("evidence", path, 18)], confirm=True)
        self.assertTrue(erg.executed)
        self.assertIn("OHNE ausgefuehrten Rueckweg", erg.reason)
        # Die Zusammenfassung darf nicht "wiederhergestellt" sagen, wo nichts
        # wiederhergestellt wurde.
        self.assertNotIn("und wiederhergestellt", erg.reason)


if __name__ == "__main__":
    unittest.main()

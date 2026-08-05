# =============================================================================
# tests/test_backup_restore.py
# IT-Forensisches Ermittlungswerkzeug - Datensicherung
# =============================================================================
# Testsuite fuer Build 680: DER RUECKWEG (Vorgang 2785556a).
#
# WAS HIER AUF DEM SPIEL STEHT: Bis zu diesem Build gab es im Bestand keinen
# erprobten Weg zurueck. Eine Sicherung, deren Rueckweg nie gefahren wurde,
# ist eine Vermutung und kein Beleg - und im Ernstfall gibt es keine zweite
# Gelegenheit, das zu bemerken.
#
# WH01 ist deshalb der Test, um den es in diesem Vorgang eigentlich geht: er
# faehrt den GANZEN Weg - sichern, Original beschaedigen, zurueckspielen,
# tauschen, gegenpruefen - und zwar mit den Daten, an denen sich der Erfolg
# ablesen laesst.
#
# WH01 - DER VOLLSTAENDIGE WEG. Sichern (BackupTool), Original zerstoeren,
#        restore fahren, von Hand tauschen, und danach sind die Daten und
#        die user_version wieder da. Der Rueckgabewert ist dabei 1 und
#        nicht 0 - die Kopie ist in Ordnung, das ZIEL ist es nicht, und
#        genau das soll der Wert sagen.
# WH02 - Eine abweichende Pruefsumme HAELT DEN WEG AN. Nichts wird
#        geschrieben, der Rueckgabewert ist der schwerste (3).
# WH03 - KEINE vorgelegte Pruefsumme ist ein BEFUND und kein Durchmarsch -
#        genau der Zustand, den der Vorgang beklagt.
# WH04 - Ein belegtes Ziel sperrt den TAUSCH und nicht die Kopie. 'nicht
#        messbar' zaehlt dabei nicht als Ruhe (96f2b18f). Die Trennung von
#        'darf die Kopie entstehen' und 'darf getauscht werden' ist an
#        diesem und an WH01 erarbeitet worden.
# WH05 - HEISSES JOURNAL NEBEN DEM ZIEL: die Sperrprobe wird NICHT gefahren,
#        und die Zieldatei liegt danach unveraendert da. Der wichtigste
#        Schutz dieses Bauteils.
# WH06 - Der Trockenlauf prueft alles und schreibt nichts - und sagt, dass
#        er bestanden hat (das ist etwas anderes als ein Fehlschlag).
# WH07 - Eine fehlende oder leere Sicherung: die Folgeschritte gelten als
#        OFFEN und nicht als bestanden (Grundregel 1).
# WH08 - DIE ZUSAGE IST ERZWUNGEN: faellt der Schreibpfad mit dem Original
#        zusammen, fliegt eine Ausnahme und das Original bleibt unberuehrt.
# WH09 - Der Bericht nennt, was er NICHT geprueft hat; ASCII, 78 Zeichen.
# WH10 - Das JSON traegt dieselben Aussagen wie der Text.
# WH11 - Die Anleitung erscheint NUR neben einer fertigen Kopie - und nennt
#        das Beiseitelegen des Originals vor dem Einsetzen.
# WH12 - Keine halbe Datei: bricht das Schreiben ab, liegt KEINE
#        '.wiederhergestellt' da.
# CR01 - CLI: 'restore --trocken' ueber die Registrierung, End-to-End.
# CR02 - CLI: 'restore' schreibt die Kopie UND den Beleg daneben; die
#        Originaldatenbank ist danach unveraendert.
# CR03 - CLI: ohne --sicherung und ohne --db-label bricht es ab.
#
# Version: v0.8.680 - Build: 680 - 2026-08-05
# =============================================================================

import io
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations
from management.audit.audit_log import AuditLog
from management.migrations.runner import MigrationRunner, discover
from management.backup import backup_admin
from management.backup.backup_wiederhersteller import (
    ENDUNG_VORHER, ENDUNG_WIEDERHERGESTELLT, RC_BEFUND, RC_OK,
    RC_UNBRAUCHBAR, RC_VERWEIGERT, S_INTEGRITAET, S_NICHT_LEER,
    S_PRUEFSUMME, S_VORHANDEN, W_GEGENPROBE, W_GESCHRIEBEN, Z_KEIN_JOURNAL,
    BEFEHLSMARKEN, Z_RUHE, WiederherstellungsFehler, Wiederhersteller,
    bericht_json,
    bericht_text,
)
from management.migration_fleet.harness.backup import BackupTool
from management.migration_fleet.harness.hashing import sha512_file


# -----------------------------------------------------------------------------
# Helfer
# -----------------------------------------------------------------------------

def _mkdb(path, user_version=42, rows=50, marke="urzustand"):
    """
    Eine kleine Datenbank mit ABLESBAREM Inhalt.

    Die 'marke' ist der Punkt: an ihr laesst sich nach dem Tausch belegen,
    dass wirklich der Stand der SICHERUNG wieder dasteht und nicht
    irgendeiner. Ein Test, der nur 'integrity_check ok' prueft, wuerde auch
    dann gruen bleiben, wenn eine voellig andere Datenbank eingesetzt wurde.
    """
    con = sqlite3.connect(str(path))
    try:
        con.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
        con.executemany("INSERT INTO t(v) VALUES(?)",
                        [("%s-%04d" % (marke, i),) for i in range(rows)])
        con.execute("PRAGMA user_version=%d" % user_version)
        con.commit()
    finally:
        con.close()


def _inhalt(path):
    """(Zeilenzahl, erster Wert, user_version) - der ablesbare Stand."""
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        n = con.execute("SELECT count(*) FROM t").fetchone()[0]
        erst = con.execute("SELECT v FROM t ORDER BY id LIMIT 1").fetchone()[0]
        uv = con.execute("PRAGMA user_version").fetchone()[0]
    finally:
        con.close()
    return n, erst, int(uv)


def _schritt(befund, name):
    for s in befund.schritte:
        if s.name == name:
            return s
    raise AssertionError("Pruefschritt '%s' kommt im Befund nicht vor - eine "
                         "Prueffolge mit Luecken ist von einer bestandenen "
                         "nicht zu unterscheiden." % name)


class _RestoreBasis(unittest.TestCase):
    """Ein Wegwerf-Bestand je Test: Quelle, Ordner, eine Sicherung."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = self._tmpdir.name
        self.datendir = os.path.join(self.tmp, "data")
        self.sichdir = os.path.join(self.tmp, "backups")
        os.makedirs(self.datendir)
        os.makedirs(self.sichdir)
        self.ziel = os.path.join(self.datendir, "evidence_18.db")
        _mkdb(self.ziel, user_version=42, rows=50, marke="urzustand")
        ergebnis = BackupTool.create_backup(
            self.ziel, self.sichdir, db_label="evidence_18", version=42)
        self.sicherung = ergebnis.path
        self.summe = ergebnis.sha512

    def tearDown(self):
        self._tmpdir.cleanup()


# =============================================================================
# WH01 - DER VOLLSTAENDIGE WEG
# =============================================================================

class TestVollstaendigerWeg(_RestoreBasis):

    def test_wh01_sichern_zerstoeren_zurueckspielen_tauschen_gegenpruefen(self):
        """
        DER TEST, UM DEN ES IN DIESEM VORGANG GEHT.

        Er faehrt den Weg so, wie er im Ernstfall zu fahren waere, und der
        Tausch ist ausdruecklich dabei - auch wenn das Werkzeug ihn nicht
        selbst vornimmt. Ohne den Tausch waere belegt, dass eine Kopie
        entsteht; belegt sein soll aber, dass die Datenbank danach WIEDER
        LAEUFT.
        """
        # 1. AUSGANGSLAGE - der Stand, der zurueckkommen soll.
        vorher = _inhalt(self.ziel)
        self.assertEqual(vorher, (50, "urzustand-0000", 42))

        # 2. DAS ORIGINAL WIRD ZERSTOERT. Nicht geloescht, sondern
        #    UNBRAUCHBAR gemacht - das ist der haeufigere Ernstfall und der
        #    haertere Test: die Datei ist noch da und sieht von aussen aus
        #    wie eine Datenbank.
        with open(self.ziel, "r+b") as fh:
            fh.seek(0)
            fh.write(b"\x00" * 4096)
        with self.assertRaises(sqlite3.DatabaseError):
            _inhalt(self.ziel)

        # 3. DER RUECKWEG.
        werkzeug = Wiederhersteller(self.sicherung, self.ziel)
        befund = werkzeug.fahren(erwartete_summe=self.summe, schreiben=True)

        # DER RUECKGABEWERT IST HIER 1 UND NICHT 0 - und das ist richtig so.
        # Die Kopie liegt bereit und ist gegengelesen; was einen Befund
        # traegt, ist das ZIEL: es ist zerstoert. Genau das soll der Wert
        # sagen. Ein 0 waere hier die schlechtere Antwort - es hiesse
        # 'nichts zu beanstanden' ueber eine Datenbank, die nicht mehr
        # aufgeht.
        self.assertEqual(befund.rueckgabewert(), RC_BEFUND,
                         "unerwarteter Befund: %s"
                         % [(s.name, s.grund) for s in befund.offene_befunde])
        self.assertEqual([s.name for s in befund.offene_befunde], [Z_RUHE])
        # Und der Befund SAGT, dass die Zieldatenbank selbst beschaedigt
        # ist - wer nur 'nicht pruefbar' liest, sucht den Fehler bei sich.
        self.assertTrue(befund.ziel_beschaedigt)
        self.assertIn("SELBST beschaedigt", _schritt(befund, Z_RUHE).grund)

        # DIE ANLEITUNG MUSS TROTZDEM ERSCHEINEN - mit Vorbehalt. Ein
        # beschaedigtes Ziel wird die Sperrprobe NIE 'frei' melden lassen;
        # wer diesen Fall wie einen Halter behandelt, laesst den Ermittler
        # im haeufigsten Ernstfall ohne Anleitung stehen. Am Probelauf vom
        # 2026-08-05 aufgefallen.
        self.assertTrue(befund.tauschbereit)
        text = bericht_text(befund)
        self.assertIn("DER TAUSCH - VON HAND", text)
        self.assertIn("VORBEHALT - DIE ZIELDATENBANK IST SELBST BESCHAEDIGT",
                      text)
        self.assertLess(text.index("VORBEHALT"),
                        text.index("1. Alle Dienste anhalten"),
                        "Der Vorbehalt gehoert VOR Schritt 1 - wer ihn erst "
                        "danach liest, hat den Nachweis schon vergeblich an "
                        "der kaputten Datei versucht.")
        self.assertTrue(_schritt(befund, S_PRUEFSUMME).bestanden)
        self.assertTrue(_schritt(befund, W_GESCHRIEBEN).bestanden)
        self.assertTrue(_schritt(befund, W_GEGENPROBE).bestanden)
        self.assertEqual(befund.geschrieben,
                         self.ziel + ENDUNG_WIEDERHERGESTELLT)
        self.assertTrue(os.path.isfile(befund.geschrieben))

        # 3a. DAS ORIGINAL IST DABEI NICHT ANGEFASST WORDEN. Es ist kaputt -
        #     und es ist GENAUSO kaputt wie vorher. Das ist die Zusage.
        with open(self.ziel, "rb") as fh:
            self.assertEqual(fh.read(16), b"\x00" * 16)

        # 4. DER TAUSCH - der Handgriff, den das Werkzeug bewusst nicht tut.
        #    Er wird hier genau in der Reihenfolge der ausgegebenen Anleitung
        #    gefahren: erst beiseitelegen, dann einsetzen.
        beiseite = self.ziel + ENDUNG_VORHER
        os.replace(self.ziel, beiseite)
        os.replace(befund.geschrieben, self.ziel)
        self.assertTrue(os.path.isfile(beiseite),
                        "Das Original muss aufgehoben bleiben - es ist das "
                        "einzige Stueck mit Daten aus der Zeit nach der "
                        "Sicherung.")

        # 5. DIE GEGENPROBE - der Stand ist wieder da.
        self.assertEqual(_inhalt(self.ziel), vorher)
        con = sqlite3.connect("file:%s?mode=ro" % self.ziel, uri=True)
        try:
            zeilen = con.execute("PRAGMA integrity_check").fetchall()
        finally:
            con.close()
        self.assertEqual(zeilen, [("ok",)])

        # 6. UND DER WEG LAESST SICH NACHTRAEGLICH BELEGEN: die Datei am
        #    Platz traegt jetzt genau die zertifizierte Pruefsumme. Das ist
        #    Schritt 4 der Anleitung, hier maschinell gefahren.
        self.assertEqual(sha512_file(self.ziel), self.summe)


# =============================================================================
# WH02 bis WH08 - die Verweigerungen
# =============================================================================

class TestVerweigerungen(_RestoreBasis):

    def test_wh02_abweichende_pruefsumme_haelt_an(self):
        befund = Wiederhersteller(self.sicherung, self.ziel).fahren(
            erwartete_summe="deadbeef", schreiben=True)
        self.assertFalse(_schritt(befund, S_PRUEFSUMME).bestanden)
        self.assertIsNone(befund.geschrieben)
        self.assertFalse(os.path.exists(self.ziel + ENDUNG_WIEDERHERGESTELLT))
        # DER SCHWERSTE RUECKGABEWERT: hier ist nicht der Weg gescheitert,
        # sondern das, worauf man sich verlassen wollte.
        self.assertEqual(befund.rueckgabewert(), RC_UNBRAUCHBAR)
        # Und der Grund nennt beide Summen - sonst ist er nicht nachpruefbar.
        self.assertIn("deadbeef", _schritt(befund, S_PRUEFSUMME).grund)

    def test_wh03_keine_pruefsumme_ist_ein_befund(self):
        """
        Der Kern des zweiten Teils von 2785556a: die Summe wird seit Build
        354 erhoben und wurde nie ausgewertet. Sie hier stillschweigend zu
        uebergehen, hiesse diesen Zustand fortzuschreiben.
        """
        befund = Wiederhersteller(self.sicherung, self.ziel).fahren(
            erwartete_summe=None, schreiben=True)
        schritt = _schritt(befund, S_PRUEFSUMME)
        self.assertTrue(schritt.geprueft,
                        "Eine fehlende Vergleichssumme ist ein Befund und "
                        "kein uebersprungener Schritt.")
        self.assertFalse(schritt.bestanden)
        self.assertIsNone(befund.geschrieben)
        self.assertEqual(befund.rueckgabewert(), RC_UNBRAUCHBAR)
        # Die Sicherung selbst ist in Ordnung - das muss der Befund auch
        # sagen, sonst sucht jemand den Fehler an der falschen Stelle.
        self.assertTrue(_schritt(befund, S_INTEGRITAET).bestanden)

    def test_wh04_belegtes_ziel_sperrt_den_tausch_nicht_die_kopie(self):
        """
        Ein offener Schreiber auf der Zieldatenbank. Die Sperrprobe muss ihn
        bemerken - und der TAUSCH muss gesperrt sein.

        DIE KOPIE ENTSTEHT TROTZDEM, und das ist die Richtigstellung, die
        der eigene Test WH01 erzwungen hat: sie wird neben das Original
        gelegt und fasst es nicht an. Wer bei belegtem Ziel die Kopie
        verweigerte, verweigerte die Vorbereitung mit der Begruendung, dass
        die Ausfuehrung noch nicht dran ist.
        """
        halter = sqlite3.connect(self.ziel, timeout=0.1)
        try:
            halter.isolation_level = None
            halter.execute("BEGIN EXCLUSIVE")
            befund = Wiederhersteller(self.sicherung, self.ziel).fahren(
                erwartete_summe=self.summe, schreiben=True)
        finally:
            halter.rollback()
            halter.close()

        self.assertIsNotNone(befund.ruhe)
        self.assertFalse(befund.ruhe.ist_ruhig)
        self.assertFalse(_schritt(befund, Z_RUHE).bestanden)
        self.assertFalse(befund.tauschbereit)
        self.assertEqual(befund.rueckgabewert(), RC_BEFUND)
        # Die Kopie liegt bereit und ist gegengelesen ...
        self.assertIsNotNone(befund.geschrieben)
        self.assertTrue(_schritt(befund, W_GEGENPROBE).bestanden)
        # ... aber die Tauschanleitung wird NICHT ausgegeben. Sie neben
        # einem Befund am Ziel auszugeben waere eine Einladung, ihn zu
        # uebergehen.
        text = bericht_text(befund)
        self.assertNotIn("DER TAUSCH - VON HAND", text)
        self.assertIn("NOCH NICHT TAUSCHEN", text)

    def test_wh05_heisses_journal_am_ziel_wird_nicht_angefasst(self):
        """
        DER WICHTIGSTE SCHUTZ DIESES BAUTEILS.

        Liegt neben der Zieldatenbank ein heisses Journal, darf sie NICHT
        geoeffnet werden - auch nicht zur Sperrprobe. SQLite wuerde das
        Journal beim Oeffnen zurueckrollen; am 2026-08-01 wurde gemessen,
        dass dabei aus 34 MB 0 Byte werden koennen (backup_pruefer.py
        Z. 300-313). Ein Rueckweg, der beim HINSEHEN das Original
        vernichtet, waere die schlimmste aller Antworten.
        """
        with open(self.ziel + "-journal", "wb") as fh:
            fh.write(b"\xd9\xd5\x05\xf9\x20\xa1\x63\xd7" + b"\x00" * 20)
        vorher_summe = sha512_file(self.ziel)
        vorher_groesse = os.path.getsize(self.ziel)

        befund = Wiederhersteller(self.sicherung, self.ziel).fahren(
            erwartete_summe=self.summe, schreiben=True)

        self.assertFalse(_schritt(befund, Z_KEIN_JOURNAL).bestanden)
        # NICHT GEFAHREN heisst NICHT GEPRUEFT - und nicht 'bestanden'.
        self.assertFalse(_schritt(befund, Z_RUHE).geprueft)
        self.assertIsNone(befund.ruhe)
        self.assertFalse(befund.tauschbereit)
        self.assertEqual(befund.rueckgabewert(), RC_BEFUND)
        # UND DAS ORIGINAL LIEGT UNVERAENDERT DA. Das ist der Kern dieses
        # Falls: die Zieldatei wurde zu keinem Zeitpunkt geoeffnet.
        self.assertEqual(os.path.getsize(self.ziel), vorher_groesse)
        self.assertEqual(sha512_file(self.ziel), vorher_summe)
        # Das Journal liegt ebenfalls noch da - auch daran haette ein
        # Oeffnen sich gezeigt.
        self.assertTrue(os.path.exists(self.ziel + "-journal"))

    def test_wh06_trockenlauf_prueft_alles_und_schreibt_nichts(self):
        befund = Wiederhersteller(self.sicherung, self.ziel).fahren(
            erwartete_summe=self.summe, schreiben=False)
        self.assertTrue(befund.trockenlauf)
        self.assertTrue(befund.ok)
        self.assertEqual(befund.rueckgabewert(), RC_OK)
        self.assertIsNone(befund.geschrieben)
        self.assertFalse(os.path.exists(self.ziel + ENDUNG_WIEDERHERGESTELLT))
        # Die Pruefungen sind trotzdem alle gefahren.
        for name in (S_PRUEFSUMME, S_INTEGRITAET, Z_RUHE):
            self.assertTrue(_schritt(befund, name).geprueft)
            self.assertTrue(_schritt(befund, name).bestanden)
        # 'nicht geschrieben' ist hier KEIN Befund, sondern die Betriebsart.
        self.assertFalse(_schritt(befund, W_GESCHRIEBEN).geprueft)
        text = bericht_text(befund)
        self.assertIn("TROCKENLAUF BESTANDEN", text)

    def test_wh07_fehlende_und_leere_sicherung(self):
        # (a) gar nicht da
        weg = os.path.join(self.sichdir, "gibtsnicht.backup.db")
        befund = Wiederhersteller(weg, self.ziel).fahren(
            erwartete_summe=self.summe, schreiben=True)
        self.assertFalse(_schritt(befund, S_VORHANDEN).bestanden)
        # ALLE Folgeschritte stehen als OFFEN im Befund - eine Prueffolge
        # mit Luecken waere von einer bestandenen nicht zu unterscheiden.
        for name in (S_NICHT_LEER, S_PRUEFSUMME, S_INTEGRITAET, Z_RUHE):
            self.assertFalse(_schritt(befund, name).geprueft)
        self.assertEqual(befund.rueckgabewert(), RC_UNBRAUCHBAR)
        self.assertIsNone(befund.geschrieben)

        # (b) da, aber 0 Byte - die Signatur einer abgebrochenen Sicherung
        leer = os.path.join(
            self.sichdir, "leer_v1_20260805T101010Z_h.backup.db")
        open(leer, "wb").close()
        befund = Wiederhersteller(leer, self.ziel).fahren(
            erwartete_summe=self.summe, schreiben=True)
        self.assertTrue(_schritt(befund, S_VORHANDEN).bestanden)
        self.assertFalse(_schritt(befund, S_NICHT_LEER).bestanden)
        self.assertFalse(_schritt(befund, S_INTEGRITAET).geprueft,
                         "Eine leere Datei wird nicht geoeffnet.")
        self.assertEqual(befund.rueckgabewert(), RC_UNBRAUCHBAR)

    def test_wh08_zusage_ist_erzwungen_nicht_nur_zugesagt(self):
        """
        Die Zusage 'ueberschreibt niemals das Original' darf nicht bloss im
        Kommentar stehen. Genau dieser Befundtyp - eine Zusage, die nichts
        durchsetzt - liegt im Bestand schon zweimal vor (e9522fe2,
        906ede75).

        Nachgestellt wird der Fall, in dem jemand die Endung leert. Dann
        faellt der Schreibpfad mit dem Original zusammen, und es muss eine
        Ausnahme fliegen, statt das Beweismittel zu ueberschreiben.
        """
        import management.backup.backup_wiederhersteller as modul
        vorher_summe = sha512_file(self.ziel)
        alt = modul.ENDUNG_WIEDERHERGESTELLT
        modul.ENDUNG_WIEDERHERGESTELLT = ""
        try:
            werkzeug = modul.Wiederhersteller(self.sicherung, self.ziel)
            self.assertEqual(werkzeug.zielpfad(), self.ziel)
            with self.assertRaises(WiederherstellungsFehler):
                werkzeug.fahren(erwartete_summe=self.summe, schreiben=True)
        finally:
            modul.ENDUNG_WIEDERHERGESTELLT = alt
        # Das Original ist unberuehrt.
        self.assertEqual(sha512_file(self.ziel), vorher_summe)

    def test_wh12_keine_halbe_datei(self):
        """
        Bricht das Schreiben ab, darf KEINE '.wiederhergestellt' liegen -
        sonst entstuende genau der Zustand, den 'pruefen' im
        Sicherungsordner aufgedeckt hat: ein Abbruchrest, der wie ein
        Ergebnis aussieht.

        Nachgestellt ueber einen Lesefehler mitten in der Kopie.
        """
        import management.backup.backup_wiederhersteller as modul

        echt = modul.shutil.copyfileobj

        def _bricht_ab(quelle, senke, laenge=None):
            senke.write(quelle.read(64))
            raise OSError("Nachgestellter Abbruch mitten in der Kopie")

        modul.shutil.copyfileobj = _bricht_ab
        try:
            befund = modul.Wiederhersteller(self.sicherung, self.ziel).fahren(
                erwartete_summe=self.summe, schreiben=True)
        finally:
            modul.shutil.copyfileobj = echt

        self.assertIsNone(befund.geschrieben)
        self.assertFalse(_schritt(befund, W_GESCHRIEBEN).bestanden)
        self.assertFalse(os.path.exists(self.ziel + ENDUNG_WIEDERHERGESTELLT))
        # Auch keine Teildatei bleibt liegen.
        reste = [n for n in os.listdir(self.datendir) if n.endswith(".teil")]
        self.assertEqual(reste, [], "Teildateien: %s" % reste)
        # DER RUECKGABEWERT TRENNT DIE FAELLE: die Sicherung war in
        # Ordnung, es liegt nur keine Kopie bereit. Das ist etwas anderes
        # als eine untaugliche Sicherung (3) und etwas anderes als ein
        # blosser Befund am Ziel (1).
        self.assertEqual(befund.rueckgabewert(), RC_VERWEIGERT)


# =============================================================================
# WH09 bis WH11 - der Bericht
# =============================================================================

class TestBericht(_RestoreBasis):

    def test_wh09_bericht_nennt_was_er_nicht_geprueft_hat(self):
        befund = Wiederhersteller(self.sicherung, self.ziel).fahren(
            erwartete_summe=self.summe, schreiben=False)
        text = bericht_text(befund)

        # Grundregel 1: ein 'alles ok' ohne die Grenzen waere eine Zusicherung,
        # die dieser Weg nicht geben kann.
        self.assertIn("Was hier NICHT geprueft ist:", text)
        self.assertIn("INHALTLICH", text)
        self.assertIn("punktgleich", text)

        # GEPRUEFT WIRD BEIDES: der Trockenlauf UND der Bericht MIT
        # Tauschanleitung. Die Anleitung ist der laengste Teil und der mit
        # den Pfaden - sie hier auszulassen hiesse, die Regel genau dort
        # nicht zu pruefen, wo sie schwerfaellt.
        mit_anleitung = Wiederhersteller(self.sicherung, self.ziel).fahren(
            erwartete_summe=self.summe, schreiben=True)
        for fassung in (text, bericht_text(mit_anleitung)):
            self._breite_pruefen(fassung)

    @staticmethod
    def _breite_pruefen(text):
        """
        ASCII und 78 Zeichen - wie ueberall auf der Kommandozeile.

        ZWEI AUSNAHMEN, beide begruendet und beide eng gefasst:
          * eine Zeile, die aus EINEM ueberlangen Wort besteht (ein Pfad,
            eine Pruefsumme). Zerschnitten waere sie unbrauchbar.
          * eine KOPIERBARE BEFEHLSZEILE. Ein umgebrochener Befehl ist ein
            falscher Befehl; die Marken kommen aus BEFEHLSMARKEN, damit
            Bericht und Test dieselbe Quelle haben.
        Alles andere haelt die Spalte.
        """
        text.encode("ascii")
        zu_lang = []
        for zeile in text.splitlines():
            if len(zeile) <= 78:
                continue
            nackt = zeile.strip()
            if nackt.startswith(BEFEHLSMARKEN):
                continue
            if len(nackt.split()) == 1:
                continue
            zu_lang.append(zeile)
        assert zu_lang == [], "zu lange Zeilen: %s" % zu_lang

    def test_wh10_json_traegt_dieselben_aussagen(self):
        befund = Wiederhersteller(self.sicherung, self.ziel).fahren(
            erwartete_summe=self.summe, schreiben=True)
        daten = bericht_json(befund)

        self.assertEqual(daten["rueckgabewert"], befund.rueckgabewert())
        self.assertEqual(daten["ok"], befund.ok)
        self.assertEqual(daten["geschrieben"], befund.geschrieben)
        self.assertEqual(len(daten["schritte"]), len(befund.schritte))
        # Der Sperrbefund darf im JSON nicht verlorengehen: er ist die
        # Auskunft, an der im Ernstfall haengt, ob getauscht werden darf.
        self.assertEqual(daten["ruhe"]["zustand"], befund.ruhe.zustand)
        # Und es ist wirklich serialisierbar - ein JSON-Bericht, der beim
        # Schreiben scheitert, ist kein Beleg.
        json.loads(json.dumps(daten, ensure_ascii=True))

    def test_wh11_anleitung_nur_neben_fertiger_kopie(self):
        # (a) Mit Kopie: die Anleitung steht da, und sie legt das Original
        #     beiseite BEVOR sie die Kopie einsetzt.
        befund = Wiederhersteller(self.sicherung, self.ziel).fahren(
            erwartete_summe=self.summe, schreiben=True)
        text = bericht_text(befund)
        self.assertIn("DER TAUSCH - VON HAND", text)
        self.assertIn(ENDUNG_VORHER, text)
        beiseite_pos = text.index(ENDUNG_VORHER)
        einsetzen_pos = text.index(befund.geschrieben + '"')
        self.assertLess(beiseite_pos, einsetzen_pos,
                        "Das Beiseitelegen muss VOR dem Einsetzen stehen - "
                        "die Reihenfolge ist hier der Inhalt.")

        # (b) Ohne Kopie: keine Anleitung. Sie neben einem Befund auszugeben
        #     waere eine Einladung, den Befund zu uebergehen.
        befund2 = Wiederhersteller(self.sicherung, self.ziel).fahren(
            erwartete_summe="deadbeef", schreiben=True)
        self.assertNotIn("DER TAUSCH - VON HAND", bericht_text(befund2))


# =============================================================================
# CR01 bis CR03 - das Werkzeug
# =============================================================================

_PERSON = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY AUTOINCREMENT, system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL, is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0, is_support INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
)
"""

_OLD_SCRAPE_JOBS = """
CREATE TABLE scrape_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','running','done','failed')),
    manifest_path TEXT, output_path TEXT, worker_id TEXT,
    created_at INTEGER NOT NULL, started_at INTEGER, finished_at INTEGER,
    error_message TEXT, assigned_to INTEGER, note TEXT,
    FOREIGN KEY(assigned_to) REFERENCES person(id)
)
"""


class TestWerkzeug(unittest.TestCase):
    """
    Das CLI end-to-end: sichern ueber 'run', zurueckspielen ueber 'restore'.

    Es wird BEWUSST der ganze Weg ueber das Werkzeug gefahren und nicht nur
    das Bauteil aufgerufen: die Auswahl der Sicherung aus der Registrierung
    und das Zusammenfuehren mit der erhobenen Pruefsumme ist genau der
    Teil, der im Ernstfall stimmen muss.
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = self._tmpdir.name
        self.datendir = os.path.join(self.tmp, "data")
        self.dest = os.path.join(self.tmp, "backups")
        os.makedirs(os.path.join(self.datendir, "forensic"))
        os.makedirs(os.path.join(self.datendir, "evidence"))
        os.makedirs(os.path.join(self.datendir, "assets"))
        os.makedirs(self.dest)

        self.coord = os.path.join(self.datendir, "coordinator.db")
        self._build_coordinator(self.coord)

        self.evidence = os.path.join(self.datendir, "evidence",
                                     "evidence_18.db")
        _mkdb(self.evidence, user_version=7, rows=30, marke="urzustand")

        self.cfg = os.path.join(self.tmp, "config.yaml")
        with open(self.cfg, "w", encoding="utf-8") as fh:
            fh.write(
                "paths:\n"
                "  coordinator_db: %s\n"
                "  forensic_db_dir: %s\n"
                "  evidence_db_dir: %s\n"
                "  assets_db_dir: %s\n"
                "backup:\n"
                "  dest_dir: %s\n"
                "  include_shared_dbs: false\n"
                % (self.coord,
                   os.path.join(self.datendir, "forensic"),
                   os.path.join(self.datendir, "evidence"),
                   os.path.join(self.datendir, "assets"),
                   self.dest))

        # Der Sicherungslauf, auf den sich die Rueckwege beziehen.
        with redirect_stdout(io.StringIO()):
            rc = backup_admin.main(["run", "--config", self.cfg,
                                    "--actor", "h0a2898"])
        self.assertEqual(rc, 0)

    def tearDown(self):
        self._tmpdir.cleanup()

    @staticmethod
    def _build_coordinator(db_path):
        con = sqlite3.connect(db_path)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute(_PERSON)
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (1, 'h0a2898', 'Chefin', 1, 1, 0, ?)",
            (int(time.time()),))
        con.execute(_OLD_SCRAPE_JOBS)
        try:
            audit = AuditLog(con)
            MigrationRunner(con, discover(coordinator_migrations),
                            audit=audit, deployed_by="tester").run()
        finally:
            con.close()

    def test_cr01_cli_trockenlauf_ueber_die_registrierung(self):
        puffer = io.StringIO()
        with redirect_stdout(puffer):
            rc = backup_admin.main(
                ["restore", "--config", self.cfg,
                 "--db-label", "evidence_18", "--trocken"])
        ausgabe = puffer.getvalue()

        self.assertEqual(rc, RC_OK, ausgabe)
        # Die Pruefsumme wurde WIRKLICH gegengerechnet - genau das war der
        # Mangel, den 2785556a beschreibt.
        self.assertIn("SHA512 stimmt", ausgabe)
        self.assertIn("TROCKENLAUF", ausgabe)
        # Und es liegt nichts herum.
        self.assertFalse(
            os.path.exists(self.evidence + ENDUNG_WIEDERHERGESTELLT))

    def test_cr02_cli_legt_kopie_und_beleg_daneben(self):
        vorher = sha512_file(self.evidence)
        puffer = io.StringIO()
        with redirect_stdout(puffer):
            rc = backup_admin.main(
                ["restore", "--config", self.cfg,
                 "--db-label", "evidence_18"])
        ausgabe = puffer.getvalue()
        self.assertEqual(rc, RC_OK, ausgabe)

        kopie = self.evidence + ENDUNG_WIEDERHERGESTELLT
        self.assertTrue(os.path.isfile(kopie), ausgabe)

        # DER BELEG LIEGT DANEBEN. Ein Rueckweg ohne Beleg waere genau die
        # Vermutung, gegen die dieser Vorgang geschrieben ist.
        beleg = kopie + backup_admin.ENDUNG_BEFUND
        self.assertTrue(os.path.isfile(beleg))
        with open(beleg, encoding="utf-8") as fh:
            daten = json.load(fh)
        self.assertEqual(daten["rueckgabewert"], RC_OK)
        self.assertEqual(daten["geschrieben"], kopie)

        # DIE ORIGINALDATENBANK IST UNVERAENDERT. Das ist die Zusage des
        # ganzen Zuschnitts, und sie wird hier am Werkzeug gemessen und
        # nicht nur am Bauteil.
        self.assertEqual(sha512_file(self.evidence), vorher)
        self.assertEqual(_inhalt(self.evidence), (30, "urzustand-0000", 7))

        # Die Kopie taugt: sie traegt denselben Stand.
        self.assertEqual(_inhalt(kopie), (30, "urzustand-0000", 7))

    def test_cr03_ohne_auswahl_bricht_es_ab(self):
        puffer = io.StringIO()
        with redirect_stdout(puffer):
            rc = backup_admin.main(["restore", "--config", self.cfg])
        self.assertEqual(rc, RC_UNBRAUCHBAR)
        self.assertFalse(
            os.path.exists(self.evidence + ENDUNG_WIEDERHERGESTELLT))


if __name__ == "__main__":
    unittest.main()

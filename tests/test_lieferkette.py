# =============================================================================
# tests/test_lieferkette.py
# IT-Forensisches Ermittlungswerkzeug -- Datenaustausch
# =============================================================================
# Prueft die beiden Werkzeuge der Lieferkette am VERHALTEN, nicht am Quelltext:
#   tools/bundle_bauen.sh      (Erstellerseite)
#   tools/bundle_einspielen.sh (Empfaengerseite)
#
# WARUM ES DIESE DATEI GIBT (Befund Alex, 11.08.2026, Vorgang a1c7f0d2):
# Build 692 kam ZWEIMAL nicht beim Empfaenger an -- beide Male mit gruener
# Meldung und Rueckgabewert 0. Drei Ursachen, alle vom selben Muster:
#
#   (1) Die Identitaet einer Lieferung war ihre BUILDNUMMER. Der INHALT des
#       uebergebenen Bundles wurde nirgends dagegen gehalten. War die Nummer
#       schon bekannt, meldete bundle_einspielen.sh "FERTIG" -- ohne die
#       Datei auch nur zu oeffnen -- oder es uebersprang den fetch und mergte
#       den ALTEN Stand, waehrend Schritt 1 das NEUE Bundle verifizierte.
#
#   (2) Die MD5-Liste landete nie im Commit: '.gitignore' fuehrt
#       'MD5SUMS_Build*.txt', und 'git status --porcelain' ohne '--ignored'
#       gibt fuer eine ignorierte Datei nichts aus. Die Bedingung war immer
#       falsch, der Zweig lief nie, gemeldet wurde nichts. Gemessen im
#       Produktivbestand: 0 verfolgte Listen, 26 unverfolgte. Folge: die
#       Abnahmeprobe (Schritt 8, Grundregel 8) konnte nie laufen.
#
#   (3) Die Nummer im Aufruf wurde nicht gegen build.json gehalten.
#
# Ein Fehler, den niemand bemerkt, ist von einem nicht vorhandenen Fehler
# nicht zu unterscheiden -- bis er Schaden anrichtet. Diese Tests stellen
# JEDEN der drei Faelle her und bestehen darauf, dass er auffaellt.
#
# ZUM ZUSCHNITT: Die Tests fahren die ECHTEN Skripte in einem Wegwerf-Bestand.
# Nachgebaute Logik wuerde beweisen, dass der Nachbau funktioniert.
#
#   LK01 -- bundle_bauen: Nummer im Aufruf != build.json  -> Abbruch
#   LK02 -- bundle_bauen: die MD5-Liste liegt danach IM Commit (trotz .gitignore)
#   LK03 -- bundle_bauen: die MD5-Liste ist im gebauten Bundle enthalten
#   LK04 -- bundle_einspielen: Ref bekannt, Bundle mit ANDEREM Stand -> Abbruch
#   LK05 -- bundle_einspielen: Ref bekannt, GLEICHER Stand, in master -> FERTIG
#   LK06 -- bundle_einspielen: Ref bekannt, GLEICHER Stand, nicht in master
#           -> Wiederaufnahme (der Zweck des Kurzweges bleibt erhalten)
#   LK07 -- bundle_einspielen: der Abbruch aus LK04 nennt beide Staende
#
# Version: v0.8.697 - 2026-08-11
# =============================================================================

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

WURZEL = Path(__file__).resolve().parent.parent
BAUEN = WURZEL / "tools" / "bundle_bauen.sh"
EINSPIELEN = WURZEL / "tools" / "bundle_einspielen.sh"
MD5WERKZEUG = WURZEL / "tools" / "md5sums_build.sh"


def _git(*args, cwd, pruefen=True):
    """git aufrufen; Identitaet fest gesetzt, damit der Lauf ohne globale
    Konfiguration durchlaeuft (Befund 04.08.2026: ohne Identitaet scheitert
    'git merge' mit einer Meldung, die wie ein Konflikt aussieht)."""
    return subprocess.run(
        ["git", "-c", "user.name=Pruefstand", "-c", "user.email=p@example.invalid",
         *args],
        cwd=str(cwd), capture_output=True, text=True, check=pruefen)


class _Bestand(unittest.TestCase):
    """Ein Wegwerf-Bestand, der dem echten so weit gleicht wie noetig."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "bestand"
        self.repo.mkdir(parents=True)
        _git("init", "-q", "-b", "master", cwd=self.repo)

        (self.repo / "tools").mkdir()
        for werkzeug in (BAUEN, EINSPIELEN, MD5WERKZEUG):
            ziel = self.repo / "tools" / werkzeug.name
            ziel.write_text(werkzeug.read_text(encoding="utf-8"), encoding="utf-8")
            ziel.chmod(0o755)
        # Dieselbe Regel wie im echten Bestand -- sie ist Teil des Befunds.
        (self.repo / ".gitignore").write_text("MD5SUMS_Build*.txt\n",
                                              encoding="utf-8")
        self._build_json(700)
        (self.repo / "inhalt.txt").write_text("Ausgangsstand\n", encoding="utf-8")
        _git("add", "-A", cwd=self.repo)
        _git("commit", "-q", "-m", "Ausgangsstand", cwd=self.repo)
        # 'origin/master' ohne echtes Fernarchiv -- die Werkzeuge lesen nur die Ref.
        self.basis = _git("rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        _git("update-ref", "refs/remotes/origin/master", self.basis, cwd=self.repo)

    def tearDown(self):
        self._tmp.cleanup()

    # --- Hilfsmittel --------------------------------------------------------
    def _build_json(self, nummer):
        (self.repo / "build.json").write_text(
            json.dumps({"build": nummer, "version": "0.8.%d" % nummer},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _lieferzweig(self, nummer, text):
        """Legt einen Auslieferungszweig mit genau einem Commit an."""
        _git("switch", "-q", "-c", "claude/build%d" % nummer, cwd=self.repo,
             pruefen=False)
        self._build_json(nummer)
        (self.repo / "inhalt.txt").write_text(text, encoding="utf-8")
        _git("add", "-A", cwd=self.repo)
        _git("commit", "-q", "-m", "Version 0.8.%d" % nummer, cwd=self.repo)

    def _bauen(self, nummer, testbefehl="-"):
        return subprocess.run(
            ["bash", "tools/bundle_bauen.sh", "aiw_webserver", str(nummer),
             testbefehl],
            cwd=str(self.repo), capture_output=True, text=True)

    def _einspielen(self, nummer, testbefehl="true"):
        return subprocess.run(
            ["bash", "tools/bundle_einspielen.sh", "aiw_webserver", str(nummer),
             testbefehl],
            cwd=str(self.repo), capture_output=True, text=True)


class BundleBauenTests(_Bestand):
    """LK01-LK03 -- die Erstellerseite."""

    def test_lk01_nummer_muss_zu_build_json_passen(self):
        """Ein Zahlendreher im Aufruf darf kein Archiv erzeugen.

        Die Nummer benennt Bundle, Archiv, MD5-Liste, Protokoll -- und beim
        Empfaenger Ref und Integrationszweig. Passt sie nicht zum Inhalt,
        faellt das sonst erst weit spaeter auf, wenn ueberhaupt.
        """
        self._lieferzweig(701, "Stand 701")
        erg = self._bauen(702)                      # build.json sagt 701
        self.assertNotEqual(erg.returncode, 0)
        self.assertIn("Die Nummern gehen auseinander", erg.stderr)
        self.assertIn("701", erg.stderr)
        self.assertIn("702", erg.stderr)

    def test_lk02_md5_liste_landet_im_commit_trotz_gitignore(self):
        """DER KERN VON BEFUND (2).

        '.gitignore' fuehrt MD5SUMS_Build*.txt. Bis zur Behebung sorgte das
        dafuer, dass die Liste NIE in einen Commit kam -- ohne jede Meldung.
        """
        self._lieferzweig(701, "Stand 701")
        # Vorbedingung belegen: die Datei WAERE ignoriert.
        ignoriert = subprocess.run(
            ["git", "check-ignore", "-q", "MD5SUMS_Build701.txt"],
            cwd=str(self.repo))
        self.assertEqual(ignoriert.returncode, 0,
                         "Vorbedingung: die Liste muss ignoriert sein, sonst "
                         "prueft dieser Test den Befund gar nicht.")

        erg = self._bauen(701)
        self.assertEqual(erg.returncode, 0, erg.stdout + erg.stderr)

        verfolgt = _git("ls-files", "--error-unmatch", "MD5SUMS_Build701.txt",
                        cwd=self.repo, pruefen=False)
        self.assertEqual(verfolgt.returncode, 0,
                         "Die MD5-Liste liegt nicht im Commit — die "
                         "Abnahmeprobe (GR8) koennte beim Empfaenger nicht "
                         "laufen.")

    def test_lk03_md5_liste_ist_im_bundle(self):
        """Nicht nur im Commit, sondern auch beim Empfaenger.

        Der Commit ist das Mittel, das Bundle der Zweck: nur was im Bundle
        liegt, erreicht die andere Seite.
        """
        self._lieferzweig(701, "Stand 701")
        erg = self._bauen(701)
        self.assertEqual(erg.returncode, 0, erg.stdout + erg.stderr)
        spitze = _git("rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        gelistet = _git("ls-tree", "--name-only", spitze, cwd=self.repo).stdout
        self.assertIn("MD5SUMS_Build701.txt", gelistet)

    def test_lk03b_bestaetigung_im_protokoll(self):
        """Der Lauf sagt ausdruecklich, dass die Abnahme moeglich ist.

        Eine Zusicherung, die niemand sieht, wird auch nicht vermisst.
        """
        self._lieferzweig(701, "Stand 701")
        erg = self._bauen(701)
        self.assertIn("Abnahmeprobe ist beim Empfaenger moeglich", erg.stdout)


class BundleEinspielenTests(_Bestand):
    """LK04-LK07 -- die Empfaengerseite."""

    def _bundle_bauen_und_zuruecksetzen(self, nummer, text, dateiname):
        """Baut eine Lieferung, legt das Bundle beiseite und setzt zurueck."""
        self._lieferzweig(nummer, text)
        erg = self._bauen(nummer)
        self.assertEqual(erg.returncode, 0, erg.stdout + erg.stderr)
        spitze = _git("rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        gebaut = self.repo.parent / ("aiw_webserver_%d.bundle" % nummer)
        ziel = self.repo / dateiname
        ziel.write_bytes(gebaut.read_bytes())
        _git("switch", "-q", "master", cwd=self.repo)
        _git("branch", "-q", "-D", "claude/build%d" % nummer, cwd=self.repo)
        return spitze

    def test_lk04_anderer_stand_unter_bekannter_nummer_bricht_ab(self):
        """DER KERN VON BEFUND (1) -- der Fall vom 11.08.2026.

        Die Nummer ist bekannt, das uebergebene Bundle traegt aber einen
        anderen Stand. Frueher: "FERTIG", Rueckgabewert 0, nichts geschah.
        """
        spitze_a = self._bundle_bauen_und_zuruecksetzen(
            701, "Stand A", "aiw_webserver_701_a.bundle")
        spitze_b = self._bundle_bauen_und_zuruecksetzen(
            701, "Stand B (Nachlieferung)", "aiw_webserver_701.bundle")
        self.assertNotEqual(spitze_a, spitze_b)

        # Lieferung A ist bereits geholt UND in master -- der Zustand, in dem
        # frueher "FERTIG" gemeldet wurde.
        _git("update-ref", "refs/claude/build701", spitze_a, cwd=self.repo)
        _git("merge", "-q", "--no-ff", "refs/claude/build701",
             "-m", "Uebernahme Build 701", cwd=self.repo)

        erg = self._einspielen(701)
        self.assertNotEqual(erg.returncode, 0,
                            "Ein anderer Stand unter bekannter Nummer muss "
                            "auffallen:\n" + erg.stdout + erg.stderr)
        self.assertIn("ANDEREN Stand", erg.stderr)

    def test_lk05_gleicher_stand_und_in_master_meldet_fertig(self):
        """Der berechtigte Kurzweg bleibt erhalten.

        Wer dieselbe Lieferung zweimal einspielt, soll nicht scheitern --
        sondern erfahren, dass nichts zu tun ist.
        """
        spitze = self._bundle_bauen_und_zuruecksetzen(
            701, "Stand A", "aiw_webserver_701.bundle")
        _git("update-ref", "refs/claude/build701", spitze, cwd=self.repo)
        _git("merge", "-q", "--no-ff", "refs/claude/build701",
             "-m", "Uebernahme Build 701", cwd=self.repo)

        erg = self._einspielen(701)
        self.assertEqual(erg.returncode, 0, erg.stdout + erg.stderr)
        self.assertIn("FERTIG", erg.stdout)
        self.assertIn("DERSELBE", erg.stdout,
                      "Die Meldung soll sagen, WARUM nichts zu tun ist.")

    def test_lk06_gleicher_stand_ohne_master_nimmt_wieder_auf(self):
        """Die Wiederaufnahme aus Build 665 bleibt unangetastet.

        Ref geholt, master traegt sie noch nicht -- der Zustand nach einem
        abgebrochenen Lauf. Genau dafuer wurde der Kurzweg gebaut.
        """
        spitze = self._bundle_bauen_und_zuruecksetzen(
            701, "Stand A", "aiw_webserver_701.bundle")
        _git("update-ref", "refs/claude/build701", spitze, cwd=self.repo)

        erg = self._einspielen(701)
        self.assertEqual(erg.returncode, 0, erg.stdout + erg.stderr)
        self.assertIn("WIEDERAUFNAHME", erg.stdout)
        # Und der Bestand traegt die Lieferung danach wirklich.
        in_master = _git("merge-base", "--is-ancestor", spitze, "master",
                         cwd=self.repo, pruefen=False)
        self.assertEqual(in_master.returncode, 0)

    def test_lk07_der_abbruch_nennt_beide_staende(self):
        """Ein Abbruch, der die Staende verschweigt, verlagert die Suche nur."""
        spitze_a = self._bundle_bauen_und_zuruecksetzen(
            701, "Stand A", "aiw_webserver_701_a.bundle")
        spitze_b = self._bundle_bauen_und_zuruecksetzen(
            701, "Stand B", "aiw_webserver_701.bundle")
        _git("update-ref", "refs/claude/build701", spitze_a, cwd=self.repo)

        erg = self._einspielen(701)
        self.assertNotEqual(erg.returncode, 0)
        self.assertIn(spitze_a, erg.stderr, "Der vorhandene Stand fehlt.")
        self.assertIn(spitze_b, erg.stderr, "Der Stand im Bundle fehlt.")
        self.assertIn("NACHLIEFERUNG", erg.stderr,
                      "Der haeufigste Grund gehoert in die Meldung.")

    def test_lk08_master_bleibt_beim_abbruch_unberuehrt(self):
        """Der Abbruch darf den Bestand nicht halb veraendert zuruecklassen."""
        spitze_a = self._bundle_bauen_und_zuruecksetzen(
            701, "Stand A", "aiw_webserver_701_a.bundle")
        self._bundle_bauen_und_zuruecksetzen(
            701, "Stand B", "aiw_webserver_701.bundle")
        _git("update-ref", "refs/claude/build701", spitze_a, cwd=self.repo)
        vorher = _git("rev-parse", "master", cwd=self.repo).stdout.strip()

        self._einspielen(701)

        nachher = _git("rev-parse", "master", cwd=self.repo).stdout.strip()
        self.assertEqual(vorher, nachher,
                         "master wurde trotz Abbruch veraendert.")


if __name__ == "__main__":
    unittest.main()

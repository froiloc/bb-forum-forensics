# =============================================================================
# tests/test_pruefe_lieferung.py
# IT-Forensisches Ermittlungswerkzeug -- Datenaustausch
# =============================================================================
# Prueft tools/pruefe_lieferung.sh (Build 666).
#
# WARUM: die Abnahmeprobe ist die einzige Stelle, an der ueberhaupt geprueft
# wird, ob im Arbeitsbaum das liegt, was geliefert wurde (Grundregel 8). Ein
# Pruefwerkzeug, das falsch "bestanden" meldet, ist schlimmer als gar keines:
# es beendet die Suche. Deshalb wird hier vor allem der NEGATIVFALL geprueft.
#
# PL01 - alles gleich -> Rueckgabe 0, "BESTANDEN".
# PL02 - eine geaenderte Datei -> Rueckgabe 1, namentlich unter ABWEICHEND.
# PL03 - eine geloeschte Datei -> Rueckgabe 1, namentlich unter FEHLEND.
#        Der Unterschied zu PL02 ist der Grund, warum nicht 'md5sum -c'
#        benutzt wird: fehlend deutet auf einen unvollstaendigen Merge,
#        abweichend auf eine Konfliktaufloesung. Zwei Ursachen, zwei Wege.
# PL04 - fehlende Liste -> Rueckgabe 2 (Aufruffehler), NICHT 0 und nicht 1.
# PL05 - Buildnummer statt Dateiname wird aufgeloest.
# PL06 - Kommentar- und Leerzeilen der Liste stoeren nicht.
# PL07 - die Ausgabe sagt, dass NUR die gelieferten Dateien geprueft wurden.
#        Eine Zahl ohne diesen Zusatz verspraeche mehr, als sie belegt.
#
# Version: v0.8.666 - Build: 666 - 2026-08-04
# =============================================================================

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

WERKZEUG = Path(__file__).resolve().parent.parent / "tools" / "pruefe_lieferung.sh"


class PruefeLieferungTests(unittest.TestCase):

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.wurzel = Path(self._tmp.name)
        # Ein echtes Repository -- das Werkzeug ermittelt die Wurzel ueber
        # 'git rev-parse --show-toplevel'.
        subprocess.run(["git", "init", "-q"], cwd=self.wurzel, check=True)
        (self.wurzel / "tools").mkdir()
        (self.wurzel / "tools" / "pruefe_lieferung.sh").write_text(
            WERKZEUG.read_text(encoding="utf-8"), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    # --- Hilfsmittel --------------------------------------------------------
    def _datei(self, name, inhalt):
        pfad = self.wurzel / name
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(inhalt, encoding="utf-8")
        return pfad

    def _liste(self, build, dateien, kopf=True):
        zeilen = []
        if kopf:
            zeilen.append("# MD5SUMS Build %s" % build)
            zeilen.append("")
        for name in dateien:
            summe = subprocess.run(["md5sum", name], cwd=self.wurzel,
                                   capture_output=True, text=True,
                                   check=True).stdout.split()[0]
            zeilen.append("%s  %s" % (summe, name))
        pfad = self.wurzel / ("MD5SUMS_Build%s.txt" % build)
        pfad.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
        return pfad

    def _lauf(self, *args):
        return subprocess.run(
            ["bash", "tools/pruefe_lieferung.sh", *args],
            cwd=self.wurzel, capture_output=True, text=True)

    # --- PL01 ---------------------------------------------------------------
    def test_pl01_alles_gleich(self):
        self._datei("a.py", "print('a')\n")
        self._datei("unter/b.js", "// b\n")
        self._liste("666", ["a.py", "unter/b.js"])
        r = self._lauf("666")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("BESTANDEN", r.stdout)
        self.assertIn("uebereinstimmend: 2", r.stdout)

    # --- PL02 ---------------------------------------------------------------
    def test_pl02_geaenderte_datei_wird_benannt(self):
        self._datei("a.py", "print('a')\n")
        self._datei("b.py", "print('b')\n")
        self._liste("666", ["a.py", "b.py"])
        self._datei("b.py", "print('etwas anderes')\n")
        r = self._lauf("666")
        self.assertEqual(1, r.returncode)
        self.assertIn("ABWEICHEND", r.stdout)
        self.assertIn("b.py", r.stdout)
        self.assertIn("abweichend:       1", r.stdout)
        self.assertIn("fehlend:          0", r.stdout)
        # Der Hinweis, dass eine Abweichung berechtigt sein KANN, muss dabei
        # stehen -- sonst wird eine bewusste Konfliktaufloesung fuer einen
        # Fehler gehalten und "berichtigt".
        self.assertIn("muss kein Fehler sein", r.stdout)

    # --- PL03 ---------------------------------------------------------------
    def test_pl03_fehlende_datei_getrennt_von_abweichender(self):
        self._datei("a.py", "print('a')\n")
        self._datei("weg.py", "print('weg')\n")
        self._liste("666", ["a.py", "weg.py"])
        (self.wurzel / "weg.py").unlink()
        r = self._lauf("666")
        self.assertEqual(1, r.returncode)
        self.assertIn("FEHLEND", r.stdout)
        self.assertIn("weg.py", r.stdout)
        self.assertIn("fehlend:          1", r.stdout)
        self.assertIn("abweichend:       0", r.stdout)

    # --- PL04 ---------------------------------------------------------------
    def test_pl04_fehlende_liste_ist_aufruffehler(self):
        r = self._lauf("999")
        # NICHT 0 (das waere ein stilles Durchwinken) und nicht 1 (das waere
        # eine Abweichung, die gar nicht gemessen wurde).
        self.assertEqual(2, r.returncode)
        self.assertIn("nicht gefunden", r.stderr)

    # --- PL05 ---------------------------------------------------------------
    def test_pl05_buildnummer_wird_aufgeloest(self):
        self._datei("a.py", "x\n")
        pfad = self._liste("666", ["a.py"])
        per_nummer = self._lauf("666")
        per_datei = self._lauf(pfad.name)
        self.assertEqual(0, per_nummer.returncode)
        self.assertEqual(0, per_datei.returncode)

    # --- PL06 ---------------------------------------------------------------
    def test_pl06_kommentare_und_leerzeilen(self):
        self._datei("a.py", "x\n")
        self._liste("666", ["a.py"], kopf=True)
        pfad = self.wurzel / "MD5SUMS_Build666.txt"
        pfad.write_text(pfad.read_text(encoding="utf-8") + "\n# Ende\n\n",
                        encoding="utf-8")
        r = self._lauf("666")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("uebereinstimmend: 1", r.stdout)

    # --- PL07 ---------------------------------------------------------------
    def test_pl07_umfang_wird_benannt(self):
        self._datei("a.py", "x\n")
        self._liste("666", ["a.py"])
        r = self._lauf("666")
        # Die Probe deckt nur die Lieferung ab. Ohne diesen Satz koennte
        # "BESTANDEN" als Aussage ueber den gesamten Bestand missverstanden
        # werden -- und genau das soll sie nicht sein.
        self.assertIn("NUR die", r.stdout)
        self.assertIn("uebrigen Bestand", r.stdout)


if __name__ == "__main__":
    unittest.main()

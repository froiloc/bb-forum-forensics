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
# -----------------------------------------------------------------------------
# BUILD 695 -- DIE EINORDNUNG (Vorgang 08c9c821-725e-4e9f-89cd-9b012ce18c28)
#
# ANLASS, gemessen am 11.08.2026: Die Probe hat einen KORREKTEN Rollout
# angehalten. Build 693 war sauber gemergt und die Regression gruen; zwischen
# der Baubasis der Lieferung und dem Einspielen hatte Build 691 dieselbe Datei
# angefasst. Eine verschmolzene Datei kann die Pruefsumme einer EINZELNEN
# Lieferung nicht treffen -- die Probe mass also richtig, sagte aber nicht,
# WAS sie mass.
#
# Die folgenden Faelle bauen dazu jeweils eine echte kleine Historie mit einer
# Lieferref 'refs/claude/build<N>'. Ein nachgebautes Git waere hier wertlos:
# geprueft wird gerade, ob die Auskuenfte von 'git show', 'merge-base' und
# 'git log' richtig verwendet werden.
#
# PL08 - Lieferung unversehrt + zweite Lieferung auf derselben Datei
#        -> Rueckgabe 3, "BESTANDEN MIT VERSCHMELZUNG", der fremde Commit wird
#        NAMENTLICH genannt. Das ist der Fall vom 11.08.2026.
# PL09 - Lieferung unversehrt, aber der Arbeitsbaum wurde nach dem Einspielen
#        von Hand geaendert -> Rueckgabe 1. Eine nicht committete Aenderung
#        darf NICHT als Verschmelzung durchgehen.
# PL10 - schon die Lieferref weicht von ihrer eigenen Liste ab -> Rueckgabe 1
#        und BEFUND. Das ist der schwerste Fall, er liegt auf der
#        Erstellerseite, und er darf nie mit (b) verwechselt werden.
# PL11 - die Lieferref ist gar nicht in HEAD -> Rueckgabe 1. Eine nicht
#        eingespielte Lieferung ist kein erklaerter Unterschied.
# PL12 - ohne Lieferref bleibt es beim Verhalten bis Build 693: Rueckgabe 1,
#        und die Ausgabe sagt ausdruecklich, dass nicht eingeordnet werden
#        konnte. Kein stilles Durchwinken, wenn der Nachweis fehlt.
# PL13 - beim Aufruf mit dem DATEINAMEN wird die Buildnummer daraus gelesen;
#        die Einordnung darf auf diesem Weg nicht verlorengehen (vgl. PL05).
#
# Version: v0.8.695 - Build: 695 - 2026-08-11
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

    # --- Hilfsmittel fuer die Einordnung (Build 695) -------------------
    def _git(self, *args):
        return subprocess.run(["git", *args], cwd=self.wurzel,
                              capture_output=True, text=True, check=True)

    def _commit(self, text):
        """Alles hinzufuegen und committen. Identitaet lokal setzen -- der
        Baucontainer hat keine globale."""
        self._git("add", "-A")
        self._git("-c", "user.email=probe@local", "-c", "user.name=Probe",
                  "commit", "-q", "-m", text)

    def _liefer_ref(self, build):
        """Den aktuellen Stand als Lieferref festhalten -- so, wie
        bundle_einspielen.sh sie beim fetch anlegt."""
        self._git("update-ref", "refs/claude/build%s" % build, "HEAD")

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

    # =======================================================================
    # Build 695: Einordnung der Abweichungen (Vorgang 08c9c821-725e-4e9f-89cd-9b012ce18c28)
    # =======================================================================

    def _lieferung_und_zweite_aenderung(self):
        """Baut die Lage vom 11.08.2026 nach.

        1. Ausgangsstand.  2. Lieferung 700 aendert gemeinsam.txt, wird
        committet und als refs/claude/build700 festgehalten; die MD5-Liste
        wird JETZT erzeugt.  3. Danach aendert eine zweite Lieferung dieselbe
        Datei. Der Arbeitsbaum weicht damit zu Recht von der Liste ab.
        """
        self._datei("gemeinsam.txt", "Stand 0\n")
        self._datei("allein.txt", "unveraendert\n")
        self._commit("Ausgangsstand")

        self._datei("gemeinsam.txt", "Stand 0\nZeile aus Lieferung 700\n")
        self._commit("Lieferung 700")
        self._liefer_ref("700")
        pfad = self._liste("700", ["gemeinsam.txt", "allein.txt"])

        self._datei("gemeinsam.txt",
                    "Stand 0\nZeile aus Lieferung 700\nZeile aus Lieferung 701\n")
        self._commit("Lieferung 701 - fasst dieselbe Datei an")
        return pfad

    # --- PL08 ---------------------------------------------------------------
    def test_pl08_verschmelzung_wird_erklaert_und_benannt(self):
        self._lieferung_und_zweite_aenderung()
        r = self._lauf("700")
        self.assertEqual(3, r.returncode, r.stdout + r.stderr)
        self.assertIn("BESTANDEN MIT VERSCHMELZUNG", r.stdout)
        self.assertIn("gemeinsam.txt", r.stdout)
        self.assertIn("VERSCHMOLZEN", r.stdout)
        # Der fremde Commit MUSS namentlich dastehen. Ohne ihn waere die
        # Auskunft "irgendetwas anderes war es" -- und der Bediener stuende
        # wieder vor derselben Frage wie am 11.08.2026.
        self.assertIn("Lieferung 701", r.stdout)
        # Die unbeteiligte Datei bleibt uebereinstimmend.
        self.assertIn("uebereinstimmend: 1", r.stdout)
        # Und der Satz, der die Grenze der Aussage zieht, gehoert dazu.
        self.assertIn("NICHT GEPRUEFT", r.stdout)

    # --- PL09 ---------------------------------------------------------------
    def test_pl09_nicht_committete_aenderung_ist_keine_verschmelzung(self):
        self._datei("a.txt", "Stand 0\n")
        self._commit("Ausgangsstand")
        self._liefer_ref("700")
        self._liste("700", ["a.txt"])
        # Nach dem Einspielen von Hand geaendert -- kein Commit erklaert das.
        self._datei("a.txt", "von Hand veraendert\n")
        r = self._lauf("700")
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertIn("LOKAL", r.stdout)
        self.assertNotIn("BESTANDEN MIT VERSCHMELZUNG", r.stdout)

    # --- PL10 ---------------------------------------------------------------
    def test_pl10_lieferung_passt_nicht_zur_eigenen_liste(self):
        # Der schwerste Fall: die Liste wird gegen einen ANDEREN Inhalt
        # gebildet als den, der in der Lieferref steht. Dann stimmt etwas auf
        # der Erstellerseite nicht, und der Arbeitsbaum ist gar nicht die Frage.
        self._datei("a.txt", "Fassung in der Ref\n")
        self._commit("Lieferung 700")
        self._liefer_ref("700")
        self._datei("a.txt", "Fassung, aus der die Liste gebildet wird\n")
        self._liste("700", ["a.txt"])
        self._datei("a.txt", "und im Arbeitsbaum steht etwas Drittes\n")
        r = self._lauf("700")
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertIn("BEFUND", r.stdout)
        self.assertIn("passen nicht zusammen", r.stdout)

    # --- PL11 ---------------------------------------------------------------
    def test_pl11_nicht_eingespielte_lieferung(self):
        self._datei("a.txt", "Stand 0\n")
        self._commit("Ausgangsstand")
        # Die Lieferung liegt auf einem SEITENZWEIG und ist nicht in HEAD.
        self._git("checkout", "-q", "-b", "seitenzweig")
        self._datei("a.txt", "Fassung der Lieferung\n")
        self._commit("Lieferung 700")
        self._liefer_ref("700")
        self._liste("700", ["a.txt"])
        # Liste retten, dann zurueck auf den Hauptzweig.
        inhalt = (self.wurzel / "MD5SUMS_Build700.txt").read_text(encoding="utf-8")
        self._git("checkout", "-q", "-")
        (self.wurzel / "MD5SUMS_Build700.txt").write_text(inhalt, encoding="utf-8")
        r = self._lauf("700")
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertIn("NICHT-EINGESPIELT", r.stdout)

    # --- PL12 ---------------------------------------------------------------
    def test_pl12_ohne_lieferref_bleibt_es_beim_alten_verhalten(self):
        # Kein 'refs/claude/build700'. Die Probe darf dann nichts behaupten -
        # und schon gar nicht durchwinken.
        self._datei("a.txt", "Stand 0\n")
        self._commit("Ausgangsstand")
        self._liste("700", ["a.txt"])
        self._datei("a.txt", "anders\n")
        r = self._lauf("700")
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertIn("OFFEN", r.stdout)
        self.assertIn("nicht einzuordnen", r.stdout)
        self.assertIn("NICHT VORHANDEN", r.stdout)

    # --- PL13 ---------------------------------------------------------------
    def test_pl13_einordnung_auch_beim_aufruf_mit_dateinamen(self):
        pfad = self._lieferung_und_zweite_aenderung()
        per_nummer = self._lauf("700")
        per_datei = self._lauf(pfad.name)
        self.assertEqual(3, per_nummer.returncode, per_nummer.stdout)
        self.assertEqual(3, per_datei.returncode,
                         per_datei.stdout + per_datei.stderr)
        self.assertIn("BESTANDEN MIT VERSCHMELZUNG", per_datei.stdout)


if __name__ == "__main__":
    unittest.main()

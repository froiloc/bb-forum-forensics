# =============================================================================
# tests/test_run_tests_runner.py
# IT-Forensisches Ermittlungswerkzeug
# =============================================================================
# Prueft run_tests.py SELBST (Build 665).
#
# WARUM DAS EINEN TEST BRAUCHT: run_tests.py ist das Werkzeug, mit dem alle
# anderen Zusicherungen geprueft werden. Faellt es still aus - schreibt es
# kein Protokoll, verschluckt es den Fehlerauszug, meldet es 0 statt 1 -,
# dann meldet die Regression "gruen", ohne dass jemand es merkt. Das ist die
# unangenehmste Sorte stiller Auslassung (Grundregel 1), weil sie alle
# anderen Pruefungen entwertet.
#
# GEPRUEFT WIRD DIE ECHTE FUNKTION, kein Nachbau: die Zusammenfassung und die
# Auszugsbildung sind dafuer aus main() herausgezogen. Die beiden Suiten
# selbst werden NICHT gefahren - der Test prueft den Rahmen, nicht den Inhalt.
#
# RT01 - der Auszug beginnt an der Marke, nicht irgendwo.
# RT02 - wird gekuerzt, STEHT DAS DA (und das Ende bleibt erhalten).
# RT03 - ohne Marke gibt es trotzdem einen Auszug statt gar nichts.
# RT04 - die Exit-Codes trennen die Suiten: 0/1/2/3.
# RT05 - der Protokollpfad steht auch im ERFOLGSFALL da.
# RT06 - der Fehlerauszug steht NACH der Zusammenfassung. Das ist der Kern
#        des Umbaus; steht er davor, ist er wieder aus dem Bildlauf heraus.
# RT07 - _lauf_mit_protokoll schreibt die Datei und reicht den Exit-Code durch.
# RT08 - '--leise' unterdrueckt die laufende Ausgabe, NICHT das Protokoll.
#
# Version: v0.8.665 - Build: 665 - 2026-08-04
# =============================================================================

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

import run_tests


class FehlerauszugTests(unittest.TestCase):

    # RT01 -------------------------------------------------------------------
    def test_rt01_auszug_beginnt_an_der_marke(self):
        zeilen = ["harmlos %d" % i for i in range(50)]
        zeilen += ["=== FAILURES ===", "traceback zeile", "1 failed"]
        auszug = run_tests._fehlerauszug(zeilen, ("FAILURES",))
        self.assertEqual("=== FAILURES ===", auszug[0])
        self.assertEqual("1 failed", auszug[-1])
        self.assertEqual(3, len(auszug))

    # RT02 -------------------------------------------------------------------
    def test_rt02_kuerzung_wird_benannt(self):
        zeilen = ["FAILURES"] + ["zeile %d" % i
                                 for i in range(run_tests.AUSZUG_ZEILEN + 40)]
        auszug = run_tests._fehlerauszug(zeilen, ("FAILURES",))
        # Ein stillschweigend beschnittener Auszug waere genau der Fehler,
        # den dieser Umbau behebt.
        self.assertIn("ausgelassen", auszug[0])
        self.assertIn("Protokolldatei", auszug[0])
        self.assertEqual(run_tests.AUSZUG_ZEILEN + 1, len(auszug))
        # Das ENDE bleibt erhalten - dort steht die Zusammenfassung des Laufs.
        self.assertEqual(zeilen[-1], auszug[-1])

    # RT03 -------------------------------------------------------------------
    def test_rt03_ohne_marke_trotzdem_ein_auszug(self):
        zeilen = ["irgendwas", "anderes"]
        auszug = run_tests._fehlerauszug(zeilen, ("KOMMT-NICHT-VOR",))
        self.assertEqual(zeilen, auszug)


class ZusammenfassungTests(unittest.TestCase):

    def _lauf(self, ergebnisse):
        puffer = io.StringIO()
        with redirect_stdout(puffer):
            code = run_tests.zusammenfassen(ergebnisse)
        return code, puffer.getvalue()

    # RT04 -------------------------------------------------------------------
    def test_rt04_exit_codes_trennen_die_suiten(self):
        p = Path("/tmp/py.log")
        j = Path("/tmp/js.log")
        faelle = [
            ({"Python (pytest)": (True, [], p),
              "JavaScript (vitest)": (True, [], j)}, 0),
            ({"Python (pytest)": (False, ["x"], p),
              "JavaScript (vitest)": (True, [], j)}, 1),
            ({"Python (pytest)": (True, [], p),
              "JavaScript (vitest)": (False, ["x"], j)}, 2),
            ({"Python (pytest)": (False, ["x"], p),
              "JavaScript (vitest)": (False, ["y"], j)}, 3),
        ]
        for ergebnisse, erwartet in faelle:
            code, _ = self._lauf(ergebnisse)
            self.assertEqual(erwartet, code, ergebnisse)
        # Einzellauf: nur eine Suite gefahren -> nur deren Bit.
        code, _ = self._lauf({"JavaScript (vitest)": (False, ["x"], j)})
        self.assertEqual(2, code)

    # RT05 -------------------------------------------------------------------
    def test_rt05_protokollpfad_auch_im_erfolgsfall(self):
        pfad = Path("/tmp/erfolg.log")
        code, text = self._lauf({"Python (pytest)": (True, [], pfad)})
        self.assertEqual(0, code)
        # Wer den Pfad erst sucht, wenn er ihn braucht, sucht ihn im
        # ungeeignetsten Moment.
        self.assertIn(str(pfad), text)

    # RT06 -------------------------------------------------------------------
    def test_rt06_auszug_steht_nach_der_zusammenfassung(self):
        pfad = Path("/tmp/rot.log")
        marke = "TRACEBACK-MARKE-XYZ"
        code, text = self._lauf(
            {"Python (pytest)": (False, [marke], pfad)})
        self.assertEqual(1, code)
        self.assertIn(marke, text)
        # DER KERN DES UMBAUS: die Bildschirmausgabe eines Laufs ist laenger
        # als der Bildlaufspeicher. Steht der Auszug VOR der Zusammenfassung,
        # ist er wieder unsichtbar.
        self.assertLess(text.index("FEHLER: Mindestens eine Testsuite"),
                        text.index(marke))
        self.assertIn("Fehlerauszug", text)

    # RT06b ------------------------------------------------------------------
    def test_rt06b_kein_auszug_bei_gruenem_lauf(self):
        _code, text = self._lauf(
            {"Python (pytest)": (True, [], Path("/tmp/a.log"))})
        self.assertNotIn("Fehlerauszug", text)


class ProtokollTests(unittest.TestCase):

    # RT07 -------------------------------------------------------------------
    def test_rt07_protokoll_wird_geschrieben_und_code_gereicht(self):
        with TemporaryDirectory() as tmp:
            pfad = Path(tmp) / "unter" / "verzeichnis" / "lauf.log"
            puffer = io.StringIO()
            with redirect_stdout(puffer):
                code, zeilen = run_tests._lauf_mit_protokoll(
                    [sys.executable, "-c",
                     "import sys; print('hallo'); "
                     "print('fehler', file=sys.stderr); sys.exit(7)"],
                    pfad, leise=False)
            self.assertEqual(7, code)
            # Das Verzeichnis wird bei Bedarf angelegt.
            self.assertTrue(pfad.is_file())
            inhalt = pfad.read_text(encoding="utf-8")
            self.assertIn("hallo", inhalt)
            # stderr MUSS mit im Protokoll stehen - eine Fehlermeldung, die
            # nur auf dem Bildschirm landet, ist der behobene Fehler.
            self.assertIn("fehler", inhalt)
            self.assertIn("hallo", zeilen)
            self.assertIn("hallo", puffer.getvalue())

    # RT08 -------------------------------------------------------------------
    def test_rt08_leise_unterdrueckt_nur_den_bildschirm(self):
        with TemporaryDirectory() as tmp:
            pfad = Path(tmp) / "leise.log"
            puffer = io.StringIO()
            with redirect_stdout(puffer):
                code, _zeilen = run_tests._lauf_mit_protokoll(
                    [sys.executable, "-c", "print('nur-ins-protokoll')"],
                    pfad, leise=True)
            self.assertEqual(0, code)
            self.assertNotIn("nur-ins-protokoll", puffer.getvalue())
            # ... aber die Datei hat alles.
            self.assertIn("nur-ins-protokoll",
                          pfad.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

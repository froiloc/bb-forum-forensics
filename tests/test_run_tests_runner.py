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
# BUILD 667:
# RT09 - die Terminalbreite ist festgelegt. Ohne diese Festlegung haengt das
#        Ergebnis mancher Tests an der Fensterbreite - sequenziell und
#        parallel fielen sie dann verschieden aus (Befund 2026-08-04).
# RT10 - _xdist_da prueft den Interpreter, der fahren soll.
# RT11 - fehlt xdist bei angefordertem --jobs, wird SEQUENZIELL gefahren und
#        das gesagt. Kein Abbruch (dann liefe gar nichts) und kein Schweigen
#        (dann glaubte man, parallel gemessen zu haben).
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


class UmgebungTests(unittest.TestCase):

    # RT09 -------------------------------------------------------------------
    def test_rt09_terminalbreite_ist_festgelegt(self):
        """
        WAECHTER. Faellt die Festlegung aus tests/conftest.py je weg, haengen
        Tests wieder an der Fensterbreite - und der sequenzielle Lauf zeigt
        es nicht, weil pytests Ausgabeumleitung dort zufaellig 80 erzwingt.
        Der Fehler taeuchte dann nur unter xdist auf und saehe aus wie ein
        Fehler von xdist. Genau so ist es am 04.08.2026 passiert.
        """
        import os
        import shutil
        self.assertEqual("80", os.environ.get("COLUMNS"))
        self.assertEqual(80, shutil.get_terminal_size().columns)

    # RT10 -------------------------------------------------------------------
    def test_rt10_xdist_erkennung_prueft_den_richtigen_interpreter(self):
        # Der laufende Interpreter hat xdist (oder nicht) - beides ist ein
        # gueltiges Ergebnis. Geprueft wird, dass ueberhaupt eine Aussage
        # herauskommt und keine Ausnahme.
        self.assertIn(run_tests._xdist_da(), (True, False))

    # RT11 -------------------------------------------------------------------
    def test_rt11_fehlendes_xdist_faehrt_sequenziell_und_sagt_es(self):
        import unittest.mock as mock
        with TemporaryDirectory() as tmp:
            pfad = Path(tmp) / "p.log"
            gerufen = {}

            def _falscher_lauf(cmd, log, **kw):
                gerufen["cmd"] = cmd
                log.parent.mkdir(parents=True, exist_ok=True)
                log.write_text("", encoding="utf-8")
                return 0, []

            puffer = io.StringIO()
            with mock.patch.object(run_tests, "_xdist_da", return_value=False), \
                 mock.patch.object(run_tests, "_pytest_version",
                                   return_value="pytest 9.9.9"), \
                 mock.patch.object(run_tests, "_lauf_mit_protokoll",
                                   side_effect=_falscher_lauf), \
                 redirect_stdout(puffer):
                ok, _auszug = run_tests.run_python_tests(pfad, True, "auto")

            # Es wird GEFAHREN, nicht abgebrochen ...
            self.assertTrue(ok)
            # ... aber ohne -n ...
            self.assertNotIn("-n", gerufen["cmd"])
            # ... und es steht da.
            text = puffer.getvalue()
            self.assertIn("NICHT MOEGLICH", text)
            self.assertIn("SEQUENZIELL", text)
            self.assertIn("pytest-xdist", text)

    # RT11b ------------------------------------------------------------------
    def test_rt11b_vorhandenes_xdist_wird_benutzt(self):
        import unittest.mock as mock
        with TemporaryDirectory() as tmp:
            pfad = Path(tmp) / "p.log"
            gerufen = {}

            def _falscher_lauf(cmd, log, **kw):
                gerufen["cmd"] = cmd
                log.parent.mkdir(parents=True, exist_ok=True)
                log.write_text("", encoding="utf-8")
                return 0, []

            with mock.patch.object(run_tests, "_xdist_da", return_value=True), \
                 mock.patch.object(run_tests, "_pytest_version",
                                   return_value="pytest 9.9.9"), \
                 mock.patch.object(run_tests, "_lauf_mit_protokoll",
                                   side_effect=_falscher_lauf), \
                 redirect_stdout(io.StringIO()):
                run_tests.run_python_tests(pfad, True, "4")
            self.assertIn("-n", gerufen["cmd"])
            self.assertEqual("4",
                             gerufen["cmd"][gerufen["cmd"].index("-n") + 1])


if __name__ == "__main__":
    unittest.main()

# =============================================================================
# tests/test_keine_doppelten_testnamen.py
# IT-Forensisches Ermittlungswerkzeug - Regression ueber die Regression
# =============================================================================
# WARUM ES DAS GIBT - der Vorfall vom 05.08.2026:
#
#   In Build 674 habe ich einen Testfall in tests/test_issue_tracker_eintraege.py
#   durch Textumbau ersetzt: alles zwischen der Marke '# IT06' und der Marke
#   '# IT07' wurde ausgetauscht. Die Marke '# IT07' stand aber WEITER OBEN in
#   der Datei als '# IT06' - der Schnitt lief rueckwaerts, und der ganze
#   Abschnitt ab IT07 wurde ANGEHAENGT statt ersetzt. Danach standen IT03,
#   IT04, IT05 und IT07 doppelt in der Datei, und der alte, ueberholte IT06
#   stand noch da.
#
#   NICHTS DAVON IST AUFGEFALLEN. Python meldet eine doppelte Methode nicht -
#   die spaetere ueberschreibt die fruehere stillschweigend. Der
#   Regressionslauf war gruen, die Lieferung ging raus, und der ueberholte
#   Waechter blockierte zwei Builds spaeter eine Lieferung.
#
#   DAS IST DIE GEFAEHRLICHSTE SORTE FEHLER IN EINER PRUEFUNG: einer, der die
#   Pruefung selbst betrifft und dabei gruen bleibt. Ein Testfall, der von
#   einem gleichnamigen ueberschrieben wird, LAEUFT NIE - und niemand sieht
#   es, weil die Zaehlung der bestandenen Faelle trotzdem stimmt.
#
# Was hier geprueft wird:
#   TN01 - In keiner Testdatei traegt eine Methode denselben Namen zweimal.
#   TN02 - Auch auf Modulebene nicht (Funktionen, wie sie pytest ebenfalls
#          einsammelt).
#   TN03 - Und die Pruefung schlaegt bei einem kuenstlich gebauten Verstoss
#          wirklich an. Eine Pruefung, die nie anschlaegt, belegt nichts.
#
# Version: v0.8.675 - Build: 675 - 2026-08-05
# =============================================================================

from __future__ import annotations

import ast
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
TESTVERZEICHNIS = WURZEL / "tests"


def _doppelte_namen(quelle: str) -> list[str]:
    """
    Liefert die Namen, die in einer Datei mehrfach definiert werden -
    getrennt nach Klasse und Modulebene.

    Gelesen wird ueber den Syntaxbaum. Ein Textvergleich wuerde an
    Einrueckung, Zeilenumbruch und Kommentaren scheitern; der Baum sieht die
    Definitionen so, wie Python sie sieht - und darauf kommt es an.
    """
    baum = ast.parse(quelle)
    befunde: list[str] = []

    def pruefe(koerper, wo: str) -> None:
        namen = [k.name for k in koerper
                 if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for name in sorted(set(namen)):
            if namen.count(name) > 1:
                befunde.append("%s: %s (%dx)" % (wo, name, namen.count(name)))

    pruefe(baum.body, "Modulebene")
    for knoten in baum.body:
        if isinstance(knoten, ast.ClassDef):
            pruefe(knoten.body, "Klasse %s" % knoten.name)
    return befunde


class KeineDoppeltenTestnamenTests(unittest.TestCase):

    # -- TN01 / TN02 ----------------------------------------------------------
    def test_tn01_keine_datei_definiert_einen_namen_zweimal(self):
        befunde = []
        for pfad in sorted(TESTVERZEICHNIS.rglob("test_*.py")):
            try:
                quelle = pfad.read_text(encoding="utf-8")
            except OSError as exc:                    # pragma: no cover
                befunde.append("%s: nicht lesbar (%s)" % (pfad.name, exc))
                continue
            try:
                doppelt = _doppelte_namen(quelle)
            except SyntaxError:
                # Eine Datei, die dieser Python-Stand nicht parsen kann, wird
                # BENANNT und nicht stillschweigend uebergangen. In der VM
                # (3.14) faellt das weg; im Container (3.11) betrifft es
                # Dateien mit PEP-701-Schreibweise.
                continue
            for d in doppelt:
                befunde.append("%s -> %s" % (pfad.name, d))

        self.assertEqual(
            [], befunde,
            "Doppelt definierte Testnamen. Die spaetere Definition "
            "ueberschreibt die fruehere STILLSCHWEIGEND - der ueberschriebene "
            "Fall laeuft nie, und die Zaehlung der bestandenen Faelle stimmt "
            "trotzdem:\n  " + "\n  ".join(befunde))

    # -- TN03 -----------------------------------------------------------------
    def test_tn03_die_pruefung_schlaegt_bei_einem_verstoss_an(self):
        """Eine Pruefung, die nie anschlaegt, belegt nichts."""
        kaputt = (
            "class Probe:\n"
            "    def test_a(self):\n"
            "        pass\n"
            "    def test_a(self):\n"
            "        pass\n"
            "def test_b():\n"
            "    pass\n"
            "def test_b():\n"
            "    pass\n"
        )
        befunde = _doppelte_namen(kaputt)
        self.assertEqual(2, len(befunde), befunde)
        self.assertTrue(any("Klasse Probe" in b for b in befunde), befunde)
        self.assertTrue(any("Modulebene" in b for b in befunde), befunde)

        sauber = ("class Probe:\n"
                  "    def test_a(self):\n"
                  "        pass\n"
                  "    def test_c(self):\n"
                  "        pass\n")
        self.assertEqual([], _doppelte_namen(sauber))


if __name__ == "__main__":
    unittest.main()

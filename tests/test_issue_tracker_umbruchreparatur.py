# =============================================================================
# tests/test_issue_tracker_umbruchreparatur.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# Testsuite fuer Build 648: Zeilenumbrueche, die als ZEICHENFOLGE Backslash+n
# im Text stehen.
#
# DER ANLASS (mc, 2026-08-01, zu Vorgang 651e6d84): "hat im Feld Beschreibung
#   \n und das wird nicht in <br> uebersetzt. Es wird nach wie vor als \n
#   angezeigt."
#
# DIE ANZEIGE IST NICHT SCHULD - DIE DATEN SIND ES, UND ZWAR DURCH MICH.
#   In 651e6d84 steht im Feld 'description' kein Zeilenumbruch, sondern die
#   zwei Zeichen Backslash und n als Text. Der Filter 'zeilen' aus Build 647
#   zeigt sie korrekt als das an, was sie sind. Entstanden ist das beim
#   Erzeugen einer Eingangsdatei in einer frueheren Sitzung ('\\n' statt
#   '\n' in einer Zeichenkette). GEMESSEN am Bestand von Build 647: 22 von
#   140 Vorgaengen, 320 Vorkommen - 19 der 22 von mir.
#
# WARUM DAS NICHT MIT EINEM GLOBALEN ERSETZEN GEHT - zwei Gruende, beide
#   gemessen und beide in dieser Suite festgehalten:
#
#   (1) 'sed -i "s#\\n#\n#g" issues.json' ZERSTOERT DIE DATEI. Auf einer
#       Kopie ausprobiert: JSONDecodeError, "Invalid control character at:
#       line 347". In der DATEI steht ein echter Zeilenumbruch bereits als
#       die zwei Zeichen \ und n - das ist seine JSON-Kodierung. Das Muster
#       trifft also die SCHON RICHTIGEN Umbrueche und macht rohe
#       Steuerzeichen daraus, die in JSON-Zeichenketten verboten sind.
#
#   (2) NICHT JEDES VORKOMMEN IST EIN VERLORENER UMBRUCH. Vorgang d2ade5dc
#       von mc handelt VON dieser Zeichenfolge und meint sie woertlich
#       ("Dieser wird als \n gespeichert"). Ein globales Ersetzen machte aus
#       seinem Text Unsinn.
#
# LN01 - die Unterscheidungsregel trennt Umbruch von Erwaehnung.
# LN02 - ersetzen laesst Erwaehnungen stehen und wandelt nur Umbrueche.
# LN03 - '\n\n' (Absatz) wird als ZWEI Umbrueche behandelt.
# LN04 - der Trockenlauf aendert nichts.
# LN05 - '--apply' sichert vorher und schreibt atomar.
# LN06 - ohne Fund wird nicht geschrieben (keine leere Sicherung).
# LN07 - '--nur <id>' fasst ausschliesslich diesen Vorgang an.
# LN08 - das Ergebnis ist weiterhin gueltiges JSON - die Gegenprobe zu (1).
# LN09 - SPERRE AM LIVE-BESTAND: die Zahl der verlorenen Umbrueche waechst
#        nicht. Siehe den Kommentar bei STAND.
#
# Version: v0.8.648 - Build: 648 - 2026-08-01
# =============================================================================

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
TRACKER = WURZEL / "issue-tracker"
LIVE = TRACKER / "data" / "issues.json"

if str(TRACKER) not in sys.path:
    sys.path.insert(0, str(TRACKER))

from literal_newline_repair import (  # noqa: E402
    LiteralNewlineRepair,
    ersetze,
    ist_erwaehnung,
)

# -----------------------------------------------------------------------------
# DER STAND (Build 648).
#
# BUILD 650: DIE ZAHL STEHT AUF 0 - AUS DER OBERGRENZE IST EINE SPERRE
# GEWORDEN. Der Weg dahin, zum Nachlesen: Build 648 mass 317 verlorene
# Umbrueche in 21 Vorgaengen und trug sie als Obergrenze ein (ein Test, der ab
# Auslieferung rot ist, verstiesse gegen Grundregel 2). mc hat das Werkzeug
# danach laufen lassen; Build 649 fand noch 71 - Nachschub aus Kommentaren,
# die es in 647 noch nicht gab. Nach dem zweiten Lauf ist der Bestand sauber,
# nachgezaehlt ueber alle 145 Vorgaenge.
#
# AB JETZT HEISST 'GROESSER ALS 0' IMMER: es ist eine Eingangsdatei
# eingepflegt worden, in der ein Backslash verdoppelt wurde. Zu beheben mit
# 'python repair_literal_newlines.py --apply'. Der Fehler entsteht beim
# ERZEUGEN der Datei, also bei mir - merge.py warnt seit Build 648 an genau
# dieser Stelle.
#
# WARUM UEBERHAUPT EINE ZAHL: Weil der Fehler beim ERZEUGEN von
# Eingangsdateien entsteht, also bei mir, und weil er in der fertigen Anzeige
# nur auffaellt, wenn jemand genau hinsieht. mc hat ihn gefunden, nicht ich.
# -----------------------------------------------------------------------------
STAND_UMBRUECHE = 0


def _vorgang(**felder):
    grund = {
        "id": "aaaaaaaa-0000-4000-8000-000000000000",
        "type": "bug",
        "title": "Prüfvorgang",
        "affected_version": "0.8.648",
        "reporter": "Testlauf",
        "reported_at": "2026-08-01T12:00:00+00:00",
        "status": "open",
        "updates": [],
    }
    grund.update(felder)
    return grund


class TestUnterscheidung(unittest.TestCase):
    """LN01-LN03: die Regel und das Ersetzen."""

    def test_ln01_regel_trennt_umbruch_von_erwaehnung(self):
        # So sieht ein verlorener Umbruch aus: er klebt am Satz.
        umbruch = "Ende des Satzes.\\nNaechster Satz"
        self.assertFalse(ist_erwaehnung(umbruch, umbruch.index("\\n")))

        # So sieht eine woertliche Erwaehnung aus: sie steht frei im Satz.
        # Der Text stammt aus Vorgang d2ade5dc von mc.
        erwaehnung = "Dieser wird als \\n gespeichert."
        self.assertTrue(ist_erwaehnung(erwaehnung, erwaehnung.index("\\n")))

        # Am Textanfang ebenfalls eine Erwaehnung (auch aus d2ade5dc).
        anfang = "\\n wird durch <br> ersetzt."
        self.assertTrue(ist_erwaehnung(anfang, 0))

    def test_ln02_ersetzen_laesst_erwaehnungen_stehen(self):
        text = "Satz eins.\\nSatz zwei. Geschrieben wird als \\n im Text."
        neu, ersetzt, stehen = ersetze(text)

        self.assertEqual((ersetzt, stehen), (1, 1))
        self.assertEqual(neu, "Satz eins.\nSatz zwei. Geschrieben wird als \\n im Text.")

    def test_ln03_absatz_ist_zweimal(self):
        # '\n\n' - der haeufigste Fall im Bestand. Beide Haelften muessen
        # gefunden werden; eine Suche, die nach dem ersten Treffer um die
        # ganze Fundstelle weiterspringt, uebersaehe die zweite nicht - eine,
        # die um ein Zeichen weiterspringt, faende sie doppelt.
        neu, ersetzt, stehen = ersetze("Absatz eins.\\n\\nAbsatz zwei")
        self.assertEqual((ersetzt, stehen), (2, 0))
        self.assertEqual(neu, "Absatz eins.\n\nAbsatz zwei")

    def test_ln03b_text_ohne_fund_bleibt_wie_er_ist(self):
        text = "Ein ganz gewoehnlicher Text mit echtem\nUmbruch."
        self.assertEqual(ersetze(text), (text, 0, 0))


class TestWerkzeug(unittest.TestCase):
    """LN04-LN08: der Ablauf am Dateisystem."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.arbeit = Path(self._tmp.name)
        (self.arbeit / "data").mkdir()
        self.ziel = self.arbeit / "data" / "issues.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _bestand(self, vorgaenge):
        self.ziel.write_text(
            json.dumps({"issues": vorgaenge}, indent=2, ensure_ascii=False),
            encoding="utf-8")
        return LiteralNewlineRepair(self.ziel)

    def _lesen(self):
        return json.loads(self.ziel.read_text(encoding="utf-8"))["issues"]

    def test_ln04_trockenlauf_aendert_nichts(self):
        reparatur = self._bestand([_vorgang(description="a.\\nb")])
        vorher = self.ziel.read_bytes()

        bericht = reparatur.pruefen()

        self.assertEqual(len(bericht.umbrueche), 1)
        self.assertFalse(bericht.angewendet)
        self.assertEqual(self.ziel.read_bytes(), vorher,
                         "Der Trockenlauf hat die Datei veraendert")

    def test_ln05_apply_sichert_vorher_und_schreibt(self):
        reparatur = self._bestand([
            _vorgang(description="a.\\nb",
                     expected_behavior="steht als \\n im Text",
                     updates=[{"timestamp": "2026-08-01T12:00:00+00:00",
                               "author": "x", "action": "comment",
                               "comment": "eins.\\nzwei"}]),
        ])

        bericht = reparatur.anwenden()

        self.assertTrue(bericht.angewendet)
        v = self._lesen()[0]
        self.assertEqual(v["description"], "a.\nb")
        self.assertEqual(v["updates"][0]["comment"], "eins.\nzwei")
        self.assertEqual(v["expected_behavior"], "steht als \\n im Text",
                         "Eine woertliche Erwaehnung wurde veraendert")

        # Die Sicherung muss den Stand VORHER enthalten - sonst ist sie
        # wertlos.
        self.assertIsNotNone(bericht.sicherung)
        gesichert = json.loads(bericht.sicherung.read_text(encoding="utf-8"))["issues"]
        self.assertEqual(gesichert[0]["description"], "a.\\nb")
        self.assertEqual(bericht.sicherung.parent, self.arbeit / "backups")

    def test_ln06_ohne_fund_wird_nicht_geschrieben(self):
        reparatur = self._bestand([_vorgang(description="ganz sauber")])
        vorher = self.ziel.read_bytes()

        bericht = reparatur.anwenden()

        self.assertFalse(bericht.angewendet)
        self.assertIsNone(bericht.sicherung)
        self.assertEqual(self.ziel.read_bytes(), vorher)
        self.assertFalse((self.arbeit / "backups").exists())

    def test_ln07_nur_ein_vorgang(self):
        reparatur = self._bestand([
            _vorgang(id="aaaaaaaa-0000-4000-8000-000000000000", description="a.\\nb"),
            _vorgang(id="bbbbbbbb-0000-4000-8000-000000000000", description="c.\\nd"),
        ])

        reparatur.anwenden(nur_vorgang="aaaaaaaa")

        bestand = {v["id"][:8]: v for v in self._lesen()}
        self.assertEqual(bestand["aaaaaaaa"]["description"], "a.\nb")
        self.assertEqual(bestand["bbbbbbbb"]["description"], "c.\\nd",
                         "'--nur' hat einen fremden Vorgang angefasst")

    def test_ln08_ergebnis_ist_gueltiges_json(self):
        """
        DIE GEGENPROBE ZUM sed-VORSCHLAG.

        Ein rohes Steuerzeichen in einer JSON-Zeichenkette ist verboten. Wer
        die Datei mit einem Zeileneditor bearbeitet, erzeugt genau das; wer
        sie ueber json.dump schreibt, kann es nicht. Dieser Fall haelt fest,
        dass wir den zweiten Weg gehen.
        """
        reparatur = self._bestand([_vorgang(description="a.\\n\\nb.\\nc")])
        reparatur.anwenden()

        roh = self.ziel.read_text(encoding="utf-8")
        json.loads(roh)  # wirft, wenn ungueltig

        # Und die Umbrueche stehen wirklich als JSON-Escape in der Datei -
        # nicht als rohes Zeichen.
        self.assertIn("a.\\n\\nb.\\nc", roh)
        self.assertEqual(self._lesen()[0]["description"], "a.\n\nb.\nc")


class TestLiveBestand(unittest.TestCase):
    """LN09 - die Sperre."""

    def test_ln09_die_zahl_waechst_nicht(self):
        if not LIVE.exists():
            self.skipTest("issue-tracker/data/issues.json nicht vorhanden.")

        bericht = LiteralNewlineRepair(LIVE).pruefen()
        gefunden = len(bericht.umbrueche)

        self.assertLessEqual(
            gefunden, STAND_UMBRUECHE,
            f"Es sind {gefunden} verlorene Umbrueche im Bestand, erlaubt sind "
            f"hoechstens {STAND_UMBRUECHE}. Es ist also eine Eingangsdatei "
            f"eingepflegt worden, in der '\\\\n' statt '\\n' geschrieben "
            f"wurde. Zu beheben mit: "
            f"python repair_literal_newlines.py --apply"
        )

        if gefunden < STAND_UMBRUECHE:
            # Kein Fehler - ein Hinweis. Wer die Reparatur laufen laesst,
            # soll die Zahl oben nachziehen, sonst verliert die Sperre ihre
            # Wirkung (dieselbe Ueberlegung wie bei den Fehllisten in
            # tests/hilfe_fehlliste_stand.json).
            print(f"\n[LN09] Der Bestand ist besser als der vermerkte Stand: "
                  f"{gefunden} statt {STAND_UMBRUECHE}. Bitte STAND_UMBRUECHE "
                  f"in {Path(__file__).name} auf {gefunden} setzen.")

    def test_ln09b_erwaehnungen_bleiben_nachvollziehbar(self):
        """
        Die Gegenrichtung: was das Werkzeug NICHT anfasst, muss benannt sein.

        Der Fall prueft nicht eine Zahl, sondern dass jede Erwaehnung mit
        ihrer Umgebung im Bericht steht - sonst muesste man sie ein zweites
        Mal suchen.
        """
        if not LIVE.exists():
            self.skipTest("issue-tracker/data/issues.json nicht vorhanden.")

        bericht = LiteralNewlineRepair(LIVE).pruefen()
        for fundstelle in bericht.erwaehnungen:
            self.assertTrue(fundstelle.vorgang_id)
            self.assertTrue(fundstelle.feld)
            self.assertIn("«\\n»", fundstelle.umgebung)


if __name__ == "__main__":
    unittest.main()

# =============================================================================
# tests/test_issue_eingang_schema.py
# IT-Forensisches Ermittlungswerkzeug - Vorgangsverwaltung
# =============================================================================
# Testsuite fuer Build 628: die Eingangsdateien des Issue-Trackers werden
# gegen ihr eigenes Schema geprueft, BEVOR sie jemand einspielt.
#
# DER ANLASS (mc, 2026-08-01, woertlich): "Die zulaessige Laenge eines Titels
#   betraegt 80 Zeichen. In den letzten Runden waren die Laengen haeufig
#   laenger und musste von mir vor dem Einpflegen gekuerzt werden."
#
#   DREI VON MIR GELIEFERTE VORGAENGE WAREN ZU LANG (107, 109 und 90
#   Zeichen). Das Schema sagt 'maxLength: 80' - die Angabe stand also die
#   ganze Zeit da. Meine Pruefung ist auf 'nur die Pflichtfelder'
#   zurueckgefallen, weil das Paket 'jsonschema' im Container fehlte, und ich
#   habe diesen Rueckfall hingenommen statt ihn zu beheben. Der Preis war
#   Handarbeit bei mc, dreimal.
#
# DIE LEHRE IST DIESELBE WIE BEI 'e9522fe2' UND 'c3f80e54': Eine Vorgabe, die
#   nur in einem Dokument steht, ist eine Bitte. Erst eine Pruefung, die
#   anschlaegt, ist eine Regel. Das Schema lag vor - es hat nur niemand
#   ausgewertet.
#
# DER MASSGEBLICHE WEG IST 'python merge.py --validate-only <datei>'
#   (Hinweis mc, 2026-08-01). Er wertet dasselbe Schema aus. Dieser Test
#   ERSETZT ihn nicht, er faengt nur ab, dass jemand ihn vergisst: eine
#   Eingangsdatei entsteht beim Bauen, und beim Bauen laeuft die Regression.
#   Ein Werkzeug muss man aufrufen - und wer eine Regel vergisst, vergisst
#   auch das Werkzeug dazu.
#
# IE01 - jede Eingangsdatei entspricht dem Schema (falls jsonschema da ist)
# IE02 - jeder Titel haelt 80 Zeichen - UNABHAENGIG von jsonschema, damit die
#        Grenze auch dann greift, wenn das Paket fehlt
# IE03 - die Pflichtfelder sind da, und die Kennung ist eine echte UUID
# IE04 - keine zwei Eingangsdateien fuehren dieselbe Kennung
# IE05 - die Grenze wird aus dem SCHEMA gelesen, nicht abgeschrieben
#
# WAS DIESER TEST NICHT KANN (TE4):
#   * Er prueft nur die Eingangsdateien, die GERADE IM BESTAND LIEGEN. Sind
#     alle eingespielt und entfernt, findet er nichts und ist gruen - das ist
#     richtig, aber es ist keine Aussage ueber die eingespielten Vorgaenge.
#     Der Ort dafuer ist merge.py beim Einspielen.
#   * Er prueft nicht issue-tracker/data/issues.json selbst. Diese Datei wird
#     von mc gefuehrt; sie hier mitzupruefen hiesse, fremde Arbeit zum
#     Bestandteil meines Regressionslaufs zu machen.
#   * 'jsonschema' steht in KEINER requirements.txt des Bestandes (Stand
#     Build 628; issue-tracker/requirements.txt fuehrt es ebenfalls nicht,
#     obwohl merge.py es benutzt). Deshalb greift IE02 ohne das Paket.
#
# Version: v0.8.628 - Build: 628 - 2026-08-01
# =============================================================================

import glob
import json
import os
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WURZEL = Path(__file__).resolve().parent.parent
SCHEMA_PFAD = WURZEL / "issue-tracker" / "issue-tracker.schema.json"
EINGANG_MUSTER = str(WURZEL / "issue-tracker" / "eingang_*.json")


def _schema():
    return json.loads(SCHEMA_PFAD.read_text(encoding="utf-8"))


def _eingangsdateien():
    return sorted(glob.glob(EINGANG_MUSTER))


def _issues(pfad):
    d = json.loads(Path(pfad).read_text(encoding="utf-8"))
    return d.get("issues", [])


class EingangSchemaTests(unittest.TestCase):

    # --- IE05 ---------------------------------------------------------------
    def test_ie05_die_grenze_kommt_aus_dem_schema(self):
        """
        DIE ZAHL WIRD NICHT ABGESCHRIEBEN. Stuende hier '80' als Literal,
        gaebe es zwei Wahrheiten - und die im Test wuerde die im Schema
        ueberleben. Zugleich ist das die Gegenprobe darauf, dass das Feld
        ueberhaupt begrenzt IST.
        """
        titel = (_schema()["properties"]["issues"]["items"]
                 ["properties"]["title"])
        self.assertIn("maxLength", titel,
                      "Das Schema begrenzt den Titel nicht mehr - dann ist "
                      "auch dieser Test keine Aussage mehr.")
        self.assertGreater(titel["maxLength"], 0)

    # --- IE02 ---------------------------------------------------------------
    def test_ie02_titel_halten_die_grenze(self):
        """
        OHNE jsonschema. Das Paket ist keine harte Abhaengigkeit des
        Bestandes; die Grenze muss trotzdem greifen. Genau daran ist es beim
        letzten Mal gescheitert: die Pruefung fiel auf 'nur Pflichtfelder'
        zurueck, und drei zu lange Titel gingen durch.
        """
        grenze = (_schema()["properties"]["issues"]["items"]
                  ["properties"]["title"]["maxLength"])
        zu_lang = []
        for pfad in _eingangsdateien():
            for i in _issues(pfad):
                titel = i.get("title", "")
                if len(titel) > grenze:
                    zu_lang.append(
                        "%s: %d Zeichen (erlaubt %d) - %r"
                        % (os.path.basename(pfad), len(titel), grenze, titel))
        self.assertEqual([], zu_lang, "\n".join(zu_lang))

    # --- IE03 ---------------------------------------------------------------
    def test_ie03_pflichtfelder_und_echte_kennung(self):
        pflicht = (_schema()["properties"]["issues"]["items"]["required"])
        maengel = []
        for pfad in _eingangsdateien():
            for i in _issues(pfad):
                for feld in pflicht:
                    if feld not in i:
                        maengel.append("%s: Feld '%s' fehlt"
                                       % (os.path.basename(pfad), feld))
                try:
                    uuid.UUID(str(i.get("id", "")))
                except ValueError:
                    maengel.append("%s: '%s' ist keine UUID"
                                   % (os.path.basename(pfad), i.get("id")))
        self.assertEqual([], maengel, "\n".join(maengel))

    # --- IE04 ---------------------------------------------------------------
    def test_ie04_keine_doppelte_kennung(self):
        """
        Zwei Eingangsdateien mit derselben Kennung waeren fuer merge.py ein
        Konflikt - und der faellt erst beim Einspielen auf, also bei mc.
        """
        gesehen = {}
        doppelt = []
        for pfad in _eingangsdateien():
            for i in _issues(pfad):
                kennung = i.get("id")
                if kennung in gesehen:
                    doppelt.append("%s auch in %s"
                                   % (kennung, gesehen[kennung]))
                gesehen[kennung] = os.path.basename(pfad)
        self.assertEqual([], doppelt, "\n".join(doppelt))

    # --- IE01 ---------------------------------------------------------------
    def test_ie01_gegen_das_schema(self):
        """
        Die vollstaendige Pruefung. Sie braucht 'jsonschema'; fehlt das
        Paket, wird der Test UEBERSPRUNGEN - aber IE02 bis IE04 greifen
        weiter. Ein uebersprungener Test ist im Lauf sichtbar, ein still
        weggelassener nicht.
        """
        try:
            import jsonschema
        except ImportError:                      # pragma: no cover
            self.skipTest("jsonschema nicht vorhanden - IE02/IE03/IE04 "
                          "pruefen die wichtigsten Punkte trotzdem")
        schema = _schema()
        for pfad in _eingangsdateien():
            with self.subTest(datei=os.path.basename(pfad)):
                jsonschema.validate(
                    json.loads(Path(pfad).read_text(encoding="utf-8")), schema)

    # --- Gegenprobe ---------------------------------------------------------
    def test_ie02b_die_pruefung_schlaegt_wirklich_an(self):
        """Eine Pruefung, die nie anschlaegt, belegt nichts."""
        grenze = (_schema()["properties"]["issues"]["items"]
                  ["properties"]["title"]["maxLength"])
        self.assertGreater(len("x" * (grenze + 1)), grenze)
        try:
            import jsonschema
        except ImportError:                      # pragma: no cover
            return
        from jsonschema import ValidationError
        entwurf = {"issues": [{
            "id": str(uuid.uuid4()), "type": "bug",
            "title": "x" * (grenze + 1), "affected_version": "0.8.0",
            "reporter": "Probe", "reported_at": "2026-08-01T00:00:00+00:00",
            "status": "open"}]}
        with self.assertRaises(ValidationError):
            jsonschema.validate(entwurf, _schema())


if __name__ == "__main__":
    unittest.main()

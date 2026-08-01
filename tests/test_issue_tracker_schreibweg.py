# =============================================================================
# tests/test_issue_tracker_schreibweg.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# Testsuite fuer Build 642: der SCHREIBWEG zur issues.json und die TRENNUNG
# der Sicherungen.
#
# WORUM ES GEHT. Bis Build 641 gab es zwei Wege, auf denen die einzige Datei
# mit dem gesamten Vorgangsbestand geschrieben wurde - server.py und merge.py -
# und beide taten es unmittelbar:
#
#     with open(pfad, "w", encoding="utf-8") as f:
#         json.dump(...)
#
# 'open(..., "w")' kuerzt die Datei auf null Byte, BEVOR der erste Vorgang
# geschrieben ist. Faellt in diesem Fenster etwas aus, ist der Bestand weg.
# Ab Build 642 wird in eine Nachbardatei geschrieben und atomar umgehaengt.
#
# ZWEITER BEFUND: server.py raeumte alte Sicherungen per Glob
# 'issues_backup_*.json' ab - und dieses Muster passt auch auf
# 'issues_backup_before_merge_*.json', also auf die Sicherungen des
# Merge-Werkzeugs. Der Server durfte fremde Sicherungen loeschen.
#
# WARUM DIE PRUEFUNG DES SERVERS AM QUELLTEXT HAENGT: server.py laesst sich in
# der Testumgebung nicht importieren, weil es 'fastapi' voraussetzt und das
# Paket keine Abhaengigkeit der Regression ist (dieselbe Lage wie bei
# 'jsonschema', vgl. tests/test_issue_tracker_schema.py). Die MECHANIK liegt
# deshalb ab Build 642 in zwei importierbaren Dateien - json_safe_writer.py
# und backup_names.py -, die hier unmittelbar geprueft werden. Fuer server.py
# selbst bleibt die Frage 'benutzt er sie auch?', und die wird am Quelltext
# beantwortet. Das ist eine schwaechere Aussage als ein Lauf, aber es ist eine
# ueberpruefbare - und sie schlaegt an, wenn jemand den alten Weg wieder
# einbaut.
#
# SW01 - JsonSafeWriter schreibt den erwarteten Inhalt, UTF-8, unveraendertes
#        Format (indent=2, keine ASCII-Maskierung).
# SW02 - waehrend des Schreibens gibt es keinen Zwischenstand: nach einem
#        Fehler in der Serialisierung ist die alte Datei UNVERAENDERT.
# SW03 - es bleibt keine temporaere Datei liegen (weder im Erfolgs- noch im
#        Fehlerfall).
# SW04 - der Schreibweg legt fehlende Verzeichnisse an.
# SW05 - eigene_sicherungen trennt Server-, Merge- und Reparatur-Sicherungen
#        und laesst Fremdes unangetastet.
# SW06 - GEGENPROBE AM QUELLTEXT: IssueManager.save benutzt den sicheren
#        Schreibweg und kein 'open(..., "w")'.
# SW07 - GEGENPROBE AM QUELLTEXT: _create_backup waehlt die zu loeschenden
#        Sicherungen nicht mehr per Glob aus.
# SW08 - GEGENPROBE AM QUELLTEXT: merge.py save_file benutzt den sicheren
#        Schreibweg.
#
# Version: v0.8.642 - Build: 642 - 2026-08-01
# =============================================================================

import ast
import json

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
TRACKER = WURZEL / "issue-tracker"

# Die Bausteine des Trackers liegen nicht im Python-Pfad des Projekts; sie
# gehoeren zu einem eigenstaendigen Werkzeug. Fuer die Pruefung wird ihr
# Verzeichnis ergaenzt.
if str(TRACKER) not in sys.path:
    sys.path.insert(0, str(TRACKER))

from backup_names import (  # noqa: E402
    MERGE_MUSTER,
    REPARATUR_MUSTER,
    SERVER_MUSTER,
    eigene_sicherungen,
    ist_merge_sicherung,
    ist_server_sicherung,
    merge_sicherungsname,
    reparatur_sicherungsname,
    server_sicherungsname,
)
from json_safe_writer import JsonSafeWriter  # noqa: E402


class NichtSerialisierbar:
    """Ein Objekt, an dem json.dump zuverlaessig scheitert."""


def _methode(datei: Path, klasse: str, methode: str) -> ast.FunctionDef:
    """
    Liefert den Syntaxbaum EINER Methode.

    WARUM UEBER DEN SYNTAXBAUM UND NICHT PER TEXTSUCHE - und das ist hier
    keine Stilfrage, sondern ein Befund aus dem ersten Lauf dieser Suite:
    Die Methoden tragen ab Build 642 einen Kommentar, der den alten,
    gefaehrlichen Aufruf WOERTLICH zitiert ("bis Build 641 stand hier
    open(..., 'w')"). Eine Textsuche findet dieses Zitat und meldet einen
    Fehler, den es nicht gibt. Ein Test, der die Dokumentation seines
    eigenen Gegenstands nicht von dessen Code unterscheiden kann, ist
    unbrauchbar - er zwingt dazu, Erklaerungen wegzulassen.

    Der Syntaxbaum kennt den Unterschied: Kommentare stehen dort nicht, und
    ein Docstring ist eine Zeichenkette und kein Aufruf.
    """
    quelle = datei.read_text(encoding="utf-8")
    baum = ast.parse(quelle)
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.ClassDef) and knoten.name == klasse:
            for unterknoten in knoten.body:
                if isinstance(unterknoten, ast.FunctionDef) and unterknoten.name == methode:
                    return unterknoten
    raise AssertionError(f"{klasse}.{methode} nicht gefunden in {datei}")


def _oeffnet_zum_schreiben(knoten: ast.FunctionDef) -> bool:
    """Wahr, wenn in der Methode 'open(..., "w"...)' TATSAECHLICH aufgerufen wird."""
    for unterknoten in ast.walk(knoten):
        if not isinstance(unterknoten, ast.Call):
            continue
        if not (isinstance(unterknoten.func, ast.Name) and unterknoten.func.id == "open"):
            continue
        argumente = list(unterknoten.args) + [kw.value for kw in unterknoten.keywords]
        for argument in argumente:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                if argument.value.startswith(("w", "a", "x")):
                    return True
    return False


def _ruft_auf(knoten: ast.FunctionDef, name: str) -> bool:
    """Wahr, wenn in der Methode eine Funktion/Methode dieses Namens aufgerufen wird."""
    for unterknoten in ast.walk(knoten):
        if not isinstance(unterknoten, ast.Call):
            continue
        ziel = unterknoten.func
        if isinstance(ziel, ast.Attribute) and ziel.attr == name:
            return True
        if isinstance(ziel, ast.Name) and ziel.id == name:
            return True
    return False


class TestJsonSafeWriter(unittest.TestCase):
    """SW01-SW04: der Schreibweg selbst."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.ziel = self.dir / "issues.json"
        self.writer = JsonSafeWriter()

    def tearDown(self):
        self._tmp.cleanup()

    def test_sw01_schreibt_inhalt_und_format(self):
        # Ein mehrsprachiger Text - das Forum ist multilingual, und die
        # Zusicherung 'ensure_ascii=False' ist deshalb keine Kosmetik.
        nutzlast = {"issues": [{"id": "x", "title": "Prüfung – Ärger, 日本語, кириллица"}]}
        self.writer.write(self.ziel, nutzlast)

        roh = self.ziel.read_text(encoding="utf-8")
        self.assertEqual(json.loads(roh), nutzlast)
        self.assertIn("日本語", roh, "Unicode wurde maskiert statt geschrieben")
        self.assertIn('\n  "issues"', roh, "Einrueckung 2 wurde nicht beibehalten")
        self.assertTrue(roh.endswith("\n"), "Abschliessender Zeilenumbruch fehlt")

    def test_sw02_alte_fassung_bleibt_bei_fehler_erhalten(self):
        alt = {"issues": [{"id": "alt", "title": "darf nicht verlorengehen"}]}
        self.writer.write(self.ziel, alt)
        vorher = self.ziel.read_bytes()

        with self.assertRaises(TypeError):
            self.writer.write(self.ziel, {"issues": [NichtSerialisierbar()]})

        self.assertEqual(
            self.ziel.read_bytes(), vorher,
            "Die Zieldatei wurde durch einen gescheiterten Schreibvorgang veraendert"
        )

    def test_sw03_keine_temporaere_datei_bleibt_liegen(self):
        self.writer.write(self.ziel, {"issues": []})
        with self.assertRaises(TypeError):
            self.writer.write(self.ziel, {"issues": [NichtSerialisierbar()]})

        reste = [p.name for p in self.dir.iterdir()
                 if p.name.startswith(JsonSafeWriter.TEMP_PREFIX)]
        self.assertEqual(reste, [], f"Temporaere Reste liegengeblieben: {reste}")

    def test_sw04_legt_fehlendes_verzeichnis_an(self):
        tief = self.dir / "a" / "b" / "issues.json"
        self.writer.write(tief, {"issues": []})
        self.assertTrue(tief.exists())


class TestSicherungsnamen(unittest.TestCase):
    """SW05: wem gehoert welche Sicherung."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        zeit = datetime(2026, 8, 1, 18, 35, 48)
        self.server = server_sicherungsname(zeit)
        self.merge = merge_sicherungsname(zeit)
        self.reparatur = reparatur_sicherungsname(zeit)

    def tearDown(self):
        self._tmp.cleanup()

    def test_sw05a_muster_trennen_sauber(self):
        self.assertTrue(ist_server_sicherung(self.server))
        self.assertFalse(ist_server_sicherung(self.merge),
                         "Das Server-Muster passt auf eine Merge-Sicherung - "
                         "genau der Fehler aus Build 641")
        self.assertFalse(ist_server_sicherung(self.reparatur))
        self.assertTrue(ist_merge_sicherung(self.merge))
        self.assertFalse(ist_merge_sicherung(self.server))

    def test_sw05b_auswahl_greift_nur_die_eigenen(self):
        namen = [self.server, self.merge, self.reparatur,
                 "issues_backup_20260731_101010.json",
                 "issues_backup_before_merge_20260731_101010.json",
                 "issues_backup_20260729_164658.json",
                 "handnotiz.json",
                 "issues_backup_von_hand.json"]
        for name in namen:
            (self.dir / name).write_text("{}", encoding="utf-8")

        server = [p.name for p in eigene_sicherungen(self.dir, SERVER_MUSTER)]
        merge = [p.name for p in eigene_sicherungen(self.dir, MERGE_MUSTER)]
        reparatur = [p.name for p in eigene_sicherungen(self.dir, REPARATUR_MUSTER)]

        self.assertEqual(len(server), 3)
        self.assertEqual(len(merge), 2)
        self.assertEqual(len(reparatur), 1)

        # Die eigentliche Zusicherung: keine Ueberschneidung, und was zu
        # keinem Muster passt, taucht in keiner Liste auf.
        alle = server + merge + reparatur
        self.assertEqual(len(alle), len(set(alle)))
        self.assertNotIn("handnotiz.json", alle)
        self.assertNotIn("issues_backup_von_hand.json", alle)

    def test_sw05c_reihenfolge_ist_zeitlich(self):
        for tag in (3, 1, 2):
            name = server_sicherungsname(datetime(2026, 8, tag, 12, 0, 0))
            (self.dir / name).write_text("{}", encoding="utf-8")
        namen = [p.name for p in eigene_sicherungen(self.dir, SERVER_MUSTER)]
        self.assertEqual(namen, sorted(namen))
        self.assertIn("20260801", namen[0], "Aelteste Sicherung steht nicht vorne")


class TestQuelltextSperren(unittest.TestCase):
    """
    SW06-SW08: die Gegenproben am Quelltext.

    Sie sagen nichts ueber die Laufzeit aus - sie halten nur fest, dass die
    beiden Werkzeuge den sicheren Weg auch benutzen. Wer den alten Weg wieder
    einbaut, laeuft hier auf.
    """

    def test_sw06_server_speichert_ueber_den_sicheren_weg(self):
        knoten = _methode(TRACKER / "server.py", "IssueManager", "save")
        self.assertTrue(_ruft_auf(knoten, "write"),
                        "IssueManager.save benutzt den sicheren Schreibweg nicht")
        self.assertFalse(_oeffnet_zum_schreiben(knoten),
                         "IssueManager.save kuerzt die Zieldatei wieder unmittelbar")

    def test_sw07_server_bereinigt_nicht_mehr_per_glob(self):
        knoten = _methode(TRACKER / "server.py", "IssueManager", "_create_backup")
        self.assertTrue(_ruft_auf(knoten, "eigene_sicherungen"),
                        "_create_backup waehlt nicht nach eigenem Muster aus")
        self.assertFalse(_ruft_auf(knoten, "glob"),
                         "_create_backup waehlt wieder per Glob aus - das trifft "
                         "auch die Sicherungen von merge.py")

    def test_sw08_merge_speichert_ueber_den_sicheren_weg(self):
        knoten = _methode(TRACKER / "merge.py", "IssueMergeEngine", "save_file")
        self.assertTrue(_ruft_auf(knoten, "write"),
                        "merge.py save_file benutzt den sicheren Schreibweg nicht")
        self.assertFalse(_oeffnet_zum_schreiben(knoten),
                         "merge.py save_file kuerzt die Zieldatei wieder unmittelbar")


if __name__ == "__main__":
    unittest.main()

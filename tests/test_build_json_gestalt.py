# =============================================================================
# tests/test_build_json_gestalt.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite fuer Build 645: die GESTALT der build.json.
#
# DER ANLASS - zweimal am selben Tag, in zwei Ausfertigungen:
#
#   e839be3 (Version 0.8.644a):  "build": 644a,
#       -> UNGUELTIGES JSON. json.loads bricht ab ("Expecting ',' delimiter").
#
#   24b4772 (Version 0.8.644b):  "build": "644a",
#       -> gueltiges JSON, aber eine ZEICHENKETTE.
#
# BEIDE MALE DIESELBE FOLGE. core/build_info.py Z. 84 macht
# 'int(data.get("build", 0))' innerhalb eines 'try'; jeder Fehler landet im
# 'except Exception' und setzt Build 0, Version 0.0.0, Datum 'unbekannt'.
# Gemessen im Klon:
#
#   ERROR build.json konnte nicht gelesen werden:
#         invalid literal for int() with base 10: '644a'
#   BuildInfo liest: 0  0.0.0
#
# WARUM DAS SCHWERER WIEGT, ALS ES AUSSIEHT: Der Server startet trotzdem. Er
# meldet sich nur als Build 0. Dieselbe Zahl steht dann im Erzeugungsvermerk
# jedes Berichts (management/export/*: 'Fallback 0'), im Cache-Buster der
# Auslieferung (server/shell_handler.py) und in der Statusauskunft
# (forensic_api/status.py). Das ist genau der Zustand aus Vorgang ff7e80ab,
# 'Berichte entstehen still mit Ersatz-Erzeugungsvermerk (Build 0, unbekannt)'
# - nur diesmal nicht als Randfall, sondern fuer JEDEN Bericht.
#
# DIE LEHRE IST DIESELBE WIE BEI 'e9522fe2' UND BEI DER TITELLAENGE IN BUILD
# 628: Eine Vorgabe, die nur in einer Datei steht, ist eine Bitte. Erst eine
# Pruefung, die anschlaegt, ist eine Regel. Die Konvention gab es seit jeher -
# 326fc50 (Version 0.8.637a) fuehrt "build": 637 und den Zwischenstand NUR in
# 'version'. Sie stand nur nirgends geschrieben und wurde von nichts geprueft.
#
# BJ01 - build.json ist gueltiges JSON.
# BJ02 - 'build' ist eine GANZE ZAHL (kein Text, kein Komma-Wert).
# BJ03 - 'version' passt zum Versionsmuster des Projekts, Zwischenstaende
#        ('0.8.645a') ausdruecklich eingeschlossen.
# BJ04 - 'build' und 'version' passen zueinander: die Zahl in 'build' ist die
#        letzte Zahlengruppe von 'version'.
# BJ05 - GEGENPROBE AM LEBENDEN OBJEKT: core.build_info.BuildInfo liest die
#        Datei ohne Rueckfall auf Build 0.
#
# Version: v0.8.645 - Build: 645 - 2026-08-01
# =============================================================================

import json
import re
import sys
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
BUILD_JSON = WURZEL / "build.json"

#: Dasselbe Muster wie in issue-tracker/issue-tracker.schema.json und in
#: merge.py: drei Zahlengruppen, wahlweise ein Buchstabe fuer den
#: Zwischenstand.
VERSIONS_MUSTER = re.compile(r"^\d+\.\d+\.\d+[a-z]?$")


class TestBuildJsonGestalt(unittest.TestCase):

    def setUp(self):
        self.assertTrue(BUILD_JSON.is_file(), f"{BUILD_JSON} fehlt")
        self.roh = BUILD_JSON.read_text(encoding="utf-8")

    def test_bj01_ist_gueltiges_json(self):
        try:
            self.daten = json.loads(self.roh)
        except json.JSONDecodeError as fehler:
            self.fail(
                f"build.json ist kein gueltiges JSON: {fehler}. "
                f"Alles, was die Datei liest, faellt damit auf Build 0 / "
                f"v0.0.0 zurueck - der Server startet, meldet sich aber als "
                f"Build 0, und jeder Bericht traegt diese Zahl."
            )

    def test_bj02_build_ist_eine_ganze_zahl(self):
        daten = json.loads(self.roh)
        self.assertIn("build", daten, "build.json fuehrt kein Feld 'build'")
        wert = daten["build"]
        self.assertIsInstance(
            wert, int,
            f"'build' ist {type(wert).__name__} mit dem Wert {wert!r}, "
            f"erwartet wird eine ganze Zahl. core/build_info.py macht "
            f"int(...) und faellt sonst auf Build 0 zurueck. Ein "
            f"Zwischenstand gehoert NUR in 'version' (so wie 0.8.637a in "
            f"Commit 326fc50: \"build\": 637, \"version\": \"0.8.637\")."
        )
        # bool ist in Python ein int - hier waere es trotzdem Unsinn.
        self.assertNotIsInstance(wert, bool)
        self.assertGreater(wert, 0)

    def test_bj03_version_haelt_das_muster(self):
        daten = json.loads(self.roh)
        version = daten.get("version")
        self.assertIsInstance(version, str, "'version' ist keine Zeichenkette")
        self.assertRegex(
            version, VERSIONS_MUSTER,
            f"'version' = {version!r} passt nicht auf das Versionsmuster des "
            f"Projekts (z.B. '0.8.645' oder '0.8.645a')."
        )

    def test_bj04_build_und_version_passen_zueinander(self):
        daten = json.loads(self.roh)
        version = str(daten.get("version", ""))
        treffer = re.match(r"^\d+\.\d+\.(\d+)[a-z]?$", version)
        if not treffer:
            self.skipTest("Version haelt das Muster nicht - siehe BJ03.")
        self.assertEqual(
            int(treffer.group(1)), int(daten["build"]),
            f"'build' ({daten['build']}) und 'version' ({version}) sagen "
            f"Verschiedenes. Beide werden gelesen und an verschiedenen Stellen "
            f"angezeigt; welche gilt, waere danach eine Ratefrage."
        )

    def test_bj05_build_info_liest_ohne_rueckfall(self):
        """
        GEGENPROBE AM LEBENDEN OBJEKT.

        BJ01-BJ04 pruefen die Datei. Dieser Fall prueft den LESER - denn er
        ist es, der still auf 0 zurueckfaellt. Waere die Zusicherung nur an
        der Datei festgemacht, wuerde eine Aenderung am Leser sie aushebeln,
        ohne dass etwas anschlaegt.
        """
        if str(WURZEL) not in sys.path:
            sys.path.insert(0, str(WURZEL))
        try:
            from core.build_info import BuildInfo
        except Exception as fehler:  # pragma: no cover - Umgebungssache
            self.skipTest(f"core.build_info nicht ladbar: {fehler}")

        info = BuildInfo(WURZEL).as_dict()
        self.assertNotEqual(
            info["build"], 0,
            "BuildInfo faellt auf Build 0 zurueck - die Datei ist fuer den "
            "Leser unbrauchbar, auch wenn sie fuer das Auge in Ordnung aussieht."
        )
        self.assertNotEqual(info["version"], "0.0.0")
        self.assertEqual(info["build"], json.loads(self.roh)["build"])


if __name__ == "__main__":
    unittest.main()

# =============================================================================
# tests/test_issue_tracker_schema.py
# IT-Forensisches Ermittlungswerkzeug — Issue-Tracker
# =============================================================================
# Testsuite fuer Build 566: das Schema des Issue-Trackers.
#
# WARUM OHNE 'jsonschema': das Paket ist KEINE Projektabhaengigkeit
# (issue-tracker/requirements.txt fuehrt es nicht, und im uebrigen Baum wird es
# nirgends importiert). Ein Test, der es voraussetzt, waere in der VM rot -
# und ein roter Test, der nichts ueber den Pruefling aussagt, ist schlimmer als
# keiner. Geprueft werden deshalb genau die Zusicherungen, um die es geht:
# die Versionsmuster und die Typen der drei Versionsfelder.
#
# IT01 — das Schema ist ladbar und fuehrt die drei Versionsfelder.
# IT02 — das Muster akzeptiert 0.8.560 UND 0.8.560a (Zwischenstaende) und
#        weist Unsinn ab.
# IT03 — die beiden OPTIONALEN Versionsfelder duerfen null sein, das
#        Pflichtfeld affected_version nicht.
# IT04 — die mitgelieferte Beispieldatei haelt das eigene Schema ein.
#        (Vor Build 566 tat sie das NICHT: sie fuehrt resolved_in_version=null,
#        das Schema verlangte aber 'string'.)
# IT05 — der Live-Bestand haelt die Versionsregeln ein, soweit vorhanden.
#
# Version: v0.8.566 · Build: 566 · 2026-07-29
# =============================================================================

import json
import re
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCHEMA = _ROOT / "issue-tracker" / "issue-tracker.schema.json"
_EXAMPLE = _ROOT / "issue-tracker" / "issue-tracker.example.json"
_DATA = _ROOT / "issue-tracker" / "data" / "issues.json"

_VERSION_FIELDS = ("affected_version", "resolved_in_version", "target_version")
_OPTIONAL = ("resolved_in_version", "target_version")


def _props():
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    return schema["properties"]["issues"]["items"]["properties"]


def _typen(spec):
    """Schema-'type' immer als Menge, egal ob String oder Liste."""
    t = spec.get("type")
    return set(t) if isinstance(t, list) else {t}


class IssueTrackerSchemaTests(unittest.TestCase):

    # IT01 ---------------------------------------------------------------
    def test_it01_schema_ladbar_und_vollstaendig(self):
        p = _props()
        for feld in _VERSION_FIELDS:
            self.assertIn(feld, p, "Versionsfeld %s fehlt im Schema." % feld)
            self.assertIn("pattern", p[feld],
                          "%s hat kein Muster." % feld)

    # IT02 ---------------------------------------------------------------
    def test_it02_muster_erlaubt_zwischenstaende(self):
        """
        Anlass: Commit a92a6f8 traegt '0.8.560a'. Das alte Muster
        ^\\d+\\.\\d+\\.\\d+$ liess solche Zwischenstaende nicht zu - man haette
        auf '0.8.560' runden und den Unterschied im Fliesstext nachtragen
        muessen, also genau die Ungenauigkeit erzeugt, die ein Tracker
        vermeiden soll.
        """
        p = _props()
        for feld in _VERSION_FIELDS:
            rx = re.compile(p[feld]["pattern"])
            for gut in ("0.8.560", "0.8.560a", "1.2.0", "10.20.30z"):
                self.assertTrue(rx.match(gut),
                                "%s: %r sollte zulaessig sein." % (feld, gut))
            # Die Grenze bleibt eng: EIN Kleinbuchstabe, nicht beliebiger Text.
            for schlecht in ("0.8", "0.8.560ab", "", "0.8.560A", "v0.8.560",
                             "0.8.560-rc1"):
                self.assertIsNone(rx.match(schlecht),
                                  "%s: %r haette abgelehnt werden muessen."
                                  % (feld, schlecht))

    # IT03 ---------------------------------------------------------------
    def test_it03_optionale_versionsfelder_duerfen_null_sein(self):
        """
        Der Tracker selbst schreibt fuer nicht gesetzte Versionen 'null'
        (server.py) - das Schema muss das abbilden, sonst beschreibt es nicht
        die Wirklichkeit. Das PFLICHTfeld affected_version bleibt string.
        """
        p = _props()
        for feld in _OPTIONAL:
            self.assertIn("null", _typen(p[feld]),
                          "%s muss null zulassen." % feld)
        self.assertEqual(_typen(p["affected_version"]), {"string"})

    # IT04 ---------------------------------------------------------------
    def test_it04_beispieldatei_haelt_das_eigene_schema_ein(self):
        """Eine mitgelieferte Beispieldatei, die das eigene Schema verletzt,
        ist eine Anleitung zum Fehler."""
        self._pruefe_datei(_EXAMPLE)

    # IT05 ---------------------------------------------------------------
    def test_it05_live_bestand_haelt_die_versionsregeln_ein(self):
        if not _DATA.exists():
            self.skipTest("issue-tracker/data/issues.json nicht vorhanden.")
        self._pruefe_datei(_DATA)

    # --------------------------------------------------------------------
    def _pruefe_datei(self, pfad: Path):
        p = _props()
        doc = json.loads(pfad.read_text(encoding="utf-8"))
        self.assertIn("issues", doc)
        for eintrag in doc["issues"]:
            kennung = eintrag.get("id", "?")
            for feld in _VERSION_FIELDS:
                if feld not in eintrag:
                    continue
                wert = eintrag[feld]
                if wert is None:
                    self.assertIn("null", _typen(p[feld]),
                                  "%s: %s ist null, das Schema verbietet es."
                                  % (kennung, feld))
                    continue
                self.assertIsInstance(wert, str,
                                      "%s: %s ist kein Text." % (kennung, feld))
                self.assertTrue(re.match(p[feld]["pattern"], wert),
                                "%s: %s=%r verletzt das Muster."
                                % (kennung, feld, wert))


if __name__ == "__main__":
    unittest.main()

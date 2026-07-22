# =============================================================================
# tests/test_typed_validation.py
# IT-Forensisches Ermittlungswerkzeug — core/typed_validation.py (Build 498)
# =============================================================================
# Testsuite fuer die SERVERSEITIGE typisierte Validierung. Muss DECKUNGSGLEICH
# zu userinfo/validation_rules.js::checkTyped (vitest T01-T16) sein.
#
# CT01 — leere Pruefart / leere Regel -> ok
# CT02 — regex Treffer / kein Treffer (SUCHE wie JS RegExp.test)
# CT03 — regex fehlerhaft -> nicht ok
# CT04 — list Mitgliedschaft exakt; kein JSON-Array -> nicht ok
# CT05 — like % / _ / Full-Match / Metazeichen literal
# CT06 — unbekannte Pruefart -> nicht ok
# CT07 — ci: regex/list/like ignorieren Gross-/Kleinschreibung
# CT08 — like_to_regex verankert + ci-Flag
#
# Version: v0.8.498 · Build: 498 · 2026-07-22
# =============================================================================

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.typed_validation import check_typed, like_to_regex


class TypedValidationTests(unittest.TestCase):

    def test_CT01_leer_ok(self):
        self.assertEqual(check_typed("", "", "x"), (True, ""))
        self.assertEqual(check_typed("regex", "   ", "x"), (True, ""))
        self.assertEqual(check_typed(None, None, "x"), (True, ""))

    def test_CT02_regex(self):
        self.assertTrue(check_typed("regex", "^AIW[0-9]+$", "AIW123")[0])
        self.assertFalse(check_typed("regex", "^AIW[0-9]+$", "XY")[0])
        # SUCHE (nicht verankert), wenn die Regel keine Anker setzt.
        self.assertTrue(check_typed("regex", "AIW", "xxAIWxx")[0])

    def test_CT03_regex_fehlerhaft(self):
        ok, msg = check_typed("regex", "([", "x")
        self.assertFalse(ok)
        self.assertIn("fehlerhaft", msg)

    def test_CT04_list(self):
        rule = '["rot","gruen","blau"]'
        self.assertTrue(check_typed("list", rule, "gruen")[0])
        self.assertFalse(check_typed("list", rule, "gelb")[0])
        self.assertFalse(check_typed("list", rule, "ro")[0])   # kein Teiltreffer
        self.assertFalse(check_typed("list", "rot,gruen", "rot")[0])  # kein JSON

    def test_CT05_like(self):
        self.assertTrue(check_typed("like", "AIW%", "AIW-2024-1")[0])
        self.assertTrue(check_typed("like", "AIW%", "AIW")[0])       # % = 0
        self.assertFalse(check_typed("like", "AIW%", "XAIW")[0])
        self.assertTrue(check_typed("like", "A_C", "ABC")[0])
        self.assertFalse(check_typed("like", "A_C", "AC")[0])        # _ fehlt
        self.assertFalse(check_typed("like", "ABC", "ABCD")[0])      # Full-Match
        self.assertTrue(check_typed("like", "a.b", "a.b")[0])        # . literal
        self.assertFalse(check_typed("like", "a.b", "axb")[0])

    def test_CT06_unbekannt(self):
        ok, msg = check_typed("zauber", "x", "x")
        self.assertFalse(ok)
        self.assertIn("Unbekannte", msg)

    def test_CT07_case_insensitive(self):
        self.assertTrue(check_typed("regex", "^abc$", "ABC", ci=True)[0])
        self.assertFalse(check_typed("regex", "^abc$", "ABC", ci=False)[0])
        self.assertTrue(check_typed("list", '["Rot","Gruen"]', "rot", ci=True)[0])
        self.assertFalse(check_typed("list", '["Rot","Gruen"]', "rot", ci=False)[0])
        self.assertTrue(check_typed("like", "AIW%", "aiw-1", ci=True)[0])
        self.assertFalse(check_typed("like", "AIW%", "aiw-1", ci=False)[0])

    def test_CT08_like_to_regex(self):
        rx = like_to_regex("a%b_c")
        self.assertTrue(rx.pattern.startswith("^"))
        self.assertTrue(rx.pattern.endswith("$"))
        self.assertIsNotNone(rx.search("aXXXbYc"))
        self.assertIsNone(rx.search("aXXXbc"))    # _ fehlt
        self.assertIsNotNone(like_to_regex("abc", ci=True).search("ABC"))
        self.assertIsNone(like_to_regex("abc", ci=False).search("ABC"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

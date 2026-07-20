# =============================================================================
# tests/test_checklist_status.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Onboarding/Offboarding (AP-2G)
# =============================================================================
# Testsuite fuer Build 464: ChecklistStatus (Kataloge + Zustandslogik).
#
# CS01 — Arten + Kataloge (je 5 Schritte, geordnet).
# CS02 — Schritt-Validierung: unbekannter Schritt/Art -> Fehler.
# CS03 — Zustaende: 'offen' implizit (nicht gespeichert); STORED = erledigt/
#        nicht_zutreffend.
# CS04 — Grund-Pflicht: 'nicht_zutreffend' ohne Notiz -> Fehler; sonst ok.
#
# Reine Logik, kein I/O.
# Version: v0.7.464 · Build: 464 · 2026-07-20
# =============================================================================

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.onboarding.checklist_status import (
    ChecklistStatus,
    ChecklistStatusError,
    KINDS,
    STORED_STATUSES,
)


class ChecklistStatusTests(unittest.TestCase):

    # CS01 -------------------------------------------------------------------
    def test_cs01_kinds_and_catalogs(self):
        self.assertEqual(set(KINDS), {"onboarding", "offboarding"})
        self.assertEqual(len(ChecklistStatus.steps("onboarding")), 5)
        self.assertEqual(len(ChecklistStatus.steps("offboarding")), 5)
        # Reihenfolge stabil, erster Onboarding-Schritt.
        self.assertEqual(ChecklistStatus.step_codes("onboarding")[0],
                         "person_angelegt")
        self.assertIn("faelle_umverteilt",
                      ChecklistStatus.step_codes("offboarding"))
        self.assertIn("Personendatensatz",
                      ChecklistStatus.step_label("onboarding", "person_angelegt"))

    # CS02 -------------------------------------------------------------------
    def test_cs02_step_validation(self):
        self.assertTrue(
            ChecklistStatus.is_valid_step("onboarding", "einweisung"))
        self.assertFalse(
            ChecklistStatus.is_valid_step("onboarding", "quatsch"))
        # Offboarding-Schritt gilt NICHT als Onboarding-Schritt.
        self.assertFalse(
            ChecklistStatus.is_valid_step("onboarding", "zugang_gesperrt"))
        with self.assertRaises(ChecklistStatusError):
            ChecklistStatus.require_step("onboarding", "quatsch")
        with self.assertRaises(ChecklistStatusError):
            ChecklistStatus.require_kind("egal")

    # CS03 -------------------------------------------------------------------
    def test_cs03_states(self):
        self.assertEqual(set(STORED_STATUSES),
                         {"erledigt", "nicht_zutreffend"})
        self.assertFalse(ChecklistStatus.is_stored("offen"))
        self.assertTrue(ChecklistStatus.is_stored("erledigt"))
        self.assertTrue(ChecklistStatus.is_known("offen"))
        self.assertFalse(ChecklistStatus.is_known("quatsch"))
        ChecklistStatus.require_status("offen")   # kein Fehler (Reset)
        with self.assertRaises(ChecklistStatusError):
            ChecklistStatus.require_status("quatsch")

    # CS04 -------------------------------------------------------------------
    def test_cs04_reason_required(self):
        self.assertTrue(ChecklistStatus.requires_reason("nicht_zutreffend"))
        self.assertFalse(ChecklistStatus.requires_reason("erledigt"))
        with self.assertRaises(ChecklistStatusError):
            ChecklistStatus.check_reason("nicht_zutreffend", "  ")
        ChecklistStatus.check_reason("nicht_zutreffend", "entfaellt, extern")
        ChecklistStatus.check_reason("erledigt", "")   # kein Grund noetig


if __name__ == "__main__":
    unittest.main()

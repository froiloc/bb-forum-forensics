# =============================================================================
# tests/test_release_status.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Externe Fallfreigabe (AP-2G)
# =============================================================================
# Testsuite fuer Build 462: ReleaseStatus (Zustandsmaschine) + Umfang-Vokabular.
#
# RS01 — Zustaende/Endzustand korrekt.
# RS02 — freigegeben -> widerrufen erlaubt; widerrufen ist ENDGUELTIG.
# RS03 — unbekannter Ziel-/Quellzustand -> Fehler.
# RS04 — Umfang-Vokabular: gueltig/ungueltig, Label, Katalog.
#
# Reine Logik, kein I/O.
# Version: v0.7.462 · Build: 462 · 2026-07-20
# =============================================================================

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.external.release_status import (
    ReleaseStatus,
    ReleaseStatusError,
    UMFANG_ORDER,
    umfang_catalog,
    umfang_is_valid,
    umfang_label,
)


class ReleaseStatusTests(unittest.TestCase):

    # RS01 -------------------------------------------------------------------
    def test_rs01_states(self):
        self.assertTrue(ReleaseStatus.is_valid("freigegeben"))
        self.assertTrue(ReleaseStatus.is_valid("widerrufen"))
        self.assertFalse(ReleaseStatus.is_valid("quatsch"))
        self.assertTrue(ReleaseStatus.is_final("widerrufen"))
        self.assertFalse(ReleaseStatus.is_final("freigegeben"))

    # RS02 -------------------------------------------------------------------
    def test_rs02_transition_and_finality(self):
        ReleaseStatus.check_transition("freigegeben", "widerrufen")  # ok
        self.assertEqual(ReleaseStatus.allowed_next("widerrufen"), ())
        with self.assertRaises(ReleaseStatusError) as ctx:
            ReleaseStatus.check_transition("widerrufen", "freigegeben")
        self.assertIn("ENDGUELTIG", str(ctx.exception))

    # RS03 -------------------------------------------------------------------
    def test_rs03_unknown_states(self):
        with self.assertRaises(ReleaseStatusError):
            ReleaseStatus.check_transition("freigegeben", "quatsch")
        with self.assertRaises(ReleaseStatusError):
            ReleaseStatus.allowed_next("quatsch")

    # RS04 -------------------------------------------------------------------
    def test_rs04_umfang_vocabulary(self):
        self.assertEqual(set(UMFANG_ORDER), {"bericht", "akte", "auszug"})
        self.assertTrue(umfang_is_valid("bericht"))
        self.assertFalse(umfang_is_valid("alles"))
        self.assertIn("Ermittlungsbericht", umfang_label("bericht"))
        # unbekannt wird NICHT verschluckt -> Rueckgabe des Rohwerts.
        self.assertEqual(umfang_label("xyz"), "xyz")
        cat = umfang_catalog()
        self.assertEqual([c["code"] for c in cat], list(UMFANG_ORDER))


if __name__ == "__main__":
    unittest.main()

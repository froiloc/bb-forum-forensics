# =============================================================================
# tests/test_promotion_status.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Betrieb/Governance (AP-2G)
# =============================================================================
# Testsuite fuer Build 460: PromotionStatus (reine Zustandsmaschine).
#
# PS01 — Zustandsmengen: gespeicherte Zustaende, 'offen' ist NICHT gespeichert,
#        Endzustaende korrekt.
# PS02 — Erlaubte Uebergaenge ab 'offen' und ab 'gesichtet'.
# PS03 — Wiederaufgriff: 'zurueckgestellt' -> 'gesichtet' ist erlaubt.
# PS04 — Endzustaende sind UNWIDERRUFLICH (uebernommen/fremdzustaendig -> X).
# PS05 — 'offen' ist kein gueltiges ZIEL; unbekannte Zustaende schlagen fehl.
# PS06 — Grund-Pflicht: zurueckgestellt/fremdzustaendig verlangen einen Grund.
#
# Reine Logik, kein I/O — der Stichtag/Zustand wird uebergeben, nie gelesen.
# Version: v0.7.460 · Build: 460 · 2026-07-20
# =============================================================================

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.ops.promotion_status import (
    FINAL_STATUSES,
    INITIAL,
    STORED_STATUSES,
    PromotionStatus,
    PromotionStatusError,
)


class PromotionStatusTests(unittest.TestCase):

    # PS01 -------------------------------------------------------------------
    def test_ps01_state_sets(self):
        self.assertEqual(
            set(STORED_STATUSES),
            {"gesichtet", "uebernommen", "zurueckgestellt", "fremdzustaendig"})
        # 'offen' ist die implizite Eingangslage, NIE gespeichert.
        self.assertEqual(INITIAL, "offen")
        self.assertFalse(PromotionStatus.is_stored("offen"))
        self.assertTrue(PromotionStatus.is_known("offen"))
        for s in STORED_STATUSES:
            self.assertTrue(PromotionStatus.is_stored(s))
        self.assertEqual(set(FINAL_STATUSES),
                         {"uebernommen", "fremdzustaendig"})
        self.assertTrue(PromotionStatus.is_final("uebernommen"))
        self.assertFalse(PromotionStatus.is_final("gesichtet"))

    # PS02 -------------------------------------------------------------------
    def test_ps02_transitions_from_offen_and_gesichtet(self):
        # Ab 'offen' ist jeder gespeicherte Zustand erreichbar (erste
        # Entscheidung).
        for target in STORED_STATUSES:
            PromotionStatus.check_transition("offen", target)  # kein Fehler
        # Ab 'gesichtet': uebernommen/zurueckgestellt/fremdzustaendig, aber NICHT
        # 'gesichtet' -> 'gesichtet' (kein Selbst-Uebergang vorgesehen).
        for target in ("uebernommen", "zurueckgestellt", "fremdzustaendig"):
            PromotionStatus.check_transition("gesichtet", target)
        with self.assertRaises(PromotionStatusError):
            PromotionStatus.check_transition("gesichtet", "gesichtet")

    # PS03 -------------------------------------------------------------------
    def test_ps03_reopen_zurueckgestellt(self):
        # Wiederaufgriff einer Zurueckstellung ist ausdruecklich erlaubt.
        PromotionStatus.check_transition("zurueckgestellt", "gesichtet")
        PromotionStatus.check_transition("zurueckgestellt", "uebernommen")
        PromotionStatus.check_transition("zurueckgestellt", "fremdzustaendig")

    # PS04 -------------------------------------------------------------------
    def test_ps04_final_states_irreversible(self):
        for final in FINAL_STATUSES:
            self.assertEqual(PromotionStatus.allowed_next(final), ())
            for target in STORED_STATUSES:
                with self.assertRaises(PromotionStatusError) as ctx:
                    PromotionStatus.check_transition(final, target)
                # Die Meldung nennt ausdruecklich die Endgueltigkeit.
                self.assertIn("ENDGUELTIG", str(ctx.exception))

    # PS05 -------------------------------------------------------------------
    def test_ps05_offen_not_a_target_and_unknown_states(self):
        # 'offen' ist kein gueltiges ZIEL.
        with self.assertRaises(PromotionStatusError):
            PromotionStatus.check_transition("gesichtet", "offen")
        # Unbekannter Quell-/Zielzustand.
        with self.assertRaises(PromotionStatusError):
            PromotionStatus.check_transition("quatsch", "gesichtet")
        with self.assertRaises(PromotionStatusError):
            PromotionStatus.check_transition("offen", "quatsch")
        with self.assertRaises(PromotionStatusError):
            PromotionStatus.allowed_next("quatsch")

    # PS06 -------------------------------------------------------------------
    def test_ps06_reason_required(self):
        self.assertTrue(PromotionStatus.requires_reason("zurueckgestellt"))
        self.assertTrue(PromotionStatus.requires_reason("fremdzustaendig"))
        self.assertFalse(PromotionStatus.requires_reason("gesichtet"))
        self.assertFalse(PromotionStatus.requires_reason("uebernommen"))
        # Fehlender Grund -> Fehler; vorhandener Grund -> ok.
        with self.assertRaises(PromotionStatusError):
            PromotionStatus.check_reason("zurueckgestellt", "   ")
        with self.assertRaises(PromotionStatusError):
            PromotionStatus.check_reason("fremdzustaendig", "")
        PromotionStatus.check_reason("zurueckgestellt", "kein Bezug zum Fall")
        PromotionStatus.check_reason("uebernommen", "")  # kein Grund noetig


if __name__ == "__main__":
    unittest.main()

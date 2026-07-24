# =============================================================================
# tests/test_crossfinding_channel_status.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Querfunde (AP-2A)
# =============================================================================
# Testsuite fuer Build 507: CrossfindingChannelStatus — die Zustandsmaschine des
# Querfund-Rueckkanals. REINE LOGIK (keine DB, keine Uhr), daher hier
# vollstaendig und schnell pruefbar.
#
# CS01 — Zustandsmengen: 'offen' ist NIE speicherbar, aber benennbar;
#        Endzustaende korrekt; Labels vorhanden.
# CS02 — vollstaendige Uebergangsmatrix: JEDE Kombination aus 5 Quell- und
#        4 Zielzustaenden wird geprueft (erlaubt / verboten) — kein
#        Stichprobenglueck.
# CS03 — Endzustaende sind unumkehrbar, mit sprechender Begruendung.
# CS04 — 'quittiert' -> 'zugestellt' ist eigens verboten ("nicht ungesehen
#        machbar") und liefert die eigene Meldung.
# CS05 — 'offen' ist kein gueltiges ZIEL.
# CS06 — Pflichttext: verwertet (Basis) und nicht_relevant (Grund) verlangen
#        ihn, zugestellt/quittiert nicht; Leerraum zaehlt nicht als Angabe.
# CS07 — unbekannter Zustand wirft (nie stille leere Auswahl); rank() ordnet
#        Handlungsbeduerftiges zuerst.
#
# Version: v0.8.507 · Build: 507 · 2026-07-24
# =============================================================================

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.crossref.crossfinding_channel_status import (
    ALLOWED_TRANSITIONS,
    CrossfindingChannelError,
    CrossfindingChannelStatus as S,
    FINAL_STATUSES,
    INITIAL,
    STATUS_ORDER,
    STORED_STATUSES,
)


class CrossfindingChannelStatusTests(unittest.TestCase):

    # CS01 -------------------------------------------------------------------
    def test_cs01_zustandsmengen(self):
        self.assertEqual(INITIAL, "offen")
        # Der Pseudo-Zustand ist benennbar, aber NIE speicherbar.
        self.assertFalse(S.is_stored("offen"))
        self.assertTrue(S.is_known("offen"))
        for s in STORED_STATUSES:
            self.assertTrue(S.is_stored(s), s)
            self.assertTrue(S.is_known(s), s)
        self.assertEqual(set(FINAL_STATUSES), {"verwertet", "nicht_relevant"})
        for s in FINAL_STATUSES:
            self.assertTrue(S.is_final(s), s)
        self.assertFalse(S.is_final("quittiert"))
        # Jeder Zustand hat ein Label (nie leer -> nie eine leere Zelle).
        for s in STATUS_ORDER:
            self.assertTrue(S.label(s), s)

    # CS02 -------------------------------------------------------------------
    def test_cs02_vollstaendige_uebergangsmatrix(self):
        """
        Alle 5 x 4 Kombinationen. Erwartung direkt aus ALLOWED_TRANSITIONS —
        aber der Test prueft check_transition(), also den WEG, den der Repo
        tatsaechlich geht, nicht die Tabelle gegen sich selbst.
        """
        geprueft = 0
        for current in STATUS_ORDER:
            for target in STORED_STATUSES:
                geprueft += 1
                erlaubt = target in ALLOWED_TRANSITIONS[current]
                if erlaubt:
                    S.check_transition(current, target)   # darf nicht werfen
                else:
                    with self.assertRaises(CrossfindingChannelError,
                                           msg="%s -> %s" % (current, target)):
                        S.check_transition(current, target)
        self.assertEqual(geprueft, 5 * 4)

        # Die fachlich wichtigen Kanten ausdruecklich benannt:
        S.check_transition("offen", "quittiert")       # Zwischenschritt darf
        S.check_transition("offen", "verwertet")       #   uebersprungen werden
        S.check_transition("zugestellt", "quittiert")
        S.check_transition("quittiert", "nicht_relevant")

    # CS03 -------------------------------------------------------------------
    def test_cs03_endzustaende_unumkehrbar(self):
        for final in FINAL_STATUSES:
            self.assertEqual(S.allowed_next(final), ())
            for target in STORED_STATUSES:
                with self.assertRaises(CrossfindingChannelError) as cm:
                    S.check_transition(final, target)
                self.assertIn("ENDGUELTIG", str(cm.exception))

    # CS04 -------------------------------------------------------------------
    def test_cs04_quittiert_nicht_zurueck_auf_zugestellt(self):
        with self.assertRaises(CrossfindingChannelError) as cm:
            S.check_transition("quittiert", "zugestellt")
        self.assertIn("nicht ungesehen machen", str(cm.exception))

    # CS05 -------------------------------------------------------------------
    def test_cs05_offen_ist_kein_ziel(self):
        for current in STATUS_ORDER:
            with self.assertRaises(CrossfindingChannelError):
                S.check_transition(current, "offen")

    # CS06 -------------------------------------------------------------------
    def test_cs06_pflichttext(self):
        self.assertTrue(S.requires_reason("verwertet"))
        self.assertTrue(S.requires_reason("nicht_relevant"))
        self.assertFalse(S.requires_reason("zugestellt"))
        self.assertFalse(S.requires_reason("quittiert"))

        # Ohne Pflichttext (auch reiner Leerraum zaehlt nicht) -> Fehler.
        for target in ("verwertet", "nicht_relevant"):
            for leer in ("", "   ", None):
                with self.assertRaises(CrossfindingChannelError):
                    S.check_reason(target, leer)
            S.check_reason(target, "belegt in Vermerk 7")   # darf nicht werfen
            # Die Meldung sagt, WAS gemeint ist — Basis oder Grund.
            with self.assertRaises(CrossfindingChannelError) as cm:
                S.check_reason(target, "")
            self.assertIn(S.reason_meaning(target), str(cm.exception))

        # Zustaende ohne Pflichttext duerfen leer bleiben.
        for target in ("zugestellt", "quittiert"):
            S.check_reason(target, "")
            self.assertEqual(S.reason_meaning(target), "")

    # CS07 -------------------------------------------------------------------
    def test_cs07_unbekannt_wirft_und_rangfolge(self):
        with self.assertRaises(CrossfindingChannelError):
            S.allowed_next("quatsch")
        with self.assertRaises(CrossfindingChannelError):
            S.check_transition("quatsch", "quittiert")
        self.assertFalse(S.is_known("quatsch"))

        # Handlungsbeduerftiges zuerst, Erledigtes zuletzt.
        raenge = [S.rank(s) for s in STATUS_ORDER]
        self.assertEqual(raenge, sorted(raenge))
        self.assertEqual(raenge, [0, 1, 2, 3, 4])
        self.assertLess(S.rank("offen"), S.rank("verwertet"))


if __name__ == "__main__":
    unittest.main()

# =============================================================================
# tests/test_ad_sync_plan.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AD-Abgleich (Build 501)
# =============================================================================
# Testsuite fuer den SyncPlanner (management/ad_sync/sync_plan.py) —
# REINE Logik, kein I/O (Bauplan Build501_502 §10).
#
# SP01 — GLITCH-SCHUTZ: leere AD-Antwort -> AdSyncPlanError (nie stiller
#        Massen-Entfernungs-Plan).
# SP02 — Neuaufnahme: AD-Mitglied ohne person-Satz -> create; leerer
#        displayName faellt auf den sam zurueck.
# SP03 — Namensaenderung: aktiver Satz, abweichender displayName -> rename
#        mit alt/neu; Abgleich case-insensitiv, Identitaet bleibt DB-Schreibweise.
# SP04 — Unveraendert: identischer Anzeigename -> unchanged, keine Aenderung.
# SP05 — Entfernungs-Kandidat: aktiver Satz, sam nicht im AD -> Kandidat
#        (NICHT create/rename); inaktiver Satz nicht im AD -> unchanged_inactive.
# SP06 — Reaktivierungs-Kandidat: inaktiver Satz, sam wieder im AD ->
#        Kandidat mit display_name_ad (auch bei Namensgleichheit).
# SP07 — Mehrdeutige AD-Antwort (sam doppelt, case-insensitiv) -> Fehler.
# SP08 — AD-Mitglied ohne sam -> Fehler (kein stilles Ueberspringen).
# SP09 — Altbestand ohne is_active-Schluessel gilt als aktiv.
# SP10 — counts()/as_dict() spiegeln die Mengen (Beleg-Payload AD_SYNC_RUN).
#
# Version: v0.8.501 · Build: 501 · 2026-07-24
# =============================================================================

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.ad_sync.sync_plan import AdSyncPlanError, SyncPlanner


def _p(pid, sam, name, active=True, **extra):
    d = {"id": pid, "system_username": sam, "display_name": name,
         "is_active": active}
    d.update(extra)
    return d


class SyncPlannerTests(unittest.TestCase):

    # SP01 -------------------------------------------------------------------
    def test_sp01_empty_ad_raises(self):
        with self.assertRaises(AdSyncPlanError):
            SyncPlanner.build([], [_p(1, "h001", "KHK Muster")])

    # SP02 -------------------------------------------------------------------
    def test_sp02_create_with_display_fallback(self):
        plan = SyncPlanner.build(
            [{"sam": "h0neu", "display_name": ""},
             {"sam": "h0zwei", "display_name": "KOKin Beispiel"}],
            [],
        )
        self.assertEqual(
            plan.create,
            [{"sam": "h0neu", "display_name": "h0neu"},
             {"sam": "h0zwei", "display_name": "KOKin Beispiel"}])
        self.assertEqual(plan.rename, [])
        self.assertEqual(plan.deactivate_candidates, [])

    # SP03 -------------------------------------------------------------------
    def test_sp03_rename_case_insensitive(self):
        plan = SyncPlanner.build(
            [{"sam": "H001", "display_name": "KHK Muster, PP Neustadt"}],
            [_p(7, "h001", "KHK Muster, PP Altstadt")],
        )
        self.assertEqual(plan.create, [])
        self.assertEqual(plan.rename, [{
            "person_id": 7,
            "system_username": "h001",   # Identitaet: DB-Schreibweise
            "display_name_alt": "KHK Muster, PP Altstadt",
            "display_name_neu": "KHK Muster, PP Neustadt",
        }])

    # SP04 -------------------------------------------------------------------
    def test_sp04_unchanged(self):
        plan = SyncPlanner.build(
            [{"sam": "h001", "display_name": "KHK Muster"}],
            [_p(1, "h001", "KHK Muster")],
        )
        self.assertEqual(plan.counts()["unchanged"], 1)
        self.assertEqual(plan.create, [])
        self.assertEqual(plan.rename, [])
        self.assertEqual(plan.deactivate_candidates, [])
        self.assertEqual(plan.reactivate_candidates, [])

    # SP05 -------------------------------------------------------------------
    def test_sp05_deactivate_candidate_and_inactive_stays(self):
        plan = SyncPlanner.build(
            [{"sam": "h001", "display_name": "KHK Muster"}],
            [_p(1, "h001", "KHK Muster"),
             _p(2, "h0weg", "KOK Weg", active=True),
             _p(3, "h0alt", "KHKin Ruhestand", active=False)],
        )
        self.assertEqual(plan.deactivate_candidates, [{
            "person_id": 2, "system_username": "h0weg",
            "display_name": "KOK Weg"}])
        self.assertEqual(plan.counts()["unchanged_inactive"], 1)
        self.assertEqual(plan.reactivate_candidates, [])

    # SP06 -------------------------------------------------------------------
    def test_sp06_reactivate_candidate(self):
        plan = SyncPlanner.build(
            [{"sam": "h0alt", "display_name": "KHKin Zurueck"}],
            [_p(3, "h0alt", "KHKin Ruhestand", active=False)],
        )
        self.assertEqual(plan.reactivate_candidates, [{
            "person_id": 3, "system_username": "h0alt",
            "display_name": "KHKin Ruhestand",
            "display_name_ad": "KHKin Zurueck"}])
        # KEIN rename fuer inaktive Saetze (Nachzug erst bei Reaktivierung).
        self.assertEqual(plan.rename, [])
        self.assertEqual(plan.create, [])

    # SP07 -------------------------------------------------------------------
    def test_sp07_duplicate_sam_raises(self):
        with self.assertRaises(AdSyncPlanError):
            SyncPlanner.build(
                [{"sam": "h001", "display_name": "A"},
                 {"sam": "H001", "display_name": "B"}],
                [],
            )

    # SP08 -------------------------------------------------------------------
    def test_sp08_missing_sam_raises(self):
        with self.assertRaises(AdSyncPlanError):
            SyncPlanner.build(
                [{"sam": "  ", "display_name": "Ohne Kennung"}], [])

    # SP09 -------------------------------------------------------------------
    def test_sp09_legacy_person_without_is_active_is_active(self):
        legacy = {"id": 1, "system_username": "h001",
                  "display_name": "KHK Muster"}  # kein is_active (vor M020)
        plan = SyncPlanner.build(
            [{"sam": "h002", "display_name": "Neu"}], [legacy])
        # Altbestand gilt als aktiv -> Entfernungs-Kandidat, kein Reaktivierer.
        self.assertEqual(len(plan.deactivate_candidates), 1)
        self.assertEqual(plan.reactivate_candidates, [])

    # SP10 -------------------------------------------------------------------
    def test_sp10_counts_and_as_dict(self):
        plan = SyncPlanner.build(
            [{"sam": "h0neu", "display_name": "Neu"},
             {"sam": "h001", "display_name": "Umbenannt"},
             {"sam": "h0alt", "display_name": "Zurueck"}],
            [_p(1, "h001", "Alt"),
             _p(2, "h0weg", "Weg"),
             _p(3, "h0alt", "Ruhe", active=False)],
        )
        c = plan.counts()
        self.assertEqual(
            (c["create"], c["rename"], c["deactivate_candidates"],
             c["reactivate_candidates"]), (1, 1, 1, 1))
        d = plan.as_dict()
        self.assertEqual(d["counts"], c)
        self.assertEqual(d["create"][0]["sam"], "h0neu")


if __name__ == "__main__":
    unittest.main()

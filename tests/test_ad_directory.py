# =============================================================================
# tests/test_ad_directory.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AD-Schicht (F4)
# =============================================================================
# Testsuite fuer Build 462: ADDirectory (gekapselt, mockbar, nur lesend).
#
# AD01 — resolve_recipient: bekannter Empfaenger -> Kennung + Anzeigename.
# AD02 — DEFAULT-DENY: unbekannte/leere Kennung -> ADDirectoryError.
# AD03 — case-insensitiv, aber KANONISCHE Schreibweise zurueck.
# AD04 — leere Allowlist -> niemand freigabefaehig; members() leer.
# AD05 — members()/group Anzeige.
#
# Reine Logik, kein I/O.
# Version: v0.7.462 · Build: 462 · 2026-07-20
# =============================================================================

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.external.ad_directory import ADDirectory, ADDirectoryError


class ADDirectoryTests(unittest.TestCase):

    def setUp(self):
        self.ad = ADDirectory(
            recipients={"h0b1234": "KHK Muster, PP Musterstadt",
                        "h0c9999": "KOKin Beispiel"},
            group="SEC_16_03_EK-Zarewitsch-Extern")

    # AD01 -------------------------------------------------------------------
    def test_ad01_resolve_known(self):
        r = self.ad.resolve_recipient("h0b1234")
        self.assertEqual(r["kennung"], "h0b1234")
        self.assertEqual(r["display_name"], "KHK Muster, PP Musterstadt")
        self.assertTrue(self.ad.is_member("h0b1234"))

    # AD02 -------------------------------------------------------------------
    def test_ad02_default_deny(self):
        with self.assertRaises(ADDirectoryError):
            self.ad.resolve_recipient("h0xxxxx")
        with self.assertRaises(ADDirectoryError):
            self.ad.resolve_recipient("")
        self.assertFalse(self.ad.is_member("h0xxxxx"))

    # AD03 -------------------------------------------------------------------
    def test_ad03_case_insensitive_canonical(self):
        # Grossschreibung wird erkannt ...
        self.assertTrue(self.ad.is_member("H0B1234"))
        r = self.ad.resolve_recipient("  H0B1234 ")
        # ... aber die KANONISCHE (konfigurierte) Schreibweise kommt zurueck.
        self.assertEqual(r["kennung"], "h0b1234")

    # AD04 -------------------------------------------------------------------
    def test_ad04_empty_allowlist_denies_all(self):
        empty = ADDirectory()
        self.assertEqual(empty.members(), [])
        with self.assertRaises(ADDirectoryError):
            empty.resolve_recipient("h0b1234")

    # AD05 -------------------------------------------------------------------
    def test_ad05_members_and_group(self):
        self.assertEqual(self.ad.group, "SEC_16_03_EK-Zarewitsch-Extern")
        members = self.ad.members()
        self.assertEqual([m["kennung"] for m in members],
                         ["h0b1234", "h0c9999"])   # sortiert


if __name__ == "__main__":
    unittest.main()

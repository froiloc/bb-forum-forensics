# =============================================================================
# tests/test_lkae_distribution.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: LKAe-Distribution (AP-2G)
# =============================================================================
# Testsuite fuer Build 466: lkae_dist (Demo-Paketbau + Selbst-Verifikation).
#
# LD01 — build(): Paket entsteht (Code + Demo-DB + Manifest); Manifest is_demo +
#        Freigabe-Vermerk; verify() gruen.
# LD02 — build() ohne Freigabe -> LkaeDistributionError (default-deny).
# LD03 — build() bei PROD-Ueberlappung -> LkaeDistributionError (NICHT PROD).
# LD04 — build() in ein nicht-leeres Ziel -> Fehler.
# LD05 — verify() erkennt Aenderung (Manipulation).
# LD06 — verify() erkennt eine zusaetzliche Datei.
# LD07 — Whitelist/Ausschluss: keine *.md aus management/, kein __pycache__;
#        --no-docker laesst das Dockerfile weg.
#
# Version: v0.7.466 · Build: 466 · 2026-07-20
# =============================================================================

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.distribution import lkae_dist
from management.distribution.lkae_dist import LkaeDistributionError

# Ein PROD-Pfad, der garantiert NICHT unter dem Temp-Ziel liegt.
_FAKE_PROD = ["/nonexistent/aiw_prod/data"]


class LkaeDistributionTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._root = tempfile.mkdtemp()
        cls.target = os.path.join(cls._root, "demo")
        cls.res = lkae_dist.build(
            target_dir=cls.target, freigabe="Freigabe EK-Leitung Az.12/26",
            actor="demo_chef", prod_data_paths=_FAKE_PROD)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._root, ignore_errors=True)

    # LD01 -------------------------------------------------------------------
    def test_ld01_package_built(self):
        t = Path(self.target)
        self.assertTrue((t / "management.py").exists())
        self.assertTrue((t / "core").is_dir())
        self.assertTrue((t / "db").is_dir())
        self.assertTrue((t / "data" / "coordinator.db").exists())
        self.assertTrue((t / "config.yaml").exists())
        self.assertTrue((t / "start.sh").exists())
        self.assertTrue((t / "manifest.json").exists())

        manifest = json.loads((t / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["is_demo"])
        self.assertEqual(manifest["freigabe"]["vermerk"],
                         "Freigabe EK-Leitung Az.12/26")
        self.assertEqual(manifest["freigabe"]["actor"], "demo_chef")
        self.assertGreater(manifest["file_count"], 0)

        v = lkae_dist.verify(self.target)
        self.assertTrue(v["ok"], v)

    # LD02 -------------------------------------------------------------------
    def test_ld02_freigabe_required(self):
        with self.assertRaises(LkaeDistributionError):
            lkae_dist.build(target_dir=os.path.join(self._root, "x"),
                            freigabe="   ")

    # LD03 -------------------------------------------------------------------
    def test_ld03_prod_overlap_refused(self):
        tgt = os.path.join(self._root, "p")
        with self.assertRaises(LkaeDistributionError):
            lkae_dist.build(target_dir=tgt, freigabe="ok",
                            prod_data_paths=[os.path.join(tgt, "data")])

    # LD04 -------------------------------------------------------------------
    def test_ld04_nonempty_target_refused(self):
        tgt = os.path.join(self._root, "ne")
        os.makedirs(tgt)
        Path(tgt, "vorhanden.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(LkaeDistributionError):
            lkae_dist.build(target_dir=tgt, freigabe="ok",
                            prod_data_paths=_FAKE_PROD)

    # LD05 -------------------------------------------------------------------
    def test_ld05_verify_detects_tamper(self):
        tgt = os.path.join(self._root, "tamper")
        lkae_dist.build(target_dir=tgt, freigabe="ok", prod_data_paths=_FAKE_PROD)
        mgmt = Path(tgt, "management.py")
        mgmt.write_text(mgmt.read_text(encoding="utf-8") + "\n# tampered\n",
                        encoding="utf-8")
        v = lkae_dist.verify(tgt)
        self.assertFalse(v["ok"])
        self.assertIn("management.py", v["mismatch"])

    # LD06 -------------------------------------------------------------------
    def test_ld06_verify_detects_extra(self):
        tgt = os.path.join(self._root, "extra")
        lkae_dist.build(target_dir=tgt, freigabe="ok", prod_data_paths=_FAKE_PROD)
        Path(tgt, "zusatz.txt").write_text("unerwartet", encoding="utf-8")
        v = lkae_dist.verify(tgt)
        self.assertFalse(v["ok"])
        self.assertIn("zusatz.txt", v["extra"])

    # LD07 -------------------------------------------------------------------
    def test_ld07_whitelist_and_no_docker(self):
        t = Path(self.target)
        # Kein interner Planungs-*.md unter management/ (nur README_DEMO.md an
        # der Wurzel ist erlaubt).
        mds = [p for p in (t / "management").rglob("*.md")]
        self.assertEqual(mds, [], "interne *.md ins Paket gelangt")
        # Kein __pycache__ mitgepackt.
        caches = [p for p in t.rglob("__pycache__")]
        self.assertEqual(caches, [])
        # --no-docker laesst das Dockerfile weg.
        tgt = os.path.join(self._root, "nodocker")
        lkae_dist.build(target_dir=tgt, freigabe="ok",
                        prod_data_paths=_FAKE_PROD, include_docker=False)
        self.assertFalse(Path(tgt, "Dockerfile").exists())
        self.assertTrue(Path(tgt, "README_DEMO.md").exists())


if __name__ == "__main__":
    unittest.main()

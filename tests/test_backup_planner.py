# =============================================================================
# tests/test_backup_planner.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Backup/PITR (Welle 0)
# =============================================================================
# Testsuite fuer Build 352: Backup-Konfiguration + Enumeration + Speicherplatz-
# Vorabpruefung.
#
# BC01 — BackupConfig.from_loader: Werte aus config.yaml korrekt getypt.
# BC02 — BackupConfig: ungueltiger checkpoint ('truncate') -> Fehler.
# BC03 — BackupConfig: retention < 1 / factor <= 0 -> Fehler.
# BP01 — enumerate_sources: findet coordinator + shared + alle per-uid DBs.
# BP02 — include_shared_dbs=False: default/templates/translations ausgelassen.
# BP03 — plan: total_size + required_free korrekt; ok bei genug Platz.
# BP04 — plan: absurd hoher min_free_factor -> ok=False + Begruendung.
# BP05 — plan: fehlende Einzel-DB (translations) -> in missing, nicht fatal.
# BP06 — plan: unerreichbares Ziel -> ok=False + Begruendung.
# BP07 — plan: keine Quellen -> ok=False.
#
# Version: v0.7.352 · Build: 352 · 2026-07-10
# =============================================================================

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.backup.backup_config import BackupConfig, BackupConfigError
from management.backup.backup_planner import BackupPlanner


def _write(path, data=b"x"):
    with open(path, "wb") as f:
        f.write(data)


class _StubLoader:
    """Minimaler ConfigLoader-Ersatz mit .get(dotted_key, default)."""
    def __init__(self, values):
        self._v = values

    def get(self, key, default=None):
        return self._v.get(key, default)


class BackupConfigTests(unittest.TestCase):

    def test_bc01_from_loader(self):
        cfg = BackupConfig.from_loader(_StubLoader({
            "backup.dest_dir": "\\\\prod01\\dfs\\backups\\",
            "backup.retention_count": 5,
            "backup.min_free_factor": 1.5,
            "backup.checkpoint": "passive",
            "backup.include_shared_dbs": True,
        }))
        self.assertEqual(cfg.dest_dir, "\\\\prod01\\dfs\\backups\\")
        self.assertEqual(cfg.retention_count, 5)
        self.assertAlmostEqual(cfg.min_free_factor, 1.5)
        self.assertEqual(cfg.checkpoint, "passive")
        self.assertTrue(cfg.include_shared_dbs)

    def test_bc01b_defaults(self):
        # Leerer Loader -> dokumentierte Defaults.
        cfg = BackupConfig.from_loader(_StubLoader({}))
        self.assertEqual(cfg.dest_dir, "./backups/")
        self.assertEqual(cfg.retention_count, 7)
        self.assertAlmostEqual(cfg.min_free_factor, 1.3)
        self.assertEqual(cfg.checkpoint, "passive")
        self.assertTrue(cfg.include_shared_dbs)

    def test_bc02_truncate_rejected(self):
        with self.assertRaises(BackupConfigError):
            BackupConfig.from_loader(_StubLoader(
                {"backup.checkpoint": "truncate"}))

    def test_bc03_bounds(self):
        with self.assertRaises(BackupConfigError):
            BackupConfig.from_loader(_StubLoader(
                {"backup.retention_count": 0}))
        with self.assertRaises(BackupConfigError):
            BackupConfig.from_loader(_StubLoader(
                {"backup.min_free_factor": 0}))


class BackupPlannerTests(unittest.TestCase):

    def setUp(self):
        import tempfile
        self._tmp = tempfile.mkdtemp()
        base = Path(self._tmp)
        (base / "data").mkdir()
        (base / "data" / "forensic").mkdir()
        (base / "data" / "evidence").mkdir()
        (base / "data" / "assets").mkdir()
        (base / "backups").mkdir()

        _write(base / "data" / "coordinator.db", b"c" * 100)
        _write(base / "data" / "default.db", b"d" * 50)
        _write(base / "data" / "templates.db", b"t" * 40)
        _write(base / "data" / "translations.db", b"r" * 30)
        _write(base / "data" / "forensic" / "forensic_18.db", b"f" * 200)
        _write(base / "data" / "evidence" / "evidence_18.db", b"e" * 300)
        _write(base / "data" / "assets" / "assets_18.db", b"a" * 60)
        # Nicht-.db-Datei im Verzeichnis -> muss ignoriert werden.
        _write(base / "data" / "evidence" / "notiz.txt", b"ignore")

        self._paths = {
            "coordinator_db": str(base / "data" / "coordinator.db"),
            "default_db": str(base / "data" / "default.db"),
            "templates_db": str(base / "data" / "templates.db"),
            "translations_db": str(base / "data" / "translations.db"),
            "forensic_db_dir": str(base / "data" / "forensic"),
            "evidence_db_dir": str(base / "data" / "evidence"),
            "assets_db_dir": str(base / "data" / "assets"),
        }
        self._dest = str(base / "backups")
        self._base = base

    def tearDown(self):
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    def _cfg(self, **over):
        base = dict(dest_dir=self._dest, retention_count=7,
                    min_free_factor=1.3, checkpoint="passive",
                    include_shared_dbs=True)
        base.update(over)
        return BackupConfig(**base)

    def test_bp01_enumerate_all(self):
        pl = BackupPlanner(self._paths, self._cfg())
        sources, missing = pl.enumerate_sources()
        labels = sorted(s.label for s in sources)
        self.assertEqual(labels, [
            "assets_18", "coordinator", "default", "evidence_18",
            "forensic_18", "templates", "translations"])
        self.assertEqual(missing, [])  # alles vorhanden
        # notiz.txt wurde ignoriert.
        self.assertNotIn("notiz", labels)

    def test_bp02_exclude_shared(self):
        pl = BackupPlanner(self._paths, self._cfg(include_shared_dbs=False))
        sources, _ = pl.enumerate_sources()
        labels = sorted(s.label for s in sources)
        self.assertEqual(labels, [
            "assets_18", "coordinator", "evidence_18", "forensic_18"])

    def test_bp03_plan_ok_and_sizes(self):
        pl = BackupPlanner(self._paths, self._cfg())
        plan = pl.plan()
        expected_total = 100 + 50 + 40 + 30 + 200 + 300 + 60
        self.assertEqual(plan.total_size, expected_total)
        import math
        self.assertEqual(plan.required_free,
                         int(math.ceil(expected_total * 1.3)))
        self.assertTrue(plan.ok)     # Temp-FS hat reichlich Platz
        self.assertEqual(plan.reason, "")

    def test_bp04_insufficient_space(self):
        # Absurd hoher Faktor -> benoetigt mehr als frei ist.
        pl = BackupPlanner(self._paths, self._cfg(min_free_factor=1e15))
        plan = pl.plan()
        self.assertFalse(plan.ok)
        self.assertIn("Zu wenig Speicher", plan.reason)

    def test_bp05_missing_single_db(self):
        os.remove(self._base / "data" / "translations.db")
        pl = BackupPlanner(self._paths, self._cfg())
        plan = pl.plan()
        self.assertTrue(plan.ok)  # fehlende translations.db ist nicht fatal
        self.assertTrue(any("translations" in m for m in plan.missing))

    def test_bp06_dest_unreachable(self):
        cfg = self._cfg(dest_dir="/nonexistent_root_xyz/sub/backups")
        pl = BackupPlanner(self._paths, cfg)
        plan = pl.plan()
        self.assertFalse(plan.ok)
        self.assertIn("nicht", plan.reason.lower())

    def test_bp07_no_sources(self):
        empty_paths = {
            "coordinator_db": str(self._base / "data" / "fehlt.db"),
            "forensic_db_dir": str(self._base / "leer1"),
            "evidence_db_dir": str(self._base / "leer2"),
            "assets_db_dir": str(self._base / "leer3"),
        }
        pl = BackupPlanner(empty_paths,
                           self._cfg(include_shared_dbs=False))
        plan = pl.plan()
        self.assertFalse(plan.ok)
        self.assertIn("Keine Quell", plan.reason)


if __name__ == "__main__":
    unittest.main()

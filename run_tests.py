#!/usr/bin/env python3
"""
run_tests.py — Testrunner für aiw_sqlite_prepper
=================================================
Stellt sicher dass das Projektroot im sys.path liegt und
führt alle Regressionstests aus.

Aufruf (aus beliebigem Verzeichnis):
    python /pfad/zu/aiw_sqlite_prepper/run_tests.py

Build: 003 · 2026-04-07
"""
import sys
import unittest
from pathlib import Path

# Projektroot immer zuerst in sys.path eintragen
project_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(project_root))

if __name__ == "__main__":
    loader = unittest.TestLoader()
    # top_level_dir = project_root sorgt dafür dass Module als
    # 'tests.test_stage1' statt 'test_stage1' gefunden werden —
    # beides funktioniert, aber top_level_dir verhindert den
    # "Start directory is not importable"-Fehler in Python 3.14.
    suite = loader.discover(
        start_dir     = str(project_root / "tests"),
        pattern       = "test_*.py",
        top_level_dir = str(project_root),
    )
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

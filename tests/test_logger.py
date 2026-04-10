# =============================================================================
# tests/test_logger.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite für core/logger.py
#
# Abgedeckte Testfälle:
#   T01 — setup_logging() registriert genau zwei Handler (Konsole + Datei)
#   T02 — setup_logging() ist idempotent (Mehrfachaufruf erzeugt keine Duplikate)
#   T03 — Log-Level "info" wird korrekt gesetzt
#   T04 — Log-Level "debug" wird korrekt gesetzt
#   T05 — Logdatei wird angelegt (Verzeichnis wird erstellt falls nötig)
#   T06 — get_logger(__name__) gibt Logger mit korrektem Präfix zurück
#   T07 — get_logger("__main__") gibt Root-Logger zurück
#   T08 — Logger schreibt tatsächlich in die Logdatei
#   T09 — reset_for_testing() ermöglicht erneutes setup_logging()
#   T10 — Propagation zum Python-Root-Logger ist deaktiviert
#
# Version: v0.1.0 · Build: 002 · 2026-04-10
# =============================================================================

import sys
import os
import logging
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config_loader import ConfigLoader
from core.logger import setup_logging, get_logger, reset_for_testing, _ROOT_LOGGER_NAME


def _make_config(tmp_dir: str, level: str = "info") -> ConfigLoader:
    """Hilfsfunktion: Erstellt eine minimale ConfigLoader-Instanz für Tests."""
    logfile = os.path.join(tmp_dir, "logs", "test.log")
    config_path = os.path.join(tmp_dir, "config.yaml")
    with open(config_path, "w", encoding="utf-8") as fh:
        fh.write(textwrap.dedent(f"""
            logging:
              level: "{level}"
              logfile: "{logfile}"
              max_bytes: 1048576
              backup_count: 2
            paths:
              coordinator_db: "./data/coordinator.db"
              forensic_db_dir: "./data/forensic/"
              default_db: "./data/default.db"
              evidence_db_dir: "./data/evidence/"
        """))
    return ConfigLoader(config_path=config_path)


class TestSetupLogging(unittest.TestCase):
    """T01–T05, T10: setup_logging()-Verhalten"""

    def setUp(self):
        reset_for_testing()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        reset_for_testing()

    def test_T01_zwei_handler(self):
        """T01: setup_logging() registriert genau zwei Handler."""
        cfg = _make_config(self.tmp)
        setup_logging(cfg)
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        self.assertEqual(len(root.handlers), 2)

    def test_T02_idempotent(self):
        """T02: Mehrfacher Aufruf von setup_logging() erzeugt keine doppelten Handler."""
        cfg = _make_config(self.tmp)
        setup_logging(cfg)
        setup_logging(cfg)
        setup_logging(cfg)
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        self.assertEqual(len(root.handlers), 2)

    def test_T03_level_info(self):
        """T03: Log-Level 'info' wird korrekt auf dem Root-Logger gesetzt."""
        cfg = _make_config(self.tmp, level="info")
        setup_logging(cfg)
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        self.assertEqual(root.level, logging.INFO)

    def test_T04_level_debug(self):
        """T04: Log-Level 'debug' wird korrekt auf dem Root-Logger gesetzt."""
        cfg = _make_config(self.tmp, level="debug")
        setup_logging(cfg)
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        self.assertEqual(root.level, logging.DEBUG)

    def test_T05_logdatei_wird_angelegt(self):
        """T05: Logdatei und ihr Verzeichnis werden angelegt, falls sie nicht existieren."""
        cfg = _make_config(self.tmp)
        logfile = cfg.get("logging.logfile")
        # Verzeichnis darf noch nicht existieren
        self.assertFalse(Path(logfile).exists())
        setup_logging(cfg)
        # Nach Initialisierung muss die Datei existieren
        self.assertTrue(Path(logfile).exists())

    def test_T10_keine_propagation(self):
        """T10: Propagation zum Python-Root-Logger ist deaktiviert."""
        cfg = _make_config(self.tmp)
        setup_logging(cfg)
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        self.assertFalse(root.propagate)


class TestGetLogger(unittest.TestCase):
    """T06–T07: get_logger()-Verhalten"""

    def setUp(self):
        reset_for_testing()
        self.tmp = tempfile.mkdtemp()
        cfg = _make_config(self.tmp)
        setup_logging(cfg)

    def tearDown(self):
        reset_for_testing()

    def test_T06_logger_name_prefix(self):
        """T06: get_logger(__name__) gibt Logger mit 'forensic.'-Präfix zurück."""
        logger = get_logger("core.config_loader")
        self.assertTrue(
            logger.name.startswith(_ROOT_LOGGER_NAME + "."),
            f"Erwartet Präfix '{_ROOT_LOGGER_NAME}.', erhalten: '{logger.name}'"
        )

    def test_T07_main_logger(self):
        """T07: get_logger('__main__') gibt den Projekt-Root-Logger zurück."""
        logger = get_logger("__main__")
        self.assertEqual(logger.name, _ROOT_LOGGER_NAME)


class TestLoggingOutput(unittest.TestCase):
    """T08–T09: Ausgabe und Reset"""

    def setUp(self):
        reset_for_testing()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        reset_for_testing()

    def test_T08_schreibt_in_logdatei(self):
        """T08: Ein Log-Eintrag erscheint tatsächlich in der Logdatei."""
        cfg = _make_config(self.tmp, level="info")
        setup_logging(cfg)
        logger = get_logger("test.modul")
        testmeldung = "FORENSIC_TEST_MARKER_XYZ_42"
        logger.info(testmeldung)

        # Alle Handler schließen, damit Puffer geleert werden
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        for handler in root.handlers:
            handler.flush()

        logfile = cfg.get("logging.logfile")
        inhalt = Path(logfile).read_text(encoding="utf-8")
        self.assertIn(testmeldung, inhalt)

    def test_T09_reset_ermoeglicht_neuinitialisierung(self):
        """T09: reset_for_testing() ermöglicht erneuten setup_logging()-Aufruf."""
        cfg = _make_config(self.tmp)
        setup_logging(cfg)
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        self.assertEqual(len(root.handlers), 2)

        reset_for_testing()
        # Nach Reset: keine Handler mehr
        self.assertEqual(len(root.handlers), 0)

        # Erneutes Setup muss funktionieren
        tmp2 = tempfile.mkdtemp()
        cfg2 = _make_config(tmp2)
        setup_logging(cfg2)
        self.assertEqual(len(root.handlers), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)

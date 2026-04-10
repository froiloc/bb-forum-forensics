# =============================================================================
# tests/test_config_loader.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite für core/config_loader.py
#
# Abgedeckte Testfälle:
#   T01 — Laden einer vollständigen config.yaml
#   T02 — Laden einer leeren config.yaml (alle Defaults greifen)
#   T03 — Partieller YAML-Override (fehlende Schlüssel behalten Defaults)
#   T04 — Fehler bei nicht vorhandener config.yaml
#   T05 — Fehler bei ungültigem YAML (kein Dict auf Wurzelebene)
#   T06 — get() mit Punkt-separiertem Schlüssel
#   T07 — get() mit unbekanntem Schlüssel gibt default zurück
#   T08 — apply_cli_overrides() überschreibt Werte korrekt
#   T09 — apply_cli_overrides() ignoriert None-Werte
#   T10 — Validierung: ungültiger server.mode
#   T11 — Validierung: ungültiger server.port (zu klein)
#   T12 — Validierung: ungültiger server.port (kein Integer)
#   T13 — Validierung: ungültiges logging.level
#   T14 — Validierung: ungültiges support.temp_db
#   T15 — Validierung: leerer Pfad in paths.*
#   T16 — as_dict() gibt Tiefen-Kopie zurück (keine Mutation des internen Zustands)
#   T17 — config_path-Property gibt aufgelösten Pfad zurück
#   T18 — CLI-Override hat Vorrang vor YAML-Wert (Eskalationskette)
#   T19 — YAML-Wert hat Vorrang vor Coded Default (Eskalationskette)
#   T20 — Tiefer Merge: url_patterns.asset_prefixes aus YAML überschreibt Default
#
# Version: v0.1.0 · Build: 001 · 2026-04-10
# =============================================================================

import sys
import os
import tempfile
import textwrap
import unittest
from pathlib import Path

# Sicherstellen, dass das Projektverzeichnis im Suchpfad liegt,
# unabhängig davon, von wo die Tests gestartet werden.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config_loader import ConfigLoader


def _write_yaml(tmp_dir: str, content: str) -> str:
    """Hilfsfunktion: Schreibt YAML-Inhalt in eine temporäre Datei."""
    path = os.path.join(tmp_dir, "config.yaml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(textwrap.dedent(content))
    return path


class TestConfigLoaderLoad(unittest.TestCase):
    """T01–T05: Laden und Fehlerverhalten"""

    def test_T01_vollstaendige_config(self):
        """T01: Laden einer vollständigen config.yaml mit allen Sektionen."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_yaml(tmp, """
                server:
                  host: "127.0.0.2"
                  port: 9090
                  mode: "cli"
                paths:
                  coordinator_db: "/mnt/cdb.db"
                  forensic_db_dir: "/mnt/forensic/"
                  default_db: "/mnt/default.db"
                  evidence_db_dir: "/mnt/evidence/"
                logging:
                  level: "info"
                  logfile: "/var/log/server.log"
                  max_bytes: 5242880
                  backup_count: 3
                support:
                  temp_db: "file"
            """)
            cfg = ConfigLoader(config_path=path)
            self.assertEqual(cfg.get("server.port"), 9090)
            self.assertEqual(cfg.get("server.mode"), "cli")
            self.assertEqual(cfg.get("paths.coordinator_db"), "/mnt/cdb.db")
            self.assertEqual(cfg.get("logging.level"), "info")
            self.assertEqual(cfg.get("logging.backup_count"), 3)
            self.assertEqual(cfg.get("support.temp_db"), "file")

    def test_T02_leere_config(self):
        """T02: Leere config.yaml — alle Coded Defaults greifen."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_yaml(tmp, "")
            cfg = ConfigLoader(config_path=path)
            # Coded Defaults aus config_loader._DEFAULTS
            self.assertEqual(cfg.get("server.host"), "127.0.0.2")
            self.assertEqual(cfg.get("server.port"), 80)
            self.assertEqual(cfg.get("server.mode"), "job")
            self.assertEqual(cfg.get("support.temp_db"), "memory")

    def test_T03_partieller_override(self):
        """T03: YAML überschreibt nur gesetzte Schlüssel; fehlende behalten Default."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_yaml(tmp, """
                server:
                  port: 8080
            """)
            cfg = ConfigLoader(config_path=path)
            # Überschrieben
            self.assertEqual(cfg.get("server.port"), 8080)
            # Nicht in YAML — Default greift
            self.assertEqual(cfg.get("server.host"), "127.0.0.2")
            self.assertEqual(cfg.get("server.mode"), "job")

    def test_T04_datei_nicht_gefunden(self):
        """T04: FileNotFoundError wenn config.yaml nicht existiert."""
        with self.assertRaises(FileNotFoundError):
            ConfigLoader(config_path="/nicht/existent/config.yaml")

    def test_T05_kein_dict_auf_wurzel(self):
        """T05: ValueError wenn YAML-Wurzel kein Dict ist (z.B. nur ein String)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_yaml(tmp, "nur_ein_string\n")
            with self.assertRaises(ValueError):
                ConfigLoader(config_path=path)


class TestConfigLoaderGet(unittest.TestCase):
    """T06–T07: get()-Methode"""

    def setUp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_yaml(tmp, "")
            # ConfigLoader außerhalb des TemporaryDirectory-Kontexts verwenden
            # würde scheitern — deshalb Objekt im setUp erzeugen und Pfad merken.
            self._tmp = tempfile.mkdtemp()
            self._path = _write_yaml(self._tmp, "")
            self.cfg = ConfigLoader(config_path=self._path)

    def test_T06_get_punkt_schluessel(self):
        """T06: get() mit Punkt-separiertem Schlüssel gibt korrekten Wert zurück."""
        self.assertEqual(self.cfg.get("server.host"), "127.0.0.2")
        self.assertEqual(self.cfg.get("server.port"), 80)
        self.assertIsInstance(
            self.cfg.get("url_patterns.asset_prefixes"), list
        )
        self.assertIn(
            "/forum/style/",
            self.cfg.get("url_patterns.asset_prefixes")
        )

    def test_T07_unbekannter_schluessel(self):
        """T07: get() mit unbekanntem Schlüssel gibt default zurück."""
        self.assertIsNone(self.cfg.get("nicht.vorhanden"))
        self.assertEqual(self.cfg.get("nicht.vorhanden", "fallback"), "fallback")


class TestConfigLoaderCliOverrides(unittest.TestCase):
    """T08–T09, T18: CLI-Override-Logik"""

    def _make_cfg(self, yaml_content: str = "") -> ConfigLoader:
        tmp = tempfile.mkdtemp()
        path = _write_yaml(tmp, yaml_content)
        return ConfigLoader(config_path=path)

    def test_T08_cli_override_setzt_wert(self):
        """T08: apply_cli_overrides() schreibt Werte korrekt in Konfiguration."""
        cfg = self._make_cfg()
        cfg.apply_cli_overrides({
            "server.mode": "support",
            "logging.level": "debug",
        })
        self.assertEqual(cfg.get("server.mode"), "support")
        self.assertEqual(cfg.get("logging.level"), "debug")

    def test_T09_cli_override_ignoriert_none(self):
        """T09: None-Werte in overrides werden ignoriert (CLI-Arg nicht gesetzt)."""
        cfg = self._make_cfg()
        original_mode = cfg.get("server.mode")
        cfg.apply_cli_overrides({"server.mode": None})
        self.assertEqual(cfg.get("server.mode"), original_mode)

    def test_T18_cli_vorrang_vor_yaml(self):
        """T18: CLI-Override hat Vorrang vor YAML-Wert (Eskalationskette)."""
        cfg = self._make_cfg("""
            server:
              mode: "cli"
        """)
        # YAML setzt mode=cli
        self.assertEqual(cfg.get("server.mode"), "cli")
        # CLI überschreibt auf support
        cfg.apply_cli_overrides({"server.mode": "support"})
        self.assertEqual(cfg.get("server.mode"), "support")


class TestConfigLoaderValidation(unittest.TestCase):
    """T10–T15: Validierung ungültiger Konfigurationswerte"""

    def _make_cfg_with(self, yaml_content: str) -> None:
        tmp = tempfile.mkdtemp()
        path = _write_yaml(tmp, yaml_content)
        ConfigLoader(config_path=path)  # Soll ValueError werfen

    def test_T10_ungültiger_mode(self):
        """T10: ValueError bei ungültigem server.mode."""
        with self.assertRaises(ValueError):
            self._make_cfg_with("server:\n  mode: 'phantom'\n")

    def test_T11_port_zu_klein(self):
        """T11: ValueError bei server.port = 0."""
        with self.assertRaises(ValueError):
            self._make_cfg_with("server:\n  port: 0\n")

    def test_T12_port_kein_integer(self):
        """T12: ValueError bei server.port als String."""
        with self.assertRaises(ValueError):
            self._make_cfg_with("server:\n  port: 'achtzig'\n")

    def test_T13_ungültiges_log_level(self):
        """T13: ValueError bei ungültigem logging.level."""
        with self.assertRaises(ValueError):
            self._make_cfg_with("logging:\n  level: 'verbose'\n")

    def test_T14_ungültiges_temp_db(self):
        """T14: ValueError bei ungültigem support.temp_db."""
        with self.assertRaises(ValueError):
            self._make_cfg_with("support:\n  temp_db: 'redis'\n")

    def test_T15_leerer_pfad(self):
        """T15: ValueError wenn paths.forensic_db_dir leer ist."""
        with self.assertRaises(ValueError):
            self._make_cfg_with("paths:\n  forensic_db_dir: ''\n")


class TestConfigLoaderMisc(unittest.TestCase):
    """T16–T17, T19–T20: Verschiedenes"""

    def _make_cfg(self, yaml_content: str = "") -> ConfigLoader:
        tmp = tempfile.mkdtemp()
        path = _write_yaml(tmp, yaml_content)
        return ConfigLoader(config_path=path)

    def test_T16_as_dict_tiefenkopie(self):
        """T16: as_dict() gibt Tiefen-Kopie zurück; Mutation ändert nicht den internen Zustand."""
        cfg = self._make_cfg()
        d = cfg.as_dict()
        d["server"]["host"] = "MUTIERT"
        # Interner Zustand darf nicht verändert worden sein
        self.assertEqual(cfg.get("server.host"), "127.0.0.2")

    def test_T17_config_path_property(self):
        """T17: config_path-Property gibt aufgelösten absoluten Pfad zurück."""
        tmp = tempfile.mkdtemp()
        path = _write_yaml(tmp, "")
        cfg = ConfigLoader(config_path=path)
        self.assertTrue(cfg.config_path.is_absolute())
        self.assertTrue(cfg.config_path.exists())

    def test_T19_yaml_vorrang_vor_default(self):
        """T19: YAML-Wert hat Vorrang vor Coded Default."""
        cfg = self._make_cfg("""
            server:
              port: 9999
        """)
        # YAML-Wert (9999) soll den Coded Default (80) überschreiben
        self.assertEqual(cfg.get("server.port"), 9999)

    def test_T20_tiefer_merge_asset_prefixes(self):
        """T20: YAML-Liste für url_patterns.asset_prefixes überschreibt Default vollständig."""
        cfg = self._make_cfg("""
            url_patterns:
              asset_prefixes:
                - "/custom/style/"
                - "/custom/img/"
        """)
        prefixes = cfg.get("url_patterns.asset_prefixes")
        self.assertEqual(prefixes, ["/custom/style/", "/custom/img/"])
        # Kein gemischtes Merge mit alten Defaults
        self.assertNotIn("/forum/style/", prefixes)


if __name__ == "__main__":
    unittest.main(verbosity=2)

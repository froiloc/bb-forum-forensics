# =============================================================================
# tests/test_user_resolver.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite für core/user_resolver.py
#
# Strategie:
#   Da user_resolver.py plattformabhängigen Code enthält, werden die
#   internen _resolve_linux() und _resolve_windows()-Methoden direkt
#   getestet, indem Umgebungsvariablen temporär gesetzt und die
#   _platform-Eigenschaft über Monkey-Patching überschrieben wird.
#   So können alle Pfade auf jeder Plattform getestet werden.
#
# Abgedeckte Testfälle:
#   T01 — Erfolgreiche Auflösung unter Linux via USER-Umgebungsvariable
#   T02 — Erfolgreiche Auflösung unter Linux via pwd-Fallback (kein USER gesetzt)
#   T03 — UserResolverError wenn weder USER noch pwd einen Namen liefern (Linux)
#   T04 — Erfolgreiche Auflösung unter Windows via USERNAME-Umgebungsvariable
#   T05 — UserResolverError wenn USERNAME leer ist (Windows)
#   T06 — UserResolverError wenn USERNAME nicht gesetzt ist (Windows)
#   T07 — system_username-Property gibt unveränderlichen Wert zurück
#   T08 — is_linux / is_windows-Properties korrekt gesetzt
#   T09 — Leerzeichen im Benutzernamen werden getrimmt
#   T10 — Realer Systembenutzer wird auf der tatsächlichen Plattform ermittelt
#
# Version: v0.1.0 · Build: 003 · 2026-04-10
# =============================================================================

import sys
import os
import platform
import unittest
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import setup_logging, reset_for_testing
from core.config_loader import ConfigLoader
from core.user_resolver import UserResolver, UserResolverError


def _setup_test_logging():
    """Hilfsfunktion: Initialisiert Logging für Tests."""
    reset_for_testing()
    tmp = tempfile.mkdtemp()
    config_path = os.path.join(tmp, "config.yaml")
    logfile = os.path.join(tmp, "logs", "test.log")
    with open(config_path, "w") as fh:
        fh.write(textwrap.dedent(f"""
            logging:
              level: "debug"
              logfile: "{logfile}"
              max_bytes: 1048576
              backup_count: 2
            paths:
              coordinator_db: "./data/coordinator.db"
              forensic_db_dir: "./data/forensic/"
              default_db: "./data/default.db"
              evidence_db_dir: "./data/evidence/"
        """))
    cfg = ConfigLoader(config_path=config_path)
    setup_logging(cfg)


class TestUserResolverLinux(unittest.TestCase):
    """T01–T03: Linux-Auflösungspfade"""

    def setUp(self):
        _setup_test_logging()

    def tearDown(self):
        reset_for_testing()

    def _make_linux_resolver(self) -> UserResolver:
        """Erstellt einen UserResolver, dessen Plattform auf 'linux' erzwungen wird."""
        resolver = UserResolver.__new__(UserResolver)
        resolver._platform = "linux"
        return resolver

    def test_T01_linux_via_user_env(self):
        """T01: Erfolgreiche Auflösung unter Linux via USER-Umgebungsvariable."""
        resolver = self._make_linux_resolver()
        with patch.dict(os.environ, {"USER": "ermittler_alice"}):
            name = resolver._resolve_linux()
        self.assertEqual(name, "ermittler_alice")

    def test_T02_linux_via_pwd_fallback(self):
        """T02: Fallback auf pwd.getpwuid() wenn USER nicht gesetzt ist."""
        resolver = self._make_linux_resolver()
        env_ohne_user = {k: v for k, v in os.environ.items() if k != "USER"}

        # pwd.getpwuid() simulieren
        mock_pwd_entry = MagicMock()
        mock_pwd_entry.pw_name = "pwd_benutzer"

        with patch.dict(os.environ, env_ohne_user, clear=True):
            with patch("pwd.getpwuid", return_value=mock_pwd_entry):
                name = resolver._resolve_linux()

        self.assertEqual(name, "pwd_benutzer")

    def test_T03_linux_kein_benutzername(self):
        """T03: UserResolverError wenn weder USER noch pwd einen Namen liefern."""
        resolver = self._make_linux_resolver()
        env_ohne_user = {k: v for k, v in os.environ.items() if k != "USER"}

        with patch.dict(os.environ, env_ohne_user, clear=True):
            with patch("pwd.getpwuid", side_effect=KeyError("uid not found")):
                with self.assertRaises(UserResolverError):
                    resolver._resolve_linux()


class TestUserResolverWindows(unittest.TestCase):
    """T04–T06: Windows-Auflösungspfade"""

    def setUp(self):
        _setup_test_logging()

    def tearDown(self):
        reset_for_testing()

    def _make_windows_resolver(self) -> UserResolver:
        """Erstellt einen UserResolver, dessen Plattform auf 'windows' erzwungen wird."""
        resolver = UserResolver.__new__(UserResolver)
        resolver._platform = "windows"
        return resolver

    def test_T04_windows_via_username_env(self):
        """T04: Erfolgreiche Auflösung unter Windows via USERNAME (SAMAccountName)."""
        resolver = self._make_windows_resolver()
        with patch.dict(os.environ, {"USERNAME": "h012345"}):
            name = resolver._resolve_windows()
        self.assertEqual(name, "h012345")

    def test_T05_windows_username_leer(self):
        """T05: UserResolverError wenn USERNAME eine leere Zeichenkette ist."""
        resolver = self._make_windows_resolver()
        with patch.dict(os.environ, {"USERNAME": ""}):
            with self.assertRaises(UserResolverError):
                resolver._resolve_windows()

    def test_T06_windows_username_nicht_gesetzt(self):
        """T06: UserResolverError wenn USERNAME nicht gesetzt ist."""
        resolver = self._make_windows_resolver()
        env_ohne_username = {k: v for k, v in os.environ.items() if k != "USERNAME"}
        with patch.dict(os.environ, env_ohne_username, clear=True):
            with self.assertRaises(UserResolverError):
                resolver._resolve_windows()


class TestUserResolverProperties(unittest.TestCase):
    """T07–T09: Properties und Hilfsmethoden"""

    def setUp(self):
        _setup_test_logging()

    def tearDown(self):
        reset_for_testing()

    def _make_resolver_with_name(self, name: str, plat: str) -> UserResolver:
        """Erstellt einen fertig initialisierten UserResolver mit vorgegebenem Namen."""
        resolver = UserResolver.__new__(UserResolver)
        resolver._platform = plat
        resolver._system_username = name
        return resolver

    def test_T07_property_unveraenderlich(self):
        """T07: system_username-Property gibt konsistent denselben Wert zurück."""
        resolver = self._make_resolver_with_name("h099999", "windows")
        self.assertEqual(resolver.system_username, "h099999")
        self.assertEqual(resolver.system_username, "h099999")

    def test_T08_is_linux_is_windows(self):
        """T08: is_linux und is_windows-Properties korrekt gesetzt."""
        linux_resolver = self._make_resolver_with_name("alice", "linux")
        self.assertTrue(linux_resolver.is_linux)
        self.assertFalse(linux_resolver.is_windows)

        win_resolver = self._make_resolver_with_name("h012345", "windows")
        self.assertTrue(win_resolver.is_windows)
        self.assertFalse(win_resolver.is_linux)

    def test_T09_leerzeichen_werden_getrimmt(self):
        """T09: Führende und abschließende Leerzeichen im Benutzernamen werden entfernt."""
        resolver = self._make_resolver_with_name("", "linux")

        # Linux: USER mit Leerzeichen
        with patch.dict(os.environ, {"USER": "  alice  "}):
            name = resolver._resolve_linux()
        self.assertEqual(name, "alice")

        # Windows: USERNAME mit Leerzeichen
        resolver._platform = "windows"
        with patch.dict(os.environ, {"USERNAME": "  h012345  "}):
            name = resolver._resolve_windows()
        self.assertEqual(name, "h012345")


class TestUserResolverReal(unittest.TestCase):
    """T10: Integration — reale Plattform"""

    def setUp(self):
        _setup_test_logging()

    def tearDown(self):
        reset_for_testing()

    def test_T10_realer_systembenutzer(self):
        """T10: Auf der tatsächlichen Plattform wird ein nicht-leerer Benutzername ermittelt."""
        # Dieser Test läuft auf der echten Plattform ohne Mocking.
        # Er prüft, dass die vollständige Initialisierung fehlerfrei durchläuft
        # und einen sinnvollen Benutzernamen liefert.
        current_platform = platform.system().lower()
        if current_platform == "linux":
            # Sicherstellen, dass USER gesetzt ist (in CI-Umgebungen manchmal nicht)
            if not os.environ.get("USER"):
                self.skipTest("USER-Umgebungsvariable nicht gesetzt — Test übersprungen")

        resolver = UserResolver()
        self.assertIsInstance(resolver.system_username, str)
        self.assertGreater(len(resolver.system_username), 0)
        self.assertIn(resolver.platform, ("linux", "windows", "darwin"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

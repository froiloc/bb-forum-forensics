# =============================================================================
# tests/test_hosts_manager.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite für core/hosts_manager.py
#
# Strategie:
#   Alle Tests verwenden eine temporäre hosts-Datei statt der echten
#   Systemdatei. Die _hosts_path-Instanzvariable wird nach der
#   Initialisierung auf einen tempfile-Pfad umgebogen.
#   Plattformabhängiger Code (ctypes, os.geteuid) wird per Mock isoliert.
#   Alle Tests laufen plattformunabhängig auf Linux und Windows.
#
# Abgedeckte Testfälle:
#   T01 — DEV-Modus (enabled=false), Eintrag vorhanden → Info-Log, kein Abbruch
#   T02 — DEV-Modus (enabled=false), Eintrag fehlt → Warnung, kein Abbruch
#   T03 — DEV-Modus (enabled=false), hosts-Datei nicht lesbar → Warnung, kein Abbruch
#   T04 — DEV-Modus (enabled=false), kein hostname konfiguriert → no-op
#   T05 — PROD-Modus (enabled=true), Eintrag fehlt → wird hinzugefügt
#   T06 — PROD-Modus (enabled=true), Eintrag bereits vorhanden → keine Duplikate
#   T07 — PROD-Modus (enabled=true), kein hostname → HostsManagerError
#   T08 — PROD-Modus (enabled=true), keine Adminrechte (Windows) → HostsManagerError
#   T09 — PROD-Modus (enabled=true), keine Rootrechte (Linux) → HostsManagerError
#   T10 — cleanup() entfernt markierten Eintrag (PROD, entry_added_by_us=True)
#   T11 — cleanup() lässt manuelle Einträge unangetastet
#   T12 — cleanup() ist no-op wenn entry_added_by_us=False
#   T13 — cleanup() ist no-op im DEV-Modus (enabled=false)
#   T14 — _entry_exists() erkennt korrekte IP + Hostname-Kombination
#   T15 — _entry_exists() ignoriert auskommentierte Zeilen
#
# Version: v0.1.0 · Build: 011 · 2026-04-11
# =============================================================================

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import setup_logging, reset_for_testing
from core.config_loader import ConfigLoader
from core.hosts_manager import HostsManager, HostsManagerError, _MARKER


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _setup_test_logging(tmp_dir: str):
    """Initialisiert Logging mit temporärem Logfile für Tests."""
    reset_for_testing()
    config_path = os.path.join(tmp_dir, "config.yaml")
    logfile = os.path.join(tmp_dir, "logs", "test.log")
    with open(config_path, "w") as fh:
        fh.write(textwrap.dedent(f"""
            logging:
              level: "debug"
              logfile: "{logfile}"
              max_bytes: 1048576
              backup_count: 2
            paths:
              coordinator_db: "./coordinator.db"
              forensic_db_dir: "./forensic/"
              default_db: "./default.db"
              evidence_db_dir: "./evidence/"
        """))
    cfg = ConfigLoader(config_path=config_path)
    setup_logging(cfg)


def _make_config(tmp_dir: str, enabled: bool, hostname: str = "forum.example.org",
                 target_ip: str = "127.0.0.2") -> ConfigLoader:
    """Erstellt eine ConfigLoader-Instanz mit hosts_management-Einstellungen."""
    config_path = os.path.join(tmp_dir, "config.yaml")
    logfile = os.path.join(tmp_dir, "logs", "test.log")
    with open(config_path, "w") as fh:
        fh.write(textwrap.dedent(f"""
            logging:
              level: "debug"
              logfile: "{logfile}"
              max_bytes: 1048576
              backup_count: 2
            paths:
              coordinator_db: "./coordinator.db"
              forensic_db_dir: "./forensic/"
              default_db: "./default.db"
              evidence_db_dir: "./evidence/"
            hosts_management:
              enabled: {"true" if enabled else "false"}
              forum_hostname: "{hostname}"
              target_ip: "{target_ip}"
        """))
    return ConfigLoader(config_path=config_path)


def _make_hosts_file(tmp_dir: str, content: str = "") -> Path:
    """Erstellt eine temporäre hosts-Datei mit gegebenem Inhalt."""
    hosts_path = Path(tmp_dir) / "hosts"
    hosts_path.write_text(content, encoding="utf-8")
    return hosts_path


def _make_manager(config: ConfigLoader, hosts_path: Path,
                  is_windows: bool = False) -> HostsManager:
    """
    Erstellt einen HostsManager und biegt _hosts_path auf die temporäre
    Datei um. _is_windows wird per Parameter gesetzt, damit plattformunabhängig
    beide Pfade getestet werden können.
    """
    mgr = HostsManager(config)
    mgr._hosts_path = hosts_path
    mgr._is_windows = is_windows
    return mgr


# ---------------------------------------------------------------------------
# T01–T04: DEV-Modus (enabled=false)
# ---------------------------------------------------------------------------

class TestHostsManagerDev(unittest.TestCase):
    """T01–T04: DEV-Modus — no-op mit optionaler Warnung."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        _setup_test_logging(self._tmp)

    def tearDown(self):
        reset_for_testing()

    def test_T01_dev_eintrag_vorhanden(self):
        """T01: DEV-Modus, Eintrag manuell vorhanden → setup() ohne Fehler, kein Schreiben."""
        existing = "127.0.0.2  forum.example.org\n"
        hosts = _make_hosts_file(self._tmp, existing)
        config = _make_config(self._tmp, enabled=False)
        mgr = _make_manager(config, hosts)

        mgr.setup()  # darf nicht werfen

        # Datei muss unverändert sein
        self.assertEqual(hosts.read_text(encoding="utf-8"), existing)
        # Kein Marker wurde hinzugefügt
        self.assertNotIn(_MARKER, hosts.read_text(encoding="utf-8"))

    def test_T02_dev_eintrag_fehlt(self):
        """T02: DEV-Modus, Eintrag nicht vorhanden → Warnung, kein Abbruch, kein Schreiben."""
        hosts = _make_hosts_file(self._tmp, "# leere hosts-Datei\n")
        config = _make_config(self._tmp, enabled=False)
        mgr = _make_manager(config, hosts)

        # setup() darf trotz fehlendem Eintrag NICHT werfen
        mgr.setup()

        # Datei bleibt unverändert
        self.assertNotIn("forum.example.org", hosts.read_text(encoding="utf-8"))
        # entry_added_by_us muss False bleiben
        self.assertFalse(mgr._entry_added_by_us)

    def test_T03_dev_hosts_nicht_lesbar(self):
        """T03: DEV-Modus, hosts-Datei nicht lesbar → Warnung, kein Abbruch."""
        # Nicht-existierende Datei simuliert Lesefehler
        hosts = Path(self._tmp) / "nonexistent_hosts"
        config = _make_config(self._tmp, enabled=False)
        mgr = _make_manager(config, hosts)

        # setup() darf nicht werfen — _entry_exists() gibt False zurück
        mgr.setup()
        self.assertFalse(mgr._entry_added_by_us)

    def test_T04_dev_kein_hostname(self):
        """T04: DEV-Modus, forum_hostname leer → vollständiges no-op."""
        hosts = _make_hosts_file(self._tmp, "")
        config = _make_config(self._tmp, enabled=False, hostname="")
        mgr = _make_manager(config, hosts)

        mgr.setup()  # darf nicht werfen

        # Datei bleibt leer
        self.assertEqual(hosts.read_text(encoding="utf-8"), "")


# ---------------------------------------------------------------------------
# T05–T09: PROD-Modus (enabled=true)
# ---------------------------------------------------------------------------

class TestHostsManagerProd(unittest.TestCase):
    """T05–T09: PROD-Modus — automatische Verwaltung."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        _setup_test_logging(self._tmp)

    def tearDown(self):
        reset_for_testing()

    def _make_admin_linux_manager(self, hosts_path: Path,
                                   config: ConfigLoader) -> HostsManager:
        """Erstellt einen Linux-Manager mit simulierten Root-Rechten."""
        mgr = _make_manager(config, hosts_path, is_windows=False)
        # Root-Rechte simulieren: os.geteuid() → 0
        mgr._check_admin_rights = lambda: None  # type: ignore[method-assign]
        return mgr

    def test_T05_prod_eintrag_wird_hinzugefuegt(self):
        """T05: PROD-Modus, Eintrag fehlt → wird mit Marker hinzugefügt."""
        hosts = _make_hosts_file(self._tmp, "127.0.0.1  localhost\n")
        config = _make_config(self._tmp, enabled=True)
        mgr = self._make_admin_linux_manager(hosts, config)

        mgr.setup()

        content = hosts.read_text(encoding="utf-8")
        self.assertIn("forum.example.org", content)
        self.assertIn("127.0.0.2", content)
        self.assertIn(_MARKER, content)
        self.assertTrue(mgr._entry_added_by_us)

    def test_T06_prod_kein_duplikat(self):
        """T06: PROD-Modus, Eintrag bereits vorhanden → kein Duplikat wird geschrieben."""
        existing = "127.0.0.1  localhost\n127.0.0.2  forum.example.org\n"
        hosts = _make_hosts_file(self._tmp, existing)
        config = _make_config(self._tmp, enabled=True)
        mgr = self._make_admin_linux_manager(hosts, config)

        mgr.setup()

        content = hosts.read_text(encoding="utf-8")
        # Genau eine Zeile mit forum.example.org
        occurrences = content.count("forum.example.org")
        self.assertEqual(occurrences, 1)
        # entry_added_by_us muss False bleiben, da Eintrag bereits existierte
        self.assertFalse(mgr._entry_added_by_us)

    def test_T07_prod_kein_hostname(self):
        """T07: PROD-Modus, forum_hostname leer → HostsManagerError."""
        hosts = _make_hosts_file(self._tmp, "")
        config = _make_config(self._tmp, enabled=True, hostname="")
        mgr = _make_manager(config, hosts)

        with self.assertRaises(HostsManagerError):
            mgr.setup()

    def test_T08_prod_keine_adminrechte_windows(self):
        """T08: PROD-Modus, Windows ohne Adminrechte → HostsManagerError."""
        hosts = _make_hosts_file(self._tmp, "")
        config = _make_config(self._tmp, enabled=True)
        mgr = _make_manager(config, hosts, is_windows=True)

        # ctypes.windll existiert nur auf Windows. Wir mocken _check_admin_rights()
        # direkt auf der Instanz so, dass es eine HostsManagerError wirft —
        # das entspricht exakt dem Verhalten der echten Methode bei fehlendem Admin.
        def _no_admin():
            raise HostsManagerError(
                "Der Server muss als Administrator gestartet werden."
            )
        mgr._check_admin_rights = _no_admin  # type: ignore[method-assign]

        with self.assertRaises(HostsManagerError) as ctx:
            mgr.setup()

        self.assertIn("Administrator", str(ctx.exception))

    def test_T08b_check_admin_rights_windows_ctypes_fehler(self):
        """T08b: _check_admin_rights() wirft HostsManagerError wenn ctypes-Aufruf fehlschlägt.
        Simuliert den Fall, dass ctypes.windll nicht verfügbar ist oder eine
        Exception wirft — z.B. auf einer nicht-Windows-Plattform im PROD-Modus.
        """
        hosts = _make_hosts_file(self._tmp, "")
        config = _make_config(self._tmp, enabled=True)
        mgr = _make_manager(config, hosts, is_windows=True)

        # Den lokalen ctypes-Import in _check_admin_rights() durch einen
        # Mock ersetzen, der beim Aufruf von IsUserAnAdmin eine Exception wirft.
        # Wir patchen __import__ nur für 'ctypes', alle anderen Imports bleiben.
        original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def _mock_import(name, *args, **kwargs):
            if name == "ctypes":
                mock_ctypes = MagicMock()
                mock_ctypes.windll.shell32.IsUserAnAdmin.side_effect = OSError(
                    "ctypes nicht verfügbar"
                )
                return mock_ctypes
            return original_import(name, *args, **kwargs)

        import builtins
        with patch.object(builtins, "__import__", side_effect=_mock_import):
            with self.assertRaises(HostsManagerError) as ctx:
                mgr._check_admin_rights()

        self.assertIn("Administrator", str(ctx.exception))

    def test_T09_prod_keine_rootrechte_linux(self):
        """T09: PROD-Modus, Linux ohne Root-Rechte → HostsManagerError."""
        hosts = _make_hosts_file(self._tmp, "")
        config = _make_config(self._tmp, enabled=True)
        mgr = _make_manager(config, hosts, is_windows=False)

        # os.geteuid() → 1000 (normaler Benutzer, nicht root)
        with patch("os.geteuid", return_value=1000):
            with self.assertRaises(HostsManagerError) as ctx:
                mgr.setup()

        self.assertIn("Root", str(ctx.exception))


# ---------------------------------------------------------------------------
# T10–T13: cleanup()
# ---------------------------------------------------------------------------

class TestHostsManagerCleanup(unittest.TestCase):
    """T10–T13: cleanup() — Entfernen des Eintrags."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        _setup_test_logging(self._tmp)

    def tearDown(self):
        reset_for_testing()

    def test_T10_cleanup_entfernt_markierten_eintrag(self):
        """T10: cleanup() entfernt die von diesem Tool gesetzte Zeile."""
        marked_line = f"127.0.0.2  forum.example.org  {_MARKER}\n"
        initial = f"127.0.0.1  localhost\n{marked_line}"
        hosts = _make_hosts_file(self._tmp, initial)
        config = _make_config(self._tmp, enabled=True)
        mgr = _make_manager(config, hosts)
        # entry_added_by_us manuell auf True setzen (simuliert vorherigen setup())
        mgr._entry_added_by_us = True

        mgr.cleanup()

        content = hosts.read_text(encoding="utf-8")
        self.assertNotIn("forum.example.org", content)
        self.assertNotIn(_MARKER, content)
        # localhost-Zeile muss erhalten bleiben
        self.assertIn("127.0.0.1  localhost", content)

    def test_T11_cleanup_laesst_manuelle_eintraege_intakt(self):
        """T11: cleanup() berührt nicht manuell gesetzte Einträge ohne Marker."""
        manual_line = "127.0.0.2  forum.example.org\n"
        hosts = _make_hosts_file(self._tmp, manual_line)
        config = _make_config(self._tmp, enabled=True)
        mgr = _make_manager(config, hosts)
        mgr._entry_added_by_us = True  # obwohl wir ihn nicht gesetzt haben

        mgr.cleanup()

        # Manuelle Zeile (ohne Marker) muss erhalten bleiben
        content = hosts.read_text(encoding="utf-8")
        self.assertIn("forum.example.org", content)
        self.assertNotIn(_MARKER, content)

    def test_T12_cleanup_noop_wenn_nicht_gesetzt(self):
        """T12: cleanup() tut nichts wenn entry_added_by_us=False."""
        initial = f"127.0.0.2  forum.example.org  {_MARKER}\n"
        hosts = _make_hosts_file(self._tmp, initial)
        config = _make_config(self._tmp, enabled=True)
        mgr = _make_manager(config, hosts)
        # entry_added_by_us bleibt False (Default)

        mgr.cleanup()

        # Datei bleibt unverändert
        self.assertEqual(hosts.read_text(encoding="utf-8"), initial)

    def test_T13_cleanup_noop_in_dev_modus(self):
        """T13: cleanup() ist vollständiges no-op im DEV-Modus (enabled=false)."""
        initial = f"127.0.0.2  forum.example.org  {_MARKER}\n"
        hosts = _make_hosts_file(self._tmp, initial)
        config = _make_config(self._tmp, enabled=False)
        mgr = _make_manager(config, hosts)
        mgr._entry_added_by_us = True  # würde in PROD löschen

        mgr.cleanup()

        # Im DEV-Modus (enabled=false) darf nichts gelöscht werden
        self.assertEqual(hosts.read_text(encoding="utf-8"), initial)


# ---------------------------------------------------------------------------
# T14–T15: _entry_exists()
# ---------------------------------------------------------------------------

class TestHostsManagerEntryExists(unittest.TestCase):
    """T14–T15: _entry_exists() — Erkennungslogik."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        _setup_test_logging(self._tmp)

    def tearDown(self):
        reset_for_testing()

    def test_T14_eintrag_erkannt(self):
        """T14: _entry_exists() erkennt korrekte IP + Hostname-Kombination."""
        cases = [
            # Normaler Eintrag
            "127.0.0.2  forum.example.org\n",
            # Mit Marker
            f"127.0.0.2  forum.example.org  {_MARKER}\n",
            # Mit führenden Leerzeichen (unüblich, aber möglich)
            "  127.0.0.2  forum.example.org\n",
        ]
        for content in cases:
            hosts = _make_hosts_file(self._tmp, content)
            config = _make_config(self._tmp, enabled=False)
            mgr = _make_manager(config, hosts)
            with self.subTest(content=content.strip()):
                self.assertTrue(
                    mgr._entry_exists(),
                    f"Eintrag hätte erkannt werden sollen: {content!r}",
                )

    def test_T15_auskommentierte_zeile_ignoriert(self):
        """T15: _entry_exists() ignoriert auskommentierte Zeilen."""
        content = "# 127.0.0.2  forum.example.org\n"
        hosts = _make_hosts_file(self._tmp, content)
        config = _make_config(self._tmp, enabled=False)
        mgr = _make_manager(config, hosts)

        self.assertFalse(mgr._entry_exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

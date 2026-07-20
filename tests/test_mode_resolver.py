# =============================================================================
# tests/test_mode_resolver.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite für core/mode_resolver.py
#
# Strategie:
#   Alle Tests verwenden echte SQLite3-In-Memory- oder temporäre Datenbanken
#   statt Mocks für die DB-Schicht. Das stellt sicher, dass die SQL-Abfragen
#   gegen das tatsächliche Schema getestet werden.
#   UserResolver wird per Monkey-Patching mit einem festen Systembenutzernamen
#   versehen, um plattformunabhängig zu testen.
#
# Abgedeckte Testfälle:
#   T01 — Modus 'job': Offener Job wird korrekt aufgelöst
#   T02 — Modus 'job': Kein Job vorhanden → ModeResolverError
#   T03 — Modus 'job': Systembenutzer nicht in person → ModeResolverError
#   T04 — Modus 'job': person-Tabelle fehlt → ModeResolverError
#   T05 — Modus 'job': forensic_db wird aus subject_id abgeleitet (Build 308)
#   T06 — Modus 'cli': subject_id per CLI → ResolvedContext korrekt
#   T07 — Modus 'cli': username per CLI → subject_id aus coordinator.db aufgelöst
#   T08 — Modus 'cli': Weder subject_id noch username → ModeResolverError
#   T09 — Modus 'support': Wie cli, mode='support' im Ergebnis
#   T10 — Modus aus CLI überschreibt config.yaml (Eskalationskette)
#   T11 — Modus aus config.yaml überschreibt Coded Default (Eskalationskette)
#   T12 — Ungültiger Modus → ModeResolverError
#   T13 — Dateinamensschema: forensic_<uid>.db und evidence_<uid>.db korrekt
#   T14 — Modus 'cli': coordinator.db nicht erreichbar, subject_id bekannt → Fallback
#   T15 — ResolvedContext ist frozen (unveränderlich)
#   T16 — Modus 'job': Mehrere Jobs → ältester mit höchster Priorität gewählt
#   T17 — Modus 'cli': username-Lookup gibt neuesten scrape_jobs-Eintrag zurück
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import sys
import os
import sqlite3
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import setup_logging, reset_for_testing
from core.config_loader import ConfigLoader
from core.user_resolver import UserResolver
from core.mode_resolver import ModeResolver, ModeResolverError, ResolvedContext


# ---------------------------------------------------------------------------
# Test-Hilfsfunktionen
# ---------------------------------------------------------------------------

def _make_config(tmp_dir: str, extra_yaml: str = "") -> ConfigLoader:
    """
    Erstellt eine minimale ConfigLoader-Instanz mit tmp-Pfaden.

    extra_yaml wird als separater YAML-Block geschrieben und über die
    Basiskonfiguration gemergt. Um YAML-Kollisionen bei gleichen Top-Level-
    Schlüsseln zu vermeiden, wird extra_yaml in eine eigene temporäre Datei
    geschrieben und per apply_cli_overrides() als flaches Override aufgebracht.

    Für Tests, die nur server.mode überschreiben wollen, wird extra_yaml
    als Schlüssel-Wert-Tupel übergeben: extra_overrides dict statt raw YAML.
    Da _make_config() bereits in vielen Tests ohne extra_yaml genutzt wird,
    bleibt der Signatur-Parameter erhalten — aber extra_yaml wird jetzt als
    yaml-Fragment in eine zweite Datei geschrieben und dann manuell gemergt.
    """
    import yaml as _yaml

    coordinator_db = os.path.join(tmp_dir, "coordinator.db")
    forensic_dir   = os.path.join(tmp_dir, "forensic")
    evidence_dir   = os.path.join(tmp_dir, "evidence")
    default_db     = os.path.join(tmp_dir, "default.db")
    logfile        = os.path.join(tmp_dir, "logs", "test.log")
    config_path    = os.path.join(tmp_dir, "config.yaml")

    os.makedirs(forensic_dir, exist_ok=True)
    os.makedirs(evidence_dir, exist_ok=True)

    # Basiskonfiguration als Dict aufbauen
    base: dict = {
        "paths": {
            "coordinator_db":  coordinator_db,
            "forensic_db_dir": forensic_dir + "/",
            "evidence_db_dir": evidence_dir + "/",
            "default_db":      default_db,
        },
        "logging": {
            "level":        "debug",
            "logfile":      logfile,
            "max_bytes":    1048576,
            "backup_count": 2,
        },
    }

    # extra_yaml als Overlay mergen (falls angegeben)
    if extra_yaml.strip():
        overlay = _yaml.safe_load(textwrap.dedent(extra_yaml))
        if isinstance(overlay, dict):
            for key, value in overlay.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    base[key].update(value)
                else:
                    base[key] = value

    with open(config_path, "w", encoding="utf-8") as fh:
        _yaml.dump(base, fh, allow_unicode=True)

    return ConfigLoader(config_path=config_path)


def _make_user_resolver(system_username: str = "h012345") -> UserResolver:
    """Erstellt einen UserResolver mit vorgegebenem Systembenutzernamen."""
    resolver = UserResolver.__new__(UserResolver)
    resolver._platform = "linux"
    resolver._system_username = system_username
    return resolver


def _setup_coordinator_db(db_path: str) -> sqlite3.Connection:
    """
    Erstellt eine minimale coordinator.db mit person- und
    scrape_jobs-Tabellen. Gibt eine offene Verbindung zurück.
    """
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS person (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            system_username  TEXT NOT NULL UNIQUE,
            display_name     TEXT NOT NULL,
            is_investigator  INTEGER NOT NULL DEFAULT 1,
            is_supervisor    INTEGER NOT NULL DEFAULT 0,
            is_support       INTEGER NOT NULL DEFAULT 0,
            created_at       INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scrape_jobs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id      INTEGER NOT NULL,
            username     TEXT NOT NULL,
            priority     INTEGER NOT NULL DEFAULT 3,
            status       TEXT NOT NULL DEFAULT 'pending',
            output_path  TEXT,
            assigned_to  INTEGER REFERENCES person(id),
            created_at   INTEGER NOT NULL DEFAULT 0,
            started_at   INTEGER,
            finished_at  INTEGER,
            error_message TEXT,
            worker_id    TEXT,
            manifest_path TEXT
        );
        CREATE TABLE IF NOT EXISTS cases (
            subject_id             INTEGER PRIMARY KEY,
            username            TEXT NOT NULL,
            assigned_to         INTEGER,
            priority            INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
            status              TEXT NOT NULL DEFAULT 'open'
                                CHECK(status IN ('open','in_progress','approved','closed')),
            approved_at         INTEGER,
            total_pages_scraped INTEGER,
            note                TEXT,
            created_at          INTEGER NOT NULL,
            updated_at          INTEGER NOT NULL
        );
    """)
    con.commit()
    return con


def _setup_test_logging(tmp_dir: str):
    """Initialisiert Logging für Tests."""
    reset_for_testing()
    cfg = _make_config(tmp_dir)
    setup_logging(cfg)


# ---------------------------------------------------------------------------
# Testklassen
# ---------------------------------------------------------------------------

class TestModeResolverJob(unittest.TestCase):
    """T01–T05, T16: Modus 'job'"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _setup_test_logging(self.tmp)
        self.cfg = _make_config(self.tmp)
        self.usr = _make_user_resolver("h012345")

    def tearDown(self):
        reset_for_testing()

    def _make_db_with_job(
        self,
        system_username: str = "h012345",
        subject_id: int = 42,
        username: str = "verdaechtiger42",
        status: str = "open",
        priority: int = 3,
        output_path: str = None,  # Build 308: ungenutzt (Signatur beibehalten)
    ) -> str:
        """
        Legt coordinator.db mit einem Investigator und einer zugewiesenen Fallakte
        (cases) an. Build 308: Job-Modus löst über cdb.cases auf, nicht scrape_jobs.
        """
        db_path = self.cfg.get("paths.coordinator_db")
        con = _setup_coordinator_db(db_path)
        con.execute(
            "INSERT INTO person (system_username, display_name, created_at) "
            "VALUES (?, 'Ermittler Test', 0)",
            (system_username,),
        )
        investigator_id = con.execute(
            "SELECT id FROM person WHERE system_username = ?",
            (system_username,),
        ).fetchone()[0]
        con.execute(
            "INSERT INTO cases "
            "(subject_id, username, assigned_to, priority, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 100, 100)",
            (subject_id, username, investigator_id, priority, status),
        )
        con.commit()
        con.close()
        return db_path

    def test_T01_job_korrekt_aufgeloest(self):
        """T01: Offener Job wird korrekt aufgelöst — alle Felder stimmen."""
        self._make_db_with_job(subject_id=42, username="verdaechtiger42")
        resolver = ModeResolver(self.cfg, self.usr, {"mode": "job"})
        ctx = resolver.resolve()

        self.assertEqual(ctx.mode, "job")
        self.assertEqual(ctx.subject_id, 42)
        self.assertEqual(ctx.username, "verdaechtiger42")
        self.assertTrue(str(ctx.forensic_db).endswith("forensic_42.db"))
        self.assertTrue(str(ctx.evidence_db).endswith("evidence_42.db"))
        self.assertIsNotNone(ctx.investigator_id)

    def test_T02_kein_job(self):
        """T02: Kein offener Fall → ModeResolverError."""
        self._make_db_with_job(status="closed")  # abgeschlossener Fall
        resolver = ModeResolver(self.cfg, self.usr, {"mode": "job"})
        with self.assertRaises(ModeResolverError):
            resolver.resolve()

    def test_T03_benutzer_nicht_in_person(self):
        """T03: Systembenutzer nicht in person-Tabelle → ModeResolverError."""
        db_path = self.cfg.get("paths.coordinator_db")
        con = _setup_coordinator_db(db_path)
        # Anderen Benutzer eintragen, aber nicht h012345
        con.execute(
            "INSERT INTO person (system_username, display_name, created_at) "
            "VALUES ('anderer_nutzer', 'Jemand', 0)"
        )
        con.commit()
        con.close()

        resolver = ModeResolver(self.cfg, self.usr, {"mode": "job"})
        with self.assertRaises(ModeResolverError):
            resolver.resolve()

    def test_T04_person_tabelle_fehlt(self):
        """T04: person-Tabelle existiert nicht → ModeResolverError."""
        db_path = self.cfg.get("paths.coordinator_db")
        # Leere DB ohne Tabellen
        con = sqlite3.connect(db_path)
        con.close()

        resolver = ModeResolver(self.cfg, self.usr, {"mode": "job"})
        with self.assertRaises(ModeResolverError):
            resolver.resolve()

    def test_T05_forensic_db_aus_subject_id(self):
        """T05 (Build 308): forensic_db wird deterministisch aus subject_id abgeleitet;
        der frühere output_path-Override entfällt (cases führt kein output_path)."""
        self._make_db_with_job(subject_id=42)
        resolver = ModeResolver(self.cfg, self.usr, {"mode": "job"})
        ctx = resolver.resolve()
        self.assertTrue(str(ctx.forensic_db).endswith("forensic_42.db"))

    def test_T16_mehrere_faelle_prioritaet(self):
        """T16: Bei mehreren zugewiesenen Fällen wird der mit höchster Priorität
        (kleinste Zahl) gewählt."""
        db_path = self.cfg.get("paths.coordinator_db")
        con = _setup_coordinator_db(db_path)
        con.execute(
            "INSERT INTO person (system_username, display_name, created_at) "
            "VALUES ('h012345', 'Ermittler', 0)"
        )
        inv_id = con.execute(
            "SELECT id FROM person WHERE system_username='h012345'"
        ).fetchone()[0]
        # Fall mit niedrigerer Priorität (höhere Zahl) → soll nicht gewählt werden
        con.execute(
            "INSERT INTO cases "
            "(subject_id, username, assigned_to, priority, status, created_at, updated_at) "
            "VALUES (99, 'nutzer99', ?, 5, 'open', 200, 200)",
            (inv_id,),
        )
        # Fall mit höherer Priorität (kleinere Zahl) → soll gewählt werden
        con.execute(
            "INSERT INTO cases "
            "(subject_id, username, assigned_to, priority, status, created_at, updated_at) "
            "VALUES (77, 'nutzer77', ?, 1, 'open', 300, 300)",
            (inv_id,),
        )
        con.commit()
        con.close()

        resolver = ModeResolver(self.cfg, self.usr, {"mode": "job"})
        ctx = resolver.resolve()
        self.assertEqual(ctx.subject_id, 77)


class TestModeResolverCli(unittest.TestCase):
    """T06–T08, T14, T17: Modus 'cli'"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _setup_test_logging(self.tmp)
        self.cfg = _make_config(self.tmp)
        self.usr = _make_user_resolver("h012345")

    def tearDown(self):
        reset_for_testing()

    def _make_db_with_suspect(self, subject_id: int, username: str) -> None:
        """Legt coordinator.db mit einem Ermittler und einem Beschuldigten-Job an."""
        db_path = self.cfg.get("paths.coordinator_db")
        con = _setup_coordinator_db(db_path)
        con.execute(
            "INSERT INTO person (system_username, display_name, created_at) "
            "VALUES ('h012345', 'Ermittler', 0)"
        )
        inv_id = con.execute(
            "SELECT id FROM person WHERE system_username='h012345'"
        ).fetchone()[0]
        con.execute(
            "INSERT INTO scrape_jobs "
            "(subject_id, username, priority, status, assigned_to, created_at) "
            "VALUES (?, ?, 3, 'pending', ?, 0)",
            (subject_id, username, inv_id),
        )
        con.commit()
        con.close()

    def test_T06_cli_subject_id(self):
        """T06: Modus 'cli' mit --subject-id → ResolvedContext korrekt."""
        self._make_db_with_suspect(55, "nutzer55")
        resolver = ModeResolver(
            self.cfg, self.usr, {"mode": "cli", "subject_id": 55}
        )
        ctx = resolver.resolve()
        self.assertEqual(ctx.mode, "cli")
        self.assertEqual(ctx.subject_id, 55)
        self.assertEqual(ctx.username, "nutzer55")
        self.assertTrue(str(ctx.forensic_db).endswith("forensic_55.db"))

    def test_T07_cli_username_aufloesen(self):
        """T07: Modus 'cli' mit --username → subject_id aus coordinator.db aufgelöst."""
        self._make_db_with_suspect(66, "nutzer66")
        resolver = ModeResolver(
            self.cfg, self.usr, {"mode": "cli", "username": "nutzer66"}
        )
        ctx = resolver.resolve()
        self.assertEqual(ctx.subject_id, 66)
        self.assertEqual(ctx.username, "nutzer66")

    def test_T08_cli_weder_id_noch_name(self):
        """T08: Weder --subject-id noch --username → ModeResolverError."""
        resolver = ModeResolver(self.cfg, self.usr, {"mode": "cli"})
        with self.assertRaises(ModeResolverError):
            resolver.resolve()

    def test_T14_coordinator_db_nicht_erreichbar_mit_subject_id(self):
        """T14: coordinator.db fehlt, aber subject_id bekannt → Fallback ohne username."""
        # coordinator.db wird nicht angelegt → Fallback
        resolver = ModeResolver(
            self.cfg, self.usr, {"mode": "cli", "subject_id": 77}
        )
        ctx = resolver.resolve()
        self.assertEqual(ctx.subject_id, 77)
        self.assertEqual(ctx.username, "uid_77")
        self.assertIsNone(ctx.investigator_id)

    def test_T17_cli_username_neuester_eintrag(self):
        """T17: Bei mehreren scrape_jobs-Einträgen wird der neueste verwendet."""
        db_path = self.cfg.get("paths.coordinator_db")
        con = _setup_coordinator_db(db_path)
        con.execute(
            "INSERT INTO person (system_username, display_name, created_at) "
            "VALUES ('h012345', 'Ermittler', 0)"
        )
        inv_id = con.execute(
            "SELECT id FROM person WHERE system_username='h012345'"
        ).fetchone()[0]
        # Zwei Jobs für denselben Beschuldigten — verschiedene Usernamen
        # (Namenswechsel des Beschuldigten zwischen zwei Jobs)
        con.execute(
            "INSERT INTO scrape_jobs "
            "(subject_id, username, priority, status, assigned_to, created_at) "
            "VALUES (88, 'alter_name', 3, 'done', ?, 100)",
            (inv_id,),
        )
        con.execute(
            "INSERT INTO scrape_jobs "
            "(subject_id, username, priority, status, assigned_to, created_at) "
            "VALUES (88, 'neuer_name', 3, 'pending', ?, 200)",
            (inv_id,),
        )
        con.commit()
        con.close()

        resolver = ModeResolver(
            self.cfg, self.usr, {"mode": "cli", "subject_id": 88}
        )
        ctx = resolver.resolve()
        # Neuester Eintrag (höchste id) soll gewählt werden
        self.assertEqual(ctx.username, "neuer_name")


class TestModeResolverSupport(unittest.TestCase):
    """T09: Modus 'support'"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _setup_test_logging(self.tmp)
        self.cfg = _make_config(self.tmp)
        self.usr = _make_user_resolver("h012345")

    def tearDown(self):
        reset_for_testing()

    def test_T09_support_modus(self):
        """T09: Modus 'support' → mode='support' im ResolvedContext."""
        db_path = self.cfg.get("paths.coordinator_db")
        con = _setup_coordinator_db(db_path)
        con.execute(
            "INSERT INTO person (system_username, display_name, created_at) "
            "VALUES ('h012345', 'Support', 0)"
        )
        inv_id = con.execute(
            "SELECT id FROM person WHERE system_username='h012345'"
        ).fetchone()[0]
        con.execute(
            "INSERT INTO scrape_jobs "
            "(subject_id, username, priority, status, assigned_to, created_at) "
            "VALUES (33, 'nutzer33', 3, 'pending', ?, 0)",
            (inv_id,),
        )
        con.commit()
        con.close()

        resolver = ModeResolver(
            self.cfg, self.usr, {"mode": "support", "subject_id": 33}
        )
        ctx = resolver.resolve()
        self.assertEqual(ctx.mode, "support")
        self.assertEqual(ctx.subject_id, 33)


class TestModeResolverEscalation(unittest.TestCase):
    """T10–T12: Eskalationskette und Validierung"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _setup_test_logging(self.tmp)
        self.usr = _make_user_resolver("h012345")

    def tearDown(self):
        reset_for_testing()

    def test_T10_cli_ueberschreibt_config(self):
        """T10: Modus aus CLI überschreibt config.yaml-Wert."""
        cfg = _make_config(self.tmp, "server:\n  mode: 'job'\n")
        resolver = ModeResolver(cfg, self.usr, {"mode": "cli", "subject_id": 1})
        ctx = resolver.resolve()
        self.assertEqual(ctx.mode, "cli")

    def test_T11_config_ueberschreibt_default(self):
        """T11: Modus aus config.yaml überschreibt Coded Default ('job')."""
        cfg = _make_config(self.tmp, "server:\n  mode: 'cli'\n")
        # Kein CLI-Modus gesetzt → config.yaml-Wert greift
        resolver = ModeResolver(cfg, self.usr, {"subject_id": 1})
        ctx = resolver.resolve()
        self.assertEqual(ctx.mode, "cli")

    def test_T12_ungültiger_modus(self):
        """T12: Ungültiger Modus → ModeResolverError."""
        cfg = _make_config(self.tmp)
        resolver = ModeResolver(cfg, self.usr, {"mode": "phantom"})
        with self.assertRaises(ModeResolverError):
            resolver.resolve()


class TestModeResolverPaths(unittest.TestCase):
    """T13, T15: Pfadzusammensetzung und Unveränderlichkeit"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _setup_test_logging(self.tmp)
        self.cfg = _make_config(self.tmp)
        self.usr = _make_user_resolver("h012345")

    def tearDown(self):
        reset_for_testing()

    def test_T13_dateinamensschema(self):
        """T13: Dateinamensschema forensic_<uid>.db und evidence_<uid>.db korrekt."""
        resolver = ModeResolver(
            self.cfg, self.usr, {"mode": "cli", "subject_id": 123}
        )
        ctx = resolver.resolve()
        self.assertEqual(ctx.forensic_db.name, "forensic_123.db")
        self.assertEqual(ctx.evidence_db.name, "evidence_123.db")

    def test_T15_resolved_context_frozen(self):
        """T15: ResolvedContext ist ein frozen dataclass — keine Mutation möglich."""
        resolver = ModeResolver(
            self.cfg, self.usr, {"mode": "cli", "subject_id": 1}
        )
        ctx = resolver.resolve()
        with self.assertRaises((AttributeError, TypeError)):
            ctx.subject_id = 999  # type: ignore


if __name__ == "__main__":
    unittest.main(verbosity=2)

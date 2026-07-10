# =============================================================================
# tests/test_integration.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Phase 5: Integrationstest — Ende-zu-Ende-Abnahme
#
# Strategie:
#   Alle Tests starten einen echten ForensicHTTPServer auf einem freien
#   Loopback-Port (127.0.0.1:0 — OS wählt Port automatisch). Die Server-
#   Instanz wird in einem Hintergrundthread betrieben. Alle Datenbanken
#   sind echte SQLite3-Dateien in einem temporären Verzeichnis.
#
#   Die forensic_db wird korrekt versiegelt: SHA-256 wird nach dem Befüllen
#   mit compute_sha256_for_sealing() berechnet und in forensic_meta
#   eingetragen — exakt wie Stage 2 es im Produktionsbetrieb tut.
#
#   Der ConnectionManager und StartupChecker werden in der Startsequenz
#   wie in main.py verwendet — kein Mocking der Datenbankschicht.
#
# Abgedeckte Testfälle:
#   T01 — Startsequenz: Server startet ohne Fehler gegen echte DBs
#   T02 — Shell-Request: GET auf bekannte Forum-URL → HTTP 200, HTML-Shell
#   T03 — Shell-Request: GET auf unbekannte URL → HTTP 404 + NOT_IN_SCOPE
#   T04 — AJAX-Request: /_forensic/page bekannte URL → JSON, in_scope=True
#   T05 — AJAX-Request: /_forensic/page unbekannte URL → JSON, in_scope=False
#   T06 — AJAX-Request: /_forensic/page, html NULL → fetch_failed=True
#   T07 — Asset-Request: CSS-Datei aus default_db → HTTP 200
#   T08 — Asset-Request: unbekanntes Asset → HTTP 404
#   T09 — /_forensic/status → JSON mit korrektem user_id
#   T10 — POST außerhalb /_forensic/ → HTTP 404
#   T11 — /_forensic/annotate: vollständiger Schreibzyklus in evidence_db
#   T12 — /_forensic/viewport: Batch wird in evidence_db gespeichert
#   T13 — Sonderfall: scrape_context='investigator' → korrekt im Envelope
#   T14 — Sonderfall: URL mit ?pid= → Auflösung via post_aliases
#   T15 — Shutdown: bundle.close() nach Server-Stop ohne Fehler
#
# Version: v0.1.0 · Build: 011 · 2026-04-11
# =============================================================================

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import setup_logging, reset_for_testing
from core.config_loader import ConfigLoader
from core.mode_resolver import ResolvedContext
from core.startup_checks import StartupChecker, FORENSIC_DB_SCHEMA_VERSION
from db.connection_manager import ConnectionManager
from server.http_server import ForensicHTTPServer


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

# Server lauscht auf 127.0.0.1 (Loopback) mit Port 0 (OS wählt freien Port).
# 127.0.0.2 wird für den Produktionsbetrieb reserviert — in Tests nutzen
# wir 127.0.0.1 um keine Systemkonfiguration zu benötigen.
_TEST_HOST = "127.0.0.1"

# Header-Name für AJAX-Anfragen
_AJAX_HEADER = "X-Forensic-Request"
_AJAX_VALUE  = "ajax"


# ---------------------------------------------------------------------------
# Hilfsfunktionen — Datenbank-Aufbau
# ---------------------------------------------------------------------------

def _make_config(tmp: str) -> ConfigLoader:
    """Erstellt eine ConfigLoader-Instanz für Tests."""
    reset_for_testing()
    config_path = os.path.join(tmp, "config.yaml")
    logfile     = os.path.join(tmp, "logs", "test.log")
    with open(config_path, "w") as fh:
        fh.write(textwrap.dedent(f"""
            server:
              host: "{_TEST_HOST}"
              port: 8080
              mode: "cli"
            logging:
              level: "debug"
              logfile: "{logfile}"
              max_bytes: 1048576
              backup_count: 2
            paths:
              coordinator_db: "{os.path.join(tmp, 'coordinator.db')}"
              forensic_db_dir: "{tmp}"
              default_db: "{os.path.join(tmp, 'default.db')}"
              evidence_db_dir: "{tmp}"
            hosts_management:
              enabled: false
              forum_hostname: ""
            support:
              temp_db: "memory"
            url_patterns:
              asset_prefixes:
                - "/forum/style/"
                - "/forum/img/"
              alias_patterns:
                post_id_param: "pid"
                notify_param: "notify"
                fragment_post: "p"
        """))
    return ConfigLoader(config_path=config_path)


def _create_forensic_db(path: Path) -> None:
    """
    Erstellt eine vollständige, korrekt versiegelte forensic_db.
    Enthält vier Testseiten:
      - /forum/viewtopic.php?id=1  (user, HTML vorhanden)
      - /forum/viewtopic.php?id=2  (investigator, HTML vorhanden)
      - /forum/viewtopic.php?id=3  (user, html=NULL — fetch_failed)
      - /forum/viewtopic.php?id=4  (user, HTML vorhanden, mit page_alias)
    Alias:
      - post_aliases: post_id=99 → topic_id=4, forum_id=1
      - page_aliases: /forum/viewtopic.php?pid=99#p99 → page_id von id=4
    """
    con = sqlite3.connect(str(path))
    con.executescript(f"""
        CREATE TABLE forensic_meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE pages (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            url_canonical  TEXT    NOT NULL,
            html           BLOB,
            fetched_at     INTEGER NOT NULL,
            http_status    INTEGER NOT NULL,
            scrape_context TEXT    NOT NULL DEFAULT 'user',
            method         TEXT    NOT NULL DEFAULT 'GET',
            UNIQUE(url_canonical, method)
        );
        CREATE TABLE page_aliases (
            url_raw  TEXT PRIMARY KEY,
            page_id  INTEGER NOT NULL REFERENCES pages(id)
        );
        CREATE TABLE post_aliases (
            post_id   INTEGER PRIMARY KEY,
            topic_id  INTEGER NOT NULL,
            forum_id  INTEGER NOT NULL
        );
        CREATE TABLE pm_aliases (
            pm_post_id   INTEGER PRIMARY KEY,
            pm_topic_id  INTEGER NOT NULL
        );
        CREATE TABLE notify_aliases (
            notify_id INTEGER PRIMARY KEY,
            post_id   INTEGER NOT NULL
        );
        CREATE TABLE scrape_targets (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            scrape_context TEXT NOT NULL DEFAULT 'user',
            url_type       TEXT NOT NULL,
            forum_id       INTEGER,
            topic_id       INTEGER,
            post_id        INTEGER,
            pm_topic_id    INTEGER,
            pm_post_id     INTEGER,
            thanks_post_id INTEGER,
            poll_topic_id  INTEGER,
            actor_user_id  INTEGER,
            actor_username TEXT,
            static_url     TEXT,
            source_tables  TEXT
        );
        INSERT INTO forensic_meta VALUES ('schema_version', '{FORENSIC_DB_SCHEMA_VERSION}');
        INSERT INTO forensic_meta VALUES ('user_id', '42');
        INSERT INTO forensic_meta VALUES ('username', 'testnutzer');
        INSERT INTO forensic_meta VALUES ('created_at', '1700000000');
        INSERT INTO forensic_meta VALUES ('manifest_sha256', 'test');
    """)

    # HTML-BLOBs als echte bytes via Parameter-Binding einfügen.
    # SQL-Textliterale würden von SQLite als TEXT gespeichert — blob_handler
    # erwartet jedoch bytes (BLOB). Parameter-Binding mit bytes-Werten
    # erzwingt den korrekten BLOB-Typ.
    pages = [
        ('/forum/viewtopic.php?id=1',
         b'<html><head><title>Thread 1</title></head><body><p id="p10">Beitrag</p></body></html>',
         1700000001, 200, 'user', 'GET'),
        ('/forum/viewtopic.php?id=2',
         b'<html><head><title>Gesperrt</title></head><body><p>Gesperrter Inhalt</p></body></html>',
         1700000002, 200, 'investigator', 'GET'),
        ('/forum/viewtopic.php?id=3',
         None,   # html=NULL — fetch_failed-Fall
         1700000003, 404, 'user', 'GET'),
        ('/forum/viewtopic.php?id=4',
         b'<html><head><title>Thread 4</title></head><body><p id="p99">Post 99</p></body></html>',
         1700000004, 200, 'user', 'GET'),
    ]
    con.executemany(
        "INSERT INTO pages (url_canonical, html, fetched_at, http_status, scrape_context, method) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        pages,
    )

    con.executescript("""
        INSERT INTO page_aliases (url_raw, page_id)
        VALUES ('/forum/viewtopic.php?pid=99#p99', 4);

        INSERT INTO post_aliases (post_id, topic_id, forum_id)
        VALUES (99, 4, 1);
    """)
    con.commit()

    # SHA-256 korrekt versiegeln (wie Stage 2)
    checker = StartupChecker(
        config=_DummyConfig(),
        context=_DummyContext(path),
    )
    sha256 = checker.compute_sha256_for_sealing(path)
    con.execute(
        "INSERT INTO forensic_meta VALUES ('sha256', ?)", (sha256,)
    )
    con.commit()
    con.close()

    # READ-ONLY setzen
    path.chmod(0o444)


def _create_default_db(path: Path) -> None:
    """Erstellt eine default.db mit einem Test-CSS-Asset."""
    con = sqlite3.connect(str(path))
    con.executescript("""
        CREATE TABLE default_meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE default_assets (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT    NOT NULL UNIQUE,
            data         BLOB,
            mime_type    TEXT,
            file_size    INTEGER,
            source_note  TEXT    NOT NULL DEFAULT '',
            fetched_at   INTEGER
        );
        CREATE TABLE default_urls (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url         TEXT    NOT NULL UNIQUE,
            url_hash    TEXT    NOT NULL,
            asset_id    INTEGER REFERENCES default_assets(id),
            url_context TEXT    NOT NULL DEFAULT '',
            http_status INTEGER,
            added_at    INTEGER NOT NULL DEFAULT 0
        );
        INSERT INTO default_meta VALUES ('schema_version', '1');
        INSERT INTO default_assets (content_hash, data, mime_type, file_size, source_note)
        VALUES ('abc123', X'2F2A20746573742E637373202A2F', 'text/css', 14, 'test');
        INSERT INTO default_urls (url, url_hash, asset_id, url_context, http_status, added_at)
        VALUES ('/forum/style/test.css', 'hash1', 1, 'style', 200, 1700000000);
    """)
    con.commit()
    con.close()


def _create_coordinator_db(path: Path) -> None:
    """Erstellt eine minimale coordinator.db."""
    con = sqlite3.connect(str(path))
    con.executescript("""
        CREATE TABLE person (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            system_username  TEXT    NOT NULL UNIQUE,
            display_name     TEXT    NOT NULL,
            is_investigator  INTEGER NOT NULL DEFAULT 1,
            is_supervisor    INTEGER NOT NULL DEFAULT 0,
            is_support       INTEGER NOT NULL DEFAULT 0,
            created_at       INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE scrape_jobs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            username     TEXT    NOT NULL,
            priority     INTEGER NOT NULL DEFAULT 3,
            status       TEXT    NOT NULL DEFAULT 'pending',
            output_path  TEXT,
            assigned_to  INTEGER,
            created_at   INTEGER NOT NULL DEFAULT 0,
            started_at   INTEGER,
            finished_at  INTEGER,
            error_message TEXT,
            worker_id    TEXT,
            manifest_path TEXT
        );
    """)
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# Dummy-Objekte für compute_sha256_for_sealing()
# ---------------------------------------------------------------------------

class _DummyConfig:
    """Minimale ConfigLoader-Schnittstelle für StartupChecker."""
    def get(self, key, default=None):
        return default


class _DummyContext:
    """Minimale ResolvedContext-Schnittstelle für StartupChecker."""
    def __init__(self, forensic_db: Path):
        self.forensic_db    = forensic_db
        self.evidence_db    = forensic_db  # wird nicht geprüft
        self.default_db     = forensic_db
        self.coordinator_db = forensic_db
        self.mode           = "cli"
        self.investigator_id = None


# ---------------------------------------------------------------------------
# Fixture: Testumgebung aufbauen und Server starten
# ---------------------------------------------------------------------------

class _ServerFixture(unittest.TestCase):
    """
    Basisklasse für alle Integrationstests.
    setUp() baut alle Datenbanken auf, startet den Server in einem
    Hintergrundthread und wartet bis er bereit ist.
    tearDown() stoppt den Server und schließt alle Verbindungen.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls._setup_databases()
        cls._start_server()

    @classmethod
    def _setup_databases(cls):
        """Legt alle Testdatenbanken an."""
        cls.forensic_path   = Path(cls.tmp) / "forensic_42.db"
        cls.evidence_path   = Path(cls.tmp) / "evidence_42.db"
        cls.default_path    = Path(cls.tmp) / "default.db"
        cls.coordinator_path = Path(cls.tmp) / "coordinator.db"

        _create_forensic_db(cls.forensic_path)
        _create_default_db(cls.default_path)
        _create_coordinator_db(cls.coordinator_path)
        # evidence_db leer anlegen — EvidenceDb legt Tabellen beim Init an
        sqlite3.connect(str(cls.evidence_path)).close()

    @classmethod
    def _start_server(cls):
        """Startet den Server in einem Daemon-Thread."""
        cls.config = _make_config(cls.tmp)

        cls.context = ResolvedContext(
            mode="cli",
            user_id=42,
            username="testnutzer",
            forensic_db=cls.forensic_path,
            evidence_db=cls.evidence_path,
            default_db=cls.default_path,
            coordinator_db=cls.coordinator_path,
            assets_db=Path(cls.tmp) / "assets_42.db",
            investigator_id=1,
            investigator_username="h012345",
        )

        cls.bundle = ConnectionManager(cls.context, cls.config).open()
        cls.server = ForensicHTTPServer(
            _TEST_HOST, 0,  # Port 0 → OS wählt freien Port (Config-Port 8080 ignoriert)
            cls.bundle, cls.context, cls.config,
        )
        # Tatsächlich zugewiesenen Port merken
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://{_TEST_HOST}:{cls.port}"

        cls._thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls._thread.start()

        # Warten bis der Server bereit ist (max. 3 Sekunden)
        deadline = time.time() + 3.0
        while time.time() < deadline:
            try:
                urllib.request.urlopen(
                    f"{cls.base_url}/_forensic/status", timeout=0.5
                )
                break
            except Exception:
                time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.bundle.close()
        reset_for_testing()

    def setUp(self):
        # Logging muss für jeden Test initialisiert sein
        pass

    # ------------------------------------------------------------------
    # HTTP-Hilfsmethoden
    # ------------------------------------------------------------------

    def _get(self, path: str, ajax: bool = False) -> tuple[int, bytes, dict]:
        """Sendet GET-Request. Gibt (status, body, headers) zurück."""
        req = urllib.request.Request(f"{self.base_url}{path}")
        if ajax:
            req.add_header(_AJAX_HEADER, _AJAX_VALUE)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        except HTTPError as exc:
            # HTTPError enthält ebenfalls die Response-Header — diese
            # müssen explizit übernommen werden, da urllib sie bei 4xx
            # nicht automatisch weitergibt.
            return exc.code, exc.read(), dict(exc.headers)

    def _post(self, path: str, data: dict) -> tuple[int, bytes, dict]:
        """Sendet POST-Request mit JSON-Body. Gibt (status, body, headers) zurück."""
        body = json.dumps(data).encode("utf-8")
        req  = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Content-Length", str(len(body)))
        req.add_header(_AJAX_HEADER, _AJAX_VALUE)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        except HTTPError as exc:
            return exc.code, exc.read(), {}


# ---------------------------------------------------------------------------
# T01–T02: Startsequenz und Shell-Requests
# ---------------------------------------------------------------------------

class TestIntegrationStart(_ServerFixture):
    """T01–T02: Server-Start und grundlegender Shell-Request."""

    def test_T01_server_startet(self):
        """T01: Server startet ohne Fehler und antwortet auf /_forensic/status."""
        status, body, _ = self._get("/_forensic/status")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("version", data)
        self.assertEqual(data["user_id"], 42)

    def test_T02_shell_request_bekannte_url(self):
        """T02: GET auf bekannte Forum-URL → HTTP 200, HTML-Shell mit forensic-viewport."""
        status, body, headers = self._get("/forum/viewtopic.php?id=1")
        self.assertEqual(status, 200)
        html = body.decode("utf-8", errors="replace")
        # Shell enthält den forensic-viewport-Container
        self.assertIn("forensic-viewport", html)
        # Shell enthält toolbar.js
        self.assertIn("toolbar.js", html)


# ---------------------------------------------------------------------------
# T03: NOT_IN_SCOPE
# ---------------------------------------------------------------------------

class TestIntegrationNotInScope(_ServerFixture):
    """T03: Unbekannte URL → NOT_IN_SCOPE."""

    def test_T03_shell_unbekannte_url(self):
        """T03: GET auf unbekannte URL → HTTP 404 mit X-Forensic-Status: NOT_IN_SCOPE."""
        status, body, headers = self._get("/forum/viewtopic.php?id=9999")
        self.assertEqual(status, 404)
        # X-Forensic-Status-Header muss NOT_IN_SCOPE enthalten.
        # Header-Namen sind case-insensitiv — Wert wird in Großbuchstaben verglichen.
        header_keys_lower = {k.lower(): v for k, v in headers.items()}
        self.assertIn(
            "NOT_IN_SCOPE",
            header_keys_lower.get("x-forensic-status", "").upper()
        )


# ---------------------------------------------------------------------------
# T04–T06: AJAX-Requests (/_forensic/page)
# ---------------------------------------------------------------------------

class TestIntegrationAjaxPage(_ServerFixture):
    """T04–T06: AJAX-Requests über /_forensic/page."""

    def test_T04_ajax_bekannte_url(self):
        """T04: /_forensic/page bekannte URL → JSON-Envelope, in_scope=True."""
        import urllib.parse
        url = urllib.parse.quote("/forum/viewtopic.php?id=1", safe="")
        status, body, _ = self._get(f"/_forensic/page?url={url}", ajax=True)
        self.assertEqual(status, 200)
        env = json.loads(body)
        self.assertTrue(env["in_scope"])
        self.assertFalse(env["fetch_failed"])
        self.assertEqual(env["scrape_context"], "user")
        self.assertIsNotNone(env["html"])

    def test_T05_ajax_unbekannte_url(self):
        """T05: /_forensic/page unbekannte URL → in_scope=False."""
        import urllib.parse
        url = urllib.parse.quote("/forum/viewtopic.php?id=9999", safe="")
        status, body, _ = self._get(f"/_forensic/page?url={url}", ajax=True)
        self.assertEqual(status, 200)
        env = json.loads(body)
        self.assertFalse(env["in_scope"])

    def test_T06_ajax_fetch_failed(self):
        """T06: /_forensic/page auf Seite mit html=NULL → fetch_failed=True."""
        import urllib.parse
        url = urllib.parse.quote("/forum/viewtopic.php?id=3", safe="")
        status, body, _ = self._get(f"/_forensic/page?url={url}", ajax=True)
        self.assertEqual(status, 200)
        env = json.loads(body)
        self.assertTrue(env["in_scope"])
        self.assertTrue(env["fetch_failed"])


# ---------------------------------------------------------------------------
# T07–T08: Asset-Requests
# ---------------------------------------------------------------------------

class TestIntegrationAssets(_ServerFixture):
    """T07–T08: Statische Assets aus default_db."""

    def test_T07_css_asset_vorhanden(self):
        """T07: CSS-Datei aus default_db → HTTP 200."""
        status, body, _ = self._get("/forum/style/test.css")
        self.assertEqual(status, 200)
        self.assertGreater(len(body), 0)

    def test_T08_unbekanntes_asset(self):
        """T08: Unbekanntes Asset → HTTP 404."""
        status, _, _ = self._get("/forum/style/nichtvorhanden.css")
        self.assertEqual(status, 404)


# ---------------------------------------------------------------------------
# T09: /_forensic/status
# ---------------------------------------------------------------------------

class TestIntegrationStatus(_ServerFixture):
    """T09: Serverstatus-Endpunkt."""

    def test_T09_status_json(self):
        """T09: /_forensic/status liefert vollständiges JSON mit korrektem user_id."""
        status, body, _ = self._get("/_forensic/status")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["user_id"], 42)
        self.assertEqual(data["username"], "testnutzer")
        self.assertEqual(data["mode"], "cli")
        self.assertIn("version", data)
        self.assertIn("ts", data)


# ---------------------------------------------------------------------------
# T10: POST außerhalb /_forensic/
# ---------------------------------------------------------------------------

class TestIntegrationPostBlocked(_ServerFixture):
    """T10: POST außerhalb /_forensic/ → HTTP 404."""

    def test_T10_post_ausserhalb_forensic(self):
        """T10: POST auf normale Forum-URL → HTTP 404 (Formulare gesperrt)."""
        status, _, _ = self._post("/forum/login.php", {"user": "x", "pass": "y"})
        self.assertEqual(status, 404)


# ---------------------------------------------------------------------------
# T11–T12: Annotation und Viewport — vollständiger Schreibzyklus
# ---------------------------------------------------------------------------

class TestIntegrationWriteCycle(_ServerFixture):
    """T11–T12: Schreibzyklus in evidence_db über AJAX-Endpunkte."""

    def test_T11_annotation_schreibzyklus(self):
        """T11: POST /_forensic/annotate → Annotation in evidence_db gespeichert."""
        status, body, _ = self._post("/_forensic/annotate", {
            "page_url":  "/forum/viewtopic.php?id=1",
            "category":  "CAT_PERSON",
            "text":      "Integrations-Testnotiz",
            "element_id": "p10",
        })
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result["status"], "ok")
        annotation_id = result["id"]
        self.assertIsInstance(annotation_id, int)
        self.assertGreater(annotation_id, 0)

        # Gegenprüfung: Annotation liegt tatsächlich in der evidence_db
        annotations = self.bundle.evidence.get_annotations(
            "/forum/viewtopic.php?id=1"
        )
        texts = [a.text for a in annotations]
        self.assertIn("Integrations-Testnotiz", texts)

    def test_T12_viewport_batch(self):
        """T12: POST /_forensic/viewport → Batch in evidence_db gespeichert."""
        events = [
            {"element_id": "p10", "visible_ms": 2500,
             "ts_enter": 1700000100000, "ts_leave": 1700000102500},
        ]
        status, body, _ = self._post("/_forensic/viewport", {
            "page_url": "/forum/viewtopic.php?id=1",
            "events":   events,
        })
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["saved"], 1)


# ---------------------------------------------------------------------------
# T13: scrape_context='investigator'
# ---------------------------------------------------------------------------

class TestIntegrationInvestigatorContext(_ServerFixture):
    """T13: scrape_context='investigator' wird korrekt im Envelope übermittelt."""

    def test_T13_investigator_context_im_envelope(self):
        """T13: Seite mit scrape_context='investigator' → korrekt im JSON-Envelope."""
        import urllib.parse
        url = urllib.parse.quote("/forum/viewtopic.php?id=2", safe="")
        status, body, _ = self._get(f"/_forensic/page?url={url}", ajax=True)
        self.assertEqual(status, 200)
        env = json.loads(body)
        self.assertTrue(env["in_scope"])
        self.assertEqual(env["scrape_context"], "investigator")


# ---------------------------------------------------------------------------
# T14: URL-Auflösung via post_aliases (?pid=)
# ---------------------------------------------------------------------------

class TestIntegrationAliasResolution(_ServerFixture):
    """T14: ?pid= URL-Auflösung via post_aliases."""

    def test_T14_pid_aufloesung(self):
        """T14: ?pid=99 → Auflösung via post_aliases → korrekte Seite zurück."""
        import urllib.parse
        # URL mit pid-Parameter — soll auf /forum/viewtopic.php?id=4 aufgelöst werden
        url = urllib.parse.quote("/forum/viewtopic.php?pid=99", safe="")
        status, body, _ = self._get(f"/_forensic/page?url={url}", ajax=True)
        self.assertEqual(status, 200)
        env = json.loads(body)
        self.assertTrue(env["in_scope"])
        self.assertFalse(env["fetch_failed"])
        # blob_handler._extract_body() liefert den <body>-Inhalt ohne <head>.
        # Wir prüfen auf einen Wert aus dem <body> der Thread-4-Seite.
        self.assertIn("p99", env["html"])


# ---------------------------------------------------------------------------
# T15: Sauberer Shutdown
# ---------------------------------------------------------------------------

class TestIntegrationShutdown(unittest.TestCase):
    """T15: Sauberer Shutdown — bundle.close() nach Server-Stop ohne Fehler."""

    def test_T15_sauberer_shutdown(self):
        """T15: Server kann gestartet und sauber gestoppt werden."""
        tmp = tempfile.mkdtemp()
        reset_for_testing()

        forensic_path    = Path(tmp) / "forensic_99.db"
        evidence_path    = Path(tmp) / "evidence_99.db"
        default_path     = Path(tmp) / "default.db"
        coordinator_path = Path(tmp) / "coordinator.db"

        _create_forensic_db(forensic_path)
        _create_default_db(default_path)
        _create_coordinator_db(coordinator_path)
        sqlite3.connect(str(evidence_path)).close()

        config = _make_config(tmp)
        context = ResolvedContext(
            mode="cli", user_id=99, username="shutdown_test",
            forensic_db=forensic_path, evidence_db=evidence_path,
            default_db=default_path, coordinator_db=coordinator_path,
            assets_db=Path(coordinator_path).parent / "assets_42.db",
            investigator_id=None,
            investigator_username="h012345",
        )

        bundle = ConnectionManager(context, config).open()
        server = ForensicHTTPServer(
            _TEST_HOST, 0, bundle, context, config  # Port 0 → OS wählt freien Port
        )
        port = server.server_address[1]

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        # Kurze Aktivität sicherstellen
        time.sleep(0.05)
        try:
            urllib.request.urlopen(
                f"http://{_TEST_HOST}:{port}/_forensic/status", timeout=2
            )
        except Exception:
            pass

        # Sauberer Shutdown
        server.shutdown()
        server.server_close()

        # bundle.close() darf nach Server-Stop nicht werfen
        try:
            bundle.close()
        except Exception as exc:
            self.fail(f"bundle.close() nach Shutdown warf Exception: {exc}")

        reset_for_testing()


if __name__ == "__main__":
    unittest.main(verbosity=2)

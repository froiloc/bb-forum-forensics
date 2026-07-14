# =============================================================================
# tests/test_assets_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite für db/assets_db.py und Kaskade in server/asset_handler.py
#
# T01 — AssetsDb: Schema vorhanden (assets, asset_urls, assets_meta)
# T02 — AssetsDb: get_asset() mit bekannter URL → AssetRecord mit Daten
# T03 — AssetsDb: get_asset() mit bekannter URL, data=NULL → available=False
# T04 — AssetsDb: get_asset() mit unbekannter URL → None
# T05 — AssetsDb: get_asset() MIME-Type korrekt zurückgegeben
# T06 — AssetsDb: get_asset() fehlender MIME-Type → application/octet-stream
# T07 — AssetsDb: has_asset() bekannte URL → True
# T08 — AssetsDb: has_asset() unbekannte URL → False
# T09 — AssetsDb: con=None → kein Absturz, alle Methoden geben None/False zurück
# T10 — AssetsDb: asset_count() korrekte Anzahl
# T11 — AssetsDb: get_meta() bekannter Schlüssel zurückgegeben
# T12 — AssetHandler: Kaskade — assets_<uid>.db-Treffer schlägt default.db-Treffer
# T13 — AssetHandler: Kaskade — leere assets_db fällt auf default.db zurück
# T14 — AssetHandler: beide DBs leer → HTTP 404
# T15 — ConnectionManager: fehlende assets_<uid>.db → kein Absturz beim Open
#
# Version: v0.1.0 · Build: 024 · 2026-04-15
# =============================================================================

import os
import sqlite3
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import setup_logging, reset_for_testing
from core.config_loader import ConfigLoader
from db.assets_db import AssetsDb, AssetRecord


# ---------------------------------------------------------------------------
# Logging-Setup für Tests
# ---------------------------------------------------------------------------

def _setup_test_logging():
    reset_for_testing()
    tmp = tempfile.mkdtemp()
    config_path = os.path.join(tmp, "config.yaml")
    with open(config_path, "w") as fh:
        fh.write(textwrap.dedent(f"""
            logging:
              level: "debug"
              logfile: "{os.path.join(tmp, 'logs', 'test.log')}"
              max_bytes: 1048576
              backup_count: 2
            paths:
              coordinator_db: "./c.db"
              forensic_db_dir: "./f/"
              default_db: "./d.db"
              evidence_db_dir: "./e/"
              assets_db_dir: "./a/"
        """))
    setup_logging(ConfigLoader(config_path=config_path))


# ---------------------------------------------------------------------------
# Hilfsfunktionen: Test-DBs anlegen
# ---------------------------------------------------------------------------

def _make_adb() -> tuple[sqlite3.Connection, str]:
    """Erstellt eine temporäre assets_<uid>.db mit Testdaten, ATTACHED als adb."""
    # Physische DB-Datei anlegen und Schema befüllen
    path = tempfile.mktemp(suffix=".db")
    raw = sqlite3.connect(path)
    raw.executescript("""
        CREATE TABLE assets_meta (
            key   TEXT NOT NULL PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE assets (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT NOT NULL UNIQUE,
            data         BLOB,
            mime_type    TEXT,
            file_size    INTEGER,
            source_note  TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE asset_urls (
            url         TEXT NOT NULL PRIMARY KEY,
            asset_id    INTEGER NOT NULL REFERENCES assets(id),
            url_context TEXT NOT NULL DEFAULT 'unknown',
            page_id     INTEGER,
            url_hash    TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX assets_hash_idx ON assets (content_hash);
        CREATE INDEX au_asset_idx    ON asset_urls (asset_id);
        CREATE INDEX au_context_idx  ON asset_urls (url_context);
        CREATE INDEX au_hash_idx     ON asset_urls (url_hash);

        INSERT INTO assets_meta (key, value) VALUES ('schema_version', '1');
        INSERT INTO assets (content_hash, data, mime_type, file_size, source_note)
            VALUES ('abc123', X'89504E47', 'image/png', 4, 'test');
        INSERT INTO assets (content_hash, data, mime_type, file_size, source_note)
            VALUES ('nulldata', NULL, 'image/jpeg', NULL, 'test-null');
        INSERT INTO asset_urls (url, asset_id, url_context, url_hash)
            VALUES ('/forum/img/avatars/42.png', 1, 'avatar', 'h1');
        INSERT INTO asset_urls (url, asset_id, url_context, url_hash)
            VALUES ('/forum/img/avatars/null.jpg', 2, 'avatar', 'h2');
    """)
    raw.commit()
    raw.close()

    # Haupt-Connection erstellen und adb ATTACH
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    uri = Path(path).as_uri() + "?mode=ro"
    con.execute(f"ATTACH DATABASE '{uri}' AS adb")
    return con, path


def _make_ddb(con: sqlite3.Connection) -> None:
    """
    Fügt ddb-Tabellen (default_assets/default_urls) zu einer bestehenden
    Haupt-Connection hinzu — in-memory, kein separates ATTACH nötig da
    wir DefaultDb hier mocken.
    """
    pass  # DefaultDb wird für Kaskaden-Tests gemockt


# ---------------------------------------------------------------------------
# T01–T11: AssetsDb Unit-Tests
# ---------------------------------------------------------------------------

class TestAssetsDbInit(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _setup_test_logging()

    def test_T01_schema_vorhanden(self):
        """T01: Schema-Test — assets, asset_urls, assets_meta nach Init vorhanden."""
        con, path = _make_adb()
        try:
            db = AssetsDb(con)
            self.assertTrue(db.is_available)
            # Alle drei Tabellen direkt abfragen
            con.execute("SELECT COUNT(*) FROM adb.assets").fetchone()
            con.execute("SELECT COUNT(*) FROM adb.asset_urls").fetchone()
            con.execute("SELECT COUNT(*) FROM adb.assets_meta").fetchone()
        finally:
            con.close()
            os.unlink(path)

    def test_T09_con_none_kein_absturz(self):
        """T09: con=None → kein Absturz, AssetsDb startet ohne Fehler."""
        db = AssetsDb(None)
        self.assertFalse(db.is_available)

    def test_T09b_con_none_get_asset_returns_none(self):
        """T09: con=None → get_asset() gibt None zurück."""
        db = AssetsDb(None)
        self.assertIsNone(db.get_asset("/forum/img/avatars/42.png"))

    def test_T09c_con_none_has_asset_returns_false(self):
        """T09: con=None → has_asset() gibt False zurück."""
        db = AssetsDb(None)
        self.assertFalse(db.has_asset("/forum/img/avatars/42.png"))

    def test_T09d_con_none_asset_count_returns_zero(self):
        """T09: con=None → asset_count() gibt 0 zurück."""
        db = AssetsDb(None)
        self.assertEqual(db.asset_count(), 0)

    def test_T09e_con_none_get_meta_returns_none(self):
        """T09: con=None → get_meta() gibt None zurück."""
        db = AssetsDb(None)
        self.assertIsNone(db.get_meta("schema_version"))


class TestAssetsDbLookup(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _setup_test_logging()
        cls.con, cls.path = _make_adb()
        cls.db = AssetsDb(cls.con)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        os.unlink(cls.path)

    def test_T02_get_asset_bekannte_url_liefert_record(self):
        """T02: get_asset() mit bekannter URL → AssetRecord mit Daten."""
        record = self.db.get_asset("/forum/img/avatars/42.png")
        self.assertIsNotNone(record)
        self.assertIsInstance(record, AssetRecord)
        self.assertTrue(record.available)
        self.assertEqual(record.data, bytes([0x89, 0x50, 0x4E, 0x47]))

    def test_T03_get_asset_null_daten_available_false(self):
        """T03: get_asset() mit NULL-Daten → available=False."""
        record = self.db.get_asset("/forum/img/avatars/null.jpg")
        self.assertIsNotNone(record)
        self.assertFalse(record.available)
        self.assertIsNone(record.data)

    def test_T04_get_asset_unbekannte_url_gibt_none(self):
        """T04: get_asset() mit unbekannter URL → None."""
        result = self.db.get_asset("/forum/img/avatars/nonexistent.png")
        self.assertIsNone(result)

    def test_T05_get_asset_mime_type_korrekt(self):
        """T05: get_asset() MIME-Type wird korrekt zurückgegeben."""
        record = self.db.get_asset("/forum/img/avatars/42.png")
        self.assertEqual(record.mime_type, "image/png")

    def test_T06_get_asset_fehlender_mime_type_fallback(self):
        """T06: get_asset() fehlender MIME-Type → application/octet-stream.
        
        Verwendet eine eigene Verbindung, da adb READ-ONLY (kein INSERT möglich).
        """
        path = tempfile.mktemp(suffix=".db")
        raw = sqlite3.connect(path)
        raw.execute("CREATE TABLE assets_meta (key TEXT PRIMARY KEY, value TEXT)")
        raw.execute(
            "CREATE TABLE assets (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "content_hash TEXT NOT NULL UNIQUE, data BLOB, mime_type TEXT, "
            "file_size INTEGER, source_note TEXT NOT NULL DEFAULT '')"
        )
        raw.execute(
            "CREATE TABLE asset_urls (url TEXT NOT NULL PRIMARY KEY, "
            "asset_id INTEGER NOT NULL, url_context TEXT NOT NULL DEFAULT 'unknown', "
            "page_id INTEGER, url_hash TEXT NOT NULL DEFAULT '')"
        )
        raw.execute(
            "INSERT INTO assets (content_hash, data, mime_type, file_size, source_note) "
            "VALUES (?, ?, NULL, 1, 'test')", ("nomime_t06", b"\xFF")
        )
        raw.execute(
            "INSERT INTO asset_urls (url, asset_id, url_context, url_hash) "
            "VALUES (?, 1, 'unknown', 'h99')", ("/forum/img/test/nomime.bin",)
        )
        raw.commit(); raw.close()
        try:
            con2 = sqlite3.connect(":memory:")
            con2.row_factory = sqlite3.Row
            uri = Path(path).as_uri() + "?mode=ro"
            con2.execute(f"ATTACH DATABASE '{uri}' AS adb")
            db2 = AssetsDb(con2)
            record = db2.get_asset("/forum/img/test/nomime.bin")
            self.assertIsNotNone(record)
            self.assertEqual(record.mime_type, "application/octet-stream")
            con2.close()
        finally:
            os.unlink(path)

    def test_T07_has_asset_bekannte_url_true(self):
        """T07: has_asset() bekannte URL → True."""
        self.assertTrue(self.db.has_asset("/forum/img/avatars/42.png"))

    def test_T08_has_asset_unbekannte_url_false(self):
        """T08: has_asset() unbekannte URL → False."""
        self.assertFalse(self.db.has_asset("/forum/img/avatars/nonexistent.png"))

    def test_T10_asset_count_korrekt(self):
        """T10: asset_count() gibt korrekte Anzahl zurück."""
        count = self.db.asset_count()
        self.assertGreaterEqual(count, 2)

    def test_T11_get_meta_schluessel(self):
        """T11: get_meta() bekannter Schlüssel wird zurückgegeben."""
        val = self.db.get_meta("schema_version")
        self.assertEqual(val, "1")


# ---------------------------------------------------------------------------
# T12–T14: AssetHandler Kaskaden-Tests
# ---------------------------------------------------------------------------

class TestAssetHandlerKaskade(unittest.TestCase):
    """
    Testet die Kaskade assets_<uid>.db → default.db → 404 im AssetHandler.
    DefaultDb und das Bundle werden gemockt, um Datenbankabhängigkeiten
    zu vermeiden.
    """

    @classmethod
    def setUpClass(cls):
        _setup_test_logging()

    def _make_handler_and_mock(self, assets_record, default_record):
        """
        Erstellt einen AssetHandler mit gemocktem Bundle.
        assets_record: was bundle.assets.get_asset() zurückgibt
        default_record: was bundle.default.get_asset() zurückgibt
        """
        from server.asset_handler import AssetHandler

        bundle = MagicMock()
        bundle.assets.get_asset.return_value = assets_record
        bundle.default.get_asset.return_value = default_record

        handler = AssetHandler(bundle)
        request_handler = MagicMock()

        return handler, request_handler, bundle

    def _make_asset_record(self, url, data=b"\x89PNG", mime="image/png"):
        return AssetRecord(url=url, data=data, mime_type=mime, file_size=len(data))

    def test_T12_assets_db_treffer_schlaegt_default(self):
        """T12: Kaskade — assets_<uid>.db-Treffer schlägt default.db-Treffer."""
        asset_rec   = self._make_asset_record("/forum/img/avatars/42.png", b"ASSETS_DATA", "image/png")
        default_rec = self._make_asset_record("/forum/img/avatars/42.png", b"DEFAULT_DATA", "image/png")

        handler, req_handler, bundle = self._make_handler_and_mock(asset_rec, default_rec)
        handler.handle(req_handler, "/forum/img/avatars/42.png")

        # send_response_body muss mit assets-Daten aufgerufen worden sein
        req_handler.send_response_body.assert_called_once_with(
            status=200, body=b"ASSETS_DATA", content_type="image/png"
        )
        # default.get_asset darf NICHT aufgerufen worden sein
        bundle.default.get_asset.assert_not_called()

    def test_T13_leere_assets_db_fallback_auf_default(self):
        """T13: Kaskade — leere assets_db fällt auf default.db zurück."""
        default_rec = self._make_asset_record("/forum/style/main.css", b"CSS_DATA", "text/css")

        handler, req_handler, bundle = self._make_handler_and_mock(None, default_rec)
        handler.handle(req_handler, "/forum/style/main.css")

        req_handler.send_response_body.assert_called_once_with(
            status=200, body=b"CSS_DATA", content_type="text/css"
        )

    def test_T14_beide_dbs_leer_404(self):
        """T14: beide DBs leer → HTTP 404."""
        handler, req_handler, _ = self._make_handler_and_mock(None, None)
        handler.handle(req_handler, "/forum/img/avatars/unknown.png")

        req_handler.send_response_body.assert_called_once_with(404, b"")


# ---------------------------------------------------------------------------
# T15: ConnectionManager — fehlende assets_<uid>.db → kein Absturz
# ---------------------------------------------------------------------------

class TestConnectionManagerOhneAssetsDb(unittest.TestCase):
    """
    Testet dass ConnectionManager startet ohne assets_<uid>.db.
    Verwendet minimale echte DBs für forensic/default/evidence.
    """

    @classmethod
    def setUpClass(cls):
        _setup_test_logging()

    def _make_minimal_forensic_db(self, path: str) -> None:
        """Erstellt eine forensic_<uid>.db mit Minimalschema."""
        con = sqlite3.connect(path)
        con.executescript("""
            CREATE TABLE pages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                url         TEXT NOT NULL,
                html_blob   BLOB,
                scraped_at  TEXT
            );
            CREATE TABLE forensic_meta (key TEXT PRIMARY KEY, value TEXT);
        """)
        con.commit()
        con.close()

    def _make_minimal_default_db(self, path: str) -> None:
        """Erstellt eine default.db mit Minimalschema."""
        con = sqlite3.connect(path)
        con.executescript("""
            CREATE TABLE default_meta   (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE default_assets (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                content_hash TEXT NOT NULL UNIQUE,
                data         BLOB,
                mime_type    TEXT,
                file_size    INTEGER
            );
            CREATE TABLE default_urls (
                url      TEXT NOT NULL PRIMARY KEY,
                asset_id INTEGER NOT NULL REFERENCES default_assets(id),
                url_hash TEXT NOT NULL DEFAULT ''
            );
        """)
        con.commit()
        con.close()

    def test_T15_fehlende_assets_db_kein_absturz(self):
        """T15: ConnectionManager öffnet ohne assets_<uid>.db — kein Absturz."""
        import sys
        from unittest.mock import patch, MagicMock

        # Minimale echte DBs anlegen
        tmp = tempfile.mkdtemp()
        forensic_path = os.path.join(tmp, "forensic_99.db")
        default_path  = os.path.join(tmp, "default.db")
        evidence_path = os.path.join(tmp, "evidence_99.db")
        assets_path   = os.path.join(tmp, "assets_99.db")  # NICHT anlegen

        self._make_minimal_forensic_db(forensic_path)
        self._make_minimal_default_db(default_path)
        # evidence_db wird beim ersten Öffnen angelegt

        # ResolvedContext mocken
        ctx = MagicMock()
        ctx.mode          = "cli"
        ctx.user_id       = 99
        ctx.forensic_db   = Path(forensic_path)
        ctx.default_db    = Path(default_path)
        ctx.evidence_db   = Path(evidence_path)
        ctx.coordinator_db = Path(os.path.join(tmp, "coordinator.db"))  # nicht vorhanden — OK
        ctx.assets_db     = Path(assets_path)   # NICHT vorhanden — soll kein Fehler sein

        config = MagicMock()
        # Build 408: Der bisherige Blanko-Mock ('get' liefert IMMER "memory")
        # bildete den echten ConfigLoader nicht ab — der liefert fuer unbekannte
        # Schluessel den uebergebenen Default zurueck. Seit die Journalmodus-Weiche
        # 'db.journal_mode' abfragt (und unzulaessige Werte bewusst NICHT still
        # auf den Default biegt), fiel diese Ungenauigkeit auf. Der Mock verhaelt
        # sich jetzt wie ConfigLoader.get(key, default).
        config.get.side_effect = (
            lambda key, default=None: {"support.temp_db": "memory"}.get(key, default)
        )

        from db.connection_manager import ConnectionManager
        manager = ConnectionManager(ctx, config)

        # Muss ohne Exception öffnen
        bundle = manager.open()
        self.assertIsNotNone(bundle)
        self.assertIsNotNone(bundle.assets)
        # assets_db nicht verfügbar — is_available muss False sein
        self.assertFalse(bundle.assets.is_available)
        # Lookups müssen trotzdem funktionieren (None / False)
        self.assertIsNone(bundle.assets.get_asset("/forum/img/avatars/1.png"))
        self.assertFalse(bundle.assets.has_asset("/forum/img/avatars/1.png"))

        bundle.close()


# ---------------------------------------------------------------------------
# T16–T21: URL-Normalisierung mit forum_base_url (Build 018)
# ---------------------------------------------------------------------------

class TestAssetsDbForumBaseUrl(unittest.TestCase):
    """T16–T21: AssetsDb.get_asset() und has_asset() mit forum_base_url."""

    def setUp(self):
        _setup_test_logging()
        # DB mit Onion-URL als Schlüssel anlegen
        path = tempfile.mktemp(suffix=".db")
        raw = sqlite3.connect(path)
        raw.executescript("""
            CREATE TABLE assets_meta (key TEXT NOT NULL PRIMARY KEY, value TEXT);
            CREATE TABLE assets (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                content_hash TEXT NOT NULL UNIQUE,
                data         BLOB,
                mime_type    TEXT,
                file_size    INTEGER,
                source_note  TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE asset_urls (
                url         TEXT NOT NULL PRIMARY KEY,
                asset_id    INTEGER NOT NULL REFERENCES assets(id),
                url_context TEXT NOT NULL DEFAULT 'unknown',
                page_id     INTEGER,
                url_hash    TEXT NOT NULL DEFAULT ''
            );
            INSERT INTO assets (content_hash, data, mime_type, file_size, source_note)
                VALUES ('abc', X'89504E47', 'image/png', 4, 'test');
            INSERT INTO asset_urls (url, asset_id, url_context, url_hash)
                VALUES (
                    'http://alice4nonion.onion/forum/img/test.png',
                    1, 'static', 'h1'
                );
        """)
        raw.commit()
        raw.close()
        self._path = path
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        uri = Path(path).as_uri() + "?mode=ro"
        con.execute(f"ATTACH DATABASE '{uri}' AS adb")
        self._con = con

    def tearDown(self):
        self._con.close()
        Path(self._path).unlink(missing_ok=True)
        reset_for_testing()

    def test_T16_ohne_base_url_kein_treffer(self):
        """T16: Ohne forum_base_url findet get_asset() Onion-URL nicht über Pfad."""
        adb = AssetsDb(self._con, forum_base_url=None)
        result = adb.get_asset("/forum/img/test.png")
        self.assertIsNone(result)

    def test_T17_mit_base_url_treffer(self):
        """T17: Mit forum_base_url wird Pfad korrekt zu Onion-URL expandiert."""
        adb = AssetsDb(
            self._con,
            forum_base_url="http://alice4nonion.onion"
        )
        result = adb.get_asset("/forum/img/test.png")
        self.assertIsNotNone(result)
        self.assertTrue(result.available)
        self.assertEqual(result.mime_type, "image/png")

    def test_T18_trailing_slash_wird_entfernt(self):
        """T18: Abschließender Slash in forum_base_url wird korrekt entfernt."""
        adb = AssetsDb(
            self._con,
            forum_base_url="http://alice4nonion.onion/"  # Slash am Ende
        )
        result = adb.get_asset("/forum/img/test.png")
        self.assertIsNotNone(result)

    def test_T19_has_asset_mit_base_url(self):
        """T19: has_asset() findet Eintrag mit forum_base_url."""
        adb = AssetsDb(
            self._con,
            forum_base_url="http://alice4nonion.onion"
        )
        self.assertTrue(adb.has_asset("/forum/img/test.png"))

    def test_T20_has_asset_ohne_base_url(self):
        """T20: has_asset() findet keinen Eintrag ohne forum_base_url."""
        adb = AssetsDb(self._con, forum_base_url=None)
        self.assertFalse(adb.has_asset("/forum/img/test.png"))

    def test_T21_unbekannter_pfad_gibt_none(self):
        """T21: Pfad der nicht in asset_urls liegt → None auch mit base_url."""
        adb = AssetsDb(
            self._con,
            forum_base_url="http://alice4nonion.onion"
        )
        result = adb.get_asset("/forum/img/does_not_exist.png")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)

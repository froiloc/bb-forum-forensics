# =============================================================================
# tests/test_default_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite für db/default_db.py
#
# T01 — Initialisierung: ddb korrekt angebunden
# T02 — get_asset(): bekannte URL liefert AssetRecord mit Daten
# T03 — get_asset(): bekannte URL mit NULL-Daten → available=False
# T04 — get_asset(): unbekannte URL gibt None zurück
# T05 — get_asset(): MIME-Type wird korrekt zurückgegeben
# T06 — get_asset(): fehlender MIME-Type → application/octet-stream
# T07 — has_asset(): bekannte URL gibt True zurück
# T08 — has_asset(): unbekannte URL gibt False zurück
# T09 — get_meta(): bekannter Schlüssel zurückgegeben
# T10 — asset_count(): korrekte Anzahl
#
# Version: v0.1.0 · Build: 007 · 2026-04-10
# =============================================================================

import sys, os, sqlite3, tempfile, textwrap, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import setup_logging, reset_for_testing
from core.config_loader import ConfigLoader
from db.default_db import DefaultDb, AssetRecord


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
        """))
    setup_logging(ConfigLoader(config_path=config_path))


def _make_ddb() -> tuple[sqlite3.Connection, str]:
    """Erstellt eine temporäre default.db mit Testdaten."""
    path = tempfile.mktemp(suffix=".db")
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE default_meta   (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE default_assets (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT NOT NULL UNIQUE,
            data         BLOB,
            mime_type    TEXT,
            file_size    INTEGER,
            source_note  TEXT NOT NULL,
            fetched_at   INTEGER
        );
        CREATE TABLE default_urls (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            url        TEXT NOT NULL UNIQUE,
            url_hash   TEXT NOT NULL,
            asset_id   INTEGER REFERENCES default_assets(id),
            url_context TEXT NOT NULL,
            http_status INTEGER,
            added_at   INTEGER NOT NULL
        );
        INSERT INTO default_meta VALUES ('schema_version', '1');
        INSERT INTO default_assets (content_hash, data, mime_type, file_size, source_note)
            VALUES ('hash_css', X'626F6479207B7D', 'text/css', 7, 'test');
        INSERT INTO default_assets (content_hash, data, mime_type, file_size, source_note)
            VALUES ('hash_null', NULL, 'image/png', NULL, 'test_null');
        INSERT INTO default_assets (content_hash, data, mime_type, file_size, source_note)
            VALUES ('hash_nomime', X'FF', NULL, 1, 'test_nomime');
        INSERT INTO default_urls (url, url_hash, asset_id, url_context, http_status, added_at)
            VALUES ('/forum/style/main.css', 'h1', 1, 'style', 200, 0);
        INSERT INTO default_urls (url, url_hash, asset_id, url_context, http_status, added_at)
            VALUES ('/forum/img/logo.png', 'h2', 2, 'image', 200, 0);
        INSERT INTO default_urls (url, url_hash, asset_id, url_context, http_status, added_at)
            VALUES ('/forum/img/icon.gif', 'h3', 3, 'image', 200, 0);
    """)
    con.commit()
    con.close()
    return path


def _attach(ddb_path: str) -> sqlite3.Connection:
    main = sqlite3.connect(":memory:")
    main.row_factory = sqlite3.Row
    main.execute(f"ATTACH DATABASE '{ddb_path}' AS ddb")
    return main


class TestDefaultDb(unittest.TestCase):
    def setUp(self):
        _setup_test_logging()
        self.ddb_path = _make_ddb()
        self.con = _attach(self.ddb_path)
        self.ddb = DefaultDb(self.con)

    def tearDown(self):
        self.con.close()
        reset_for_testing()
        try: os.unlink(self.ddb_path)
        except OSError: pass

    def test_T01_init(self):
        """T01: DefaultDb.__init__() erkennt korrekt angebundene ddb."""
        self.assertIsNotNone(self.ddb)

    def test_T02_get_asset_mit_daten(self):
        """T02: Bekannte URL liefert AssetRecord mit Daten."""
        asset = self.ddb.get_asset("/forum/style/main.css")
        self.assertIsNotNone(asset)
        self.assertIsInstance(asset, AssetRecord)
        self.assertTrue(asset.available)
        self.assertIsNotNone(asset.data)

    def test_T03_get_asset_null_daten(self):
        """T03: Bekannte URL mit NULL-Daten → available=False."""
        asset = self.ddb.get_asset("/forum/img/logo.png")
        self.assertIsNotNone(asset)
        self.assertFalse(asset.available)
        self.assertIsNone(asset.data)

    def test_T04_get_asset_unbekannt(self):
        """T04: Unbekannte URL gibt None zurück."""
        self.assertIsNone(self.ddb.get_asset("/forum/nicht/vorhanden.css"))

    def test_T05_mime_type(self):
        """T05: MIME-Type wird korrekt zurückgegeben."""
        asset = self.ddb.get_asset("/forum/style/main.css")
        self.assertEqual(asset.mime_type, "text/css")

    def test_T06_fehlender_mime_type_default(self):
        """T06: Fehlender MIME-Type → 'application/octet-stream'."""
        asset = self.ddb.get_asset("/forum/img/icon.gif")
        self.assertEqual(asset.mime_type, "application/octet-stream")

    def test_T07_has_asset_bekannt(self):
        """T07: has_asset() gibt True für bekannte URL zurück."""
        self.assertTrue(self.ddb.has_asset("/forum/style/main.css"))

    def test_T08_has_asset_unbekannt(self):
        """T08: has_asset() gibt False für unbekannte URL zurück."""
        self.assertFalse(self.ddb.has_asset("/forum/unbekannt.css"))

    def test_T09_get_meta(self):
        """T09: get_meta() gibt bekannten Schlüssel zurück."""
        self.assertEqual(self.ddb.get_meta("schema_version"), "1")
        self.assertIsNone(self.ddb.get_meta("nicht_vorhanden"))

    def test_T10_asset_count(self):
        """T10: asset_count() gibt korrekte Anzahl zurück."""
        self.assertEqual(self.ddb.asset_count(), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)

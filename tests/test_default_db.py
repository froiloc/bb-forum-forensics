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


def _make_ddb_with_known_users(identified_ids: list[int] | None = None) -> str:
    """
    Hilfsfunktion: Erstellt temporäre default.db mit known_users,
    known_aliases und optional identified_users.
    default_assets wird angelegt damit DefaultDb._verify_attachment() nicht scheitert.
    Beleg: Projektgespräch 2026-05-16 (Build 198).
    """
    path = tempfile.mktemp(suffix=".db")
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE default_assets (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT NOT NULL UNIQUE,
            data         BLOB,
            mime_type    TEXT,
            file_size    INTEGER,
            source_note  TEXT NOT NULL,
            fetched_at   INTEGER
        );
        CREATE TABLE known_users (
            user_id  INTEGER PRIMARY KEY,
            username TEXT    NOT NULL
        );
        CREATE TABLE known_aliases (
            alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  INTEGER NOT NULL,
            name     TEXT    NOT NULL
        );
        INSERT INTO known_users VALUES (100, 'TestNutzer');
        INSERT INTO known_users VALUES (200, 'AndererNutzer');
        INSERT INTO known_users VALUES (300, 'DritterNutzer');
        INSERT INTO known_aliases VALUES (NULL, 200, 'Alias200');
    """)
    if identified_ids is not None:
        con.execute(
            "CREATE TABLE identified_users (user_id INTEGER PRIMARY KEY)"
        )
        for uid in identified_ids:
            con.execute(
                "INSERT INTO identified_users VALUES (?)", (uid,)
            )
    con.commit()
    con.close()
    return path


def _attach_ku(ddb_path: str) -> sqlite3.Connection:
    """Öffnet :memory: und attachiert ddb_path als 'ddb'."""
    main = sqlite3.connect(":memory:")
    main.row_factory = sqlite3.Row
    main.execute(f"ATTACH DATABASE '{ddb_path}' AS ddb")
    return main


class TestSearchKnownUsersIdentified(unittest.TestCase):
    """
    Tests für search_known_users() mit is_identified-Flag.
    Build 198, 2026-05-16: Abgleich gegen identified_users in default.db.
    """

    def setUp(self):
        _setup_test_logging()

    def tearDown(self):
        reset_for_testing()

    def test_T11_is_identified_false_ohne_tabelle(self):
        """
        T11: is_identified=False für alle Treffer wenn identified_users fehlt.
        Graceful degradation — kein Fehler, kein Absturz.
        Beleg: Build 198, Projektgespräch 2026-05-16.
        """
        path = _make_ddb_with_known_users(identified_ids=None)
        con = _attach_ku(path)
        ddb = DefaultDb(con)
        results = ddb.search_known_users("TestNutzer")
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["is_identified"])
        con.close()
        os.unlink(path)

    def test_T12_is_identified_true(self):
        """
        T12: is_identified=True wenn user_id in identified_users vorhanden.
        Beleg: Build 198, Projektgespräch 2026-05-16.
        """
        path = _make_ddb_with_known_users(identified_ids=[100])
        con = _attach_ku(path)
        ddb = DefaultDb(con)
        results = ddb.search_known_users("TestNutzer")
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["is_identified"])
        con.close()
        os.unlink(path)

    def test_T13_is_identified_false_nicht_in_tabelle(self):
        """
        T13: is_identified=False wenn user_id NICHT in identified_users.
        Beleg: Build 198, Projektgespräch 2026-05-16.
        """
        path = _make_ddb_with_known_users(identified_ids=[999])  # andere ID
        con = _attach_ku(path)
        ddb = DefaultDb(con)
        results = ddb.search_known_users("TestNutzer")
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["is_identified"])
        con.close()
        os.unlink(path)

    def test_T14_gemischte_treffer(self):
        """
        T14: Treffer-Liste mit identifizierten und nicht-identifizierten Nutzern.
        TestNutzer (100) ist identifiziert, AndererNutzer (200) nicht.
        Beleg: Build 198, Projektgespräch 2026-05-16.
        """
        path = _make_ddb_with_known_users(identified_ids=[100])
        con = _attach_ku(path)
        ddb = DefaultDb(con)
        results = ddb.search_known_users("Nutzer")
        self.assertGreaterEqual(len(results), 2)
        by_uid = {r["user_id"]: r for r in results}
        self.assertTrue(by_uid[100]["is_identified"])
        self.assertFalse(by_uid[200]["is_identified"])
        con.close()
        os.unlink(path)

    def test_T15_alias_treffer_is_identified(self):
        """
        T15: is_identified wird auch für Alias-Treffer korrekt gesetzt.
        AndererNutzer (200) hat Alias 'Alias200' und ist identifiziert.
        Beleg: Build 198, Projektgespräch 2026-05-16.
        """
        path = _make_ddb_with_known_users(identified_ids=[200])
        con = _attach_ku(path)
        ddb = DefaultDb(con)
        # Suche über Alias — direkt nach "Alias200"
        results = ddb.search_known_users("Alias200")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["user_id"], 200)
        self.assertEqual(results[0]["matched_alias"], "Alias200")
        self.assertTrue(results[0]["is_identified"])
        con.close()
        os.unlink(path)

    def test_T16_zu_kurzer_suchbegriff(self):
        """
        T16: Suchbegriff < 4 Zeichen → leere Liste (keine Änderung durch Build 198).
        Beleg: Build 198 — Sicherheitsnetz unverändert.
        """
        path = _make_ddb_with_known_users(identified_ids=[100])
        con = _attach_ku(path)
        ddb = DefaultDb(con)
        results = ddb.search_known_users("ab")
        self.assertEqual(results, [])
        con.close()
        os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)

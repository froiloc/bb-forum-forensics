# =============================================================================
# tests/test_forensic_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite für db/forensic_db.py
#
# Strategie:
#   Alle Tests arbeiten mit einer echten In-Memory-SQLite3-Datenbank, die
#   das vollständige forensic_db-Schema enthält. fdb wird per ATTACH an eine
#   Haupt-In-Memory-DB gebunden, exakt wie connection_manager.py es tun wird.
#
# Abgedeckte Testfälle:
#   T01 — Initialisierung: blob_lookup-View wird angelegt
#   T02 — get_page(): direkte URL (url_canonical) wird gefunden
#   T03 — get_page(): Alias-URL (page_aliases.url_raw) wird gefunden
#   T04 — get_page(): unbekannte URL gibt None zurück
#   T05 — get_page(): html IS NULL → PageRecord.fetch_failed = True
#   T06 — get_page(): scrape_context wird korrekt zurückgegeben
#   T07 — get_page_by_id(): Seite per ID gefunden
#   T08 — get_page_by_id(): unbekannte ID gibt None zurück
#   T09 — resolve_post_alias(): bekannte post_id aufgelöst
#   T10 — resolve_post_alias(): unbekannte post_id gibt None zurück
#   T11 — resolve_pm_alias(): bekannte pm_post_id aufgelöst
#   T12 — resolve_pm_alias(): unbekannte pm_post_id gibt None zurück
#   T13 — resolve_notify_alias(): bekannte notify_id aufgelöst
#   T14 — resolve_notify_alias(): unbekannte notify_id gibt None zurück
#   T15 — get_meta(): bekannter Schlüssel zurückgegeben
#   T16 — get_meta(): unbekannter Schlüssel gibt None zurück
#   T17 — get_scrape_context(): korrekt ohne BLOB zu laden
#   T18 — page_count(): korrekte Anzahl
#   T19 — ForensicDb ist READ-ONLY: kein Schreiben in fdb möglich
#   T20 — blob_lookup vereinheitlicht: url_canonical und url_raw beide abrufbar
#
# Version: v0.1.0 · Build: 028 · 2026-04-15
# =============================================================================

import sys
import os
import sqlite3
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import setup_logging, reset_for_testing
from core.config_loader import ConfigLoader
from db.forensic_db import ForensicDb, PageRecord, PostAliasRecord, PmAliasRecord, NotifyAliasRecord


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _setup_test_logging():
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
              coordinator_db: "./coordinator.db"
              forensic_db_dir: "./forensic/"
              default_db: "./default.db"
              evidence_db_dir: "./evidence/"
        """))
    cfg = ConfigLoader(config_path=config_path)
    setup_logging(cfg)


def _create_fdb_in_memory() -> sqlite3.Connection:
    """
    Erstellt eine In-Memory-forensic_db mit vollständigem Schema und
    Testdaten. Gibt sie als anonyme Verbindung zurück (für ATTACH geeignet).

    Da SQLite In-Memory-DBs nicht per ATTACH mit :memory: verbunden werden
    können, wird eine temporäre Datei verwendet.
    """
    tmp = tempfile.mktemp(suffix=".db")
    con = sqlite3.connect(tmp)
    con.executescript("""
        CREATE TABLE forensic_meta (
            key   TEXT NOT NULL PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE pages (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            url_canonical  TEXT NOT NULL,
            html           BLOB,
            fetched_at     INTEGER NOT NULL,
            http_status    INTEGER NOT NULL,
            scrape_context TEXT NOT NULL DEFAULT 'user',
            method         TEXT NOT NULL DEFAULT 'GET',
            UNIQUE(url_canonical, method)
        );
        CREATE TABLE page_aliases (
            url_raw TEXT NOT NULL PRIMARY KEY,
            page_id INTEGER NOT NULL REFERENCES pages(id)
        );
        CREATE TABLE post_aliases (
            post_id  INTEGER NOT NULL PRIMARY KEY,
            topic_id INTEGER NOT NULL,
            forum_id INTEGER NOT NULL
        );
        CREATE TABLE pm_aliases (
            pm_post_id  INTEGER NOT NULL PRIMARY KEY,
            pm_topic_id INTEGER NOT NULL
        );
        CREATE TABLE notify_aliases (
            notify_id INTEGER NOT NULL PRIMARY KEY,
            post_id   INTEGER NOT NULL
        );

        INSERT INTO forensic_meta VALUES ('schema_version', '1');
        INSERT INTO forensic_meta VALUES ('user_id', '42');
        INSERT INTO forensic_meta VALUES ('username', 'testnutzer');
        INSERT INTO forensic_meta VALUES ('sha256', 'abc123');

        INSERT INTO pages (url_canonical, html, fetched_at, http_status, scrape_context, method)
        VALUES
            ('/forum/viewtopic.php?id=100',
             X'3C68746D6C3E546F706963313C2F68746D6C3E',
             1700000000, 200, 'user', 'GET'),
            ('/forum/viewtopic.php?id=200',
             NULL,
             1700000001, 403, 'investigator', 'GET'),
            ('/forum/profile.php?id=42',
             X'3C68746D6C3E50726F66696C653C2F68746D6C3E',
             1700000002, 200, 'user', 'GET'),
            ('/forum/viewtopic.php?id=300',
             X'3C68746D6C3E546F706963333C2F68746D6C3E',
             1700000003, 200, 'actor:99', 'GET');

        INSERT INTO page_aliases VALUES
            ('/forum/viewtopic.php?id=100#p12345', 1),
            ('/forum/viewtopic.php?pid=12345#p12345', 1);

        INSERT INTO post_aliases VALUES
            (12345, 100, 5),
            (67890, 200, 7);

        INSERT INTO pm_aliases VALUES
            (555, 10),
            (556, 10);

        INSERT INTO notify_aliases VALUES
            (9001, 12345),
            (9002, 67890);
    """)
    con.commit()
    con.close()
    return tmp   # Pfad zurückgeben für ATTACH


def _make_attached_connection(fdb_path: str) -> sqlite3.Connection:
    """
    Erstellt eine In-Memory-Haupt-DB und bindet fdb per ATTACH an.
    Entspricht dem Verhalten von connection_manager.py.
    """
    # Haupt-DB: In-Memory evidence_db (leer, nur als Träger für TEMP VIEW)
    main_con = sqlite3.connect(":memory:")
    main_con.row_factory = sqlite3.Row
    main_con.execute(f"ATTACH DATABASE '{fdb_path}' AS fdb")
    main_con.commit()
    return main_con


# ---------------------------------------------------------------------------
# Testklassen
# ---------------------------------------------------------------------------

class TestForensicDbInit(unittest.TestCase):
    """T01: Initialisierung"""

    def setUp(self):
        _setup_test_logging()
        self.fdb_path = _create_fdb_in_memory()
        self.con = _make_attached_connection(self.fdb_path)

    def tearDown(self):
        self.con.close()
        reset_for_testing()
        try:
            os.unlink(self.fdb_path)
        except OSError:
            pass

    def test_T01_blob_lookup_view_angelegt(self):
        """T01: ForensicDb.__init__() legt blob_lookup-View an."""
        fdb = ForensicDb(self.con)
        # View muss abfragbar sein
        row = self.con.execute(
            "SELECT COUNT(*) FROM blob_lookup"
        ).fetchone()
        self.assertIsNotNone(row)
        # 4 Seiten + 2 Aliases = 6 Einträge im View
        self.assertEqual(row[0], 6)


class TestForensicDbGetPage(unittest.TestCase):
    """T02–T06: get_page()"""

    def setUp(self):
        _setup_test_logging()
        self.fdb_path = _create_fdb_in_memory()
        self.con = _make_attached_connection(self.fdb_path)
        self.fdb = ForensicDb(self.con)

    def tearDown(self):
        self.con.close()
        reset_for_testing()
        try:
            os.unlink(self.fdb_path)
        except OSError:
            pass

    def test_T02_direkte_url(self):
        """T02: Direkte URL (url_canonical) wird korrekt gefunden."""
        page = self.fdb.get_page("/forum/viewtopic.php?id=100")
        self.assertIsNotNone(page)
        self.assertIsInstance(page, PageRecord)
        self.assertEqual(page.page_id, 1)
        self.assertEqual(page.http_status, 200)
        self.assertFalse(page.fetch_failed)

    def test_T03_alias_url(self):
        """T03: Alias-URL (page_aliases.url_raw) wird auf korrekte Seite aufgelöst."""
        page = self.fdb.get_page("/forum/viewtopic.php?id=100#p12345")
        self.assertIsNotNone(page)
        # Muss auf dieselbe Seite wie die direkte URL zeigen
        self.assertEqual(page.page_id, 1)

    def test_T04_unbekannte_url(self):
        """T04: Unbekannte URL gibt None zurück."""
        page = self.fdb.get_page("/forum/viewtopic.php?id=9999")
        self.assertIsNone(page)

    def test_T05_html_null_fetch_failed(self):
        """T05: html IS NULL → PageRecord.fetch_failed = True."""
        page = self.fdb.get_page("/forum/viewtopic.php?id=200")
        self.assertIsNotNone(page)
        self.assertIsNone(page.html)
        self.assertTrue(page.fetch_failed)
        self.assertEqual(page.http_status, 403)

    def test_T06_scrape_context(self):
        """T06: scrape_context wird korrekt aus der DB übernommen."""
        page_user = self.fdb.get_page("/forum/viewtopic.php?id=100")
        self.assertEqual(page_user.scrape_context, "user")

        page_inv = self.fdb.get_page("/forum/viewtopic.php?id=200")
        self.assertEqual(page_inv.scrape_context, "investigator")

        page_actor = self.fdb.get_page("/forum/viewtopic.php?id=300")
        self.assertEqual(page_actor.scrape_context, "actor:99")


class TestForensicDbGetPageById(unittest.TestCase):
    """T07–T08: get_page_by_id()"""

    def setUp(self):
        _setup_test_logging()
        self.fdb_path = _create_fdb_in_memory()
        self.con = _make_attached_connection(self.fdb_path)
        self.fdb = ForensicDb(self.con)

    def tearDown(self):
        self.con.close()
        reset_for_testing()
        try:
            os.unlink(self.fdb_path)
        except OSError:
            pass

    def test_T07_bekannte_id(self):
        """T07: Bekannte page_id gibt korrekten PageRecord zurück."""
        page = self.fdb.get_page_by_id(1)
        self.assertIsNotNone(page)
        self.assertEqual(page.url, "/forum/viewtopic.php?id=100")

    def test_T08_unbekannte_id(self):
        """T08: Unbekannte page_id gibt None zurück."""
        page = self.fdb.get_page_by_id(9999)
        self.assertIsNone(page)


class TestForensicDbAliases(unittest.TestCase):
    """T09–T14: Alias-Auflösungen"""

    def setUp(self):
        _setup_test_logging()
        self.fdb_path = _create_fdb_in_memory()
        self.con = _make_attached_connection(self.fdb_path)
        self.fdb = ForensicDb(self.con)

    def tearDown(self):
        self.con.close()
        reset_for_testing()
        try:
            os.unlink(self.fdb_path)
        except OSError:
            pass

    def test_T09_post_alias_bekannt(self):
        """T09: Bekannte post_id wird auf topic_id und forum_id aufgelöst."""
        result = self.fdb.resolve_post_alias(12345)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, PostAliasRecord)
        self.assertEqual(result.post_id, 12345)
        self.assertEqual(result.topic_id, 100)
        self.assertEqual(result.forum_id, 5)

    def test_T10_post_alias_unbekannt(self):
        """T10: Unbekannte post_id gibt None zurück."""
        result = self.fdb.resolve_post_alias(99999)
        self.assertIsNone(result)

    def test_T11_pm_alias_bekannt(self):
        """T11: Bekannte pm_post_id wird auf pm_topic_id aufgelöst."""
        result = self.fdb.resolve_pm_alias(555)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, PmAliasRecord)
        self.assertEqual(result.pm_post_id, 555)
        self.assertEqual(result.pm_topic_id, 10)

    def test_T12_pm_alias_unbekannt(self):
        """T12: Unbekannte pm_post_id gibt None zurück."""
        result = self.fdb.resolve_pm_alias(99999)
        self.assertIsNone(result)

    def test_T13_notify_alias_bekannt(self):
        """T13: Bekannte notify_id wird auf post_id aufgelöst."""
        result = self.fdb.resolve_notify_alias(9001)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, NotifyAliasRecord)
        self.assertEqual(result.notify_id, 9001)
        self.assertEqual(result.post_id, 12345)

    def test_T14_notify_alias_unbekannt(self):
        """T14: Unbekannte notify_id gibt None zurück."""
        result = self.fdb.resolve_notify_alias(99999)
        self.assertIsNone(result)


class TestForensicDbMeta(unittest.TestCase):
    """T15–T18: Metadaten und Hilfsmethoden"""

    def setUp(self):
        _setup_test_logging()
        self.fdb_path = _create_fdb_in_memory()
        self.con = _make_attached_connection(self.fdb_path)
        self.fdb = ForensicDb(self.con)

    def tearDown(self):
        self.con.close()
        reset_for_testing()
        try:
            os.unlink(self.fdb_path)
        except OSError:
            pass

    def test_T15_get_meta_bekannt(self):
        """T15: Bekannter Schlüssel aus forensic_meta wird zurückgegeben."""
        self.assertEqual(self.fdb.get_meta("user_id"), "42")
        self.assertEqual(self.fdb.get_meta("username"), "testnutzer")
        self.assertEqual(self.fdb.get_meta("schema_version"), "1")

    def test_T16_get_meta_unbekannt(self):
        """T16: Unbekannter Schlüssel gibt None zurück."""
        self.assertIsNone(self.fdb.get_meta("nicht_vorhanden"))

    def test_T17_get_scrape_context(self):
        """T17: get_scrape_context() gibt Kontext zurück ohne BLOB zu laden."""
        ctx = self.fdb.get_scrape_context("/forum/viewtopic.php?id=200")
        self.assertEqual(ctx, "investigator")
        # Unbekannte URL
        ctx2 = self.fdb.get_scrape_context("/forum/viewtopic.php?id=9999")
        self.assertIsNone(ctx2)

    def test_T18_page_count(self):
        """T18: page_count() gibt korrekte Anzahl der Seiten zurück."""
        count = self.fdb.page_count()
        self.assertEqual(count, 4)  # 4 Einträge in pages-Tabelle


class TestForensicDbReadOnly(unittest.TestCase):
    """T19–T20: READ-ONLY und View-Vollständigkeit"""

    def setUp(self):
        _setup_test_logging()
        self.fdb_path = _create_fdb_in_memory()
        self.con = _make_attached_connection(self.fdb_path)
        self.fdb = ForensicDb(self.con)

    def tearDown(self):
        self.con.close()
        reset_for_testing()
        try:
            os.unlink(self.fdb_path)
        except OSError:
            pass

    def test_T19_kein_schreiben_in_fdb(self):
        """T19: ForensicDb enthält keine Schreiboperationen auf fdb.
        Erlaubt sind: CREATE TEMP VIEW und DROP VIEW IF EXISTS blob_lookup
        (beide operieren auf dem TEMP-Schema, nicht auf fdb)."""
        import inspect
        source = inspect.getsource(type(self.fdb))
        forbidden = ["INSERT", "UPDATE", "DELETE", "CREATE TABLE"]
        for stmt in forbidden:
            if stmt == "CREATE TABLE":
                self.assertNotIn(stmt + " ", source,
                    f"ForensicDb enthält '{stmt}' — Schreiboperation verboten")
            else:
                self.assertNotIn(stmt, source,
                    f"ForensicDb enthält '{stmt}' — Schreiboperation verboten")
        # DROP ist nur für TEMP VIEW erlaubt — nicht für fdb-Tabellen
        self.assertNotIn("DROP TABLE", source,
            "ForensicDb enthält 'DROP TABLE' — Schreiboperation verboten")
        self.assertNotIn("DROP INDEX", source,
            "ForensicDb enthält 'DROP INDEX' — Schreiboperation verboten")
        # DROP VIEW IF EXISTS blob_lookup ist erlaubt (TEMP-Schema)
        self.assertIn("DROP VIEW IF EXISTS blob_lookup", source)

    def test_T20_blob_lookup_beide_quellen(self):
        """T20: blob_lookup liefert sowohl url_canonical als auch url_raw-Treffer.
        canonical_url ist immer pages.url_canonical, url ist die gesuchte URL."""
        # Direkte URL
        page_direct = self.fdb.get_page("/forum/viewtopic.php?id=100")
        self.assertIsNotNone(page_direct)
        # Bei direktem Treffer: url == canonical_url
        self.assertEqual(page_direct.url, page_direct.canonical_url)

        # Alias-URL (url_raw aus page_aliases)
        page_alias1 = self.fdb.get_page("/forum/viewtopic.php?id=100#p12345")
        page_alias2 = self.fdb.get_page("/forum/viewtopic.php?pid=12345#p12345")

        self.assertIsNotNone(page_alias1)
        self.assertIsNotNone(page_alias2)

        # Alle drei zeigen auf dieselbe Seite
        self.assertEqual(page_direct.page_id, page_alias1.page_id)
        self.assertEqual(page_direct.page_id, page_alias2.page_id)

        # Bei Alias-Treffer: url = url_raw, canonical_url = pages.url_canonical
        self.assertEqual(page_alias1.url, "/forum/viewtopic.php?id=100#p12345")
        self.assertEqual(page_alias1.canonical_url, page_direct.canonical_url)

        # Inhalt ist identisch
        self.assertEqual(page_direct.html, page_alias1.html)


class TestForensicDbForumBaseUrl(unittest.TestCase):
    """T21–T25: ForensicDb.get_forum_base_url() (Build 018)"""

    def setUp(self):
        _setup_test_logging()
        self.fdb_path = _create_fdb_in_memory()
        self.con = _make_attached_connection(self.fdb_path)
        self.fdb = ForensicDb(self.con)

    def tearDown(self):
        self.con.close()
        reset_for_testing()
        try:
            os.unlink(self.fdb_path)
        except OSError:
            pass

    def _set_meta(self, key: str, value: str) -> None:
        """Schreibt einen forensic_meta-Eintrag direkt in die Test-DB."""
        raw = sqlite3.connect(self.fdb_path)
        raw.execute(
            "INSERT OR REPLACE INTO forensic_meta (key, value) VALUES (?, ?)",
            (key, value),
        )
        raw.commit()
        raw.close()

    def test_T21_beide_felder_gesetzt(self):
        """T21: protocol + domainname → vollständige Basis-URL."""
        self._set_meta("protocol", "http")
        self._set_meta("domainname", "alice4nonion.onion")
        result = self.fdb.get_forum_base_url()
        self.assertEqual(result, "http://alice4nonion.onion")

    def test_T22_fehlendes_protocol(self):
        """T22: Fehlt 'protocol' → None."""
        self._set_meta("domainname", "alice4nonion.onion")
        result = self.fdb.get_forum_base_url()
        self.assertIsNone(result)

    def test_T23_fehlendes_domainname(self):
        """T23: Fehlt 'domainname' → None."""
        self._set_meta("protocol", "http")
        result = self.fdb.get_forum_base_url()
        self.assertIsNone(result)

    def test_T24_beide_felder_fehlen(self):
        """T24: Fehlen beide Felder → None."""
        result = self.fdb.get_forum_base_url()
        self.assertIsNone(result)

    def test_T25_https_protokoll(self):
        """T25: protocol='https' wird korrekt zusammengesetzt."""
        self._set_meta("protocol", "https")
        self._set_meta("domainname", "secure.example.onion")
        result = self.fdb.get_forum_base_url()
        self.assertEqual(result, "https://secure.example.onion")


class TestForensicDbBlobLookupOnionPrefix(unittest.TestCase):
    """T26–T28: blob_lookup-View entfernt Onion-Präfix aus url_canonical und url_raw (Build 028)"""

    BASE_URL = "http://alice4nonion.onion"

    def setUp(self):
        _setup_test_logging()
        # Eigene DB mit Onion-URLs in pages und page_aliases anlegen
        self.fdb_path = tempfile.mktemp(suffix=".db")
        raw = sqlite3.connect(self.fdb_path)
        raw.executescript(f"""
            CREATE TABLE forensic_meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE pages (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                url_canonical TEXT NOT NULL,
                html          BLOB,
                fetched_at    INTEGER NOT NULL DEFAULT 0,
                http_status   INTEGER NOT NULL DEFAULT 0,
                scrape_context TEXT NOT NULL DEFAULT 'user',
                method        TEXT NOT NULL DEFAULT 'GET',
                UNIQUE(url_canonical, method)
            );
            CREATE TABLE page_aliases (
                url_raw  TEXT NOT NULL PRIMARY KEY,
                page_id  INTEGER NOT NULL REFERENCES pages(id)
            );
            INSERT INTO forensic_meta VALUES ('schema_version', '1');
            INSERT INTO forensic_meta VALUES ('protocol', 'http');
            INSERT INTO forensic_meta VALUES ('domainname', 'alice4nonion.onion');
            INSERT INTO pages (url_canonical, html, fetched_at, http_status, scrape_context, method)
            VALUES
                ('{self.BASE_URL}/forum/beginner/', X'3C68746D6C3E583C2F68746D6C3E',
                 1700000000, 200, 'user', 'GET'),
                ('{self.BASE_URL}/forum/viewtopic.php?id=200',
                 X'3C68746D6C3E593C2F68746D6C3E',
                 1700000001, 200, 'user', 'GET');
            INSERT INTO page_aliases (url_raw, page_id) VALUES
                ('{self.BASE_URL}/forum/beginner/index.php', 1),
                ('{self.BASE_URL}/', 1);
        """)
        raw.commit()
        raw.close()
        self.con = _make_attached_connection(self.fdb_path)
        self.fdb = ForensicDb(self.con)

    def tearDown(self):
        self.con.close()
        reset_for_testing()
        try:
            os.unlink(self.fdb_path)
        except OSError:
            pass

    def test_T26_url_canonical_ohne_praefix(self):
        """T26: Direkter Treffer über url_canonical — Onion-Präfix wird entfernt."""
        page = self.fdb.get_page("/forum/beginner/")
        self.assertIsNotNone(page)
        self.assertEqual(page.url, "/forum/beginner/")
        # canonical_url bleibt vollständig (wird von blob_handler für base_href genutzt)
        self.assertIn("alice4nonion.onion", page.canonical_url)

    def test_T27_url_raw_alias_ohne_praefix(self):
        """T27: Alias-Treffer über url_raw — Onion-Präfix wird entfernt."""
        page = self.fdb.get_page("/forum/beginner/index.php")
        self.assertIsNotNone(page)
        self.assertEqual(page.url, "/forum/beginner/index.php")

    def test_T28_slash_alias_ohne_praefix(self):
        """T28: Alias '/' (url_raw=Onion+'/') wird auf '/' reduziert."""
        page = self.fdb.get_page("/")
        self.assertIsNotNone(page)
        self.assertEqual(page.url, "/")
        # canonical_url zeigt auf /forum/beginner/
        self.assertIn("/forum/beginner/", page.canonical_url)


class TestForensicDbUserinfoBlob(unittest.TestCase):
    """T29–T32: get_userinfo_blob() — Lesen des Phase-B-HTML-BLOBs.
    Beleg: Projektgespräch 2026-04-18.
    """

    def setUp(self):
        _setup_test_logging()
        self.fdb_path = _create_fdb_in_memory()
        self.con = _make_attached_connection(self.fdb_path)
        self.fdb = ForensicDb(self.con)

    def tearDown(self):
        self.con.close()
        reset_for_testing()
        try:
            os.unlink(self.fdb_path)
        except OSError:
            pass

    def test_T29_keine_static_pages_tabelle_gibt_none(self):
        """T29: Wenn static_pages nicht existiert, gibt get_userinfo_blob() None zurück."""
        # Standard-Testdatenbank hat keine static_pages-Tabelle
        result = self.fdb.get_userinfo_blob()
        self.assertIsNone(result)

    def test_T30_kein_userinfo_eintrag_gibt_none(self):
        """T30: Tabelle vorhanden aber kein 'userinfo'-Eintrag → None."""
        # static_pages in fdb anlegen, aber leer lassen
        fdb_con = sqlite3.connect(self.fdb_path)
        fdb_con.execute(
            "CREATE TABLE IF NOT EXISTS static_pages "
            "(key TEXT PRIMARY KEY, html BLOB NOT NULL, "
            "generated_at INTEGER NOT NULL, generator_version TEXT NOT NULL)"
        )
        fdb_con.commit()
        fdb_con.close()

        result = self.fdb.get_userinfo_blob()
        self.assertIsNone(result)

    def test_T31_blob_als_bytes_wird_decoded(self):
        """T31: BLOB als bytes-Objekt wird korrekt als UTF-8 dekodiert."""
        html_content = "<div id=\"userinfo-static\"><p>Testinhalt</p></div>"
        fdb_con = sqlite3.connect(self.fdb_path)
        fdb_con.execute(
            "CREATE TABLE IF NOT EXISTS static_pages "
            "(key TEXT PRIMARY KEY, html BLOB NOT NULL, "
            "generated_at INTEGER NOT NULL, generator_version TEXT NOT NULL)"
        )
        fdb_con.execute(
            "INSERT INTO static_pages VALUES ('userinfo', ?, 1700000000, 'test')",
            (html_content.encode("utf-8"),)
        )
        fdb_con.commit()
        fdb_con.close()

        result = self.fdb.get_userinfo_blob()
        self.assertIsNotNone(result)
        self.assertIn("userinfo-static", result)
        self.assertIn("Testinhalt", result)

    def test_T32_blob_als_string_wird_direkt_zurueckgegeben(self):
        """T32: BLOB als TEXT-Objekt wird direkt zurückgegeben."""
        html_content = "<div id=\"userinfo-static\"><p>String-Inhalt</p></div>"
        fdb_con = sqlite3.connect(self.fdb_path)
        fdb_con.execute(
            "CREATE TABLE IF NOT EXISTS static_pages "
            "(key TEXT PRIMARY KEY, html BLOB NOT NULL, "
            "generated_at INTEGER NOT NULL, generator_version TEXT NOT NULL)"
        )
        fdb_con.execute(
            "INSERT INTO static_pages VALUES ('userinfo', ?, 1700000000, 'test')",
            (html_content,)
        )
        fdb_con.commit()
        fdb_con.close()

        result = self.fdb.get_userinfo_blob()
        self.assertIsNotNone(result)
        self.assertIn("String-Inhalt", result)

class TestResolvePostsProgress(unittest.TestCase):
    """Build 303: resolve_posts_progress() — pid → Seite + Fortschritt."""

    def setUp(self):
        _setup_test_logging()
        self.fdb_path = tempfile.mktemp(suffix=".db")
        con = sqlite3.connect(self.fdb_path)
        con.executescript("""
            CREATE TABLE forensic_meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_canonical TEXT NOT NULL, html BLOB,
                fetched_at INTEGER NOT NULL, http_status INTEGER NOT NULL,
                scrape_context TEXT NOT NULL DEFAULT 'user',
                method TEXT NOT NULL DEFAULT 'GET'
            );
            -- post_aliases MIT page/page_resolved (Prepper Build 098+)
            CREATE TABLE post_aliases (
                post_id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL,
                forum_id INTEGER NOT NULL,
                page INTEGER, page_resolved INTEGER NOT NULL DEFAULT 0
            );
            INSERT INTO forensic_meta VALUES ('user_id', '42');
            INSERT INTO pages (url_canonical, html, fetched_at, http_status)
            VALUES
              ('/forum/viewtopic.php?id=100',      X'3C68746D6C3E', 1700000000, 200),
              ('/forum/viewtopic.php?id=100&p=2',  X'3C68746D6C3E', 1700000001, 200);
            -- 12345 → Seite 1 (id 1), 67890 → Seite 2 (id 2), 99999 → unaufgelöst
            INSERT INTO post_aliases VALUES
              (12345, 100, 5, 1, 1),
              (67890, 100, 5, 2, 1),
              (99999, 100, 5, NULL, 0);
        """)
        con.commit()
        con.close()

        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.execute(f"ATTACH DATABASE '{self.fdb_path}' AS fdb")
        # evidence-Tabellen (annotations, page_visits) in der Haupt-DB
        self.con.executescript("""
            CREATE TABLE annotations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_url TEXT NOT NULL, tags_json TEXT
            );
            CREATE TABLE page_visits (page_url TEXT NOT NULL, ts INTEGER NOT NULL);
            -- Seite 1: annotiert + betrachtet → 100
            INSERT INTO annotations (page_url, tags_json)
              VALUES ('/forum/viewtopic.php?id=100', '["x"]');
            INSERT INTO page_visits VALUES ('/forum/viewtopic.php?id=100', 1700000500);
            -- Seite 2: nur betrachtet → 50
            INSERT INTO page_visits VALUES ('/forum/viewtopic.php?id=100&p=2', 1700000600);
        """)
        self.con.commit()
        self.fdb = ForensicDb(self.con)

    def tearDown(self):
        self.con.close()
        reset_for_testing()
        try:
            os.unlink(self.fdb_path)
        except OSError:
            pass

    def test_resolved_page1_progress_100(self):
        r = self.fdb.resolve_posts_progress([12345])
        e = r[12345]
        self.assertTrue(e["resolved"])
        self.assertEqual(e["pageId"], 1)
        self.assertEqual(e["topicId"], 100)
        self.assertEqual(e["forumId"], 5)
        self.assertEqual(e["url"], "/forum/viewtopic.php?id=100")
        self.assertEqual(e["progressPercent"], 100)

    def test_resolved_page2_progress_50(self):
        r = self.fdb.resolve_posts_progress([67890])
        e = r[67890]
        self.assertTrue(e["resolved"])
        self.assertEqual(e["pageId"], 2)
        self.assertEqual(e["url"], "/forum/viewtopic.php?id=100&p=2")
        self.assertEqual(e["progressPercent"], 50)

    def test_unresolved_page_null(self):
        r = self.fdb.resolve_posts_progress([99999])
        e = r[99999]
        self.assertFalse(e["resolved"])
        self.assertNotIn("pageId", e)
        self.assertEqual(e["topicId"], 100)

    def test_unknown_pid_resolved_false(self):
        r = self.fdb.resolve_posts_progress([11111])
        self.assertFalse(r[11111]["resolved"])

    def test_mixed_batch(self):
        r = self.fdb.resolve_posts_progress([12345, 67890, 99999, 11111])
        self.assertEqual(len(r), 4)
        self.assertTrue(r[12345]["resolved"])
        self.assertTrue(r[67890]["resolved"])
        self.assertFalse(r[99999]["resolved"])
        self.assertFalse(r[11111]["resolved"])

    def test_empty_list(self):
        self.assertEqual(self.fdb.resolve_posts_progress([]), {})

    def test_missing_page_columns_graceful(self):
        """post_aliases ohne page/page_resolved → alle unaufgelöst, kein Crash."""
        path2 = tempfile.mktemp(suffix=".db")
        c = sqlite3.connect(path2)
        c.executescript("""
            CREATE TABLE forensic_meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE pages (id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_canonical TEXT NOT NULL, html BLOB, fetched_at INTEGER NOT NULL,
                http_status INTEGER NOT NULL, scrape_context TEXT DEFAULT 'user',
                method TEXT DEFAULT 'GET');
            CREATE TABLE post_aliases (post_id INTEGER PRIMARY KEY,
                topic_id INTEGER NOT NULL, forum_id INTEGER NOT NULL);
            INSERT INTO post_aliases VALUES (12345, 100, 5);
        """)
        c.commit(); c.close()
        con2 = sqlite3.connect(":memory:")
        con2.row_factory = sqlite3.Row
        con2.execute(f"ATTACH DATABASE '{path2}' AS fdb")
        con2.commit()
        try:
            fdb2 = ForensicDb(con2)
            r = fdb2.resolve_posts_progress([12345])
            self.assertFalse(r[12345]["resolved"])
            self.assertEqual(r[12345]["topicId"], 100)
        finally:
            con2.close()
            try:
                os.unlink(path2)
            except OSError:
                pass


class TestResolvePostPage(unittest.TestCase):
    """
    Build 699 (Vorgang f5956e6b): resolve_post_page() — der Beitrag und die
    Seite, die ihn TRAEGT.

    R01 — gemessene Seite (post_aliases.page) wird geliefert
    R02 — die Basis-URL wird abgeschnitten (Lookup-Form von get_page)
    R03 — page_resolved=0 → Nachmessung im BLOB findet den richtigen Chunk
    R04 — Nachmessung erkennt auch den inneren Anker id="pp<id>"
    R05 — Nachmessung: bei Mehrfachvorkommen gewinnt der niedrigste Chunk
    R06 — kein Chunk traegt den Anker → None (kein Raten, Grundregel 1)
    R07 — unbekannte post_id → None
    R08 — post_aliases ohne page-Spalten (Schema v1) → Nachmessung greift
    R09 — die Nachmessung verwechselt topic_id=5 nicht mit 50 oder 512
    R10 — post_aliases.page zeigt ins Leere → Nachmessung uebernimmt
    R11 — Chunk mit html IS NULL gilt nicht als Treffer
    """

    # p777 steht NUR im zweiten Chunk — die Lage aus der Fehlermeldung.
    CHUNK1 = b'<html><body><div id="p100">erster</div></body></html>'
    CHUNK2 = b'<html><body><div id="p777">gesuchter Beitrag</div></body></html>'

    def setUp(self):
        _setup_test_logging()
        self.fdb_path = tempfile.mktemp(suffix=".db")

    def tearDown(self):
        reset_for_testing()
        try:
            os.unlink(self.fdb_path)
        except OSError:
            pass

    # -- Aufbau ------------------------------------------------------------
    def _baue(self, seiten, post_aliases, meta=None, mit_page_spalten=True):
        """
        Legt eine fdb an und liefert eine ForensicDb darauf.

        seiten:        Liste (url_canonical, html|None)
        post_aliases:  Liste (post_id, topic_id, forum_id, page|None, resolved)
                       bzw. ohne die letzten beiden bei mit_page_spalten=False
        meta:          dict fuer forensic_meta (z. B. protocol/domainname)
        """
        con = sqlite3.connect(self.fdb_path)
        pa_schema = (
            "CREATE TABLE post_aliases (post_id INTEGER PRIMARY KEY, "
            "topic_id INTEGER NOT NULL, forum_id INTEGER NOT NULL, "
            "page INTEGER, page_resolved INTEGER NOT NULL DEFAULT 0);"
            if mit_page_spalten else
            "CREATE TABLE post_aliases (post_id INTEGER PRIMARY KEY, "
            "topic_id INTEGER NOT NULL, forum_id INTEGER NOT NULL);"
        )
        con.executescript(
            "CREATE TABLE forensic_meta (key TEXT PRIMARY KEY, value TEXT);"
            "CREATE TABLE pages (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "url_canonical TEXT NOT NULL, html BLOB, "
            "fetched_at INTEGER NOT NULL, http_status INTEGER NOT NULL, "
            "scrape_context TEXT NOT NULL DEFAULT 'user', "
            "method TEXT NOT NULL DEFAULT 'GET');"
            "CREATE TABLE page_aliases (url_raw TEXT PRIMARY KEY, "
            "page_id INTEGER NOT NULL);"
            + pa_schema
        )
        for key, value in (meta or {}).items():
            con.execute("INSERT INTO forensic_meta VALUES (?, ?)", (key, value))
        for url, html in seiten:
            con.execute(
                "INSERT INTO pages (url_canonical, html, fetched_at, http_status) "
                "VALUES (?, ?, 1700000000, 200)", (url, html),
            )
        for zeile in post_aliases:
            platzhalter = ",".join("?" * len(zeile))
            con.execute(
                f"INSERT INTO post_aliases VALUES ({platzhalter})", zeile
            )
        con.commit()
        con.close()

        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.execute(f"ATTACH DATABASE '{self.fdb_path}' AS fdb")
        self.addCleanup(self.con.close)
        return ForensicDb(self.con)

    def _zwei_chunks(self, post_aliases, meta=None, mit_page_spalten=True):
        return self._baue(
            [("/forum/viewtopic.php?id=500",     self.CHUNK1),
             ("/forum/viewtopic.php?id=500&p=2", self.CHUNK2)],
            post_aliases, meta=meta, mit_page_spalten=mit_page_spalten,
        )

    # -- Faelle ------------------------------------------------------------
    def test_R01_gemessene_seite(self):
        fdb = self._zwei_chunks([(777, 500, 5, 2, 1)])
        treffer = fdb.resolve_post_page(777)
        self.assertIsNotNone(treffer)
        self.assertEqual(treffer.page_id, 2)
        self.assertEqual(treffer.url, "/forum/viewtopic.php?id=500&p=2")
        self.assertEqual(treffer.quelle, "gemessen")

    def test_R02_basis_url_wird_abgeschnitten(self):
        """R02: get_page() sucht auf der basisbereinigten Adresse — die
        gelieferte url muss genau diese Form haben, sonst faende der
        anschliessende Lookup die Seite nicht."""
        basis = "http://alice4nonion.onion"
        fdb = self._baue(
            [(f"{basis}/forum/viewtopic.php?id=500",     self.CHUNK1),
             (f"{basis}/forum/viewtopic.php?id=500&p=2", self.CHUNK2)],
            [(777, 500, 5, 2, 1)],
            meta={"protocol": "http", "domainname": "alice4nonion.onion"},
        )
        treffer = fdb.resolve_post_page(777)
        self.assertEqual(treffer.url, "/forum/viewtopic.php?id=500&p=2")
        # Gegenprobe: unter genau dieser Adresse findet get_page() den BLOB.
        self.assertIsNotNone(fdb.get_page(treffer.url))

    def test_R03_nachmessung_bei_unaufgeloester_spalte(self):
        fdb = self._zwei_chunks([(777, 500, 5, None, 0)])
        treffer = fdb.resolve_post_page(777)
        self.assertIsNotNone(treffer)
        self.assertEqual(treffer.url, "/forum/viewtopic.php?id=500&p=2")
        self.assertEqual(treffer.quelle, "blob")

    def test_R04_innerer_anker_zaehlt(self):
        """R04: Der Renderpfad viewtopic0 Z.975 setzt id="pp<id>" — derselbe
        Beitrag, andere Schreibweise. Beleg: post_page_measurer.py."""
        fdb = self._baue(
            [("/forum/viewtopic.php?id=500",     self.CHUNK1),
             ("/forum/viewtopic.php?id=500&p=2",
              b'<html><body><div id="pp777">x</div></body></html>')],
            [(777, 500, 5, None, 0)],
        )
        treffer = fdb.resolve_post_page(777)
        self.assertEqual(treffer.url, "/forum/viewtopic.php?id=500&p=2")

    def test_R05_niedrigster_chunk_gewinnt(self):
        """R05: StickFP/Umfragen wiederholen den ersten Beitrag oben auf jedem
        Folge-Chunk. Heimat ist der niedrigste — dieselbe Regel wie im
        PostPageMeasurer, damit Vor- und Nachmessung uebereinstimmen."""
        wiederholt = b'<html><body><div id="p100">erster</div></body></html>'
        fdb = self._baue(
            [("/forum/viewtopic.php?id=500&p=3", wiederholt),
             ("/forum/viewtopic.php?id=500",     wiederholt),
             ("/forum/viewtopic.php?id=500&p=2", wiederholt)],
            [(100, 500, 5, None, 0)],
        )
        treffer = fdb.resolve_post_page(100)
        self.assertEqual(treffer.url, "/forum/viewtopic.php?id=500")

    def test_R06_kein_chunk_traegt_den_anker(self):
        fdb = self._zwei_chunks([(999, 500, 5, None, 0)])
        self.assertIsNone(fdb.resolve_post_page(999))

    def test_R07_unbekannte_post_id(self):
        fdb = self._zwei_chunks([(777, 500, 5, 2, 1)])
        self.assertIsNone(fdb.resolve_post_page(4242))

    def test_R08_schema_v1_ohne_page_spalten(self):
        """R08: forensic_db-Schema v1 kennt post_aliases.page nicht. Die
        Nachmessung ersetzt die fehlende Vormessung — die Weiterverwendung
        einer v1-Datenbank bleibt damit moeglich (SUPPORTED_..._VERSIONS)."""
        fdb = self._zwei_chunks([(777, 500, 5)], mit_page_spalten=False)
        treffer = fdb.resolve_post_page(777)
        self.assertIsNotNone(treffer)
        self.assertEqual(treffer.url, "/forum/viewtopic.php?id=500&p=2")
        self.assertEqual(treffer.quelle, "blob")

    def test_R09_aehnliche_topic_ids_werden_nicht_verwechselt(self):
        """R09: Die Vorauswahl per LIKE trifft auch id=50 und id=512. Erst der
        Ausdruck auf der Adresse entscheidet. Ohne ihn lieferte die
        Nachmessung eine Seite eines FREMDEN Themas."""
        fdb = self._baue(
            [("/forum/viewtopic.php?id=5",      self.CHUNK1),
             ("/forum/viewtopic.php?id=50",     self.CHUNK2),
             ("/forum/viewtopic.php?id=512&p=2", self.CHUNK2)],
            [(777, 5, 5, None, 0)],
        )
        # Der Anker p777 steht nur in den Seiten der FREMDEN Themen.
        self.assertIsNone(fdb.resolve_post_page(777))

    def test_R10_page_zeigt_ins_leere(self):
        """R10: post_aliases.page nennt eine pages.id, die es nicht gibt.
        Statt eines Absturzes oder eines stillen Seite-1-Rueckfalls uebernimmt
        die Nachmessung."""
        fdb = self._zwei_chunks([(777, 500, 5, 4242, 1)])
        treffer = fdb.resolve_post_page(777)
        self.assertIsNotNone(treffer)
        self.assertEqual(treffer.url, "/forum/viewtopic.php?id=500&p=2")
        self.assertEqual(treffer.quelle, "blob")

    def test_R11_fehlgeschlagener_abruf_ist_kein_treffer(self):
        """R11: html IS NULL heisst 'Abruf fehlgeschlagen'. Ein fehlender
        Inhalt belegt weder Anwesenheit noch Abwesenheit des Beitrags."""
        fdb = self._baue(
            [("/forum/viewtopic.php?id=500",     self.CHUNK1),
             ("/forum/viewtopic.php?id=500&p=2", None)],
            [(777, 500, 5, None, 0)],
        )
        self.assertIsNone(fdb.resolve_post_page(777))


class TestBlobEnthaeltAnker(unittest.TestCase):
    """
    Build 699: blob_enthaelt_anker() — die Ankerprobe fuer sich.

    A01 — aeusserer Anker id="p<id>" wird erkannt
    A02 — innerer Anker id="pp<id>" wird erkannt
    A03 — Praefixverwechslung: id="p7770" ist NICHT der Beitrag 777
    A04 — html=None ergibt False (kein Beleg, keine Behauptung)
    A05 — str statt bytes wird behandelt
    """

    def setUp(self):
        _setup_test_logging()

    def tearDown(self):
        reset_for_testing()

    def test_A01_aeusserer_anker(self):
        from db.forensic_db import blob_enthaelt_anker
        self.assertTrue(blob_enthaelt_anker(b'<div id="p777">x</div>', 777))

    def test_A02_innerer_anker(self):
        from db.forensic_db import blob_enthaelt_anker
        self.assertTrue(blob_enthaelt_anker(b'<div id="pp777">x</div>', 777))

    def test_A03_keine_praefixverwechslung(self):
        """A03: Ohne das abschliessende Anfuehrungszeichen im Muster wuerde
        id="p7770" als Beitrag 777 gelten — und der Sprung landete auf einem
        fremden Beitrag."""
        from db.forensic_db import blob_enthaelt_anker
        self.assertFalse(blob_enthaelt_anker(b'<div id="p7770">x</div>', 777))

    def test_A04_none(self):
        from db.forensic_db import blob_enthaelt_anker
        self.assertFalse(blob_enthaelt_anker(None, 777))

    def test_A05_str_statt_bytes(self):
        from db.forensic_db import blob_enthaelt_anker
        self.assertTrue(blob_enthaelt_anker('<div id="p777">x</div>', 777))



class TestListPmPostIds(unittest.TestCase):
    """
    Build 703 (Vorgang da84f94f): list_pm_post_ids() — Dialog → Nachrichten.

    WOZU: Die Uebersetzungsanzeige braucht je PN-Dialogseite die Menge der
    Nachrichten, BEVOR das Seiten-DOM steht. Bei Forenbeitraegen liefert
    trdb.translations.topic_id diese Menge; bei PN steht dort nichts
    (Datenprobe Alex, 12.08.2026). Die Zuordnung kommt deshalb aus dem
    forensischen Bestand.

    PM01 — alle Nachrichten eines Dialogs, BEIDE Gespraechsseiten
    PM02 — fremder Dialog wird nicht mitgeliefert
    PM03 — unbekannter Dialog -> leere Liste (kein Fehler)
    PM04 — fehlende Tabelle -> leere Liste, kein Absturz
    """

    def setUp(self):
        _setup_test_logging()
        self.fdb_path = tempfile.mktemp(suffix=".db")

    def tearDown(self):
        reset_for_testing()
        try:
            os.unlink(self.fdb_path)
        except OSError:
            pass

    def _fdb(self, mit_tabelle=True):
        con = sqlite3.connect(self.fdb_path)
        con.execute("CREATE TABLE forensic_meta (key TEXT PRIMARY KEY, value TEXT)")
        con.execute(
            "CREATE TABLE pages (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "url_canonical TEXT NOT NULL, html BLOB, fetched_at INTEGER NOT NULL, "
            "http_status INTEGER NOT NULL, scrape_context TEXT DEFAULT 'user', "
            "method TEXT DEFAULT 'GET')"
        )
        con.execute("CREATE TABLE page_aliases (url_raw TEXT PRIMARY KEY, "
                    "page_id INTEGER NOT NULL)")
        if mit_tabelle:
            con.execute("CREATE TABLE pm_aliases (pm_post_id INTEGER PRIMARY KEY, "
                        "pm_topic_id INTEGER NOT NULL)")
            con.executemany(
                "INSERT INTO pm_aliases VALUES (?,?)",
                # Dialog 85844: drei Nachrichten — im Bestand stehen BEIDE
                # Gespraechsseiten (Prepper: alle pms_new_posts des Dialogs).
                [(44573, 85844), (44574, 85844), (44575, 85844),
                 (51000, 82544)],
            )
        con.commit()
        con.close()

        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.execute(f"ATTACH DATABASE '{self.fdb_path}' AS fdb")
        self.addCleanup(self.con.close)
        return ForensicDb(self.con)

    def test_PM01_alle_nachrichten_des_dialogs(self):
        fdb = self._fdb()
        self.assertEqual(sorted(fdb.list_pm_post_ids(85844)),
                         [44573, 44574, 44575])

    def test_PM02_fremder_dialog_bleibt_draussen(self):
        fdb = self._fdb()
        self.assertEqual(fdb.list_pm_post_ids(82544), [51000])

    def test_PM03_unbekannter_dialog_leer(self):
        fdb = self._fdb()
        self.assertEqual(fdb.list_pm_post_ids(999999), [])

    def test_PM04_ohne_tabelle_leer(self):
        fdb = self._fdb(mit_tabelle=False)
        self.assertEqual(fdb.list_pm_post_ids(85844), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)

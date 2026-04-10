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
# Version: v0.1.0 · Build: 006 · 2026-04-10
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
            url_canonical  TEXT NOT NULL UNIQUE,
            html           BLOB,
            fetched_at     INTEGER NOT NULL,
            http_status    INTEGER NOT NULL,
            scrape_context TEXT NOT NULL DEFAULT 'user'
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

        INSERT INTO pages (url_canonical, html, fetched_at, http_status, scrape_context)
        VALUES
            ('/forum/viewtopic.php?id=100',
             X'3C68746D6C3E546F706963313C2F68746D6C3E',
             1700000000, 200, 'user'),
            ('/forum/viewtopic.php?id=200',
             NULL,
             1700000001, 403, 'investigator'),
            ('/forum/profile.php?id=42',
             X'3C68746D6C3E50726F66696C653C2F68746D6C3E',
             1700000002, 200, 'user'),
            ('/forum/viewtopic.php?id=300',
             X'3C68746D6C3E546F706963333C2F68746D6C3E',
             1700000003, 200, 'actor:99');

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
        """T19: Schreibversuch auf fdb.pages schlägt fehl (fdb ist READ-ONLY angebunden)."""
        # In dieser Test-Konfiguration ist fdb nicht URI mode=ro angebunden —
        # das ist Aufgabe von connection_manager.py in der Produktion.
        # Wir prüfen hier, dass ForensicDb selbst keine Schreibmethoden hat.
        # Alle öffentlichen Methoden sind: get_page, get_page_by_id,
        # resolve_*_alias, get_meta, get_scrape_context, page_count.
        # Keine davon enthält INSERT/UPDATE/DELETE.
        import inspect
        source = inspect.getsource(type(self.fdb))
        forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE TABLE"]
        for stmt in forbidden:
            # Erlaubt ist CREATE TEMP VIEW (für den blob_lookup-View)
            if stmt == "CREATE TABLE":
                self.assertNotIn(stmt + " ", source,
                    f"ForensicDb enthält '{stmt}' — Schreiboperation verboten")
            else:
                self.assertNotIn(stmt, source,
                    f"ForensicDb enthält '{stmt}' — Schreiboperation verboten")

    def test_T20_blob_lookup_beide_quellen(self):
        """T20: blob_lookup liefert sowohl url_canonical als auch url_raw-Treffer."""
        # Direkte URL
        page_direct = self.fdb.get_page("/forum/viewtopic.php?id=100")
        self.assertIsNotNone(page_direct)

        # Alias-URL (url_raw aus page_aliases)
        page_alias1 = self.fdb.get_page("/forum/viewtopic.php?id=100#p12345")
        page_alias2 = self.fdb.get_page("/forum/viewtopic.php?pid=12345#p12345")

        self.assertIsNotNone(page_alias1)
        self.assertIsNotNone(page_alias2)

        # Alle drei zeigen auf dieselbe Seite
        self.assertEqual(page_direct.page_id, page_alias1.page_id)
        self.assertEqual(page_direct.page_id, page_alias2.page_id)

        # Inhalt ist identisch
        self.assertEqual(page_direct.html, page_alias1.html)


if __name__ == "__main__":
    unittest.main(verbosity=2)

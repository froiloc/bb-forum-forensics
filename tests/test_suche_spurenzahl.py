# =============================================================================
# tests/test_suche_spurenzahl.py
# IT-Forensisches Ermittlungswerkzeug — Suche (Build 678)
# =============================================================================
# Vorgang 1157e5f3: traceCountTotal war IMMER 0.
#
# DIE URSACHE, nachlesbar im alten SQL: die Verbindung zu fdb.scrape_targets
# fragte nach url_type IN ('topic', 'pm', 'forum', 'profile'). Die ersten drei
# sind GRUPPENNAMEN der Spurennavigation und keine Werte von url_type - dort
# stehen 'viewtopic', 'viewforum', 'pmsnew_post', 'pms_partner' und so fort.
# Von vier Zweigen konnte also nur einer je zutreffen ('profile'); fuer jede
# Themen-, Forums- und PN-Seite kam zwangslaeufig 0 heraus.
#
# DIE BEHEBUNG benutzt DIESELBE Vorschrift wie die Seite selbst:
# get_trace_elements_for_page() liefert die Marken, die Minimap und
# Spurennavigation anzeigen. Die Uebersicht kann damit gar nicht mehr etwas
# anderes behaupten als die Seite.
#
# Testfaelle:
#   TC01 - Eine Themenseite mit Spuren bekommt die richtige Zahl, nicht 0.
#   TC02 - Die Zahl stimmt mit get_trace_elements_for_page() ueberein - die
#          EINE Vorschrift, an zwei Stellen gelesen.
#   TC03 - Eine Seite ohne Spuren bekommt 0. Ein Waechter, der immer
#          anschlaegt, ist keiner.
#   TC04 - Die Listenabfrage verbindet scrape_targets nicht mehr. Das war der
#          Fehler UND die teuerste Verbindung (ueber 120 Millionen
#          Zeichenkettenvergleiche im echten Bestand).
#   TC05 - 'traces_desc' wird ERSETZT und das steht in der Antwort. Eine
#          stille Ersetzung waere die Sorte Auslassung, die Grundregel 1
#          verbietet.
#
# Version: v0.8.678 - Build: 678 - 2026-08-05
# =============================================================================

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import reset_for_testing          # noqa: E402
from db.forensic_db import ForensicDb              # noqa: E402
from forensic_api.search import SearchEndpoint     # noqa: E402

BASIS = "http://alice.onion"


def _bestand() -> sqlite3.Connection:
    """
    Wegwerf-Bestand mit zwei Themenseiten:
      Thema 500 - drei Beitraege des Beschuldigten (drei Spuren)
      Thema 600 - keine Spuren
    """
    fdb_pfad = tempfile.mktemp(suffix="_fdb.db")
    fdb = sqlite3.connect(fdb_pfad)
    fdb.executescript("""
        CREATE TABLE forensic_meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_canonical TEXT NOT NULL, html BLOB, title TEXT,
            fetched_at INTEGER NOT NULL DEFAULT 0,
            http_status INTEGER NOT NULL DEFAULT 200,
            scrape_context TEXT NOT NULL DEFAULT 'user',
            method TEXT NOT NULL DEFAULT 'GET',
            UNIQUE(url_canonical, method));
        CREATE TABLE page_aliases (
            url_raw TEXT NOT NULL PRIMARY KEY, page_id INTEGER NOT NULL);
        CREATE TABLE post_aliases (
            post_id INTEGER NOT NULL PRIMARY KEY,
            topic_id INTEGER NOT NULL, forum_id INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE pm_aliases (
            pm_post_id INTEGER NOT NULL PRIMARY KEY,
            pm_topic_id INTEGER NOT NULL);
        CREATE TABLE scrape_targets (
            id INTEGER PRIMARY KEY, scrape_context TEXT NOT NULL DEFAULT 'user',
            url_type TEXT NOT NULL, forum_id INTEGER, topic_id INTEGER,
            post_id INTEGER, pm_topic_id INTEGER, pm_post_id INTEGER,
            thanks_post_id INTEGER, poll_topic_id INTEGER,
            actor_user_id INTEGER, actor_username TEXT, static_url TEXT,
            source_tables TEXT NOT NULL DEFAULT '');
        INSERT INTO forensic_meta VALUES ('protocol','http'),
                                         ('domainname','alice.onion');
        INSERT INTO pages (id, url_canonical, title, html) VALUES
            (1, 'http://alice.onion/forum/viewtopic.php?id=500', 'Thema mit Spuren', x'00'),
            (2, 'http://alice.onion/forum/viewtopic.php?id=600', 'Thema ohne Spuren', x'00');
        -- Drei Beitraege des Beschuldigten in Thema 500
        INSERT INTO post_aliases (post_id, topic_id) VALUES
            (9001, 500), (9002, 500), (9003, 500), (9500, 600);
        INSERT INTO scrape_targets (id, url_type, post_id, topic_id) VALUES
            (1, 'viewtopic', 9001, 500),
            (2, 'viewtopic', 9002, 500),
            (3, 'viewtopic', 9003, 500);
    """)
    fdb.commit()
    fdb.close()

    haupt = sqlite3.connect(":memory:")
    haupt.row_factory = sqlite3.Row
    haupt.executescript("""
        CREATE TABLE annotations (
            id INTEGER PRIMARY KEY, page_url TEXT NOT NULL, element_id TEXT,
            category TEXT, text TEXT, ts INTEGER, investigator_id TEXT,
            local_id TEXT, tags_json TEXT, post_id INTEGER, created_by TEXT,
            selection_json TEXT);
        CREATE TABLE page_visits (
            id INTEGER PRIMARY KEY, page_url TEXT NOT NULL,
            scrape_context TEXT, ts INTEGER, investigator_id TEXT);
    """)
    haupt.execute("ATTACH DATABASE '%s' AS fdb" % fdb_pfad)
    haupt.commit()
    return haupt


class SucheSpurenzahlTests(unittest.TestCase):

    def setUp(self):
        reset_for_testing()
        self.con = _bestand()
        self.db = ForensicDb.__new__(ForensicDb)
        self.db._con = self.con

    def tearDown(self):
        self.con.close()

    def _nach_url(self, treffer, teil):
        for t in treffer:
            if teil in t["url"]:
                return t
        self.fail("Seite mit '%s' nicht in den Treffern: %s"
                  % (teil, [t["url"] for t in treffer]))

    # -- TC01 -----------------------------------------------------------------
    def test_tc01_seite_mit_spuren_zaehlt_richtig(self):
        treffer = self.db.search_pages(limit=50)
        mit = self._nach_url(treffer, "id=500")
        self.assertEqual(
            3, mit["traceCountTotal"],
            "Die Themenseite traegt drei Beitraege des Beschuldigten. Bis "
            "Build 677 stand hier 0.")

    # -- TC02 -----------------------------------------------------------------
    def test_tc02_dieselbe_vorschrift_wie_die_seite(self):
        """
        Die EINE Vorschrift, an zwei Stellen gelesen. Waeren es zwei
        Vorschriften, koennte die Uebersicht etwas anderes anzeigen als die
        Seite selbst - und niemand wuesste, welche der beiden Zahlen gilt.
        """
        treffer = self.db.search_pages(limit=50)
        for t in treffer:
            page_id = 1 if "id=500" in t["url"] else 2
            with self.subTest(url=t["url"]):
                self.assertEqual(
                    len(self.db.get_trace_elements_for_page(page_id)),
                    t["traceCountTotal"])

    # -- TC03 -----------------------------------------------------------------
    def test_tc03_seite_ohne_spuren_bleibt_null(self):
        treffer = self.db.search_pages(limit=50)
        ohne = self._nach_url(treffer, "id=600")
        self.assertEqual(0, ohne["traceCountTotal"],
                         "Ein Waechter, der immer anschlaegt, ist keiner.")

    # -- TC04 -----------------------------------------------------------------
    def test_tc04_listenabfrage_verbindet_scrape_targets_nicht_mehr(self):
        """
        Die alte Verbindung war zugleich der Fehler und die teuerste Stelle:
        ein LIKE ohne Anker zwischen jeder Seite und jedem Erfassungsziel -
        im echten Bestand ueber 120 Millionen Zeichenkettenvergleiche.
        """
        gesehene = []

        class Mitschrift:
            def __init__(self, echt):
                self._echt = echt

            def execute(self, sql, *args, **kwargs):
                gesehene.append(sql)
                return self._echt.execute(sql, *args, **kwargs)

            def __getattr__(self, name):
                return getattr(self._echt, name)

        echte = self.db._con
        self.db._con = Mitschrift(echte)
        try:
            self.db.search_pages(limit=50)
        finally:
            self.db._con = echte

        # Die grosse Listenabfrage erkennt man an 'GROUP BY p.id'.
        listen = [s for s in gesehene if "GROUP BY p.id" in s]
        self.assertTrue(listen, "Listenabfrage nicht mitgeschrieben.")
        for s in listen:
            self.assertNotIn(
                "scrape_targets", s,
                "Die Listenabfrage verbindet scrape_targets wieder - das war "
                "der Fehler aus 1157e5f3 und zugleich die teuerste Stelle.")

    # -- TC05 -----------------------------------------------------------------
    def test_tc05_ersetzte_sortierung_wird_angeschrieben(self):
        bundle = MagicMock()
        bundle.forensic = self.db
        endpunkt = SearchEndpoint(bundle=bundle, context=MagicMock(),
                                  config=MagicMock())
        handler = MagicMock()
        gefangen = {}

        def merke(status, body, content_type=None):
            gefangen["body"] = json.loads(body.decode("utf-8"))

        handler.send_response_body = merke

        endpunkt.handle(handler, {"sort": ["traces_desc"]})
        ersetzt = gefangen["body"]["sortierung_ersetzt"]
        self.assertIsNotNone(
            ersetzt,
            "Eine stille Ersetzung waere die Sorte Auslassung, die "
            "Grundregel 1 verbietet.")
        self.assertEqual("traces_desc", ersetzt["bestellt"])
        self.assertEqual("last_viewed_desc", ersetzt["geliefert"])
        self.assertIn("Spurenzahl", ersetzt["grund"])

        # Gegenprobe: eine bediente Sortierung wird NICHT als ersetzt gemeldet.
        endpunkt.handle(handler, {"sort": ["url_asc"]})
        self.assertIsNone(gefangen["body"]["sortierung_ersetzt"])


if __name__ == "__main__":
    unittest.main()

# =============================================================================
# tests/test_trace_sequence.py
# IT-Forensisches Ermittlungswerkzeug — OP-KN-7: Spur-Navigation
# =============================================================================
# Testsuite für:
#   db/forensic_db.py::ForensicDb.get_trace_sequence()
#   forensic_api/trace_sequence.py::TraceSequenceEndpoint
#
# Strategie:
#   ForensicDb-Tests: In-Memory SQLite mit Schema aus forensic_2948078_db.sql.
#   fdb wird per ATTACH an die Haupt-DB gebunden (pages + annotations in
#   Haupt-DB für search_pages/trace_sequence, scrape_targets in fdb).
#   TraceSequenceEndpoint: Minimal-Mock für ForensicRequestHandler.
#
# Testfälle:
#   T01 — get_trace_sequence(): leere DB → leere Liste
#   T02 — get_trace_sequence(): topic-Spur wird geliefert
#   T03 — get_trace_sequence(): profile-Spur wird geliefert
#   T04 — get_trace_sequence(): pm-Spur wird geliefert
#   T05 — get_trace_sequence(): Gruppenreihenfolge: profile < pm < topic < other
#   T06 — get_trace_sequence(): Deduplizierung — gleiche URL nur einmal
#   T07 — get_trace_sequence(): url_type='static' wird übersprungen
#   T08 — get_trace_sequence(): Spur ohne zugehörige pages-Zeile wird übersprungen
#   T09 — get_trace_sequence(): chronologische Reihenfolge innerhalb Gruppe (id ASC)
#   T10 — get_trace_sequence(): Pflichtfelder url, title, group, trace_id vorhanden
#   T11 — TraceSequenceEndpoint.handle(): HTTP 200, JSON mit 'sequence' + 'total'
#   T12 — TraceSequenceEndpoint.handle(): status='ok' im Response
#   T13 — TraceSequenceEndpoint.handle(): leere Sequenz → total=0, sequence=[]
#
# Version: v0.1.0 · Build: 073 · 2026-04-27
# Klassifikation: VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
# =============================================================================

import sys
import os
import sqlite3
import tempfile
import textwrap
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import reset_for_testing
from db.forensic_db import ForensicDb


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _suppress_logging():
    reset_for_testing()


def _create_attached_db(scrape_targets: list[dict] | None = None,
                        pages: list[dict] | None = None) -> sqlite3.Connection:
    """
    Erstellt eine Haupt-In-Memory-DB (evidence) mit ATTACH auf eine
    temporäre fdb-Datei.

    scrape_targets: Liste von dicts mit Feldern:
        id, url_type, forum_id, topic_id, post_id, pm_topic_id,
        pm_post_id, thanks_post_id, poll_topic_id, actor_user_id,
        actor_username, static_url, source_tables, scrape_context
    pages: Liste von dicts mit Feldern:
        url_canonical, title, html, http_status, scrape_context, method
    """
    # Temporäre fdb-Datei (ATTACH erfordert Datei, kein :memory:)
    fdb_path = tempfile.mktemp(suffix="_fdb.db")
    fdb_con = sqlite3.connect(fdb_path)
    fdb_con.executescript("""
        CREATE TABLE IF NOT EXISTS forensic_meta (
            key   TEXT NOT NULL PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS pages (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            url_canonical  TEXT NOT NULL,
            html           BLOB,
            title          TEXT,
            fetched_at     INTEGER NOT NULL DEFAULT 0,
            http_status    INTEGER NOT NULL DEFAULT 200,
            scrape_context TEXT NOT NULL DEFAULT 'user',
            method         TEXT NOT NULL DEFAULT 'GET',
            UNIQUE(url_canonical, method)
        );
        CREATE TABLE IF NOT EXISTS page_aliases (
            url_raw TEXT NOT NULL PRIMARY KEY,
            page_id INTEGER NOT NULL REFERENCES pages(id)
        );
        CREATE TABLE IF NOT EXISTS post_aliases (
            post_id  INTEGER NOT NULL PRIMARY KEY,
            topic_id INTEGER NOT NULL,
            forum_id INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pm_aliases (
            pm_post_id  INTEGER NOT NULL PRIMARY KEY,
            pm_topic_id INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notify_aliases (
            notify_id INTEGER NOT NULL PRIMARY KEY,
            post_id   INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scrape_targets (
            id              INTEGER PRIMARY KEY,
            scrape_context  TEXT NOT NULL DEFAULT 'user',
            url_type        TEXT NOT NULL,
            forum_id        INTEGER,
            topic_id        INTEGER,
            post_id         INTEGER,
            pm_topic_id     INTEGER,
            pm_post_id      INTEGER,
            thanks_post_id  INTEGER,
            poll_topic_id   INTEGER,
            actor_user_id   INTEGER,
            actor_username  TEXT,
            static_url      TEXT,
            source_tables   TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO forensic_meta VALUES ('user_id', '2948078');
        INSERT INTO forensic_meta VALUES ('username', 'testnutzer');
    """)

    # pages einfügen
    for p in (pages or []):
        fdb_con.execute(
            "INSERT OR IGNORE INTO pages "
            "(url_canonical, title, html, http_status, scrape_context, method) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                p.get("url_canonical"),
                p.get("title"),
                p.get("html", b"<html></html>"),
                p.get("http_status", 200),
                p.get("scrape_context", "user"),
                p.get("method", "GET"),
            ),
        )

    # scrape_targets einfügen
    for st in (scrape_targets or []):
        fdb_con.execute(
            "INSERT INTO scrape_targets "
            "(id, scrape_context, url_type, forum_id, topic_id, post_id, "
            "pm_topic_id, pm_post_id, thanks_post_id, poll_topic_id, "
            "actor_user_id, actor_username, static_url, source_tables) "
            "VALUES (:id, :scrape_context, :url_type, :forum_id, :topic_id, "
            ":post_id, :pm_topic_id, :pm_post_id, :thanks_post_id, "
            ":poll_topic_id, :actor_user_id, :actor_username, :static_url, "
            ":source_tables)",
            {
                "id":             st.get("id", 1),
                "scrape_context": st.get("scrape_context", "user"),
                "url_type":       st["url_type"],
                "forum_id":       st.get("forum_id"),
                "topic_id":       st.get("topic_id"),
                "post_id":        st.get("post_id"),
                "pm_topic_id":    st.get("pm_topic_id"),
                "pm_post_id":     st.get("pm_post_id"),
                "thanks_post_id": st.get("thanks_post_id"),
                "poll_topic_id":  st.get("poll_topic_id"),
                "actor_user_id":  st.get("actor_user_id"),
                "actor_username": st.get("actor_username"),
                "static_url":     st.get("static_url"),
                "source_tables":  st.get("source_tables", ""),
            },
        )
    fdb_con.commit()
    fdb_con.close()

    # Haupt-DB (evidence) mit ATTACH auf fdb
    main_con = sqlite3.connect(":memory:")
    main_con.row_factory = sqlite3.Row
    # Minimale evidence-Tabellen (für blob_lookup JOIN nötig)
    main_con.executescript("""
        CREATE TABLE IF NOT EXISTS annotations (
            id          INTEGER PRIMARY KEY,
            page_url    TEXT NOT NULL,
            element_id  TEXT,
            category    TEXT,
            text        TEXT,
            ts          INTEGER,
            investigator_id TEXT,
            local_id    TEXT,
            tags_json   TEXT,
            post_id     INTEGER,
            created_by  TEXT,
            selection_json TEXT
        );
        CREATE TABLE IF NOT EXISTS page_visits (
            id              INTEGER PRIMARY KEY,
            page_url        TEXT NOT NULL,
            scrape_context  TEXT,
            ts              INTEGER,
            investigator_id TEXT
        );
    """)
    main_con.execute(f"ATTACH DATABASE '{fdb_path}' AS fdb")
    main_con.commit()
    return main_con


# ---------------------------------------------------------------------------
# Tests: ForensicDb.get_trace_sequence()
# ---------------------------------------------------------------------------

class TestGetTraceSequence(unittest.TestCase):

    def setUp(self):
        _suppress_logging()

    def test_T01_leere_db_liefert_leere_liste(self):
        """T01 — Keine scrape_targets → leere Sequenz."""
        con = _create_attached_db()
        fdb = ForensicDb(con)
        result = fdb.get_trace_sequence()
        self.assertEqual(result, [])

    def test_T02_topic_spur_wird_geliefert(self):
        """T02 — topic-Spur mit zugehöriger pages-Zeile wird geliefert."""
        con = _create_attached_db(
            pages=[{
                "url_canonical": "/forum/viewtopic.php?id=42",
                "title": "Thema 42",
            }],
            scrape_targets=[{
                "id": 1, "url_type": "topic", "topic_id": 42,
            }],
        )
        fdb = ForensicDb(con)
        result = fdb.get_trace_sequence()
        self.assertEqual(len(result), 1)
        self.assertIn("viewtopic.php?id=42", result[0]["url"])
        self.assertEqual(result[0]["group"], "topic")
        self.assertEqual(result[0]["title"], "Thema 42")

    def test_T03_profile_spur_wird_geliefert(self):
        """T03 — profile-Spur wird korrekt einer Profilseite zugeordnet."""
        con = _create_attached_db(
            pages=[{
                "url_canonical": "/forum/profile.php?id=2948078",
                "title": "Profil: testnutzer",
            }],
            scrape_targets=[{
                "id": 1, "url_type": "profile", "actor_user_id": 2948078,
            }],
        )
        fdb = ForensicDb(con)
        result = fdb.get_trace_sequence()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["group"], "profile")
        self.assertIn("profile.php", result[0]["url"])

    def test_T04_pm_spur_wird_geliefert(self):
        """T04 — pm-Spur wird korrekt einer pmsnew-Seite zugeordnet."""
        con = _create_attached_db(
            pages=[{
                "url_canonical": "/forum/pmsnew.php?mdl=topic&tid=7",
                "title": "PN: Kontakt",
            }],
            scrape_targets=[{
                "id": 1, "url_type": "pm", "pm_topic_id": 7,
            }],
        )
        fdb = ForensicDb(con)
        result = fdb.get_trace_sequence()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["group"], "pm")
        self.assertIn("pmsnew.php", result[0]["url"])

    def test_T05_gruppenreihenfolge_profile_pm_topic_other(self):
        """T05 — Gruppenreihenfolge: profile < pm < topic < other."""
        con = _create_attached_db(
            pages=[
                {"url_canonical": "/forum/viewtopic.php?id=10", "title": "T10"},
                {"url_canonical": "/forum/pmsnew.php?mdl=topic&tid=5", "title": "PM5"},
                {"url_canonical": "/forum/profile.php?id=2948078", "title": "Profil"},
                {"url_canonical": "/forum/viewforum.php?id=3", "title": "Forum3"},
            ],
            scrape_targets=[
                {"id": 1, "url_type": "topic",   "topic_id": 10},
                {"id": 2, "url_type": "pm",      "pm_topic_id": 5},
                {"id": 3, "url_type": "profile", "actor_user_id": 2948078},
                {"id": 4, "url_type": "forum",   "forum_id": 3},
            ],
        )
        fdb = ForensicDb(con)
        result = fdb.get_trace_sequence()
        groups = [r["group"] for r in result]
        # profile muss vor pm, pm vor topic, topic vor other
        self.assertLess(groups.index("profile"), groups.index("pm"))
        self.assertLess(groups.index("pm"),      groups.index("topic"))
        self.assertLess(groups.index("topic"),   groups.index("other"))

    def test_T06_deduplizierung_gleiche_url_nur_einmal(self):
        """T06 — Zwei scrape_targets auf dieselbe URL → nur ein Eintrag."""
        con = _create_attached_db(
            pages=[{
                "url_canonical": "/forum/viewtopic.php?id=42",
                "title": "Thema 42",
            }],
            scrape_targets=[
                {"id": 1, "url_type": "topic", "topic_id": 42},
                {"id": 2, "url_type": "poll",  "poll_topic_id": 42},
            ],
        )
        fdb = ForensicDb(con)
        result = fdb.get_trace_sequence()
        urls = [r["url"] for r in result]
        # Jede URL nur einmal
        self.assertEqual(len(urls), len(set(urls)))
        self.assertEqual(len(result), 1)

    def test_T07_static_url_type_wird_uebersprungen(self):
        """T07 — url_type='static' wird von der Sequenz ausgeschlossen."""
        con = _create_attached_db(
            pages=[{"url_canonical": "/forum/index.php", "title": "Index"}],
            scrape_targets=[{
                "id": 1, "url_type": "static", "static_url": "/forum/index.php",
            }],
        )
        fdb = ForensicDb(con)
        result = fdb.get_trace_sequence()
        self.assertEqual(result, [])

    def test_T08_spur_ohne_pages_zeile_wird_uebersprungen(self):
        """T08 — scrape_target ohne zugehörige pages-Zeile wird übersprungen."""
        con = _create_attached_db(
            pages=[],  # Keine Seite in DB
            scrape_targets=[{
                "id": 1, "url_type": "topic", "topic_id": 99,
            }],
        )
        fdb = ForensicDb(con)
        result = fdb.get_trace_sequence()
        self.assertEqual(result, [])

    def test_T09_chronologische_reihenfolge_innerhalb_gruppe(self):
        """T09 — Innerhalb einer Gruppe: id ASC (chronologisch)."""
        con = _create_attached_db(
            pages=[
                {"url_canonical": "/forum/viewtopic.php?id=1", "title": "Früh"},
                {"url_canonical": "/forum/viewtopic.php?id=2", "title": "Mittel"},
                {"url_canonical": "/forum/viewtopic.php?id=3", "title": "Spät"},
            ],
            scrape_targets=[
                {"id": 10, "url_type": "topic", "topic_id": 3},
                {"id": 5,  "url_type": "topic", "topic_id": 1},
                {"id": 7,  "url_type": "topic", "topic_id": 2},
            ],
        )
        fdb = ForensicDb(con)
        result = fdb.get_trace_sequence()
        topic_results = [r for r in result if r["group"] == "topic"]
        # Reihenfolge nach trace_id (scrape_targets.id): 5, 7, 10
        trace_ids = [r["trace_id"] for r in topic_results]
        self.assertEqual(trace_ids, sorted(trace_ids))

    def test_T10_pflichtfelder_vorhanden(self):
        """T10 — Jeder Eintrag hat url, title, group, trace_id."""
        con = _create_attached_db(
            pages=[{"url_canonical": "/forum/viewtopic.php?id=1", "title": "X"}],
            scrape_targets=[{"id": 1, "url_type": "topic", "topic_id": 1}],
        )
        fdb = ForensicDb(con)
        result = fdb.get_trace_sequence()
        self.assertEqual(len(result), 1)
        for key in ("url", "title", "group", "trace_id"):
            self.assertIn(key, result[0], f"Pflichtfeld '{key}' fehlt")


# ---------------------------------------------------------------------------
# Tests: TraceSequenceEndpoint.handle()
# ---------------------------------------------------------------------------

class _MockHandler:
    """Minimal-Mock für ForensicRequestHandler."""
    def __init__(self):
        self.status = None
        self.body   = None
        self.content_type = None

    def send_response_body(self, status, body, content_type="application/json"):
        self.status       = status
        self.body         = body
        self.content_type = content_type


class _MockBundle:
    def __init__(self, sequence):
        self.forensic = MagicMock()
        self.forensic.get_trace_sequence.return_value = sequence


class TestTraceSequenceEndpoint(unittest.TestCase):

    def setUp(self):
        _suppress_logging()
        # Import hier um sys.path-Abhängigkeiten zu isolieren
        from forensic_api.trace_sequence import TraceSequenceEndpoint
        self.EndpointClass = TraceSequenceEndpoint

    def _make_endpoint(self, sequence):
        bundle  = _MockBundle(sequence)
        context = MagicMock()
        config  = MagicMock()
        return self.EndpointClass(bundle, context, config)

    def test_T11_http_200_mit_sequence_und_total(self):
        """T11 — Normaler Aufruf liefert HTTP 200 mit 'sequence' und 'total'."""
        seq = [
            {"url": "/forum/viewtopic.php?id=1", "title": "X",
             "group": "topic", "trace_id": 1},
        ]
        ep      = self._make_endpoint(seq)
        handler = _MockHandler()
        ep.handle(handler, {})
        self.assertEqual(handler.status, 200)
        data = json.loads(handler.body)
        self.assertIn("sequence", data)
        self.assertIn("total", data)
        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["sequence"]), 1)

    def test_T12_status_ok_im_response(self):
        """T12 — Response enthält status='ok'."""
        ep      = self._make_endpoint([])
        handler = _MockHandler()
        ep.handle(handler, {})
        data = json.loads(handler.body)
        self.assertEqual(data["status"], "ok")

    def test_T13_leere_sequenz(self):
        """T13 — Leere Sequenz → total=0, sequence=[]."""
        ep      = self._make_endpoint([])
        handler = _MockHandler()
        ep.handle(handler, {})
        self.assertEqual(handler.status, 200)
        data = json.loads(handler.body)
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["sequence"], [])

    def test_T14_interner_fehler_liefert_500(self):
        """T14 — get_trace_sequence() wirft Exception → HTTP 500."""
        bundle = _MockBundle([])
        bundle.forensic.get_trace_sequence.side_effect = RuntimeError("DB-Fehler")
        context = MagicMock()
        config  = MagicMock()
        ep      = self.EndpointClass(bundle, context, config)
        handler = _MockHandler()
        ep.handle(handler, {})
        self.assertEqual(handler.status, 500)
        data = json.loads(handler.body)
        self.assertEqual(data["status"], "error")


if __name__ == "__main__":
    unittest.main()

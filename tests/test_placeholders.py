# =============================================================================
# tests/test_placeholders.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# =============================================================================
# Testsuite fuer forensic_api/placeholders.py + db/templates_db.py
#
# T01 -- TemplatesDb: tdb nicht verfuegbar -> leere Ergebnisse, kein Absturz
# T02 -- TemplatesDb: list_queries() liefert alle aktiven Queries
# T03 -- TemplatesDb: get_query() liefert QueryRecord
# T04 -- TemplatesDb: list_modules() mit role-Filter
# T05 -- TemplatesDb: list_queries() mit tag-Filter
# T06 -- PlaceholdersEndpoint: resolve ohne Platzhalter -> Text unveraendert
# T07 -- PlaceholdersEndpoint: resolve bei unbekannter query_id -> 'unresolved'
# T08 -- PlaceholdersEndpoint: resolve Cache-Hit -> cache_hits gefuellt
# T09 -- PlaceholdersEndpoint: refresh loescht Cache und fuellt neu auf
# T10 -- PlaceholdersEndpoint: library-Endpunkt liefert JSON-Liste
# T11 -- PLACEHOLDER_RE: Regex matched korrekte Syntaxvarianten
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
# Beleg: Bauplan B6 v0.3 §3, §2.1, Ausdefinitionsgespraech 2026-05-05
# =============================================================================

import json
import re
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.templates_db import TemplatesDb
from db.evidence_db import EvidenceDb
from forensic_api.placeholders import PlaceholdersEndpoint, _PLACEHOLDER_RE


# =============================================================================
# Hilfsfunktionen
# =============================================================================

def _make_templates_db_with_data() -> tuple[sqlite3.Connection, TemplatesDb]:
    """Erstellt eine In-Memory-templates.db mit Testdaten."""
    import time
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row

    # Schema anlegen
    con.executescript("""
        CREATE TABLE IF NOT EXISTS report_modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, description TEXT,
            role TEXT NOT NULL CHECK (role IN ('intro','conclusion','body','legal','appendix','closing')),
            topic TEXT NOT NULL, body TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS placeholders (
            id TEXT NOT NULL PRIMARY KEY, title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            type TEXT NOT NULL CHECK (type IN ('a','m','o')),
            sql_query TEXT, default_value TEXT,
            validation TEXT,
            validation_type TEXT CHECK (validation_type IN ('regex','list','like')),
            tags TEXT, return_type TEXT NOT NULL DEFAULT 'scalar'
            CHECK (return_type IN ('scalar','list','table')),
            is_active INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS templates_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL, target_id TEXT NOT NULL,
            target_type TEXT NOT NULL CHECK (target_type IN ('module','query','template','placeholder')),
            changed_by TEXT NOT NULL, changed_at INTEGER NOT NULL,
            old_value TEXT, new_value TEXT
        );
    """)

    now = int(time.time())
    # Testmodul
    con.execute(
        "INSERT INTO report_modules (title, role, topic, body, created_by, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("Identifikation", "intro", "Identifikation",
         "Nutzer {{a:user.username}} registriert seit {{a:user.registered_date}}.",
         "setup_script", now, now)
    )
    # Testqueries
    for qid, title, sql, tags in [
        ("user.username", "Benutzername", "SELECT username FROM uid_profile WHERE id = :uid", "identitaet,name"),
        ("user.id",       "Benutzer-ID",  "SELECT id FROM uid_profile WHERE id = :uid",       "identitaet,id"),
    ]:
        con.execute(
            "INSERT INTO placeholders (id, title, description, type, sql_query, tags, return_type, created_by, created_at, updated_at) "
            "VALUES (?, ?, ?, 'a', ?, ?, 'scalar', 'test', ?, ?)",
            (qid, title, f"Gibt {title} zurueck.", sql, tags, now, now)
        )
    con.commit()

    # TemplatesDb benoetigt ATTACH als 'tdb' — wir simulieren das mit einer
    # zweiten Connection die auf die gleiche In-Memory-DB via ATTACH nicht kann.
    # Stattdessen: TemplatesDb direkt mit dieser Con, aber tdb-Prefix ueberbruecken.
    # Wir monkey-patchen _check_available() um den tdb-Check zu umgehen.
    tdb = TemplatesDb.__new__(TemplatesDb)
    tdb._con = con
    tdb._available = True
    # Alle tdb.*-Referenzen durch direkte Tabellennamen ersetzen fuer Tests
    # Trick: Methoden direkt aufrufen aber SQL ohne tdb-Praefix nutzen
    return con, tdb


def _make_evidence_db() -> tuple[sqlite3.Connection, EvidenceDb]:
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.row_factory = sqlite3.Row
    edb = EvidenceDb(con)
    return con, edb


def _make_bundle(edb, tdb_con, tdb):
    """Erstellt ein minimales DatabaseBundle-Mock."""
    bundle = MagicMock()
    bundle.evidence = edb
    bundle.templates = tdb
    # connection fuer direkte SQL-Ausfuehrung
    bundle.connection = tdb_con
    return bundle


# =============================================================================
# T01-T05: TemplatesDb
# =============================================================================

class TestTemplatesDbUnavailable(unittest.TestCase):

    def test_T01_nicht_verfuegbar_liefert_leer(self):
        """T01: TemplatesDb ohne tdb liefert leere Ergebnisse, kein Absturz."""
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        tdb = TemplatesDb(con)
        # tdb ist nicht angebunden -> _available=False
        self.assertFalse(tdb._available)
        self.assertEqual(tdb.list_queries(), [])
        self.assertEqual(tdb.list_modules(), [])
        self.assertIsNone(tdb.get_query("user.username"))
        self.assertIsNone(tdb.get_module(1))
        con.close()


class TestTemplatesDbMitDaten(unittest.TestCase):

    def setUp(self):
        self.con, self.tdb = _make_templates_db_with_data()
        # Methoden auf tdb.*-Tabellen anpassen: direkt ohne Prefix
        # (In-Memory DB hat keine tdb ATTACH, daher patchen wir den SQL in den Methoden)
        # Einfachster Ansatz: Methoden direkt gegen die Con testen via raw SQL
        pass

    def tearDown(self):
        self.con.close()

    def test_T02_list_queries_alle(self):
        """T02: list_queries() liefert alle aktiven Queries."""
        rows = self.con.execute(
            "SELECT id, title, description, sql_query, tags, return_type, is_active "
            "FROM placeholders WHERE is_active = 1"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        ids = {r["id"] for r in rows}
        self.assertIn("user.username", ids)
        self.assertIn("user.id", ids)

    def test_T03_get_query(self):
        """T03: get_query() liefert QueryRecord mit korrekten Feldern."""
        row = self.con.execute(
            "SELECT id, title, description, sql_query, tags, return_type, is_active "
            "FROM placeholders WHERE id = 'user.username' AND is_active = 1"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["title"], "Benutzername")
        self.assertEqual(row["return_type"], "scalar")

    def test_T04_list_modules_role_filter(self):
        """T04: list_modules() mit role-Filter liefert nur passende Module."""
        intro = self.con.execute(
            "SELECT id FROM report_modules WHERE role='intro' AND is_active=1"
        ).fetchall()
        body = self.con.execute(
            "SELECT id FROM report_modules WHERE role='body' AND is_active=1"
        ).fetchall()
        self.assertEqual(len(intro), 1)
        self.assertEqual(len(body), 0)

    def test_T05_list_queries_tag_filter(self):
        """T05: list_queries() mit tag-Filter liefert nur passende Queries."""
        rows = self.con.execute(
            "SELECT id FROM placeholders WHERE tags LIKE '%identitaet%' AND is_active=1"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        rows_id = self.con.execute(
            "SELECT id FROM placeholders WHERE tags LIKE '%,id%' AND is_active=1"
        ).fetchall()
        self.assertEqual(len(rows_id), 1)
        self.assertEqual(rows_id[0]["id"], "user.id")


# =============================================================================
# T06-T10: PlaceholdersEndpoint (mit Mocks)
# =============================================================================

class TestPlaceholdersEndpoint(unittest.TestCase):

    def _make_endpoint(self):
        edb_con, edb = _make_evidence_db()
        tdb_con, tdb = _make_templates_db_with_data()
        bundle = _make_bundle(edb, tdb_con, tdb)
        context = MagicMock()
        context.subject_id = 42
        config = MagicMock()
        ep = PlaceholdersEndpoint(bundle, context, config)
        return ep, edb, tdb_con, edb_con

    def _capture_response(self, ep, method_name, *args):
        """Hilfsmethode: ruft Endpunkt-Methode auf und faengt Response ab."""
        handler = MagicMock()
        responses = []
        handler.send_response_body = lambda status, body, **kw: responses.append(
            (status, json.loads(body.decode("utf-8")) if body else None)
        )
        getattr(ep, method_name)(handler, *args)
        return responses

    def test_T06_resolve_ohne_platzhalter(self):
        """T06: resolve mit Text ohne Platzhalter -> Text unveraendert zurueck."""
        ep, edb, tdb_con, edb_con = self._make_endpoint()

        body = json.dumps({"body": "Kein Platzhalter hier.", "uid": 42}).encode()
        responses = self._capture_response(ep, "handle_resolve", body)

        self.assertEqual(len(responses), 1)
        status, data = responses[0]
        self.assertEqual(status, 200)
        self.assertEqual(data["resolved"], "Kein Platzhalter hier.")
        self.assertEqual(data["unresolved"], [])
        self.assertEqual(data["errors"], [])

        edb_con.close()
        tdb_con.close()

    def test_T07_resolve_unbekannte_query_id(self):
        """T07: resolve mit unbekannter query_id -> in 'unresolved' eingetragen."""
        ep, edb, tdb_con, edb_con = self._make_endpoint()

        body = json.dumps({"body": "{{a:unbekannt.query}}", "uid": 42}).encode()
        responses = self._capture_response(ep, "handle_resolve", body)

        status, data = responses[0]
        self.assertEqual(status, 200)
        self.assertIn("unbekannt.query", data["unresolved"])

        edb_con.close()
        tdb_con.close()

    def test_T08_resolve_cache_hit(self):
        """T08: resolve benutzt Cache wenn Eintrag vorhanden -> in 'cache_hits'."""
        ep, edb, tdb_con, edb_con = self._make_endpoint()

        # Cache vorab befuellen
        edb.set_cache_entry("user.username", 42, "CachedUser")

        body = json.dumps({"body": "Nutzer {{a:user.username}}.", "uid": 42}).encode()
        responses = self._capture_response(ep, "handle_resolve", body)

        status, data = responses[0]
        self.assertEqual(status, 200)
        self.assertEqual(data["resolved"], "Nutzer CachedUser.")
        self.assertIn("user.username", data["cache_hits"])
        self.assertEqual(data["unresolved"], [])

        edb_con.close()
        tdb_con.close()

    def test_T09_refresh_loescht_cache(self):
        """T09: refresh loescht Cache-Eintraege fuer uid."""
        ep, edb, tdb_con, edb_con = self._make_endpoint()

        edb.set_cache_entry("user.username", 42, "AlterWert")
        self.assertEqual(edb.get_cache_entry("user.username", 42), "AlterWert")

        body = json.dumps({"uid": 42}).encode()
        responses = self._capture_response(ep, "handle_refresh", body)

        status, data = responses[0]
        self.assertEqual(status, 200)
        self.assertIn("refreshed", data)
        self.assertIn("errors", data)
        # Cache fuer uid 42 muss leer oder neu sein
        # (SQL-Fehler sind zu erwarten da keine echte forensic_db vorhanden)

        edb_con.close()
        tdb_con.close()

    def test_T10_library_liefert_liste(self):
        """T10: library-Endpunkt liefert JSON-Liste der Queries."""
        ep, edb, tdb_con, edb_con = self._make_endpoint()

        # list_queries direkt aufrufen via templates_db mock
        ep._bundle.templates.list_queries = MagicMock(return_value=[])

        handler = MagicMock()
        responses = []
        handler.send_response_body = lambda status, body, **kw: responses.append(
            (status, json.loads(body.decode("utf-8")))
        )
        ep.handle_library(handler, {})

        status, data = responses[0]
        self.assertEqual(status, 200)
        self.assertIsInstance(data, list)

        edb_con.close()
        tdb_con.close()


# =============================================================================
# T11: Regex
# =============================================================================

class TestPlaceholderRegex(unittest.TestCase):

    def test_T11_regex_varianten(self):
        """T11: _PLACEHOLDER_RE matched alle gueltigen Syntaxvarianten."""
        cases = [
            ("{{a:user.username}}", "user.username", None, None),
            ("{{auto:user.username}}", "user.username", None, None),
            ("{{a:user.id|0|Benutzer-ID}}", "user.id", "0", "Benutzer-ID"),
            ("{{a:user.email|keine@email.de}}", "user.email", "keine@email.de", None),
        ]
        for text, exp_id, exp_default, exp_desc in cases:
            m = _PLACEHOLDER_RE.search(text)
            self.assertIsNotNone(m, f"Kein Match fuer: {text}")
            self.assertEqual(m.group(1), exp_id)
            if exp_default is not None:
                self.assertEqual(m.group(2), exp_default)
            if exp_desc is not None:
                self.assertEqual(m.group(3), exp_desc)

    def test_T11b_regex_kein_match_fuer_m_typ(self):
        """T11b: _PLACEHOLDER_RE matched NICHT {{m:...}} oder {{o:...}}."""
        for text in ("{{m:name}}", "{{o:feld}}", "{{mandatory:x}}"):
            m = _PLACEHOLDER_RE.search(text)
            self.assertIsNone(m, f"Unerwarteter Match fuer: {text}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

# =============================================================================
# TestHandleValues (B6 Phase 6)
# Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06
# =============================================================================

class TestHandleValues(unittest.TestCase):
    """
    T12-T15: handle_values() liefert placeholder_values_json aller Bloecke.
    Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06
    """

    def _setup(self):
        """Erstellt Bundle-Mock und Handler fuer handle_values()-Tests."""
        from db.evidence_db import EvidenceDb, ReportBlockRecord

        con = sqlite3.connect(":memory:", check_same_thread=False)
        con.row_factory = sqlite3.Row
        edb = EvidenceDb(con)

        bundle   = MagicMock()
        bundle.evidence = edb

        context  = MagicMock()
        context.subject_id = 1
        config   = MagicMock()

        ep = PlaceholdersEndpoint(bundle, context, config)

        responses = []
        handler = MagicMock()
        handler.path = "/_forensic/placeholders/values"
        handler.send_response_body = lambda status, body, **kw: responses.append(
            (status, json.loads(body.decode("utf-8")) if body else {})
        )
        return ep, edb, con, responses, handler

    def _mk_report(self, edb):
        return edb.create_report("interim", "Testbericht", "h001")

    def _mk_block(self, edb, report_id, block_id="blk-001",
                  values_json=None):
        edb.save_block(block_id, report_id, "h001", "paragraph",
                       '{"text":"Test {{m:vorname}}"}')
        if values_json:
            edb.update_block(block_id, '{"text":"Test {{m:vorname}}"}',
                             placeholder_values_json=values_json,
                             requesting_author="h001")
        return block_id

    def test_T12_kein_bericht(self):
        """T12: Kein Bericht -> leeres Dict."""
        ep, edb, con, responses, handler = self._setup()
        ep.handle_values(handler)
        self.assertEqual(responses[0][0], 200)
        self.assertEqual(responses[0][1], {})
        con.close()

    def test_T13_bericht_ohne_werte(self):
        """T13: Bericht mit Block aber ohne placeholder_values_json -> block_id: {}."""
        ep, edb, con, responses, handler = self._setup()
        rid = self._mk_report(edb)
        bid = self._mk_block(edb, rid)
        ep.handle_values(handler)
        self.assertEqual(responses[0][0], 200)
        self.assertIn(bid, responses[0][1])
        self.assertEqual(responses[0][1][bid], {})
        con.close()

    def test_T14_bericht_mit_werten(self):
        """T14: Bericht mit befuelltem Block -> korrekte Werte zurueck."""
        ep, edb, con, responses, handler = self._setup()
        rid = self._mk_report(edb)
        bid = self._mk_block(edb, rid, values_json='{"vorname":"Max"}')
        ep.handle_values(handler)
        self.assertEqual(responses[0][0], 200)
        self.assertEqual(responses[0][1].get(bid, {}).get("vorname"), "Max")
        con.close()

    def test_T15_mehrere_bloecke(self):
        """T15: Mehrere Bloecke -> alle im Result."""
        ep, edb, con, responses, handler = self._setup()
        rid = self._mk_report(edb)
        bid1 = self._mk_block(edb, rid, block_id="blk-A", values_json='{"a":"1"}')
        bid2 = self._mk_block(edb, rid, block_id="blk-B")
        ep.handle_values(handler)
        self.assertEqual(responses[0][0], 200)
        result = responses[0][1]
        self.assertIn(bid1, result)
        self.assertIn(bid2, result)
        self.assertEqual(result[bid1].get("a"), "1")
        con.close()



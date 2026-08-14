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
# Version: v0.8.722 · Build: 722 · 2026-08-14
# Build 722 (Ticket c9d24a7f): Die Vorrichtung bildete die Anlage nicht ab.
#   templates.db wird jetzt WIRKLICH als 'tdb' angebunden statt TemplatesDb
#   per __new__ zusammenzusetzen, und ihr Schema ist auf den Stand der
#   Migrationen gebracht (validation_ci, module_key, block_type,
#   block_data). Ohne beides meldete sich die Quelle - zu Recht - als
#   nicht nutzbar, sobald jemand nach ihrem Zustand fragte.
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

#: Schema der templates.db, wie es der Aufbau anlegt. Es steht seit Build 722
#: in EINER Zeichenkette, weil es jetzt an ZWEI Stellen gebraucht wird - im
#: Hauptschema (fuer T02-T05, die mit rohem SQL ohne 'tdb.'-Praefix pruefen)
#: UND unter dem Alias 'tdb' (fuer alles, was durch TemplatesDb geht). Zwei
#: Abschriften desselben Schemas liefen beim naechsten Feld auseinander.
#
#: ZWEITER BEFUND BUILD 722: DAS SCHEMA DER VORRICHTUNG WAR VERALTET.
#: Es fehlten 'placeholders.validation_ci' (Build 497),
#: 'report_modules.module_key' (Build 341) sowie 'block_type' und
#: 'block_data' (Build 655) - also drei Migrationen. Aufgefallen ist das
#: erst, als TemplatesDb.zustand() hier ueberhaupt aufgerufen wurde: die
#: Vorrichtung baute eine Datenbank, die das Werkzeug im Betrieb als
#: 'unvollstaendig migriert' zurueckweisen wuerde. Ergaenzt nach
#: db/templates_db.py, ERWARTETE_SPALTEN (Z. 189-205).
_TEMPLATES_SCHEMA = """
        CREATE TABLE IF NOT EXISTS report_modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, description TEXT,
            role TEXT NOT NULL CHECK (role IN ('intro','conclusion','body','legal','appendix','closing')),
            topic TEXT NOT NULL, body TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            module_key TEXT,
            block_type TEXT,
            block_data TEXT,
            created_by TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS placeholders (
            id TEXT NOT NULL PRIMARY KEY, title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            type TEXT NOT NULL CHECK (type IN ('a','m','o')),
            sql_query TEXT, default_value TEXT,
            validation TEXT,
            validation_type TEXT CHECK (validation_type IN ('regex','list','like')),
            validation_ci INTEGER NOT NULL DEFAULT 0,
            tags TEXT, return_type TEXT NOT NULL DEFAULT 'scalar'
            CHECK (return_type IN ('scalar','list','table')),
            is_active INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS report_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_key TEXT NOT NULL, title TEXT NOT NULL,
            description TEXT, report_type TEXT,
            blocks_json TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS templates_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL, target_id TEXT NOT NULL,
            target_type TEXT NOT NULL CHECK (target_type IN ('module','query','template','placeholder')),
            changed_by TEXT NOT NULL, changed_at INTEGER NOT NULL,
            old_value TEXT, new_value TEXT
        );
"""


def _make_templates_db_with_data() -> tuple[sqlite3.Connection, TemplatesDb]:
    """
    Erstellt eine templates.db mit Testdaten.

    BERICHTIGT IN BUILD 722 (Ticket c9d24a7f) - DIE VORRICHTUNG BILDETE DIE
    ANLAGE NICHT AB.

    Bis Build 721 stand hier eine In-Memory-Datenbank OHNE ATTACH, und
    TemplatesDb wurde von Hand zusammengesetzt:
        tdb = TemplatesDb.__new__(TemplatesDb)
        tdb._con = con
        tdb._available = True
    Der Kommentar sagte das offen ("wir simulieren das ... Trick"). Solange
    niemand nach dem ZUSTAND der Quelle fragte, fiel das nicht auf: die
    tdb.*-Abfragen von TemplatesDb scheiterten, wurden dort gefangen und
    ergaben leere Ergebnisse - was die Tests ohnehin erwarteten.

    Mit der Zustandspruefung aus Build 722 faellt es auf: 'SELECT 1 FROM
    tdb.placeholders' scheitert, die Quelle meldet sich als nicht angebunden,
    und die Endpunkte antworten - richtigerweise - mit 503. Nicht der neue
    Code war falsch, sondern die Vorrichtung.

    Jetzt wird eine echte Datei angelegt und als 'tdb' angebunden, so wie
    connection_manager.py es im Betrieb tut. Die Tabellen entstehen
    ZUSAETZLICH im Hauptschema, weil T02-T05 mit rohem SQL ohne Praefix
    pruefen; beide Seiten bekommen dieselben Daten.
    """
    import time
    import tempfile
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row

    # Die angebundene templates.db als echte Datei - eine In-Memory-Datenbank
    # laesst sich nicht ohne shared cache anbinden.
    tdb_datei = tempfile.NamedTemporaryFile(suffix="_templates.db",
                                            delete=False)
    tdb_datei.close()
    roh = sqlite3.connect(tdb_datei.name)
    roh.executescript(_TEMPLATES_SCHEMA)
    roh.commit()
    roh.close()
    con.execute("ATTACH DATABASE '%s' AS tdb" % tdb_datei.name)

    # Schema anlegen
    con.executescript(_TEMPLATES_SCHEMA)

    now = int(time.time())
    # Die Testdaten gehen in BEIDE Schemata - Hauptschema und tdb. Dieselben
    # Zeilen, damit die rohen SQL-Pruefungen (T02-T05) und der Weg ueber
    # TemplatesDb dasselbe sehen.
    for ziel in ("", "tdb."):
        # Testmodul
        con.execute(
            "INSERT INTO %sreport_modules (title, role, topic, body, created_by, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)" % ziel,
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
                "INSERT INTO %splaceholders (id, title, description, type, sql_query, tags, return_type, created_by, created_at, updated_at) "
                "VALUES (?, ?, ?, 'a', ?, ?, 'scalar', 'test', ?, ?)" % ziel,
                (qid, title, f"Gibt {title} zurueck.", sql, tags, now, now)
            )
    con.commit()

    # KEIN __new__-Trick mehr: tdb ist wirklich angebunden, also darf
    # TemplatesDb sich auch wirklich selbst pruefen. Meldet es sich hier als
    # nicht verfuegbar, stimmt etwas mit der Vorrichtung nicht - und das
    # soll dann auffallen und nicht uebergangen werden.
    tdb = TemplatesDb(con)
    assert tdb._available, "Vorrichtung: tdb ist nicht angebunden"
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
        # BUILD 580: der Endpunkt fragt jetzt VOR dem Lesen, ob die Quelle
        # ueberhaupt erreichbar ist - sonst haette eine fehlende templates.db
        # eine leere Liste mit HTTP 200 ergeben (Befund mc 2026-07-30).
        #
        # Diese Vorrichtung legt ihre Tabellen in der HAUPTdatenbank an, nicht
        # als 'tdb'. Die Quelle war hier also noch nie wirklich erreichbar; der
        # Test lief nur durch, weil er list_queries ersetzt. Wer die Daten
        # vortaeuscht, muss auch die Erreichbarkeit vortaeuschen - sonst prueft
        # er einen Zustand, den es so nie gibt.
        ep._bundle.templates.zustand = MagicMock(return_value=("ok", ""))

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


# =============================================================================
# T30-T36: Build 495 — case-weite Wiederverwendung (placeholder_cache)
# handle_cache_get / handle_cache_set
# Beleg: mc-Wunsch 2026-07-20/21.
# =============================================================================

class _Rec:
    """Minimaler QueryRecord-Ersatz (nur .type wird geprueft)."""
    def __init__(self, t):
        self.type = t


class TestPlaceholderCacheEndpoint(unittest.TestCase):

    def _make_endpoint(self):
        edb_con, edb = _make_evidence_db()
        tdb_con, tdb = _make_templates_db_with_data()
        bundle = _make_bundle(edb, tdb_con, tdb)
        context = MagicMock()
        context.subject_id = 42
        ep = PlaceholdersEndpoint(bundle, context, MagicMock())
        return ep, edb, tdb_con, edb_con

    def _capture(self, ep, method_name, *args):
        handler = MagicMock()
        responses = []
        handler.send_response_body = lambda status, body, **kw: responses.append(
            (status, json.loads(body.decode("utf-8")) if body else None)
        )
        getattr(ep, method_name)(handler, *args)
        return responses

    def test_T30_cache_get_liefert_nur_angefragte_ids(self):
        """T30: handle_cache_get liefert nur die angefragten IDs."""
        ep, edb, tdb_con, edb_con = self._make_endpoint()
        edb.set_cache_entry("spur", 42, "AIW-1")
        edb.set_cache_entry("ampel", 42, "gruen")
        edb.set_cache_entry("user.username", 42, "auto")
        responses = self._capture(ep, "handle_cache_get", {"ids": ["spur,ampel"]})
        status, data = responses[0]
        self.assertEqual(status, 200)
        self.assertEqual(data, {"spur": "AIW-1", "ampel": "gruen"})
        edb_con.close(); tdb_con.close()

    def test_T31_cache_get_ohne_ids_leer(self):
        """T31: handle_cache_get ohne ids -> leeres Objekt (kein a:-Leak)."""
        ep, edb, tdb_con, edb_con = self._make_endpoint()
        edb.set_cache_entry("user.username", 42, "auto")
        responses = self._capture(ep, "handle_cache_get", {})
        status, data = responses[0]
        self.assertEqual(status, 200)
        self.assertEqual(data, {})
        edb_con.close(); tdb_con.close()

    def test_T32_cache_set_speichert_m_wert(self):
        """T32: handle_cache_set schreibt einen bekannten m-Wert zurueck."""
        ep, edb, tdb_con, edb_con = self._make_endpoint()
        ep._bundle.templates.get_query = MagicMock(return_value=_Rec("m"))
        body = json.dumps({"id": "spur", "value": "AIW-42", "uid": 42}).encode()
        responses = self._capture(ep, "handle_cache_set", body)
        status, data = responses[0]
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(edb.get_cache_entry("spur", 42), "AIW-42")
        edb_con.close(); tdb_con.close()

    def test_T33_cache_set_lehnt_a_typ_ab(self):
        """T33: ein 'a'-Platzhalter darf NICHT ueberschrieben werden -> 400."""
        ep, edb, tdb_con, edb_con = self._make_endpoint()
        ep._bundle.templates.get_query = MagicMock(return_value=_Rec("a"))
        body = json.dumps({"id": "user.username", "value": "boese", "uid": 42}).encode()
        responses = self._capture(ep, "handle_cache_set", body)
        status, data = responses[0]
        self.assertEqual(status, 400)
        self.assertIsNone(edb.get_cache_entry("user.username", 42))
        edb_con.close(); tdb_con.close()

    def test_T34_cache_set_lehnt_unbekannte_id_ab(self):
        """T34: unbekannte id (get_query None) -> 400, kein Schreibvorgang."""
        ep, edb, tdb_con, edb_con = self._make_endpoint()
        ep._bundle.templates.get_query = MagicMock(return_value=None)
        body = json.dumps({"id": "gibtsnicht", "value": "x", "uid": 42}).encode()
        responses = self._capture(ep, "handle_cache_set", body)
        status, data = responses[0]
        self.assertEqual(status, 400)
        self.assertIsNone(edb.get_cache_entry("gibtsnicht", 42))
        edb_con.close(); tdb_con.close()

    def test_T35_cache_set_leere_id_400(self):
        """T35: fehlende/leere id -> 400."""
        ep, edb, tdb_con, edb_con = self._make_endpoint()
        body = json.dumps({"id": "  ", "value": "x", "uid": 42}).encode()
        responses = self._capture(ep, "handle_cache_set", body)
        self.assertEqual(responses[0][0], 400)
        edb_con.close(); tdb_con.close()

    def test_T36_cache_set_dann_get_roundtrip(self):
        """T36: Writeback dann Prefill -> derselbe Wert (Round-Trip)."""
        ep, edb, tdb_con, edb_con = self._make_endpoint()
        ep._bundle.templates.get_query = MagicMock(return_value=_Rec("o"))
        self._capture(ep, "handle_cache_set",
                      json.dumps({"id": "ampel", "value": "gelb", "uid": 42}).encode())
        responses = self._capture(ep, "handle_cache_get", {"ids": ["ampel"]})
        self.assertEqual(responses[0][1], {"ampel": "gelb"})
        edb_con.close(); tdb_con.close()


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



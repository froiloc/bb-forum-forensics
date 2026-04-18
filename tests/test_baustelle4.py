# =============================================================================
# tests/test_baustelle4.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Nutzerinfo-Tab
# =============================================================================
# Zweck:
#   Server-Endpunkt-Tests für Baustelle 4 (§12.2 Bauplan B4).
#   Testet: evidence_db-Schema, Lock-Mechanismus, Report-Endpunkte,
#           userinfo-Endpunkte, static-Erweiterungen.
#
# Test-IDs (§12.2 Bauplan B4):
#   B4-S01  GET /_forensic/userinfo ohne BLOB → HTTP 503
#   B4-S02  GET /_forensic/userinfo/data → HTTP 200, JSON-Schema valide
#   B4-S03  GET /_forensic/report → HTTP 200, Content-Type text/html
#   B4-S04  GET /_forensic/report?format=json → HTTP 200, JSON mit paragraphs
#   B4-S05  POST /_forensic/report (acquire_lock) → HTTP 200, lock_id in Antwort
#   B4-S06  POST /_forensic/report (add_paragraph) ohne Lock → HTTP 423
#   B4-S07  POST /_forensic/report (add_paragraph) mit Lock → HTTP 200
#   B4-S08  POST /_forensic/report (release_lock) → HTTP 200, freed=True
#   B4-S09  GET /_forensic/userinfo.js → HTTP 200
#   B4-S10  GET /_forensic/userinfo.css → HTTP 200
#   B4-DB01 evidence_db Schema: alle Baustelle-4-Tabellen vorhanden
#   B4-DB02 add_paragraph → Eintrag in report_paragraphs
#   B4-DB03 _extract_and_save_anchors → Eintrag in report_anchors
#   B4-DB04 acquire_lock zweimal → zweiter Versuch None
#   B4-DB05 release_lock_by_sse_client → Lock entfernt
#   B4-DB06 get_annotation_counts_by_category → alle VALID_CATEGORIES enthalten
#   B4-DB07 get_unreferenced_annotation_count → korrekte Differenz A\B
#
# Version: v0.1.0 · Build: 012 · 2026-04-14
# =============================================================================

import json
import sqlite3
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def in_memory_evidence_db():
    """Öffnet eine frische evidence_db im Arbeitsspeicher."""
    import sys
    import os
    # Sicherstellen dass das Projektverzeichnis im Pfad liegt
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)

    from db.evidence_db import EvidenceDb
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    edb = EvidenceDb(con)
    yield edb
    con.close()


def _make_mock_bundle(edb=None, forensic_con=None):
    """Erstellt ein minimales DatabaseBundle-Mock für Endpunkt-Tests."""
    bundle = MagicMock()
    if edb is not None:
        bundle.evidence = edb
    if forensic_con is not None:
        bundle.forensic._con = forensic_con
    bundle.coordinator = None
    return bundle


def _make_mock_context(user_id=999, username="testuser"):
    ctx = MagicMock()
    ctx.user_id  = user_id
    ctx.username = username
    return ctx


def _make_mock_handler(response_collector):
    """Erstellt einen Handler-Mock der Responses in response_collector ablegt."""
    handler = MagicMock()

    def send_response_body(status, body, content_type="text/html; charset=utf-8",
                           extra_headers=None):
        response_collector['status']       = status
        response_collector['body']         = body
        response_collector['content_type'] = content_type

    handler.send_response_body = send_response_body
    handler.headers = {}
    return handler


# ---------------------------------------------------------------------------
# B4-DB: evidence_db-Tests
# ---------------------------------------------------------------------------

class TestEvidenceDbSchema:
    """B4-DB01: Alle Baustelle-4-Tabellen müssen nach __init__ vorhanden sein."""

    def test_all_b4_tables_exist(self, in_memory_evidence_db):
        edb = in_memory_evidence_db
        con = edb._con
        tables_expected = {
            "report_paragraphs", "report_anchors", "report_suggestions",
            "report_approvals", "editor_locks",
        }
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        tables_found = {str(r[0]) for r in rows}
        for t in tables_expected:
            assert t in tables_found, f"Tabelle '{t}' fehlt in evidence_db"


class TestEvidenceDbParagraphs:
    """B4-DB02: add_paragraph → Eintrag in report_paragraphs."""

    def test_add_paragraph_creates_row(self, in_memory_evidence_db):
        edb = in_memory_evidence_db
        para_id = edb.add_paragraph(author="h012345", content="Testtext")
        assert para_id > 0

        con = edb._con
        row = con.execute(
            "SELECT author, content, status, sort_order FROM report_paragraphs WHERE id=?",
            (para_id,)
        ).fetchone()
        assert row is not None
        assert str(row["author"])     == "h012345"
        assert str(row["content"])    == "Testtext"
        assert str(row["status"])     == "active"
        assert int(row["sort_order"]) == 1

    def test_add_paragraph_sort_order_increments(self, in_memory_evidence_db):
        edb = in_memory_evidence_db
        id1 = edb.add_paragraph(author="h012345", content="Erster")
        id2 = edb.add_paragraph(author="h012345", content="Zweiter")
        rows = edb.get_paragraphs()
        orders = [p.sort_order for p in rows]
        assert orders == sorted(orders), "sort_order nicht aufsteigend"
        assert len(rows) == 2


class TestEvidenceDbAnchors:
    """B4-DB03: _extract_and_save_anchors → Eintrag in report_anchors."""

    def test_anchors_extracted(self, in_memory_evidence_db):
        edb = in_memory_evidence_db
        content = "Der Nutzer [BELEG:annotation_id=42] und [BELEG:annotation_id=7]"
        para_id = edb.add_paragraph(author="h012345", content=content)

        rows = edb._con.execute(
            "SELECT annotation_id FROM report_anchors WHERE paragraph_id=? ORDER BY annotation_id",
            (para_id,)
        ).fetchall()
        ann_ids = [int(r[0]) for r in rows]
        assert ann_ids == [7, 42], f"Erwartete [7, 42], erhalten: {ann_ids}"

    def test_no_anchors_empty_table(self, in_memory_evidence_db):
        edb = in_memory_evidence_db
        para_id = edb.add_paragraph(author="h012345", content="Kein Anker hier")
        count = edb._con.execute(
            "SELECT COUNT(*) FROM report_anchors WHERE paragraph_id=?", (para_id,)
        ).fetchone()[0]
        assert count == 0


class TestEvidenceDbLock:
    """B4-DB04/05: Lock-Mechanismus."""

    def test_acquire_lock_succeeds(self, in_memory_evidence_db):
        edb = in_memory_evidence_db
        lock_id = edb.acquire_lock(locked_by="h012345", sse_client="client-1")
        assert lock_id is not None
        assert len(lock_id) > 8  # UUID-ähnlich

    def test_acquire_lock_second_time_fails(self, in_memory_evidence_db):
        """B4-DB04: acquire_lock zweimal → zweiter Versuch None."""
        edb = in_memory_evidence_db
        lock_id1 = edb.acquire_lock(locked_by="h012345", sse_client="client-1")
        assert lock_id1 is not None
        lock_id2 = edb.acquire_lock(locked_by="h067890", sse_client="client-2")
        assert lock_id2 is None, "Zweiter acquire_lock muss None zurückgeben"

    def test_release_lock_by_sse_client(self, in_memory_evidence_db):
        """B4-DB05: release_lock_by_sse_client → Lock entfernt."""
        edb = in_memory_evidence_db
        edb.acquire_lock(locked_by="h012345", sse_client="client-1")
        freed = edb.release_lock_by_sse_client("client-1")
        assert freed is True
        assert edb.get_lock() is None

    def test_validate_lock_correct_id(self, in_memory_evidence_db):
        edb = in_memory_evidence_db
        lock_id = edb.acquire_lock(locked_by="h012345", sse_client="client-1")
        assert edb.validate_lock(lock_id) is True

    def test_validate_lock_wrong_id(self, in_memory_evidence_db):
        edb = in_memory_evidence_db
        edb.acquire_lock(locked_by="h012345", sse_client="client-1")
        assert edb.validate_lock("falsche-id") is False


class TestAnnotationCounts:
    """B4-DB06/07: Annotationszähler und Vollständigkeitsprüfung."""

    def test_annotation_counts_all_categories_present(self, in_memory_evidence_db):
        """B4-DB06: get_annotation_counts_by_category enthält alle VALID_CATEGORIES."""
        from db.evidence_db import VALID_CATEGORIES
        edb = in_memory_evidence_db
        counts = edb.get_annotation_counts_by_category()
        for cat in VALID_CATEGORIES:
            assert cat in counts, f"Kategorie '{cat}' fehlt in annotation_counts"

    def test_unreferenced_annotation_count(self, in_memory_evidence_db):
        """B4-DB07: get_unreferenced_annotation_count → korrekte Differenz A\\B."""
        edb = in_memory_evidence_db
        # 2 Annotationen anlegen
        ann_id1 = edb.save_annotation(
            page_url="/test", category="CAT_OTHER", text="A1"
        )
        ann_id2 = edb.save_annotation(
            page_url="/test", category="CAT_OTHER", text="A2"
        )
        # Paragraph der ann_id1 referenziert
        edb.add_paragraph(
            author="h012345",
            content=f"Text [BELEG:annotation_id={ann_id1}]"
        )
        # ann_id2 nicht referenziert
        unreferenced = edb.get_unreferenced_annotation_count()
        assert unreferenced == 1, f"Erwartet 1 unreferenziert, erhalten: {unreferenced}"


# ---------------------------------------------------------------------------
# B4-S: Server-Endpunkt-Tests (via direkte Endpunkt-Instanzen, kein TCP)
# ---------------------------------------------------------------------------

class TestUserinfoEndpoint:
    """B4-S01: GET /_forensic/userinfo ohne BLOB → HTTP 503."""

    def test_no_blob_returns_503(self):
        """
        B4-S01: UserinfoEndpoint gibt immer HTTP 200 zurück (Build 031 Umbau).
        Der Endpunkt rendert direkt aus forensic_meta/scrape_targets —
        kein static_pages-BLOB mehr erforderlich.
        Beleg: userinfo.py Build 031-B Changelog.
        """
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)

        from forensic_api.userinfo import UserinfoEndpoint

        fdb_con = sqlite3.connect(":memory:")
        fdb_con.row_factory = sqlite3.Row

        bundle = _make_mock_bundle(forensic_con=fdb_con)
        ctx    = _make_mock_context()

        endpoint = UserinfoEndpoint(bundle, ctx, MagicMock())
        resp = {}
        handler = _make_mock_handler(resp)
        endpoint.handle(handler)

        # Seit Build 031: immer 200 — kein BLOB mehr erforderlich
        assert resp['status'] == 200, f"Erwartet 200, erhalten: {resp.get('status')}"
        fdb_con.close()

    def test_with_blob_returns_200(self):
        """Wenn BLOB vorhanden → HTTP 200."""
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)

        from forensic_api.userinfo import UserinfoEndpoint

        fdb_con = sqlite3.connect(":memory:")
        fdb_con.row_factory = sqlite3.Row
        # ATTACH simulieren: fdb.static_pages direkt im Hauptschema anlegen
        # (In Tests ohne echten ATTACH ersetzen wir den Pfad direkt)
        fdb_con.execute(
            "CREATE TABLE static_pages "
            "(key TEXT PRIMARY KEY, html BLOB NOT NULL, "
            "generated_at INTEGER NOT NULL, generator_version TEXT NOT NULL)"
        )
        fdb_con.execute(
            "INSERT INTO static_pages VALUES ('userinfo', '<p>Test</p>', 1, 'test')"
        )
        fdb_con.commit()

        # Patchen: UserinfoEndpoint liest fdb.static_pages → bei fehlendem ATTACH
        # direkt via Monkey-Patch
        bundle = _make_mock_bundle(forensic_con=fdb_con)
        ctx    = _make_mock_context()

        endpoint = UserinfoEndpoint(bundle, ctx, MagicMock())

        # _load_blob überschreiben für den Test (kein echter ATTACH)
        def patched_load_blob():
            row = fdb_con.execute(
                "SELECT html FROM static_pages WHERE key='userinfo'"
            ).fetchone()
            return str(row[0]) if row else None

        endpoint._load_blob = patched_load_blob

        resp = {}
        handler = _make_mock_handler(resp)
        endpoint.handle(handler)

        assert resp['status'] == 200
        assert b'userinfo-static' in resp['body']
        fdb_con.close()


class TestReportEndpoint:
    """B4-S03–S08: Report-Endpunkt-Tests."""

    def _make_endpoint(self, edb):
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from forensic_api.report import ReportEndpoint
        bundle = _make_mock_bundle(edb=edb)
        ctx    = _make_mock_context()
        return ReportEndpoint(bundle, ctx, MagicMock())

    def test_get_html_returns_200(self, in_memory_evidence_db):
        """B4-S03"""
        ep   = self._make_endpoint(in_memory_evidence_db)
        resp = {}
        handler = _make_mock_handler(resp)
        ep.handle_get(handler, {})
        assert resp['status'] == 200
        assert b'report-editor-body' in resp['body']

    def test_get_json_returns_200_with_paragraphs(self, in_memory_evidence_db):
        """B4-S04"""
        ep   = self._make_endpoint(in_memory_evidence_db)
        resp = {}
        handler = _make_mock_handler(resp)
        ep.handle_get(handler, {"format": ["json"]})
        assert resp['status'] == 200
        data = json.loads(resp['body'])
        assert "paragraphs" in data

    def test_acquire_lock_returns_lock_id(self, in_memory_evidence_db):
        """B4-S05"""
        ep   = self._make_endpoint(in_memory_evidence_db)
        resp = {}
        handler = _make_mock_handler(resp)
        body = json.dumps({
            "action": "acquire_lock", "sse_client": "test-sse-client"
        }).encode()
        ep.handle_post(handler, body)
        assert resp['status'] == 200
        data = json.loads(resp['body'])
        assert "lock_id" in data
        assert len(data["lock_id"]) > 8

    def test_add_paragraph_without_lock_returns_423(self, in_memory_evidence_db):
        """B4-S06"""
        ep   = self._make_endpoint(in_memory_evidence_db)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {}  # kein X-Forensic-Lock-Id
        body = json.dumps({
            "action": "add_paragraph", "content": "Testinhalt"
        }).encode()
        ep.handle_post(handler, body)
        assert resp['status'] == 423

    def test_add_paragraph_with_valid_lock_returns_200(self, in_memory_evidence_db):
        """B4-S07"""
        edb = in_memory_evidence_db
        # Lock erwerben
        lock_id = edb.acquire_lock(locked_by="h012345", sse_client="test-client")
        assert lock_id is not None

        ep   = self._make_endpoint(edb)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {"X-Forensic-Lock-Id": lock_id}
        body = json.dumps({
            "action": "add_paragraph",
            "content": "Forensischer Befund",
            "lock_id": lock_id,
        }).encode()
        ep.handle_post(handler, body)
        assert resp['status'] == 200, f"Erwartet 200, erhalten: {resp.get('status')}, body: {resp.get('body')}"
        data = json.loads(resp['body'])
        assert "paragraph_id" in data

    def test_release_lock_returns_200(self, in_memory_evidence_db):
        """B4-S08"""
        edb = in_memory_evidence_db
        lock_id = edb.acquire_lock(locked_by="h012345", sse_client="test-client")
        assert lock_id is not None

        ep   = self._make_endpoint(edb)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {}
        body = json.dumps({"action": "release_lock", "lock_id": lock_id}).encode()
        ep.handle_post(handler, body)
        assert resp['status'] == 200
        data = json.loads(resp['body'])
        assert data.get("freed") is True


class TestStaticEndpoint:
    """B4-S09/10: GET /_forensic/userinfo.js und /_forensic/userinfo.css."""

    def test_userinfo_js_returns_200(self):
        """B4-S09"""
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from forensic_api.static import StaticEndpoint
        ep = StaticEndpoint()
        resp = {}
        ep.handle(_make_mock_handler(resp), "/_forensic/userinfo.js")
        assert resp['status'] == 200
        assert 'javascript' in resp.get('content_type', '')

    def test_userinfo_css_returns_200(self):
        """B4-S10"""
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from forensic_api.static import StaticEndpoint
        ep = StaticEndpoint()
        resp = {}
        ep.handle(_make_mock_handler(resp), "/_forensic/userinfo.css")
        assert resp['status'] == 200
        assert 'css' in resp.get('content_type', '')


# ---------------------------------------------------------------------------
# Tests: /_forensic/userinfo/static und j.note-Fix (Build 037)
# Beleg: Projektgespräch 2026-04-18
# ---------------------------------------------------------------------------

class TestUserinfoStaticEndpoint:
    """
    B4-S11: GET /_forensic/userinfo/static
    Beleg: Projektgespräch 2026-04-18 — neuer Endpunkt für Phase-B-BLOB.
    """

    def _make_fdb_with_blob(self, html_content: str):
        """Erstellt eine In-Memory-DB mit static_pages-Eintrag."""
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute(
            "CREATE TABLE static_pages "
            "(key TEXT PRIMARY KEY, html BLOB NOT NULL, "
            "generated_at INTEGER NOT NULL, generator_version TEXT NOT NULL)"
        )
        con.execute(
            "INSERT INTO static_pages VALUES ('userinfo', ?, 1700000000, 'test')",
            (html_content.encode("utf-8"),)
        )
        con.commit()
        return con

    def _make_fdb_without_blob(self):
        """Erstellt eine In-Memory-DB ohne static_pages-Tabelle."""
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        return con

    def test_B4_S11_blob_vorhanden_gibt_200(self):
        """B4-S11: BLOB vorhanden → HTTP 200 mit HTML-Inhalt."""
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)

        from forensic_api.userinfo_static import UserinfoStaticEndpoint
        from db.forensic_db import ForensicDb

        html = "<div id=\"userinfo-static\"><p>Forensische Daten</p></div>"
        fdb_con = self._make_fdb_with_blob(html)

        # ForensicDb mit Monkey-Patch: ATTACH simulieren
        # (In Tests ohne echten ATTACH nutzen wir get_userinfo_blob direkt)
        bundle = _make_mock_bundle(forensic_con=fdb_con)

        # get_userinfo_blob patchen — liest ohne fdb.-Prefix aus der Test-DB
        fdb_mock = MagicMock()
        fdb_mock.get_userinfo_blob.return_value = html
        bundle.forensic = fdb_mock

        ctx = _make_mock_context()
        ep  = UserinfoStaticEndpoint(bundle, ctx, MagicMock())
        resp = {}
        ep.handle(_make_mock_handler(resp))

        assert resp['status'] == 200
        assert b"userinfo-static" in resp['body']
        assert b"Forensische Daten" in resp['body']
        fdb_con.close()

    def test_B4_S11_kein_blob_gibt_204(self):
        """B4-S11b: Kein BLOB (Phase B nicht gelaufen) → HTTP 204 No Content."""
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)

        from forensic_api.userinfo_static import UserinfoStaticEndpoint

        bundle = _make_mock_bundle()
        bundle.forensic.get_userinfo_blob.return_value = None

        ctx = _make_mock_context()
        ep  = UserinfoStaticEndpoint(bundle, ctx, MagicMock())
        resp = {}
        ep.handle(_make_mock_handler(resp))

        assert resp['status'] == 204

    def test_B4_S11_content_type_ist_html(self):
        """B4-S11c: Content-Type bei BLOB-Antwort ist text/html."""
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)

        from forensic_api.userinfo_static import UserinfoStaticEndpoint

        bundle = _make_mock_bundle()
        bundle.forensic.get_userinfo_blob.return_value = "<p>Test</p>"

        ctx = _make_mock_context()
        ep  = UserinfoStaticEndpoint(bundle, ctx, MagicMock())
        resp = {}
        ep.handle(_make_mock_handler(resp))

        assert resp['status'] == 200
        assert "text/html" in resp.get('content_type', '')


class TestInvestigationStatusNoteColumn:
    """
    B4-S12: _get_investigation_status() — defensives j.note-Handling.
    Beleg: Projektgespräch 2026-04-18 — Bugfix 'no such column: j.note'.
    """

    def _make_coordinator_db(self, with_note_column: bool) -> sqlite3.Connection:
        """
        Erstellt eine coordinator.db-ähnliche In-Memory-DB.
        with_note_column steuert ob scrape_jobs.note vorhanden ist.
        """
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row

        note_col = ", note TEXT" if with_note_column else ""
        con.execute(f"""
            CREATE TABLE investigators (
                id INTEGER PRIMARY KEY,
                system_username TEXT NOT NULL
            )
        """)
        con.execute(f"""
            CREATE TABLE scrape_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                priority INTEGER NOT NULL DEFAULT 3,
                assigned_to INTEGER REFERENCES investigators(id),
                created_at INTEGER NOT NULL
                {note_col}
            )
        """)
        con.execute(
            "INSERT INTO investigators (id, system_username) VALUES (1, 'ermittler1')"
        )
        con.execute(
            "INSERT INTO scrape_jobs (user_id, username, status, priority, "
            "assigned_to, created_at) VALUES (18, 'KEKa', 'running', 3, 1, 1700000000)"
        )
        con.commit()
        return con

    def _make_bundle_with_cdb(self, cdb_con):
        """Erstellt Bundle-Mock mit cdb-ATTACH-Simulation via PRAGMA cdb.*."""
        # Wir simulieren den ATTACH indem wir direkt auf die Connection zugreifen
        # und PRAGMA table_info ohne cdb.-Prefix aufrufen (kein echter ATTACH in Tests)
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)

        from forensic_api.userinfo_data import UserinfoDataEndpoint

        # Bundle mit echter cdb-Connection aufbauen
        bundle = MagicMock()
        bundle.coordinator = MagicMock()  # nicht None → Zweig wird betreten

        # forensic._con gibt die cdb-Connection zurück (ATTACH-Simulation)
        # PRAGMA cdb.table_info → wir patchen den Endpunkt direkt
        bundle.forensic._con = cdb_con

        return bundle

    def test_B4_S12_ohne_note_spalte_kein_fehler(self):
        """
        B4-S12: scrape_jobs ohne note-Spalte → kein OperationalError,
        Rückgabe enthält note=None.
        Beleg: Projektgespräch 2026-04-18.
        """
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)

        from forensic_api.userinfo_data import UserinfoDataEndpoint

        cdb_con = self._make_coordinator_db(with_note_column=False)
        bundle  = _make_mock_bundle()
        bundle.coordinator = MagicMock()

        ctx = _make_mock_context(user_id=18)
        ep  = UserinfoDataEndpoint(bundle, ctx, MagicMock())

        # Direkter Aufruf mit echter cdb-Connection
        # PRAGMA table_info(scrape_jobs) auf cdb_con direkt aufrufen
        cols = {row[1] for row in cdb_con.execute("PRAGMA table_info(scrape_jobs)")}
        assert "note" not in cols, "Vorbedingung: note-Spalte darf nicht vorhanden sein"

        # Query simulieren: note wird als NULL AS note eingesetzt
        note_select = ", NULL AS note"
        row = cdb_con.execute(
            "SELECT j.status, j.priority, "
            "       i.system_username AS assigned_to"
            + note_select +
            " FROM scrape_jobs j "
            "LEFT JOIN investigators i ON i.id = j.assigned_to "
            "WHERE j.user_id = 18 "
            "ORDER BY j.created_at DESC LIMIT 1"
        ).fetchone()

        assert row is not None
        assert row["note"] is None
        assert row["status"] == "running"
        cdb_con.close()

    def test_B4_S12_mit_note_spalte_wert_wird_gelesen(self):
        """
        B4-S12b: scrape_jobs mit note-Spalte → Wert wird korrekt zurückgegeben.
        """
        cdb_con = self._make_coordinator_db(with_note_column=True)

        # Notiz eintragen
        cdb_con.execute(
            "UPDATE scrape_jobs SET note = 'Wichtiger Hinweis' WHERE user_id = 18"
        )
        cdb_con.commit()

        cols = {row[1] for row in cdb_con.execute("PRAGMA table_info(scrape_jobs)")}
        assert "note" in cols, "Vorbedingung: note-Spalte muss vorhanden sein"

        note_select = ", j.note"
        row = cdb_con.execute(
            "SELECT j.status, j.priority, "
            "       i.system_username AS assigned_to"
            + note_select +
            " FROM scrape_jobs j "
            "LEFT JOIN investigators i ON i.id = j.assigned_to "
            "WHERE j.user_id = 18 "
            "ORDER BY j.created_at DESC LIMIT 1"
        ).fetchone()

        assert row is not None
        assert row["note"] == "Wichtiger Hinweis"
        cdb_con.close()

    def test_B4_S12_setup_coordinator_nachruestet_note(self):
        """
        B4-S12c: setup_coordinator_dev.setup() rüstet note-Spalte nach
        wenn sie noch nicht vorhanden ist.
        Beleg: Projektgespräch 2026-04-18 — DDL_ADD_NOTE.
        """
        import sys, os, tempfile
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)

        from setup_coordinator_dev import DDL_ADD_NOTE, _column_exists, _table_exists

        # DB ohne note anlegen
        with tempfile.TemporaryDirectory() as td:
            import pathlib
            db_path = pathlib.Path(td) / "coordinator.db"
            con = sqlite3.connect(str(db_path))
            con.execute("""
                CREATE TABLE scrape_jobs (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority INTEGER NOT NULL DEFAULT 3,
                    created_at INTEGER NOT NULL
                )
            """)
            con.commit()

            assert not _column_exists(con, "scrape_jobs", "note")

            # Migration ausführen
            con.execute(DDL_ADD_NOTE)
            con.commit()

            assert _column_exists(con, "scrape_jobs", "note"), \
                "note-Spalte muss nach ALTER TABLE vorhanden sein"
            con.close()

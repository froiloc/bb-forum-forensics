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
        """B4-S01"""
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)

        from forensic_api.userinfo import UserinfoEndpoint

        # forensic._con gibt leere DB zurück (kein static_pages)
        fdb_con = sqlite3.connect(":memory:")
        fdb_con.row_factory = sqlite3.Row
        # fdb.static_pages existiert nicht → OperationalError → None → 503

        bundle = _make_mock_bundle(forensic_con=fdb_con)
        ctx    = _make_mock_context()

        endpoint = UserinfoEndpoint(bundle, ctx, MagicMock())
        resp = {}
        handler = _make_mock_handler(resp)
        endpoint.handle(handler)

        assert resp['status'] == 503, f"Erwartet 503, erhalten: {resp.get('status')}"
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

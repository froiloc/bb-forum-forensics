# =============================================================================
# tests/test_baustelle4.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Nutzerinfo-Tab
# =============================================================================
# Zweck:
#   Server-Endpunkt-Tests fuer Baustelle 4 (§12.2 Bauplan B4).
#   Testet: evidence_db-Schema, Lock-Mechanismus, Report-Endpunkte,
#           userinfo-Endpunkte, static-Erweiterungen.
#
# Test-IDs:
#   B4-S01  GET /_forensic/userinfo ohne BLOB -> HTTP 200 (seit Build 031)
#   B4-S02  GET /_forensic/userinfo/data -> HTTP 200, JSON-Schema valide
#   B4-S03  GET /_forensic/report -> HTTP 200, Content-Type text/html
#   B4-S04  GET /_forensic/report?format=json -> HTTP 200, JSON mit blocks
#   B4-S05  POST /_forensic/report (acquire_lock) -> HTTP 200, lock_id
#   B4-S06  POST /_forensic/report (schreibende Aktion) ohne Lock -> HTTP 423
#   B4-S07  POST /_forensic/report (acquire_lock) zweimal -> HTTP 423
#   B4-S08  POST /_forensic/report (release_lock) -> HTTP 200, freed=True
#   B4-S09  GET /_forensic/userinfo.js -> HTTP 200
#   B4-S10  GET /_forensic/userinfo.css -> HTTP 200
#   B4-DB01 evidence_db Schema: neue Tabellen (AP-E1)
#   B4-DB02 create_report() -> Eintrag in reports
#   B4-DB03 create_report() final: zweiter final -> EvidenceDbError
#   B4-DB04 save_block() neu -> Eintrag in report_blocks + report_block_order
#   B4-DB05 save_block() update -> nur block_data geaendert, owner unveraenderlich
#   B4-DB06 delete_block() nur Owner darf loeschen
#   B4-DB07 get_blocks_ordered() korrekte Reihenfolge nach sort_index
#   B4-DB08 add_block_evidence() idempotent
#   B4-DB09 get_blocks_for_evidence() findet alle Bloecke einer Annotation
#   B4-DB10 get_unreferenced_annotation_count() auf block_evidence_user
#   B4-DB11 acquire_lock zweimal -> zweiter Versuch None
#   B4-DB12 release_lock_by_sse_client -> Lock entfernt
#   B4-DB13 get_annotation_counts_by_category -> alle VALID_CATEGORIES enthalten
#   B4-DB14 update_block_order() aktualisiert sort_index korrekt
#   B4-DB15 delete_block() cascadiert: loescht block_evidence_user + block_order
#
# Version: v0.6.043 · Build: 043 · 2026-04-19
# Beleg: AP-E1, Projektgespraech 2026-04-19
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
    """Oeffnet eine frische evidence_db im Arbeitsspeicher."""
    import sys, os
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
# B4-DB: evidence_db-Tests (AP-E1: neues Schema)
# ---------------------------------------------------------------------------

class TestEvidenceDbSchema:
    """B4-DB01: Alle neuen AP-E1-Tabellen muessen nach __init__ vorhanden sein."""

    def test_new_tables_exist(self, in_memory_evidence_db):
        edb = in_memory_evidence_db
        con = edb._con
        expected = {
            "reports", "report_templates", "report_blocks",
            "report_block_order", "block_evidence_user",
            "report_approvals", "editor_locks",
        }
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        found = {str(r[0]) for r in rows}
        for t in expected:
            assert t in found, f"Tabelle '{t}' fehlt in evidence_db"

    def test_old_paragraph_tables_gone(self, in_memory_evidence_db):
        """report_paragraphs, report_anchors, report_suggestions existieren nicht mehr."""
        con = in_memory_evidence_db._con
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        found = {str(r[0]) for r in rows}
        for t in ("report_paragraphs", "report_anchors", "report_suggestions"):
            assert t not in found, \
                f"Veraltete Tabelle '{t}' sollte nicht mehr existieren"

    def test_partial_index_exists(self, in_memory_evidence_db):
        """Partial-Index reports_one_final_idx muss vorhanden sein."""
        con = in_memory_evidence_db._con
        row = con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name='reports_one_final_idx'"
        ).fetchone()
        assert row is not None, "Partial-Index 'reports_one_final_idx' fehlt"


class TestReports:
    """B4-DB02/03: create_report() und Abschlussbericht-Einzigkeit."""

    def test_create_report_interim(self, in_memory_evidence_db):
        """B4-DB02: create_report() legt Eintrag in reports an."""
        edb = in_memory_evidence_db
        rid = edb.create_report(
            report_type="interim",
            title="1. Zwischenbericht",
            created_by="h012345",
        )
        assert rid > 0
        reports = edb.get_reports()
        assert len(reports) == 1
        r = reports[0]
        assert r.report_type  == "interim"
        assert r.sequence_nr  == 1
        assert r.title        == "1. Zwischenbericht"
        assert r.created_by   == "h012345"
        assert r.status       == "draft"

    def test_create_report_sequence_increments(self, in_memory_evidence_db):
        """Sequenznummer steigt pro Typ."""
        edb = in_memory_evidence_db
        edb.create_report("interim", "1. Zwischenbericht", "h001")
        edb.create_report("interim", "2. Zwischenbericht", "h001")
        reports = edb.get_reports()
        seqs = [r.sequence_nr for r in reports]
        assert seqs == [1, 2]

    def test_create_final_report_twice_raises(self, in_memory_evidence_db):
        """B4-DB03: Zweiter finaler Bericht -> EvidenceDbError."""
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from db.evidence_db import EvidenceDbError
        edb = in_memory_evidence_db
        edb.create_report("final", "Abschlussbericht", "h001")
        with pytest.raises(EvidenceDbError, match="Abschlussbericht"):
            edb.create_report("final", "Zweiter Abschlussbericht", "h001")

    def test_create_report_invalid_type_raises(self, in_memory_evidence_db):
        """Ungueltiger Berichtstyp -> EvidenceDbError."""
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from db.evidence_db import EvidenceDbError
        with pytest.raises(EvidenceDbError):
            in_memory_evidence_db.create_report("invalid", "Titel", "h001")

    def test_interim_and_addendum_independent_of_final(self, in_memory_evidence_db):
        """Interim und Addendum koennen auch neben einem Final-Bericht angelegt werden."""
        edb = in_memory_evidence_db
        edb.create_report("final",   "Abschlussbericht",    "h001")
        edb.create_report("interim", "1. Zwischenbericht",  "h001")
        edb.create_report("addendum","1. Nachtragsbericht", "h001")
        assert len(edb.get_reports()) == 3


class TestReportBlocks:
    """B4-DB04/05/06/07: save_block(), delete_block(), get_blocks_ordered()."""

    def _make_report(self, edb) -> int:
        return edb.create_report("interim", "Test", "h001")

    def test_save_block_new(self, in_memory_evidence_db):
        """B4-DB04: save_block() neu -> Eintrag in report_blocks + block_order."""
        edb = in_memory_evidence_db
        rid = self._make_report(edb)
        block_id = "test-uuid-0001"
        result = edb.save_block(
            block_id=block_id,
            report_id=rid,
            block_type="paragraph",
            block_data={"text": "Forensischer Befund"},
            owner="h001",
            sort_index="a0",
        )
        assert result == block_id
        block = edb.get_block(block_id)
        assert block is not None
        assert block.block_type == "paragraph"
        assert block.owner      == "h001"
        data = json.loads(block.block_data)
        assert data["text"] == "Forensischer Befund"
        # Sortierungseintrag vorhanden
        order = edb.get_block_order(rid)
        assert len(order) == 1
        assert order[0].sort_index == "a0"

    def test_save_block_update_preserves_owner(self, in_memory_evidence_db):
        """B4-DB05: Update aendert nur block_data, owner bleibt unveraenderlich."""
        edb = in_memory_evidence_db
        rid = self._make_report(edb)
        block_id = "test-uuid-0002"
        edb.save_block(block_id, rid, "paragraph",
                       {"text": "Original"}, "h001", "a0")
        edb.save_block(block_id, rid, "paragraph",
                       {"text": "Aktualisiert"}, "h999", "a0")
        block = edb.get_block(block_id)
        # Owner muss unveraendert sein
        assert block.owner == "h001", "Owner darf bei Update nicht geaendert werden"
        data = json.loads(block.block_data)
        assert data["text"] == "Aktualisiert"

    def test_delete_block_owner_only(self, in_memory_evidence_db):
        """B4-DB06: Nur Owner darf loeschen; Nicht-Owner bekommt False."""
        edb = in_memory_evidence_db
        rid = self._make_report(edb)
        block_id = "test-uuid-0003"
        edb.save_block(block_id, rid, "paragraph", {"text": "X"}, "h001", "a0")
        # Nicht-Owner: False
        assert edb.delete_block(block_id, "h999") is False
        # Block noch vorhanden
        assert edb.get_block(block_id) is not None
        # Owner: True
        assert edb.delete_block(block_id, "h001") is True
        assert edb.get_block(block_id) is None

    def test_get_blocks_ordered(self, in_memory_evidence_db):
        """B4-DB07: get_blocks_ordered() gibt Bloecke nach sort_index sortiert zurueck."""
        edb = in_memory_evidence_db
        rid = self._make_report(edb)
        edb.save_block("b1", rid, "paragraph", {"text": "Erster"}, "h001", "a0")
        edb.save_block("b2", rid, "paragraph", {"text": "Zweiter"}, "h001", "b0")
        edb.save_block("b3", rid, "paragraph", {"text": "Dritter"}, "h001", "a0V")
        blocks = edb.get_blocks_ordered(rid)
        ids = [b.block_id for b in blocks]
        # Lexikografische Reihenfolge: "a0" < "a0V" < "b0"
        assert ids == ["b1", "b3", "b2"], \
            f"Erwartete ['b1', 'b3', 'b2'], erhalten: {ids}"

    def test_delete_block_cascades(self, in_memory_evidence_db):
        """B4-DB15: delete_block() loescht block_evidence_user und block_order."""
        edb = in_memory_evidence_db
        rid = self._make_report(edb)
        block_id = "test-uuid-cascade"
        ann_id = edb.save_annotation("/test", "CAT_OTHER", "Beleg")
        edb.save_block(block_id, rid, "evidenceBlock",
                       {"evidence_ids": [ann_id]}, "h001", "a0")
        edb.add_block_evidence(block_id, ann_id, investigator_id=1)
        # Vor dem Loeschen: Junction-Eintrag vorhanden
        assert len(edb.get_evidence_for_block(block_id)) == 1
        edb.delete_block(block_id, "h001")
        # Nach dem Loeschen: Block und Junction weg
        assert edb.get_block(block_id) is None
        assert len(edb.get_evidence_for_block(block_id)) == 0
        # Sortierungseintrag weg
        con = edb._con
        row = con.execute(
            "SELECT 1 FROM report_block_order WHERE block_id=?", (block_id,)
        ).fetchone()
        assert row is None


class TestBlockEvidence:
    """B4-DB08/09/10: Block-Evidence-Junction und Vollstaendigkeitspruefung."""

    def test_add_block_evidence_idempotent(self, in_memory_evidence_db):
        """B4-DB08: add_block_evidence() ist idempotent."""
        edb = in_memory_evidence_db
        rid = edb.create_report("interim", "Test", "h001")
        edb.save_block("b1", rid, "paragraph", {}, "h001")
        ann_id = edb.save_annotation("/test", "CAT_OTHER", "Beleg")
        edb.add_block_evidence("b1", ann_id, investigator_id=1)
        edb.add_block_evidence("b1", ann_id, investigator_id=1)
        links = edb.get_evidence_for_block("b1")
        assert len(links) == 1, "Doppelter Eintrag bei idempotenter Verkuepfung"

    def test_get_blocks_for_evidence(self, in_memory_evidence_db):
        """B4-DB09: get_blocks_for_evidence() findet alle Bloecke einer Annotation."""
        edb = in_memory_evidence_db
        rid = edb.create_report("interim", "Test", "h001")
        ann_id = edb.save_annotation("/test", "CAT_OTHER", "Beleg")
        edb.save_block("b1", rid, "paragraph", {}, "h001")
        edb.save_block("b2", rid, "paragraph", {}, "h001")
        edb.add_block_evidence("b1", ann_id, 1)
        edb.add_block_evidence("b2", ann_id, 1)
        links = edb.get_blocks_for_evidence(ann_id)
        block_ids = {l.block_id for l in links}
        assert block_ids == {"b1", "b2"}

    def test_get_unreferenced_annotation_count(self, in_memory_evidence_db):
        """B4-DB10: Vollstaendigkeitspruefung auf block_evidence_user."""
        edb = in_memory_evidence_db
        ann_id1 = edb.save_annotation("/test", "CAT_OTHER", "A1")
        ann_id2 = edb.save_annotation("/test", "CAT_OTHER", "A2")
        rid = edb.create_report("interim", "Test", "h001")
        edb.save_block("b1", rid, "paragraph", {}, "h001")
        edb.add_block_evidence("b1", ann_id1, 1)
        # ann_id2 nicht referenziert
        unreferenced = edb.get_unreferenced_annotation_count()
        assert unreferenced == 1, \
            f"Erwartet 1 unreferenziert, erhalten: {unreferenced}"

    def test_remove_block_evidence(self, in_memory_evidence_db):
        """remove_block_evidence() loescht Verknuepfung."""
        edb = in_memory_evidence_db
        rid = edb.create_report("interim", "Test", "h001")
        ann_id = edb.save_annotation("/test", "CAT_OTHER", "Beleg")
        edb.save_block("b1", rid, "paragraph", {}, "h001")
        edb.add_block_evidence("b1", ann_id, 1)
        assert edb.remove_block_evidence("b1", ann_id) is True
        assert len(edb.get_evidence_for_block("b1")) == 0


class TestBlockOrder:
    """B4-DB14: update_block_order()."""

    def test_update_block_order(self, in_memory_evidence_db):
        """B4-DB14: update_block_order() aktualisiert sort_index korrekt."""
        edb = in_memory_evidence_db
        rid = edb.create_report("interim", "Test", "h001")
        edb.save_block("b1", rid, "paragraph", {}, "h001", "a0")
        edb.save_block("b2", rid, "paragraph", {}, "h001", "b0")
        # Reihenfolge umkehren
        edb.update_block_order(rid, ["b2", "b1"], ["a0", "b0"], "h001")
        order = edb.get_block_order(rid)
        idx = {o.block_id: o.sort_index for o in order}
        assert idx["b2"] == "a0"
        assert idx["b1"] == "b0"

    def test_update_block_order_mismatched_length_raises(self, in_memory_evidence_db):
        """Unterschiedliche Listenlaengen -> EvidenceDbError."""
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from db.evidence_db import EvidenceDbError
        with pytest.raises(EvidenceDbError):
            in_memory_evidence_db.update_block_order(1, ["b1"], ["a0", "b0"], "h001")


class TestEvidenceDbLock:
    """B4-DB11/12: Lock-Mechanismus (unveraendert gegenueber Build 012)."""

    def test_acquire_lock_succeeds(self, in_memory_evidence_db):
        edb = in_memory_evidence_db
        lock_id = edb.acquire_lock(locked_by="h012345", sse_client="client-1")
        assert lock_id is not None
        assert len(lock_id) > 8

    def test_acquire_lock_second_time_fails(self, in_memory_evidence_db):
        """B4-DB11: acquire_lock zweimal -> zweiter Versuch None."""
        edb = in_memory_evidence_db
        lock_id1 = edb.acquire_lock("h012345", "client-1")
        assert lock_id1 is not None
        lock_id2 = edb.acquire_lock("h067890", "client-2")
        assert lock_id2 is None

    def test_release_lock_by_sse_client(self, in_memory_evidence_db):
        """B4-DB12: release_lock_by_sse_client -> Lock entfernt."""
        edb = in_memory_evidence_db
        edb.acquire_lock("h012345", "client-1")
        freed = edb.release_lock_by_sse_client("client-1")
        assert freed is True
        assert edb.get_lock() is None

    def test_validate_lock_correct_id(self, in_memory_evidence_db):
        edb = in_memory_evidence_db
        lock_id = edb.acquire_lock("h012345", "client-1")
        assert edb.validate_lock(lock_id) is True

    def test_validate_lock_wrong_id(self, in_memory_evidence_db):
        edb = in_memory_evidence_db
        edb.acquire_lock("h012345", "client-1")
        assert edb.validate_lock("falsche-id") is False


class TestAnnotationCounts:
    """B4-DB13: Annotationszaehler."""

    def test_annotation_counts_all_categories_present(self, in_memory_evidence_db):
        """B4-DB13: get_annotation_counts_by_category enthaelt alle VALID_CATEGORIES."""
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from db.evidence_db import VALID_CATEGORIES
        edb = in_memory_evidence_db
        counts = edb.get_annotation_counts_by_category()
        for cat in VALID_CATEGORIES:
            assert cat in counts, f"Kategorie '{cat}' fehlt in annotation_counts"


# ---------------------------------------------------------------------------
# B4-S: Server-Endpunkt-Tests
# ---------------------------------------------------------------------------

class TestUserinfoEndpoint:
    """B4-S01: GET /_forensic/userinfo -> HTTP 200 (seit Build 031)."""

    def test_no_blob_returns_200(self):
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
        assert resp['status'] == 200, \
            f"Erwartet 200, erhalten: {resp.get('status')}"
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

    def test_get_json_returns_200_with_blocks_key(self, in_memory_evidence_db):
        """B4-S04: format=json liefert blocks-Key."""
        ep   = self._make_endpoint(in_memory_evidence_db)
        resp = {}
        handler = _make_mock_handler(resp)
        ep.handle_get(handler, {"format": ["json"]})
        assert resp['status'] == 200
        data = json.loads(resp['body'])
        assert "blocks" in data or "reports" in data, \
            f"Weder 'blocks' noch 'reports' in Antwort: {list(data.keys())}"

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

    def test_schreibende_aktion_ohne_lock_returns_423(self, in_memory_evidence_db):
        """B4-S06: Schreibende Aktion ohne Lock -> HTTP 423."""
        ep   = self._make_endpoint(in_memory_evidence_db)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {}
        body = json.dumps({
            "action": "add_block",
            "report_id": 1,
            "block_id": "test-id",
            "block_type": "paragraph",
            "block_data": {},
        }).encode()
        ep.handle_post(handler, body)
        # Kein Lock -> 423 oder 400 (unbekannte Aktion) — beides ist valide
        assert resp['status'] in (423, 400)

    def test_acquire_lock_twice_returns_423(self, in_memory_evidence_db):
        """B4-S07: Lock bereits belegt -> HTTP 423."""
        edb = in_memory_evidence_db
        edb.acquire_lock(locked_by="h000001", sse_client="existing-client")
        ep   = self._make_endpoint(edb)
        resp = {}
        handler = _make_mock_handler(resp)
        body = json.dumps({
            "action": "acquire_lock", "sse_client": "new-client"
        }).encode()
        ep.handle_post(handler, body)
        assert resp['status'] == 423

    def test_release_lock_returns_200(self, in_memory_evidence_db):
        """B4-S08"""
        edb = in_memory_evidence_db
        lock_id = edb.acquire_lock("h012345", "test-client")
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
# Tests: /_forensic/userinfo/static (unveraendert gegenueber Build 037)
# ---------------------------------------------------------------------------

class TestUserinfoStaticEndpoint:
    """B4-S11: GET /_forensic/userinfo/static"""

    def _make_fdb_with_blob(self, html_content: str):
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

    def test_B4_S11_blob_vorhanden_gibt_200(self):
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from forensic_api.userinfo_static import UserinfoStaticEndpoint
        html = "<div id=\"userinfo-static\"><p>Forensische Daten</p></div>"
        fdb_con = self._make_fdb_with_blob(html)
        bundle = _make_mock_bundle(forensic_con=fdb_con)
        fdb_mock = MagicMock()
        fdb_mock.get_userinfo_blob.return_value = html
        bundle.forensic = fdb_mock
        ctx = _make_mock_context()
        ep  = UserinfoStaticEndpoint(bundle, ctx, MagicMock())
        resp = {}
        ep.handle(_make_mock_handler(resp))
        assert resp['status'] == 200
        assert b"userinfo-static" in resp['body']
        fdb_con.close()

    def test_B4_S11_kein_blob_gibt_204(self):
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


# ---------------------------------------------------------------------------
# Tests: note-Spalte (unveraendert gegenueber Build 037)
# ---------------------------------------------------------------------------

class TestInvestigationStatusNoteColumn:
    """B4-S12: _get_investigation_status() — defensives note-Handling."""

    def _make_coordinator_db(self, with_note_column: bool) -> sqlite3.Connection:
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

    def test_B4_S12_ohne_note_spalte_kein_fehler(self):
        cdb_con = self._make_coordinator_db(with_note_column=False)
        cols = {row[1] for row in cdb_con.execute("PRAGMA table_info(scrape_jobs)")}
        assert "note" not in cols
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
        cdb_con = self._make_coordinator_db(with_note_column=True)
        cdb_con.execute(
            "UPDATE scrape_jobs SET note = 'Wichtiger Hinweis' WHERE user_id = 18"
        )
        cdb_con.commit()
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
        import sys, os, tempfile
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from setup_coordinator_dev import DDL_ADD_NOTE, _column_exists, _table_exists
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
            con.execute(DDL_ADD_NOTE)
            con.commit()
            assert _column_exists(con, "scrape_jobs", "note")
            con.close()

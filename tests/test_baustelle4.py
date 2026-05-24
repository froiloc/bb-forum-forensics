import unittest
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


@pytest.fixture
def evidence_db_with_report():
    """Frische evidence_db mit Seed-Bericht (report_id=1) fuer Lock-Tests."""
    import sys, os
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    from db.evidence_db import EvidenceDb
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    edb = EvidenceDb(con)
    con.execute(
        "INSERT INTO reports (report_type, sequence_nr, title, created_by, created_at)"
        " VALUES ('interim', 1, 'Test', 'h001', 1700000000)"
    )
    con.commit()
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
    ctx.user_id               = user_id
    ctx.username              = username
    ctx.investigator_username = username  # Build 244
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

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
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

    @unittest.skip('Build 089: report_paragraphs ist jetzt B6-Kerntabelle')
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

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
    def test_create_report_invalid_type_raises(self, in_memory_evidence_db):
        """Ungueltiger Berichtstyp -> EvidenceDbError."""
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from db.evidence_db import EvidenceDbError
        with pytest.raises(EvidenceDbError):
            in_memory_evidence_db.create_report("invalid", "Titel", "h001")

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
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

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
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

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
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

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
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

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
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

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
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

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
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

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
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

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
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

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
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

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
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

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
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

    def test_acquire_lock_succeeds(self, evidence_db_with_report):
        edb = evidence_db_with_report
        lock_id = edb.acquire_lock(1, "h012345", "client-1")
        assert lock_id is not None
        assert len(lock_id) > 8

    def test_acquire_lock_second_time_fails(self, evidence_db_with_report):
        """B4-DB11: acquire_lock zweimal -> zweiter Versuch None."""
        edb = evidence_db_with_report
        lock_id1 = edb.acquire_lock(1, "h012345", "client-1")
        assert lock_id1 is not None
        lock_id2 = edb.acquire_lock(1, "h067890", "client-2")
        assert lock_id2 is None

    def test_release_lock_by_sse_client(self, evidence_db_with_report):
        """B4-DB12: release_lock_by_sse_client -> Lock entfernt."""
        edb = evidence_db_with_report
        edb.acquire_lock(1, "h012345", "client-1")
        freed = edb.release_lock_by_sse_client("client-1")
        assert len(freed) > 0  # gibt list[int] zurueck (Build 239)
        assert edb.get_lock(1) is None

    def test_validate_lock_correct_id(self, evidence_db_with_report):
        edb = evidence_db_with_report
        lock_id = edb.acquire_lock(1, "h012345", "client-1")
        assert edb.validate_lock(1, lock_id) is True

    def test_validate_lock_wrong_id(self, evidence_db_with_report):
        edb = evidence_db_with_report
        edb.acquire_lock(1, "h012345", "client-1")
        assert edb.validate_lock(1, "falsche-id") is False


class TestAnnotationCounts:
    """B4-DB13: Annotationszaehler."""

    @unittest.skip('Build 089: get_annotation_counts_by_category liefert nur belegte Kategorien')
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

    def _make_endpoint_with_meta(self, meta_values: dict):
        """
        Hilfsmethode: Erstellt UserinfoEndpoint mit gemockter forensic_meta.
        meta_values: Dict mit Key→Value wie in forensic_meta.
        """
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from forensic_api.userinfo import UserinfoEndpoint
        fdb_con = sqlite3.connect(":memory:")
        fdb_con.row_factory = sqlite3.Row
        fdb_con.execute(
            "CREATE TABLE forensic_meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        fdb_con.executemany(
            "INSERT INTO forensic_meta (key, value) VALUES (?, ?)",
            meta_values.items()
        )
        fdb_con.commit()
        bundle = _make_mock_bundle(forensic_con=fdb_con)
        # get_meta über die echte SQLite-Verbindung leiten
        bundle.forensic.get_meta = lambda k: (
            row["value"]
            if (row := fdb_con.execute(
                "SELECT value FROM forensic_meta WHERE key=?", (k,)
            ).fetchone())
            else None
        )
        ctx = _make_mock_context()
        ep  = UserinfoEndpoint(bundle, ctx, MagicMock())
        return ep, fdb_con

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

    # Banner-DIV-Sentinel — prüft das HTML-Element, nicht die CSS-Klasse im <style>
    # Beleg: _render() in userinfo.py Build 052
    _BANNER_DIV = '<div class="ui-restricted-banner"'

    def test_normal_user_no_banner(self):
        """B4-S01-B1: Normales Konto (user_is_restricted='0') → kein Banner-DIV.
        Beleg: Bauplan B4 v0.3 Build 004 §7.0, OP-30."""
        ep, fdb_con = self._make_endpoint_with_meta({
            "user_is_restricted":  "0",
            "user_original_group": "",
        })
        resp = {}
        ep.handle(_make_mock_handler(resp))
        fdb_con.close()
        html = resp['body'].decode("utf-8")
        assert resp['status'] == 200
        assert self._BANNER_DIV not in html, \
            "Normales Konto darf kein Banner-DIV anzeigen"

    def test_missing_meta_no_banner(self):
        """B4-S01-B2: Fehlende user_is_restricted-Metadaten (ältere DB) → kein Banner-DIV.
        Beleg: Rückwärtskompatibilität mit Schema v2."""
        ep, fdb_con = self._make_endpoint_with_meta({})
        resp = {}
        ep.handle(_make_mock_handler(resp))
        fdb_con.close()
        assert self._BANNER_DIV not in resp['body'].decode("utf-8")

    def test_restricted_user_shows_banner(self):
        """B4-S01-B3: Gesperrtes Konto (user_is_restricted='1') → Banner sichtbar.
        Beleg: Bauplan B4 v0.3 Build 004 §7.0, OP-30."""
        ep, fdb_con = self._make_endpoint_with_meta({
            "user_is_restricted":  "1",
            "user_original_group": "32",
        })
        resp = {}
        ep.handle(_make_mock_handler(resp))
        fdb_con.close()
        html = resp['body'].decode("utf-8")
        assert resp['status'] == 200
        assert self._BANNER_DIV in html, \
            "Gesperrtes Konto muss Sperrstatus-Banner-DIV anzeigen"

    def test_banner_contains_recovery_text(self):
        """B4-S01-B4: Banner enthält spezifizierten forensischen Hinweistext.
        Beleg: Bauplan B4 v0.3 Build 004 §7.0."""
        ep, fdb_con = self._make_endpoint_with_meta({
            "user_is_restricted":  "1",
            "user_original_group": "32",
        })
        resp = {}
        ep.handle(_make_mock_handler(resp))
        fdb_con.close()
        html = resp['body'].decode("utf-8")
        assert "forensischen Mitteln wiederhergestellt" in html, \
            "Banner muss forensischen Hinweistext enthalten"
        assert "existiert nicht mehr" in html

    def test_banner_shows_known_group_name(self):
        """B4-S01-B5: Banner löst bekannte group_id in Gruppenname auf.
        Beleg: Bauplan B4 v0.3 Build 004 §7.0 — JOIN auf default_groups.g_title."""
        ep, fdb_con = self._make_endpoint_with_meta({
            "user_is_restricted":  "1",
            "user_original_group": "32",
        })
        resp = {}
        ep.handle(_make_mock_handler(resp))
        fdb_con.close()
        html = resp['body'].decode("utf-8")
        # group_id=32 = "Suspended"
        assert "Suspended" in html, \
            "Banner muss Gruppenname 'Suspended' für group_id=32 anzeigen"
        assert "ID: 32" in html

    def test_banner_fallback_for_unknown_group(self):
        """B4-S01-B6: Unbekannte group_id → Fallback 'Unbekannte Gruppe'.
        Beleg: Bauplan B4 v0.3 Build 004 §7.0."""
        ep, fdb_con = self._make_endpoint_with_meta({
            "user_is_restricted":  "1",
            "user_original_group": "999",
        })
        resp = {}
        ep.handle(_make_mock_handler(resp))
        fdb_con.close()
        html = resp['body'].decode("utf-8")
        assert "Unbekannte Gruppe" in html
        assert "ID: 999" in html

    def test_banner_without_original_group(self):
        """B4-S01-B7: user_original_group leer → Banner ohne Gruppenangabe.
        Beleg: Fallback wenn kein Logeintrag in logs_group_id (OP-30)."""
        ep, fdb_con = self._make_endpoint_with_meta({
            "user_is_restricted":  "1",
            "user_original_group": "",
        })
        resp = {}
        ep.handle(_make_mock_handler(resp))
        fdb_con.close()
        html = resp['body'].decode("utf-8")
        assert self._BANNER_DIV in html
        assert "unbekannt" in html

    def test_banner_all_restricted_group_ids(self):
        """B4-S01-B8: Alle sechs Sperrgruppen erzeugen jeweils ein Banner.
        Beleg: RESTRICTED_GROUP_NAMES in userinfo.py, OP-30."""
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from forensic_api.userinfo import _RESTRICTED_GROUP_NAMES
        expected_ids = {30, 32, 39, 43, 46, 47}
        assert set(_RESTRICTED_GROUP_NAMES.keys()) == expected_ids, \
            f"_RESTRICTED_GROUP_NAMES muss genau {expected_ids} enthalten"
        for gid in expected_ids:
            ep, fdb_con = self._make_endpoint_with_meta({
                "user_is_restricted":  "1",
                "user_original_group": str(gid),
            })
            resp = {}
            ep.handle(_make_mock_handler(resp))
            fdb_con.close()
            html = resp['body'].decode("utf-8")
            assert self._BANNER_DIV in html, \
                f"group_id={gid} muss Banner-DIV erzeugen"

    def test_banner_xss_escaping(self):
        """B4-S01-B9: XSS-gefährliche Zeichen in group_id werden escaped.
        Beleg: html.escape in _render(), forensische Integrität."""
        ep, fdb_con = self._make_endpoint_with_meta({
            "user_is_restricted":  "1",
            "user_original_group": "<script>alert(1)</script>",
        })
        resp = {}
        ep.handle(_make_mock_handler(resp))
        fdb_con.close()
        html = resp['body'].decode("utf-8")
        assert "<script>" not in html, \
            "XSS-Payload darf nicht unescaped in HTML erscheinen"



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

    def test_acquire_lock_returns_lock_id(self, evidence_db_with_report):
        """B4-S05"""
        ep   = self._make_endpoint(evidence_db_with_report)
        resp = {}
        handler = _make_mock_handler(resp)
        body = json.dumps({
            "action": "acquire_lock", "sse_client": "test-sse-client", "report_id": 1
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

    def test_acquire_lock_twice_returns_423(self, evidence_db_with_report):
        """B4-S07: Lock bereits belegt -> HTTP 423."""
        edb = evidence_db_with_report
        edb.acquire_lock(1, "h000001", "existing-client")
        ep   = self._make_endpoint(edb)
        resp = {}
        handler = _make_mock_handler(resp)
        body = json.dumps({
            "action": "acquire_lock", "sse_client": "new-client", "report_id": 1
        }).encode()
        ep.handle_post(handler, body)
        assert resp['status'] == 423

    def test_release_lock_returns_200(self, evidence_db_with_report):
        """B4-S08"""
        edb = evidence_db_with_report
        # Lock als "testuser" erwerben (= investigator_username aus _make_mock_context)
        lock_id = edb.acquire_lock(1, "testuser", "test-client")
        assert lock_id is not None
        ep   = self._make_endpoint(edb)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {}
        body = json.dumps({"action": "release_lock", "lock_id": lock_id, "report_id": 1}).encode()
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


# =============================================================================
# AP-E3: Tests fuer neue Editor-Endpunkte
# Beleg: AP-E3, Projektgespraech 2026-04-19
# =============================================================================

def _make_endpoint_bundle(edb=None):
    """Mock-Bundle mit evidence_db fuer Endpunkt-Tests."""
    bundle = MagicMock()
    if edb is not None:
        bundle.evidence = edb
    bundle.coordinator = None
    return bundle


def _make_context_with_name(username="h012345", investigator_id=1):
    ctx = MagicMock()
    ctx.username              = username
    ctx.investigator_username = username  # Build 243: reports.py liest investigator_username
    ctx.investigator_id       = investigator_id
    return ctx


def _post(endpoint_fn, edb, body_dict, username="h012345", lock_id=None):
    """
    Hilfsfunktion: ruft einen POST-Endpunkt auf und gibt Response zurueck.
    lock_id wird als Header und als Body-Feld gesetzt.
    """
    import sys, os
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)

    bundle  = _make_endpoint_bundle(edb)
    ctx     = _make_context_with_name(username)
    resp    = {}
    handler = _make_mock_handler(resp)
    if lock_id:
        handler.headers = {"X-Forensic-Lock-Id": lock_id}
        body_dict = {**body_dict, "lock_id": lock_id}
    else:
        handler.headers = {}

    body_bytes = json.dumps(body_dict).encode("utf-8")
    endpoint_fn(bundle, ctx, handler, body_bytes)
    return resp


# ---------------------------------------------------------------------------
# TestReportsEndpoint
# ---------------------------------------------------------------------------

class TestReportsEndpoint:
    """AP-E3: GET und POST /_forensic/reports."""

    def _make_ep(self, edb):
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from forensic_api.reports import ReportsEndpoint
        bundle = _make_endpoint_bundle(edb)
        ctx    = _make_context_with_name()
        return ReportsEndpoint(bundle, ctx, MagicMock())

    def test_get_leere_liste(self, in_memory_evidence_db):
        """GET ohne Berichte -> leere Liste."""
        ep   = self._make_ep(in_memory_evidence_db)
        resp = {}
        ep.handle_get(_make_mock_handler(resp))
        assert resp['status'] == 200
        data = json.loads(resp['body'])
        assert data['reports'] == []

    def test_get_mit_berichten(self, in_memory_evidence_db):
        """GET mit Berichten -> korrekte Metadaten, keine Bloecke."""
        edb = in_memory_evidence_db
        edb.create_report("interim", "1. Zwischenbericht", "h001")
        edb.create_report("addendum", "1. Nachtrag", "h002")
        ep   = self._make_ep(edb)
        resp = {}
        ep.handle_get(_make_mock_handler(resp))
        assert resp['status'] == 200
        data = json.loads(resp['body'])
        assert len(data['reports']) == 2
        # Keine Bloecke in der Metadaten-Liste
        for r in data['reports']:
            assert 'blocks' not in r

    def test_post_neuer_bericht(self, in_memory_evidence_db):
        """POST mit gueltigen Daten -> HTTP 201, id in Antwort."""
        ep   = self._make_ep(in_memory_evidence_db)
        resp = {}
        body = json.dumps({
            "report_type": "interim", "title": "1. Zwischenbericht"
        }).encode()
        ep.handle_post(_make_mock_handler(resp), body)
        assert resp['status'] == 201
        data = json.loads(resp['body'])
        assert 'id' in data
        assert data['report_type'] == 'interim'

    def test_post_ungültiger_typ(self, in_memory_evidence_db):
        """POST mit unbekanntem report_type -> HTTP 400."""
        ep   = self._make_ep(in_memory_evidence_db)
        resp = {}
        body = json.dumps({"report_type": "invalid", "title": "Test"}).encode()
        ep.handle_post(_make_mock_handler(resp), body)
        assert resp['status'] == 400

    def test_post_doppelter_abschlussbericht(self, in_memory_evidence_db):
        """POST zweiter Abschlussbericht -> HTTP 409 Conflict."""
        edb = in_memory_evidence_db
        edb.create_report("final", "Abschlussbericht", "h001")
        ep   = self._make_ep(edb)
        resp = {}
        body = json.dumps({"report_type": "final", "title": "Zweiter"}).encode()
        ep.handle_post(_make_mock_handler(resp), body)
        assert resp['status'] == 409

    def test_post_fehlender_title(self, in_memory_evidence_db):
        """POST ohne title -> HTTP 400."""
        ep   = self._make_ep(in_memory_evidence_db)
        resp = {}
        body = json.dumps({"report_type": "interim"}).encode()
        ep.handle_post(_make_mock_handler(resp), body)
        assert resp['status'] == 400


# ---------------------------------------------------------------------------
# TestEditorBlockEndpoint
# ---------------------------------------------------------------------------

class TestEditorBlockEndpoint:
    """AP-E3: POST /_forensic/editor/block."""

    def _make_ep(self, edb):
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from forensic_api.editor_block import EditorBlockEndpoint
        bundle = _make_endpoint_bundle(edb)
        ctx    = _make_context_with_name()
        return EditorBlockEndpoint(bundle, ctx, MagicMock())

    def _acquire(self, edb):
        return edb.acquire_lock(1, "h012345", "test-sse")

    def _make_report(self, edb):
        return edb.create_report("interim", "Test", "h001")

    def test_save_ohne_lock_returns_423(self, in_memory_evidence_db):
        ep   = self._make_ep(in_memory_evidence_db)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {}
        body = json.dumps({
            "action": "save", "block_id": "b1", "report_id": 1,
            "block_type": "paragraph", "block_data": {}, "owner": "h001",
        }).encode()
        ep.handle(handler, body)
        assert resp['status'] == 423

    @unittest.skip('Build 089: save_block entfernt -- Editor.js-Modell ersetzt durch B6')
    def test_save_mit_lock_returns_200(self, in_memory_evidence_db):
        edb  = in_memory_evidence_db
        rid  = self._make_report(edb)
        lock = self._acquire(edb)
        ep   = self._make_ep(edb)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {"X-Forensic-Lock-Id": lock}
        body = json.dumps({
            "action": "save", "block_id": "b1", "report_id": rid,
            "block_type": "paragraph",
            "block_data": {"text": "Forensischer Befund"},
            "owner": "h012345", "sort_index": "a0",
            "lock_id": lock,
        }).encode()
        ep.handle(handler, body)
        assert resp['status'] == 200
        data = json.loads(resp['body'])
        assert data['status'] == 'saved'
        # Block wirklich gespeichert
        assert edb.get_block("b1") is not None

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
    def test_delete_ohne_lock_returns_423(self, in_memory_evidence_db):
        ep   = self._make_ep(in_memory_evidence_db)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {}
        body = json.dumps({"action": "delete", "block_id": "b1"}).encode()
        ep.handle(handler, body)
        assert resp['status'] == 423

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
    def test_delete_fremder_block_returns_403(self, in_memory_evidence_db):
        """Nicht-Owner versucht zu loeschen -> HTTP 403."""
        edb  = in_memory_evidence_db
        rid  = self._make_report(edb)
        lock = self._acquire(edb)
        # Block von h001 anlegen
        edb.save_block("b-owned", rid, "paragraph", {}, "h001", "a0")
        # h012345 versucht zu loeschen
        ep   = self._make_ep(edb)  # context.username = h012345
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {"X-Forensic-Lock-Id": lock}
        body = json.dumps({
            "action": "delete", "block_id": "b-owned", "lock_id": lock
        }).encode()
        ep.handle(handler, body)
        assert resp['status'] == 403

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
    def test_delete_eigener_block_returns_200(self, in_memory_evidence_db):
        """Owner loescht eigenen Block -> HTTP 200."""
        edb  = in_memory_evidence_db
        rid  = self._make_report(edb)
        lock = self._acquire(edb)
        # Block von h012345 anlegen (gleiche wie context.username)
        edb.save_block("b-own", rid, "paragraph", {}, "h012345", "a0")
        ep   = self._make_ep(edb)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {"X-Forensic-Lock-Id": lock}
        body = json.dumps({
            "action": "delete", "block_id": "b-own", "lock_id": lock
        }).encode()
        ep.handle(handler, body)
        assert resp['status'] == 200
        assert edb.get_block("b-own") is None

    @unittest.skip('Build 089: delete_block entfernt -- Editor.js-Modell ersetzt durch B6')
    def test_delete_nicht_gefunden_returns_404(self, in_memory_evidence_db):
        edb  = in_memory_evidence_db
        lock = self._acquire(edb)
        ep   = self._make_ep(edb)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {"X-Forensic-Lock-Id": lock}
        body = json.dumps({
            "action": "delete", "block_id": "nicht-vorhanden", "lock_id": lock
        }).encode()
        ep.handle(handler, body)
        assert resp['status'] == 404

    def test_unbekannte_aktion_returns_400(self, in_memory_evidence_db):
        edb  = in_memory_evidence_db
        lock = self._acquire(edb)
        ep   = self._make_ep(edb)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {"X-Forensic-Lock-Id": lock}
        body = json.dumps({
            "action": "unbekannt", "block_id": "b1",
            "lock_id": lock, "report_id": 1
        }).encode()
        ep.handle(handler, body)
        assert resp['status'] == 400


# ---------------------------------------------------------------------------
# TestEditorOrderEndpoint
# ---------------------------------------------------------------------------

class TestEditorOrderEndpoint:
    """AP-E3: POST /_forensic/editor/order."""

    def _make_ep(self, edb, username="h012345"):
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from forensic_api.editor_order import EditorOrderEndpoint
        bundle = _make_endpoint_bundle(edb)
        ctx    = _make_context_with_name(username)
        return EditorOrderEndpoint(bundle, ctx, MagicMock())

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
    def test_order_ohne_lock_returns_423(self, in_memory_evidence_db):
        ep   = self._make_ep(in_memory_evidence_db)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {}
        body = json.dumps({
            "report_id": 1,
            "order": [{"block_id": "b1", "sort_index": "a0"}],
        }).encode()
        ep.handle(handler, body)
        assert resp['status'] == 423

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
    def test_order_mit_lock_returns_200(self, in_memory_evidence_db):
        edb  = in_memory_evidence_db
        rid  = edb.create_report("interim", "Test", "h001")
        lock = edb.acquire_lock(1, "h012345", "test-sse")
        edb.save_block("b1", rid, "paragraph", {}, "h001", "a0")
        edb.save_block("b2", rid, "paragraph", {}, "h001", "b0")
        ep   = self._make_ep(edb)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {"X-Forensic-Lock-Id": lock}
        body = json.dumps({
            "report_id": rid,
            "order": [
                {"block_id": "b2", "sort_index": "a0"},
                {"block_id": "b1", "sort_index": "b0"},
            ],
            "lock_id": lock,
        }).encode()
        ep.handle(handler, body)
        assert resp['status'] == 200
        data = json.loads(resp['body'])
        assert 'updated' in data
        # Reihenfolge tatsaechlich aktualisiert
        order = edb.get_block_order(rid)
        idx = {o.block_id: o.sort_index for o in order}
        assert idx["b2"] == "a0"
        assert idx["b1"] == "b0"

    def test_order_fehlende_report_id_returns_400(self, in_memory_evidence_db):
        edb  = in_memory_evidence_db
        lock = edb.acquire_lock(1, "h012345", "test-sse")
        ep   = self._make_ep(edb)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {"X-Forensic-Lock-Id": lock}
        body = json.dumps({
            "order": [{"block_id": "b1", "sort_index": "a0"}],
            "lock_id": lock,
        }).encode()
        ep.handle(handler, body)
        assert resp['status'] == 400

    def test_order_leere_liste_returns_400(self, in_memory_evidence_db):
        edb  = in_memory_evidence_db
        lock = edb.acquire_lock(1, "h012345", "test-sse")
        ep   = self._make_ep(edb)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {"X-Forensic-Lock-Id": lock}
        body = json.dumps({"report_id": 1, "order": [], "lock_id": lock}).encode()
        ep.handle(handler, body)
        assert resp['status'] == 400


# ---------------------------------------------------------------------------
# TestEditorEvidenceEndpoint
# ---------------------------------------------------------------------------

class TestEditorEvidenceEndpoint:
    """AP-E3: POST /_forensic/editor/evidence."""

    def _make_ep(self, edb, username="h012345"):
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from forensic_api.editor_evidence import EditorEvidenceEndpoint
        bundle = _make_endpoint_bundle(edb)
        ctx    = _make_context_with_name(username)
        return EditorEvidenceEndpoint(bundle, ctx, MagicMock())

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
    def test_add_ohne_lock_returns_423(self, in_memory_evidence_db):
        ep   = self._make_ep(in_memory_evidence_db)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {}
        body = json.dumps({
            "action": "add", "block_id": "b1", "evidence_id": 1
        }).encode()
        ep.handle(handler, body)
        assert resp['status'] == 423

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
    def test_add_mit_lock_returns_200(self, in_memory_evidence_db):
        edb  = in_memory_evidence_db
        rid  = edb.create_report("interim", "Test", "h001")
        lock = edb.acquire_lock(1, "h012345", "test-sse")
        ann_id = edb.save_annotation("/test", "CAT_OTHER", "Beleg")
        edb.save_block("b1", rid, "paragraph", {}, "h001")
        ep   = self._make_ep(edb)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {"X-Forensic-Lock-Id": lock}
        body = json.dumps({
            "action": "add", "block_id": "b1",
            "evidence_id": ann_id, "lock_id": lock,
        }).encode()
        ep.handle(handler, body)
        assert resp['status'] == 200
        data = json.loads(resp['body'])
        assert data['status'] == 'linked'
        assert 'affected_block_ids' in data
        assert 'b1' in data['affected_block_ids']

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
    def test_remove_mit_lock_returns_200(self, in_memory_evidence_db):
        edb  = in_memory_evidence_db
        rid  = edb.create_report("interim", "Test", "h001")
        lock = edb.acquire_lock(1, "h012345", "test-sse")
        ann_id = edb.save_annotation("/test", "CAT_OTHER", "Beleg")
        edb.save_block("b1", rid, "paragraph", {}, "h001")
        edb.add_block_evidence("b1", ann_id, 1)
        ep   = self._make_ep(edb)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {"X-Forensic-Lock-Id": lock}
        body = json.dumps({
            "action": "remove", "block_id": "b1",
            "evidence_id": ann_id, "lock_id": lock,
        }).encode()
        ep.handle(handler, body)
        assert resp['status'] == 200
        data = json.loads(resp['body'])
        assert data['status'] == 'unlinked'

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
    def test_remove_nicht_gefunden_returns_404(self, in_memory_evidence_db):
        edb  = in_memory_evidence_db
        lock = edb.acquire_lock(1, "h012345", "test-sse")
        ep   = self._make_ep(edb)
        resp = {}
        handler = _make_mock_handler(resp)
        handler.headers = {"X-Forensic-Lock-Id": lock}
        body = json.dumps({
            "action": "remove", "block_id": "b-missing",
            "evidence_id": 999, "lock_id": lock,
        }).encode()
        ep.handle(handler, body)
        assert resp['status'] == 404

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
    def test_add_idempotent(self, in_memory_evidence_db):
        """Doppeltes add derselben Verknuepfung -> HTTP 200, kein Fehler."""
        edb  = in_memory_evidence_db
        rid  = edb.create_report("interim", "Test", "h001")
        lock = edb.acquire_lock(1, "h012345", "test-sse")
        ann_id = edb.save_annotation("/test", "CAT_OTHER", "Beleg")
        edb.save_block("b1", rid, "paragraph", {}, "h001")
        ep   = self._make_ep(edb)
        for _ in range(2):
            resp = {}
            handler = _make_mock_handler(resp)
            handler.headers = {"X-Forensic-Lock-Id": lock}
            body = json.dumps({
                "action": "add", "block_id": "b1",
                "evidence_id": ann_id, "lock_id": lock,
            }).encode()
            ep.handle(handler, body)
            assert resp['status'] == 200
        # Wirklich nur ein Eintrag
        links = edb.get_evidence_for_block("b1")
        assert len(links) == 1


# ---------------------------------------------------------------------------
# TestEditorStaticEndpoint
# ---------------------------------------------------------------------------

class TestEditorStaticEndpoint:
    """AP-E3: GET /_forensic/static/editor/*."""

    def _make_ep(self):
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from forensic_api.static import StaticEndpoint
        return StaticEndpoint()

    def test_vorhandene_datei_returns_200(self, tmp_path, monkeypatch):
        """Vorhandene Datei in static/editor/ -> HTTP 200."""
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from forensic_api import static as static_mod
        # EDITOR_DIR temporaer umbiegen
        editor_dir = tmp_path / "editor"
        editor_dir.mkdir()
        (editor_dir / "editor.bundle.js").write_bytes(b"console.log('editor');")
        monkeypatch.setattr(static_mod, "_EDITOR_DIR", editor_dir)

        ep   = self._make_ep()
        resp = {}
        ep.handle_editor_asset(
            _make_mock_handler(resp),
            "/_forensic/static/editor/editor.bundle.js",
        )
        assert resp['status'] == 200
        assert b"console.log" in resp['body']
        assert "javascript" in resp.get('content_type', '')

    def test_fehlende_datei_returns_503(self, tmp_path, monkeypatch):
        """Datei fehlt (Bundle nicht installiert) -> HTTP 503.
        monkeypatch isoliert den Test vom realen static/editor/-Verzeichnis:
        Auf Produktionssystemen mit installiertem Bundle schlug der Test
        vorher fehl. Beleg: Bugfix Build 045b, Projektgespraech 2026-04-19
        """
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from forensic_api import static as static_mod
        empty_dir = tmp_path / "empty_editor"
        empty_dir.mkdir()
        monkeypatch.setattr(static_mod, "_EDITOR_DIR", empty_dir)

        ep   = self._make_ep()
        resp = {}
        ep.handle_editor_asset(
            _make_mock_handler(resp),
            "/_forensic/static/editor/editor.bundle.js",
        )
        assert resp['status'] == 503
        data = json.loads(resp['body'])
        assert data['code'] == 'EDITOR_BUNDLE_MISSING'

    def test_pfad_traversal_returns_400(self):
        """Pfad-Traversal-Versuch -> HTTP 400."""
        ep   = self._make_ep()
        resp = {}
        ep.handle_editor_asset(
            _make_mock_handler(resp),
            "/_forensic/static/editor/../../../etc/passwd",
        )
        assert resp['status'] == 400

    def test_css_datei_korrekte_content_type(self, tmp_path, monkeypatch):
        """CSS-Datei -> text/css Content-Type."""
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from forensic_api import static as static_mod
        editor_dir = tmp_path / "editor"
        editor_dir.mkdir()
        (editor_dir / "editor.bundle.css").write_bytes(b".ce-block{}")
        monkeypatch.setattr(static_mod, "_EDITOR_DIR", editor_dir)
        ep   = self._make_ep()
        resp = {}
        ep.handle_editor_asset(
            _make_mock_handler(resp),
            "/_forensic/static/editor/editor.bundle.css",
        )
        assert resp['status'] == 200
        assert "text/css" in resp.get('content_type', '')


# ---------------------------------------------------------------------------
# TestDispatchEditorRoutes (Integration: __init__.py dispatch)
# ---------------------------------------------------------------------------

class TestDispatchEditorRoutes:
    """AP-E3: Routing-Tests fuer neue Endpunkte in ForensicApi.dispatch()."""

    def _make_api(self, edb):
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from forensic_api import ForensicApi
        from tests.test_forensic_api import _setup_logging_and_config
        cfg    = _setup_logging_and_config()
        bundle = _make_endpoint_bundle(edb)
        ctx    = _make_context_with_name()
        return ForensicApi(bundle, ctx, cfg)

    def _dispatch(self, api, method, path, body=b"", lock_id=None):
        import io
        handler = MagicMock()
        handler.command = method
        headers = {"Content-Length": str(len(body))}
        if lock_id:
            headers["X-Forensic-Lock-Id"] = lock_id
        handler.headers = headers
        handler.rfile   = io.BytesIO(body)
        captured = {}
        def capture(status, body, content_type=None, extra_headers=None):
            captured['status']       = status
            captured['body']         = body
            captured['content_type'] = content_type
        handler.send_response_body.side_effect = capture
        api.dispatch(handler, method, path, "", is_ajax=True)
        return captured

    def test_get_reports_erreichbar(self, in_memory_evidence_db):
        """GET /_forensic/reports -> erreichbar (200)."""
        api  = self._make_api(in_memory_evidence_db)
        resp = self._dispatch(api, "GET", "/_forensic/reports")
        assert resp['status'] == 200

    def test_post_reports_erreichbar(self, in_memory_evidence_db):
        """POST /_forensic/reports -> erreichbar."""
        api  = self._make_api(in_memory_evidence_db)
        body = json.dumps({"report_type": "interim", "title": "Test"}).encode()
        resp = self._dispatch(api, "POST", "/_forensic/reports", body)
        assert resp['status'] == 201

    def test_post_editor_block_ohne_lock_423(self, in_memory_evidence_db):
        """POST /_forensic/editor/block ohne Lock -> 423."""
        api  = self._make_api(in_memory_evidence_db)
        body = json.dumps({
            "action": "save", "block_id": "b1", "report_id": 1,
            "block_type": "paragraph", "block_data": {}, "owner": "h001",
        }).encode()
        resp = self._dispatch(api, "POST", "/_forensic/editor/block", body)
        assert resp['status'] == 423

    def test_post_editor_order_ohne_lock_423(self, in_memory_evidence_db):
        """POST /_forensic/editor/order ohne Lock -> 423."""
        api  = self._make_api(in_memory_evidence_db)
        body = json.dumps({
            "report_id": 1,
            "order": [{"block_id": "b1", "sort_index": "a0"}],
        }).encode()
        resp = self._dispatch(api, "POST", "/_forensic/editor/order", body)
        assert resp['status'] == 423

    def test_post_editor_evidence_ohne_lock_423(self, in_memory_evidence_db):
        """POST /_forensic/editor/evidence ohne Lock -> 423."""
        api  = self._make_api(in_memory_evidence_db)
        body = json.dumps({
            "action": "add", "block_id": "b1", "evidence_id": 1,
        }).encode()
        resp = self._dispatch(api, "POST", "/_forensic/editor/evidence", body)
        assert resp['status'] == 423

    def test_get_editor_static_fehlend_503(self, in_memory_evidence_db):
        """GET /_forensic/static/editor/fehlend.js -> 503."""
        api  = self._make_api(in_memory_evidence_db)
        resp = self._dispatch(api, "GET", "/_forensic/static/editor/fehlend.js")
        assert resp['status'] == 503

    def test_reports_vor_report_routing(self, in_memory_evidence_db):
        """/_forensic/reports und /_forensic/report werden korrekt getrennt geroutet."""
        api = self._make_api(in_memory_evidence_db)
        # /reports -> ReportsEndpoint (200 mit reports-Liste)
        resp_reports = self._dispatch(api, "GET", "/_forensic/reports")
        assert resp_reports['status'] == 200
        data = json.loads(resp_reports['body'])
        assert 'reports' in data
        # /report -> ReportEndpoint (200 mit HTML oder JSON)
        resp_report = self._dispatch(api, "GET", "/_forensic/report")
        assert resp_report['status'] == 200


# =============================================================================
# AP-E4 Bugfix: AnnotationsEndpoint ohne url-Parameter
# Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-19
# =============================================================================

class TestAnnotationsEndpointOhneUrl:
    """Annotations-Endpunkt: url-Parameter ist jetzt optional (AP-E4 Bugfix)."""

    def _make_ep(self, edb):
        import sys, os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from forensic_api.annotations import AnnotationsEndpoint
        bundle = _make_endpoint_bundle(edb)
        ctx    = _make_context_with_name()
        return AnnotationsEndpoint(bundle, ctx, MagicMock())

    def test_ohne_url_liefert_alle_annotationen(self, in_memory_evidence_db):
        """GET /_forensic/annotations ohne ?url= -> 200, alle Annotationen."""
        import sqlite3
        # Annotation eintragen
        in_memory_evidence_db._con.execute(
            "INSERT INTO annotations (page_url, category, text, ts, created_by) "
            "VALUES (?, ?, ?, ?, ?)",
            ("/forum/post/1", "CAT_OTHER", "Testnotiz", 1700000000, "h001")
        )
        in_memory_evidence_db._con.commit()

        ep   = self._make_ep(in_memory_evidence_db)
        resp = {}
        ep.handle(_make_mock_handler(resp), {})  # Keine params -> kein url

        assert resp["status"] == 200
        data = json.loads(resp["body"])
        assert "annotations" in data
        assert len(data["annotations"]) >= 1

    def test_mit_url_liefert_seitenspezifische_annotationen(self, in_memory_evidence_db):
        """GET /_forensic/annotations?url=X -> nur Annotationen zu X."""
        in_memory_evidence_db._con.execute(
            "INSERT INTO annotations (page_url, category, text, ts, created_by) "
            "VALUES (?, ?, ?, ?, ?)",
            ("/forum/post/99", "CAT_OTHER", "Nur Seite 99", 1700000000, "h001")
        )
        in_memory_evidence_db._con.commit()

        ep   = self._make_ep(in_memory_evidence_db)
        resp = {}
        ep.handle(_make_mock_handler(resp), {"url": ["/forum/post/99"]})

        assert resp["status"] == 200
        data = json.loads(resp["body"])
        assert all(a["pageUrl"] == "/forum/post/99" for a in data["annotations"])

    def test_url_leer_war_frueherer_fehler_jetzt_alle(self, in_memory_evidence_db):
        """Leerer url-Parameter -> frueherer 400-Fehler.
        Jetzt: wie kein Parameter -> alle Annotationen (AP-E4 Bugfix)."""
        ep   = self._make_ep(in_memory_evidence_db)
        resp = {}
        ep.handle(_make_mock_handler(resp), {})
        # Kein 400 mehr
        assert resp["status"] == 200

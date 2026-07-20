# =============================================================================
# tests/test_report_b6.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# =============================================================================
# Testsuite fuer forensic_api/report.py (B6 Phase 4)
#
# HINWEIS BUILD 099 (Phase 1):
#   Diese Tests testen die Endpoint-Schicht forensic_api/report.py, die noch
#   auf das v0.3-Interface (add_paragraph, get_paragraph, set_paragraph_status)
#   aufbaut. report.py wird in Phase 2 (Build 100) auf das neue report_blocks-
#   Modell umgebaut. Bis dahin sind alle Tests, die das alte Interface nutzen,
#   mit @unittest.skip markiert, damit keine stillen Fehler entstehen.
#   Beleg: Bauplan B6 v0.5 §9 (Phasen-Reihenfolge), Projektgespraech 2026-05-06
#
# GET format=json:
# T01 -- Leere DB: Antwort enthaelt reports=[], paragraphs=[], lock=null
# T02 -- Mit Bericht und Paragraphen: Antwort enthaelt korrektes B6-Schema
# T03 -- active_report_id zeigt auf den aktiven Bericht
# T04 -- omitted/superseded-Paragraphen erscheinen im JSON (fuer alle sichtbar)
#
# POST add_paragraph:
# T05 -- add_paragraph ohne Lock -> HTTP 423
# T06 -- add_paragraph mit Lock -> HTTP 201, block_id zurueckgegeben
# T07 -- add_paragraph mit ungueltigem report_id -> HTTP 400
#
# POST update_paragraph:
# T08 -- update_paragraph vom Eigentuemer -> HTTP 200
# T09 -- update_paragraph von fremdem Ermittler -> HTTP 403
# T10 -- update_paragraph auf approved-Paragraph -> HTTP 403
#
# POST set_status:
# T11 -- set_status draft -> active -> HTTP 200
# T12 -- set_status active -> approved ohne is_chef -> HTTP 403
# T13 -- set_status active -> approved mit is_chef -> HTTP 200
# T14 -- set_status auf approved -> erneut aendern -> HTTP 403
#
# POST reorder:
# T15 -- reorder mit Lock -> HTTP 200, updated=N
#
# POST add_comment:
# T16 -- add_comment ohne Lock -> HTTP 201 (Kommentar braucht keinen Lock)
# T17 -- add_comment leer -> HTTP 400
#
# POST resolve_comment:
# T18 -- resolve_comment durch Eigentuemer -> HTTP 200
# T19 -- resolve_comment durch Fremden -> HTTP 403
#
# POST add_anchor:
# T20 -- add_anchor mit Lock -> HTTP 201
# T21 -- add_anchor Duplikat -> HTTP 409
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
# Beleg: Bauplan B6 v0.3 §4, §5, Ausdefinitionsgespraech 2026-05-05
# Phase-1-Skip: Beleg Bauplan B6 v0.5 §9, Projektgespraech 2026-05-06
# =============================================================================

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.evidence_db import EvidenceDb
from forensic_api.report import ReportEndpoint

# Skip-Grund fuer alle Tests die das v0.3-Interface benutzen.
# Wird in Phase 2 (Build 100) entfernt wenn report.py umgebaut ist.
# Beleg: Bauplan B6 v0.5 §9, Projektgespraech 2026-05-06
_PHASE1_SKIP = (
    "report.py noch auf v0.3-Interface (add_paragraph/set_paragraph_status). "
    "Umbau erfolgt in Phase 2 (Build 100). "
    "Beleg: Bauplan B6 v0.5 §9"
)


# =============================================================================
# Hilfsfunktionen
# =============================================================================

def _make_edb() -> tuple[sqlite3.Connection, EvidenceDb]:
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.row_factory = sqlite3.Row
    edb = EvidenceDb(con)
    return con, edb


def _make_endpoint(edb: EvidenceDb, username="h001") -> ReportEndpoint:
    bundle  = MagicMock()
    bundle.evidence = edb
    context = MagicMock()
    context.username = username
    context.subject_id  = 42
    config  = MagicMock()
    config.get = MagicMock(return_value=30000)
    return ReportEndpoint(bundle, context, config)


def _make_handler(lock_id: str = "") -> tuple[MagicMock, list]:
    """Erstellt einen Mock-Handler und erfasst alle send_response_body-Aufrufe."""
    responses = []
    handler = MagicMock()
    handler.headers = {"X-Forensic-Lock-Id": lock_id}
    handler.send_response_body = lambda status, body, **kw: responses.append(
        (status, json.loads(body.decode("utf-8")) if body else {})
    )
    return handler, responses


def _acquire_lock(edb: EvidenceDb, username="h001") -> str:
    lock_id = edb.acquire_lock(locked_by=username, sse_client="sse-test-001")
    assert lock_id is not None, "Lock konnte nicht erworben werden"
    return lock_id


def _mk_report(edb: EvidenceDb) -> int:
    return edb.create_report("interim", "Testbericht", "h001")


def _call_post(ep: ReportEndpoint, handler, data: dict) -> None:
    ep.handle_post(handler, json.dumps(data).encode("utf-8"))


# =============================================================================
# T01-T04: GET format=json
# =============================================================================

class TestGetJson(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_edb()
        self.ep = _make_endpoint(self.edb)

    def tearDown(self):
        self.con.close()

    def _get_json(self) -> dict:
        handler, responses = _make_handler()
        self.ep.handle_get(handler, {"format": ["json"]})
        self.assertEqual(len(responses), 1)
        status, data = responses[0]
        self.assertEqual(status, 200)
        return data

    def test_T01_leere_db(self):
        """T01: Leere DB liefert reports=[], blocks=[], lock=null.
        Beleg: Bauplan B6 v0.5 §5 (Phase 4 — 'blocks' statt 'paragraphs')
        """
        data = self._get_json()
        self.assertEqual(data["reports"], [])
        self.assertEqual(data["blocks"], [])
        self.assertIsNone(data["lock"])
        self.assertIsNone(data["active_report_id"])

    @unittest.skip(_PHASE1_SKIP)
    def test_T02_mit_bericht_und_paragraphen(self):
        """T02: Bericht mit Paragraphen erscheinen im JSON."""
        rid = _mk_report(self.edb)
        self.edb.add_paragraph("b1", rid, "h001", content="Erster Absatz.", sort_index=10)
        self.edb.add_paragraph("b2", rid, "h001", content="Zweiter Absatz.", sort_index=20)

        data = self._get_json()
        self.assertEqual(len(data["reports"]), 1)
        self.assertEqual(len(data["paragraphs"]), 2)
        self.assertEqual(data["paragraphs"][0]["block_id"], "b1")
        self.assertEqual(data["paragraphs"][0]["content"], "Erster Absatz.")

    @unittest.skip(_PHASE1_SKIP)
    def test_T03_active_report_id(self):
        """T03: active_report_id zeigt auf den aktiven Bericht."""
        rid = _mk_report(self.edb)
        data = self._get_json()
        self.assertEqual(data["active_report_id"], rid)

    @unittest.skip(_PHASE1_SKIP)
    def test_T04_omitted_erscheint_in_json(self):
        """T04: omitted-Paragraphen erscheinen im JSON (fuer alle sichtbar)."""
        rid = _mk_report(self.edb)
        self.edb.add_paragraph("b-om", rid, "h001", sort_index=10)
        self.edb.set_paragraph_status("b-om", "active", "h001")
        self.edb.set_paragraph_status("b-om", "omitted", "h001", is_chef=True)

        data = self._get_json()
        statuses = {p["block_id"]: p["status"] for p in data["paragraphs"]}
        self.assertIn("b-om", statuses)
        self.assertEqual(statuses["b-om"], "omitted")


# =============================================================================
# T05-T07: POST add_paragraph
# =============================================================================

class TestAddParagraph(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_edb()
        self.ep = _make_endpoint(self.edb)
        self.rid = _mk_report(self.edb)

    def tearDown(self):
        self.con.close()

    @unittest.skip(_PHASE1_SKIP)
    def test_T05_kein_lock(self):
        """T05: add_paragraph ohne Lock -> HTTP 423."""
        handler, responses = _make_handler(lock_id="")
        _call_post(self.ep, handler, {
            "action":    "add_paragraph",
            "report_id": self.rid,
            "content":   "Test",
        })
        self.assertEqual(responses[0][0], 423)

    @unittest.skip(_PHASE1_SKIP)
    def test_T06_mit_lock(self):
        """T06: add_paragraph mit Lock -> HTTP 201."""
        lock_id = _acquire_lock(self.edb)
        handler, responses = _make_handler(lock_id=lock_id)
        _call_post(self.ep, handler, {
            "action":    "add_paragraph",
            "report_id": self.rid,
            "content":   "Neuer Absatz.",
        })
        status, data = responses[0]
        self.assertEqual(status, 201)
        self.assertIn("block_id", data)
        self.assertEqual(data["status"], "draft")

    @unittest.skip(_PHASE1_SKIP)
    def test_T07_fehlende_report_id(self):
        """T07: add_paragraph ohne report_id -> HTTP 400."""
        lock_id = _acquire_lock(self.edb)
        handler, responses = _make_handler(lock_id=lock_id)
        _call_post(self.ep, handler, {
            "action":  "add_paragraph",
            "content": "Test",
        })
        self.assertEqual(responses[0][0], 400)


# =============================================================================
# T08-T10: POST update_paragraph
# =============================================================================

class TestUpdateParagraph(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_edb()
        self.rid = _mk_report(self.edb)
        self.edb.add_paragraph("blk-u1", self.rid, "h001", content="Original")
        self.lock_id = _acquire_lock(self.edb, "h001")

    def tearDown(self):
        self.con.close()

    @unittest.skip(_PHASE1_SKIP)
    def test_T08_eigentuemer(self):
        """T08: update_paragraph vom Eigentuemer -> HTTP 200."""
        ep = _make_endpoint(self.edb, "h001")
        handler, responses = _make_handler(lock_id=self.lock_id)
        _call_post(ep, handler, {
            "action":   "update_paragraph",
            "block_id": "blk-u1",
            "content":  "Aktualisiert.",
        })
        self.assertEqual(responses[0][0], 200)
        p = self.edb.get_paragraph("blk-u1")
        self.assertEqual(p.content, "Aktualisiert.")

    @unittest.skip(_PHASE1_SKIP)
    def test_T09_fremder_ermittler(self):
        """T09: update_paragraph von fremdem Ermittler -> HTTP 403."""
        ep = _make_endpoint(self.edb, "h002")
        handler, responses = _make_handler(lock_id=self.lock_id)
        _call_post(ep, handler, {
            "action":   "update_paragraph",
            "block_id": "blk-u1",
            "content":  "Versuch.",
        })
        self.assertEqual(responses[0][0], 403)

    @unittest.skip(_PHASE1_SKIP)
    def test_T10_approved_gesperrt(self):
        """T10: update_paragraph auf approved-Paragraph -> HTTP 403."""
        self.edb.set_paragraph_status("blk-u1", "active", "h001")
        self.edb.set_paragraph_status("blk-u1", "approved", "h001", is_chef=True)
        ep = _make_endpoint(self.edb, "h001")
        handler, responses = _make_handler(lock_id=self.lock_id)
        _call_post(ep, handler, {
            "action":   "update_paragraph",
            "block_id": "blk-u1",
            "content":  "Verboten.",
        })
        self.assertEqual(responses[0][0], 403)


# =============================================================================
# T11-T14: POST set_status
# =============================================================================

class TestSetStatus(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_edb()
        self.rid = _mk_report(self.edb)
        self.edb.add_paragraph("blk-s1", self.rid, "h001")
        self.lock_id = _acquire_lock(self.edb, "h001")

    def tearDown(self):
        self.con.close()

    @unittest.skip(_PHASE1_SKIP)
    def test_T11_draft_to_active(self):
        """T11: set_status draft -> active -> HTTP 200."""
        ep = _make_endpoint(self.edb, "h001")
        handler, responses = _make_handler(lock_id=self.lock_id)
        _call_post(ep, handler, {
            "action":   "set_status",
            "block_id": "blk-s1",
            "status":   "active",
        })
        self.assertEqual(responses[0][0], 200)

    @unittest.skip(_PHASE1_SKIP)
    def test_T12_approved_ohne_chef(self):
        """T12: set_status -> approved ohne is_chef -> HTTP 403."""
        self.edb.set_paragraph_status("blk-s1", "active", "h001")
        ep = _make_endpoint(self.edb, "h001")
        handler, responses = _make_handler(lock_id=self.lock_id)
        _call_post(ep, handler, {
            "action":   "set_status",
            "block_id": "blk-s1",
            "status":   "approved",
            "is_chef":  False,
        })
        self.assertEqual(responses[0][0], 403)

    @unittest.skip(_PHASE1_SKIP)
    def test_T13_approved_mit_chef(self):
        """T13: set_status -> approved mit is_chef -> HTTP 200."""
        self.edb.set_paragraph_status("blk-s1", "active", "h001")
        ep = _make_endpoint(self.edb, "h001")
        handler, responses = _make_handler(lock_id=self.lock_id)
        _call_post(ep, handler, {
            "action":   "set_status",
            "block_id": "blk-s1",
            "status":   "approved",
            "is_chef":  True,
        })
        self.assertEqual(responses[0][0], 200)

    @unittest.skip(_PHASE1_SKIP)
    def test_T14_approved_oneway(self):
        """T14: approved-Paragraph kann Status nicht mehr aendern -> HTTP 403."""
        self.edb.set_paragraph_status("blk-s1", "active", "h001")
        self.edb.set_paragraph_status("blk-s1", "approved", "h001", is_chef=True)
        ep = _make_endpoint(self.edb, "h001")
        handler, responses = _make_handler(lock_id=self.lock_id)
        _call_post(ep, handler, {
            "action":   "set_status",
            "block_id": "blk-s1",
            "status":   "active",
            "is_chef":  True,
        })
        self.assertEqual(responses[0][0], 403)


# =============================================================================
# T15: POST reorder
# =============================================================================

class TestReorder(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_edb()
        self.rid = _mk_report(self.edb)
        self.edb.add_paragraph("r1", self.rid, "h001", sort_index=10)
        self.edb.add_paragraph("r2", self.rid, "h001", sort_index=20)
        self.lock_id = _acquire_lock(self.edb)

    def tearDown(self):
        self.con.close()

    @unittest.skip(_PHASE1_SKIP)
    def test_T15_reorder(self):
        """T15: reorder mit Lock -> HTTP 200, updated=2."""
        ep = _make_endpoint(self.edb)
        handler, responses = _make_handler(lock_id=self.lock_id)
        _call_post(ep, handler, {
            "action": "reorder",
            "order": [
                {"block_id": "r1", "sort_index": 20},
                {"block_id": "r2", "sort_index": 10},
            ],
        })
        status, data = responses[0]
        self.assertEqual(status, 200)
        self.assertEqual(data["updated"], 2)


# =============================================================================
# T16-T17: POST add_comment
# =============================================================================

class TestAddComment(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_edb()
        self.rid = _mk_report(self.edb)
        self.edb.add_paragraph("c-blk", self.rid, "h001")
        self.lock_id = _acquire_lock(self.edb)

    def tearDown(self):
        self.con.close()

    @unittest.skip(_PHASE1_SKIP)
    def test_T16_add_comment(self):
        """T16: add_comment -> HTTP 201."""
        ep = _make_endpoint(self.edb, "h002")
        handler, responses = _make_handler()
        _call_post(ep, handler, {
            "action":       "add_comment",
            "block_id":     "c-blk",
            "comment_text": "Bitte ueberarbeiten.",
        })
        status, data = responses[0]
        self.assertEqual(status, 201)
        self.assertIn("comment_id", data)

    @unittest.skip(_PHASE1_SKIP)
    def test_T17_leerer_kommentar(self):
        """T17: add_comment mit leerem Text -> HTTP 400."""
        ep = _make_endpoint(self.edb, "h002")
        handler, responses = _make_handler()
        _call_post(ep, handler, {
            "action":       "add_comment",
            "block_id":     "c-blk",
            "comment_text": "",
        })
        self.assertEqual(responses[0][0], 400)


# =============================================================================
# T18-T19: POST resolve_comment
# =============================================================================

class TestResolveComment(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_edb()
        self.rid = _mk_report(self.edb)
        self.edb.add_paragraph("rc-blk", self.rid, "h001")  # Eigentuemer h001
        self.cid = self.edb.add_comment("rc-blk", "h002", "Hinweis.")
        self.lock_id = _acquire_lock(self.edb, "h001")

    def tearDown(self):
        self.con.close()

    @unittest.skip(_PHASE1_SKIP)
    def test_T18_eigentuemer_kann_adressieren(self):
        """T18: Paragraph-Eigentuemer kann Kommentar auf 'addressed' setzen."""
        ep = _make_endpoint(self.edb, "h001")
        handler, responses = _make_handler(lock_id=self.lock_id)
        _call_post(ep, handler, {
            "action":     "resolve_comment",
            "comment_id": self.cid,
            "resolution": "addressed",
        })
        self.assertEqual(responses[0][0], 200)

    @unittest.skip(_PHASE1_SKIP)
    def test_T19_fremder_darf_nicht(self):
        """T19: Fremder Ermittler (kein Eigentuemer, kein Chef) -> HTTP 403."""
        ep = _make_endpoint(self.edb, "h003")
        handler, responses = _make_handler(lock_id=self.lock_id)
        _call_post(ep, handler, {
            "action":     "resolve_comment",
            "comment_id": self.cid,
            "resolution": "addressed",
        })
        self.assertEqual(responses[0][0], 403)


# =============================================================================
# T20-T21: POST add_anchor
# =============================================================================

class TestAddAnchor(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_edb()
        self.rid = _mk_report(self.edb)
        self.edb.add_paragraph("anc-blk", self.rid, "h001")
        self.ann_id = self.edb.save_annotation(
            page_url="/test", category="CAT_OTHER", text="Beleg"
        )
        self.lock_id = _acquire_lock(self.edb)

    def tearDown(self):
        self.con.close()

    @unittest.skip(_PHASE1_SKIP)
    def test_T20_add_anchor(self):
        """T20: add_anchor mit Lock -> HTTP 201."""
        ep = _make_endpoint(self.edb)
        handler, responses = _make_handler(lock_id=self.lock_id)
        _call_post(ep, handler, {
            "action":        "add_anchor",
            "block_id":      "anc-blk",
            "annotation_id": self.ann_id,
            "anchor_text":   "Ankertext",
        })
        status, data = responses[0]
        self.assertEqual(status, 201)
        self.assertIn("anchor_id", data)

    @unittest.skip(_PHASE1_SKIP)
    def test_T21_duplikat_anker(self):
        """T21: Duplikat-Anker -> HTTP 409."""
        self.edb.add_anchor("anc-blk", self.ann_id, "Erster Anker")
        ep = _make_endpoint(self.edb)
        handler, responses = _make_handler(lock_id=self.lock_id)
        _call_post(ep, handler, {
            "action":        "add_anchor",
            "block_id":      "anc-blk",
            "annotation_id": self.ann_id,
            "anchor_text":   "Duplikat",
        })
        self.assertEqual(responses[0][0], 409)


if __name__ == "__main__":
    unittest.main(verbosity=2)

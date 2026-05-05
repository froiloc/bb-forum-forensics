# =============================================================================
# tests/test_evidence_db_b6.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# =============================================================================
# Testsuite fuer B6-Schema-Methoden in db/evidence_db.py
#
# T01 -- add_paragraph() legt Eintrag mit status='draft' an
# T02 -- add_paragraph() setzt report_block_order wenn sort_index angegeben
# T03 -- get_paragraph() liefert korrekten ReportParagraphRecord
# T04 -- get_paragraphs() sortiert nach sort_index ASC
# T05 -- update_paragraph_content() nur durch Eigentuemer
# T06 -- update_paragraph_content() schlaegt fuer 'approved' fehl
# T07 -- set_paragraph_status() draft -> active durch Eigentuemer
# T08 -- set_paragraph_status() active -> approved nur durch Chef
# T09 -- set_paragraph_status() approved -> * schlaegt fehl (One-Way)
# T10 -- set_block_order() aktualisiert sort_index korrekt
# T11 -- get_block_order_for_report() liefert sortierte Eintraege
# T12 -- add_anchor() erzeugt Eintrag in report_anchors
# T13 -- add_anchor() wirft EvidenceDbError bei Duplikat
# T14 -- get_anchored_annotation_ids() liefert korrekte Menge
# T15 -- get_unreferenced_annotation_count() korrekt nach Anker-Anlage
# T16 -- add_comment() erzeugt Kommentar mit status='pending'
# T17 -- resolve_comment() pending -> addressed durch Paragraph-Eigentuemer
# T18 -- resolve_comment() pending -> revoked nur durch Kommentator
# T19 -- resolve_comment() One-Way: zweiter Aufruf schlaegt fehl
# T20 -- get_cache_entry() Cache-Miss liefert None
# T21 -- set_cache_entry() und get_cache_entry() runden Wert korrekt
# T22 -- clear_cache_for_uid() loescht nur Eintraege fuer angegebene uid
# T23 -- create_report() ohne template_id (B6: template_id entfernt)
# T24 -- get_report_status() auf B6-Schema (report_paragraphs statt report_blocks)
#
# Version: v0.6.089 · Build: 089 · 2026-05-05
# Beleg: Bauplan B6 v0.3 §2.3, Ausdefinitionsgespraech 2026-05-05
# =============================================================================

import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.evidence_db import EvidenceDb, EvidenceDbError


def _make_db() -> tuple[sqlite3.Connection, EvidenceDb]:
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.row_factory = sqlite3.Row
    edb = EvidenceDb(con)
    return con, edb


def _mk_report(edb: EvidenceDb) -> int:
    return edb.create_report("interim", "Testbericht", "h001")


class TestParagraphen(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_db()
        self.report_id = _mk_report(self.edb)

    def tearDown(self):
        self.con.close()

    def test_T01_add_paragraph_default_draft(self):
        """T01: add_paragraph() legt Paragraph mit status='draft' an."""
        bid = self.edb.add_paragraph(
            block_id="blk-001",
            report_id=self.report_id,
            author="h001",
            content="Erster Absatz.",
        )
        self.assertEqual(bid, "blk-001")
        p = self.edb.get_paragraph("blk-001")
        self.assertIsNotNone(p)
        self.assertEqual(p.status, "draft")
        self.assertEqual(p.author, "h001")

    def test_T02_add_paragraph_mit_sort_index(self):
        """T02: add_paragraph() traegt sort_index in report_block_order ein."""
        self.edb.add_paragraph(
            block_id="blk-002",
            report_id=self.report_id,
            author="h001",
            sort_index=10,
        )
        order = self.edb.get_block_order_for_report(self.report_id)
        self.assertEqual(len(order), 1)
        self.assertEqual(order[0]["block_id"], "blk-002")
        self.assertEqual(order[0]["sort_index"], 10)

    def test_T03_get_paragraph_liefert_record(self):
        """T03: get_paragraph() liefert korrekten ReportParagraphRecord."""
        self.edb.add_paragraph(
            block_id="blk-003",
            report_id=self.report_id,
            author="h002",
            content="Inhalt.",
            module_id=5,
        )
        p = self.edb.get_paragraph("blk-003")
        self.assertEqual(p.author, "h002")
        self.assertEqual(p.content, "Inhalt.")
        self.assertEqual(p.module_id, 5)
        self.assertEqual(p.report_id, self.report_id)

    def test_T04_get_paragraphs_sortiert(self):
        """T04: get_paragraphs() sortiert nach sort_index ASC."""
        self.edb.add_paragraph("blk-10", self.report_id, "h001", sort_index=30)
        self.edb.add_paragraph("blk-20", self.report_id, "h001", sort_index=10)
        self.edb.add_paragraph("blk-30", self.report_id, "h001", sort_index=20)
        paras = self.edb.get_paragraphs(self.report_id)
        self.assertEqual([p.block_id for p in paras], ["blk-20", "blk-30", "blk-10"])

    def test_T05_update_nur_eigentuemer(self):
        """T05: update_paragraph_content() nur durch Eigentuemer erlaubt."""
        self.edb.add_paragraph("blk-e1", self.report_id, "h001")
        with self.assertRaises(EvidenceDbError):
            self.edb.update_paragraph_content("blk-e1", "Neu", None, "h002")

    def test_T06_update_approved_verboten(self):
        """T06: update_paragraph_content() schlaegt fuer 'approved'-Paragraph fehl."""
        self.edb.add_paragraph("blk-a1", self.report_id, "h001")
        self.edb.set_paragraph_status("blk-a1", "active", "h001")
        self.edb.set_paragraph_status("blk-a1", "approved", "h001", is_chef=True)
        with self.assertRaises(EvidenceDbError):
            self.edb.update_paragraph_content("blk-a1", "Neu", None, "h001")

    def test_T07_status_draft_to_active(self):
        """T07: set_paragraph_status() draft -> active durch Eigentuemer."""
        self.edb.add_paragraph("blk-s1", self.report_id, "h001")
        result = self.edb.set_paragraph_status("blk-s1", "active", "h001")
        self.assertTrue(result)
        self.assertEqual(self.edb.get_paragraph("blk-s1").status, "active")

    def test_T08_approved_nur_chef(self):
        """T08: set_paragraph_status() active -> approved nur durch Chef."""
        self.edb.add_paragraph("blk-s2", self.report_id, "h001")
        self.edb.set_paragraph_status("blk-s2", "active", "h001")
        with self.assertRaises(EvidenceDbError):
            self.edb.set_paragraph_status("blk-s2", "approved", "h001", is_chef=False)
        # Mit is_chef=True muss es funktionieren
        self.edb.set_paragraph_status("blk-s2", "approved", "h001", is_chef=True)
        self.assertEqual(self.edb.get_paragraph("blk-s2").status, "approved")

    def test_T09_approved_ist_oneway(self):
        """T09: approved-Paragraph kann Status nicht mehr aendern."""
        self.edb.add_paragraph("blk-s3", self.report_id, "h001")
        self.edb.set_paragraph_status("blk-s3", "active", "h001")
        self.edb.set_paragraph_status("blk-s3", "approved", "h001", is_chef=True)
        with self.assertRaises(EvidenceDbError):
            self.edb.set_paragraph_status("blk-s3", "active", "h001", is_chef=True)


class TestBlockOrder(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_db()
        self.report_id = _mk_report(self.edb)

    def tearDown(self):
        self.con.close()

    def test_T10_set_block_order(self):
        """T10: set_block_order() aktualisiert sort_index korrekt."""
        self.edb.add_paragraph("bo-1", self.report_id, "h001", sort_index=1)
        self.edb.add_paragraph("bo-2", self.report_id, "h001", sort_index=2)
        count = self.edb.set_block_order(
            [{"block_id": "bo-1", "sort_index": 20},
             {"block_id": "bo-2", "sort_index": 10}],
            modified_by="h002",
        )
        self.assertEqual(count, 2)
        order = self.edb.get_block_order_for_report(self.report_id)
        self.assertEqual(order[0]["block_id"], "bo-2")
        self.assertEqual(order[0]["sort_index"], 10)

    def test_T11_get_block_order_sortiert(self):
        """T11: get_block_order_for_report() liefert nach sort_index sortiert."""
        self.edb.add_paragraph("or-1", self.report_id, "h001", sort_index=50)
        self.edb.add_paragraph("or-2", self.report_id, "h001", sort_index=5)
        order = self.edb.get_block_order_for_report(self.report_id)
        self.assertEqual(order[0]["sort_index"], 5)
        self.assertEqual(order[1]["sort_index"], 50)


class TestAnker(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_db()
        rid = _mk_report(self.edb)
        self.edb.add_paragraph("anc-1", rid, "h001")
        # Annotation anlegen
        self.ann_id = self.edb.save_annotation(
            page_url="/test", category="CAT_OTHER", text="Beleg"
        )

    def tearDown(self):
        self.con.close()

    def test_T12_add_anchor(self):
        """T12: add_anchor() erzeugt Eintrag in report_anchors."""
        aid = self.edb.add_anchor("anc-1", self.ann_id, "Ankertext")
        self.assertGreater(aid, 0)
        anchors = self.edb.get_anchors_for_paragraph("anc-1")
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].anchor_text, "Ankertext")

    def test_T13_add_anchor_duplikat(self):
        """T13: add_anchor() wirft EvidenceDbError bei Duplikat."""
        self.edb.add_anchor("anc-1", self.ann_id, "Anker 1")
        with self.assertRaises(EvidenceDbError):
            self.edb.add_anchor("anc-1", self.ann_id, "Anker 2")

    def test_T14_get_anchored_ids(self):
        """T14: get_anchored_annotation_ids() liefert korrekte Menge."""
        self.edb.add_anchor("anc-1", self.ann_id, "Anker")
        ids = self.edb.get_anchored_annotation_ids()
        self.assertIn(self.ann_id, ids)

    def test_T15_unreferenced_count(self):
        """T15: get_unreferenced_annotation_count() korrekt nach Anker-Anlage."""
        # Vor Anker: 1 unreferenziert
        self.assertEqual(self.edb.get_unreferenced_annotation_count(), 1)
        self.edb.add_anchor("anc-1", self.ann_id, "Anker")
        # Nach Anker: 0 unreferenziert
        self.assertEqual(self.edb.get_unreferenced_annotation_count(), 0)


class TestKommentare(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_db()
        rid = _mk_report(self.edb)
        self.edb.add_paragraph("com-1", rid, "h001")  # Eigentuemer h001

    def tearDown(self):
        self.con.close()

    def test_T16_add_comment_pending(self):
        """T16: add_comment() erzeugt Kommentar mit status='pending'."""
        cid = self.edb.add_comment("com-1", "h002", "Bitte ueberarbeiten.")
        self.assertGreater(cid, 0)
        comments = self.edb.get_comments_for_paragraph("com-1")
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0].status, "pending")

    def test_T17_resolve_addressed_durch_eigentuemer(self):
        """T17: resolve_comment() pending -> addressed durch Paragraph-Eigentuemer."""
        cid = self.edb.add_comment("com-1", "h002", "Hinweis.")
        result = self.edb.resolve_comment(
            cid, "addressed", "h001", requesting_user="h001"
        )
        self.assertTrue(result)
        c = self.edb.get_comments_for_paragraph("com-1")[0]
        self.assertEqual(c.status, "addressed")

    def test_T18_resolve_revoked_nur_kommentator(self):
        """T18: resolve_comment() pending -> revoked nur durch Kommentator."""
        cid = self.edb.add_comment("com-1", "h002", "Hinweis.")
        # h001 (nicht Kommentator) darf nicht revoken
        with self.assertRaises(EvidenceDbError):
            self.edb.resolve_comment(
                cid, "revoked", "h001", requesting_user="h001"
            )
        # h002 (Kommentator) darf revoken
        result = self.edb.resolve_comment(
            cid, "revoked", "h002", requesting_user="h002"
        )
        self.assertTrue(result)

    def test_T19_resolve_oneway(self):
        """T19: resolve_comment() ist One-Way (kein zweiter Aufruf)."""
        cid = self.edb.add_comment("com-1", "h002", "Hinweis.")
        self.edb.resolve_comment(cid, "addressed", "h001", requesting_user="h001")
        with self.assertRaises(EvidenceDbError):
            self.edb.resolve_comment(cid, "dismissed", "h001", requesting_user="h001")


class TestPlaceholderCache(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_db()

    def tearDown(self):
        self.con.close()

    def test_T20_cache_miss(self):
        """T20: get_cache_entry() liefert None bei Cache-Miss."""
        result = self.edb.get_cache_entry("user.username", 42)
        self.assertIsNone(result)

    def test_T21_set_und_get(self):
        """T21: set_cache_entry() und get_cache_entry() runden Wert korrekt."""
        self.edb.set_cache_entry("user.username", 42, "TestUser")
        result = self.edb.get_cache_entry("user.username", 42)
        self.assertEqual(result, "TestUser")

    def test_T22_clear_loescht_nur_uid(self):
        """T22: clear_cache_for_uid() loescht nur Eintraege fuer angegebene uid."""
        self.edb.set_cache_entry("user.username", 42, "UserA")
        self.edb.set_cache_entry("user.username", 99, "UserB")
        deleted = self.edb.clear_cache_for_uid(42)
        self.assertEqual(deleted, 1)
        self.assertIsNone(self.edb.get_cache_entry("user.username", 42))
        self.assertEqual(self.edb.get_cache_entry("user.username", 99), "UserB")


class TestReportB6(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_db()

    def tearDown(self):
        self.con.close()

    def test_T23_create_report_ohne_template_id(self):
        """T23: create_report() funktioniert ohne template_id (B6 entfernt dieses Feld)."""
        rid = self.edb.create_report("interim", "Testbericht", "h001")
        self.assertGreater(rid, 0)
        r = self.edb.get_report(rid)
        self.assertEqual(r.report_type, "interim")
        self.assertEqual(r.created_by, "h001")

    def test_T24_get_report_status_b6(self):
        """T24: get_report_status() liest aus report_paragraphs (B6-Schema)."""
        # Vor Paragraph: has_draft=False
        status = self.edb.get_report_status()
        self.assertFalse(status["has_draft"])

        # Nach Paragraph: has_draft=True
        rid = self.edb.create_report("interim", "Test", "h001")
        self.edb.add_paragraph("p-stat", rid, "h001", content="Inhalt")
        status = self.edb.get_report_status()
        self.assertTrue(status["has_draft"])
        self.assertEqual(status["last_editor"], "h001")


if __name__ == "__main__":
    unittest.main(verbosity=2)

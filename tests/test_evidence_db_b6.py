# =============================================================================
# tests/test_evidence_db_b6.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# =============================================================================
# Testsuite fuer B6-Schema-Methoden in db/evidence_db.py
#
# T01 -- save_block() legt neuen Block in report_blocks an (INSERT)
# T02 -- save_block() setzt report_block_order wenn sort_index angegeben
# T03 -- get_block() liefert korrekten ReportBlockRecord
# T04 -- get_blocks_for_report() sortiert nach sort_index ASC
# T05 -- update_block() nur durch Eigentuemer erlaubt
# T06 -- update_block() schlaegt fuer freigegebenen Bericht fehl
# T07 -- save_block() UPDATE: author und created_at unveraenderlich
# T08 -- delete_block() entfernt Block und Kaskade (order, anchors, comments)
# T09 -- delete_block() nur durch Eigentuemer erlaubt
# T10 -- set_block_order() aktualisiert sort_index korrekt
# T11 -- get_block_order_for_report() liefert sortierte Eintraege
# T12 -- add_anchor() erzeugt Eintrag in report_anchors
# T13 -- add_anchor() wirft EvidenceDbError bei Duplikat
# T14 -- get_anchored_annotation_ids() liefert korrekte Menge
# T15 -- get_unreferenced_annotation_count() korrekt nach Anker-Anlage
# T16 -- add_comment() erzeugt Kommentar mit status='pending'
# T17 -- resolve_comment() pending -> addressed durch Block-Eigentuemer
# T18 -- resolve_comment() pending -> revoked nur durch Kommentator
# T19 -- resolve_comment() One-Way: zweiter Aufruf schlaegt fehl
# T20 -- get_cache_entry() Cache-Miss liefert None
# T21 -- set_cache_entry() und get_cache_entry() speichern korrekt
# T22 -- clear_cache_for_uid() loescht nur Eintraege fuer angegebene uid
# T23 -- create_report() korrekt (kein Block-Status-Lifecycle)
# T24 -- get_report_status() liest aus report_blocks (Phase 1)
# T25 -- get_anchors_for_block() liefert Anker fuer Block
# T26 -- get_comments_for_block() liefert Kommentare fuer Block
#
# Version: v0.6.099 · Build: 099 · 2026-05-06
# Beleg: Bauplan B6 v0.5 §2.3, Projektgespraech 2026-05-06
# =============================================================================

import sqlite3
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.evidence_db import EvidenceDb, EvidenceDbError, ReportBlockRecord


def _make_db() -> tuple[sqlite3.Connection, EvidenceDb]:
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.row_factory = sqlite3.Row
    edb = EvidenceDb(con)
    return con, edb


def _mk_report(edb: EvidenceDb) -> int:
    return edb.create_report("interim", "Testbericht", "h001")


class TestBloecke(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_db()
        self.report_id = _mk_report(self.edb)

    def tearDown(self):
        self.con.close()

    def test_T01_save_block_insert(self):
        """T01: save_block() legt neuen Block an und liefert block_id zurueck."""
        bid = self.edb.save_block(
            block_id="blk-001",
            report_id=self.report_id,
            author="h001",
            block_type="paragraph",
            block_data='{"text":"Erster Absatz."}',
        )
        self.assertEqual(bid, "blk-001")
        b = self.edb.get_block("blk-001")
        self.assertIsNotNone(b)
        self.assertIsInstance(b, ReportBlockRecord)
        self.assertEqual(b.author, "h001")
        self.assertEqual(b.block_type, "paragraph")
        self.assertEqual(b.block_data, '{"text":"Erster Absatz."}')
        self.assertEqual(b.report_id, self.report_id)

    def test_T02_save_block_mit_sort_index(self):
        """T02: save_block() traegt sort_index in report_block_order ein."""
        self.edb.save_block(
            block_id="blk-002",
            report_id=self.report_id,
            author="h001",
            block_type="header",
            sort_index=10,
        )
        order = self.edb.get_block_order_for_report(self.report_id)
        self.assertEqual(len(order), 1)
        self.assertEqual(order[0]["block_id"], "blk-002")
        self.assertEqual(order[0]["sort_index"], 10)

    def test_T03_get_block_liefert_record(self):
        """T03: get_block() liefert korrekten ReportBlockRecord."""
        self.edb.save_block(
            block_id="blk-003",
            report_id=self.report_id,
            author="h002",
            block_type="list",
            block_data='{"items":["A","B"]}',
            module_id=5,
        )
        b = self.edb.get_block("blk-003")
        self.assertEqual(b.author, "h002")
        self.assertEqual(b.block_type, "list")
        self.assertEqual(b.block_data, '{"items":["A","B"]}')
        self.assertEqual(b.module_id, 5)
        self.assertEqual(b.report_id, self.report_id)

    def test_T04_get_blocks_for_report_sortiert(self):
        """T04: get_blocks_for_report() sortiert nach sort_index ASC."""
        self.edb.save_block("blk-10", self.report_id, "h001", "paragraph", sort_index=30)
        self.edb.save_block("blk-20", self.report_id, "h001", "paragraph", sort_index=10)
        self.edb.save_block("blk-30", self.report_id, "h001", "paragraph", sort_index=20)
        blocks = self.edb.get_blocks_for_report(self.report_id)
        self.assertEqual([b.block_id for b in blocks], ["blk-20", "blk-30", "blk-10"])

    def test_T05_update_nur_eigentuemer(self):
        """T05: update_block() nur durch Eigentuemer erlaubt."""
        self.edb.save_block("blk-e1", self.report_id, "h001", "paragraph")
        with self.assertRaises(EvidenceDbError):
            self.edb.update_block("blk-e1", '{"text":"Neu"}', None, "h002")

    def test_T06_update_approved_bericht_verboten(self):
        """T06: update_block() schlaegt fehl wenn Bericht freigegeben."""
        self.edb.save_block("blk-a1", self.report_id, "h001", "paragraph")
        # Build 379: Die Zustandsmaschine erlaubt kein 'draft' -> 'approved'
        # (BERICHTS-STATUSMODELL). Der Weg fuehrt ueber 'submitted'.
        self.edb.update_report_status(self.report_id, "submitted", "autor")
        self.edb.update_report_status(self.report_id, "approved", "chef")
        with self.assertRaises(EvidenceDbError):
            self.edb.update_block("blk-a1", '{"text":"Neu"}', None, "h001")

    def test_T07_save_block_update_author_unveraenderlich(self):
        """T07: save_block() UPDATE aendert author und created_at nicht."""
        self.edb.save_block("blk-u1", self.report_id, "h001", "paragraph",
                            block_data='{"text":"Alt"}')
        b_vor = self.edb.get_block("blk-u1")
        time.sleep(0.01)
        self.edb.save_block("blk-u1", self.report_id, "h001", "paragraph",
                            block_data='{"text":"Neu"}')
        b_nach = self.edb.get_block("blk-u1")
        self.assertEqual(b_nach.author, b_vor.author)
        self.assertEqual(b_nach.created_at, b_vor.created_at)
        self.assertEqual(b_nach.block_data, '{"text":"Neu"}')

    def test_T07b_save_block_update_report_id_unveraenderlich(self):
        """T07b (Build 477): save_block() UPDATE verschiebt einen Block NIE
        in einen anderen Vermerk/Bericht.

        Reproduziert die BERICHTS-VERTAUSCHUNG: Ein bestehender Block von
        Vermerk A wird per save_block() mit der report_id von Vermerk B
        gespeichert (so wie es der Auto-Save nach einem Vermerk-Wechsel tat,
        weil DocumentLayer die report_id aus dem bereits umgeschalteten
        ReportLayer-Kontext injiziert). Erwartung: Der Block bleibt bei A,
        B bleibt leer.
        Beleg: Bugfix Build 477, Fehlerbeschreibung Baustelle 6.
        """
        report_a = self.report_id
        report_b = self.edb.create_report("addendum", "Vermerk B", "h001")

        # Block gehoert zu Vermerk A.
        self.edb.save_block("blk-move", report_a, "h001", "paragraph",
                            block_data='{"text":"Inhalt A"}')
        self.assertEqual(self.edb.get_block("blk-move").report_id, report_a)

        # UPDATE desselben Blocks — faelschlich mit report_id von Vermerk B.
        self.edb.save_block("blk-move", report_b, "h001", "paragraph",
                            block_data='{"text":"Inhalt A – bearbeitet"}')

        # Der Block MUSS bei A bleiben, der Inhalt darf aktualisiert sein.
        b_nach = self.edb.get_block("blk-move")
        self.assertEqual(
            b_nach.report_id, report_a,
            "report_id wurde bei UPDATE veraendert — Block wurde verschoben!",
        )
        self.assertEqual(b_nach.block_data, '{"text":"Inhalt A – bearbeitet"}')

        # Gegenprobe: Vermerk B enthaelt keinen Block; Vermerk A genau einen.
        self.assertEqual(len(self.edb.get_blocks_for_report(report_b)), 0)
        blocks_a = self.edb.get_blocks_for_report(report_a)
        self.assertEqual([b.block_id for b in blocks_a], ["blk-move"])

    def test_T08_delete_block_kaskade(self):
        """T08: delete_block() entfernt Block und alle Kaskaden-Eintraege."""
        self.edb.save_block("blk-d1", self.report_id, "h001", "paragraph", sort_index=1)
        ann_id = self.edb.save_annotation("/test", "CAT_OTHER", "Text")
        self.edb.add_anchor("blk-d1", ann_id, "Anker")
        self.edb.add_comment("blk-d1", "h002", "Kommentar")

        result = self.edb.delete_block("blk-d1", "h001")
        self.assertTrue(result)

        self.assertIsNone(self.edb.get_block("blk-d1"))
        self.assertEqual(len(self.edb.get_block_order_for_report(self.report_id)), 0)
        self.assertEqual(len(self.edb.get_anchors_for_block("blk-d1")), 0)
        self.assertEqual(len(self.edb.get_comments_for_block("blk-d1")), 0)

    def test_T09_delete_block_nur_eigentuemer(self):
        """T09: delete_block() wirft EvidenceDbError wenn nicht Eigentuemer."""
        self.edb.save_block("blk-d2", self.report_id, "h001", "paragraph")
        with self.assertRaises(EvidenceDbError):
            self.edb.delete_block("blk-d2", "h002")
        self.assertIsNotNone(self.edb.get_block("blk-d2"))


class TestBlockOrder(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_db()
        self.report_id = _mk_report(self.edb)

    def tearDown(self):
        self.con.close()

    def test_T10_set_block_order(self):
        """T10: set_block_order() aktualisiert sort_index korrekt."""
        self.edb.save_block("bo-1", self.report_id, "h001", "paragraph", sort_index=1)
        self.edb.save_block("bo-2", self.report_id, "h001", "paragraph", sort_index=2)
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
        self.edb.save_block("or-1", self.report_id, "h001", "paragraph", sort_index=50)
        self.edb.save_block("or-2", self.report_id, "h001", "paragraph", sort_index=5)
        order = self.edb.get_block_order_for_report(self.report_id)
        self.assertEqual(order[0]["sort_index"], 5)
        self.assertEqual(order[1]["sort_index"], 50)


class TestAnker(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_db()
        rid = _mk_report(self.edb)
        self.edb.save_block("anc-1", rid, "h001", "paragraph")
        self.ann_id = self.edb.save_annotation(
            page_url="/test", category="CAT_OTHER", text="Beleg"
        )

    def tearDown(self):
        self.con.close()

    def test_T12_add_anchor(self):
        """T12: add_anchor() erzeugt Eintrag in report_anchors."""
        aid = self.edb.add_anchor("anc-1", self.ann_id, "Ankertext")
        self.assertGreater(aid, 0)
        anchors = self.edb.get_anchors_for_block("anc-1")
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
        self.assertEqual(self.edb.get_unreferenced_annotation_count(), 1)
        self.edb.add_anchor("anc-1", self.ann_id, "Anker")
        self.assertEqual(self.edb.get_unreferenced_annotation_count(), 0)

    def test_T25_get_anchors_for_block(self):
        """T25: get_anchors_for_block() liefert Anker fuer Block."""
        self.edb.add_anchor("anc-1", self.ann_id, "Textanker")
        anchors = self.edb.get_anchors_for_block("anc-1")
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].block_id, "anc-1")
        self.assertEqual(anchors[0].annotation_id, self.ann_id)


class TestKommentare(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_db()
        rid = _mk_report(self.edb)
        self.edb.save_block("com-1", rid, "h001", "paragraph")

    def tearDown(self):
        self.con.close()

    def test_T16_add_comment_pending(self):
        """T16: add_comment() erzeugt Kommentar mit status='pending'."""
        cid = self.edb.add_comment("com-1", "h002", "Bitte ueberarbeiten.")
        self.assertGreater(cid, 0)
        comments = self.edb.get_comments_for_block("com-1")
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0].status, "pending")

    def test_T17_resolve_addressed_durch_eigentuemer(self):
        """T17: resolve_comment() pending -> addressed durch Block-Eigentuemer."""
        cid = self.edb.add_comment("com-1", "h002", "Hinweis.")
        result = self.edb.resolve_comment(
            cid, "addressed", "h001", requesting_user="h001"
        )
        self.assertTrue(result)
        c = self.edb.get_comments_for_block("com-1")[0]
        self.assertEqual(c.status, "addressed")

    def test_T18_resolve_revoked_nur_kommentator(self):
        """T18: resolve_comment() pending -> revoked nur durch Kommentator."""
        cid = self.edb.add_comment("com-1", "h002", "Hinweis.")
        with self.assertRaises(EvidenceDbError):
            self.edb.resolve_comment(cid, "revoked", "h001", requesting_user="h001")
        result = self.edb.resolve_comment(
            cid, "revoked", "h002", requesting_user="h002"
        )
        self.assertTrue(result)

    def test_T19_resolve_oneway(self):
        """T19: resolve_comment() ist One-Way (kein zweiter Aufruf moeglich)."""
        cid = self.edb.add_comment("com-1", "h002", "Hinweis.")
        self.edb.resolve_comment(cid, "addressed", "h001", requesting_user="h001")
        with self.assertRaises(EvidenceDbError):
            self.edb.resolve_comment(cid, "dismissed", "h001", requesting_user="h001")

    def test_T26_get_comments_for_block(self):
        """T26: get_comments_for_block() liefert Kommentare fuer Block."""
        self.edb.add_comment("com-1", "h002", "Erster Kommentar.")
        self.edb.add_comment("com-1", "h003", "Zweiter Kommentar.")
        comments = self.edb.get_comments_for_block("com-1")
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0].block_id, "com-1")
        self.assertEqual(comments[0].author, "h002")


class TestPlaceholderCache(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_db()

    def tearDown(self):
        self.con.close()

    def test_T20_cache_miss(self):
        """T20: get_cache_entry() liefert None bei Cache-Miss."""
        self.assertIsNone(self.edb.get_cache_entry("user.username", 42))

    def test_T21_set_und_get(self):
        """T21: set_cache_entry() und get_cache_entry() speichern korrekt."""
        self.edb.set_cache_entry("user.username", 42, "TestUser")
        self.assertEqual(self.edb.get_cache_entry("user.username", 42), "TestUser")

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

    def test_T23_create_report_korrekt(self):
        """T23: create_report() funktioniert korrekt (kein Block-Status-Lifecycle)."""
        rid = self.edb.create_report("interim", "Testbericht", "h001")
        self.assertGreater(rid, 0)
        r = self.edb.get_report(rid)
        self.assertEqual(r.report_type, "interim")
        self.assertEqual(r.created_by, "h001")
        self.assertEqual(r.status, "draft")

    def test_T24_get_report_status_liest_report_blocks(self):
        """T24: get_report_status() liest aus report_blocks (Phase 1)."""
        status = self.edb.get_report_status()
        self.assertFalse(status["has_draft"])

        rid = self.edb.create_report("interim", "Test", "h001")
        self.edb.save_block("p-stat", rid, "h001", "paragraph",
                            block_data='{"text":"Inhalt"}')
        status = self.edb.get_report_status()
        self.assertTrue(status["has_draft"])
        self.assertEqual(status["last_editor"], "h001")


if __name__ == "__main__":
    unittest.main(verbosity=2)

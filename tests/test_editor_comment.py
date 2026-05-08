# =============================================================================
# tests/test_editor_comment.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# =============================================================================
# Testsuite fuer forensic_api/editor_comment.py
#
# T01 -- add_comment: fehlende Pflichtfelder -> HTTP 400
# T02 -- add_comment: leerer comment_text -> HTTP 400
# T03 -- add_comment: erfolgreich -> HTTP 201 mit comment_id
# T04 -- add_comment: EvidenceDbError -> HTTP 400
# T05 -- resolve_comment: fehlende Pflichtfelder -> HTTP 400
# T06 -- resolve_comment: ungueltige resolution -> HTTP 400
# T07 -- resolve_comment: addressed ohne Lock -> HTTP 423
# T08 -- resolve_comment: dismissed ohne Lock -> HTTP 423
# T09 -- resolve_comment: revoked ohne Lock -> erlaubt (HTTP 200)
# T10 -- resolve_comment: addressed mit Lock -> HTTP 200
# T11 -- resolve_comment: EvidenceDbError (FORBIDDEN) -> HTTP 403
# T12 -- resolve_comment: Kommentar nicht gefunden -> HTTP 404
#
# Version: v0.6.102 · Build: 102 · 2026-05-06
# Beleg: Bauplan B6 v0.5 §4.4.4, §5, Projektgespraech 2026-05-06
# =============================================================================

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.evidence_db import EvidenceDb, EvidenceDbError
from forensic_api.editor_comment import EditorCommentEndpoint


# =============================================================================
# Hilfsfunktionen
# =============================================================================

def _make_edb() -> tuple[sqlite3.Connection, EvidenceDb]:
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.row_factory = sqlite3.Row
    edb = EvidenceDb(con)
    return con, edb


def _make_bundle(edb: EvidenceDb) -> MagicMock:
    bundle = MagicMock()
    bundle.evidence = edb
    # coordinator.db: kein Chef-Recht per Default
    bundle.coordinator.get_investigator_by_username.return_value = None
    return bundle


def _make_handler() -> tuple[MagicMock, list]:
    """Erstellt einen Mock-Handler und sammelt alle Antworten."""
    responses = []
    handler = MagicMock()
    handler.headers = {}
    handler.send_response_body = lambda status, body, **kw: responses.append(
        (status, json.loads(body.decode("utf-8")) if body else {})
    )
    return handler, responses


def _mk_report(edb: EvidenceDb) -> int:
    return edb.create_report("interim", "Testbericht", "h001")


def _mk_block(edb: EvidenceDb, report_id: int, author="h001",
              block_id="blk-001") -> str:
    edb.save_block(block_id, report_id, author, "paragraph", '{"text":"Test"}')
    return block_id


def _mk_comment(edb: EvidenceDb, block_id: str,
                author="h002", text="Hinweis.") -> int:
    return edb.add_comment(block_id, author, text)


# =============================================================================
# T01-T04: action_add_comment
# =============================================================================

class TestAddComment(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_edb()
        self.bundle = _make_bundle(self.edb)
        self.rid = _mk_report(self.edb)
        _mk_block(self.edb, self.rid)

    def tearDown(self):
        self.con.close()

    def _ep(self, username="h002") -> EditorCommentEndpoint:
        return EditorCommentEndpoint(self.bundle, username)

    def test_T01_fehlende_block_id(self):
        """T01: block_id fehlt -> HTTP 400."""
        handler, responses = _make_handler()
        self._ep().action_add_comment(handler, {"comment_text": "Test"})
        self.assertEqual(responses[0][0], 400)
        self.assertEqual(responses[0][1]["code"], "MISSING_FIELDS")

    def test_T02_leerer_comment_text(self):
        """T02: leerer comment_text -> HTTP 400."""
        handler, responses = _make_handler()
        self._ep().action_add_comment(handler, {
            "block_id": "blk-001", "comment_text": "   "
        })
        self.assertEqual(responses[0][0], 400)

    def test_T03_erfolgreich(self):
        """T03: gueltige Anfrage -> HTTP 201 mit comment_id."""
        handler, responses = _make_handler()
        self._ep().action_add_comment(handler, {
            "block_id":     "blk-001",
            "comment_text": "Bitte ueberarbeiten.",
        })
        self.assertEqual(responses[0][0], 201)
        self.assertIn("comment_id", responses[0][1])
        self.assertGreater(responses[0][1]["comment_id"], 0)

    def test_T04_evidence_db_error(self):
        """T04: EvidenceDbError (z.B. leerer author) -> HTTP 400."""
        handler, responses = _make_handler()
        # Ungueltige block_id (existiert nicht) -> EvidenceDbError
        # Da report_comments FK auf report_blocks — sqlite3 FK-Check muss aktiv sein
        # Einfacher: leeren author erzwingen via Monkeypatching
        orig = self.edb.add_comment
        def failing(*args, **kwargs):
            raise EvidenceDbError("author darf nicht leer sein.")
        self.edb.add_comment = failing
        try:
            self._ep().action_add_comment(handler, {
                "block_id": "blk-001", "comment_text": "Test"
            })
        finally:
            self.edb.add_comment = orig
        self.assertEqual(responses[0][0], 400)


# =============================================================================
# T05-T12: action_resolve_comment
# =============================================================================

class TestResolveComment(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_edb()
        self.bundle = _make_bundle(self.edb)
        self.rid = _mk_report(self.edb)
        _mk_block(self.edb, self.rid, author="h001")
        # Lock anlegen fuer Tests die ihn benoetigen
        self.lock_id = self.edb.acquire_lock("h001", "sse-test")
        self.cid = _mk_comment(self.edb, "blk-001", author="h002")

    def tearDown(self):
        self.con.close()

    def _ep(self, username="h001") -> EditorCommentEndpoint:
        return EditorCommentEndpoint(self.bundle, username)

    def test_T05_fehlende_comment_id(self):
        """T05: comment_id fehlt -> HTTP 400."""
        handler, responses = _make_handler()
        self._ep().action_resolve_comment(handler,
            {"resolution": "addressed"}, self.lock_id)
        self.assertEqual(responses[0][0], 400)

    def test_T06_ungueltige_resolution(self):
        """T06: ungueltige resolution -> HTTP 400."""
        handler, responses = _make_handler()
        self._ep().action_resolve_comment(handler,
            {"comment_id": self.cid, "resolution": "xyz"}, self.lock_id)
        self.assertEqual(responses[0][0], 400)

    def test_T07_addressed_ohne_lock(self):
        """T07: addressed ohne Lock -> HTTP 423."""
        handler, responses = _make_handler()
        self._ep().action_resolve_comment(handler,
            {"comment_id": self.cid, "resolution": "addressed"}, None)
        self.assertEqual(responses[0][0], 423)

    def test_T08_dismissed_ohne_lock(self):
        """T08: dismissed ohne Lock -> HTTP 423."""
        handler, responses = _make_handler()
        self._ep().action_resolve_comment(handler,
            {"comment_id": self.cid, "resolution": "dismissed"}, None)
        self.assertEqual(responses[0][0], 423)

    def test_T09_revoked_ohne_lock_erlaubt(self):
        """T09: revoked benoetigt kein Lock -> HTTP 200."""
        handler, responses = _make_handler()
        # h002 ist Kommentator -> darf revoken
        ep = EditorCommentEndpoint(self.bundle, "h002")
        ep.action_resolve_comment(handler,
            {"comment_id": self.cid, "resolution": "revoked"}, None)
        self.assertEqual(responses[0][0], 200)
        self.assertEqual(responses[0][1]["resolution"], "revoked")

    def test_T10_addressed_mit_lock(self):
        """T10: addressed mit gueltigem Lock -> HTTP 200."""
        handler, responses = _make_handler()
        # h001 ist Block-Eigentuemer -> darf addressed setzen
        self._ep("h001").action_resolve_comment(handler,
            {"comment_id": self.cid, "resolution": "addressed"}, self.lock_id)
        self.assertEqual(responses[0][0], 200)

    def test_T11_forbidden(self):
        """T11: Fremder darf nicht adressieren -> HTTP 403."""
        handler, responses = _make_handler()
        # h003 ist weder Kommentator noch Block-Eigentuemer noch Chef
        ep = EditorCommentEndpoint(self.bundle, "h003")
        ep.action_resolve_comment(handler,
            {"comment_id": self.cid, "resolution": "addressed"}, self.lock_id)
        self.assertEqual(responses[0][0], 403)

    def test_T12_kommentar_nicht_gefunden(self):
        """T12: unbekannte comment_id -> HTTP 404."""
        handler, responses = _make_handler()
        self._ep().action_resolve_comment(handler,
            {"comment_id": 99999, "resolution": "addressed"}, self.lock_id)
        self.assertEqual(responses[0][0], 404)


    def test_T13_oneway_nach_erstem_erfolg_liefert_403(self):
        """
        T13 Regression Bug 3.5/2.31:
        Ein erfolgreiches revoked (200) soll beim zweiten Versuch 403 liefern.
        Sichert die One-Way-Grundregel (Grundregel 15) serverseitig ab.
        Beleg: Bugfix Build 126, Projektgespraech 2026-05-08
        """
        # Erster Aufruf: revoked durch Kommentator h002 -> 200
        handler1, responses1 = _make_handler()
        ep = EditorCommentEndpoint(self.bundle, "h002")
        ep.action_resolve_comment(
            handler1, {"comment_id": self.cid, "resolution": "revoked"}, None
        )
        self.assertEqual(responses1[0][0], 200, "Erster revoked-Aufruf muss 200 sein")

        # Zweiter Aufruf: Kommentar ist bereits revoked -> 403 (One-Way)
        handler2, responses2 = _make_handler()
        ep.action_resolve_comment(
            handler2, {"comment_id": self.cid, "resolution": "revoked"}, None
        )
        self.assertEqual(
            responses2[0][0], 403,
            "Zweiter Aufruf auf geloesten Kommentar muss 403 sein (One-Way)"
        )
        self.assertIn("One-Way", responses2[0][1].get("error", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)

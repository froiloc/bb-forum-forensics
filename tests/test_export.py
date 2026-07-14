# =============================================================================
# tests/test_export.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6/7: Berichte & Exports
# =============================================================================
# Testsuite fuer forensic_api/export.py (NEU ab Build 399).
#
# HISTORIE: Bis Build 397 testeten fuenf Faelle (T03/T04/T05/T07/T08) ein
# v0.3-Interface (get_paragraphs / report_paragraphs) und waren @unittest.skip
# ("Umbau in Build 100" — nie gekommen, Befund B2). Die verbliebenen liefen
# gegen einen MagicMock-Bundle und waren "gruen aber tot".
#
# Diese Suite prueft den umgestellten, DUENNEN Endpunkt gegen eine ECHTE
# EvidenceDb (kein MagicMock an der Interface-Grenze):
#   E01 -- Default-Format html -> 200, valides HTML, Content-Disposition
#   E02 -- format=docx   -> 200 (.docx/ZIP), 503 nur falls python-docx fehlt (Build 402)
#   E03 -- format=sqlite -> 200 (SQLite-Magic) (Build 402)
#   E04 -- unbekanntes Format -> 400
#   E05 -- kein Bericht vorhanden -> 404
#   E06 -- explizite report_id wird beachtet (Entwurf -> Statuskopf ENTWURF)
#   E07 -- report_id keine Zahl -> 400
#
# Frueheres T08 ("report_paragraphs nur active/approved") ENTFAELLT bewusst:
# der Status liegt seit dem Editor.js-Umbau am Bericht (reports.status), nicht
# mehr am Absatz (Befund B3). Dies ist vermerkt, nicht still geloescht (GR1).
#
# Version: v0.7.402 · Build: 402 · 2026-07-14
# =============================================================================

import json
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.evidence_db import EvidenceDb
from forensic_api.export import ExportEndpoint


# -- kleine, ECHTE Testdoubles (keine MagicMocks an der DB-Grenze) -----------
class _Bundle:
    """Minimaler DatabaseBundle-Ersatz: echte EvidenceDb, keine Templates/Assets."""
    def __init__(self, edb, con):
        self.evidence = edb
        self.templates = None
        self.assets = None
        self.connection = con


class _Context:
    def __init__(self, uid=42, username="TestNutzer"):
        self.user_id = uid
        self.username = username


class _Handler:
    """Faengt send_response_body ab."""
    def __init__(self):
        self.calls = []

    def send_response_body(self, status, body, **kw):
        self.calls.append((status, body, kw))

    @property
    def last(self):
        return self.calls[-1]


def _make(seed=True):
    con = sqlite3.connect(":memory:", check_same_thread=False)
    edb = EvidenceDb(con)
    if seed:
        con.execute("INSERT INTO reports (id, report_type, sequence_nr, title, created_by, created_at, status) "
                    "VALUES (1,'final',2,'Haupt','inv',2000,'submitted')")
        con.execute("INSERT INTO reports (id, report_type, sequence_nr, title, created_by, created_at, status) "
                    "VALUES (2,'interim',1,'Neben','inv',2500,'draft')")
        con.execute("INSERT INTO report_blocks (block_id, report_id, author, created_at, updated_at, "
                    "block_type, block_data, placeholder_values_json, module_id) "
                    "VALUES ('b1',1,'inv',2000,2000,'paragraph',?,NULL,NULL)",
                    (json.dumps({"text": "Hallo Welt"}),))
        con.execute("INSERT INTO report_block_order (block_id, sort_index, last_modified_by, last_modified_at) "
                    "VALUES ('b1',0,'inv',2000)")
        con.commit()
    return ExportEndpoint(_Bundle(edb, con), _Context(), config=None)


class TestExportEndpoint(unittest.TestCase):

    def test_E01_default_html_ok(self):
        ep = _make()
        h = _Handler()
        ep.handle_get(h, {})                      # kein format -> Default html
        status, body, kw = h.last
        self.assertEqual(status, 200)
        self.assertTrue(body.decode("utf-8").startswith("<!DOCTYPE html>"))
        self.assertIn("attachment", kw["extra_headers"]["Content-Disposition"])

    def test_E02_docx_ok(self):
        # Build 402: DOCX ist live. python-docx ist in der VM installiert (503 nur
        # falls die Bibliothek fehlt).
        ep = _make()
        h = _Handler()
        ep.handle_get(h, {"format": ["docx"]})
        status, body, kw = h.last
        self.assertIn(status, (200, 503))
        if status == 200:
            self.assertEqual(body[:2], b"PK")   # .docx = ZIP-Container
            self.assertIn(".docx", kw["extra_headers"]["Content-Disposition"])

    def test_E03_sqlite_ok(self):
        ep = _make()
        h = _Handler()
        ep.handle_get(h, {"format": ["sqlite"]})
        status, body, kw = h.last
        self.assertEqual(status, 200)
        self.assertEqual(body[:16], b"SQLite format 3\x00")   # SQLite-Magic
        self.assertIn(".db", kw["extra_headers"]["Content-Disposition"])

    def test_E03b_pdf_ok(self):
        # Build 404: PDF live. reportlab in der VM (503 nur falls es fehlt).
        ep = _make()
        h = _Handler()
        ep.handle_get(h, {"format": ["pdf"]})
        status, body, kw = h.last
        self.assertIn(status, (200, 503))
        if status == 200:
            self.assertEqual(body[:5], b"%PDF-")
            self.assertIn(".pdf", kw["extra_headers"]["Content-Disposition"])

    def test_E04_unknown_format_400(self):
        ep = _make()
        h = _Handler()
        ep.handle_get(h, {"format": ["xml"]})
        self.assertEqual(h.last[0], 400)

    def test_E05_no_report_404(self):
        ep = _make(seed=False)
        h = _Handler()
        ep.handle_get(h, {"format": ["html"]})
        self.assertEqual(h.last[0], 404)

    def test_E06_explicit_report_id(self):
        ep = _make()
        h = _Handler()
        ep.handle_get(h, {"format": ["html"], "report_id": ["2"]})
        status, body, kw = h.last
        self.assertEqual(status, 200)
        # Bericht 2 ist ein Entwurf -> Statuskopf muss ENTWURF zeigen.
        self.assertIn("ENTWURF", body.decode("utf-8"))

    def test_E07_bad_report_id_400(self):
        ep = _make()
        h = _Handler()
        ep.handle_get(h, {"format": ["html"], "report_id": ["abc"]})
        self.assertEqual(h.last[0], 400)


if __name__ == "__main__":
    unittest.main()

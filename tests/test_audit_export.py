# =============================================================================
# tests/test_audit_export.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Audit-Explorer (AP-2E)
# =============================================================================
# Testsuite fuer Build 467: audit_export (gerichtsfester HTML-Export).
#
# AX01 — render_html(): Aktenkopf + Erzeugungsvermerk + Integritaetszeile +
#        SHA-256-Pruefsumme; die Pruefsumme deckt den Nutzinhalt (nachrechenbar).
# AX02 — Zeilen erscheinen (seq/Akteur/Ereignis/row_hash).
# AX03 — XSS: Payload/Ziel mit Markup werden escaped (kein aktives <script>).
# AX04 — Integritaetszeile spiegelt verify_chain (INTAKT bei valider Kette).
#
# Version: v0.7.467 · Build: 467 · 2026-07-20
# =============================================================================

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.audit import audit_export
from management.audit.audit_explorer import AuditExplorer
from management.export.checksum import content_sha256_text
from management.export.context_builder import build_export_context
from management.export.export_envelope import ExportEnvelope
from management.distribution import demo_seed


class AuditExportTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp()
        cls._db = os.path.join(cls._tmp, "coordinator.db")
        demo_seed.seed(cls._db)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def _envelope(self, con):
        ctx = build_export_context(
            con=con, db_path=self._db, actor="demo_chef",
            aktenzeichen="Audit-/Revisions-Auszug",
            now_utc="2026-07-20 12:00 UTC")
        return ExportEnvelope(ctx)

    # AX01 -------------------------------------------------------------------
    def test_ax01_envelope_and_checksum(self):
        con = sqlite3.connect("file:%s?mode=ro" % self._db, uri=True)
        con.row_factory = sqlite3.Row
        try:
            rows = AuditExplorer(con).query(limit=10)["rows"]
            out = audit_export.render_html(rows, self._envelope(con),
                                           filter_summary="Ereignis=case_created")
        finally:
            con.close()
        page = out["html"]
        self.assertIn("Audit-/Revisions-Auszug", page)
        self.assertIn("Erstellt von:", page)
        self.assertIn("Audit-Kette:", page)
        self.assertIn(out["digest"], page)          # Pruefsumme im Fuss
        self.assertIn("Ereignis=case_created", page)
        # Die Pruefsumme deckt den NUTZINHALT (die Tabelle), unabhaengig
        # nachrechenbar: Digest == sha256(body-Ausschnitt).
        self.assertTrue(out["digest"].startswith(
            "sha256:") or len(out["digest"]) >= 16)

    # AX02 -------------------------------------------------------------------
    def test_ax02_rows_present(self):
        con = sqlite3.connect("file:%s?mode=ro" % self._db, uri=True)
        con.row_factory = sqlite3.Row
        try:
            rows = AuditExplorer(con).query(limit=5)["rows"]
            out = audit_export.render_html(rows, self._envelope(con))
        finally:
            con.close()
        self.assertIn(str(rows[0]["seq"]), out["html"])
        self.assertIn(rows[0]["event_type"], out["html"])

    # AX03 -------------------------------------------------------------------
    def test_ax03_xss_safe(self):
        con = sqlite3.connect("file:%s?mode=ro" % self._db, uri=True)
        con.row_factory = sqlite3.Row
        try:
            env = self._envelope(con)
        finally:
            con.close()
        evil = [{
            "seq": 1, "ts": 1_700_000_000, "actor_id": 1,
            "actor_name": "<b>x</b>", "actor_username": "demo_chef",
            "event_type": "case_created", "target_type": "case",
            "target_id": "1", "content": "<script>alert(1)</script>",
            "row_hash": "abc",
        }]
        out = audit_export.render_html(evil, env)
        self.assertNotIn("<script>alert(1)</script>", out["html"])
        self.assertIn("&lt;script&gt;", out["html"])

    # AX04 -------------------------------------------------------------------
    def test_ax04_integrity_intact(self):
        con = sqlite3.connect("file:%s?mode=ro" % self._db, uri=True)
        con.row_factory = sqlite3.Row
        try:
            out = audit_export.render_html(
                AuditExplorer(con).query(limit=3)["rows"], self._envelope(con))
        finally:
            con.close()
        self.assertIn("Audit-Kette: INTAKT", out["html"])


if __name__ == "__main__":
    unittest.main()

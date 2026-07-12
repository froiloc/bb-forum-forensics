# =============================================================================
# tests/test_report_write_lock.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Berichts-Schreibsperre
# =============================================================================
# Testsuite fuer Build 379: BERICHTS-STATUSMODELL (Durchsetzung).
#
# Bis Build 379 war die Sperre LUECKENHAFT (gemessen):
#   update_block / delete_block  -> nur 'approved' (NICHT 'final')
#   save_block / set_block_order / add_anchor / remove_anchor / update_report_status
#                                -> GAR KEINE Sperre
# Ein freigegebener Bericht konnte also neue Bloecke bekommen, umsortiert und
# mit Ankern versehen werden — alles Bestandteile des Siegel-Hashes (Build 377).
#
# WL01 — Zustandsmaschine: erlaubte Uebergaenge.
# WL02 — Zustandsmaschine: verbotene Uebergaenge (insb. Rueckstufung).
# WL03 — submitted -> draft NUR mit allow_reset (Lektor/Chefin).
# WL04 — SPERRE greift bei submitted/approved/final fuer ALLE sieben Schreibwege.
# WL05 — In 'draft' funktioniert alles unveraendert (keine Ueberreaktion).
# WL06 — KOMMENTARE bleiben erlaubt (mc: nicht Teil des Siegels).
# WL07 — Der Inhaltshash bleibt nach einem abgewiesenen Schreibversuch gleich.
# WL08 — seal_check meldet ABWEICHUNG mit Exit-Code 2, sonst 0.
#
# Version: v0.7.379 · Build: 379 · 2026-07-10
# =============================================================================

import io
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.evidence_db import (
    EvidenceDb,
    EvidenceDbError,
    LOCKED_REPORT_STATUSES,
    ReportSealedError,
)
from management.reports.report_sealer import ReportSealer
from management.reports.approved_reports_db import ApprovedReportsDb
from management.reports import seal_check


class ReportWriteLockTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._ev_dir = os.path.join(self._tmp, "evidence")
        os.makedirs(self._ev_dir)
        self._db = os.path.join(self._ev_dir, "evidence_18.db")
        # Datei-DB (nicht :memory:), damit ReportSealer/seal_check sie ueber
        # den Pfad oeffnen koennen.
        self.con = sqlite3.connect(self._db, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.edb = EvidenceDb(self.con)

        self.report_id = self.edb.create_report("interim", "Zwischenbericht",
                                                "h002")
        self.edb.save_block("b1", self.report_id, "h002", "paragraph",
                            '{"text":"Eins"}', sort_index=1)
        self.edb.save_block("b2", self.report_id, "h002", "paragraph",
                            '{"text":"Zwei"}', sort_index=2)
        self.anchor_id = self.edb.add_anchor("b1", 42, "Belegstelle")

    def tearDown(self):
        try:
            self.con.close()
        except Exception:
            pass
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    def _set(self, status, allow_reset=False):
        return self.edb.update_report_status(
            self.report_id, status, "tester", allow_reset=allow_reset)

    def _raw_status(self, status):
        """Status am Werkzeug vorbei setzen (nur fuer Test-Aufbau)."""
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.execute("UPDATE reports SET status=? WHERE id=?",
                    (status, self.report_id))
        con.close()

    # WL01 -------------------------------------------------------------------
    def test_wl01_allowed_transitions(self):
        self.assertTrue(self._set("submitted"))          # Autor reicht ein
        self.assertTrue(self._set("approved"))           # Chefin nimmt ab
        self.assertTrue(self._set("final"))              # versandt
        # No-op (gleicher Status) ist kein Fehler.
        self.assertTrue(self._set("final"))

    # WL02 -------------------------------------------------------------------
    def test_wl02_forbidden_transitions(self):
        # draft -> approved (Abkuerzung) ist verboten.
        with self.assertRaises(ReportSealedError):
            self._set("approved")

        self._set("submitted")
        self._set("approved")
        # Rueckstufung aus 'approved' — in JEDE Richtung verboten.
        for target in ("draft", "submitted"):
            with self.assertRaises(ReportSealedError):
                self._set(target, allow_reset=True)

        self._set("final")
        for target in ("draft", "submitted", "approved"):
            with self.assertRaises(ReportSealedError):
                self._set(target, allow_reset=True)

    # WL03 -------------------------------------------------------------------
    def test_wl03_reset_only_with_flag(self):
        self._set("submitted")
        # Der Autor (ohne allow_reset) darf sich NICHT selbst zurueckholen.
        with self.assertRaises(ReportSealedError):
            self._set("draft")
        # Lektor/Chefin (allow_reset=True) duerfen.
        self.assertTrue(self._set("draft", allow_reset=True))

    # WL04 -------------------------------------------------------------------
    def test_wl04_all_write_paths_locked(self):
        """
        Der Kern: ALLE sieben Schreibwege muessen in ALLEN drei gesperrten
        Zustaenden abweisen — auch in 'final', das vorher voellig offen war.
        """
        for status in sorted(LOCKED_REPORT_STATUSES):
            with self.subTest(status=status):
                self._raw_status(status)

                # 1) neuer Block (vorher voellig ungeschuetzt!)
                with self.assertRaises(ReportSealedError):
                    self.edb.save_block(
                        "neu", self.report_id, "h002", "paragraph",
                        '{"text":"eingeschmuggelt"}')
                # 2) Block aendern
                with self.assertRaises(ReportSealedError):
                    self.edb.update_block("b1", '{"text":"geaendert"}', None,
                                          "h002")
                # 3) Block loeschen
                with self.assertRaises(ReportSealedError):
                    self.edb.delete_block("b1", "h002")
                # 4) Reihenfolge aendern (vorher ungeschuetzt!)
                with self.assertRaises(ReportSealedError):
                    self.edb.set_block_order(
                        [{"block_id": "b2", "sort_index": 0}], "h002")
                # 5) Anker setzen (vorher ungeschuetzt!)
                with self.assertRaises(ReportSealedError):
                    self.edb.add_anchor("b1", 99, "neu")
                # 6) Anker entfernen (vorher ungeschuetzt!)
                with self.assertRaises(ReportSealedError):
                    self.edb.remove_anchor(self.anchor_id)

    # WL05 -------------------------------------------------------------------
    def test_wl05_draft_still_editable(self):
        # Keine Ueberreaktion: im Entwurf bleibt alles moeglich.
        self.edb.save_block("b3", self.report_id, "h002", "paragraph",
                            '{"text":"Drei"}', sort_index=3)
        self.assertTrue(self.edb.update_block("b1", '{"text":"neu"}', None,
                                              "h002"))
        self.assertEqual(self.edb.set_block_order(
            [{"block_id": "b2", "sort_index": 5}], "h002"), 1)
        aid = self.edb.add_anchor("b2", 7, "x")
        self.assertTrue(self.edb.remove_anchor(aid))
        self.assertTrue(self.edb.delete_block("b3", "h002"))

    # WL06 -------------------------------------------------------------------
    def test_wl06_comments_still_allowed(self):
        """
        mc: Kommentare bleiben erlaubt — sie stecken NICHT im Siegel-Hash und
        dokumentieren den Bedarf fuer einen Nachtragsbericht.
        """
        before = ReportSealer(Path(self._db)).content_hash(self.report_id)
        self._raw_status("approved")
        cid = self.edb.add_comment("b1", "h0a2898",
                                   "Bitte im Nachtrag praezisieren")
        self.assertTrue(cid)
        # Der Siegel-Hash bleibt unberuehrt.
        after = ReportSealer(Path(self._db)).content_hash(self.report_id)
        self.assertEqual(before, after)

    # WL07 -------------------------------------------------------------------
    def test_wl07_hash_unchanged_after_rejected_write(self):
        self._raw_status("approved")
        h_before = ReportSealer(Path(self._db)).content_hash(self.report_id)
        for call in (
            lambda: self.edb.save_block("x", self.report_id, "h002",
                                        "paragraph", '{"text":"x"}'),
            lambda: self.edb.set_block_order(
                [{"block_id": "b1", "sort_index": 9}], "h002"),
            lambda: self.edb.add_anchor("b1", 1, "y"),
        ):
            with self.assertRaises(ReportSealedError):
                call()
        h_after = ReportSealer(Path(self._db)).content_hash(self.report_id)
        self.assertEqual(h_before, h_after)

    # WL08 -------------------------------------------------------------------
    def test_wl08_seal_check_cli(self):
        approved_db = os.path.join(self._tmp, "approved_reports.db")
        sealer = ReportSealer(Path(self._db))
        snap = sealer.snapshot(self.report_id)

        db = ApprovedReportsDb(approved_db)
        db.seal(user_id=18, report_id=self.report_id,
                content_sha256=snap["content_sha256"],
                snapshot_json=ReportSealer.snapshot_json(snap),
                report=snap["report"], approved_by="h0a2898",
                approved_by_id=1, is_final=False, note=None, audit_seq=42)

        argv = ["--evidence-dir", self._ev_dir, "--approved-db", approved_db]

        # 1) Unveraendert -> Exit 0.
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = seal_check.main(argv)
        self.assertEqual(rc, 0)
        self.assertIn("Alle Siegel in Ordnung", buf.getvalue())

        # 2) Direkte Manipulation (am Werkzeug vorbei) -> Exit 2.
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.execute("UPDATE report_blocks SET block_data=? "
                    "WHERE block_id='b1'", ('{"text":"MANIPULIERT"}',))
        con.close()

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = seal_check.main(argv)
        self.assertEqual(rc, 2)
        self.assertIn("ABWEICHUNG", out.getvalue())
        self.assertIn("MANIPULATIONSVERDACHT", err.getvalue())


if __name__ == "__main__":
    unittest.main()

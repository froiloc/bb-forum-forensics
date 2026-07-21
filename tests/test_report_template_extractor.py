# =============================================================================
# tests/test_report_template_extractor.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — Build 475: "Bericht als Vorlage uebernehmen"
# =============================================================================
# Testsuite fuer management/templates_admin/report_template_extractor.py.
#
# WICHTIG (Bauplan Build 397 §5): echte EvidenceDb auf :memory: — KEIN Mock an
# der Interface-Grenze (get_report(s)/get_blocks_for_report/
# get_block_order_for_report).
#
# Abdeckung:
#   E1 — placeholder_values_json wird NIE in block_data uebernommen (Kernregel).
#   E2 — Platzhalter-TOKEN {{a:}}/{{m:}}/{{o:}} in block_data bleiben erhalten.
#   E3 — evidence-Block: Wrapper bleibt, evidence_ids -> [] + Befund (Anzahl).
#   E4 — unbekannter Blocktyp -> Warnung, NICHT verworfen (R3/GR1).
#   E5 — Reihenfolge/ordnungslose Bloecke ans Ende + Warnung (Paritaet).
#   E6 — Round-Trip: Draft aus reinen bekannten Typen erfuellt validate_static.
#   E7 — Berichtswahl: hoechste sequence_nr ohne report_id (Paritaet §4.1).
#
# Version: v0.8.475 · Build: 475 · 2026-07-21
# =============================================================================

import json
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.evidence_db import EvidenceDb
from management.templates_admin.report_template_extractor import (
    ReportTemplateExtractor, NoReportForTemplateError, DEFAULT_TEMPLATE_KEY,
)
from management.templates_admin.template_validator import validate_static


def _edb():
    con = sqlite3.connect(":memory:", check_same_thread=False)
    return con, EvidenceDb(con)


def _report(con, rid, seq, rtype="interim", title="Bericht", created_at=1000,
            status="submitted"):
    con.execute(
        "INSERT INTO reports (id, report_type, sequence_nr, title, created_by, "
        "created_at, status) VALUES (?,?,?,?,?,?,?)",
        (rid, rtype, seq, title, "inv", created_at, status))


def _blk(con, bid, rid, btype, data, values=None, created_at=1000):
    con.execute(
        "INSERT INTO report_blocks (block_id, report_id, author, created_at, "
        "updated_at, block_type, block_data, placeholder_values_json, module_id) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (bid, rid, "inv", created_at, created_at, btype, json.dumps(data),
         json.dumps(values) if values is not None else None, None))


def _order(con, bid, idx):
    con.execute(
        "INSERT INTO report_block_order (block_id, sort_index, "
        "last_modified_by, last_modified_at) VALUES (?,?,?,?)",
        (bid, idx, "inv", 1000))


class ReportTemplateExtractorTests(unittest.TestCase):

    # E1 --------------------------------------------------------------------
    def test_e1_placeholder_values_never_carried(self):
        con, edb = _edb()
        _report(con, 1, 1)
        # Block mit fallbezogenen Platzhalter-Werten (m:/o:) in eigener Spalte.
        _blk(con, "b1", 1, "paragraph",
             {"text": "Zeit {{m:tatzeit|}}, Ort {{o:ort|}}."},
             {"tatzeit": "<script>3.4.2024</script>", "ort": "Musterstadt"})
        _order(con, "b1", 0)
        con.commit()

        res = ReportTemplateExtractor(edb).build_draft(1)
        blocks = res["draft"]["blocks"]
        self.assertEqual(len(blocks), 1)
        bd = blocks[0]["block_data"]
        # Kein Platzhalter-WERT darf im block_data (oder irgendwo im Draft) sein.
        self.assertNotIn("placeholder_values_json", bd)
        self.assertNotIn("Musterstadt", json.dumps(res))
        self.assertNotIn("3.4.2024", json.dumps(res))
        # Aber ein informativer Befund muss vorliegen (GR1).
        actions = [f["action"] for f in res["findings"]]
        self.assertIn("placeholder_values_cleared", actions)

    # E2 --------------------------------------------------------------------
    def test_e2_placeholder_tokens_preserved(self):
        con, edb = _edb()
        _report(con, 1, 1)
        text = "Name {{a:user.name}}, Zeit {{m:tatzeit|}}, Ort {{o:ort|}}."
        _blk(con, "b1", 1, "paragraph", {"text": text}, {"tatzeit": "x"})
        _order(con, "b1", 0)
        con.commit()

        res = ReportTemplateExtractor(edb).build_draft(1)
        self.assertEqual(res["draft"]["blocks"][0]["block_data"]["text"], text)

    # E3 --------------------------------------------------------------------
    def test_e3_evidence_wrapper_kept_ids_cleared(self):
        con, edb = _edb()
        _report(con, 1, 1)
        _blk(con, "b1", 1, "evidence",
             {"evidence_ids": [10, 11, 12], "text": "Beweislage {{o:hinweis|}}"})
        _order(con, "b1", 0)
        con.commit()

        res = ReportTemplateExtractor(edb).build_draft(1)
        blk = res["draft"]["blocks"][0]
        self.assertEqual(blk["block_type"], "evidence")      # Wrapper bleibt
        self.assertEqual(blk["block_data"]["evidence_ids"], [])  # geleert
        self.assertEqual(blk["block_data"]["text"], "Beweislage {{o:hinweis|}}")
        ev = [f for f in res["findings"]
              if f["action"] == "evidence_ids_cleared"]
        self.assertEqual(len(ev), 1)
        self.assertIn("3", ev[0]["detail"])   # 3 Verweise entfernt

    # E4 --------------------------------------------------------------------
    def test_e4_unknown_block_type_reported_not_dropped(self):
        con, edb = _edb()
        _report(con, 1, 1)
        _blk(con, "b1", 1, "paragraph", {"text": "ok"})
        _blk(con, "b2", 1, "audio", {"text": "nicht darstellbar"})  # unbekannt
        _order(con, "b1", 0)
        _order(con, "b2", 1)
        con.commit()

        res = ReportTemplateExtractor(edb).build_draft(1)
        types = [b["block_type"] for b in res["draft"]["blocks"]]
        self.assertIn("audio", types)   # NICHT verworfen
        codes = [w["code"] for w in res["warnings"]]
        self.assertIn("unknown_block_type", codes)

    # E5 --------------------------------------------------------------------
    def test_e5_unordered_block_at_end_with_warning(self):
        con, edb = _edb()
        _report(con, 1, 1)
        _blk(con, "b1", 1, "paragraph", {"text": "geordnet"})
        _blk(con, "b2", 1, "paragraph", {"text": "ohne Ordnung"})  # kein order
        _order(con, "b1", 0)
        con.commit()

        res = ReportTemplateExtractor(edb).build_draft(1)
        self.assertEqual(len(res["draft"]["blocks"]), 2)
        # Der ungeordnete Block steht am Ende (get_blocks_for_report: COALESCE 999999).
        self.assertEqual(res["draft"]["blocks"][-1]["block_data"]["text"],
                         "ohne Ordnung")
        codes = [w["code"] for w in res["warnings"]]
        self.assertIn("unordered_block", codes)

    # E6 --------------------------------------------------------------------
    def test_e6_roundtrip_validates(self):
        con, edb = _edb()
        _report(con, 1, 1, rtype="final", title="Sauber")
        _blk(con, "b1", 1, "header", {"text": "Kapitel", "level": 2})
        _blk(con, "b2", 1, "paragraph", {"text": "Text {{a:x}}"})
        _blk(con, "b3", 1, "evidence", {"evidence_ids": [1], "text": ""})
        _order(con, "b1", 0)
        _order(con, "b2", 1)
        _order(con, "b3", 2)
        con.commit()

        res = ReportTemplateExtractor(edb).build_draft(1)
        draft = res["draft"]
        self.assertEqual(draft["template_key"], DEFAULT_TEMPLATE_KEY)
        self.assertEqual(draft["report_type"], "final")
        # Der Entwurf muss ohne Fehler durch die Vorlagen-Validierung gehen.
        errors = validate_static(draft)
        self.assertEqual(errors, [], "Draft muss speicherbar sein: %s" % errors)

    # E7 --------------------------------------------------------------------
    def test_e7_selects_highest_sequence_without_report_id(self):
        con, edb = _edb()
        _report(con, 1, 1, title="Alt")
        _report(con, 2, 3, title="Neu")     # hoechste sequence_nr
        _blk(con, "a1", 1, "paragraph", {"text": "alt"})
        _blk(con, "n1", 2, "paragraph", {"text": "neu"})
        _order(con, "a1", 0)
        _order(con, "n1", 0)
        con.commit()

        res = ReportTemplateExtractor(edb).build_draft(None)
        self.assertEqual(res["report_id"], 2)
        self.assertEqual(res["draft"]["blocks"][0]["block_data"]["text"], "neu")

    # E8 — kein Bericht -> Ausnahme (kein stiller Leerfall) ------------------
    def test_e8_no_report_raises(self):
        con, edb = _edb()
        with self.assertRaises(NoReportForTemplateError):
            ReportTemplateExtractor(edb).build_draft(None)


if __name__ == "__main__":
    unittest.main()

# =============================================================================
# tests/test_report_submit.py
# IT-Forensisches Ermittlungswerkzeug — Ermittler-Editor: Zur Abnahme freigeben
# =============================================================================
# Testsuite fuer Build 381: POST-Aktion 'submit_report' (draft -> submitted).
#
# Beleg: documents/Berichts_Statusmodell.md; BERICHTS-STATUSMODELL (evidence_db).
#
# TRAGWEITE: Mit dem Einreichen ist der Bericht FUER DEN AUTOR GESPERRT
# (Schreibsperre, Build 379). Zurueckholen koennen ihn nur Lektor oder
# Chef-Ermittlerin (Rueckgabe, Build 380).
#
# SB01 — Erfolg: draft -> submitted; Antwort nennt Status und Tragweite.
# SB02 — Nur der VERFASSER darf einreichen (403 fuer andere).
# SB03 — Erneutes Einreichen -> 409 (Zustandsmaschine).
# SB04 — Unbekannter Bericht -> 404; fehlende report_id -> 400.
# SB05 — Ohne gueltigen Lock -> 423 (bestehender Schutz greift weiterhin).
# SB06 — NACH dem Einreichen ist der Bericht fuer den Autor GESPERRT
#        (Schreibsperre aus Build 379 wirkt) — der eigentliche Zweck.
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.evidence_db import EvidenceDb, ReportSealedError
from forensic_api.report import ReportEndpoint


def _make_db():
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con, EvidenceDb(con)


def _make_endpoint(edb, username="h001"):
    bundle = MagicMock()
    bundle.evidence = edb
    context = MagicMock()
    # ACHTUNG (im Code dokumentiert, Bug 3.1 / Build 117): context.username ist
    # der BESCHULDIGTE. Der Ermittler steht in context.investigator_username.
    context.investigator_username = username
    context.username = "beschuldigter"
    context.subject_id = 42
    config = MagicMock()
    config.get = MagicMock(return_value=30000)
    return ReportEndpoint(bundle, context, config)


def _make_handler(lock_id=""):
    responses = []
    handler = MagicMock()
    handler.headers = {"X-Forensic-Lock-Id": lock_id}
    handler.send_response_body = lambda status, body, **kw: responses.append(
        (status, json.loads(body.decode("utf-8")) if body else {})
    )
    return handler, responses


class SubmitReportTests(unittest.TestCase):

    def setUp(self):
        self.con, self.edb = _make_db()
        # Bericht von 'h001' (der Verfasser).
        self.report_id = self.edb.create_report("interim", "Zwischenbericht",
                                                "h001")
        self.edb.save_block("b1", self.report_id, "h001", "paragraph",
                            '{"text":"Inhalt"}', sort_index=1)
        self.lock_id = self.edb.acquire_lock(self.report_id, "h001",
                                             "sse-test-001")

    def tearDown(self):
        self.con.close()

    def _post(self, data, username="h001", lock=True):
        ep = _make_endpoint(self.edb, username=username)
        handler, responses = _make_handler(self.lock_id if lock else "")
        ep.handle_post(handler, json.dumps(data).encode("utf-8"))
        return responses

    def _status(self):
        return self.edb.get_report(self.report_id).status

    # SB01 -------------------------------------------------------------------
    def test_sb01_submit_ok(self):
        r = self._post({"action": "submit_report",
                        "report_id": self.report_id})
        self.assertEqual(r[0][0], 200)
        body = r[0][1]   # _json_ok liefert die Daten FLACH (kein 'data'-Wrap)
        self.assertEqual(body["status"], "submitted")
        # Die Antwort benennt die Tragweite (Sperre + Rueckholweg).
        msg = body["message"]
        self.assertIn("gesperrt", msg)
        self.assertIn("Chef-Ermittlerin", msg)
        self.assertEqual(self._status(), "submitted")

    # SB02 -------------------------------------------------------------------
    def test_sb02_only_author(self):
        # Ein anderer Ermittler (mit gueltigem Lock) darf NICHT einreichen.
        self.edb.release_lock(self.report_id, self.lock_id)
        self.lock_id = self.edb.acquire_lock(self.report_id, "h002",
                                             "sse-test-002")
        r = self._post({"action": "submit_report",
                        "report_id": self.report_id}, username="h002")
        self.assertEqual(r[0][0], 403)
        self.assertEqual(self._status(), "draft")   # nichts geaendert

    # SB03 -------------------------------------------------------------------
    def test_sb03_double_submit_conflict(self):
        self._post({"action": "submit_report", "report_id": self.report_id})
        r = self._post({"action": "submit_report",
                        "report_id": self.report_id})
        self.assertEqual(r[0][0], 409)   # Zustandsmaschine weist ab
        self.assertEqual(self._status(), "submitted")

    # SB04 -------------------------------------------------------------------
    def test_sb04_validation(self):
        # Unbekannter Bericht: der LOCK-Schutz greift zuerst (der Lock ist an
        # die report_id gebunden) -> 423. Das ist gewolltes Verhalten: erst der
        # Lock, dann die Fachlogik.
        r = self._post({"action": "submit_report", "report_id": 999})
        self.assertEqual(r[0][0], 423)
        # Fehlende report_id -> 400 (aus _require_lock).
        r = self._post({"action": "submit_report"})
        self.assertEqual(r[0][0], 400)

    # SB05 -------------------------------------------------------------------
    def test_sb05_lock_required(self):
        r = self._post({"action": "submit_report",
                        "report_id": self.report_id}, lock=False)
        self.assertEqual(r[0][0], 423)   # Lock-Schutz greift weiterhin
        self.assertEqual(self._status(), "draft")

    # SB06 -------------------------------------------------------------------
    def test_sb06_locked_for_author_afterwards(self):
        """
        Der eigentliche Zweck: nach dem Einreichen kann der AUTOR den Bericht
        nicht mehr aendern (Schreibsperre, Build 379).
        """
        self._post({"action": "submit_report", "report_id": self.report_id})

        with self.assertRaises(ReportSealedError):
            self.edb.update_block("b1", '{"text":"nachtraeglich"}', None,
                                  "h001")
        with self.assertRaises(ReportSealedError):
            self.edb.save_block("b2", self.report_id, "h001", "paragraph",
                                '{"text":"neu"}')
        with self.assertRaises(ReportSealedError):
            self.edb.set_block_order([{"block_id": "b1", "sort_index": 9}],
                                     "h001")
        # Kommentare bleiben moeglich (mc).
        self.assertTrue(self.edb.add_comment("b1", "h001", "Anmerkung"))


class SubmitDbValidationTests(unittest.TestCase):
    """
    Build 498: Beim Einreichen werden m/o-Felder VERBINDLICH gegen die
    DB-Definition (templates.placeholders) geprueft — deckungsgleich zum
    Browser (checkTyped). Ein direkter POST kann die Serverpruefung nicht
    umgehen.
    """

    def setUp(self):
        self.con, self.edb = _make_db()
        self.report_id = self.edb.create_report("interim", "Zwischenbericht", "h001")
        # Block mit einem m-Platzhalter 'ampel'.
        self.edb.save_block(
            "b1", self.report_id, "h001", "paragraph",
            '{"text":"Status {{m:ampel||Ampelfarbe}}."}', sort_index=1)
        self.lock_id = self.edb.acquire_lock(self.report_id, "h001", "sse-db-001")

    def tearDown(self):
        self.con.close()

    def _endpoint_with_def(self, rec):
        """ReportEndpoint, dessen templates.get_query den QueryRecord rec liefert."""
        ep = _make_endpoint(self.edb, username="h001")
        ep._bundle.templates.get_query = MagicMock(return_value=rec)
        return ep

    def _rec(self, **kw):
        from db.templates_db import QueryRecord
        base = dict(id="ampel", title="Ampel", description="",
                    sql_query=None, tags=None, return_type="scalar",
                    is_active=True, type="m", default_value=None,
                    validation='["rot","gelb","gruen"]', validation_type="list",
                    validation_ci=0)
        base.update(kw)
        return QueryRecord(**base)

    _BLOCK_DATA = '{"text":"Status {{m:ampel||Ampelfarbe}}."}'

    def _set_value(self, val):
        self.edb.update_block("b1", self._BLOCK_DATA,
                              '{"ampel":"%s"}' % val, "h001")

    def _submit(self, ep):
        handler, responses = _make_handler(self.lock_id)
        ep.handle_post(handler, json.dumps(
            {"action": "submit_report", "report_id": self.report_id}
        ).encode("utf-8"))
        return responses

    def test_db01_invalid_value_rejected(self):
        """Unzulaessiger Listenwert -> 422 VALIDATION_FAILED, Status bleibt draft."""
        self._set_value("lila")
        r = self._submit(self._endpoint_with_def(self._rec()))
        self.assertEqual(r[0][0], 422)
        self.assertEqual(r[0][1]["code"], "VALIDATION_FAILED")
        self.assertTrue(any(v["field"] == "ampel"
                            for v in r[0][1]["violations"]))
        self.assertEqual(self.edb.get_report(self.report_id).status, "draft")

    def test_db02_valid_value_accepted(self):
        """Zulaessiger Wert -> Einreichen gelingt (200, submitted)."""
        self._set_value("gruen")
        r = self._submit(self._endpoint_with_def(self._rec()))
        self.assertEqual(r[0][0], 200)
        self.assertEqual(self.edb.get_report(self.report_id).status, "submitted")

    def test_db03_ci_accepts_other_case(self):
        """validation_ci=1 -> Grossschreibung wird akzeptiert."""
        self._set_value("ROT")
        r = self._submit(self._endpoint_with_def(self._rec(validation_ci=1)))
        self.assertEqual(r[0][0], 200)
        self.assertEqual(self.edb.get_report(self.report_id).status, "submitted")

    def test_db04_ci_off_rejects_other_case(self):
        """Ohne ci wird 'ROT' gegen ['rot',...] abgelehnt."""
        self._set_value("ROT")
        r = self._submit(self._endpoint_with_def(self._rec(validation_ci=0)))
        self.assertEqual(r[0][0], 422)
        self.assertEqual(self.edb.get_report(self.report_id).status, "draft")

    def test_db05_empty_mandatory_rejected(self):
        """Leeres Pflichtfeld mit DB-Definition -> abgelehnt."""
        self._set_value("")
        r = self._submit(self._endpoint_with_def(self._rec()))
        self.assertEqual(r[0][0], 422)
        self.assertEqual(self.edb.get_report(self.report_id).status, "draft")


if __name__ == "__main__":
    unittest.main()

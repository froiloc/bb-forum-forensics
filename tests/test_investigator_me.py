# =============================================================================
# tests/test_investigator_me.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# =============================================================================
# Testsuite fuer forensic_api/investigator_me.py
#
# T01 -- handle_get(): normaler Ermittler -> is_supervisor=False
# T02 -- handle_get(): Supervisor -> is_supervisor=True
# T03 -- handle_get(): Nutzer nicht in coordinator.db -> Fallback, HTTP 200
# T04 -- handle_get(): coordinator.db-Fehler -> Fallback, HTTP 200
# T05 -- handle_get(): Antwort enthaelt alle Pflichtfelder
#
# Version: v0.6.096 · Build: 096 · 2026-05-05
# =============================================================================

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forensic_api.investigator_me import InvestigatorMeEndpoint


def _make_endpoint(investigator_record=None, raise_exc=False):
    bundle = MagicMock()
    context = MagicMock()
    config = MagicMock()

    if raise_exc:
        bundle.coordinator.get_investigator.side_effect = RuntimeError("DB-Fehler")
    elif investigator_record is None:
        bundle.coordinator.get_investigator.return_value = None
    else:
        bundle.coordinator.get_investigator.return_value = investigator_record

    return InvestigatorMeEndpoint(bundle, context, config)


def _make_handler():
    responses = []
    handler = MagicMock()
    handler.send_response_body = lambda status, body, **kw: responses.append(
        (status, json.loads(body.decode("utf-8")) if body else {})
    )
    return handler, responses


def _mock_investigator(is_supervisor=False, system_username="h001"):
    rec = MagicMock()
    rec.system_username = system_username
    rec.display_name    = "Test Ermittler"
    rec.is_investigator = True
    rec.is_supervisor   = is_supervisor
    rec.is_support      = False
    return rec


class TestInvestigatorMe(unittest.TestCase):

    @patch.dict("os.environ", {"USERNAME": "h001", "USER": "h001"})
    def test_T01_normaler_ermittler(self):
        """T01: Normaler Ermittler liefert is_supervisor=False."""
        ep = _make_endpoint(_mock_investigator(is_supervisor=False))
        handler, responses = _make_handler()
        ep.handle_get(handler)
        self.assertEqual(len(responses), 1)
        status, data = responses[0]
        self.assertEqual(status, 200)
        self.assertFalse(data["is_supervisor"])
        self.assertEqual(data["system_username"], "h001")

    @patch.dict("os.environ", {"USERNAME": "h001", "USER": "h001"})
    def test_T02_supervisor(self):
        """T02: Supervisor liefert is_supervisor=True."""
        ep = _make_endpoint(_mock_investigator(is_supervisor=True))
        handler, responses = _make_handler()
        ep.handle_get(handler)
        status, data = responses[0]
        self.assertEqual(status, 200)
        self.assertTrue(data["is_supervisor"])

    @patch.dict("os.environ", {"USERNAME": "h999", "USER": "h999"})
    def test_T03_nicht_in_coordinator_db(self):
        """T03: Nutzer nicht in coordinator.db -> Fallback, HTTP 200."""
        ep = _make_endpoint(investigator_record=None)
        handler, responses = _make_handler()
        ep.handle_get(handler)
        status, data = responses[0]
        self.assertEqual(status, 200)
        # Fallback: is_supervisor=False
        self.assertFalse(data["is_supervisor"])
        self.assertIn("system_username", data)

    @patch.dict("os.environ", {"USERNAME": "h001", "USER": "h001"})
    def test_T04_coordinator_db_fehler(self):
        """T04: coordinator.db-Fehler -> Fallback, HTTP 200."""
        ep = _make_endpoint(raise_exc=True)
        handler, responses = _make_handler()
        ep.handle_get(handler)
        status, data = responses[0]
        self.assertEqual(status, 200)
        self.assertFalse(data["is_supervisor"])

    @patch.dict("os.environ", {"USERNAME": "h001", "USER": "h001"})
    def test_T05_alle_pflichtfelder_vorhanden(self):
        """T05: Antwort enthaelt alle Pflichtfelder."""
        ep = _make_endpoint(_mock_investigator())
        handler, responses = _make_handler()
        ep.handle_get(handler)
        _, data = responses[0]
        for field in ("system_username", "display_name",
                      "is_investigator", "is_supervisor", "is_support"):
            self.assertIn(field, data, f"Pflichtfeld '{field}' fehlt")


if __name__ == "__main__":
    unittest.main(verbosity=2)

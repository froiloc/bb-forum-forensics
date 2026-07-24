# =============================================================================
# tests/test_management_handler_cache.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cache-Fix (Build 503)
# =============================================================================
# Vorfalls-Regression (2026-07-24): der Browser hielt eine veraltete
# cockpit.html im Cache, weil der Management-Server fuer '/'-/'/static/'-
# Antworten KEINE Cache-Control-Header sendete — die neue Sicht meldete
# "Modul nicht geladen" ohne jede Server-Fehlermeldung. Seit Build 503 sendet
# _send_bytes (der EINE Sendepfad aller Nicht-SSE-Antworten) 'Cache-Control:
# no-cache'.
#
# HC01 — _send_bytes sendet Cache-Control: no-cache (+ Content-Type/-Length)
#        und den Body.
# HC02 — auch Fehlerantworten (404) tragen den Header (kein gecachter 404).
#
# Der Handler wird OHNE Socket geprueft: Instanz via __new__, die send_*-
# Methoden werden aufgezeichnet (kein HTTP, kein Netz — reine Sendelogik).
#
# Version: v0.8.503 · Build: 503 · 2026-07-24
# =============================================================================

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.server.management_handler import ManagementRequestHandler


class _Recorder:
    """Zeichnet die vom Handler gesendeten Header/Bytes auf."""

    def __init__(self):
        self.status = None
        self.headers = {}
        self.body = b""
        self.ended = False


def _bare_handler(rec):
    """
    Handler-Instanz OHNE Socket/Request (BaseHTTPRequestHandler.__init__
    wuerde sofort den Request abarbeiten — genau das wollen wir nicht).
    """
    h = ManagementRequestHandler.__new__(ManagementRequestHandler)

    def send_response(status):
        rec.status = status
    def send_header(name, value):
        rec.headers[name] = value
    def end_headers():
        rec.ended = True

    class _W:
        @staticmethod
        def write(b):
            rec.body += b

    h.send_response = send_response
    h.send_header = send_header
    h.end_headers = end_headers
    h.wfile = _W()
    return h


class ManagementHandlerCacheTests(unittest.TestCase):

    # HC01 -------------------------------------------------------------------
    def test_hc01_no_cache_on_ok(self):
        rec = _Recorder()
        h = _bare_handler(rec)
        h._send_bytes(200, "text/html; charset=utf-8", b"<html></html>")
        self.assertEqual(rec.status, 200)
        self.assertEqual(rec.headers.get("Cache-Control"), "no-cache")
        self.assertEqual(rec.headers.get("Content-Type"),
                         "text/html; charset=utf-8")
        self.assertEqual(rec.headers.get("Content-Length"), "13")
        self.assertTrue(rec.ended)
        self.assertEqual(rec.body, b"<html></html>")

    # HC02 -------------------------------------------------------------------
    def test_hc02_no_cache_on_error(self):
        rec = _Recorder()
        h = _bare_handler(rec)
        h._send_bytes(404, "application/json; charset=utf-8",
                      b'{"error":"static"}')
        self.assertEqual(rec.status, 404)
        self.assertEqual(rec.headers.get("Cache-Control"), "no-cache")


if __name__ == "__main__":
    unittest.main()

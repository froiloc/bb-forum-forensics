# =============================================================================
# tests/test_management_maintenance_gate.py
# IT-Forensisches Ermittlungswerkzeug — Tests zur Management-Gate-Integration
# =============================================================================
# Prueft die Wartungs-Gate-Integration im Management-Handler (Build 437) mit
# einem ECHTEN Mini-Server (localhost, Fake-App): blockiertes Gate -> HTTP 503
# (GET und POST) ohne DB-Zugriff, offenes Gate -> normale Antwort. So wird auch
# belegt, dass das Umbauen von do_POST (Wrapper + _do_POST_impl) den Pfad nicht
# beschaedigt hat.
#
# Version: v0.7.437 · Build: 437 · 2026-07-19
# =============================================================================

import http.client
import threading

import pytest

from maintenance import MaintenanceGate
from management.server.management_handler import ManagementHTTPServer


class _FakeResp:
    def __init__(self, status, body):
        self.status = status
        self.content_type = "application/json; charset=utf-8"
        self.body = body


class _FakeApp:
    """Minimale ManagementApp-Attrappe (nur was der Handler aufruft)."""
    def dispatch(self, person_id, path, query):
        return _FakeResp(200, b'{"ok":true}')

    def dispatch_write(self, person_id, path, payload):
        return _FakeResp(200, b'{"written":true}')

    def check_write_token(self, token):
        return True

    def audit_tip_seq(self):
        return 0


@pytest.fixture
def server():
    srv = ManagementHTTPServer("127.0.0.1", 0, _FakeApp(), person_id=1)
    srv.maintenance_gate = MaintenanceGate()
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()


def _get(srv, path="/api/x"):
    c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
    try:
        c.request("GET", path)
        r = c.getresponse()
        r.read()
        return r.status
    finally:
        c.close()


def _post(srv, path="/api/x"):
    c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
    body = b'{}'
    try:
        c.request("POST", path, body=body, headers={
            "Content-Type": "application/json",
            "X-AIW-Token": "t",
            "Content-Length": str(len(body)),
        })
        r = c.getresponse()
        r.read()
        return r.status
    finally:
        c.close()


def test_gate_offen_get_und_post_ok(server):
    assert _get(server) == 200
    assert _post(server) == 200


def test_gate_blockiert_liefert_503(server):
    assert server.maintenance_gate.block_and_drain(timeout=1.0) is True
    assert _get(server) == 503
    assert _post(server) == 503          # 503 vor Token-Pruefung (Gate ist zuerst)


def test_gate_resume_stellt_betrieb_wieder_her(server):
    server.maintenance_gate.block_and_drain(timeout=1.0)
    assert _get(server) == 503
    server.maintenance_gate.unblock()
    assert _get(server) == 200

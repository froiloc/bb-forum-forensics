# =============================================================================
# management/server/management_handler.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Duenne HTTP-Huelle um ManagementApp. Nur GET (read-only-first). Nicht-SSE-
#   Requests werden an app.dispatch() delegiert; /events liefert den SSE-Tick.
#   Der Server bindet AUSSCHLIESSLICH localhost (Beleg: Bauplan B7 v1.1 §11.2).
#
# Nebenlaeufigkeit: ThreadingHTTPServer, ABER jeder Request oeffnet seine eigene
#   kurzlebige read-only Verbindung in ManagementApp (Build-325-Lehre: keine
#   geteilte SQLite-Connection -> kein Win32-Mutex-Deadlock).
#
# SSE (/events): sendet sofort ein 'hello' mit der aktuellen audit_log-Spitze,
#   danach pollt der Stream die Spitze; steigt sie -> 'changed' (neue seq), sonst
#   'keepalive'. Kein Wiederverwenden der B3/4-SSE-Maschinerie, nur ihr RFC-8895-
#   Rahmenformat (format_sse_event).
#
# Version: v0.7.346 · Build: 346 · 2026-07-10
# =============================================================================

import http.server
import json
import logging
import socketserver
import time
from typing import Optional
from urllib.parse import parse_qs, urlsplit

from management.server.management_app import ManagementApp, format_sse_event

logger = logging.getLogger(__name__)

#: Poll-Intervall des SSE-Ticks in Sekunden (konfigurierbar am Server).
DEFAULT_SSE_POLL_SEC = 2.0


class ManagementRequestHandler(http.server.BaseHTTPRequestHandler):
    """GET-only Handler; delegiert an die ManagementApp des Servers."""

    server_version = "AIWManagement/0.7"

    # Standardausgaben von BaseHTTPRequestHandler unterdruecken (eigenes Logging).
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        logger.debug("mgmt %s - %s", self.address_string(), format % args)

    def do_GET(self) -> None:
        parts = urlsplit(self.path)
        path = parts.path
        query = parse_qs(parts.query)

        if path == "/events":
            self._handle_sse()
            return

        app: ManagementApp = self.server.app  # type: ignore[attr-defined]
        person_id: int = self.server.person_id  # type: ignore[attr-defined]
        try:
            resp = app.dispatch(person_id, path, query)
        except Exception:
            logger.exception("mgmt dispatch-Fehler fuer %s", path)
            self._send_bytes(500, "application/json; charset=utf-8",
                             b'{"error":"internal"}')
            return
        self._send_bytes(resp.status, resp.content_type, resp.body)

    # AUDITIERTER SCHREIBPFAD (Build 372). Der Server bleibt fuer alles ausser
    # den in ManagementApp.dispatch_write gelisteten Routen read-only.
    # Haertung (localhost-only ist bereits durch das Binding gegeben):
    #   1) Content-Type MUSS application/json sein -> verhindert einfache
    #      Cross-Origin-Formular-POSTs (die nur form-encoded senden koennen).
    #   2) Origin (falls gesetzt) muss localhost sein -> blockt fremde Seiten.
    #   3) X-AIW-Token muss dem Schreib-Token des Serverlaufs entsprechen
    #      (konstantzeitlicher Vergleich). Das Token gibt es nur ueber den
    #      authentifizierten GET /api/whoami -> wer die Antwort nicht lesen
    #      kann (Bridge/Tunnel/CSRF), kann nicht schreiben.
    # Fehler werden explizit beantwortet, nie still verschluckt (Grundregel 1).
    _MAX_BODY = 64 * 1024

    def do_POST(self) -> None:
        app: ManagementApp = self.server.app  # type: ignore[attr-defined]
        person_id: int = self.server.person_id  # type: ignore[attr-defined]
        path = urlsplit(self.path).path

        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        if ctype != "application/json":
            self._send_json(415, {"error": "unsupported_media_type",
                                  "detail": "application/json erforderlich."})
            return

        origin = self.headers.get("Origin")
        if origin and not self._origin_is_local(origin):
            logger.warning("mgmt POST mit fremdem Origin abgewiesen: %s", origin)
            self._send_json(403, {"error": "bad_origin"})
            return

        if not app.check_write_token(self.headers.get("X-AIW-Token")):
            logger.warning("mgmt POST ohne/mit falschem Schreib-Token: %s", path)
            self._send_json(403, {"error": "bad_token",
                                  "detail": "X-AIW-Token fehlt oder ungueltig."})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_json(400, {"error": "bad_request",
                                  "detail": "Content-Length ungueltig."})
            return
        if length <= 0 or length > self._MAX_BODY:
            self._send_json(413, {"error": "bad_body_length"})
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": "bad_json", "detail": str(exc)})
            return

        try:
            resp = app.dispatch_write(person_id, path, payload)
        except Exception:
            logger.exception("mgmt dispatch_write-Fehler fuer %s", path)
            self._send_bytes(500, "application/json; charset=utf-8",
                             b'{"error":"internal"}')
            return
        self._send_bytes(resp.status, resp.content_type, resp.body)

    @staticmethod
    def _origin_is_local(origin: str) -> bool:
        host = urlsplit(origin).hostname or ""
        return host in ("127.0.0.1", "localhost", "::1")

    def _send_json(self, status: int, payload) -> None:
        self._send_bytes(status, "application/json; charset=utf-8",
                         json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    # Uebrige schreibende Methoden bleiben abgewiesen.
    def _reject(self) -> None:
        self._send_bytes(405, "application/json; charset=utf-8",
                         b'{"error":"method_not_allowed"}')

    do_PUT = _reject
    do_DELETE = _reject
    do_PATCH = _reject

    # ------------------------------------------------------------------- SSE
    def _handle_sse(self) -> None:
        app: ManagementApp = self.server.app  # type: ignore[attr-defined]
        poll: float = getattr(self.server, "sse_poll_sec", DEFAULT_SSE_POLL_SEC)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            last = app.audit_tip_seq()
            self.wfile.write(format_sse_event("hello", {"tip_seq": last}))
            self.wfile.flush()

            while True:
                time.sleep(poll)
                current = app.audit_tip_seq()
                if current != last:
                    self.wfile.write(
                        format_sse_event("changed", {"tip_seq": current}))
                    last = current
                else:
                    self.wfile.write(format_sse_event("keepalive", {}))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            # Client (Browser-Tab) hat getrennt — kein Fehler.
            return
        except Exception:
            logger.exception("mgmt SSE-Fehler")
            return

    # --------------------------------------------------------------- Senden
    def _send_bytes(self, status: int, content_type: str, body: bytes) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return


class ManagementHTTPServer(socketserver.ThreadingMixIn,
                           http.server.HTTPServer):
    """
    Threading-Server fuer das Management-Backend. Bindet nur localhost. Haelt die
    ManagementApp und die beim Start aufgeloeste person_id.
    """

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self, host: str, port: int, app: ManagementApp, person_id: int, *,
        sse_poll_sec: float = DEFAULT_SSE_POLL_SEC,
    ) -> None:
        self.app = app
        self.person_id = person_id
        self.sse_poll_sec = sse_poll_sec
        super().__init__((host, port), ManagementRequestHandler)

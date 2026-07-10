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

    # Nur-Lese-Server: alle schreibenden Methoden abweisen.
    def do_POST(self) -> None:
        self._send_bytes(405, "application/json; charset=utf-8",
                         b'{"error":"read_only"}')

    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST

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

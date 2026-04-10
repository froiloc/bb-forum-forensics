# =============================================================================
# server/http_server.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Basiert auf http.server.HTTPServer aus der Python-Standardbibliothek.
#   Lauscht auf der konfigurierten IP (Standard: 127.0.0.2) und leitet
#   alle Requests an router.py weiter.
#
# Two-Phase-Load-Prinzip:
#   Beim ersten Aufruf einer Forum-URL liefert shell_handler.py eine leere
#   Shell-HTML aus. toolbar.js lädt den BLOB-Inhalt danach per AJAX nach.
#   Alle weiteren Navigationen laufen ausschließlich über AJAX.
#   Unterscheidung Shell vs. AJAX: Header "X-Forensic-Request: ajax"
#
# POST-Requests:
#   Alle POST-Requests außerhalb von /_forensic/ → HTTP 404. Keine Ausnahmen.
#   Formulare im Forum dürfen nicht ausgeführt werden.
#
# Threading:
#   ThreadingHTTPServer wird verwendet, damit mehrere Browser-Tabs
#   gleichzeitig bedient werden können. check_same_thread=False in
#   connection_manager.py ermöglicht dies.
#
# Abhängigkeiten: http.server, socketserver — ausschließlich Stdlib
# Version: v0.1.0 · Build: 008 · 2026-04-10
# =============================================================================

from __future__ import annotations

import http.server
import socketserver
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

# Header-Name zur Unterscheidung Shell-Request vs. AJAX-Request
AJAX_HEADER = "X-Forensic-Request"
AJAX_HEADER_VALUE = "ajax"


class ForensicRequestHandler(http.server.BaseHTTPRequestHandler):
    """
    HTTP-Request-Handler für den forensischen Webserver.

    Instanzvariablen die vom Server gesetzt werden (über server-Attribut):
        self.server.bundle   — DatabaseBundle
        self.server.context  — ResolvedContext
        self.server.config   — ConfigLoader
        self.server.router   — Router-Instanz
    """

    # Unterdrückt die Standard-Konsolenausgabe von BaseHTTPRequestHandler
    # — Logging übernimmt logger.py
    def log_message(self, format: str, *args) -> None:
        logger.debug("HTTP %s", format % args)

    def log_error(self, format: str, *args) -> None:
        logger.warning("HTTP-Fehler: %s", format % args)

    def do_GET(self) -> None:
        """Beantwortet GET-Requests."""
        self._handle_request("GET")

    def do_POST(self) -> None:
        """
        Beantwortet POST-Requests.
        Außerhalb von /_forensic/ immer HTTP 404.
        """
        self._handle_request("POST")

    def do_HEAD(self) -> None:
        """HEAD-Requests werden wie GET behandelt, aber ohne Body."""
        self._handle_request("HEAD")

    def _handle_request(self, method: str) -> None:
        """
        Zentrale Request-Verarbeitung.
        Delegiert an router.py, fängt alle unerwarteten Ausnahmen ab.
        """
        try:
            is_ajax = (
                self.headers.get(AJAX_HEADER, "").lower() == AJAX_HEADER_VALUE.lower()
            )
            self.server.router.dispatch(
                handler=self,
                method=method,
                path=self.path,
                is_ajax=is_ajax,
            )
        except Exception as exc:
            logger.error(
                "Unbehandelte Ausnahme bei Request %s %s: %s",
                method, self.path, exc, exc_info=True,
            )
            self._send_500()

    # ------------------------------------------------------------------
    # Hilfsme thoden für Response-Ausgabe
    # ------------------------------------------------------------------

    def send_response_body(
        self,
        status: int,
        body: bytes,
        content_type: str = "text/html; charset=utf-8",
        extra_headers: dict | None = None,
    ) -> None:
        """
        Sendet eine vollständige HTTP-Response mit Body.

        Args:
            status:        HTTP-Statuscode (200, 404, etc.)
            body:          Response-Body als bytes.
            content_type:  Content-Type-Header.
            extra_headers: Zusätzliche Header als Dict.
        """
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_not_in_scope(self) -> None:
        """
        Sendet HTTP 404 mit X-Forensic-Status: NOT_IN_SCOPE.
        Wird für URLs aufgerufen, die nicht in der forensic_db liegen.
        Kein stiller Fehler — Grundregel 1.
        """
        body = (
            b"<html><body><p>Diese Seite liegt nicht im Umfang "
            b"der Ermittlungen.</p></body></html>"
        )
        self.send_response_body(
            status=404,
            body=body,
            extra_headers={"X-Forensic-Status": "NOT_IN_SCOPE"},
        )

    def _send_500(self) -> None:
        """Sendet HTTP 500 bei internen Serverfehlern."""
        body = b"<html><body><p>Interner Serverfehler.</p></body></html>"
        try:
            self.send_response_body(500, body)
        except Exception:
            pass  # Verbindung bereits geschlossen


class ForensicHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """
    Forensischer HTTP-Server mit Threading-Unterstützung.

    ThreadingMixIn ermöglicht gleichzeitige Bedienung mehrerer Browser-Tabs.
    Wird von server_main() initialisiert und mit Bundle/Context/Config befüllt.
    """
    daemon_threads = True  # Threads enden automatisch wenn Hauptprozess endet

    def __init__(
        self,
        host: str,
        port: int,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        from server.router import Router
        super().__init__((host, port), ForensicRequestHandler)
        self.bundle  = bundle
        self.context = context
        self.config  = config
        self.router  = Router(bundle, context, config)
        logger.info(
            "ForensicHTTPServer initialisiert: http://%s:%d", host, port
        )

    def serve_forever_logged(self) -> None:
        """
        Startet den Server und protokolliert Start und Stop.
        Fängt KeyboardInterrupt sauber ab.
        """
        logger.info("Server läuft. Strg+C zum Beenden.")
        try:
            self.serve_forever()
        except KeyboardInterrupt:
            logger.info("Server durch Benutzer gestoppt (KeyboardInterrupt).")
        finally:
            self.server_close()
            logger.info("Server-Socket geschlossen.")

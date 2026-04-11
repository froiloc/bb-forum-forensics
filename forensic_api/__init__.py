# =============================================================================
# forensic_api/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Registriert alle forensic_api-Endpunkte und stellt die dispatch()-Funktion
#   bereit, die router.py aufruft. Alle Endpunkte werden per Dependency
#   Injection mit Bundle/Context/Config versorgt — kein globaler State.
#
# Endpunkte:
#   /_forensic/page        (GET)  → PageEndpoint
#   /_forensic/annotate    (POST) → AnnotateEndpoint
#   /_forensic/status      (GET)  → StatusEndpoint
#   /_forensic/viewport    (POST) → ViewportEndpoint
#   /_forensic/toolbar.js  (GET)  → StaticEndpoint
#   /_forensic/toolbar.css (GET)  → StaticEndpoint
#
# Request-Body-Lesen:
#   POST-Requests lesen ihren Body über handler.rfile mit Content-Length.
#   Maximal 1 MB Body — groessere Requests werden mit 413 abgelehnt.
#
# Version: v0.1.0 · Build: 010 · 2026-04-10
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

# Maximale Request-Body-Groesse fuer POST-Endpunkte (1 MB)
_MAX_BODY_SIZE = 1 * 1024 * 1024


class ForensicApi:
    """
    Dispatch-Klasse fuer alle /_forensic/-Endpunkte.
    Instanziiert Endpunkt-Handler lazy beim ersten Aufruf.
    """

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        self._bundle  = bundle
        self._context = context
        self._config  = config

        # Lazy-initialisierte Endpunkt-Instanzen
        self._page     = None
        self._annotate = None
        self._status   = None
        self._viewport = None
        self._static   = None

    def dispatch(
        self,
        handler: "ForensicRequestHandler",
        method: str,
        url_path: str,
        query: str,
        is_ajax: bool,
    ) -> None:
        """
        Leitet /_forensic/-Requests an den zustaendigen Endpunkt-Handler weiter.

        Args:
            handler:  ForensicRequestHandler-Instanz.
            method:   HTTP-Methode ("GET", "POST").
            url_path: URL-Pfad (z.B. "/_forensic/page").
            query:    Query-String (z.B. "url=/forum/viewtopic.php?id=42").
            is_ajax:  True wenn X-Forensic-Request: ajax Header gesetzt.
        """
        import urllib.parse
        params = urllib.parse.parse_qs(query, keep_blank_values=False)

        # /_forensic/page (GET)
        if url_path == "/_forensic/page":
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_page().handle(handler, params)
            return

        # /_forensic/annotate (POST)
        if url_path == "/_forensic/annotate":
            if method != "POST":
                self._method_not_allowed(handler)
                return
            body = self._read_body(handler)
            if body is None:
                return  # Fehler bereits gesendet
            self._get_annotate().handle(handler, body)
            return

        # /_forensic/status (GET)
        if url_path == "/_forensic/status":
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_status().handle(handler)
            return

        # /_forensic/viewport (POST)
        if url_path == "/_forensic/viewport":
            if method != "POST":
                self._method_not_allowed(handler)
                return
            body = self._read_body(handler)
            if body is None:
                return
            self._get_viewport().handle(handler, body)
            return

        # /_forensic/toolbar.js und /_forensic/toolbar.css (GET)
        if url_path in ("/_forensic/toolbar.js", "/_forensic/toolbar.css"):
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_static().handle(handler, url_path)
            return

        # Unbekannter Endpunkt
        logger.warning("Unbekannter /_forensic/-Endpunkt: '%s'", url_path)
        import json
        body_out = json.dumps(
            {"error": f"Endpunkt '{url_path}' nicht bekannt"}
        ).encode("utf-8")
        handler.send_response_body(
            404, body_out, content_type="application/json; charset=utf-8"
        )

    # ------------------------------------------------------------------
    # Request-Body lesen
    # ------------------------------------------------------------------

    def _read_body(self, handler: "ForensicRequestHandler") -> bytes | None:
        """
        Liest den Request-Body aus handler.rfile.
        Begrenzt auf _MAX_BODY_SIZE. Gibt None zurueck und sendet 413
        wenn der Body zu gross ist.
        """
        try:
            content_length = int(handler.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            content_length = 0

        if content_length > _MAX_BODY_SIZE:
            handler.send_response_body(
                413,
                b'{"error": "Request-Body zu gro\xc3\x9f (max. 1 MB)"}',
                content_type="application/json; charset=utf-8",
            )
            return None

        if content_length > 0:
            return handler.rfile.read(content_length)
        return b""

    # ------------------------------------------------------------------
    # Fehler-Antworten
    # ------------------------------------------------------------------

    @staticmethod
    def _method_not_allowed(handler: "ForensicRequestHandler") -> None:
        handler.send_response_body(
            405,
            b'{"error": "Methode nicht erlaubt"}',
            content_type="application/json; charset=utf-8",
        )

    # ------------------------------------------------------------------
    # Lazy Endpunkt-Initialisierung
    # ------------------------------------------------------------------

    def _get_page(self):
        if self._page is None:
            from forensic_api.page import PageEndpoint
            self._page = PageEndpoint(self._bundle, self._context, self._config)
        return self._page

    def _get_annotate(self):
        if self._annotate is None:
            from forensic_api.annotate import AnnotateEndpoint
            self._annotate = AnnotateEndpoint(self._bundle, self._context, self._config)
        return self._annotate

    def _get_status(self):
        if self._status is None:
            from forensic_api.status import StatusEndpoint
            self._status = StatusEndpoint(self._bundle, self._context, self._config)
        return self._status

    def _get_viewport(self):
        if self._viewport is None:
            from forensic_api.viewport import ViewportEndpoint
            self._viewport = ViewportEndpoint(self._bundle, self._context, self._config)
        return self._viewport

    def _get_static(self):
        if self._static is None:
            from forensic_api.static import StaticEndpoint
            self._static = StaticEndpoint()
        return self._static

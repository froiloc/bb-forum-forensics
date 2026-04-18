# =============================================================================
# forensic_api/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Registriert alle forensic_api-Endpunkte und stellt die dispatch()-Funktion
#   bereit, die router.py aufruft.
#
# Endpunkte:
#   /_forensic/page             (GET)       → PageEndpoint
#   /_forensic/annotate         (POST)      → AnnotateEndpoint
#   /_forensic/status           (GET)       → StatusEndpoint
#   /_forensic/viewport         (POST)      → ViewportEndpoint
#   /_forensic/toolbar.js       (GET)       → StaticEndpoint
#   /_forensic/toolbar.css      (GET)       → StaticEndpoint
#   /_forensic/annotations      (GET)       → AnnotationsEndpoint  [B3, Build 011]
#   /_forensic/events           (GET, SSE)  → EventsEndpoint       [B3, Build 011]
#   /_forensic/userinfo         (GET)       → UserinfoEndpoint      [B4, Build 012]
#   /_forensic/userinfo/data    (GET)       → UserinfoDataEndpoint  [B4, Build 012]
#   /_forensic/userinfo/static  (GET)       → UserinfoStaticEndpoint [B4, Build 037]
#   /_forensic/userinfo.js      (GET)       → StaticEndpoint        [B4, Build 012]
#   /_forensic/userinfo.css     (GET)       → StaticEndpoint        [B4, Build 012]
#   /_forensic/report           (GET, POST) → ReportEndpoint        [B4, Build 012]
#
# Version: v0.1.0 · Build: 012 · 2026-04-14
# =============================================================================

from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

# Maximale Request-Body-Größe für POST-Endpunkte (1 MB)
_MAX_BODY_SIZE = 1 * 1024 * 1024


class ForensicApi:
    """
    Dispatch-Klasse für alle /_forensic/-Endpunkte.
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
        self._page          = None
        self._annotate      = None
        self._status        = None
        self._viewport      = None
        self._static        = None
        self._annotations   = None  # [B3, Build 011]
        self._events        = None  # [B3, Build 011]
        self._userinfo        = None  # [B4, Build 012]
        self._userinfo_data   = None  # [B4, Build 012]
        self._userinfo_static = None  # [B4, Build 037]
        self._report          = None  # [B4, Build 012]

    def dispatch(
        self,
        handler: "ForensicRequestHandler",
        method: str,
        url_path: str,
        query: str,
        is_ajax: bool,
    ) -> None:
        """
        Leitet /_forensic/-Requests an den zuständigen Endpunkt-Handler weiter.
        """
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
                return
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

        # /_forensic/toolbar.js, /_forensic/toolbar.css,
        # /_forensic/userinfo.js, /_forensic/userinfo.css (GET) [letzte zwei: B4]
        if url_path in (
            "/_forensic/toolbar.js",
            "/_forensic/toolbar.css",
            "/_forensic/userinfo.js",
            "/_forensic/userinfo.css",
        ):
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_static().handle(handler, url_path)
            return

        # /_forensic/annotations (GET) — [B3, Build 011]
        if url_path == "/_forensic/annotations":
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_annotations().handle(handler, params)
            return

        # /_forensic/events (GET, SSE) — [B3, Build 011]
        if url_path == "/_forensic/events":
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_events().handle(handler)
            return

        # /_forensic/userinfo/static (GET) — [B4, Build 037]
        # Reihenfolge: vor /data und /userinfo prüfen (längster Pfad zuerst)
        if url_path == "/_forensic/userinfo/static":
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_userinfo_static().handle(handler)
            return

        # /_forensic/userinfo/data (GET) — [B4, Build 012]
        # Reihenfolge wichtig: vor /_forensic/userinfo prüfen (längerer Pfad zuerst)
        if url_path == "/_forensic/userinfo/data":
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_userinfo_data().handle(handler)
            return

        # /_forensic/userinfo (GET) — [B4, Build 012]
        if url_path == "/_forensic/userinfo":
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_userinfo().handle(handler)
            return

        # /_forensic/report (GET, POST) — [B4, Build 012]
        if url_path == "/_forensic/report":
            if method == "GET":
                self._get_report().handle_get(handler, params)
                return
            elif method == "POST":
                body = self._read_body(handler)
                if body is None:
                    return
                self._get_report().handle_post(handler, body)
                return
            else:
                self._method_not_allowed(handler)
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

    def _read_body(self, handler: "ForensicRequestHandler") -> "bytes | None":
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

    def _get_annotations(self):
        """[B3, Build 011] Lazy-Init für AnnotationsEndpoint."""
        if self._annotations is None:
            from forensic_api.annotations import AnnotationsEndpoint
            self._annotations = AnnotationsEndpoint(self._bundle, self._context, self._config)
        return self._annotations

    def _get_events(self):
        """[B3, Build 011] Lazy-Init für EventsEndpoint (SSE)."""
        if self._events is None:
            from forensic_api.events import EventsEndpoint
            self._events = EventsEndpoint(self._bundle, self._context, self._config)
        return self._events

    def _get_userinfo_static(self):
        """[B4, Build 037] Lazy-Init für UserinfoStaticEndpoint."""
        if self._userinfo_static is None:
            from forensic_api.userinfo_static import UserinfoStaticEndpoint
            self._userinfo_static = UserinfoStaticEndpoint(self._bundle, self._context, self._config)
        return self._userinfo_static

    def _get_userinfo(self):
        """[B4, Build 012] Lazy-Init für UserinfoEndpoint."""
        if self._userinfo is None:
            from forensic_api.userinfo import UserinfoEndpoint
            self._userinfo = UserinfoEndpoint(self._bundle, self._context, self._config)
        return self._userinfo

    def _get_userinfo_data(self):
        """[B4, Build 012] Lazy-Init für UserinfoDataEndpoint."""
        if self._userinfo_data is None:
            from forensic_api.userinfo_data import UserinfoDataEndpoint
            self._userinfo_data = UserinfoDataEndpoint(self._bundle, self._context, self._config)
        return self._userinfo_data

    def _get_report(self):
        """[B4, Build 012] Lazy-Init für ReportEndpoint."""
        if self._report is None:
            from forensic_api.report import ReportEndpoint
            self._report = ReportEndpoint(self._bundle, self._context, self._config)
        return self._report

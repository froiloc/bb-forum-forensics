# =============================================================================
# forensic_api/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Registriert alle forensic_api-Endpunkte und stellt die dispatch()-Funktion
#   bereit, die router.py aufruft.
#
# Endpunkte:
#   /_forensic/page              (GET)        -> PageEndpoint
#   /_forensic/annotate          (POST)       -> AnnotateEndpoint
#   /_forensic/status            (GET)        -> StatusEndpoint
#   /_forensic/viewport          (POST)       -> ViewportEndpoint
#   /_forensic/toolbar.js        (GET)        -> StaticEndpoint
#   /_forensic/toolbar.css       (GET)        -> StaticEndpoint
#   /_forensic/annotations       (GET)        -> AnnotationsEndpoint  [B3]
#   /_forensic/events            (GET, SSE)   -> EventsEndpoint       [B3]
#   /_forensic/userinfo          (GET)        -> UserinfoEndpoint      [B4]
#   /_forensic/userinfo/data     (GET)        -> UserinfoDataEndpoint  [B4]
#   /_forensic/userinfo/static   (GET)        -> UserinfoStaticEndpoint [B4]
#   /_forensic/userinfo.js       (GET)        -> StaticEndpoint        [B4]
#   /_forensic/userinfo.css      (GET)        -> StaticEndpoint        [B4]
#   /_forensic/report            (GET, POST)  -> ReportEndpoint        [B4]
#   /_forensic/reports           (GET, POST)  -> ReportsEndpoint       [AP-E3]
#   /_forensic/editor/block      (POST)       -> EditorBlockEndpoint   [AP-E3]
#   /_forensic/editor/order      (POST)       -> EditorOrderEndpoint   [AP-E3]
#   /_forensic/editor/evidence   (POST)       -> EditorEvidenceEndpoint [AP-E3]
#   /_forensic/static/editor/*   (GET)        -> StaticEndpoint.handle_editor_asset [AP-E3]
#
# Routing-Reihenfolge bei Praefix-Konflikten:
#   Laengere/spezifischere Pfade werden zuerst geprueft:
#   /_forensic/userinfo/static  vor  /_forensic/userinfo/data  vor  /_forensic/userinfo
#   /_forensic/static/editor/*  vor  anderen /_forensic/static/-Pfaden (falls ergaenzt)
#   /_forensic/editor/*         als Praefix-Block
#   Beleg: AP-E3, Projektgespraech 2026-04-19
#
# Changelog:
#   Build 012: Erstimplementierung B3+B4-Endpunkte.
#   Build 044 (AP-E3): Fuenf neue Endpunkte ergaenzt:
#     ReportsEndpoint, EditorBlockEndpoint, EditorOrderEndpoint,
#     EditorEvidenceEndpoint, StaticEndpoint.handle_editor_asset.
#     Beleg: AP-E3, Projektgespraech 2026-04-19
#
# Version: v0.6.044 · Build: 044 · 2026-04-19
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

# Maximale Request-Body-Groesse fuer POST-Endpunkte (1 MB)
_MAX_BODY_SIZE = 1 * 1024 * 1024

# Praefix fuer Editor.js-Asset-Pfade (AP-E3)
_EDITOR_STATIC_PREFIX = "/_forensic/static/editor/"

# Praefix fuer Editor-API-Pfade (AP-E3)
_EDITOR_API_PREFIX = "/_forensic/editor/"


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
        self._page             = None
        self._annotate         = None
        self._status           = None
        self._viewport         = None
        self._static           = None
        self._annotations      = None  # [B3]
        self._events           = None  # [B3]
        self._userinfo         = None  # [B4]
        self._userinfo_data    = None  # [B4]
        self._userinfo_static  = None  # [B4]
        self._report           = None  # [B4]
        self._reports          = None  # [AP-E3]
        self._editor_block     = None  # [AP-E3]
        self._editor_order     = None  # [AP-E3]
        self._editor_evidence  = None  # [AP-E3]

    def dispatch(
        self,
        handler: "ForensicRequestHandler",
        method: str,
        url_path: str,
        query: str,
        is_ajax: bool,
    ) -> None:
        """Leitet /_forensic/-Requests an den zustaendigen Endpunkt weiter."""
        params = urllib.parse.parse_qs(query, keep_blank_values=False)

        # /_forensic/page (GET)
        if url_path == "/_forensic/page":
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_page().handle(handler, params)
            return

        # /_forensic/annotate (POST → anlegen, DELETE → löschen)
        if url_path == "/_forensic/annotate":
            if method not in ("POST", "DELETE"):
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
        # /_forensic/userinfo.js, /_forensic/userinfo.css
        if url_path in (
            "/_forensic/toolbar.js",
            "/_forensic/toolbar.css",
            "/_forensic/userinfo.js",
            "/_forensic/userinfo.css",
            "/_forensic/editor.js",      # AP-E4
        ):
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_static().handle(handler, url_path)
            return

        # /_forensic/annotations (GET) [B3]
        if url_path == "/_forensic/annotations":
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_annotations().handle(handler, params)
            return

        # /_forensic/events (GET, SSE) [B3]
        if url_path == "/_forensic/events":
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_events().handle(handler, params)
            return

        # /_forensic/static/editor/* (GET) [AP-E3]
        # Vor anderen /_forensic/static/-Pfaden pruefen (laengster Praefix zuerst).
        # Beleg: AP-E3, Projektgespraech 2026-04-19
        if url_path.startswith(_EDITOR_STATIC_PREFIX):
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_static().handle_editor_asset(handler, url_path)
            return

        # /_forensic/editor/* (POST) [AP-E3]
        # Praefix-Block: alle Editor-API-Pfade.
        # Beleg: AP-E3, Projektgespraech 2026-04-19
        if url_path.startswith(_EDITOR_API_PREFIX):
            self._dispatch_editor(handler, method, url_path)
            return

        # /_forensic/userinfo/static (GET) [B4]
        # Vor /userinfo/data und /userinfo pruefen (laengster Pfad zuerst).
        if url_path == "/_forensic/userinfo/static":
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_userinfo_static().handle(handler)
            return

        # /_forensic/userinfo/data (GET) [B4]
        if url_path == "/_forensic/userinfo/data":
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_userinfo_data().handle(handler)
            return

        # /_forensic/userinfo (GET) [B4]
        if url_path == "/_forensic/userinfo":
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_userinfo().handle(handler)
            return

        # /_forensic/reports (GET, POST) [AP-E3]
        # Vor /_forensic/report pruefen (laengerer Pfad zuerst).
        # Beleg: AP-E3, Projektgespraech 2026-04-19
        if url_path == "/_forensic/reports":
            if method == "GET":
                self._get_reports().handle_get(handler)
                return
            elif method == "POST":
                body = self._read_body(handler)
                if body is None:
                    return
                self._get_reports().handle_post(handler, body)
                return
            else:
                self._method_not_allowed(handler)
                return

        # /_forensic/report (GET, POST) [B4]
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

    def _dispatch_editor(
        self,
        handler: "ForensicRequestHandler",
        method: str,
        url_path: str,
    ) -> None:
        """
        Interne Dispatch-Funktion fuer /_forensic/editor/*-Pfade.
        Beleg: AP-E3, Projektgespraech 2026-04-19
        """
        if url_path == "/_forensic/editor/block":
            if method != "POST":
                self._method_not_allowed(handler)
                return
            body = self._read_body(handler)
            if body is None:
                return
            self._get_editor_block().handle(handler, body)
            return

        if url_path == "/_forensic/editor/order":
            if method != "POST":
                self._method_not_allowed(handler)
                return
            body = self._read_body(handler)
            if body is None:
                return
            self._get_editor_order().handle(handler, body)
            return

        if url_path == "/_forensic/editor/evidence":
            if method != "POST":
                self._method_not_allowed(handler)
                return
            body = self._read_body(handler)
            if body is None:
                return
            self._get_editor_evidence().handle(handler, body)
            return

        # Unbekannter Editor-Pfad
        import json
        logger.warning("Unbekannter Editor-Endpunkt: '%s'", url_path)
        body_out = json.dumps(
            {"error": f"Editor-Endpunkt '{url_path}' nicht bekannt"}
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
        if self._annotations is None:
            from forensic_api.annotations import AnnotationsEndpoint
            self._annotations = AnnotationsEndpoint(self._bundle, self._context, self._config)
        return self._annotations

    def _get_events(self):
        if self._events is None:
            from forensic_api.events import EventsEndpoint
            self._events = EventsEndpoint(self._bundle, self._context, self._config)
        return self._events

    def _get_userinfo_static(self):
        if self._userinfo_static is None:
            from forensic_api.userinfo_static import UserinfoStaticEndpoint
            self._userinfo_static = UserinfoStaticEndpoint(self._bundle, self._context, self._config)
        return self._userinfo_static

    def _get_userinfo(self):
        if self._userinfo is None:
            from forensic_api.userinfo import UserinfoEndpoint
            self._userinfo = UserinfoEndpoint(self._bundle, self._context, self._config)
        return self._userinfo

    def _get_userinfo_data(self):
        if self._userinfo_data is None:
            from forensic_api.userinfo_data import UserinfoDataEndpoint
            self._userinfo_data = UserinfoDataEndpoint(self._bundle, self._context, self._config)
        return self._userinfo_data

    def _get_report(self):
        if self._report is None:
            from forensic_api.report import ReportEndpoint
            self._report = ReportEndpoint(self._bundle, self._context, self._config)
        return self._report

    def _get_reports(self):
        """[AP-E3] Lazy-Init fuer ReportsEndpoint."""
        if self._reports is None:
            from forensic_api.reports import ReportsEndpoint
            self._reports = ReportsEndpoint(self._bundle, self._context, self._config)
        return self._reports

    def _get_editor_block(self):
        """[AP-E3] Lazy-Init fuer EditorBlockEndpoint."""
        if self._editor_block is None:
            from forensic_api.editor_block import EditorBlockEndpoint
            self._editor_block = EditorBlockEndpoint(self._bundle, self._context, self._config)
        return self._editor_block

    def _get_editor_order(self):
        """[AP-E3] Lazy-Init fuer EditorOrderEndpoint."""
        if self._editor_order is None:
            from forensic_api.editor_order import EditorOrderEndpoint
            self._editor_order = EditorOrderEndpoint(self._bundle, self._context, self._config)
        return self._editor_order

    def _get_editor_evidence(self):
        """[AP-E3] Lazy-Init fuer EditorEvidenceEndpoint."""
        if self._editor_evidence is None:
            from forensic_api.editor_evidence import EditorEvidenceEndpoint
            self._editor_evidence = EditorEvidenceEndpoint(self._bundle, self._context, self._config)
        return self._editor_evidence

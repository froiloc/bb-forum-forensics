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
#   /_forensic/trace_sequence    (GET)        -> TraceSequenceEndpoint  [KN-7]
#   /_forensic/reports           (GET, POST)  -> ReportsEndpoint       [AP-E3]
#   /_forensic/editor/block      (POST)       -> EditorBlockEndpoint   [AP-E3]
#   /_forensic/editor/order      (POST)       -> EditorOrderEndpoint   [AP-E3]
#   /_forensic/editor/evidence   (POST)       -> EditorEvidenceEndpoint [AP-E3]
#   /_forensic/static/vendor/*   (GET)        -> StaticEndpoint.handle_vendor_asset [Build 084]
#   /_forensic/static/editor/*   (GET)        -> StaticEndpoint.handle_editor_asset [AP-E3]
#   /_forensic/placeholders/resolve  (POST)      -> PlaceholdersEndpoint [B6]
#   /_forensic/placeholders/refresh  (POST)      -> PlaceholdersEndpoint [B6]
#   /_forensic/placeholders/library  (GET)       -> PlaceholdersEndpoint [B6]
#   /_forensic/templates             (GET)       -> TemplatesEndpoint    [B6]
#   /_forensic/templates/<id>        (GET)       -> TemplatesEndpoint    [B6]
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
#   Build 072 (KN-7): TraceSequenceEndpoint ergaenzt (/_forensic/trace_sequence).
#
#   Build 089 (B6 — Phase 3): PlaceholdersEndpoint und TemplatesEndpoint ergaenzt.
#   Build 090 (B6 — Phase 4): report.js und report.css als statische Assets registriert.
#   Build 096 (B6 — Phase 9): /_forensic/investigator/me Endpunkt ergaenzt.
#     ReportEndpoint auf B6-Schema umgestellt (Paragraphen statt Bloecke).
#     Drei neue /_forensic/placeholders/*-Endpunkte.
#     Zwei neue /_forensic/templates[/<id>]-Endpunkte.
#     Beleg: Bauplan B6 v0.3 §3, §5, 2026-05-05
#   Build 099 (B6 Phase 1): evidence_db.py auf report_blocks umgestellt.
#   Build 100 (B6 Phase 2): editor.js -> report_editor.js umbenannt.
#     report.js (contenteditable-Modell) entfernt.
#     Beleg: Bauplan B6 v0.5 §4.1, Projektgespraech 2026-05-06
#
# Version: v0.6.114 · Build: 114 · 2026-05-07
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

# Praefix fuer Vendor-Asset-Pfade (Build 084)
_VENDOR_STATIC_PREFIX = "/_forensic/static/vendor/"

# Praefix fuer Plugin-Icon-Pfade (Build 114)
_ICONS_STATIC_PREFIX  = "/_forensic/static/icons/"

# Praefix fuer Editor-API-Pfade (AP-E3)
_EDITOR_API_PREFIX = "/_forensic/editor/"

# Praefix fuer Platzhalter-API-Pfade (B6)
_PLACEHOLDERS_PREFIX = "/_forensic/placeholders/"


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
        build_info=None,
    ) -> None:
        self._bundle     = bundle
        self._build_info = build_info
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
        self._search           = None  # [KN-3]
        self._trace_sequence   = None  # [KN-7]
        self._placeholders    = None  # [B6]
        self._templates_ep    = None  # [B6]

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
            "/_forensic/report_editor.js",      # B6 Phase 2 (umbenannt von editor.js)
            "/_forensic/report.css",            # B6 Phase 4 Stylesheet
            "/_forensic/placeholder_chips.js",  # B6 Phase 4 Chips
            "/_forensic/placeholder_wizard.js", # B6 Phase 5 Wizard
            "/_forensic/module_panel.js",       # B6 Phase 6 Panel
            "/_forensic/annotation_sidebar.js", # B6 Phase 7 Sidebar
            "/_forensic/comment_thread.js",     # B6 Phase 8 Kommentare
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

        # /_forensic/version (GET) [Build 174]
        # Build-Info: version, build, date.
        # Beleg: Projektgespraech 2026-05-11
        if url_path == "/_forensic/version":
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_version().handle(handler)
            return

        # /_forensic/windows (GET/POST/DELETE) [Build 173]
        # Fenster-Registrierung fuer BroadcastChannel-Fallback.
        # Beleg: Projektgespraech 2026-05-11
        if url_path == "/_forensic/windows":
            if method not in ("GET", "POST", "DELETE"):
                self._method_not_allowed(handler)
                return
            body = self._read_body(handler) if method in ("POST", "DELETE") else None
            self._get_windows().handle(handler, method, body)
            return

        # /_forensic/static/vendor/* (GET) [Build 084]
        # Vendor-Bibliotheken (Tabulator.js). Vor editor-Praefix pruefen.
        # Beleg: Projektgespraech 2026-05-05
        if url_path.startswith(_VENDOR_STATIC_PREFIX):
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_static().handle_vendor_asset(handler, url_path)
            return

        # /_forensic/static/icons/* (GET) [Build 114]
        if method == "GET" and url_path.startswith(_ICONS_STATIC_PREFIX):
            self._get_static().handle_icons_asset(handler, url_path)
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

        # /_forensic/trace_sequence (GET) [KN-7]
        if url_path == "/_forensic/trace_sequence":
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_trace_sequence().handle(handler, params)
            return

        # /_forensic/export (GET) [B6 Phase 10/11]
        # Beleg: Bauplan B6 v0.3 §7.2, Build 097
        if url_path == '/_forensic/export':
            if method not in ('GET', 'HEAD'):
                self._method_not_allowed(handler)
                return
            self._get_export_ep().handle_get(handler, params)
            return

        # /_forensic/investigator/me (GET) [B6 Phase 9]
        # Beleg: Bauplan B6 v0.3 §4.3, Build 096
        if url_path == '/_forensic/investigator/me':
            if method not in ('GET', 'HEAD'):
                self._method_not_allowed(handler)
                return
            self._get_investigator_me().handle_get(handler)
            return

        # /_forensic/placeholders/* (POST/GET) [B6]
        # Beleg: Bauplan B6 v0.3 §3, §5, Build 089
        if url_path.startswith(_PLACEHOLDERS_PREFIX):
            self._dispatch_placeholders(handler, method, url_path, params)
            return

        # /_forensic/templates (GET, Liste) und
        # /_forensic/templates/<id> (GET, Einzelmodul) [B6]
        if url_path == "/_forensic/templates" or url_path.startswith("/_forensic/templates/"):
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_templates_ep().handle_get(handler, url_path, params)
            return

        # /_forensic/search (GET) [KN-3]
        # Kontext-Navigator: gefilterte Seitenliste für Dropdown + Modal.
        # Beleg: Bauplan KN v0.6 §7.3, Build 070.
        if url_path == "/_forensic/search":
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_search().handle(handler, params)
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

    def _dispatch_placeholders(
        self,
        handler: "ForensicRequestHandler",
        method: str,
        url_path: str,
        params: dict,
    ) -> None:
        """
        Interne Dispatch-Funktion fuer /_forensic/placeholders/*-Pfade.
        Beleg: Bauplan B6 v0.3 §3, Build 089
        """
        if url_path == "/_forensic/placeholders/resolve":
            if method != "POST":
                self._method_not_allowed(handler)
                return
            body = self._read_body(handler)
            if body is None:
                return
            self._get_placeholders().handle_resolve(handler, body)
            return

        if url_path == "/_forensic/placeholders/refresh":
            if method != "POST":
                self._method_not_allowed(handler)
                return
            body = self._read_body(handler)
            if body is None:
                return
            self._get_placeholders().handle_refresh(handler, body)
            return

        if url_path == "/_forensic/placeholders/library":
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_placeholders().handle_library(handler, params)
            return

        # B6 Phase 6: placeholder_values_json aller Bloecke des aktiven Berichts
        # Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06
        if url_path == "/_forensic/placeholders/values":
            if method not in ("GET", "HEAD"):
                self._method_not_allowed(handler)
                return
            self._get_placeholders().handle_values(handler)
            return

        import json as _json
        logger.warning("Unbekannter Placeholders-Endpunkt: '%s'", url_path)
        handler.send_response_body(
            404,
            _json.dumps({"error": f"Endpunkt '{url_path}' nicht bekannt"}
            ).encode("utf-8"),
            content_type="application/json; charset=utf-8",
        )

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

    def _get_version(self):
        """Version-Endpunkt (Build 174). Beleg: Projektgespraech 2026-05-11"""
        if not hasattr(self, '_version_ep'):
            from forensic_api.version import VersionEndpoint
            self._version_ep = VersionEndpoint(self._build_info)
        return self._version_ep

    def _get_windows(self):
        """Fenster-Registrierung (Build 173). Beleg: Projektgespraech 2026-05-11"""
        if not hasattr(self, '_windows_ep'):
            from forensic_api.windows import WindowsEndpoint
            self._windows_ep = WindowsEndpoint()
        return self._windows_ep

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

    def _get_export_ep(self):
        """[B6 Phase 10/11] Lazy-Init fuer ExportEndpoint."""
        if not hasattr(self, '_export_ep_inst') or self._export_ep_inst is None:
            from forensic_api.export import ExportEndpoint
            self._export_ep_inst = ExportEndpoint(
                self._bundle, self._context, self._config
            )
        return self._export_ep_inst

    def _get_investigator_me(self):
        """[B6 Phase 9] Lazy-Init fuer InvestigatorMeEndpoint."""
        if not hasattr(self, '_investigator_me_ep') or self._investigator_me_ep is None:
            from forensic_api.investigator_me import InvestigatorMeEndpoint
            self._investigator_me_ep = InvestigatorMeEndpoint(
                self._bundle, self._context, self._config
            )
        return self._investigator_me_ep

    def _get_placeholders(self):
        """[B6] Lazy-Init fuer PlaceholdersEndpoint. Beleg: Bauplan B6 v0.3 §3."""
        if self._placeholders is None:
            from forensic_api.placeholders import PlaceholdersEndpoint
            self._placeholders = PlaceholdersEndpoint(self._bundle, self._context, self._config)
        return self._placeholders

    def _get_templates_ep(self):
        """[B6] Lazy-Init fuer TemplatesListEndpoint. Beleg: Bauplan B6 v0.3 §5."""
        if self._templates_ep is None:
            from forensic_api.templates_ep import TemplatesListEndpoint
            self._templates_ep = TemplatesListEndpoint(self._bundle, self._context, self._config)
        return self._templates_ep

    def _get_search(self):
        """[KN-3] Lazy-Init fuer SearchEndpoint. Beleg: Bauplan KN v0.6 §12 Phase KN-3."""
        if self._search is None:
            from forensic_api.search import SearchEndpoint
            self._search = SearchEndpoint(self._bundle, self._context, self._config)
        return self._search

    def _get_trace_sequence(self):
        """[KN-7] Lazy-Init fuer TraceSequenceEndpoint. Beleg: OP-KN-7, Build 072."""
        if self._trace_sequence is None:
            from forensic_api.trace_sequence import TraceSequenceEndpoint
            self._trace_sequence = TraceSequenceEndpoint(self._bundle, self._context, self._config)
        return self._trace_sequence

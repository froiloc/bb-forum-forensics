# =============================================================================
# forensic_api/static.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkte fuer statische Frontend-Ressourcen:
#     /_forensic/toolbar.js      (GET) -> toolbar/toolbar.js
#     /_forensic/toolbar.css     (GET) -> toolbar/toolbar.css
#     /_forensic/userinfo.js     (GET) -> userinfo/userinfo.js    [Build 012]
#     /_forensic/userinfo.css    (GET) -> userinfo/userinfo.css   [Build 012]
#     /_forensic/static/editor/* (GET) -> static/editor/<file>   [AP-E3]
#
#   Verhalten bei fehlenden Ressourcen:
#     - toolbar.js / toolbar.css / userinfo.js / userinfo.css:
#       Leerer Platzhalter (kein 404) — Browser blockiert nicht.
#     - /_forensic/static/editor/*:
#       HTTP 503 Service Unavailable mit JSON-Fehlerbody wenn Datei fehlt.
#       Das Editor-Bundle fehlt = schwerwiegender Fehler, kein stiller Fallback.
#       Beleg: AP-E3, Projektgespraech 2026-04-19
#
# Changelog:
#   Build 010: Erstimplementierung (toolbar.js, toolbar.css).
#   Build 012: userinfo.js, userinfo.css ergaenzt.
#   Build 084: /_forensic/static/vendor/*-Auslieferung ergaenzt (Tabulator.js).
#   Build 044 (AP-E3): /_forensic/static/editor/*-Auslieferung ergaenzt.
#   Build 090 (B6 Phase 4): report.js und report.css ergaenzt (Fenster 3).
#     - handle_editor_asset(): dedizierte Methode fuer Editor.js-Bundle-Assets.
#     - HTTP 503 bei fehlendem Bundle (statt leerem Platzhalter).
#     - MIME-Type-Erkennung anhand Dateiendung.
#     Beleg: AP-E3, Projektgespraech 2026-04-19
#   Build 100 (B6 Phase 2): editor.js -> report_editor.js umbenannt.
#     report.js (contenteditable-Modell) entfernt.
#     Beleg: Bauplan B6 v0.5 §4.1, Projektgespraech 2026-05-06
#
# Version: v0.6.114 · Build: 114 · 2026-05-07
# =============================================================================

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler

logger = get_logger(__name__)

# Verzeichnisse relativ zu diesem Modul
_BASE_DIR      = Path(__file__).resolve().parent.parent
_TOOLBAR_DIR   = _BASE_DIR / "toolbar"
_USERINFO_DIR  = _BASE_DIR / "userinfo"
_EDITOR_DIR    = _BASE_DIR / "static" / "editor"   # AP-E3: Editor.js-Bundle
_VENDOR_DIR    = _BASE_DIR / "static" / "vendor"   # Build 084: Vendor-Bibliotheken
_ICONS_DIR     = _BASE_DIR / "static" / "icons"    # Build 114: Plugin-Icons

# Ressourcen-Registry: Pfad -> (Dateiname, MIME-Type, Verzeichnis)
_RESOURCES: dict[str, tuple[str, str, Path]] = {
    "/_forensic/toolbar.js":   ("toolbar.js",   "application/javascript; charset=utf-8", _TOOLBAR_DIR),
    "/_forensic/toolbar.css":  ("toolbar.css",  "text/css; charset=utf-8",               _TOOLBAR_DIR),
    "/_forensic/userinfo.js":  ("userinfo.js",  "application/javascript; charset=utf-8", _USERINFO_DIR),
    "/_forensic/userinfo.css": ("userinfo.css", "text/css; charset=utf-8",               _USERINFO_DIR),
    # B6 Phase 2: report_editor.js (umbenannt von editor.js, Build 100)
    # Beleg: Bauplan B6 v0.5 §4.1, Projektgespraech 2026-05-06
    "/_forensic/report_editor.js": ("report_editor.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # B6 Build 200: debug_events.js — Event-Tracing (window._uevt), USER vs. WORKFLOW
    # Beleg: Projektgespraech 2026-05-17
    "/_forensic/debug_events.js": ("debug_events.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # B6 Phase 4: Fenster-3-Stylesheet (report.css unveraendert)
    "/_forensic/report.css":   ("report.css",   "text/css; charset=utf-8",               _USERINFO_DIR),
    # B6 Phase 4 (Chip-Rendering): Platzhalter-Parser
    "/_forensic/placeholder_chips.js": ("placeholder_chips.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # B6 Phase 5 (Wizard): Platzhalter-Wizard
    "/_forensic/placeholder_wizard.js": ("placeholder_wizard.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # B6 Phase 6 (Modul-Panel): Modul-Auswahl
    "/_forensic/module_panel.js": ("module_panel.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # B6 Phase 7 (Sidebar): Annotationsseitenleiste
    "/_forensic/annotation_sidebar.js": ("annotation_sidebar.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # B6 Phase 8 (Kommentare): Kommentar-Thread
    "/_forensic/comment_thread.js": ("comment_thread.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
}

# MIME-Types fuer Editor.js-Bundle-Dateien (AP-E3)
_EDITOR_MIME: dict[str, str] = {
    ".js":    "application/javascript; charset=utf-8",
    ".css":   "text/css; charset=utf-8",
    ".woff":  "font/woff",
    ".woff2": "font/woff2",
    ".ttf":   "font/ttf",
    ".svg":   "image/svg+xml",
    ".map":   "application/json; charset=utf-8",
}

# Fehlerbody fuer fehlendes Editor-Bundle (HTTP 503)
_BUNDLE_MISSING_BODY = json.dumps(
    {
        "error": "Editor-Bundle nicht installiert",
        "code":  "EDITOR_BUNDLE_MISSING",
        "hint":  "AP-E2 ausfuehren: build_editor_bundle.py (Baustelle 1)",
    },
    ensure_ascii=False,
).encode("utf-8")


class StaticEndpoint:
    """
    Liefert statische Frontend-Ressourcen fuer Toolbar (B3),
    Nutzerinfo-Tab (B4) und Editor.js-Bundle (AP-E3) aus.
    """

    def handle(
        self,
        handler: "ForensicRequestHandler",
        url_path: str,
    ) -> None:
        """
        Verarbeitet GET-Request fuer eine bekannte statische Ressource
        (toolbar.js / toolbar.css / userinfo.js / userinfo.css).

        Fuer /_forensic/static/editor/* -> handle_editor_asset() verwenden.

        Args:
            handler:  ForensicRequestHandler-Instanz.
            url_path: Angeforderter Pfad.
        """
        entry = _RESOURCES.get(url_path)
        if entry is None:
            logger.warning("StaticEndpoint: unbekannter Pfad '%s'", url_path)
            handler.send_response_body(404, b"")
            return

        filename, mime_type, directory = entry
        file_path = directory / filename

        try:
            data = file_path.read_bytes()
            logger.debug("Static: '%s' ausgeliefert (%d bytes)", url_path, len(data))
        except FileNotFoundError:
            logger.warning(
                "Statische Ressource nicht gefunden: '%s' — leerer Platzhalter",
                file_path,
            )
            data = b""

        # Build 187 (Bug 2.93): Cache-Control: no-cache verhindert dass der Browser
        # veraltete toolbar.js/toolbar.css aus dem Cache laedt.
        # Beleg: Console zeigte build042 obwohl Server build185 lieferte.
        extra_headers = {"Cache-Control": "no-cache, must-revalidate"}
        handler.send_response_body(200, data, content_type=mime_type,
                                   extra_headers=extra_headers)

    def handle_editor_asset(
        self,
        handler: "ForensicRequestHandler",
        url_path: str,
    ) -> None:
        """
        Liefert Editor.js-Bundle-Dateien aus /_forensic/static/editor/<file> aus.

        HTTP 503 wenn die Datei nicht gefunden wird — das Bundle fehlt und muss
        via AP-E2 (build_editor_bundle.py) installiert werden.
        Beleg: AP-E3, Projektgespraech 2026-04-19

        Args:
            handler:  ForensicRequestHandler-Instanz.
            url_path: Vollstaendiger Pfad, z.B. /_forensic/static/editor/editor.bundle.js
        """
        # Dateinamen aus URL extrahieren
        # Erwartet: /_forensic/static/editor/<dateiname>
        prefix = "/_forensic/static/editor/"
        if not url_path.startswith(prefix):
            handler.send_response_body(
                400,
                json.dumps({"error": "Ungueltiger Pfad"}).encode("utf-8"),
                content_type="application/json; charset=utf-8",
            )
            return

        filename = url_path[len(prefix):]

        # Pfad-Traversal verhindern: keine Slash, keine Punkte am Anfang
        if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
            logger.warning(
                "handle_editor_asset: ungueltiger Dateiname '%s'", filename
            )
            handler.send_response_body(
                400,
                json.dumps({"error": "Ungueltiger Dateiname"}).encode("utf-8"),
                content_type="application/json; charset=utf-8",
            )
            return

        file_path = _EDITOR_DIR / filename

        # MIME-Type anhand Dateiendung bestimmen
        suffix = Path(filename).suffix.lower()
        mime_type = _EDITOR_MIME.get(suffix, "application/octet-stream")

        try:
            data = file_path.read_bytes()
            logger.debug(
                "Editor-Asset: '%s' ausgeliefert (%d bytes)", filename, len(data)
            )
            handler.send_response_body(200, data, content_type=mime_type)
        except FileNotFoundError:
            logger.warning(
                "Editor-Bundle-Datei fehlt: '%s' — HTTP 503", file_path
            )
            handler.send_response_body(
                503,
                _BUNDLE_MISSING_BODY,
                content_type="application/json; charset=utf-8",
                extra_headers={"Retry-After": "3600"},
            )

    def handle_vendor_asset(
        self,
        handler: "ForensicRequestHandler",
        url_path: str,
    ) -> None:
        """
        Liefert Vendor-Bibliotheken aus /_forensic/static/vendor/<lib>/<file> aus.

        Unterstuetzt: tabulator/tabulator.min.js, tabulator/tabulator.min.css.
        Gibt HTTP 404 zurueck wenn die Datei nicht gefunden wird.
        Beleg: Projektgespraech 2026-05-05, Build 084.

        Args:
            handler:  ForensicRequestHandler-Instanz.
            url_path: Vollstaendiger Pfad, z.B.
                      /_forensic/static/vendor/tabulator/tabulator.min.js
        """
        prefix = "/_forensic/static/vendor/"
        if not url_path.startswith(prefix):
            handler.send_response_body(
                400,
                json.dumps({"error": "Ungueltiger Pfad"}).encode("utf-8"),
                content_type="application/json; charset=utf-8",
            )
            return

        # Relativer Pfad: z.B. "tabulator/tabulator.min.js"
        rel = url_path[len(prefix):]

        # Pfad-Traversal verhindern: keine ".." erlaubt
        if not rel or ".." in rel or rel.startswith("/"):
            logger.warning(
                "handle_vendor_asset: ungueltiger Pfad '%s'", rel
            )
            handler.send_response_body(
                400,
                json.dumps({"error": "Ungueltiger Pfad"}).encode("utf-8"),
                content_type="application/json; charset=utf-8",
            )
            return

        file_path = _VENDOR_DIR / rel

        suffix = Path(file_path).suffix.lower()
        mime_map = {
            ".js":  "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".map": "application/json; charset=utf-8",
        }
        mime_type = mime_map.get(suffix, "application/octet-stream")

        try:
            data = file_path.read_bytes()
            logger.debug(
                "Vendor-Asset: '%s' ausgeliefert (%d bytes)", rel, len(data)
            )
            handler.send_response_body(200, data, content_type=mime_type)
        except FileNotFoundError:
            logger.warning(
                "Vendor-Asset nicht gefunden: '%s' — HTTP 404", file_path
            )
            handler.send_response_body(
                404,
                json.dumps({"error": f"Vendor-Datei nicht gefunden: {rel}"}).encode("utf-8"),
                content_type="application/json; charset=utf-8",
            )
    def handle_icons_asset(
        self,
        handler: "ForensicRequestHandler",
        url_path: str,
    ) -> None:
        """
        Liefert Plugin-Icons aus static/icons/<file> aus.
        Wird von /_forensic/static/icons/* und /icons/* (via Router) aufgerufen.
        Build 114: IconQuote.svg und weitere Editor.js-Plugin-Icons.
        Beleg: Projektgespraech 2026-05-07
        """
        prefix = "/_forensic/static/icons/"
        if not url_path.startswith(prefix):
            handler.send_response_body(400, b"", content_type="text/plain")
            return

        filename = url_path[len(prefix):]
        if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
            handler.send_response_body(404, b"", content_type="text/plain")
            return

        file_path = _ICONS_DIR / filename
        suffix = Path(filename).suffix.lower()
        mime_type = "image/svg+xml" if suffix == ".svg" else "application/octet-stream"

        try:
            data = file_path.read_bytes()
            logger.debug("Icons-Asset: '%s' ausgeliefert (%d bytes)", filename, len(data))
            handler.send_response_body(200, data, content_type=mime_type)
        except FileNotFoundError:
            handler.send_response_body(404, b"Not found", content_type="text/plain")



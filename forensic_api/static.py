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
# Version: v0.6.254 · Build: 254 · 2026-05-25
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
# Build 663 (Ticket d3f933cd): der Datumspaar-Baustein wird von BEIDEN
# Servern gebraucht (Management-Cockpit und Ermittler-Webserver). Er liegt
# EINMAL im Management-Baum und wird von hier aus MITAUSGELIEFERT, statt
# kopiert zu werden -- zwei Abschriften desselben Verhaltens laufen
# unweigerlich auseinander, und dann verhaelt sich dieselbe Bedienung an
# zwei Stellen verschieden.
#
# DIE KOPPLUNG IST BENANNT: faellt der Management-Baum bei einer Teil-
# auslieferung weg, liefert die Registry den leeren Platzhalter, und die
# Recherche arbeitet ohne Datumskopplung weiter (siehe
# annotation_recherche.js). Es geht dabei nichts verloren -- die Kopplung
# setzt nur eine untere Schranke und schreibt keine Werte.
_MGMT_STATIC_DIR = _BASE_DIR / "management" / "server" / "static"

# Ressourcen-Registry: Pfad -> (Dateiname, MIME-Type, Verzeichnis)
_RESOURCES: dict[str, tuple[str, str, Path]] = {
    "/_forensic/toolbar.js":   ("toolbar.js",   "application/javascript; charset=utf-8", _TOOLBAR_DIR),
    "/_forensic/toolbar.css":  ("toolbar.css",  "text/css; charset=utf-8",               _TOOLBAR_DIR),
    # Build 471 (BS3): Scrollpositions-Wiederherstellung pro Seite (eigene Klasse,
    # Grundregel 10). Wird in shell_handler.py NACH toolbar.js eingebunden.
    "/_forensic/scroll_memory.js": ("scroll_memory.js", "application/javascript; charset=utf-8", _TOOLBAR_DIR),
    # Build 534 (AP-3A): Aufklappbereich "Tatzeitraum" im Annotations-Popup
    # (eigene Klasse, Grundregel 10). Wird in shell_handler.py NACH toolbar.js
    # eingebunden — toolbar.js haengt ihn im Popup ueber window.TatzeitPanel
    # ein und laeuft ohne ihn (mit Warnung) weiter.
    "/_forensic/tatzeit_panel.js": ("tatzeit_panel.js", "application/javascript; charset=utf-8", _TOOLBAR_DIR),
    "/_forensic/userinfo.js":  ("userinfo.js",  "application/javascript; charset=utf-8", _USERINFO_DIR),
    "/_forensic/userinfo.css": ("userinfo.css", "text/css; charset=utf-8",               _USERINFO_DIR),
    # Build 390: Erfassungsmaske Ermittlungsergebnis (Baustelle 4).
    "/_forensic/userinfo_results.js": ("userinfo_results.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # B6 Phase 2: report_editor.js (umbenannt von editor.js, Build 100)
    # Beleg: Bauplan B6 v0.5 §4.1, Projektgespraech 2026-05-06
    "/_forensic/report_editor.js": ("report_editor.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # B6 Build 200: debug_events.js — Event-Tracing (window._uevt), USER vs. WORKFLOW
    # Beleg: Projektgespraech 2026-05-17
    "/_forensic/debug_events.js": ("debug_events.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # B6 Phase 4: Fenster-3-Stylesheet (report.css unveraendert)
    "/_forensic/report.css":   ("report.css",   "text/css; charset=utf-8",               _USERINFO_DIR),
    # Build 576: die Chip-Stile stehen nicht mehr in report.css, sondern in
    # einer eigenen Datei - Modul und Stil bilden ein teilbares Paar, weil
    # die Management-Oberflaeche sie ab Build 577 mitbenutzt.
    #
    # ZWEI STELLEN, NICHT EINE: die Liste in forensic_api/__init__.py sagt,
    # welche Adressen es GEBEN soll; DIESE Tabelle sagt, welche Datei
    # dahinter liegt. Build 493 hat genau diese Falle schon einmal
    # eingefangen ("in _RESOURCES, aber nie dispatcht") und dafuer
    # tests/test_report_assets_routing.py angelegt - der Test hat mich hier
    # sofort erwischt.
    "/_forensic/placeholder_chips.css": ("placeholder_chips.css", "text/css; charset=utf-8", _USERINFO_DIR),
    # B6 Phase 4 (Chip-Rendering): Platzhalter-Parser
    "/_forensic/placeholder_chips.js": ("placeholder_chips.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # Build 389: zentraler Katalog der Formatregeln (config.yaml -> validation.rules).
    # WAR BIS BUILD 492 UNGEROUTET (in report.py eingebunden, aber in KEINER
    # Allowlist -> HTTP 404, window.ValidationRules blieb undefined; die
    # Live-Formatpruefung im Browser lief nie). Build 493: nachregistriert.
    "/_forensic/validation_rules.js": ("validation_rules.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # Build 491: reine Stammvater/Klon-Verknuepfungslogik (window.PlaceholderLinks),
    # vom Wizard (Build 492) benutzt. WAR BIS BUILD 492 UNGEROUTET -> die
    # Stammvater/Klon-Mechanik war im Browser wirkungslos. Build 493: registriert.
    "/_forensic/placeholder_links.js": ("placeholder_links.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # Build 494: m/o-Platzhalterdefinitionen aus templates.placeholders
    # (window.PlaceholderDefs), Grundlage der DB-basierten Feldpruefung im Wizard.
    "/_forensic/placeholder_defs.js": ("placeholder_defs.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # Build 495: case-weite Wiederverwendung von m/o-Werten (window.PlaceholderReuse,
    # placeholder_cache Prefill/Writeback).
    "/_forensic/placeholder_reuse.js": ("placeholder_reuse.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # B6 Phase 5 (Wizard): Platzhalter-Wizard
    "/_forensic/placeholder_wizard.js": ("placeholder_wizard.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # B6 Phase 6 (Modul-Panel): Modul-Auswahl
    "/_forensic/module_panel.js": ("module_panel.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # B6 Phase 7 (Sidebar): Annotationsseitenleiste
    "/_forensic/annotation_sidebar.js": ("annotation_sidebar.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # B6 Phase 8 (Kommentare): Kommentar-Thread
    "/_forensic/comment_thread.js": ("comment_thread.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # Build 382: Bestaetigungsdialog fuer "Zur Abnahme freigeben".
    "/_forensic/submit_dialog.js": ("submit_dialog.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # B6 Paket 5-9 (Layer-Architektur, Build 254): SSELayer, ReportLayer, LockLayer,
    # DocumentLayer, editor_bootstrap. Ladereihenfolge durch Script-Tags in report.py.
    # Beleg: editor_bootstrap.js, Paket 9 Architekturentscheidung Option C
    "/_forensic/sse_layer.js":       ("sse_layer.js",       "application/javascript; charset=utf-8", _USERINFO_DIR),
    "/_forensic/report_layer.js":    ("report_layer.js",    "application/javascript; charset=utf-8", _USERINFO_DIR),
    "/_forensic/lock_layer.js":      ("lock_layer.js",      "application/javascript; charset=utf-8", _USERINFO_DIR),
    "/_forensic/document_layer.js":  ("document_layer.js",  "application/javascript; charset=utf-8", _USERINFO_DIR),
    "/_forensic/editor_bootstrap.js":("editor_bootstrap.js","application/javascript; charset=utf-8", _USERINFO_DIR),
    # Build 428 (B4 Welle 1): Annotationsrecherche im Nutzerinfo-Tab.
    # Reiner Filter-Kern, Zustands-Store, Bearbeiten-Maske, orchestrierende Sicht
    # + eigenes Stylesheet. Beleg: Bauplan_Baustelle4_Annotationsrecherche_v0_1.
    "/_forensic/annotation_filter.js":      ("annotation_filter.js",      "application/javascript; charset=utf-8", _USERINFO_DIR),
    "/_forensic/annotation_store.js":       ("annotation_store.js",       "application/javascript; charset=utf-8", _USERINFO_DIR),
    "/_forensic/annotation_edit_dialog.js": ("annotation_edit_dialog.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # Build 429 (B4 Welle 2): Identitaets-Steckbrief.
    "/_forensic/annotation_identity_profile.js": ("annotation_identity_profile.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    # Build 430 (B4 Welle 3): Zeitstrahl (ECharts wird ueber die Vendor-Route
    # /_forensic/static/vendor/echarts/echarts.min.js ausgeliefert).
    "/_forensic/annotation_timeline.js":    ("annotation_timeline.js",    "application/javascript; charset=utf-8", _USERINFO_DIR),
    # Build 431 (B4 Welle 4): Tag-Netz (Ko-Okkurrenz-Graph, ECharts).
    "/_forensic/annotation_tag_network.js": ("annotation_tag_network.js", "application/javascript; charset=utf-8", _USERINFO_DIR),
    "/_forensic/annotation_recherche.js":   ("annotation_recherche.js",   "application/javascript; charset=utf-8", _USERINFO_DIR),
    "/_forensic/annotation_recherche.css":  ("annotation_recherche.css",  "text/css; charset=utf-8",               _USERINFO_DIR),
    # Build 663 (Ticket d3f933cd): gemeinsamer Datumspaar-Baustein,
    # ausgeliefert aus dem Management-Baum (siehe _MGMT_STATIC_DIR).
    "/_forensic/cockpit_datumspaar.js": ("cockpit_datumspaar.js", "application/javascript; charset=utf-8", _MGMT_STATIC_DIR),
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



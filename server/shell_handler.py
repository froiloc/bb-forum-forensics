# =============================================================================
# server/shell_handler.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Liefert beim ersten Seitenaufruf (Shell-Request) die leere Shell-HTML aus.
#   Der BLOB-Inhalt ist zu diesem Zeitpunkt noch nicht geladen — toolbar.js
#   löst sofort nach dem Laden einen AJAX-Request auf /_forensic/page aus
#   (Two-Phase-Load).
#
# Shell-Struktur:
#   <html>
#     <head>
#       <!-- Aus BLOB extrahiert: title, base, link, style -->
#       <!-- Ergänzt: /_forensic/toolbar.css, /_forensic/toolbar.js -->
#     </head>
#     <body>
#       <div id="forensic-toolbar"></div>
#       <div id="forensic-viewport"><!-- leer, wird per AJAX befüllt --></div>
#     </body>
#   </html>
#
# Sonderfälle:
#   - URL nicht in forensic_db: Shell wird trotzdem ausgeliefert,
#     aber mit HTTP-Header X-Forensic-Status: NOT_IN_SCOPE
#   - html IS NULL (Abruf fehlgeschlagen): Shell wird ausgeliefert,
#     toolbar.js erhält die Information über den AJAX-Response
#
# page_visit wird NICHT hier protokolliert — das geschieht erst wenn
# toolbar.js den BLOB erfolgreich geladen hat (in blob_handler.py).
#
# Abhängigkeiten: server/head_extractor — internes Modul
# Version: v0.1.0 · Build: 021 · 2026-04-15
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING

from core.logger import get_logger
from server.head_extractor import HeadExtractor

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

# Build 190: Cache-Buster via Query-String — Versionsnummer aus build.json.
# Verhindert dass der Browser veraltetes toolbar.js/css aus dem Cache laedt.
def _get_build_nr() -> str:
    import json as _json
    from pathlib import Path as _Path
    try:
        build_file = _Path(__file__).parent.parent / "build.json"
        data = _json.loads(build_file.read_text(encoding="utf-8"))
        return str(data.get("build", "0"))
    except Exception:
        return "0"

_BUILD_NR = _get_build_nr()

# Konstante Shell-Bestandteile
_TOOLBAR_CSS_TAG = f'<link rel="stylesheet" href="/_forensic/toolbar.css?v={_BUILD_NR}">'
_TOOLBAR_JS_TAG  = f'<script src="/_forensic/toolbar.js?v={_BUILD_NR}"></script>'
# Build 086: Tabulator.js wird in userinfo.py eingebunden (eigenes Fenster).
# Beleg: Projektgespräch 2026-05-05 — shell_handler lädt für Hauptfenster, nicht Userinfo-Tab.

_SHELL_BODY = """\
<body>
  <div id="forensic-toolbar"></div>
  <div id="forensic-viewport" class="nojs winter notouch section-viewtopic ltr">
    <!-- Inhalt wird per AJAX nachgeladen durch toolbar.js -->
  </div>
</body>"""


class ShellHandler:
    """
    Liefert die Shell-HTML für den ersten Seitenaufruf.

    Verwendung (durch router.py):
        shell_handler.handle(request_handler, canonical_url)
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
        self._extractor = HeadExtractor()

    def handle(
        self,
        handler: "ForensicRequestHandler",
        canonical_url: str,
    ) -> None:
        """
        Erstellt und sendet die Shell-HTML für die angeforderte URL.

        Args:
            handler:       ForensicRequestHandler-Instanz.
            canonical_url: Normalisierte Forum-URL für den BLOB-Lookup.
        """
        # BLOB-Lookup — nur für <head>-Extraktion, nicht für den Body
        page = self._bundle.forensic.get_page(canonical_url)

        # <head>-Elemente extrahieren (falls Seite vorhanden und html nicht NULL)
        if page is not None and page.html is not None:
            extracted = self._extractor.extract(page.html)
        else:
            # Seite nicht vorhanden oder Abruf fehlgeschlagen →
            # leere ExtractedHead-Instanz (keine CSS, kein title)
            from server.head_extractor import ExtractedHead
            extracted = ExtractedHead()

        # Shell-HTML zusammenbauen
        html = self._build_shell(extracted, canonical_url)
        html_bytes = html.encode("utf-8")

        # HTTP-Status und Zusatz-Header bestimmen
        extra_headers: dict[str, str] = {}
        if page is None:
            # URL nicht im Scope
            status = 404
            extra_headers["X-Forensic-Status"] = "NOT_IN_SCOPE"
            logger.debug("Shell: NOT_IN_SCOPE für '%s'", canonical_url)
        else:
            status = 200
            logger.debug(
                "Shell: ausgeliefert für '%s' (context=%s, fetch_failed=%s)",
                canonical_url, page.scrape_context, page.fetch_failed,
            )

        handler.send_response_body(
            status=status,
            body=html_bytes,
            content_type="text/html; charset=utf-8",
            extra_headers=extra_headers if extra_headers else None,
        )

    def _build_shell(self, extracted, canonical_url: str) -> str:
        """
        Baut die vollständige Shell-HTML aus den extrahierten <head>-Elementen.

        Args:
            extracted:     ExtractedHead-Instanz aus head_extractor.py.
            canonical_url: URL der angeforderten Seite (für data-Attribut).

        Returns:
            Vollständige HTML-Seite als String.
        """
        # Titel: Original-Titel mit forensischem Prefix
        title = extracted.title or canonical_url
        safe_title = (
            title
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

        # Extrahierte <head>-Elemente — ohne CSS, da dieses ausschließlich
        # via _updateHead() in toolbar.js nach dem AJAX-Load eingefügt wird.
        # Würde CSS hier eingebettet, entstünde eine Dopplung: einmal in der
        # Shell-HTML und nochmals nach jedem AJAX-Load.
        head_content = extracted.to_html(include_css=False)

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
{head_content}
{_TOOLBAR_CSS_TAG}
</head>
{_SHELL_BODY}
{_TOOLBAR_JS_TAG}
</html>"""

# =============================================================================
# forensic_api/page.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/page?url=<forum_url>
#   Liefert den BLOB-Inhalt einer Forum-Seite als JSON-Envelope.
#   Dies ist der einzige Auslieferungspfad für BLOB-Inhalte.
#
# Delegiert vollständig an BlobHandler — keine eigene Lookup-Logik.
#
# Version: v0.1.0 · Build: 010 · 2026-04-10
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


class PageEndpoint:
    """Endpunkt /_forensic/page — delegiert an BlobHandler."""

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        self._bundle  = bundle
        self._context = context
        self._config  = config

        from server.blob_handler import BlobHandler
        self._blob_handler = BlobHandler(bundle, context, config)

    def handle(
        self,
        handler: "ForensicRequestHandler",
        params: dict,
    ) -> None:
        """
        Verarbeitet GET /_forensic/page?url=<ziel_url>

        Args:
            handler: ForensicRequestHandler-Instanz.
            params:  Geparste Query-Parameter (dict von Listen).
        """
        values = params.get("url")
        if not values:
            handler.send_response_body(
                400,
                b'{"error": "Parameter \'url\' fehlt"}',
                content_type="application/json; charset=utf-8",
            )
            return

        target_url = values[0]

        # Fragment aus URL extrahieren (Browser sendet kein Fragment,
        # aber /_forensic/page wird auch intern aufgerufen)
        parsed    = urllib.parse.urlparse(target_url)
        fragment  = parsed.fragment or None
        clean_url = urllib.parse.urlunparse(parsed._replace(fragment=""))

        logger.debug("/_forensic/page: url='%s' fragment=%s", clean_url, fragment)

        self._blob_handler.handle_with_fragment(handler, clean_url, fragment)

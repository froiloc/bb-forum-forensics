# =============================================================================
# forensic_api/page.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/page?url=<forum_url>[&original_method=POST]
#   Liefert den BLOB-Inhalt einer Forum-Seite als JSON-Envelope.
#   Dies ist der einzige Auslieferungspfad für BLOB-Inhalte.
#
#   Delegiert vollständig an BlobHandler — keine eigene Lookup-Logik.
#
# original_method-Parameter:
#   Die Toolbar sendet Forum-Requests immer als HTTP-POST an /_forensic/page
#   (wegen AJAX-API-Design). Damit der Server weiß, welche HTTP-Methode der
#   Originalserver für diesen Request verwendet hat, übergibt die Toolbar
#   original_method als zusätzlichen Parameter.
#
#   Werte:
#     original_method=GET  (Default, kann weggelassen werden)
#       → Normaler GET-Request, liefert Standardseite oder Abstimmungsformular.
#     original_method=POST
#       → Form-Submit (z.B. Poll-Abstimmung), liefert Abstimmungsergebnis-BLOB.
#
#   Beleg: Projektgespräch 2026-04-19.
#
# Version: v0.1.0 · Build: 042 · 2026-04-19
# Änderungen Build 042:
#   - original_method-Parameter aus Query-String lesen.
#   - Wird als method an BlobHandler.handle_with_fragment() übergeben.
#   - Default 'GET' wenn original_method fehlt oder leer ist.
#   Beleg: Projektgespräch 2026-04-19.
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
        Verarbeitet GET oder POST /_forensic/page?url=<ziel_url>[&original_method=POST]

        Args:
            handler: ForensicRequestHandler-Instanz.
            params:  Geparste Query-Parameter (dict von Listen).

        original_method-Auflösung:
            1. Aus Query-Parameter 'original_method' lesen (Toolbar setzt diesen
               bei Form-Submits, z.B. original_method=POST für Polls).
            2. Fehlender oder leerer Wert → Default 'GET'.
            3. Wert wird upper()-normalisiert ('post' → 'POST').
            Beleg: Projektgespräch 2026-04-19.
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

        # original_method lesen — Default 'GET'.
        # Die Toolbar übergibt 'POST' nur wenn es sich um ein Form-Submit handelt
        # (z.B. Poll-Abstimmung). Alle anderen Requests sind 'GET'.
        # Beleg: Projektgespräch 2026-04-19.
        method_values = params.get("original_method")
        original_method = (method_values[0].upper()
                           if method_values and method_values[0]
                           else "GET")

        # Nur GET und POST sind gültige original_method-Werte.
        # Ungültige Werte → Fallback auf GET (forensische Robustheit).
        if original_method not in ("GET", "POST"):
            logger.warning(
                "/_forensic/page: ungültiger original_method='%s' → GET.",
                original_method,
            )
            original_method = "GET"

        # Fragment aus URL extrahieren (Browser sendet kein Fragment,
        # aber /_forensic/page wird auch intern aufgerufen)
        parsed    = urllib.parse.urlparse(target_url)
        fragment  = parsed.fragment or None
        clean_url = urllib.parse.urlunparse(parsed._replace(fragment=""))

        logger.debug(
            "/_forensic/page: url='%s' fragment=%s original_method=%s",
            clean_url, fragment, original_method,
        )

        self._blob_handler.handle_with_fragment(
            handler, clean_url, fragment,
            original_method=original_method,
        )

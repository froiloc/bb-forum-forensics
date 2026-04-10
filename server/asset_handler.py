# =============================================================================
# server/asset_handler.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Liefert statische Assets (CSS, Bilder, Smilies) aus default_db aus.
#   Wird von router.py für URLs aufgerufen, die einem Asset-Präfix
#   aus config.yaml entsprechen.
#
# Verhalten:
#   Asset bekannt und data vorhanden → HTTP 200 mit korrektem MIME-Type
#   Asset bekannt aber data=NULL     → HTTP 200 mit leerem Body (kein Fehler)
#   Asset unbekannt                  → HTTP 404 (kein X-Forensic-Status,
#                                       da Assets keine Beweismittel sind)
#
# Forensische Relevanz:
#   Statische Assets sind nutzerneutral. Ein fehlendes Asset ist kein
#   forensischer Verlust — es beeinflusst nur die visuelle Darstellung.
#   NOT_IN_SCOPE gilt ausschließlich für Forum-Seiten, nicht für Assets.
#
# Abhängigkeiten: keine externen Abhängigkeiten
# Version: v0.1.0 · Build: 008 · 2026-04-10
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle

logger = get_logger(__name__)


class AssetHandler:
    """
    Liefert statische Assets aus default_db aus.

    Verwendung (durch router.py):
        asset_handler.handle(request_handler, url_path)
    """

    def __init__(self, bundle: "DatabaseBundle") -> None:
        self._bundle = bundle

    def handle(
        self,
        handler: "ForensicRequestHandler",
        url_path: str,
    ) -> None:
        """
        Sucht das Asset in default_db und liefert es aus.

        Args:
            handler:  ForensicRequestHandler-Instanz.
            url_path: URL-Pfad des Assets (ohne Query-String).
        """
        asset = self._bundle.default.get_asset(url_path)

        if asset is None:
            logger.debug("Asset nicht in default_db: '%s'", url_path)
            handler.send_response_body(404, b"")
            return

        data      = asset.data or b""
        mime_type = asset.mime_type

        logger.debug(
            "Asset ausgeliefert: '%s' (%s, %d bytes)",
            url_path, mime_type, len(data),
        )
        handler.send_response_body(
            status=200,
            body=data,
            content_type=mime_type,
        )

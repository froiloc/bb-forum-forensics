# =============================================================================
# forensic_api/fileasset.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkt GET /_forensic/fileasset?url=<encoded_full_url>
#
#   Liefert ein Asset aus assets_<uid>.db anhand seiner vollständigen
#   Original-URL (z.B. http://filer.onion/images/.../hash).
#
#   Wird ausschließlich vom Browser aufgerufen wenn blob_handler.py beim
#   Ausliefern von HTML/CSS die Original-URLs ersetzt hat:
#     http://filer.onion/img/x.jpg
#     → /_forensic/fileasset?url=http%3A%2F%2Ffiler.onion%2Fimg%2Fx.jpg
#
#   Der Browser kennt die Original-URL nicht mehr — er sieht nur den
#   lokalen Proxy-Pfad. Die forensische Integrität der gespeicherten
#   BLOBs bleibt unberührt, da das Rewriting nur bei der Auslieferung
#   stattfindet.
#
# Lookup:
#   assets_<uid>.db via AssetsDb.get_asset_by_full_url(url)
#   Kein Fallback auf default.db — Filehoster-Assets sind nutzerspezifisch.
#   Kein Live-Fetch — nur was in der DB ist wird ausgeliefert.
#
# Fehlerverhalten:
#   Kein url-Parameter     → HTTP 400
#   URL nicht in DB        → HTTP 404
#   assets_db nicht verfügbar → HTTP 404
#
# Forensische Relevanz:
#   Kein Schreiben, kein Netzwerkzugriff. READ-ONLY.
#   Beleg: Projektgespräch 2026-05-31.
#
# Version: v0.1.0 · Build: 272 · 2026-05-31
#
# Changelog Build 272 (2026-05-31):
#   - urllib.parse.unquote() auf den url-Parameter entfernt.
#     parse_qs() dekodiert den Query-Parameter bereits einmal.
#     Ein zweites unquote() dekodiert zu viel: %252F → %2F statt %252F,
#     der resultierende String stimmt nicht mit der DB-URL überein.
#     Beleg: URL-Roundtrip-Analyse 2026-05-31.
# =============================================================================

from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle

logger = get_logger(__name__)


class FileassetEndpoint:
    """
    Endpunkt /_forensic/fileasset?url=<encoded_full_url>

    Liefert Assets aus assets_<uid>.db anhand ihrer vollständigen
    Original-URL (nicht dem lokalen Pfad).
    Beleg: Projektgespräch 2026-05-31.
    """

    def __init__(self, bundle: "DatabaseBundle") -> None:
        self._bundle = bundle

    def handle(
        self,
        handler: "ForensicRequestHandler",
        params: dict,
    ) -> None:
        """
        Verarbeitet GET /_forensic/fileasset?url=<encoded>.

        Args:
            handler: ForensicRequestHandler-Instanz.
            params:  URL-Query-Parameter aus urllib.parse.parse_qs.
                     Erwartet: url (vollständige URL, URL-encoded).
        """
        # url-Parameter dekodieren
        raw = (params.get("url") or [None])[0]
        if not raw:
            logger.debug("/_forensic/fileasset: kein url-Parameter")
            handler.send_response_body(
                400, b"url-Parameter fehlt",
                content_type="text/plain; charset=utf-8",
            )
            return

        # url-Parameter: parse_qs() hat ihn bereits einmal dekodiert.
        # Kein weiteres unquote() — das würde eine Kodierungsebene zu viel
        # entfernen und den String von der DB-URL abweichen lassen.
        # Beispiel: DB hat %252F; nach parse_qs: %252F; nach extra unquote: %2F → Mismatch.
        # Beleg: URL-Roundtrip-Analyse 2026-05-31.
        full_url = raw
        logger.debug("/_forensic/fileasset: Lookup '%s'", full_url[:80])

        # Lookup in assets_<uid>.db per vollständiger URL
        asset = self._bundle.assets.get_asset_by_full_url(full_url)
        if asset is None:
            logger.debug("/_forensic/fileasset: nicht in assets_db: '%s'", full_url[:80])
            handler.send_response_body(404, b"")
            return

        data = asset.data or b""
        mime = asset.mime_type or "application/octet-stream"

        logger.debug(
            "/_forensic/fileasset: ausgeliefert '%s' (%s, %d bytes)",
            full_url[:60], mime, len(data),
        )
        handler.send_response_body(
            200, data,
            content_type=mime,
            extra_headers={"Cache-Control": "max-age=3600, immutable"},
        )

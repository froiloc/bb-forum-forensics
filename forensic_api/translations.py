# =============================================================================
# forensic_api/translations.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/translations?topic_id=<topic_id> (GET)
#   Liefert die post_ids eines Topics, fuer die eine fertige KI-Uebersetzung
#   vorliegt. Die Toolbar ruft dies einmal je viewtopic-Seite auf (parallel
#   zum Seiten-Fetch), cached das Ergebnis als Set und injiziert nur dort eine
#   Flaggen-Schaltflaeche, wo die post_id enthalten ist.
#
#   Warum topic-basiert (nicht post_id-Liste): Die Toolbar kennt topic_id direkt
#   aus der URL (viewtopic.php?id=<topic_id>) und muss nicht auf das Post-DOM
#   warten (Viewport wird asynchron befuellt). Beleg: Bauplan Build 329 §2/§4.2.
#
# Response (200):
#   { "topic_id": 69192, "post_ids": [706037, 706040], "count": 2, "status": "ok" }
#
# Fehlerfaelle:
#   - fehlender/ungueltiger topic_id  -> 400 { "error": ..., "status": "error" }
#   - trdb nicht angebunden           -> 200 leere Liste (kein Fehler; die DB
#                                        wird extern erst spaeter befuellt)
#
# Version: v0.7.329 · Build: 329 · 2026-07-07
# =============================================================================

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)


class TranslationsEndpoint:
    """
    Endpunkt /_forensic/translations (GET).

    Liest ausschliesslich aus trdb.translations (READ-ONLY, global geteilt).
    Beleg: Bauplan Build 329 §3.1
    """

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        self._bundle = bundle
        self._context = context

    def handle(
        self,
        handler: "ForensicRequestHandler",
        params: dict,
    ) -> None:
        """Verarbeitet GET /_forensic/translations?topic_id=<topic_id>."""
        raw_vals = params.get("topic_id", [])
        raw = raw_vals[0] if raw_vals else ""

        try:
            topic_id = int(str(raw).strip())
        except (ValueError, TypeError):
            topic_id = -1

        if topic_id <= 0:
            body = json.dumps(
                {"error": "Ungueltiger oder fehlender topic_id",
                 "status": "error"},
                ensure_ascii=False,
            ).encode("utf-8")
            handler.send_response_body(
                400, body, content_type="application/json; charset=utf-8"
            )
            return

        try:
            post_ids = self._bundle.translations.list_translated_post_ids(topic_id)
        except Exception as exc:  # defensiv — niemals 500 ohne Log (GR1)
            logger.error(
                "TranslationsEndpoint: list_translated_post_ids(%r) Fehler: %s",
                topic_id, exc,
            )
            body = json.dumps(
                {"error": "Interner Fehler bei der Uebersetzungs-Abfrage",
                 "status": "error"},
                ensure_ascii=False,
            ).encode("utf-8")
            handler.send_response_body(
                500, body, content_type="application/json; charset=utf-8"
            )
            return

        logger.debug(
            "/_forensic/translations: topic_id=%d -> %d uebersetzte post_ids.",
            topic_id, len(post_ids),
        )
        body_out = json.dumps(
            {"topic_id": topic_id, "post_ids": post_ids,
             "count": len(post_ids), "status": "ok"},
            ensure_ascii=False,
        ).encode("utf-8")
        handler.send_response_body(
            200, body_out, content_type="application/json; charset=utf-8"
        )

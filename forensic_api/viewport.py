# =============================================================================
# forensic_api/viewport.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/viewport (POST)
#   Nimmt Viewport-Events vom IntersectionObserver in toolbar.js entgegen
#   und speichert sie in evidence_db.
#
# Erwarteter Request-Body (JSON):
#   {
#     "page_url": "/forum/viewtopic.php?id=42",
#     "events": [
#       {
#         "element_id": "p12345",
#         "visible_ms": 3500,
#         "ts_enter":   1700000000000,
#         "ts_leave":   1700000003500
#       },
#       ...
#     ]
#   }
#
# Response:
#   200 OK:  {"saved": <anzahl>, "status": "ok"}
#   400 Bad: {"error": "<Fehlermeldung>"}
#
# Version: v0.1.0 · Build: 010 · 2026-04-10
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


class ViewportEndpoint:
    """Endpunkt /_forensic/viewport — speichert Viewport-Events."""

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        self._bundle  = bundle
        self._context = context

    def handle(
        self,
        handler: "ForensicRequestHandler",
        body: bytes,
    ) -> None:
        """
        Verarbeitet POST /_forensic/viewport

        Args:
            handler: ForensicRequestHandler-Instanz.
            body:    Request-Body als bytes (JSON).
        """
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, ValueError) as exc:
            self._error(handler, f"Ungültiges JSON: {exc}")
            return

        page_url = data.get("page_url", "").strip()
        events   = data.get("events", [])

        if not page_url:
            self._error(handler, "Feld 'page_url' fehlt oder leer")
            return
        if not isinstance(events, list):
            self._error(handler, "Feld 'events' muss eine Liste sein")
            return
        if not events:
            # Leere Batch — kein Fehler, aber auch nichts zu speichern
            body_out = json.dumps({"saved": 0, "status": "ok"}).encode("utf-8")
            handler.send_response_body(
                200, body_out, content_type="application/json; charset=utf-8"
            )
            return

        # page_url in jeden Event eintragen (kommt aus dem äußeren Objekt)
        enriched = []
        for ev in events:
            if isinstance(ev, dict):
                ev_copy = dict(ev)
                ev_copy["page_url"] = page_url
                enriched.append(ev_copy)

        try:
            saved = self._bundle.evidence.save_viewport_batch(
                enriched,
                investigator_id=self._context.investigator_id,
            )
        except Exception as exc:
            logger.error("Viewport-Batch konnte nicht gespeichert werden: %s", exc)
            self._error(handler, "Interner Fehler beim Speichern")
            return

        logger.debug(
            "/_forensic/viewport: %d Events für '%s' gespeichert",
            saved, page_url,
        )

        body_out = json.dumps(
            {"saved": saved, "status": "ok"}, ensure_ascii=False
        ).encode("utf-8")
        handler.send_response_body(
            200, body_out, content_type="application/json; charset=utf-8"
        )

    @staticmethod
    def _error(handler: "ForensicRequestHandler", message: str) -> None:
        body = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(
            400, body, content_type="application/json; charset=utf-8"
        )

# =============================================================================
# forensic_api/sync_incoming.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 3: Toolbar
# =============================================================================
# Zweck:
#   Endpunkt POST /_forensic/sync_incoming
#   Manueller Trigger fuer CrossAnnotationIntegrator.run_once().
#
# Response (JSON):
#   { "status": "ok", "integrated": N, "skipped": N, "errors": N }
#
# Beleg: Projektgespraech 2026-05-12 — Bug 2.78 (BS3).
# Version: v0.6.182 · Build: 182 · 2026-05-12
# =============================================================================

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from core.logger import get_logger
from forensic_api.cross_annotation_integrator import CrossAnnotationIntegrator

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)


class SyncIncomingEndpoint:
    """
    POST /_forensic/sync_incoming — Manueller Integrations-Trigger.
    Beleg: Projektgespraech 2026-05-12 — Bug 2.78 (BS3).
    """

    def __init__(
        self,
        bundle:  "DatabaseBundle",
        context: "ResolvedContext",
        config:  "ConfigLoader",
    ) -> None:
        self._bundle  = bundle
        self._context = context
        self._config  = config

    def handle_sync(self, handler: "ForensicRequestHandler") -> None:
        """POST /_forensic/sync_incoming — fuehrt Integrationsdurchlauf aus."""
        integrator = CrossAnnotationIntegrator(self._bundle, self._context, self._config)
        try:
            stats = integrator.run_once()
        except Exception as exc:
            logger.error("sync_incoming: unerwarteter Fehler: %s", exc)
            body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
            handler.send_response_body(500, body,
                                       content_type="application/json; charset=utf-8")
            return

        body = json.dumps(
            {"status": "ok", **stats}, ensure_ascii=False
        ).encode("utf-8")
        handler.send_response_body(200, body,
                                   content_type="application/json; charset=utf-8")
        logger.info(
            "sync_incoming: integriert=%d, uebersprungen=%d, Fehler=%d",
            stats.get("integrated", 0),
            stats.get("skipped", 0),
            stats.get("errors", 0),
        )

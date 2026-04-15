# =============================================================================
# forensic_api/status.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/status (GET)
#   Liefert den aktuellen Serverstatus als JSON.
#   Wird von toolbar.js beim Start geladen und für Diagnosezwecke verwendet.
#
# Response (JSON):
#   {
#     "mode":             "job|cli|support",
#     "user_id":          42,
#     "username":         "beschuldigter42",
#     "investigator_id":  3,
#     "page_count":       1234,
#     "annotation_count": 17,
#     "scrape_context_warning": false,
#     "ts":               1700000000,
#     "version":          "v0.1.0-build010"
#   }
#
# Version: v0.1.0 · Build: 020 · 2026-04-15
# =============================================================================

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

SERVER_VERSION = "v0.1.0-build010"


class StatusEndpoint:
    """Endpunkt /_forensic/status — liefert Serverstatus als JSON."""

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        self._bundle  = bundle
        self._context = context

    def handle(self, handler: "ForensicRequestHandler") -> None:
        """Verarbeitet GET /_forensic/status"""
        try:
            page_count       = self._bundle.forensic.page_count()
            annotation_count = self._bundle.evidence.annotation_count()
        except Exception as exc:
            logger.warning("Statusabfrage: DB-Zugriff fehlgeschlagen: %s", exc)
            page_count       = -1
            annotation_count = -1

        status = {
            "mode":              self._context.mode,
            "user_id":           self._context.user_id,
            "username":          self._context.username,
            "investigator_id":   self._context.investigator_id,
            "page_count":        page_count,
            "annotation_count":  annotation_count,
            "forum_hostname":    self._bundle.forensic.get_meta("domainname") or "",
            "ts":                int(time.time()),
            "version":           SERVER_VERSION,
        }

        body = json.dumps(status, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(
            200, body, content_type="application/json; charset=utf-8"
        )
        logger.debug("/_forensic/status ausgeliefert")

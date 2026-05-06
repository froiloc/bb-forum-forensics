# =============================================================================
# forensic_api/investigator_me.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# =============================================================================
# Zweck:
#   Endpunkt GET /_forensic/investigator/me
#
#   Liefert die Profildaten des aktuell angemeldeten Ermittlers aus
#   coordinator.db. Wird von report.js benoetigt um is_supervisor
#   (= Chef-Ermittlerin) zu ermitteln.
#
# Antwort-Schema:
#   {
#     "system_username": "h012345",
#     "display_name":    "Max Mustermann",
#     "is_investigator": true,
#     "is_supervisor":   false,   <- "Chef-Ermittlerin" im Bauplan B6
#     "is_support":      false
#   }
#
# Bei unbekanntem Nutzer (investigator_id=None oder nicht in DB):
#   { "system_username": "...", "is_supervisor": false, ... }
#   HTTP 200 — kein 404 damit das Frontend stabil weiterlaeuft.
#
# Beleg: Bauplan B6 v0.3 §4.3 (Freigabe-Workflow), Build 096
# Version: v0.6.096 · Build: 096 · 2026-05-05
# =============================================================================

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)


def _json(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


class InvestigatorMeEndpoint:
    """
    GET /_forensic/investigator/me
    Liefert Profildaten des angemeldeten Ermittlers aus coordinator.db.
    Beleg: Bauplan B6 v0.3 §4.3, Build 096
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

    def handle_get(self, handler: "ForensicRequestHandler") -> None:
        """GET /_forensic/investigator/me"""
        system_username = os.environ.get("USERNAME") or os.environ.get("USER") or ""

        # Fallback-Antwort fuer den Fall dass coordinator.db nicht verfuegbar
        fallback = {
            "system_username": system_username,
            "display_name":    system_username,
            "is_investigator": True,
            "is_supervisor":   False,
            "is_support":      False,
        }

        try:
            cdb = self._bundle.coordinator
            rec = cdb.get_investigator(system_username) if cdb else None
            if rec is None:
                logger.debug(
                    "investigator/me: '%s' nicht in coordinator.db — Fallback",
                    system_username,
                )
                handler.send_response_body(
                    200, _json(fallback),
                    content_type="application/json; charset=utf-8",
                )
                return

            handler.send_response_body(
                200,
                _json({
                    "system_username": rec.system_username,
                    "display_name":    rec.display_name,
                    "is_investigator": rec.is_investigator,
                    "is_supervisor":   rec.is_supervisor,
                    "is_support":      rec.is_support,
                }),
                content_type="application/json; charset=utf-8",
            )
            logger.debug(
                "investigator/me: '%s' is_supervisor=%s",
                rec.system_username, rec.is_supervisor,
            )

        except Exception as exc:
            logger.warning(
                "investigator/me: coordinator.db-Fehler ('%s') — Fallback", exc
            )
            handler.send_response_body(
                200, _json(fallback),
                content_type="application/json; charset=utf-8",
            )

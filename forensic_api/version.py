# =============================================================================
# forensic_api/version.py
# IT-Forensisches Ermittlungswerkzeug — Version-Endpunkt
# =============================================================================
# Zweck:
#   GET /_forensic/version — liefert Build-Info als JSON.
#   Wird von report_editor.js beim Start abgefragt und als window._buildnr
#   sowie window._version gesetzt.
#
# Build 174: Erstimplementierung.
# Beleg: Projektgespräch 2026-05-11
# =============================================================================

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler


class VersionEndpoint:
    """
    Endpunkt GET /_forensic/version — Build-Info als JSON.
    Beleg: Projektgespräch 2026-05-11
    """

    def __init__(self, build_info) -> None:
        self._build_info = build_info

    def handle(self, handler: "ForensicRequestHandler") -> None:
        body = json.dumps(self._build_info.as_dict()).encode("utf-8")
        handler.send_response_body(
            200, body,
            content_type="application/json; charset=utf-8",
            extra_headers={"Cache-Control": "no-store"},
        )

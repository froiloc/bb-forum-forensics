# =============================================================================
# forensic_api/templates_ep.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# =============================================================================
# Zweck:
#   Endpunkte fuer Berichtsmodul-Abfragen (lesend).
#
#   GET /_forensic/templates
#     Liefert gefilterte Modulliste fuer das Modul-Auswahl-Panel (§4.4).
#     Query-Parameter: ?role=body&topic=Identifikation&search=...
#     Zusaetzlich: ?topics=1 liefert alle vorhandenen topic-Werte.
#
#   GET /_forensic/templates/<id>
#     Liefert ein einzelnes Modul mit vollstaendigem Body (fuer Vorschau).
#
# Beleg: Bauplan B6 v0.3 §4.4, §5, Ausdefinitionsgespraech 2026-05-05
# Version: v0.6.089 · Build: 089 · 2026-05-05
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


def _json_ok(data) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def _json_err(msg: str, code: str = "ERROR") -> bytes:
    return json.dumps({"error": msg, "code": code}, ensure_ascii=False).encode("utf-8")


class TemplatesListEndpoint:
    """
    Lesender Zugriff auf Berichtsmodule aus templates.db.
    Beleg: Bauplan B6 v0.3 §4.4, §5
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

    def handle_get(
        self,
        handler: "ForensicRequestHandler",
        url_path: str,
        params: dict,
    ) -> None:
        """
        Routing fuer GET /_forensic/templates und /_forensic/templates/<id>.
        """
        if url_path == "/_forensic/templates":
            self._handle_list(handler, params)
        elif url_path.startswith("/_forensic/templates/"):
            id_str = url_path[len("/_forensic/templates/"):]
            self._handle_single(handler, id_str)
        else:
            handler.send_response_body(
                404, _json_err("Endpunkt nicht bekannt."),
                content_type="application/json; charset=utf-8",
            )

    def _handle_list(
        self,
        handler: "ForensicRequestHandler",
        params: dict,
    ) -> None:
        """GET /_forensic/templates — Modulliste mit optionalem Filter."""
        # Sondermodus: ?topics=1 liefert nur die topic-Werte
        if params.get("topics", [None])[0] == "1":
            topics = self._bundle.templates.list_topics()
            handler.send_response_body(
                200, _json_ok({"topics": topics}),
                content_type="application/json; charset=utf-8",
            )
            return

        role   = params.get("role",   [None])[0]
        topic  = params.get("topic",  [None])[0]
        search = params.get("search", [None])[0]

        modules = self._bundle.templates.list_modules(
            role=role, topic=topic, search=search
        )

        result = [
            {
                "id":          m.id,
                "title":       m.title,
                "description": m.description,
                "role":        m.role,
                "topic":       m.topic,
                "sort_order":  m.sort_order,
                # body wird im Listenview nicht uebertragen (zu gross)
                # Fuer den Body: GET /_forensic/templates/<id>
            }
            for m in modules
        ]

        handler.send_response_body(
            200, _json_ok(result),
            content_type="application/json; charset=utf-8",
        )

    def _handle_single(
        self,
        handler: "ForensicRequestHandler",
        id_str: str,
    ) -> None:
        """GET /_forensic/templates/<id> — Einzelmodul mit Body."""
        try:
            module_id = int(id_str)
        except ValueError:
            handler.send_response_body(
                400, _json_err(f"Ungueltiger Modul-ID-Wert: '{id_str}'"),
                content_type="application/json; charset=utf-8",
            )
            return

        m = self._bundle.templates.get_module(module_id)
        if m is None:
            handler.send_response_body(
                404,
                _json_err(f"Modul {module_id} nicht gefunden.", "NOT_FOUND"),
                content_type="application/json; charset=utf-8",
            )
            return

        handler.send_response_body(
            200,
            _json_ok({
                "id":          m.id,
                "title":       m.title,
                "description": m.description,
                "role":        m.role,
                "topic":       m.topic,
                "body":        m.body,
                "sort_order":  m.sort_order,
            }),
            content_type="application/json; charset=utf-8",
        )

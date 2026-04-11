# =============================================================================
# forensic_api/annotate.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/annotate (POST)
#   Nimmt Annotationen vom Werkzeugbalken entgegen und speichert sie
#   in evidence_db.
#
# Erwarteter Request-Body (JSON):
#   {
#     "page_url":    "/forum/viewtopic.php?id=42",
#     "element_id":  "p12345",          (optional)
#     "category":    "CAT_PERSON",
#     "text":        "Erwähnt Vorname Klaus"
#   }
#
# Response:
#   200 OK:  {"id": <annotation_id>, "status": "ok"}
#   400 Bad: {"error": "<Fehlermeldung>"}
#
# Version: v0.1.0 · Build: 010 · 2026-04-10
# =============================================================================

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from core.logger import get_logger
from db.evidence_db import VALID_CATEGORIES, EvidenceDbError

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)


class AnnotateEndpoint:
    """Endpunkt /_forensic/annotate — speichert Annotationen in evidence_db."""

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
        Verarbeitet POST /_forensic/annotate

        Args:
            handler: ForensicRequestHandler-Instanz.
            body:    Request-Body als bytes (JSON).
        """
        # JSON parsen
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, ValueError) as exc:
            self._error(handler, f"Ungültiges JSON: {exc}")
            return

        # Pflichtfelder prüfen
        page_url = data.get("page_url", "").strip()
        category = data.get("category", "").strip()
        text     = data.get("text", "")

        if not page_url:
            self._error(handler, "Feld 'page_url' fehlt oder leer")
            return
        if not category:
            self._error(handler, "Feld 'category' fehlt oder leer")
            return
        if category not in VALID_CATEGORIES:
            self._error(
                handler,
                f"Ungültige Kategorie '{category}'. "
                f"Zulässig: {sorted(VALID_CATEGORIES)}"
            )
            return

        element_id = data.get("element_id") or None

        # Annotation speichern
        try:
            annotation_id = self._bundle.evidence.save_annotation(
                page_url=page_url,
                category=category,
                text=str(text),
                element_id=element_id,
                investigator_id=self._context.investigator_id,
            )
        except EvidenceDbError as exc:
            self._error(handler, str(exc))
            return
        except Exception as exc:
            logger.error("Annotation konnte nicht gespeichert werden: %s", exc)
            self._error(handler, "Interner Fehler beim Speichern")
            return

        logger.info(
            "Annotation gespeichert: id=%d, page='%s', cat=%s, element=%s",
            annotation_id, page_url, category, element_id,
        )

        body_out = json.dumps(
            {"id": annotation_id, "status": "ok"}, ensure_ascii=False
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

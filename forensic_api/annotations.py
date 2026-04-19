# =============================================================================
# forensic_api/annotations.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 3: Forensischer Werkzeugbalken
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/annotations (GET)
#   Liefert alle Annotationen für eine bestimmte URL aus evidence_db.
#   Wird von toolbar.js nach dem BLOB-Load aufgerufen, um gespeicherte
#   Annotationen wiederherzustellen (§11.1 Bauplan Baustelle 3).
#
# Request:
#   GET /_forensic/annotations?url=<kanonische_url>
#
# Response (200 OK):
#   {
#     "annotations": [
#       {
#         "id": 42,
#         "pageUrl": "/forum/viewtopic.php?id=123",
#         "category": "CAT_PERSON",
#         "text": "Ermittlernotiz",
#         "tags": ["pgp", "username"],
#         "elementId": "p4567",
#         "selection": {
#           "xpathStart": "...", "offsetStart": 14,
#           "xpathEnd": "...",   "offsetEnd": 32,
#           "textContent": "BirnenKenner99"
#         },
#         "postId": null,
#         "localId": "uuid-v4",
#         "createdAt": 1744300000000,
#         "createdBy": "h012345",
#         "syncState": "synced"
#       }
#     ],
#     "status": "ok"
#   }
#
# Response (400):  {"error": "Feld 'url' fehlt"}
#
# Neue Datei — Baustelle 3, erste Server-Erweiterung (§11.1 Bauplan).
# Version: v0.1.0 · Build: 001 · 2026-04-13
# =============================================================================

from __future__ import annotations

import json
import urllib.parse
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)


class AnnotationsEndpoint:
    """Endpunkt /_forensic/annotations — liefert Annotationen für eine URL."""

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
        params: dict,
    ) -> None:
        """
        Verarbeitet GET /_forensic/annotations[?url=<url>]

        Ohne url-Parameter: alle Annotationen des Benutzers (fuer
        die Annotations-Sidebar in editor.js, AP-E4).
        Mit url-Parameter: nur Annotationen zur angegebenen Seite.

        Args:
            handler: ForensicRequestHandler-Instanz.
            params:  URL-Query-Parameter (aus urllib.parse.parse_qs).

        Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-19
        """
        # url-Parameter extrahieren — optional (AP-E4 Bugfix)
        url_values = params.get("url", [])
        page_url   = url_values[0].strip() if url_values else None

        # Annotationen aus DB laden
        try:
            if page_url:
                records = self._bundle.evidence.get_annotations(page_url)
            else:
                # Alle Annotationen — fuer editor.js Sidebar
                records = self._bundle.evidence.get_all_annotations()
        except Exception as exc:
            logger.error("Annotationen konnten nicht geladen werden: %s", exc)
            self._error(handler, "Interner Fehler beim Laden der Annotationen", status=500)
            return

        # In JS-kompatibles Format umwandeln (camelCase, Timestamps in ms)
        annotations_out = []
        for rec in records:
            # selection_json deserialisieren (oder None)
            selection = None
            if rec.selection_json:
                try:
                    selection = json.loads(rec.selection_json)
                except (json.JSONDecodeError, ValueError):
                    logger.warning(
                        "Annotation id=%d: selection_json ungültig, wird als null geliefert",
                        rec.id,
                    )

            # tags_json deserialisieren (oder leere Liste)
            tags = []
            if rec.tags_json:
                try:
                    tags = json.loads(rec.tags_json)
                    if not isinstance(tags, list):
                        tags = []
                except (json.JSONDecodeError, ValueError):
                    logger.warning(
                        "Annotation id=%d: tags_json ungültig, wird als [] geliefert",
                        rec.id,
                    )

            annotations_out.append({
                "id":        rec.id,
                "pageUrl":   rec.page_url,
                "category":  rec.category,
                "text":      rec.text,
                "tags":      tags,
                "elementId": rec.element_id,
                "selection": selection,
                # post_id: ganzer Post markiert (kein Textbereich)
                "postId":    rec.post_id,
                "localId":   rec.local_id,
                # ts in DB ist Sekunden, JS erwartet Millisekunden
                "createdAt": rec.ts * 1000,
                "createdBy": rec.created_by,
                # Alle aus DB geladenen Annotationen gelten als synced
                "syncState": "synced",
            })

        logger.debug(
            "Annotationen geliefert: url='%s', count=%d",
            page_url, len(annotations_out),
        )

        body_out = json.dumps(
            {"annotations": annotations_out, "status": "ok"},
            ensure_ascii=False,
        ).encode("utf-8")
        handler.send_response_body(
            200, body_out, content_type="application/json; charset=utf-8"
        )

    @staticmethod
    def _error(
        handler: "ForensicRequestHandler",
        message: str,
        status: int = 400,
    ) -> None:
        body = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(
            status, body, content_type="application/json; charset=utf-8"
        )

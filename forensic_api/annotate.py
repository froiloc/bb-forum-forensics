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
#     "page_url":      "/forum/viewtopic.php?id=42",   (Pflicht)
#     "category":      "CAT_PERSON",                   (Pflicht)
#     "text":          "Erwähnt Vorname Klaus",         (optional, Default "")
#     "element_id":    "p12345",                        (optional)
#     "local_id":      "uuid-v4-string",                (optional, Browser-UUID)
#     "post_id":       12345,                           (optional, Post-Markierung)
#     "tags":          ["pgp", "username"],             (optional, Array)
#     "selection": {                                    (optional, Textmarkierung)
#       "xpathStart":  "...",
#       "offsetStart": 14,
#       "xpathEnd":    "...",
#       "offsetEnd":   32,
#       "textContent": "BirnenKenner99"
#     }
#   }
#
# Response:
#   200 OK:  {"id": <annotation_id>, "status": "ok"}
#   400 Bad: {"error": "<Fehlermeldung>"}
#
# Änderungen gegenüber Build 010 (Baustelle 3 — §11.2 Bauplan):
#   - Neue optionale Felder: selection (XPath-Objekt), tags (Array),
#     local_id (Browser-UUID), post_id (Post-Markierung).
#   - selection wird als JSON-String in selection_json gespeichert.
#   - tags wird als JSON-Array-String in tags_json gespeichert.
#   - created_by wird aus dem Kontext (context.username) befüllt.
#
# Version: v0.1.0 · Build: 011 · 2026-04-13
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
        local_id   = data.get("local_id") or None

        # post_id: numerisch oder None
        post_id_raw = data.get("post_id")
        try:
            post_id = int(post_id_raw) if post_id_raw is not None else None
        except (TypeError, ValueError):
            post_id = None

        # selection: Objekt → JSON-String
        selection_raw = data.get("selection")
        selection_json = None
        if selection_raw is not None and isinstance(selection_raw, dict):
            # Pflichtfelder des selection-Objekts prüfen
            required_sel = {"xpathStart", "offsetStart", "xpathEnd", "offsetEnd", "textContent"}
            if required_sel.issubset(selection_raw.keys()):
                selection_json = json.dumps(selection_raw, ensure_ascii=False)
            else:
                logger.warning(
                    "selection-Objekt unvollständig (Felder fehlen): %s", selection_raw
                )

        # tags: Array → JSON-String
        tags_raw = data.get("tags")
        tags_json = None
        if tags_raw is not None and isinstance(tags_raw, list):
            # Nur Strings übernehmen, leere herausfiltern
            clean_tags = [str(t).strip() for t in tags_raw if str(t).strip()]
            tags_json = json.dumps(clean_tags, ensure_ascii=False)

        # created_by aus Kontext (SAMAccountName des Ermittlers)
        created_by = getattr(self._context, "username", "") or ""

        # Annotation speichern
        try:
            annotation_id = self._bundle.evidence.save_annotation(
                page_url=page_url,
                category=category,
                text=str(text),
                element_id=element_id,
                investigator_id=self._context.investigator_id,
                selection_json=selection_json,
                tags_json=tags_json,
                local_id=local_id,
                post_id=post_id,
                created_by=created_by,
            )
        except EvidenceDbError as exc:
            self._error(handler, str(exc))
            return
        except Exception as exc:
            logger.error("Annotation konnte nicht gespeichert werden: %s", exc)
            self._error(handler, "Interner Fehler beim Speichern")
            return

        logger.info(
            "Annotation gespeichert: id=%d, page='%s', cat=%s, element=%s, post_id=%s",
            annotation_id, page_url, category, element_id, post_id,
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

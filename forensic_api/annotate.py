# =============================================================================
# forensic_api/annotate.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/annotate
#
#   POST  — Annotation anlegen / aktualisieren (upsert via local_id)
#   DELETE — Annotation löschen (anhand Server-ID)
#
# POST Request-Body (JSON):
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
#   Response: 200 {"id": <annotation_id>, "status": "ok"}
#
# DELETE Request-Body (JSON):
#   { "id": <annotation_id> }          (Pflicht — Server-ID aus POST-Response)
#   Response: 200 {"status": "ok", "deleted": true}
#            oder {"status": "not_found", "deleted": false} (id existiert nicht)
#
# Error-Response (beide Methoden):
#   400 {"error": "<Fehlermeldung>"}
#
# Änderungen:
#   Build 011 (2026-04-13): POST implementiert (Baustelle 3, §11.2 Bauplan).
#   Build 059 (2026-04-26): DELETE implementiert (OP-KN-9 — HoverMenuModule
#     löscht Annotationen ohne Server-Call, sie erscheinen nach Reload wieder).
#     Beleg: Analyse annotate.py + evidence_db.py — kein delete_annotation()
#     vorhanden. delete_annotation() in evidence_db.py gleichzeitig ergänzt.
#
# Version: v0.1.0 · Build: 059 · 2026-04-26
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
        Verarbeitet POST und DELETE /_forensic/annotate

        POST  → Annotation speichern (upsert via local_id)
        DELETE → Annotation löschen (anhand Server-ID)

        Args:
            handler: ForensicRequestHandler-Instanz.
            body:    Request-Body als bytes (JSON).
        """
        if handler.command == "DELETE":
            self._handle_delete(handler, body)
            return

        # --- POST-Pfad (unverändert) ---
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

    def _handle_delete(
        self,
        handler: "ForensicRequestHandler",
        body: bytes,
    ) -> None:
        """
        Verarbeitet DELETE /_forensic/annotate

        Erwartet JSON-Body: {"id": <annotation_id>}

        Gibt {"status": "ok", "deleted": true} zurück wenn erfolgreich,
        {"status": "not_found", "deleted": false} wenn ID nicht existiert.

        Beleg: OP-KN-9 — ohne Server-DELETE erscheinen gelöschte Annotationen
        nach jedem loadAnnotations()-Aufruf wieder.
        """
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, ValueError) as exc:
            self._error(handler, f"Ungültiges JSON: {exc}")
            return

        ann_id_raw = data.get("id")
        if ann_id_raw is None:
            self._error(handler, "Feld 'id' fehlt")
            return
        try:
            ann_id = int(ann_id_raw)
        except (TypeError, ValueError):
            self._error(handler, f"Feld 'id' muss eine Ganzzahl sein, erhalten: {ann_id_raw!r}")
            return

        try:
            deleted = self._bundle.evidence.delete_annotation(ann_id)
        except Exception as exc:
            logger.error("Annotation konnte nicht gelöscht werden: %s", exc)
            self._error(handler, "Interner Fehler beim Löschen")
            return

        if deleted:
            logger.info("Annotation gelöscht: id=%d", ann_id)
            status = "ok"
        else:
            logger.warning("DELETE /_forensic/annotate: id=%d nicht gefunden", ann_id)
            status = "not_found"

        body_out = json.dumps(
            {"status": status, "deleted": deleted}, ensure_ascii=False
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

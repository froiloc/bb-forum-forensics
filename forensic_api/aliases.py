# =============================================================================
# forensic_api/aliases.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 3: Toolbar
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/aliases
#
#   GET    — Alle Ermittler-Aliasse laden
#   POST   — Neuen Alias anlegen
#   DELETE — Alias löschen (anhand ID)
#
# GET Response (JSON):
#   { "aliases": [{"id": 1, "term": "Panther", "createdBy": "paul"}, ...] }
#
# POST Request-Body (JSON):
#   { "term": "Panther" }
#   Response: { "id": 1, "status": "ok" }
#
# DELETE Request-Body (JSON):
#   { "id": 1 }
#   Response: { "status": "ok", "deleted": true }
#
# Beleg: Projektgespräch 2026-05-12 — Bug 2.79 (BS3).
# Version: v0.6.179 · Build: 179 · 2026-05-12
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


class AliasesEndpoint:
    """
    Endpunkt /_forensic/aliases — Ermittler-Aliasse verwalten.
    Beleg: Bug 2.79 — Projektgespräch 2026-05-12.
    """

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
        method: str,
        body: bytes,
    ) -> None:
        """Dispatch GET / POST / DELETE."""
        if method == "GET":
            self._handle_get(handler)
        elif method == "POST":
            self._handle_post(handler, body)
        elif method == "DELETE":
            self._handle_delete(handler, body)
        else:
            body_out = json.dumps({"error": "Methode nicht erlaubt"}).encode("utf-8")
            handler.send_response_body(405, body_out,
                                       content_type="application/json; charset=utf-8")

    def _handle_get(self, handler: "ForensicRequestHandler") -> None:
        """GET /_forensic/aliases — Alle Aliasse laden."""
        try:
            records = self._bundle.evidence.get_aliases()
        except Exception as exc:
            logger.error("AliasesEndpoint GET: Datenbankfehler: %s", exc)
            self._error(handler, "Interner Fehler beim Laden der Aliasse")
            return

        out = [
            {"id": r.id, "term": r.term, "createdBy": r.created_by}
            for r in records
        ]
        body = json.dumps({"aliases": out}, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(200, body,
                                   content_type="application/json; charset=utf-8")
        logger.debug("/_forensic/aliases GET: %d Aliasse", len(out))

    def _handle_post(
        self,
        handler: "ForensicRequestHandler",
        body: bytes,
    ) -> None:
        """POST /_forensic/aliases — Neuen Alias anlegen."""
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, ValueError) as exc:
            self._error(handler, f"Ungültiges JSON: {exc}")
            return

        term = (data.get("term") or "").strip()
        if not term:
            self._error(handler, "Feld 'term' fehlt oder leer")
            return

        created_by = getattr(self._context, "investigator_username", "") or ""

        try:
            alias_id = self._bundle.evidence.save_alias(term, created_by)
        except Exception as exc:
            logger.error("AliasesEndpoint POST: Fehler: %s", exc)
            self._error(handler, str(exc))
            return

        body_out = json.dumps(
            {"id": alias_id, "status": "ok"}, ensure_ascii=False
        ).encode("utf-8")
        handler.send_response_body(200, body_out,
                                   content_type="application/json; charset=utf-8")
        logger.info("Alias angelegt: id=%d term=%r by=%r", alias_id, term, created_by)

    def _handle_delete(
        self,
        handler: "ForensicRequestHandler",
        body: bytes,
    ) -> None:
        """DELETE /_forensic/aliases — Alias löschen."""
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, ValueError) as exc:
            self._error(handler, f"Ungültiges JSON: {exc}")
            return

        id_raw = data.get("id")
        if id_raw is None:
            self._error(handler, "Feld 'id' fehlt")
            return
        try:
            alias_id = int(id_raw)
        except (TypeError, ValueError):
            self._error(handler, f"Feld 'id' muss Ganzzahl sein, erhalten: {id_raw!r}")
            return

        try:
            deleted = self._bundle.evidence.delete_alias(alias_id)
        except Exception as exc:
            logger.error("AliasesEndpoint DELETE: Fehler: %s", exc)
            self._error(handler, "Interner Fehler beim Löschen")
            return

        body_out = json.dumps(
            {"status": "ok" if deleted else "not_found", "deleted": deleted},
            ensure_ascii=False,
        ).encode("utf-8")
        handler.send_response_body(200, body_out,
                                   content_type="application/json; charset=utf-8")
        if deleted:
            logger.info("Alias gelöscht: id=%d", alias_id)

    @staticmethod
    def _error(handler: "ForensicRequestHandler", message: str) -> None:
        body = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(400, body,
                                   content_type="application/json; charset=utf-8")

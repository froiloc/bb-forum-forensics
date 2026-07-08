# =============================================================================
# forensic_api/translation_meta.py
# IT-Forensisches Ermittlungswerkzeug — Endpunkt /_forensic/translation_meta
# =============================================================================
# Zweck (Build 341):
#   Liefert dem BERICHT je post_id die Daten fuer die Uebersetzungsbehandlung:
#   den bereinigten ORIGINAL-Text (posts_cleaned.clean_text), die Ausgangs-
#   sprache (source_lang) und die Provenienz (model_used/created_at, LIVE-
#   Fallback). Read-only, ausschliesslich aus trdb.
#
#   Beispiel-Antwort (found):
#   { "post_id": 705985, "found": true,
#     "original_text": "...", "source_lang": "en",
#     "model_used": "ollama/x", "created_at": "2026-06-20" }
#   Nicht vorhanden:
#   { "post_id": 705985, "found": false }
#
# Beleg: Bauplan Build 340/341 §5.2 (Original-Zitat = clean_text; read-only
#        Zusatzendpunkt bestaetigt vom Entwickler 2026-07-08).
# =============================================================================

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from core.config_loader import ConfigLoader
    from db.bundle import DatabaseBundle
    from core.context import ResolvedContext
    from server.handler import ForensicRequestHandler

logger = get_logger(__name__)


class TranslationMetaEndpoint:
    """Endpunkt /_forensic/translation_meta (GET). Read-only aus trdb."""

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        self._bundle = bundle
        self._context = context

    def handle(
        self,
        handler: "ForensicRequestHandler",
        params: dict,
    ) -> None:
        """Verarbeitet GET /_forensic/translation_meta?post_id=<id>[&source=posts|pms]."""
        raw_vals = params.get("post_id", [])
        raw = raw_vals[0] if raw_vals else ""
        try:
            post_id = int(str(raw).strip())
        except (ValueError, TypeError):
            post_id = -1

        if post_id <= 0:
            self._error(handler, 400, "Ungueltiger oder fehlender post_id")
            return

        # source trennt 'posts' (Forum) von 'pms' — unbekannter Wert -> 400 (GR1).
        source_vals = params.get("source", [])
        source = source_vals[0] if source_vals else "posts"
        if source not in ("posts", "pms"):
            self._error(handler, 400, "Ungueltiger source (erlaubt: posts, pms)")
            return

        try:
            rec = self._bundle.translations.get_meta(post_id, source)
        except Exception as exc:  # defensiv — niemals 500 ohne Log (GR1)
            logger.error(
                "TranslationMetaEndpoint: get_meta(%r) Fehler: %s", post_id, exc
            )
            self._error(handler, 500, "Interner Fehler bei der Meta-Abfrage")
            return

        if rec is None:
            # "Nicht gefunden" ist HTTP 200 mit found:false (kein 404) — die
            # Toolbar/der Bericht unterscheiden fachlich, nicht per Statuscode.
            body_out = json.dumps(
                {"post_id": post_id, "found": False},
                ensure_ascii=False,
            ).encode("utf-8")
            handler.send_response_body(
                200, body_out, content_type="application/json; charset=utf-8"
            )
            return

        logger.debug(
            "/_forensic/translation_meta: post_id=%d source=%s -> gefunden.",
            post_id, source,
        )
        body_out = json.dumps(
            {
                "post_id":       rec.post_id,
                "found":         True,
                "original_text": rec.original_text,
                "source_lang":   rec.source_lang,
                "model_used":    rec.model_used,
                "created_at":    rec.created_at,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        handler.send_response_body(
            200, body_out, content_type="application/json; charset=utf-8"
        )

    @staticmethod
    def _error(handler: "ForensicRequestHandler", code: int, msg: str) -> None:
        body = json.dumps(
            {"error": msg, "status": "error"}, ensure_ascii=False
        ).encode("utf-8")
        handler.send_response_body(
            code, body, content_type="application/json; charset=utf-8"
        )

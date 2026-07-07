# =============================================================================
# forensic_api/translate.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/translate?post_id=<post_id> (GET)
#   Liefert die fertige KI-Uebersetzung eines einzelnen Posts. Wird beim Klick
#   auf die Flaggen-Schaltflaeche geladen und im Inline-Panel angezeigt.
#
#   Provenienz (model_used, created_at) wird MITGELIEFERT, damit die Toolbar den
#   Pflicht-Hinweis 'maschinell uebersetzt, nicht gerichtsverwertbar' untrennbar
#   mit der Uebersetzung anzeigt (GR1). confidence_markers wird bewusst NICHT
#   geliefert (keine sinnvollen Daten — Projektgespraech).
#
# Response (200, gefunden):
#   { "post_id": 706037, "found": true, "translated_text": "...",
#     "model_used": "...", "created_at": "2026-06-..." }
#
# Response (200, keine Uebersetzung):
#   { "post_id": 706037, "found": false }
#   -> 'nicht gefunden' ist KEIN Fehler (kein 404), sondern eine normale Antwort.
#
# Fehlerfall:
#   - fehlender/ungueltiger post_id -> 400 { "error": ..., "status": "error" }
#
# Version: v0.7.331 · Build: 331 · 2026-07-07 (source-Param posts/pms; kein status)
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


class TranslateEndpoint:
    """
    Endpunkt /_forensic/translate (GET).

    Liest ausschliesslich aus trdb.translations (READ-ONLY, global geteilt).
    Beleg: Bauplan Build 329 §3.2
    """

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
        """Verarbeitet GET /_forensic/translate?post_id=<post_id>."""
        raw_vals = params.get("post_id", [])
        raw = raw_vals[0] if raw_vals else ""

        try:
            post_id = int(str(raw).strip())
        except (ValueError, TypeError):
            post_id = -1

        if post_id <= 0:
            body = json.dumps(
                {"error": "Ungueltiger oder fehlender post_id",
                 "status": "error"},
                ensure_ascii=False,
            ).encode("utf-8")
            handler.send_response_body(
                400, body, content_type="application/json; charset=utf-8"
            )
            return

        # Build 331: source trennt 'posts' (Forum) von 'pms'. Default 'posts';
        # unbekannter Wert -> 400 (kein stilles Ersetzen, GR1).
        source_vals = params.get("source", [])
        source = source_vals[0] if source_vals else "posts"
        if source not in ("posts", "pms"):
            body = json.dumps(
                {"error": "Ungueltiger source (erlaubt: posts, pms)",
                 "status": "error"},
                ensure_ascii=False,
            ).encode("utf-8")
            handler.send_response_body(
                400, body, content_type="application/json; charset=utf-8"
            )
            return

        try:
            rec = self._bundle.translations.get_translation(post_id, source)
        except Exception as exc:  # defensiv — niemals 500 ohne Log (GR1)
            logger.error(
                "TranslateEndpoint: get_translation(%r) Fehler: %s",
                post_id, exc,
            )
            body = json.dumps(
                {"error": "Interner Fehler bei der Uebersetzungs-Abfrage",
                 "status": "error"},
                ensure_ascii=False,
            ).encode("utf-8")
            handler.send_response_body(
                500, body, content_type="application/json; charset=utf-8"
            )
            return

        if rec is None:
            logger.debug(
                "/_forensic/translate: post_id=%d — keine Uebersetzung.", post_id
            )
            body_out = json.dumps(
                {"post_id": post_id, "found": False},
                ensure_ascii=False,
            ).encode("utf-8")
            handler.send_response_body(
                200, body_out, content_type="application/json; charset=utf-8"
            )
            return

        logger.debug(
            "/_forensic/translate: post_id=%d ausgeliefert (Modell '%s').",
            post_id, rec.model_used,
        )
        body_out = json.dumps(
            {
                "post_id":         rec.post_id,
                "found":           True,
                "translated_text": rec.translated_text,
                "model_used":      rec.model_used,
                "created_at":      rec.created_at,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        handler.send_response_body(
            200, body_out, content_type="application/json; charset=utf-8"
        )

# =============================================================================
# forensic_api/resolve_posts.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 3, Build 303
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/resolve_posts (GET)
#   Löst eine Liste von post_ids (pids) auf die gescrapte Seite (pages.id)
#   und deren Fortschritt auf. Datenquelle: fdb.post_aliases.page
#   (gemessen vom PostPageMeasurer, Beleg: aiw_sqlite_prepper Build 100/101).
#
#   Hintergrund: Die Treffer-Links auf search.php?action=show_user_posts
#   lauten viewtopic.php?pid=<post_id>#p<post_id> — sie tragen NICHT die
#   kanonische Seiten-URL und können daher nicht direkt gegen
#   /_forensic/search (seitenbasiert) gematcht werden. Dieser Endpunkt liefert
#   pro pid direkt den Fortschritt der Seite, auf der der Post steht, und
#   umgeht so zugleich das limit=50 von /_forensic/search.
#
# Request:
#   GET /_forensic/resolve_posts?pids=<komma-getrennte post_ids>
#     (Whitespace wird toleriert; nicht-numerische Werte werden verworfen.)
#
# Response (200 OK):
#   {
#     "posts": {
#       "<pid>": { "topicId", "forumId", "pageId", "url",
#                  "progressPercent", "resolved": true },
#       "<pid>": { "topicId", "forumId", "resolved": false },   # nicht aufgelöst
#       ...
#     },
#     "total":  <Anzahl angefragter pids>,
#     "status": "ok"
#   }
#
# Response (400): { "error": "...", "status": "error" }   # keine gültigen pids
# Response (500): { "error": "...", "status": "error" }
#
# Neue Datei — Baustelle 3, Build 303.
# Version: v0.1.0 · Build: 303 · 2026-06-25
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

# Obergrenze gegen überlange Anfragen (eine Trefferseite hat i. d. R. einige
# hundert Posts; 2000 ist großzügig bemessen).
_MAX_PIDS = 2000


class ResolvePostsEndpoint:
    """
    Endpunkt /_forensic/resolve_posts (GET).

    Liefert pro angefragter post_id den Fortschritt der gescrapten Seite,
    auf der der Post steht. Benutzerspezifisch — Daten ausschließlich aus
    forensic_<uid>.db (post_aliases, pages) und evidence_<uid>.db
    (annotations, page_visits) des aktuellen Benutzers.

    Beleg: Bauplan Baustelle 3, Build 303; aiw_sqlite_prepper Build 100/101.
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
        """Verarbeitet GET /_forensic/resolve_posts."""
        raw_vals = params.get("pids", [])
        raw = raw_vals[0] if raw_vals else ""

        # pids parsen: komma-getrennt, Whitespace tolerant, Duplikate entfernt,
        # Reihenfolge erhalten (für deterministische Antwort/Logs).
        seen: set[int] = set()
        pids: list[int] = []
        for tok in raw.split(","):
            tok = tok.strip()
            if not tok:
                continue
            try:
                pid = int(tok)
            except ValueError:
                continue
            if pid > 0 and pid not in seen:
                seen.add(pid)
                pids.append(pid)
            if len(pids) >= _MAX_PIDS:
                break

        if not pids:
            body = json.dumps(
                {"error": "Keine gültigen pids übergeben", "status": "error"},
                ensure_ascii=False,
            ).encode("utf-8")
            handler.send_response_body(
                400, body, content_type="application/json; charset=utf-8"
            )
            return

        try:
            resolved = self._bundle.forensic.resolve_posts_progress(pids)
        except Exception as exc:  # defensiv — niemals 500 ohne Log
            logger.error("ResolvePostsEndpoint: resolve_posts_progress() Fehler: %s", exc)
            body = json.dumps(
                {"error": "Interner Fehler bei der Post-Auflösung",
                 "status": "error"},
                ensure_ascii=False,
            ).encode("utf-8")
            handler.send_response_body(
                500, body, content_type="application/json; charset=utf-8"
            )
            return

        # JSON-Keys müssen Strings sein → pid in str umwandeln.
        posts_out = {str(pid): entry for pid, entry in resolved.items()}
        resolved_count = sum(1 for e in resolved.values() if e.get("resolved"))
        logger.debug(
            "/_forensic/resolve_posts: %d pids angefragt, %d aufgelöst.",
            len(pids), resolved_count,
        )

        body_out = json.dumps(
            {"posts": posts_out, "total": len(pids), "status": "ok"},
            ensure_ascii=False,
        ).encode("utf-8")
        handler.send_response_body(
            200, body_out, content_type="application/json; charset=utf-8"
        )

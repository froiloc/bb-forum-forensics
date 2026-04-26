# =============================================================================
# forensic_api/trace_sequence.py
# IT-Forensisches Ermittlungswerkzeug — OP-KN-7: Spur-Navigation
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/trace_sequence (GET)
#   Liefert die vollständige, geordnete Sequenz aller Seiten mit Spuren
#   des Beschuldigten. Wird von TraceNavigationModule (toolbar.js) für die
#   seitenübergreifende Spur-Navigation verwendet.
#
# Reihenfolge (Beleg: OP-KN-7, Projektgespräch 2026-04-26):
#   1. Gruppe: profile  (Profilseiten)
#   2. Gruppe: pm       (Private Nachrichten)
#   3. Gruppe: topic    (Beiträge in Themen)
#   4. Gruppe: other    (Sonstiges: forum, static, poll, thanks, ...)
#   Innerhalb jeder Gruppe: scrape_targets.id ASC (= Autoincrement =
#   chronologische Erfassungsreihenfolge aus aiw_sqlite_prepper).
#
# Request:
#   GET /_forensic/trace_sequence
#
# Response (200 OK):
#   {
#     "sequence": [
#       {
#         "url":      "/forum/profile.php?id=2948078",
#         "title":    "Profil: SomeName",
#         "group":    "profile",
#         "trace_id": 1
#       },
#       ...
#     ],
#     "total":  <Anzahl>,
#     "status": "ok"
#   }
#
# Neue Datei — OP-KN-7 (Spur-Navigation), Build 072.
# Version: v0.1.0 · Build: 072 · 2026-04-26
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

# Gruppenreihenfolge: profile → pm → topic → other
# Beleg: OP-KN-7, Projektgespräch 2026-04-26
_GROUP_ORDER = {"profile": 0, "pm": 1, "topic": 2}


def _url_type_to_group(url_type: str) -> str:
    """
    Ordnet url_type einer der vier Navigationsgruppen zu.
    Beleg: scrape_targets.url_type-Werte aus forensic_schema_db.sql.
    """
    if url_type == "profile":
        return "profile"
    if url_type in ("pm", "pmsnew"):
        return "pm"
    if url_type in ("topic", "post", "poll", "thanks"):
        return "topic"
    return "other"


class TraceSequenceEndpoint:
    """
    Endpunkt /_forensic/trace_sequence — geordnete Spurensequenz.

    Alle Spuren stammen aus fdb.scrape_targets des aktuellen Benutzers.
    Die zurückgelieferten URLs werden gegen fdb.pages aufgelöst, um
    sicherzustellen, dass nur tatsächlich gescrapte Seiten geliefert werden
    (kein Eintrag ohne zugehörigen BLOB).

    Beleg: OP-KN-7, Build 072.
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
        params: dict,
    ) -> None:
        """Verarbeitet GET /_forensic/trace_sequence."""
        try:
            sequence = self._bundle.forensic.get_trace_sequence()
        except Exception as exc:
            logger.error("TraceSequenceEndpoint: get_trace_sequence() fehlgeschlagen: %s", exc)
            body = json.dumps(
                {"error": "Interner Fehler", "status": "error"},
                ensure_ascii=False,
            ).encode("utf-8")
            handler.send_response_body(
                500, body, content_type="application/json; charset=utf-8"
            )
            return

        logger.debug("/_forensic/trace_sequence: %d Einträge", len(sequence))

        body_out = json.dumps(
            {"sequence": sequence, "total": len(sequence), "status": "ok"},
            ensure_ascii=False,
        ).encode("utf-8")
        handler.send_response_body(
            200, body_out, content_type="application/json; charset=utf-8"
        )

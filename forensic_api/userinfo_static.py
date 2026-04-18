# =============================================================================
# forensic_api/userinfo_static.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Nutzerinfo-Tab
# =============================================================================
# Zweck:
#   Endpunkt GET /_forensic/userinfo/static
#   Liefert den statischen HTML-BLOB für den Nutzerinfo-Tab aus
#   fdb.static_pages WHERE key='userinfo'.
#
#   Der BLOB wird von B0-Phase-B (phase_b_exporter.py Schritt 7) erzeugt
#   und enthält das vollständige HTML-Fragment für #userinfo-static,
#   einschließlich uid_profile, uid_surveillance, uid_posts, uid_pms_posts,
#   uid_aliases, uid_stats, Heatmap und Timeline.
#
#   userinfo.js ruft diesen Endpunkt beim Laden von Fenster 2 ab und
#   fügt das Fragment in #userinfo-static ein.
#
# Response:
#   200  text/html; charset=utf-8  — BLOB-Fragment (kein vollständiges Dokument)
#   204  No Content                — static_pages nicht vorhanden (Phase B noch
#                                    nicht gelaufen oder ältere forensic_db)
#
# Forensische Relevanz:
#   Lesezugriff auf READ-ONLY fdb (forensic_<uid>.db).
#   Kein Schreibzugriff.
#
# Beleg: Projektgespräch 2026-04-18
# Version: v0.1.0 · Build: 017 · 2026-04-18
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)


class UserinfoStaticEndpoint:
    """
    Endpunkt GET /_forensic/userinfo/static

    Liest den Phase-B-HTML-BLOB aus fdb.static_pages und liefert ihn
    als text/html. Gibt HTTP 204 zurück wenn kein BLOB vorhanden.
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

    def handle(self, handler: "ForensicRequestHandler") -> None:
        blob = self._bundle.forensic.get_userinfo_blob()

        if blob is None:
            # Phase B noch nicht gelaufen oder ältere forensic_db
            logger.debug(
                "/_forensic/userinfo/static: kein BLOB in static_pages "
                "(user_id=%d) — 204 No Content.",
                self._context.user_id,
            )
            handler.send_response_body(204, b"")
            return

        body = blob.encode("utf-8")
        handler.send_response_body(
            200, body, content_type="text/html; charset=utf-8"
        )
        logger.debug(
            "/_forensic/userinfo/static: BLOB ausgeliefert "
            "(%d Bytes, user_id=%d).",
            len(body), self._context.user_id,
        )

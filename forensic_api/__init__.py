# =============================================================================
# forensic_api/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Registriert alle forensic_api-Endpunkte und stellt die dispatch()-Funktion
#   bereit, die router.py aufruft.
#
# Stand Build 008: Platzhalter — alle Endpunkte werden in Phase 3 implementiert.
# Bekannte Endpunkte:
#   /_forensic/page        → page.py
#   /_forensic/annotate    → annotate.py
#   /_forensic/status      → status.py
#   /_forensic/viewport    → viewport.py
#   /_forensic/toolbar.js  → static.py
#   /_forensic/toolbar.css → static.py
#
# Version: v0.1.0 · Build: 008 · 2026-04-10
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


class ForensicApi:
    """
    Dispatch-Klasse für alle /_forensic/-Endpunkte.
    Phase 3 erweitert diese Klasse mit den eigentlichen Endpunkt-Handlern.
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

    def dispatch(
        self,
        handler: "ForensicRequestHandler",
        method: str,
        url_path: str,
        query: str,
        is_ajax: bool,
    ) -> None:
        """
        Leitet /_forensic/-Requests an den zuständigen Endpunkt-Handler weiter.
        """
        import urllib.parse
        params = urllib.parse.parse_qs(query, keep_blank_values=False)

        # /_forensic/page → BlobHandler (AJAX-Auslieferung)
        if url_path == "/_forensic/page":
            target_url = self._get_param(params, "url")
            if not target_url:
                handler.send_response_body(
                    400,
                    b'{"error": "Parameter url fehlt"}',
                    content_type="application/json",
                )
                return
            import urllib.parse as _up
            parsed    = _up.urlparse(target_url)
            fragment  = parsed.fragment or None
            clean_url = _up.urlunparse(parsed._replace(fragment=""))
            from server.blob_handler import BlobHandler
            bh = BlobHandler(self._bundle, self._context, self._config)
            bh.handle_with_fragment(handler, clean_url, fragment)
            return

        # /_forensic/status
        if url_path == "/_forensic/status":
            self._handle_status(handler)
            return

        # /_forensic/toolbar.css und /_forensic/toolbar.js
        if url_path in ("/_forensic/toolbar.css", "/_forensic/toolbar.js"):
            self._handle_static(handler, url_path)
            return

        # Alle anderen /_forensic/-Endpunkte: noch nicht implementiert
        logger.debug(
            "/_forensic/-Endpunkt noch nicht implementiert: '%s'", url_path
        )
        handler.send_response_body(
            501,
            f'{{"error": "Endpunkt {url_path} noch nicht implementiert"}}'
            .encode("utf-8"),
            content_type="application/json",
        )

    def _handle_status(self, handler: "ForensicRequestHandler") -> None:
        """Liefert einen minimalen Serverstatus als JSON."""
        import json
        import time
        status = {
            "mode":     self._context.mode,
            "user_id":  self._context.user_id,
            "username": self._context.username,
            "ts":       int(time.time()),
            "version":  "v0.1.0-build008",
        }
        body = json.dumps(status, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(200, body, content_type="application/json")

    def _handle_static(
        self, handler: "ForensicRequestHandler", url_path: str
    ) -> None:
        """
        Liefert toolbar.js und toolbar.css aus.
        Phase 3 ersetzt diese Platzhalter durch echte Inhalte.
        """
        if url_path.endswith(".css"):
            body = "/* toolbar.css - Platzhalter, wird in Phase 3 befüllt */".encode("utf-8")
            mime = "text/css; charset=utf-8"
        else:
            body = "/* toolbar.js - Platzhalter, wird in Phase 3 befüllt */".encode("utf-8")
            mime = "application/javascript; charset=utf-8"
        handler.send_response_body(200, body, content_type=mime)

    @staticmethod
    def _get_param(params: dict, key: str):
        values = params.get(key)
        return values[0] if values else None

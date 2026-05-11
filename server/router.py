# =============================================================================
# server/router.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Erste Verarbeitungsstufe nach dem HTTP-Server. Entscheidet anhand der
#   URL und des Request-Typs, welcher Handler zuständig ist.
#
# Routing-Logik:
#   1. POST außerhalb /_forensic/  → HTTP 404
#   2. Beginnt mit /_forensic/     → forensic_api.dispatch()
#   3. URL beginnt mit Asset-Präfix aus config → asset_handler
#   4. Shell-Request (kein AJAX-Header) → shell_handler
#   5. AJAX-Request                → blob_handler (/_forensic/page intern)
#
# URL-Normalisierung:
#   Fragment-Anker (#p12345) werden vor dem Routing entfernt.
#   Query-String wird für Asset-Erkennung und Alias-Auflösung ausgewertet.
#
# Konfigurierbarkeit:
#   Asset-Präfixe und Alias-Muster kommen aus config.yaml (url_patterns).
#   Kein Muster ist hart im Code verdrahtet.
#
# Abhängigkeiten: urllib.parse — Stdlib + interne Module
# Version: v0.6.114 · Build: 114 · 2026-05-07
# =============================================================================

from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

# Reservierter Namensraum für interne API-Endpunkte
FORENSIC_API_PREFIX = "/_forensic/"


class Router:
    """
    Leitet eingehende Requests an den zuständigen Handler weiter.

    Verwendung (durch ForensicRequestHandler):
        router.dispatch(handler, method, path, is_ajax)
    """

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
        build_info=None,
    ) -> None:
        self._bundle     = bundle
        self._context    = context
        self._config     = config
        self._build_info = build_info

        # Asset-Präfixe aus config.yaml laden
        self._asset_prefixes: list[str] = config.get(
            "url_patterns.asset_prefixes", []
        )

        # Lazy-Imports der Handler (vermeidet zirkuläre Importe)
        self._shell_handler  = None
        self._blob_handler   = None
        self._asset_handler  = None
        self._forensic_api   = None

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def dispatch(
        self,
        handler: "ForensicRequestHandler",
        method: str,
        path: str,
        is_ajax: bool,
    ) -> None:
        """
        Analysiert den Request und leitet ihn an den zuständigen Handler weiter.

        Args:
            handler:  ForensicRequestHandler-Instanz (für Response-Ausgabe).
            method:   HTTP-Methode: "GET", "POST", "HEAD".
            path:     Vollständiger Anfragepfad inkl. Query-String.
            is_ajax:  True wenn Header X-Forensic-Request: ajax gesetzt ist.
        """
        # URL in Bestandteile zerlegen
        parsed   = urllib.parse.urlparse(path)
        url_path = parsed.path          # z.B. /forum/viewtopic.php
        query    = parsed.query         # z.B. id=42&pid=123
        fragment = parsed.fragment      # leer — Browser sendet kein Fragment

        logger.debug(
            "Router: %s %s (ajax=%s)", method, url_path, is_ajax
        )

        # ----------------------------------------------------------------
        # Regel 1: POST/DELETE außerhalb /_forensic/ → 404
        # DELETE wird nur für /_forensic/annotate (OP-KN-9, Build 059) genutzt.
        # ----------------------------------------------------------------
        if method in ("POST", "DELETE") and not url_path.startswith(FORENSIC_API_PREFIX):
            logger.debug("%s außerhalb /_forensic/ blockiert: '%s'", method, url_path)
            handler.send_response_body(
                404,
                b"",
                extra_headers={"X-Forensic-Status": "POST_NOT_ALLOWED"},
            )
            return

        # ----------------------------------------------------------------
        # Regel 2: /_forensic/ → Forensik-API
        # ----------------------------------------------------------------
        if url_path.startswith(FORENSIC_API_PREFIX):
            self._get_forensic_api().dispatch(
                handler=handler,
                method=method,
                url_path=url_path,
                query=query,
                is_ajax=is_ajax,
            )
            return

        # ----------------------------------------------------------------
        # Regel 2b: /icons/ → statische Icons aus static/icons/
        # Build 114: IconQuote.svg und andere Editor.js-Plugin-Icons.
        # Beleg: Projektgespraech 2026-05-07
        # ----------------------------------------------------------------
        if url_path.startswith('/icons/') and method == 'GET':
            self._get_forensic_api().dispatch(
                handler=handler,
                method=method,
                url_path='/_forensic/static' + url_path,
                query='',
                is_ajax=False,
            )
            return

        # ----------------------------------------------------------------
        # Regel 3: Asset-URL → asset_handler
        # ----------------------------------------------------------------
        if self._is_asset_url(url_path):
            self._get_asset_handler().handle(handler, url_path)
            return

        # ----------------------------------------------------------------
        # Regel 4+5: Forum-Seiten → shell_handler oder blob_handler
        # ----------------------------------------------------------------
        # Vollständige URL ohne Fragment für DB-Lookup rekonstruieren
        canonical_url = self._build_canonical_url(url_path, query)

        if is_ajax:
            # AJAX-Request: nur BLOB-Inhalt als JSON zurückgeben
            self._get_blob_handler().handle(handler, canonical_url)
        else:
            # Shell-Request: leere Shell mit <head> ausliefern
            self._get_shell_handler().handle(handler, canonical_url)

    # ------------------------------------------------------------------
    # URL-Hilfsmethoden
    # ------------------------------------------------------------------

    def _is_asset_url(self, url_path: str) -> bool:
        """
        Prüft ob die URL ein statisches Asset ist.
        Entscheidung anhand der konfigurierten asset_prefixes.
        """
        for prefix in self._asset_prefixes:
            if url_path.startswith(prefix):
                return True
        return False

    @staticmethod
    def _build_canonical_url(url_path: str, query: str) -> str:
        """
        Baut die kanonische URL für den DB-Lookup zusammen.
        Fragment-Anker werden nicht mitgenommen (sind nicht in der DB).

        Beispiele:
          /forum/viewtopic.php + id=42   → /forum/viewtopic.php?id=42
          /forum/profile.php  + id=5     → /forum/profile.php?id=5
          /forum/index.php    + (leer)   → /forum/index.php
        """
        if query:
            return f"{url_path}?{query}"
        return url_path

    # ------------------------------------------------------------------
    # Lazy Handler-Initialisierung
    # ------------------------------------------------------------------

    def _get_shell_handler(self):
        if self._shell_handler is None:
            from server.shell_handler import ShellHandler
            self._shell_handler = ShellHandler(
                self._bundle, self._context, self._config
            )
        return self._shell_handler

    def _get_blob_handler(self):
        if self._blob_handler is None:
            from server.blob_handler import BlobHandler
            self._blob_handler = BlobHandler(
                self._bundle, self._context, self._config
            )
        return self._blob_handler

    def _get_asset_handler(self):
        if self._asset_handler is None:
            from server.asset_handler import AssetHandler
            self._asset_handler = AssetHandler(self._bundle)
        return self._asset_handler

    def _get_forensic_api(self):
        if self._forensic_api is None:
            from forensic_api import ForensicApi
            self._forensic_api = ForensicApi(
                self._bundle, self._context, self._config,
                build_info=self._build_info,
            )
        return self._forensic_api

# =============================================================================
# server/blob_handler.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Der einzige Auslieferungspfad für BLOB-Inhalte.
#   Beantwortet AJAX-Requests auf /_forensic/page?url=...
#   sowie direkte AJAX-Requests auf Forum-URLs (via router.py).
#   Gibt einen JSON-Envelope zurück, den toolbar.js in #forensic-viewport
#   injiziert.
#
# JSON-Envelope:
#   {
#     "html":           "<body-Inhalt oder null>",
#     "head": {
#       "title":         "<Seitentitel oder null>",
#       "stylesheets":   ["<href1>", "<href2>", ...],
#       "inline_styles": ["<CSS-Inhalt>", ...]
#     },
#     "scrape_context": "user|investigator|actor:<uid>",
#     "http_status":    200,
#     "fetch_failed":   false,
#     "in_scope":       true,
#     "url_canonical":  "/forum/viewtopic.php?id=42",
#     "fragment":       "p12345"   (oder null)
#   }
#
# URL-Auflösung (Reihenfolge):
#   1. Fragment-Anker extrahieren und entfernen
#   2. ?pid=<post_id>   → post_aliases → topic-URL aufbauen
#   3. ?notify=<id>     → notify_aliases → post_id → topic-URL aufbauen
#   4. Direkt in blob_lookup suchen
#
# page_visit-Protokollierung:
#   Erfolgt hier nach erfolgreichem BLOB-Lookup (in_scope=True).
#   Nicht bei NOT_IN_SCOPE und nicht bei Shell-Load.
#
# Forensische Relevanz:
#   Sonderfälle werden niemals still übergangen:
#   - NOT_IN_SCOPE:   in_scope=False im JSON
#   - fetch_failed:   fetch_failed=True + http_status im JSON
#   - investigator:   scrape_context='investigator' im JSON
#   Alle drei Zustände sind für toolbar.js sichtbar und werden angezeigt.
#
# Abhängigkeiten: json, urllib.parse — Stdlib + interne Module
# Version: v0.1.0 · Build: 023 · 2026-04-15
# =============================================================================

from __future__ import annotations

import json
import re
import urllib.parse
from typing import TYPE_CHECKING, Optional

from core.logger import get_logger
from server.head_extractor import HeadExtractor

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

# Regex für Fragment-Anker der Form #p<post_id>
_FRAGMENT_POST_RE = re.compile(r"^p(\d+)$")


class BlobHandler:
    """
    Liefert BLOB-Inhalte als JSON-Envelope für AJAX-Requests.

    Wird von router.py für AJAX-Forum-Requests aufgerufen.
    Wird auch von forensic_api/page.py für /_forensic/page aufgerufen.

    Verwendung:
        blob_handler.handle(request_handler, canonical_url)
        # oder mit explizitem Fragment:
        blob_handler.handle_with_fragment(request_handler, url, fragment)
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

        # Alias-Muster aus config.yaml
        self._post_id_param  = config.get("url_patterns.alias_patterns.post_id_param",  "pid")
        self._notify_param   = config.get("url_patterns.alias_patterns.notify_param",    "notify")
        self._fragment_post  = config.get("url_patterns.alias_patterns.fragment_post",   "p")
        self._head_extractor = HeadExtractor()

    def handle(
        self,
        handler: "ForensicRequestHandler",
        canonical_url: str,
    ) -> None:
        """
        Verarbeitet einen AJAX-Request für eine Forum-URL.

        Args:
            handler:       ForensicRequestHandler-Instanz.
            canonical_url: Normalisierte URL (ohne Fragment).
        """
        self.handle_with_fragment(handler, canonical_url, fragment=None)

    def handle_with_fragment(
        self,
        handler: "ForensicRequestHandler",
        url: str,
        fragment: Optional[str],
    ) -> None:
        """
        Verarbeitet einen AJAX-Request mit optionalem Fragment-Anker.

        Args:
            handler:  ForensicRequestHandler-Instanz.
            url:      URL (ohne Fragment).
            fragment: Fragment-Anker ohne #, z.B. "p12345", oder None.
        """
        envelope = self._resolve_and_build(url, fragment)
        body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")

        # page_visit protokollieren wenn Seite im Scope und BLOB vorhanden
        if envelope["in_scope"]:
            try:
                self._bundle.evidence.log_page_visit(
                    page_url=envelope["url_canonical"],
                    scrape_context=envelope["scrape_context"],
                    investigator_id=self._context.investigator_id,
                )
            except Exception as exc:
                # Protokollfehler dürfen die Auslieferung nicht blockieren
                logger.warning("page_visit-Protokollierung fehlgeschlagen: %s", exc)

        handler.send_response_body(
            status=200,
            body=body,
            content_type="application/json; charset=utf-8",
        )

    # ------------------------------------------------------------------
    # URL-Auflösung und Envelope-Aufbau
    # ------------------------------------------------------------------

    def _resolve_and_build(
        self, url: str, fragment: Optional[str]
    ) -> dict:
        """
        Löst die URL auf und baut den JSON-Envelope auf.

        Returns:
            Dict mit allen Envelope-Feldern.
        """
        # Schritt 1: URL und Fragment parsen
        parsed   = urllib.parse.urlparse(url)
        url_path = parsed.path
        params   = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)

        # Fragment aus URL extrahieren falls vorhanden (normalerweise leer
        # in HTTP-Requests, aber zur Sicherheit behandeln)
        if parsed.fragment and not fragment:
            fragment = parsed.fragment
        url_no_fragment = urllib.parse.urlunparse(
            parsed._replace(fragment="")
        )

        # Schritt 2: Alias-Auflösung
        resolved_url, fragment = self._resolve_aliases(
            url_no_fragment, url_path, params, fragment
        )

        # Schritt 3: BLOB-Lookup
        page = self._bundle.forensic.get_page(resolved_url)

        # Schritt 4: Envelope zusammenbauen
        if page is None:
            logger.debug("BlobHandler: NOT_IN_SCOPE für '%s'", resolved_url)
            return {
                "html":           None,
                "head":           None,
                "scrape_context": "unknown",
                "http_status":    0,
                "fetch_failed":   True,
                "in_scope":       False,
                "url_canonical":  resolved_url,
                "fragment":       fragment,
            }

        # <head>-Elemente aus BLOB extrahieren
        head_data = None
        if page.html:
            extracted = self._head_extractor.extract(page.html)
            head_data = {
                "title":         extracted.title,
                "base_href":     extracted.base_href,
                "stylesheets":   extracted.stylesheets,
                "inline_styles": extracted.inline_styles,
            }

        # <body>-Inhalt aus BLOB extrahieren
        body_html = self._extract_body(page.html) if page.html else None

        logger.debug(
            "BlobHandler: '%s' → page_id=%d, context=%s, failed=%s",
            resolved_url, page.page_id, page.scrape_context, page.fetch_failed,
        )

        return {
            "html":           body_html,
            "head":           head_data,
            "scrape_context": page.scrape_context,
            "http_status":    page.http_status,
            "fetch_failed":   page.fetch_failed,
            "in_scope":       True,
            "url_canonical":  page.url,
            "fragment":       fragment,
        }

    def _resolve_aliases(
        self,
        url: str,
        url_path: str,
        params: dict,
        fragment: Optional[str],
    ) -> tuple[str, Optional[str]]:
        """
        Löst URL-Aliasse auf und gibt (aufgelöste_url, fragment) zurück.

        Auflösungsreihenfolge:
          1. ?pid=<post_id>    → post_aliases → topic-URL
          2. ?notify=<notify>  → notify_aliases → post_id → post_aliases
          3. Direkt (keine Auflösung nötig)
        """
        fdb = self._bundle.forensic

        # Fragment aus Alias-Mustern ableiten falls nicht gesetzt
        # z.B. ?pid=12345 → fragment = "p12345"
        if not fragment:
            pid_val = self._get_single_param(params, self._post_id_param)
            if pid_val:
                fragment = f"{self._fragment_post}{pid_val}"

        # Auflösung 1: ?pid=<post_id>
        pid_str = self._get_single_param(params, self._post_id_param)
        if pid_str:
            try:
                post_id = int(pid_str)
                alias = fdb.resolve_post_alias(post_id)
                if alias:
                    resolved = f"{url_path}?id={alias.topic_id}"
                    logger.debug(
                        "pid=%d → topic_id=%d → '%s'",
                        post_id, alias.topic_id, resolved,
                    )
                    return resolved, fragment
            except (ValueError, TypeError):
                pass

        # Auflösung 2: ?notify=<notify_id>
        notify_str = self._get_single_param(params, self._notify_param)
        if notify_str:
            try:
                notify_id = int(notify_str)
                notify_alias = fdb.resolve_notify_alias(notify_id)
                if notify_alias:
                    post_alias = fdb.resolve_post_alias(notify_alias.post_id)
                    if post_alias:
                        resolved = f"{url_path}?id={post_alias.topic_id}"
                        fragment = f"{self._fragment_post}{notify_alias.post_id}"
                        logger.debug(
                            "notify=%d → post_id=%d → topic_id=%d",
                            notify_id, notify_alias.post_id, post_alias.topic_id,
                        )
                        return resolved, fragment
            except (ValueError, TypeError):
                pass

        # Keine Auflösung — URL direkt verwenden
        return url, fragment

    @staticmethod
    def _get_single_param(params: dict, key: str) -> Optional[str]:
        """
        Gibt den ersten Wert eines Query-Parameters zurück, oder None.
        parse_qs liefert Listen — wir nehmen immer den ersten Wert.
        """
        values = params.get(key)
        return values[0] if values else None

    @staticmethod
    def _extract_body(html: bytes) -> str:
        """
        Extrahiert den Inhalt zwischen <body> und </body>.
        Gibt den gesamten HTML-String zurück wenn kein <body>-Tag gefunden.

        Verwendet einfache String-Suche statt HTML-Parser für Geschwindigkeit
        bei großen BLOBs. Die gespeicherten Forum-Seiten haben immer ein
        klar strukturiertes <body>-Tag.
        """
        html_str = html.decode("utf-8", errors="replace")

        # <body ...> suchen (mit möglichen Attributen)
        body_start_idx = html_str.lower().find("<body")
        if body_start_idx == -1:
            return html_str

        # Ende des öffnenden Tags suchen
        tag_end_idx = html_str.find(">", body_start_idx)
        if tag_end_idx == -1:
            return html_str

        content_start = tag_end_idx + 1

        # </body> suchen
        body_end_idx = html_str.lower().rfind("</body>")
        if body_end_idx == -1:
            return html_str[content_start:]

        return html_str[content_start:body_end_idx]

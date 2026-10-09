# =============================================================================
# server/asset_handler.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Liefert statische Assets (CSS, Bilder, Smilies, Avatare) aus den
#   Asset-Datenbanken aus. Kaskade: assets_<uid>.db → default.db → 404.
#
# Lookup-Kaskade (NEU Build 017):
#   1. bundle.assets.get_asset(url)   — assets_<uid>.db (nutzerspezifisch,
#                                       Avatare, Post-Bilder): bevorzugt
#   2. bundle.default.get_asset(url)  — default.db (nutzerneutrale Forum-
#                                       Assets: CSS, Icons, Smilies): Fallback
#   3. HTTP 404 wenn beide nichts liefern
#
# Verhalten je Ergebnis:
#   Asset bekannt und data vorhanden → HTTP 200 mit korrektem MIME-Type
#   Asset bekannt aber data=NULL     → HTTP 200 mit leerem Body (kein Fehler)
#   Asset unbekannt in beiden DBs    → HTTP 404
#
# Forensische Relevanz:
#   Statische Assets sind nutzerneutral. Nutzerspezifische Assets
#   (Avatare, Post-Bilder) können identifikatorischen Wert haben und
#   sind daher in assets_<uid>.db getrennt gespeichert. Ein fehlendes
#   Asset ist kein forensischer Verlust — es beeinflusst nur die
#   visuelle Darstellung. NOT_IN_SCOPE gilt ausschließlich für
#   Forum-Seiten, nicht für Assets.
#
# Build 773 (Bildschleier): bei aktivem Schleier werden Bildquellen in CSS
#   durch einen Platzhalter ersetzt (core/bildschleier_css_umschreiber.py),
#   und ein Bild, das als eigenes Dokument aufgerufen wird, kommt in einer
#   verschleiernden Huelle (server/bildschleier_huelle.py). CSS traegt
#   'Cache-Control: no-store', Bilder 'Vary: Sec-Fetch-Dest, Accept'.
#
# Abhängigkeiten: keine externen Abhängigkeiten
# Version: v0.1.0 · Build: 270 · 2026-05-31
#
# Changelog Build 270 (2026-05-31):
#   - CSS-Auslieferung: url(...)-Einträge mit bekannten vollständigen
#     URLs werden durch /_forensic/fileasset?url=... ersetzt.
#     Beleg: Projektgespräch 2026-05-31.
# =============================================================================

from __future__ import annotations

import re
import urllib.parse

from typing import TYPE_CHECKING, Optional

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from db.default_db import AssetRecord

logger = get_logger(__name__)


class AssetHandler:
    """
    Liefert statische Assets per Kaskade aus assets_<uid>.db und default.db aus.

    Kaskade: assets_<uid>.db (nutzerspezifisch) → default.db (Fallback) → 404

    Verwendung (durch router.py):
        asset_handler.handle(request_handler, url_path)
    """

    def __init__(self, bundle: "DatabaseBundle", config=None,
                 context=None) -> None:
        self._bundle = bundle
        # Build 773 (Bildschleier): config/context fuer den prozessweiten
        # BildschleierDienst. Ohne sie (aeltere Aufrufer, Tests) gibt es
        # keinen Schleier-Teil — router.py uebergibt beide.
        self._config = config
        self._context = context

    def _bildschleier(self):
        """Build 773: der BildschleierDienst, oder None ohne config/context."""
        if self._config is None or self._context is None:
            return None
        from core.bildschleier_dienst import dienst
        return dienst(self._config, self._context)

    def handle(
        self,
        handler: "ForensicRequestHandler",
        url_path: str,
    ) -> None:
        """
        Sucht das Asset per Kaskade und liefert es aus.

        Lookup-Reihenfolge:
          1. assets_<uid>.db  — nutzerspezifische Bilder (Avatare, Post-Bilder)
          2. default.db       — nutzerneutrale Forum-Assets (CSS, Icons)
          3. HTTP 404         — Asset nicht vorhanden

        Args:
            handler:  ForensicRequestHandler-Instanz.
            url_path: URL-Pfad des Assets (ohne Query-String).
        """
        asset = self._lookup(url_path)

        if asset is None:
            logger.debug("Asset in keiner DB gefunden: '%s'", url_path)
            handler.send_response_body(404, b"")
            return

        data      = asset.data or b""
        mime_type = asset.mime_type

        # CSS-Rewriting: url(...)-Einträge mit bekannten vollständigen
        # URLs durch /_forensic/fileasset?url=... ersetzen.
        # Beleg: Projektgespräch 2026-05-31.
        ist_css = bool(mime_type and "css" in mime_type)
        if ist_css and data:
            data = self._rewrite_css_urls(data)

        # Build 773 (Bildschleier, Bauplan §5.3/§5.4). Nur bei aktivem
        # Schleier: Bildquellen in CSS ersetzen, Direktaufrufe von Bildern
        # mit einer Huelle beantworten. Ein Asset-Pfad ist ein Pfad auf dem
        # Forenhost — die Regel prueft ihn wurzelrelativ.
        from server.bildschleier_huelle import VARY, BildschleierHuelle
        extra: dict = {}
        ist_bild = BildschleierHuelle.ist_bild(mime_type)
        if ist_bild:
            extra["Vary"] = VARY
        if ist_css:
            # Nie zwischenspeichern: nach dem Umschalten muss das Neuladen
            # die Stylesheets im neuen Zustand holen.
            extra["Cache-Control"] = "no-store"
        d = self._bildschleier()
        if d is not None and (ist_css or ist_bild):
            zustand = d.zustand()
            if zustand.veiled:
                if ist_css and data:
                    from core.bildschleier_css_umschreiber import (
                        BildschleierCssUmschreiber)
                    text, anzahl = BildschleierCssUmschreiber(d.regel).umschreiben(
                        data.decode("utf-8", errors="replace"), url_path)
                    if anzahl:
                        data = text.encode("utf-8")
                if ist_bild and BildschleierHuelle.ist_dokumentanfrage(
                        getattr(handler, "headers", None)) \
                        and not d.regel.ist_ausgenommen(url_path, "/"):
                    anfrage = getattr(handler, "path", None) or url_path
                    logger.info("Bildschleier: Direktaufruf von '%s' -> Huelle",
                                url_path)
                    handler.send_response_body(
                        status=200, body=BildschleierHuelle.html(anfrage),
                        content_type="text/html; charset=utf-8",
                        extra_headers={"Cache-Control": "no-store",
                                       "Vary": VARY})
                    return

        logger.debug(
            "Asset ausgeliefert: '%s' (%s, %d bytes)",
            url_path, mime_type, len(data),
        )
        handler.send_response_body(
            status=200,
            body=data,
            content_type=mime_type,
            extra_headers=extra or None,
        )

    _CSS_URL_RE = re.compile(
        r'url\(["\']?(https?://[^"\')\s]+)["\']?\)',
        re.IGNORECASE,
    )

    def _rewrite_css_urls(self, css_bytes: bytes) -> bytes:
        """
        Ersetzt url(http://...) in CSS-Daten durch /_forensic/fileasset?url=...
        wenn die URL in assets_<uid>.db vorhanden ist.
        Beleg: Projektgespräch 2026-05-31.
        """
        try:
            css_str = css_bytes.decode("utf-8", errors="replace")
        except Exception:
            return css_bytes

        candidates = set(m.group(1) for m in self._CSS_URL_RE.finditer(css_str))
        if not candidates:
            return css_bytes

        known = self._bundle.assets.get_known_full_urls(candidates)
        if not known:
            return css_bytes

        for url in sorted(known, key=len, reverse=True):
            proxy = "/_forensic/fileasset?url=" + urllib.parse.quote(url, safe="")
            css_str = css_str.replace(url, proxy)

        return css_str.encode("utf-8")

    def _lookup(self, url_path: str) -> "Optional[AssetRecord]":
        """
        Führt den kaskadierten Asset-Lookup durch.

        Stufe 1: assets_<uid>.db via bundle.assets — nutzerspezifisch, bevorzugt.
        Stufe 2: default.db via bundle.default    — nutzerneutral, Fallback.

        Returns:
            AssetRecord aus der ersten Quelle, die einen Treffer liefert,
            oder None wenn beide Quellen leer sind.
        """
        # Stufe 1: assets_<uid>.db (nutzerspezifisch — Avatare, Post-Bilder)
        asset = self._bundle.assets.get_asset(url_path)
        if asset is not None:
            logger.debug("Asset aus assets_<uid>.db: '%s'", url_path)
            return asset

        # Stufe 2: default.db (nutzerneutral — CSS, Icons, Smilies)
        asset = self._bundle.default.get_asset(url_path)
        if asset is not None:
            logger.debug("Asset aus default.db: '%s'", url_path)
            return asset

        return None

# =============================================================================
# forensic_api/search.py
# IT-Forensisches Ermittlungswerkzeug — Kontext-Navigator Phase KN-3
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/search (GET)
#   Liefert eine gefilterte, sortierte Liste von PageSummaryRecords für
#   den Kontext-Navigator-Dropdown und das Erweiterte-Suche-Modal.
#   Interface-Kontrakt: Bauplan Baustelle 3 Ergänzung Kontext-Navigator
#   v0.6, §4 (PageSummaryRecord) + §7.3 (Filterparameter).
#
# Request:
#   GET /_forensic/search
#     ?q=<freitext>
#     &tags=username,pgp
#     &categories=CAT_PERSON,CAT_LOCATION
#     &progress=open|closed|all
#     &viewed_from=<unix_ms>
#     &viewed_to=<unix_ms>
#     &context=user,investigator,actor
#     &fetch_failed=true|false|all
#     &has_annotations=true|false|all
#     &sort=last_viewed_desc|last_viewed_asc|url_asc|url_desc|annotations_desc|traces_desc
#     &limit=<n>        (1–200, default 50)
#     &offset=<n>       (default 0)
#
# Response (200 OK):
#   {
#     "pages":  [ PageSummaryRecord, ... ],
#     "total":  <Anzahl zurückgegebener Einträge>,
#     "status": "ok"
#   }
#
# Response (500):
#   { "error": "Interner Fehler", "status": "error" }
#
# Neue Datei — Phase KN-3 (Bauplan KN v0.6, §12 Phase KN-3).
# Version: v0.1.0 · Build: 070 · 2026-04-26
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

# Erlaubte sort-Werte (gegen Injection absichern)
_VALID_SORT = frozenset({
    "last_viewed_desc", "last_viewed_asc",
    "url_asc", "url_desc",
    "annotations_desc", "traces_desc",
})


class SearchEndpoint:
    """
    Endpunkt /_forensic/search (GET)

    Liefert PageSummaryRecords für den Kontext-Navigator.
    Alle Daten sind benutzerspezifisch — sie stammen ausschließlich
    aus forensic_<uid>.db (fdb) und evidence_db des aktuellen Benutzers.

    Beleg: Bauplan KN v0.6, §4, §7.3, §12 Phase KN-3.
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
        """
        Verarbeitet GET /_forensic/search.

        Args:
            handler: ForensicRequestHandler-Instanz.
            params:  URL-Query-Parameter (aus urllib.parse.parse_qs).
        """
        # ------------------------------------------------------------------
        # Parameter auslesen und validieren
        # ------------------------------------------------------------------
        def _first(key: str, default: str = "") -> str:
            vals = params.get(key, [])
            return vals[0].strip() if vals else default

        # Freitext-Suche (URL + Titel)
        q = _first("q")

        # Tags (kommagetrennt)
        tags_raw = _first("tags")
        tags_filter = [t.strip() for t in tags_raw.split(",") if t.strip()] \
                      if tags_raw else None

        # Kategorien (kommagetrennt)
        cats_raw = _first("categories")
        categories_filter = [c.strip() for c in cats_raw.split(",") if c.strip()] \
                            if cats_raw else None

        # Fortschrittsfilter
        progress_raw = _first("progress", "all").lower()
        progress_filter = progress_raw if progress_raw in ("open", "closed") else None
        # Build 194: numerischer Schwellenwert für 'open' (0–99).
        # Build 195: progress_direction ('lt'=<, 'gte'=>=).
        progress_threshold = 100
        try:
            _pt = int(_first("progress_threshold", ""))
            if 0 <= _pt <= 99:
                progress_threshold = _pt
        except (ValueError, TypeError):
            pass
        progress_direction = _first("progress_direction", "lt").strip()
        if progress_direction not in ("lt", "gte"):
            progress_direction = "lt"

        # Betrachtungszeitraum (Unix-ms)
        viewed_from: int | None = None
        viewed_to:   int | None = None
        try:
            vf = _first("viewed_from")
            if vf:
                viewed_from = int(vf)
        except ValueError:
            pass
        try:
            vt = _first("viewed_to")
            if vt:
                viewed_to = int(vt)
        except ValueError:
            pass

        # Kontext-Filter (kommagetrennt: user,investigator,actor)
        ctx_raw = _first("context")
        scrape_context_filter = [c.strip() for c in ctx_raw.split(",") if c.strip()] \
                                if ctx_raw else None

        # fetch_failed-Filter
        fetch_failed_raw = _first("fetch_failed", "all").lower()
        fetch_failed_only = (fetch_failed_raw == "true")

        # has_annotations-Filter
        has_ann_raw = _first("has_annotations", "all").lower()
        has_annotations: bool | None = None
        if has_ann_raw == "true":
            has_annotations = True
        elif has_ann_raw == "false":
            has_annotations = False

        # Sortierung (Whitelist)
        sort = _first("sort", "last_viewed_desc").lower()
        if sort not in _VALID_SORT:
            sort = "last_viewed_desc"

        # Paginierung
        try:
            limit = max(1, min(200, int(_first("limit", "50"))))
        except ValueError:
            limit = 50
        try:
            offset = max(0, int(_first("offset", "0")))
        except ValueError:
            offset = 0

        # ------------------------------------------------------------------
        # DB-Abfrage
        # ------------------------------------------------------------------
        try:
            pages = self._bundle.forensic.search_pages(
                limit=limit,
                offset=offset,
                sort=sort,
                q=q,
                scrape_context_filter=scrape_context_filter,
                fetch_failed_only=fetch_failed_only,
                has_annotations=has_annotations,
                progress_filter=progress_filter,
                progress_threshold=progress_threshold,
                progress_direction=progress_direction,
                viewed_from=viewed_from,
                viewed_to=viewed_to,
                tags_filter=tags_filter,
                categories_filter=categories_filter,
            )
        except Exception as exc:
            logger.error("SearchEndpoint: Fehler bei search_pages(): %s", exc)
            body = json.dumps(
                {"error": "Interner Fehler bei der Seitensuche", "status": "error"},
                ensure_ascii=False,
            ).encode("utf-8")
            handler.send_response_body(
                500, body, content_type="application/json; charset=utf-8"
            )
            return

        # ------------------------------------------------------------------
        # BUILD 676 (Vorgang 36dcdfd8): 'total' ist jetzt die WAHRE Zahl.
        #
        # Bis Build 675 stand hier len(pages) - also die Zahl der gelieferten
        # Zeilen. Bei limit=200 meldete der Endpunkt 'total: 200', und ob das
        # die Trefferzahl war oder die erreichte Grenze, war nicht zu
        # unterscheiden. Wer 200 liest, haelt es fuer die Trefferzahl.
        #
        # DREI FELDER STATT EINEM, damit jede Frage eine eigene Antwort hat:
        #   total     - Treffer VOR der Begrenzung. -1 heisst 'nicht
        #               ermittelbar' und ist NICHT dasselbe wie 0.
        #   geliefert - wie viele Zeilen in dieser Antwort stehen.
        #   begrenzt  - hat die Grenze gegriffen? Genau die Frage, die der
        #               alte Wert offenliess.
        #
        # 'total' behaelt seinen Namen: die Oberflaeche liest ihn bereits, und
        # er bedeutet ab jetzt das, was er immer behauptet hat.
        # ------------------------------------------------------------------
        try:
            gesamt = self._bundle.forensic.search_pages(
                limit=limit,
                offset=offset,
                sort=sort,
                q=q,
                scrape_context_filter=scrape_context_filter,
                fetch_failed_only=fetch_failed_only,
                has_annotations=has_annotations,
                progress_filter=progress_filter,
                progress_threshold=progress_threshold,
                progress_direction=progress_direction,
                viewed_from=viewed_from,
                viewed_to=viewed_to,
                tags_filter=tags_filter,
                categories_filter=categories_filter,
                nur_zaehlen=True,
            )
        except Exception as exc:
            # Eine gescheiterte ZAEHLUNG darf die Ergebnisliste nicht
            # verhindern - die Seiten stehen ja schon fest. Sie wird als
            # 'unbekannt' ausgewiesen, nicht als 0.
            logger.error("SearchEndpoint: Zaehlung fehlgeschlagen: %s", exc)
            gesamt = -1

        begrenzt = (gesamt > len(pages)) if gesamt >= 0 else None

        logger.debug(
            "/_forensic/search: sort=%s q='%s' → %d von %s Seiten",
            sort, q, len(pages),
            "unbekannt" if gesamt < 0 else gesamt,
        )

        body_out = json.dumps(
            {
                "pages":     pages,
                "total":     gesamt,
                "geliefert": len(pages),
                "begrenzt":  begrenzt,
                "status":    "ok",
            },
            ensure_ascii=False,
        ).encode("utf-8")
        handler.send_response_body(
            200, body_out, content_type="application/json; charset=utf-8"
        )

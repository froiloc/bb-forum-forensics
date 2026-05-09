# =============================================================================
# forensic_api/placeholders.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# =============================================================================
# Zweck:
#   Endpunkte fuer die Platzhalter-API (Phase 3).
#
#   POST /_forensic/placeholders/resolve
#     Loest alle {{a:query_id}}-Platzhalter in einem Modultext auf.
#     Greift zunachst auf placeholder_cache zurueck. Bei Cache-Miss wird
#     die SQL aus placeholder_queries ausgefuehrt und das Ergebnis gecacht.
#
#   POST /_forensic/placeholders/refresh
#     Invalidiert den Cache fuer eine uid und fuehrt alle aktiven Queries
#     aus templates.placeholder_queries neu aus.
#
#   GET  /_forensic/placeholders/library
#     Liefert die durchsuchbare Bibliothek aller {{a:...}}-Queries.
#     Query-Parameter: ?tags=identitaet&search=username
#
# Platzhalter-Syntax (Typ 'a:'):
#   {{a:query_id|default|description}} oder Kurzform {{a:query_id}}
#   Gruppen: [1] a:  [2] query_id  [3] default (optional)  [4] desc (optional)
#
# Datenbank-Zugriffsmodell:
#   - SQL-Queries aus tdb.placeholder_queries werden gegen fdb (forensic_db)
#     ausgefuehrt. Die forensic_db ist per ATTACH als 'fdb' eingebunden und
#     enthaelt die uid_*-Tabellen.
#   - Cache-Lesen/-Schreiben: evidence_db (placeholder_cache-Tabelle).
#   - Query-Definitionen lesen: templates_db (tdb.placeholder_queries).
#
# Beleg: Bauplan B6 v0.3 §3, Ausdefinitionsgespraech 2026-05-05
# Version: v0.6.144 · Build: 144 · 2026-05-10
# =============================================================================

from __future__ import annotations

import json
import re
import sqlite3
import urllib.parse
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

# Regex fuer {{a:query_id}} und {{a:query_id|default|description}}
# Gruppe 1: query_id (Pflicht)
# Gruppe 2: default-Wert (optional, nach erstem |)
# Gruppe 3: Beschreibung (optional, nach zweitem |)
_PLACEHOLDER_RE = re.compile(
    r"\{\{(?:auto|a):([A-Za-z0-9._-]+)(?:\|([^|}]*))?(?:\|([^}]*))?\}\}"
)


def _json_ok(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def _json_err(msg: str, code: str = "ERROR") -> bytes:
    return json.dumps({"error": msg, "code": code}, ensure_ascii=False).encode("utf-8")


class PlaceholdersEndpoint:
    """
    Endpunkte fuer /_forensic/placeholders/*.
    Beleg: Bauplan B6 v0.3 §3
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

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def handle_resolve(
        self,
        handler: "ForensicRequestHandler",
        body_bytes: bytes,
    ) -> None:
        """POST /_forensic/placeholders/resolve"""
        try:
            data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            handler.send_response_body(
                400, _json_err(f"Ungueltiger JSON-Body: {exc}"),
                content_type="application/json; charset=utf-8",
            )
            return

        body_text = data.get("body", "")
        uid       = data.get("uid", self._context.user_id)

        if not isinstance(body_text, str):
            handler.send_response_body(
                400, _json_err("'body' muss ein String sein."),
                content_type="application/json; charset=utf-8",
            )
            return

        try:
            uid = int(uid)
        except (TypeError, ValueError):
            handler.send_response_body(
                400, _json_err("'uid' muss eine ganze Zahl sein."),
                content_type="application/json; charset=utf-8",
            )
            return

        resolved_text, unresolved, errors, cache_hits = self._resolve_body(
            body_text, uid
        )

        handler.send_response_body(
            200,
            _json_ok({
                "resolved":   resolved_text,
                "unresolved": unresolved,
                "errors":     errors,
                "cache_hits": cache_hits,
            }),
            content_type="application/json; charset=utf-8",
        )

    def handle_refresh(
        self,
        handler: "ForensicRequestHandler",
        body_bytes: bytes,
    ) -> None:
        """POST /_forensic/placeholders/refresh"""
        try:
            data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            handler.send_response_body(
                400, _json_err(f"Ungueltiger JSON-Body: {exc}"),
                content_type="application/json; charset=utf-8",
            )
            return

        uid = data.get("uid", self._context.user_id)
        try:
            uid = int(uid)
        except (TypeError, ValueError):
            handler.send_response_body(
                400, _json_err("'uid' muss eine ganze Zahl sein."),
                content_type="application/json; charset=utf-8",
            )
            return

        refreshed, errors = self._refresh_cache(uid)

        handler.send_response_body(
            200,
            _json_ok({"refreshed": refreshed, "errors": errors}),
            content_type="application/json; charset=utf-8",
        )

    def handle_values(
        self,
        handler: "ForensicRequestHandler",
    ) -> None:
        """
        GET /_forensic/placeholders/values?report_id=<id>

        Liefert die placeholder_values_json aller Bloecke des angegebenen
        Berichts als Dictionary: { block_id: {name: value, ...}, ... }

        Bug 2.53 Fix Build 138: report_id aus Query-Params lesen.
        Vorher wurde immer der erste/aktive Bericht genommen — das ergab
        einen 500-Fehler wenn keine Reports existierten oder der falsche
        Bericht geladen wurde.
        Beleg: Bugfix Build 138, Projektgespraech 2026-05-09
        """
        from urllib.parse import urlparse, parse_qs
        parsed   = urlparse(handler.path)
        params   = parse_qs(parsed.query)
        rid_raw  = params.get("report_id", [None])[0]

        edb = self._bundle.evidence
        result: dict[str, dict] = {}

        if rid_raw:
            try:
                report_id = int(rid_raw)
            except (ValueError, TypeError):
                handler.send_response_body(
                    400,
                    _json_err("'report_id' muss eine ganze Zahl sein", "BAD_PARAM"),
                    content_type="application/json; charset=utf-8",
                )
                return
            blocks = edb.get_blocks_for_report(report_id)
        else:
            # Fallback: aktiven Bericht bestimmen (gleiche Logik wie in report.py)
            reports = edb.get_reports()
            active_report = None
            for r in reports:
                if r.status in ("draft", "submitted"):
                    active_report = r
                    break
            if active_report is None and reports:
                active_report = reports[0]
            blocks = edb.get_blocks_for_report(active_report.id) if active_report else []

        for b in blocks:
            if b.placeholder_values_json:
                try:
                    values = json.loads(b.placeholder_values_json)
                    if isinstance(values, dict):
                        result[b.block_id] = values
                except (json.JSONDecodeError, ValueError):
                    pass
            if b.block_id not in result:
                result[b.block_id] = {}

        handler.send_response_body(
            200,
            _json_ok(result),
            content_type="application/json; charset=utf-8",
        )

    def handle_library(
        self,
        handler: "ForensicRequestHandler",
        params: dict,
    ) -> None:
        """GET /_forensic/placeholders/library?tags=...&search=..."""
        tags   = params.get("tags",   [None])[0]
        search = params.get("search", [None])[0]

        queries = self._bundle.templates.list_queries(
            tags=tags, search=search
        )

        result = [
            {
                "id":          q.id,
                "title":       q.title,
                "description": q.description,
                "tags":        q.tags.split(",") if q.tags else [],
                "return_type": q.return_type,
            }
            for q in queries
        ]

        handler.send_response_body(
            200,
            _json_ok(result),
            content_type="application/json; charset=utf-8",
        )

    # ------------------------------------------------------------------
    # Interne Logik
    # ------------------------------------------------------------------

    def _resolve_body(
        self,
        body: str,
        uid: int,
    ) -> tuple[str, list[str], list[str], list[str]]:
        """
        Ersetzt alle {{a:query_id}}-Vorkommen im Text.

        Returns:
            (resolved_text, unresolved_ids, error_ids, cache_hit_ids)
        """
        unresolved: list[str] = []
        errors:     list[str] = []
        cache_hits: list[str] = []

        def replace_match(m: re.Match) -> str:
            query_id = m.group(1)
            default  = m.group(2) or ""

            # 1. Cache pruefen
            cached = self._bundle.evidence.get_cache_entry(query_id, uid)
            if cached is not None:
                cache_hits.append(query_id)
                return cached

            # 2. Query-Definition laden
            q_rec = self._bundle.templates.get_query(query_id)
            if q_rec is None:
                logger.debug("resolve: query_id '%s' nicht in templates", query_id)
                unresolved.append(query_id)
                return default

            # 3. SQL ausfuehren gegen fdb (forensic_db)
            value = self._execute_query(q_rec.sql_query, uid, query_id, errors)
            if value is None:
                return default

            # 4. In Cache speichern
            self._bundle.evidence.set_cache_entry(query_id, uid, value)
            return value

        resolved = _PLACEHOLDER_RE.sub(replace_match, body)
        return resolved, unresolved, errors, cache_hits

    def _execute_query(
        self,
        sql: str,
        uid: int,
        query_id: str,
        errors: list[str],
    ) -> str | None:
        """
        Fuehrt eine SQL-Query gegen fdb aus.

        Die Queries in placeholder_queries werden per :uid parametrisiert
        und gegen die forensic_db (Alias 'fdb') ausgefuehrt.
        Da die Queries in templates.db als einfache SQL-Strings vorliegen,
        wird der fdb-Praefix eingefuegt wenn die Tabellen nicht qualifiziert sind.

        Returns:
            Ergebnis als String oder None bei Fehler.
        """
        try:
            row = self._bundle.connection.execute(
                sql, {"uid": uid}
            ).fetchone()
            if row is None:
                return ""
            # scalar: erster Wert der ersten Zeile
            val = row[0]
            return str(val) if val is not None else ""
        except sqlite3.OperationalError as exc:
            logger.warning(
                "Platzhalter-Query '%s' fehlgeschlagen: %s", query_id, exc
            )
            errors.append(query_id)
            return None

    def _refresh_cache(self, uid: int) -> tuple[int, list[str]]:
        """
        Invalidiert den Cache fuer uid und fuehrt alle aktiven Queries neu aus.
        Beleg: Bauplan B6 v0.3 §3.2

        Returns:
            (refreshed_count, error_ids)
        """
        # Cache leeren
        self._bundle.evidence.clear_cache_for_uid(uid)

        queries = self._bundle.templates.list_queries()
        errors: list[str] = []
        refreshed = 0

        for q in queries:
            value = self._execute_query(q.sql_query, uid, q.id, errors)
            if value is not None:
                self._bundle.evidence.set_cache_entry(q.id, uid, value)
                refreshed += 1

        logger.info(
            "placeholder_cache aktualisiert: uid=%d, %d Queries, %d Fehler",
            uid, refreshed, len(errors),
        )
        return refreshed, errors

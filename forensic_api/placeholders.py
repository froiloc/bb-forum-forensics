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
# Version: v0.8.495 · Build: 495 · 2026-07-21
# Build 495 (Platzhalter-Neuordnung, Slice 3): case-weite Wiederverwendung von
#   m/o-Ermittlerwerten. GET/POST /_forensic/placeholders/cache lesen/schreiben
#   den placeholder_cache fuer m/o-Platzhalter (Prefill/Writeback, mc-Wunsch).
#   handle_cache_set laesst NUR bekannte m/o-Platzhalter zu (Schutz des
#   {{a:}}-Auto-Caches; Grundregel 1). Kein Schemaeingriff (bestehende Tabelle).
# Build 491 (Platzhalter-Neuordnung, Slice 3): typbewusste Cache-Leerung.
#   _refresh_cache leert NUR die a-Eintraege (clear_cache_for_query_ids)
#   statt pauschal per clear_cache_for_uid — damit m/o-Ermittlerwerte im
#   placeholder_cache (fallweise Wiederverwendung, mc-Wunsch) erhalten bleiben.
#   Loest die 489-Wiedervorlage auf. Beleg: Grundregel 1.
# Build 489 (Platzhalter-Neuordnung): Query-Definitionen kommen aus
#   templates.placeholders (statt placeholder_queries; Migration:
#   management/migrate_templates_placeholders.py). Die library liefert alle
#   Typen a/m/o inkl. validation/validation_type/default_value; der
#   Cache-Refresh fuehrt nur 'a'-Definitionen aus.
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
#   Build 403: {{a:}}-Aufloesung (Cache->Query->SQL->Cache) in den gemeinsamen
#   Kern report_render/auto_query.py ausgelagert (De-Duplizierung gegen
#   report_source.py). _execute_query entfernt; Endpunkt-Verhalten unveraendert.
# =============================================================================

from __future__ import annotations

import json
import re
import urllib.parse
from typing import TYPE_CHECKING

from core.logger import get_logger

# Build 403: gemeinsamer {{a:}}-Aufloesungskern (De-Duplizierung). Bis Build 402
# lag dieselbe Cache->Query->SQL->Cache-Logik zusaetzlich in
# report_render/report_source.py. Jetzt Single Source of Truth.
from report_render.auto_query import (
    AutoQueryResolver,
    STATUS_CACHE_HIT,
    STATUS_NO_QUERY,
    STATUS_SQL_ERROR,
)

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

        body_text    = data.get("body", "")
        uid          = data.get("uid", self._context.subject_id)
        # Bug 2.17 Fix Build 286: return_values=true gibt zusaetzlich ein
        # {query_id: value}-Dict zurueck damit der Client die aufgeloesten
        # Werte als auto:query_id in placeholder_values_json speichern kann.
        # Beleg: Bugfix-Liste 2.17, Projektgespraech 2026-06-07
        return_values = bool(data.get("return_values", False))

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

        resolved_text, unresolved, errors, cache_hits, values = \
            self._resolve_body(body_text, uid, collect_values=return_values)

        result = {
            "resolved":   resolved_text,
            "unresolved": unresolved,
            "errors":     errors,
            "cache_hits": cache_hits,
        }
        if return_values:
            result["values"] = values

        handler.send_response_body(
            200,
            _json_ok(result),
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

        uid = data.get("uid", self._context.subject_id)
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

        # Build 489 (Platzhalter-Neuordnung): die Bibliothek liefert jetzt ALLE
        # Typen (a/m/o) inkl. Validierungsregeln — der Berichts-Editor (Wizard/
        # Chips, Slice 3/Build 491) bezieht seine Definitionen von hier, statt
        # sie nur aus Inline-Token-Parametern zu lesen (DB-Autoritaet,
        # Bauplan Platzhalter_DB §2.3). validation ist KLARTEXT (UTF-8);
        # eine Base64-Kodierung passiert erst im Token-Transport (mc §2.2).
        queries = self._bundle.templates.list_queries(
            tags=tags, search=search
        )

        result = [
            {
                "id":              q.id,
                "title":           q.title,
                "description":     q.description,
                "tags":            q.tags.split(",") if q.tags else [],
                "return_type":     q.return_type,
                "type":            q.type,
                "default_value":   q.default_value,
                "validation":      q.validation,
                "validation_type": q.validation_type,
                "validation_ci":   q.validation_ci,
            }
            for q in queries
        ]

        handler.send_response_body(
            200,
            _json_ok(result),
            content_type="application/json; charset=utf-8",
        )

    def handle_cache_get(
        self,
        handler: "ForensicRequestHandler",
        params: dict,
    ) -> None:
        """
        GET /_forensic/placeholders/cache?ids=a,b,c[&uid=<n>]

        Liefert die fallweise gecachten m/o-Werte fuer die angegebenen
        Platzhalter-IDs als { id: value }. Ohne ids-Parameter -> leeres Objekt
        (der Client kennt die relevanten IDs und fragt gezielt an; ohne Filter
        wuerden auch {{a:}}-Auto-Werte durchgereicht — das ist unerwuenscht).

        Build 495 (Platzhalter-Neuordnung): Grundlage des Prefill der m/o-Felder
        aus evidence_<uid>.db/placeholder_cache (mc-Wunsch, case-weite
        Wiederverwendung).
        """
        uid = params.get("uid", [None])[0]
        uid = int(uid) if uid is not None else self._context.subject_id
        try:
            uid = int(uid)
        except (TypeError, ValueError):
            handler.send_response_body(
                400, _json_err("'uid' muss eine ganze Zahl sein.", "BAD_PARAM"),
                content_type="application/json; charset=utf-8",
            )
            return

        ids_raw = params.get("ids", [None])[0]
        ids = [s for s in (ids_raw.split(",") if ids_raw else []) if s.strip()]

        entries = self._bundle.evidence.get_cache_entries_for_ids(uid, ids)
        handler.send_response_body(
            200, _json_ok(entries),
            content_type="application/json; charset=utf-8",
        )

    def handle_cache_set(
        self,
        handler: "ForensicRequestHandler",
        body_bytes: bytes,
    ) -> None:
        """
        POST /_forensic/placeholders/cache   Body: { "id": "...", "value": "..." }

        Schreibt einen m/o-Ermittlerwert in evidence_<uid>.db/placeholder_cache,
        damit er im Fall wiederverwendet werden kann (Writeback).

        SCHUTZ (Grundregel 1 / Datenintegritaet): Es werden NUR bekannte
        Platzhalter vom Typ m/o zugelassen. Ein 'a'-Auto-Platzhalter darf nicht
        ueberschrieben werden (sein Cache gehoert der Query-Aufloesung), ein
        unbekannter Bezeichner soll den case-weiten Cache nicht verunreinigen.
        Beide Faelle -> HTTP 400, KEIN Schreibvorgang.
        """
        try:
            data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            handler.send_response_body(
                400, _json_err(f"Ungueltiger JSON-Body: {exc}"),
                content_type="application/json; charset=utf-8",
            )
            return

        pid   = data.get("id")
        value = data.get("value", "")
        uid   = data.get("uid", self._context.subject_id)

        if not isinstance(pid, str) or not pid.strip():
            handler.send_response_body(
                400, _json_err("'id' fehlt oder ist leer.", "BAD_PARAM"),
                content_type="application/json; charset=utf-8",
            )
            return
        if not isinstance(value, str):
            handler.send_response_body(
                400, _json_err("'value' muss ein String sein.", "BAD_PARAM"),
                content_type="application/json; charset=utf-8",
            )
            return
        try:
            uid = int(uid)
        except (TypeError, ValueError):
            handler.send_response_body(
                400, _json_err("'uid' muss eine ganze Zahl sein.", "BAD_PARAM"),
                content_type="application/json; charset=utf-8",
            )
            return

        # Nur bekannte m/o-Platzhalter duerfen fallweise wiederverwendet werden.
        rec = self._bundle.templates.get_query(pid)
        if rec is None or rec.type not in ("m", "o"):
            handler.send_response_body(
                400,
                _json_err(
                    "Nur bekannte m/o-Platzhalter koennen case-weit "
                    "wiederverwendet werden.", "NOT_REUSABLE"),
                content_type="application/json; charset=utf-8",
            )
            return

        self._bundle.evidence.set_cache_entry(pid, uid, value)
        logger.info(
            "placeholder_cache Writeback (m/o): id=%s, uid=%d", pid, uid)
        handler.send_response_body(
            200, _json_ok({"ok": True, "id": pid, "stored": True}),
            content_type="application/json; charset=utf-8",
        )

    # ------------------------------------------------------------------
    # Interne Logik
    # ------------------------------------------------------------------

    def _resolve_body(
        self,
        body: str,
        uid: int,
        collect_values: bool = False,
    ) -> tuple[str, list[str], list[str], list[str], dict]:
        """
        Ersetzt alle {{a:query_id}}-Vorkommen im Text.

        Returns:
            (resolved_text, unresolved_ids, error_ids, cache_hit_ids, values)
            values ist leer wenn collect_values=False.
        """
        unresolved: list[str] = []
        errors:     list[str] = []
        cache_hits: list[str] = []
        values:     dict      = {}

        # Build 403: gemeinsamer Kern. write_cache=True erhaelt das bisherige
        # Endpunkt-Verhalten (der Cache wird befuellt).
        auto = AutoQueryResolver(
            self._bundle.evidence, self._bundle.templates,
            self._bundle.connection, write_cache=True,
        )

        def replace_match(m: re.Match) -> str:
            query_id = m.group(1)
            default  = m.group(2) or ""

            res = auto.resolve(query_id, uid)
            if res.status == STATUS_CACHE_HIT:
                cache_hits.append(query_id)
                if collect_values:
                    values[query_id] = res.value
                return res.value
            if res.status == STATUS_NO_QUERY:
                unresolved.append(query_id)
                return default
            if res.status == STATUS_SQL_ERROR:
                errors.append(query_id)
                return default
            # resolved / empty -> Wert einsetzen (und ggf. sammeln)
            if collect_values:
                values[query_id] = res.value
            return res.value

        resolved = _PLACEHOLDER_RE.sub(replace_match, body)
        return resolved, unresolved, errors, cache_hits, values

    def _refresh_cache(self, uid: int) -> tuple[int, list[str]]:
        """
        Invalidiert den Cache fuer uid und fuehrt alle aktiven Queries neu aus.
        Beleg: Bauplan B6 v0.3 §3.2; Build 403: SQL-Ausfuehrung ueber den
        gemeinsamen Kern (AutoQueryResolver.execute_query).

        Returns:
            (refreshed_count, error_ids)
        """
        auto = AutoQueryResolver(
            self._bundle.evidence, self._bundle.templates, self._bundle.connection,
        )
        # Build 489: NUR 'a'-Definitionen ausfuehren. m/o-Eintraege haben
        # hoechstens eine Default-Quelle und gehoeren nicht in den Auto-Refresh.
        queries = self._bundle.templates.list_queries(types=["a"])

        # Build 491 (Slice 3, 489-Wiedervorlage aufgeloest): der Cache darf
        # NICHT mehr pauschal per clear_cache_for_uid() geleert werden. Seit der
        # Platzhalter-Neuordnung koennen im placeholder_cache auch m/o-Werte
        # liegen — fallweise wiederverwendete Ermittler-Eingaben (mc-Wunsch:
        # {{m:}}/{{o:}} referenzieren eine Query auf evidence_<uid>.db/
        # placeholder_cache) oder handverlesene Vorbelegungen. Ein Auto-Refresh
        # iteriert ausschliesslich a-Definitionen und darf daher auch nur DEREN
        # Cache-Eintraege verwerfen. Alles andere waere ein stiller Datenverlust
        # und verstiesse gegen Grundregel 1 (kein Beleg darf still
        # uebersprungen/verworfen werden).
        # Beleg: db/evidence_db.py clear_cache_for_query_ids (Build 491).
        a_ids = [q.id for q in queries]
        self._bundle.evidence.clear_cache_for_query_ids(uid, a_ids)

        errors: list[str] = []
        refreshed = 0

        for q in queries:
            value, ok = auto.execute_query(q.sql_query, uid, q.id)
            if ok:
                self._bundle.evidence.set_cache_entry(q.id, uid, value)
                refreshed += 1
            else:
                errors.append(q.id)

        logger.info(
            "placeholder_cache aktualisiert: uid=%d, %d Queries, %d Fehler",
            uid, refreshed, len(errors),
        )
        return refreshed, errors

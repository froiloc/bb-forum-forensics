# =============================================================================
# report_render/auto_query.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6/7: Berichts-Ausgabe
# =============================================================================
# Zweck:
#   GEMEINSAMER Kern der {{a:query_id}}-Aufloesung (De-Duplizierung, Build 403).
#
#   Vor Build 403 existierte diese Logik ZWEIMAL, was die sicherste Art ist, sie
#   auseinanderlaufen zu lassen (dieselbe Gefahr wie beim Renderer selbst):
#     - forensic_api/placeholders.py: _resolve_body.replace_match + _execute_query
#     - report_render/report_source.py: _resolve_auto
#   Beide fuehren identisch aus: Cache pruefen -> Query-Definition laden ->
#   SQL gegen fdb ausfuehren -> Ergebnis cachen. Genau dieser Pfad lebt jetzt
#   ausschliesslich hier; beide Nutzer delegieren.
#
#   Serverunabhaengig: kein http, kein DatabaseBundle. Bekommt die DB-Wrapper
#   (evidence, templates) und die forensische Verbindung (fdb) injiziert.
#
#   write_cache (NEU/Build 403):
#     True  — der Platzhalter-Endpunkt fuellt den placeholder_cache (bisheriges
#             Verhalten, Bauplan B6 §3).
#     False — der BERICHTS-EXPORT liest den Cache nur, SCHREIBT aber NICHT in
#             evidence_<uid>.db. Das macht den Export streng lese-only und
#             respektiert den Migrationsvorbehalt sauberer als die (gecachte)
#             Zwischenloesung aus Build 399. Beleg: mc-Restpunkt (a).
#
# Statuswerte (fuer die verschiedenen Aufrufer-Semantiken):
#   cache_hit — Wert kam aus dem Cache
#   resolved  — Query lief, nicht-leeres Ergebnis
#   empty     — Query lief, leeres Ergebnis ("")
#   no_query  — keine Query-Definition (bzw. templates fehlt)
#   sql_error — SQL-Fehler oder keine forensische Verbindung
#
# Version: v0.7.403 · Build: 403 · 2026-07-14
# =============================================================================

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Optional

from core.logger import get_logger

logger = get_logger(__name__)

STATUS_CACHE_HIT = "cache_hit"
STATUS_RESOLVED  = "resolved"
STATUS_EMPTY     = "empty"
STATUS_NO_QUERY  = "no_query"
STATUS_SQL_ERROR = "sql_error"

#: Status, bei denen ein Platzhalter als NICHT aufgeloest gilt (Default einsetzen).
UNRESOLVED_STATUSES = frozenset({STATUS_NO_QUERY, STATUS_SQL_ERROR})


@dataclass
class AutoResult:
    """Ergebnis einer {{a:}}-Aufloesung.

    value  — der aufgeloeste String ("" bei leerem Ergebnis) oder None, wenn
             nicht auflösbar (no_query/sql_error).
    status — einer der STATUS_*-Werte.
    """
    value:  Optional[str]
    status: str


class AutoQueryResolver:
    """Kapselt Cache -> Query-Definition -> SQL(fdb) -> Cache fuer {{a:}}.

    Args:
        evidence:     EvidenceDb (placeholder_cache: get_cache_entry/set_cache_entry).
        templates:    TemplatesDb (get_query) — darf None sein (-> no_query).
        forensic_con: sqlite3.Connection mit ATTACH-Alias 'fdb' — darf None sein
                      (-> sql_error, da keine Ausfuehrung moeglich).
        write_cache:  ob erfolgreiche Ergebnisse in den Cache geschrieben werden.
    """

    def __init__(
        self,
        evidence: Any,
        templates: Any,
        forensic_con: Optional[sqlite3.Connection],
        write_cache: bool = True,
    ) -> None:
        self._edb = evidence
        self._tdb = templates
        self._con = forensic_con
        self._write_cache = write_cache

    # ------------------------------------------------------------------
    def execute_query(self, sql: str, uid: int, query_id: str = "") -> tuple[Optional[str], bool]:
        """Fuehrt eine Query gegen fdb aus (OHNE Cache).

        Portierung von placeholders.py:_execute_query (Verhalten unveraendert):
        row None  -> ("", True); Skalar None -> ("", True); sonst (str(val), True).
        OperationalError -> (None, False) + Warnung.

        Returns:
            (value_or_None, ok)
        """
        if self._con is None:
            return None, False
        try:
            row = self._con.execute(sql, {"uid": uid}).fetchone()
        except sqlite3.OperationalError as exc:
            logger.warning("Platzhalter-Query '%s' fehlgeschlagen: %s", query_id, exc)
            return None, False
        if row is None:
            return "", True
        val = row[0]
        return (str(val) if val is not None else ""), True

    # ------------------------------------------------------------------
    def resolve(self, query_id: str, uid: int) -> AutoResult:
        """Volle Aufloesung eines {{a:query_id}} inkl. Cache.

        Reihenfolge identisch zu placeholders.py:_resolve_body.replace_match:
          1. Cache (get_cache_entry) -> cache_hit
          2. Query-Definition (templates.get_query) -> None => no_query
          3. SQL ausfuehren -> Fehler => sql_error
          4. (optional) Cache schreiben; empty/resolved zurueck
        """
        cached = self._edb.get_cache_entry(query_id, uid)
        if cached is not None:
            return AutoResult(cached, STATUS_CACHE_HIT)

        if self._tdb is None:
            return AutoResult(None, STATUS_NO_QUERY)
        q_rec = self._tdb.get_query(query_id)
        if q_rec is None:
            logger.debug("resolve: query_id '%s' nicht in templates", query_id)
            return AutoResult(None, STATUS_NO_QUERY)

        value, ok = self.execute_query(q_rec.sql_query, uid, query_id)
        if not ok:
            return AutoResult(None, STATUS_SQL_ERROR)

        if self._write_cache:
            self._edb.set_cache_entry(query_id, uid, value)
        return AutoResult(value, STATUS_EMPTY if value == "" else STATUS_RESOLVED)

    # ------------------------------------------------------------------
    def resolve_value_or_none(self, query_id: str, uid: int) -> Optional[str]:
        """Bequemer Adapter fuer den Export-Pfad: liefert den Wert ("" moeglich)
        oder None, wenn nicht auflösbar (no_query/sql_error). Der aufrufende
        PlaceholderResolver behandelt None als 'unresolved' (R2)."""
        res = self.resolve(query_id, uid)
        if res.status in UNRESOLVED_STATUSES:
            return None
        return res.value

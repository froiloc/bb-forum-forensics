# =============================================================================
# management/reports/annotation_support_reader.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung Berichtseditor (B6) x Management (B7) — SF-2 (Build 411)
# =============================================================================
# Zweck:
#   Liefert fuer EINEN Bericht die zugrunde liegenden ANNOTATIONEN (Belege),
#   read-only, damit Lektorat (W4) und Chef-Freigabe (W5) Aussagen im Bericht
#   am Beleg verifizieren koennen.
#
#   Beleg-Kette (Feinabnahme v0.1, kartiert 2026-07-14):
#     report_blocks --< report_anchors >-- annotations --(post_id)-->
#     fdb.post_aliases (topic_id, forum_id)
#   D.h. ein Anker (report_anchors) verknuepft einen Block mit genau EINER
#   Annotation (annotations.id); die Annotation traegt die post_id des
#   Forenbeitrags; der Forenkontext (Thema/Unterforum) wird aus fdb.post_aliases
#   aufgeloest.
#
#   Warum eine eigene Klasse (Grundregel 10): reine LESE-Aggregation ueber das
#   read-only ReadonlyReportBundle (SF-1). Kein Schreibpfad, kein neues
#   Datenmodell — die evidence_<uid>.db wird NUR gelesen (Migrationsvorbehalt).
#
# Version: v0.7.411 · Build: 411 · 2026-07-14
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Beleg-Kette EINES Berichts: alle Anker seiner Bloecke + die jeweils
# verankerte Annotation. LEFT JOIN, damit ein Anker, dessen Annotation
# fehlt/verschwunden ist, SICHTBAR bleibt (Grundregel 1: kein stiller Verlust).
_ANCHOR_SQL = (
    "SELECT ra.id AS anchor_id, ra.block_id AS block_id, "
    "       ra.anchor_text AS anchor_text, ra.annotation_id AS annotation_id, "
    "       rb.block_type AS block_type, "
    "       a.category AS a_category, a.text AS a_text, "
    "       a.page_url AS a_page_url, a.post_id AS a_post_id, "
    "       a.element_id AS a_element_id, a.selection_json AS a_selection_json, "
    "       a.created_by AS a_created_by, a.ts AS a_ts, "
    "       a.deleted_at AS a_deleted_at, a.version_nr AS a_version_nr "
    "FROM report_anchors ra "
    "JOIN report_blocks rb ON rb.block_id = ra.block_id "
    "LEFT JOIN annotations a ON a.id = ra.annotation_id "
    "WHERE rb.report_id = ? "
    "ORDER BY rb.block_id ASC, ra.annotation_id ASC"
)

# Identisch zur Query in ForensicDb.resolve_post_alias (db/forensic_db.py:377):
# post_id -> (topic_id, forum_id). Direkt ausgefuehrt, um nicht die volle
# ForensicDb (mit TEMP-VIEW-Aufbau) fuer eine reine Alias-Aufloesung zu bauen.
_ALIAS_SQL = (
    "SELECT topic_id, forum_id FROM fdb.post_aliases WHERE post_id = ?"
)


class AnnotationSupportReader:
    """
    Read-only Aggregator: Bericht -> verankerte Annotationen (+ Forenkontext).

    Erwartet ein bereits geoeffnetes ReadonlyReportBundle (SF-1):
      - bundle.evidence   (EvidenceDb, read_only) fuer die Berichtswahl,
      - bundle.connection  (read-only Hauptverbindung, traegt fdb-ATTACH).
    """

    def __init__(self, bundle: Any) -> None:
        self._evidence = bundle.evidence
        self._con: sqlite3.Connection = bundle.connection

    # ------------------------------------------------------------------
    def select_report_id(self, report_id: Optional[int]) -> Optional[int]:
        """
        Berichtswahl analog §4.1 (mc): explizite report_id hat Vorrang; sonst
        der Bericht mit der hoechsten sequence_nr, Gleichstand -> juengstes
        created_at. None, wenn kein Bericht existiert.
        """
        if report_id is not None:
            rec = self._evidence.get_report(report_id)
            return rec.id if rec else None
        reports = self._evidence.get_reports()
        if not reports:
            return None
        chosen = max(reports, key=lambda r: (r.sequence_nr, r.created_at))
        return chosen.id

    # ------------------------------------------------------------------
    def read(self, report_id: Optional[int]) -> Optional[Dict[str, Any]]:
        """
        Baut die Support-Ansicht. Gibt None zurueck, wenn kein Bericht existiert
        (Aufrufer -> 404). Enthaelt KEINE Bewertung, nur die Belege.
        """
        rid = self.select_report_id(report_id)
        if rid is None:
            return None
        rep = self._evidence.get_report(rid)

        rows = self._con.execute(_ANCHOR_SQL, (rid,)).fetchall()
        alias_cache: Dict[int, Tuple[Optional[int], Optional[int]]] = {}
        items = []
        for r in rows:
            post_id = r["a_post_id"]
            topic_id: Optional[int] = None
            forum_id: Optional[int] = None
            if post_id is not None:
                topic_id, forum_id = self._resolve_alias(int(post_id),
                                                         alias_cache)
            # 'missing': der Anker zeigt auf eine Annotation, die es nicht (mehr)
            # gibt -> sichtbar machen, nicht verschweigen (Grundregel 1).
            missing = r["a_category"] is None
            items.append({
                "anchor_id": int(r["anchor_id"]),
                "block_id": r["block_id"],
                "block_type": r["block_type"],
                "anchor_text": r["anchor_text"],
                "annotation_id": int(r["annotation_id"]),
                "missing": bool(missing),
                "category": r["a_category"],
                "text": r["a_text"],
                "page_url": r["a_page_url"],
                "post_id": (int(post_id) if post_id is not None else None),
                "topic_id": topic_id,
                "forum_id": forum_id,
                "element_id": r["a_element_id"],
                "selection_json": r["a_selection_json"],
                "created_by": r["a_created_by"],
                "created_at": (int(r["a_ts"]) if r["a_ts"] is not None else None),
                "deleted": (r["a_deleted_at"] is not None),
                "version_nr": (int(r["a_version_nr"])
                               if r["a_version_nr"] is not None else None),
            })

        return {
            "report_id": rid,
            "report_title": rep.title if rep else None,
            "report_status": rep.status if rep else None,
            "report_type": rep.report_type if rep else None,
            "sequence_nr": rep.sequence_nr if rep else None,
            "anchor_count": len(items),
            "items": items,
        }

    # ------------------------------------------------------------------
    def _resolve_alias(
        self, post_id: int,
        cache: Dict[int, Tuple[Optional[int], Optional[int]]],
    ) -> Tuple[Optional[int], Optional[int]]:
        """post_id -> (topic_id, forum_id) aus fdb.post_aliases; (None,None),
        wenn fdb fehlt oder der Post dort nicht gefuehrt ist."""
        if post_id in cache:
            return cache[post_id]
        res: Tuple[Optional[int], Optional[int]] = (None, None)
        try:
            row = self._con.execute(_ALIAS_SQL, (post_id,)).fetchone()
            if row is not None:
                res = (int(row["topic_id"]), int(row["forum_id"]))
        except sqlite3.Error as exc:
            # fdb nicht angebunden / post_aliases fehlt -> kein Forenkontext.
            logger.debug("post_alias(%d) nicht aufloesbar: %s", post_id, exc)
            res = (None, None)
        cache[post_id] = res
        return res

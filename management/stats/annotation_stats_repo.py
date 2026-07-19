# =============================================================================
# management/stats/annotation_stats_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-2D)
# =============================================================================
# Zweck (Idee 12 — Annotations-Tortenstatistik):
#   Aggregiert die Annotationen der Faelle nach KATEGORIE und TAG als Grundlage
#   einer Torten-/Verteilungssicht (ECharts, B450). Die Annotationen liegen je
#   Fall in evidence_<uid>.db; diese werden AUSSCHLIESSLICH READ-ONLY geoeffnet
#   (Migrationsvorbehalt — die evidence_<uid>.db wird nie geschrieben).
#
#   SCOPE: 'alle' -> alle Faelle (Fuehrung/StA); 'eigene' -> nur die dem/der
#   Ermittler:in zugewiesenen Faelle. Die Fallmenge kommt aus coordinator.db
#   (Tabelle cases), der Zaehlstoff aus den evidence_<uid>.db.
#
#   KEIN STILLES UEBERSPRINGEN (GR1): Faelle ohne vorhandene evidence_<uid>.db
#   werden GEZAEHLT und ausgewiesen (cases_without_evidence) — nicht lautlos
#   weggelassen. Soft-geloeschte Annotationen (deleted_at IS NOT NULL) zaehlen
#   nicht mit.
#
#   Pfadaufloesung wie ReadonlyReportBundle/ReportsRepo: <evidence_dir>/
#   evidence_<uid>.db, geoeffnet mit 'file:…?mode=ro'. now-Zeit injizierbar.
#
# Version: v0.7.449 · Build: 449 · 2026-07-19
# =============================================================================

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


def aggregate_annotations(
        rows: Iterable[Tuple[Optional[str], Optional[str]]]
) -> Tuple[Dict[str, int], Dict[str, int], int]:
    """
    REINE Aggregation ueber (category, tags_json)-Paare. Liefert
    (by_category, by_tag, total).

    - category None/'' -> Sammelschluessel '(ohne Kategorie)' (kein stilles
      Verschlucken; GR1).
    - tags_json ist ein JSON-Array von Strings; None/leer -> keine Tags.
      Nicht parsebares tags_json -> die Annotation zaehlt weiter in Kategorie
      und Gesamt, ihre Tags landen im Sammelschluessel '(ungueltige Tags)'.
    """
    by_category: Dict[str, int] = {}
    by_tag: Dict[str, int] = {}
    total = 0
    for category, tags_json in rows:
        total += 1
        cat = category if (category is not None and category != "") \
            else "(ohne Kategorie)"
        by_category[cat] = by_category.get(cat, 0) + 1
        if not tags_json:
            continue
        try:
            tags = json.loads(tags_json)
        except (ValueError, TypeError):
            by_tag["(ungueltige Tags)"] = by_tag.get("(ungueltige Tags)", 0) + 1
            continue
        if not isinstance(tags, list):
            by_tag["(ungueltige Tags)"] = by_tag.get("(ungueltige Tags)", 0) + 1
            continue
        for t in tags:
            if not isinstance(t, str) or t == "":
                continue
            by_tag[t] = by_tag.get(t, 0) + 1
    return by_category, by_tag, total


class AnnotationStatsRepo:
    """Aggregiert Annotationen der Faelle (read-only) nach Kategorie und Tag."""

    def __init__(self, coordinator_con: sqlite3.Connection,
                 evidence_dir: str) -> None:
        self._con = coordinator_con
        self._evidence_dir = Path(evidence_dir)

    def _case_user_ids(self, scope: str, person_id: Optional[int]) -> List[int]:
        """user_ids der Faelle im Scope. 'eigene' -> assigned_to == person_id."""
        if scope == "eigene":
            if person_id is None:
                return []
            cur = self._con.execute(
                "SELECT user_id FROM cases WHERE assigned_to=? ORDER BY user_id",
                (person_id,))
        else:
            cur = self._con.execute(
                "SELECT user_id FROM cases ORDER BY user_id")
        return [int(r[0]) for r in cur.fetchall()]

    def _evidence_path(self, uid: int) -> Path:
        return self._evidence_dir / ("evidence_%d.db" % uid)

    def _read_case_annotations(self, uid: int
                               ) -> Optional[List[Tuple[Optional[str], Optional[str]]]]:
        """
        (category, tags_json) je nicht-geloeschter Annotation aus
        evidence_<uid>.db. None, wenn die Datei fehlt (Aufrufer zaehlt sie als
        cases_without_evidence). Rein lesend ('mode=ro').
        """
        path = self._evidence_path(uid)
        if not path.exists():
            return None
        con = sqlite3.connect("file:%s?mode=ro" % path.resolve(), uri=True)
        try:
            cur = con.execute(
                "SELECT category, tags_json FROM annotations "
                "WHERE deleted_at IS NULL")
            return [(r[0], r[1]) for r in cur.fetchall()]
        finally:
            con.close()

    def compute(self, *, scope: str = "alle",
                person_id: Optional[int] = None,
                now: Optional[int] = None) -> Dict[str, object]:
        now = int(time.time()) if now is None else int(now)
        uids = self._case_user_ids(scope, person_id)

        by_category: Dict[str, int] = {}
        by_tag: Dict[str, int] = {}
        annotations_total = 0
        cases_with_evidence = 0
        cases_without_evidence = 0

        for uid in uids:
            rows = self._read_case_annotations(uid)
            if rows is None:
                cases_without_evidence += 1
                continue
            cases_with_evidence += 1
            c_cat, c_tag, c_total = aggregate_annotations(rows)
            annotations_total += c_total
            for k, v in c_cat.items():
                by_category[k] = by_category.get(k, 0) + v
            for k, v in c_tag.items():
                by_tag[k] = by_tag.get(k, 0) + v

        # Absteigend nach Haeufigkeit sortierte Listen (stabile Zweitordnung nach
        # Schluessel) — direkt fuer die Tortensicht verwendbar.
        def _sorted(d: Dict[str, int]) -> List[Dict[str, object]]:
            return [{"key": k, "count": v}
                    for k, v in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))]

        return {
            "scope": "eigene" if scope == "eigene" else "alle",
            "generated_at": now,
            "cases_total": len(uids),
            "cases_with_evidence": cases_with_evidence,
            "cases_without_evidence": cases_without_evidence,
            "annotations_total": annotations_total,
            "by_category": _sorted(by_category),
            "by_tag": _sorted(by_tag),
        }

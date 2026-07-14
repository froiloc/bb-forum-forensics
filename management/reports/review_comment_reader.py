# =============================================================================
# management/reports/review_comment_reader.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — SF-3 (Build 412): Union-Leser der Review-Kommentare
# =============================================================================
# Zweck:
#   "Lesen am Ort": Kommentare liegen je kommentierender Person in DEREN eigener
#   Addendum-Datei (evidence_<uid>_<pid>.db). Dieser Leser vereinigt die
#   Kommentare ALLER Prueferinnen zu einem Fall/Bericht — read-only, ohne je
#   eine dieser Dateien zu schreiben (Regel "nie zwei Schreiber pro Datei").
#
#   Fundort: ./data/evidence/addenda/<bucket>/<uid>/evidence_<uid>_*.db
#   (Glob je uid; der Bucket wird deterministisch berechnet — siehe
#   db/review_addendum_db.bucket_for).
#
# Version: v0.7.412 · Build: 412 · 2026-07-14
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from db.review_addendum_db import bucket_for

logger = logging.getLogger(__name__)


class ReviewCommentReader:
    """Vereinigt die review_comments ALLER Prueferinnen eines Falls (read-only)."""

    def __init__(self, evidence_dir: str, uid: int) -> None:
        self._uid = int(uid)
        self._dir = (
            Path(evidence_dir) / "addenda" / bucket_for(uid) / str(int(uid))
        )

    # ------------------------------------------------------------------
    def read(self, report_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Alle Kommentare (optional auf report_id gefiltert), sortiert nach
        (block_id, created_at). Existiert noch keine Addendum-Datei, ist die
        Liste leer (kein Fehler).
        """
        if not self._dir.exists():
            return []
        merged: List[Dict[str, Any]] = []
        pattern = "evidence_%d_*.db" % self._uid
        for path in sorted(self._dir.glob(pattern)):
            merged.extend(self._read_one(path, report_id))
        # Stabile Gesamtsortierung ueber alle Dateien hinweg.
        merged.sort(key=lambda c: (str(c.get("block_id") or ""),
                                   int(c.get("created_at") or 0)))
        return merged

    # ------------------------------------------------------------------
    def _read_one(self, path: Path,
                  report_id: Optional[int]) -> List[Dict[str, Any]]:
        try:
            con = sqlite3.connect("file:%s?mode=ro" % path.resolve(), uri=True)
            con.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            logger.warning("Addendum '%s' nicht lesbar: %s", path.name, exc)
            return []
        try:
            if report_id is None:
                rows = con.execute("SELECT * FROM review_comments").fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM review_comments WHERE report_id = ?",
                    (int(report_id),),
                ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as exc:
            # Datei ohne erwartete Tabelle -> sichtbar machen, nicht raten.
            logger.warning("Addendum '%s' ohne review_comments: %s",
                           path.name, exc)
            return []
        finally:
            con.close()

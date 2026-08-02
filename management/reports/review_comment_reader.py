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
from typing import Any, Dict, List, Optional, Tuple

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

        Bequemer Zugang fuer Aufrufer, die den Fehlerbefund nicht auswerten.
        Wer ihn braucht, nimmt read_mit_befund().
        """
        kommentare, _fehler = self.read_mit_befund(report_id)
        return kommentare

    # ------------------------------------------------------------------
    def read_mit_befund(
        self, report_id: Optional[int] = None
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        """
        Wie read(), liefert aber ZUSAETZLICH die Liste der Addendum-Dateien,
        die nicht gelesen werden konnten.

        WARUM ES DIESE ZWEITE FASSUNG GIBT (Build 661):
          Bis Build 660 protokollierte der Leser einen Lesefehler nur
          (logger.warning) und gab dem Aufrufer eine leere Liste. Fuer den
          Aufrufer war 'diese Pruefer:in hat nichts angemerkt' damit nicht von
          'ihre Datei liess sich nicht oeffnen' zu unterscheiden — dieselbe
          Ununterscheidbarkeit, die Grundregel 1 verbietet. Im Cockpit war das
          hinnehmbar, weil dort noch andere Anzeichen sichtbar sind. Im
          Berichtseditor ist es das NICHT: die verfassende Person schliesst
          aus 'keine Anmerkung' auf 'nichts zu tun' und gibt den Vermerk frei.

          Rueckgabe je Fehler: {"datei": <name>, "grund": <text>}.
        """
        if not self._dir.exists():
            return [], []
        merged: List[Dict[str, Any]] = []
        fehler: List[Dict[str, str]] = []
        pattern = "evidence_%d_*.db" % self._uid
        for path in sorted(self._dir.glob(pattern)):
            zeilen, grund = self._read_one(path, report_id)
            merged.extend(zeilen)
            if grund is not None:
                fehler.append({"datei": path.name, "grund": grund})
        # Stabile Gesamtsortierung ueber alle Dateien hinweg.
        merged.sort(key=lambda c: (str(c.get("block_id") or ""),
                                   int(c.get("created_at") or 0)))
        return merged, fehler

    # ------------------------------------------------------------------
    def _read_one(self, path: Path, report_id: Optional[int]
                  ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Liest EINE Addendum-Datei. -> (zeilen, grund_des_fehlschlags|None)."""
        try:
            con = sqlite3.connect("file:%s?mode=ro" % path.resolve(), uri=True)
            con.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            logger.warning("Addendum '%s' nicht lesbar: %s", path.name, exc)
            return [], "nicht zu oeffnen: %s" % exc
        try:
            if report_id is None:
                rows = con.execute("SELECT * FROM review_comments").fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM review_comments WHERE report_id = ?",
                    (int(report_id),),
                ).fetchall()
            return [dict(r) for r in rows], None
        except sqlite3.Error as exc:
            # Datei ohne erwartete Tabelle -> sichtbar machen, nicht raten.
            logger.warning("Addendum '%s' ohne review_comments: %s",
                           path.name, exc)
            return [], "ohne Tabelle review_comments: %s" % exc
        finally:
            con.close()

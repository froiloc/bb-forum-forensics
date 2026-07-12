# =============================================================================
# management/reports/report_sealer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Berichts-Versiegelung
# =============================================================================
# ReportSealer — bildet den KANONISCHEN INHALTSHASH eines Berichts und dessen
# statisches Abbild (Snapshot) aus einer evidence_<uid>.db. Rein lesend.
#
# HASH-KONVENTION (uebernommen aus core/startup_checks.py, mc 2026-07-10:
#   "wie beim Hashen der forensic_<uid>.db — das Rad nicht neu erfinden"):
#     - NICHT ueber die Datei-Bytes. Ein dateibasierter Hash ist bei SQLite
#       nicht stabil (Seitenstruktur aendert sich bei jedem Schreibvorgang,
#       VACUUM, Checkpoint — auch ohne inhaltliche Aenderung).
#     - Sondern ueber einen KANONISCHEN INHALTSDUMP:
#         Zeilenformat  "<tabelle>:<repr(col1)>|<repr(col2)>|...\n" als UTF-8
#         Tabellen      in fester Reihenfolge (siehe _TABLES)
#         Zeilen        in fester, inhaltlich begruendeter Ordnung
#       -> deterministisch und reproduzierbar.
#
# UMFANG DES SIEGELS (mc 2026-07-10): NUR die Teile, die den FERTIGEN BERICHT
#   ausmachen:
#     reports            — der Berichtskopf (ohne 'status': der Status aendert
#                          sich DURCH die Freigabe selbst; er darf den Hash
#                          nicht beeinflussen, sonst wuerde das Siegel im
#                          Moment des Siegelns ungueltig — selbstreferenzieller
#                          Konflikt, dieselbe Begruendung wie beim Ausschluss
#                          des sha256-Eintrags in forensic_meta).
#     report_blocks      — die Inhaltsbloecke, in der ANZEIGE-REIHENFOLGE aus
#                          report_block_order (sort_index) — die Reihenfolge ist
#                          Teil des Berichts.
#     report_anchors     — die Verankerungen an den Beweis-Annotationen.
#   NICHT im Siegel: report_comments (Arbeitsmaterial, kein Berichtsinhalt) und
#   report_approvals/report_opened (Metadaten der Abnahme selbst).
#
# Version: v0.7.377 · Build: 377 · 2026-07-10
# =============================================================================

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class ReportSealError(Exception):
    """Bericht nicht lesbar/nicht vorhanden — nie stillschweigend ignorieren."""


# Berichtskopf OHNE 'status' (siehe Kopfkommentar: selbstreferenzieller Konflikt).
_REPORT_COLS = ("id", "report_type", "sequence_nr", "title", "created_by",
                "created_at")

_BLOCK_COLS = ("block_id", "report_id", "author", "created_at", "updated_at",
               "block_type", "block_data", "placeholder_values_json",
               "module_id")

_ANCHOR_COLS = ("id", "block_id", "annotation_id", "anchor_text", "created_at")


class ReportSealer:
    """Berechnet Inhaltshash und Abbild eines Berichts (read-only)."""

    def __init__(self, evidence_db: Path) -> None:
        self._path = Path(evidence_db)

    # ---------------------------------------------------------------- public
    def snapshot(self, report_id: int) -> Dict[str, Any]:
        """
        Statisches Abbild des Berichts + Inhaltshash.
        -> {report, blocks, anchors, content_sha256}
        Raises ReportSealError, wenn der Bericht nicht existiert.
        """
        con = self._open()
        try:
            report = self._read_report(con, report_id)
            blocks = self._read_blocks(con, report_id)
            anchors = self._read_anchors(con, blocks)
        finally:
            con.close()

        digest = self._hash(report, blocks, anchors)
        return {
            "report": report,
            "blocks": blocks,
            "anchors": anchors,
            "content_sha256": digest,
        }

    def content_hash(self, report_id: int) -> str:
        """Nur der Hash (fuer die Nachpruefung)."""
        return self.snapshot(report_id)["content_sha256"]

    def status_of(self, report_id: int) -> Optional[str]:
        """Aktueller Status des Berichts (fuer Vorbedingungen)."""
        con = self._open()
        try:
            row = con.execute("SELECT status FROM reports WHERE id=?",
                              (report_id,)).fetchone()
            return row[0] if row else None
        finally:
            con.close()

    # ------------------------------------------------------------- internals
    def _open(self) -> sqlite3.Connection:
        if not self._path.exists():
            raise ReportSealError("evidence-DB fehlt: %s" % self._path)
        try:
            return sqlite3.connect("file:%s?mode=ro" % self._path, uri=True)
        except sqlite3.Error as exc:
            raise ReportSealError("evidence-DB nicht lesbar: %s" % exc)

    def _read_report(self, con, report_id: int) -> Dict[str, Any]:
        cols = ", ".join('"%s"' % c for c in _REPORT_COLS)
        row = con.execute("SELECT %s FROM reports WHERE id=?" % cols,
                          (report_id,)).fetchone()
        if row is None:
            raise ReportSealError("Bericht %s nicht gefunden." % report_id)
        return dict(zip(_REPORT_COLS, row))

    def _read_blocks(self, con, report_id: int) -> List[Dict[str, Any]]:
        # ANZEIGE-Reihenfolge: report_block_order.sort_index. Bloecke ohne
        # Order-Eintrag sind ein Datenfehler — sie werden NICHT verschwiegen,
        # sondern deterministisch ans Ende gehaengt (nach block_id), damit sie
        # im Siegel erscheinen (Grundregel 1: kein Beleg faellt weg).
        cols = ", ".join('b."%s"' % c for c in _BLOCK_COLS)
        rows = con.execute(
            "SELECT %s FROM report_blocks b "
            "LEFT JOIN report_block_order o ON o.block_id = b.block_id "
            "WHERE b.report_id = ? "
            "ORDER BY (o.sort_index IS NULL), o.sort_index ASC, b.block_id ASC"
            % cols, (report_id,)).fetchall()
        return [dict(zip(_BLOCK_COLS, r)) for r in rows]

    def _read_anchors(self, con, blocks) -> List[Dict[str, Any]]:
        if not blocks:
            return []
        ids = [b["block_id"] for b in blocks]
        marks = ",".join("?" for _ in ids)
        cols = ", ".join('"%s"' % c for c in _ANCHOR_COLS)
        rows = con.execute(
            "SELECT %s FROM report_anchors WHERE block_id IN (%s) "
            "ORDER BY id ASC" % (cols, marks), ids).fetchall()
        return [dict(zip(_ANCHOR_COLS, r)) for r in rows]

    @staticmethod
    def _hash(report, blocks, anchors) -> str:
        """
        Kanonischer Dump -> SHA-256. Zeilenformat und repr()-Kodierung wie in
        core/startup_checks.py._compute_content_sha256 (bewusst identisch).
        """
        sha = hashlib.sha256()

        def line(table: str, values) -> None:
            sha.update((table + ":" + "|".join(repr(v) for v in values)
                        + "\n").encode("utf-8"))

        line("reports", [report[c] for c in _REPORT_COLS])
        for b in blocks:
            line("report_blocks", [b[c] for c in _BLOCK_COLS])
        for a in anchors:
            line("report_anchors", [a[c] for c in _ANCHOR_COLS])
        return sha.hexdigest()

    @staticmethod
    def snapshot_json(snapshot: Dict[str, Any]) -> str:
        """Abbild als JSON (sortierte Schluessel -> stabil)."""
        return json.dumps(
            {"report": snapshot["report"], "blocks": snapshot["blocks"],
             "anchors": snapshot["anchors"]},
            ensure_ascii=False, sort_keys=True)

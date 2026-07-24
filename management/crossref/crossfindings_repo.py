# =============================================================================
# management/crossref/crossfindings_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Querfunde (AP-2A)
# =============================================================================
# Zweck (Idee 6, Frontend/Backend AP-2A(3), Build 474):
#   REIN LESENDE Meta-Uebersicht ueber die Querfunde ("Fund ueber B im Fall A").
#   Die eigentliche Erfassung + der Transport laufen bereits VOLLAUTOMATISCH auf
#   Evidence-DB-Ebene (forensic_api/cross_annotation_integrator.py) ueber die
#   coordinator-Tabelle 'pending_cross_annotations'. Diese Sicht DUPLIZIERT das
#   NICHT — sie fuehrt nur zusammen, was dort bereits entsteht, fuer die
#   Koordination (welcher Fund betrifft welches Ziel-Subjekt, von wem, offen
#   oder integriert). Der aktive Rueckkanal (Idee 7) ist ein SPAETERER Build.
#
# Substrat 'pending_cross_annotations'. Spalten: source_iid, target_uid,
#   db_path, annotation_local_id, created_at, integrated_at.
#   STAND SEIT BUILD 506 (Governance A4, Migration M023): die Tabelle ist in
#   die MIGRATIONSKETTE ueberfuehrt und traegt zusaetzlich die VIRTUELL
#   GENERIERTE Spalte 'subject_id AS (target_uid)'. Dieses Repo liest seither
#   'subject_id' NATIV. (Bis Build 505 lag die DDL nur zur Laufzeit in
#   db/coordinator_db.py und der Schluessel hiess ausschliesslich 'target_uid'
#   — mc 2026-07-20: "wie-es-ist lesen", als eigener Governance-Punkt vermerkt.)
#
# VERTRAEGLICHKEITS-ZWEIG: Fehlt die generierte Spalte (coordinator.db vor
#   M023, etwa eine Alt-Fixture), faellt das Repo BELEGT auf 'target_uid'
#   zurueck und protokolliert das — statt mit 'no such column' zu scheitern.
#   Die AUSGABEFORM ist in beiden Faellen identisch ('subject_id'), damit das
#   Frontend aus Build 478 unveraendert gueltig bleibt.
#
# NORMALISIERUNG: Das Ziel-Subjekt eines Fundes wird in der Ausgabe als
#   'subject_id' gefuehrt (Prepper-Schema, konsistent mit dem restlichen
#   Werkzeug). Best-effort-Joins auf person (Quell-Ermittler) und
#   cases (Fall-Kontext). GRUNDREGEL 1: nicht zuordenbare Zeilen werden
#   NICHT verschluckt, sondern mit leerem Kontext (source_name=None,
#   has_case=false) sichtbar gemacht.
#
# FEHLT DAS SUBSTRAT (Tabelle nicht vorhanden), ist das ein Betriebsfehler,
#   KEIN Leerbefund: list()/counts() werfen dann CrossrefError, statt still eine
#   leere Uebersicht vorzutaeuschen (Grundregel 1).
#
# REIN LESEND: kein Writer, kein audit_log-Schreibpfad (nichts wird veraendert).
#
# Version: v0.8.474 · Build: 474 · 2026-07-20
# =============================================================================

import logging
import sqlite3
from typing import Any, Dict, List

from management.crossref.identified_subject_repo import CrossrefError

logger = logging.getLogger(__name__)


class CrossfindingsRepo:
    """Lesezugriff auf die Querfund-Meta-Uebersicht (pending_cross_annotations)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row

    # ------------------------------------------------------------------ intern
    def _table_present(self) -> bool:
        return self._con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='pending_cross_annotations'").fetchone() is not None

    def _require_substrate(self) -> None:
        if not self._table_present():
            raise CrossrefError(
                "pending_cross_annotations fehlt — coordinator.db nicht "
                "vollstaendig initialisiert. Kein stiller Leerbefund.")

    def _subject_column(self) -> str:
        """
        Liefert den Spaltennamen des Ziel-Subjekts: 'subject_id' (kanonisch ab
        M023) oder 'target_uid' (Alt-Stand). PRAGMA table_xinfo statt
        table_info — table_info VERSCHWEIGT generierte Spalten, und
        'subject_id' IST eine (Build 506).
        """
        try:
            rows = self._con.execute(
                "PRAGMA table_xinfo(pending_cross_annotations)").fetchall()
        except sqlite3.DatabaseError:
            rows = []
        names = {str(r[1]) for r in rows}
        if "subject_id" in names:
            return "subject_id"
        logger.info(
            "pending_cross_annotations ohne generierte Spalte 'subject_id' "
            "(coordinator.db vor Migration M023) — lese ersatzweise "
            "'target_uid'. Die Ausgabeform bleibt unveraendert.")
        return "target_uid"

    # ------------------------------------------------------------------- Lesen
    def list(self, only_open: bool = False) -> List[Dict[str, Any]]:
        """Querfunde, offene zuerst, dann neueste zuerst. only_open filtert auf
        noch nicht integrierte Funde."""
        self._require_substrate()
        col = self._subject_column()
        where = "WHERE pca.integrated_at IS NULL" if only_open else ""
        # Der Spaltenname stammt AUSSCHLIESSLICH aus _subject_column() und ist
        # damit auf zwei feste Literale beschraenkt — keine Fremdeingabe, also
        # keine Injektionsflaeche. Er wird als 'target_subject' ausgegeben,
        # damit _as_dict nur EINEN Namen kennen muss.
        sql = (
            "SELECT pca.id, pca.source_iid, pca.%s AS target_subject, "
            "       pca.db_path, pca.annotation_local_id, pca.created_at, "
            "       pca.integrated_at, "
            "       p.display_name AS source_name, "
            "       c.subject_id  AS case_subject "
            "FROM pending_cross_annotations pca "
            "LEFT JOIN person p ON p.id = pca.source_iid "
            "LEFT JOIN cases  c ON c.subject_id = pca.%s "
            % (col, col)
            + where +
            " ORDER BY (pca.integrated_at IS NOT NULL) ASC, "
            "          pca.created_at DESC, pca.id DESC"
        )
        rows = self._con.execute(sql).fetchall()
        return [self._as_dict(r) for r in rows]

    def counts(self) -> Dict[str, int]:
        """Gesamt / offen / integriert."""
        self._require_substrate()
        row = self._con.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN integrated_at IS NULL THEN 1 ELSE 0 END) AS offen, "
            "SUM(CASE WHEN integrated_at IS NOT NULL THEN 1 ELSE 0 END) "
            "  AS integriert "
            "FROM pending_cross_annotations").fetchone()
        return {
            "total": int(row["total"] or 0),
            "offen": int(row["offen"] or 0),
            "integriert": int(row["integriert"] or 0),
        }

    # ------------------------------------------------------------------ intern
    @staticmethod
    def _as_dict(r: sqlite3.Row) -> Dict[str, Any]:
        integ = r["integrated_at"]
        return {
            "id": int(r["id"]),
            # Ausgabename ist IMMER 'subject_id' (Prepper-Schema) — ob die
            # Quelle die generierte Spalte (ab M023) oder das alte
            # 'target_uid' war, ist fuer den Aufrufer unerheblich.
            "subject_id": int(r["target_subject"]),
            "source_iid": int(r["source_iid"]),
            # None, wenn der Quell-Ermittler nicht (mehr) zuordenbar ist —
            # die Zeile bleibt trotzdem sichtbar (Grundregel 1).
            "source_name": r["source_name"],
            "has_case": r["case_subject"] is not None,
            "annotation_local_id": r["annotation_local_id"],
            "db_path": r["db_path"],
            "created_at": int(r["created_at"]),
            "integrated_at": (int(integ) if integ is not None else None),
            "status": ("integriert" if integ is not None else "offen"),
        }

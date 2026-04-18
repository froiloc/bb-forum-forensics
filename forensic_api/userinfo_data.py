# =============================================================================
# forensic_api/userinfo_data.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Nutzerinfo-Tab
# =============================================================================
# Zweck:
#   Endpunkt GET /_forensic/userinfo/data
#   Liefert alle dynamischen Blöcke für Fenster 2 als JSON-Envelope.
#   Wird beim Laden von Fenster 2 und bei SSE-Events aufgerufen (§5.2 Bauplan B4).
#
# Response-Schema (§5.2 Bauplan B4):
#   {
#     "annotation_counts": { "CAT_176": 0, ... },
#     "annotations_total": 27,
#     "last_annotation": { "ts": ..., "investigator": "..." } | null,
#     "investigation_status": { "status": "...", "priority": ..., ... } | null,
#     "report_status": { "has_draft": ..., "last_edit_ts": ..., ... },
#     "unreferenced_annotations": 3
#   }
#
# Datenbankzugriff:
#   evidence_<uid>.db (READ): annotation_counts, report_paragraphs, editor_locks
#   coordinator.db    (READ): scrape_jobs (status, priority, assigned_to)
#   Keine Schreibzugriffe.
#
# Neue Datei — Baustelle 4.
# Version: v0.1.0 · Build: 012 · 2026-04-14
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


class UserinfoDataEndpoint:
    """
    Endpunkt GET /_forensic/userinfo/data

    Aggregiert dynamische Ermittlungsdaten aus evidence_db und coordinator.db.
    Kein Schreibzugriff — reine Leseoperation.
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

    def handle(self, handler: "ForensicRequestHandler") -> None:
        """
        Verarbeitet GET /_forensic/userinfo/data.

        Args:
            handler: ForensicRequestHandler-Instanz.
        """
        edb = self._bundle.evidence

        # Annotationszähler je Kategorie
        ann_counts = edb.get_annotation_counts_by_category()
        annotations_total = sum(ann_counts.values())
        last_ann = edb.get_last_annotation_info()

        # Vollständigkeitsprüfung (§8.4 Bauplan B4)
        unreferenced = edb.get_unreferenced_annotation_count()

        # Ermittlungsstatus aus coordinator.db (READ-ONLY)
        investigation_status = self._get_investigation_status()

        # Berichtsstatus aus evidence_db
        report_status = edb.get_report_status()

        payload = {
            "annotation_counts":        ann_counts,
            "annotations_total":        annotations_total,
            "last_annotation":          last_ann,
            "investigation_status":     investigation_status,
            "report_status":            report_status,
            "unreferenced_annotations": unreferenced,
        }

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(
            200, body, content_type="application/json; charset=utf-8"
        )
        logger.debug("/_forensic/userinfo/data: %d Annotationen, unreferenziert=%d",
                     annotations_total, unreferenced)

    def _get_investigation_status(self) -> "dict | None":
        """
        Liest den Ermittlungsstatus für den aktuellen Nutzer aus coordinator.db.
        Gibt None zurück wenn coordinator.db nicht verfügbar.

        Die Spalte 'note' in scrape_jobs ist optional (ALTER TABLE nachgerüstet).
        Die Query wird defensiv aufgebaut: note wird nur selektiert wenn die
        Spalte existiert.
        Beleg: Projektgespräch 2026-04-18 — Bugfix 'no such column: j.note'.
        """
        if self._bundle.coordinator is None:
            return None

        try:
            con = self._bundle.forensic._con  # Verbindung mit cdb-ATTACH

            # Prüfen ob 'note'-Spalte in scrape_jobs existiert
            cols = {
                row[1]
                for row in con.execute("PRAGMA cdb.table_info(scrape_jobs)")
            }
            note_select = ", j.note" if "note" in cols else ", NULL AS note"

            row = con.execute(
                "SELECT j.status, j.priority, "
                "       i.system_username AS assigned_to"
                + note_select +
                " FROM cdb.scrape_jobs j "
                "LEFT JOIN cdb.investigators i ON i.id = j.assigned_to "
                "WHERE j.user_id = ? "
                "ORDER BY j.created_at DESC LIMIT 1",
                (self._context.user_id,),
            ).fetchone()

            if row is None:
                return None

            return {
                "status":      str(row["status"]) if row["status"] else None,
                "priority":    int(row["priority"]) if row["priority"] is not None else None,
                "assigned_to": str(row["assigned_to"]) if row["assigned_to"] else None,
                "note":        str(row["note"]) if row["note"] else None,
            }
        except Exception as exc:
            logger.warning("_get_investigation_status: Fehler: %s", exc)
            return None

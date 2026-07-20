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
# Version: v0.7.469 · Build: 469 · 2026-07-20
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
#   Build 390: BUGFIX — JOIN ging auf die seit M005 nicht mehr existierende
#   Tabelle 'investigators' (jetzt 'person'); der Fehler wurde still zu
#   'nicht zugewiesen'. Siehe _get_investigation_status().
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

        Baustelle 7 (Build 307): Quelle ist die autoritative Fallakte cdb.cases
        (1:1 zur subject_id) statt der 'neuesten' scrape_jobs-Zeile.

        ── BUGFIX Build 390 (gemessen, mc 2026-07-12) ────────────────────────
        Der JOIN ging auf **cdb.investigators**. Diese Tabelle gibt es seit
        Migration M005 (Build 342) NICHT MEHR — sie heisst seither `person`.

        Wirkung des Fehlers (schwerwiegend, weil UNSICHTBAR): der JOIN warf
        "no such table: cdb.investigators", der breite `except` machte daraus
        eine Log-Warnung und ein `return None`, und die Karte
        "Ermittlungskoordination" zeigte dem Ermittler seither IMMER
        "nicht zugewiesen" — unabhaengig davon, wie der Fall tatsaechlich
        zugewiesen war. Kein Absturz, keine Meldung in der Oberflaeche.

        Das ist genau der Fall, den GRUNDREGEL 1 verbietet: ein Fehlschlag darf
        nicht still uebersprungen werden. Deshalb zwei Aenderungen:
          1. JOIN auf `cdb.person` (die Tabelle, die es gibt).
          2. Der Fehlerfall wird nicht mehr zu None geschluckt, sondern als
             {"error": ...} an die Oberflaeche gereicht. Die Karte kann dann
             "Status nicht lesbar: <Grund>" anzeigen statt einer Luege.
        ──────────────────────────────────────────────────────────────────────
        """
        if self._bundle.coordinator is None:
            # KEIN Fehler: ohne coordinator.db gibt es schlicht keine Fallakte.
            # Das ist ein Betriebszustand, kein Fehlschlag.
            return None

        try:
            con = self._bundle.forensic._con  # Verbindung mit cdb-ATTACH

            row = con.execute(
                "SELECT c.status, c.priority, "
                "       p.system_username AS assigned_to, c.note "
                "FROM cdb.cases c "
                "LEFT JOIN cdb.person p ON p.id = c.assigned_to "
                "WHERE c.subject_id = ?",
                (self._context.subject_id,),
            ).fetchone()

            if row is None:
                # Fall NICHT in der Fallakte — das ist eine echte Aussage,
                # kein Fehler (der Fall wurde noch nicht aufgenommen).
                return None

            return {
                "status":      str(row["status"]) if row["status"] else None,
                "priority":    int(row["priority"]) if row["priority"] is not None else None,
                "assigned_to": str(row["assigned_to"]) if row["assigned_to"] else None,
                "note":        str(row["note"]) if row["note"] else None,
            }
        except Exception as exc:
            # NICHT MEHR STILL (Grundregel 1): der Fehler wird protokolliert UND
            # an die Oberflaeche gereicht. Ein "nicht zugewiesen", das in
            # Wahrheit ein Datenbankfehler ist, waere ein Fehlbeleg.
            logger.error("_get_investigation_status: Fallakte nicht lesbar: %s",
                         exc)
            return {"error": str(exc)}

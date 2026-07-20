# =============================================================================
# forensic_api/cross_annotation_integrator.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 3: Toolbar
# =============================================================================
# Zweck:
#   Integriert ausstehende Fremd-Annotationen aus Transportdateien
#   (evidence_<uid2>_<iid>.db) in die Ziel-Datenbank (evidence_<uid2>.db).
#
#   Wird aufgerufen:
#     - Beim Serverstart (einmalig, synchron)
#     - Stündlich im Hintergrundthread
#     - Manuell via POST /_forensic/sync_incoming
#
# Ablauf pro pending_cross_annotations-Eintrag:
#   1. Transportdatei oeffnen (evidence_<uid2>_<iid>.db)
#   2. Annotation anhand annotation_local_id lesen
#   3. Zugehoerige Page (page_url) aus Transportdatei lesen (voller BLOB)
#   4. Beides in evidence_<uid2>.db schreiben (save_annotation + save_page)
#   5. mark_integrated() in coordinator.db
#   6. Transportdatei optional loeschen wenn alle Eintraege integriert
#
# Forensische Garantien:
#   - Transportdatei wird erst geloescht nachdem mark_integrated() erfolgreich
#   - Fehler bei einzelnen Eintraegen unterbrechen nicht den Rest
#   - Idempotent: wiederholter Aufruf schadet nicht
#
# Beleg: Projektgespraech 2026-05-12 — Bug 2.78 (BS3).
# Version: v0.7.469 · Build: 469 · 2026-07-20
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# =============================================================================

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

# Polling-Intervall in Sekunden (1 Stunde)
_POLL_INTERVAL_S = 3600


class CrossAnnotationIntegrator:
    """
    Integriert Fremd-Annotationen aus Transportdateien in die Ziel-evidence_db.
    Beleg: Projektgespraech 2026-05-12 — Bug 2.78 (BS3).
    """

    def __init__(
        self,
        bundle:  "DatabaseBundle",
        context: "ResolvedContext",
        config:  "ConfigLoader",
    ) -> None:
        self._bundle  = bundle
        self._context = context
        self._config  = config
        self._stop    = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Oeffentliche API
    # ------------------------------------------------------------------

    def run_once(self) -> dict:
        """
        Fuehrt einen einmaligen Integrationsdurchlauf aus.
        Gibt Statistik-Dict zurueck: {integrated, skipped, errors}.
        """
        target_uid = self._context.subject_id
        if target_uid is None:
            logger.debug("CrossAnnotationIntegrator: kein subject_id — uebersprungen")
            return {"integrated": 0, "skipped": 0, "errors": 0}

        cdb = self._bundle.coordinator
        if cdb is None:
            logger.debug("CrossAnnotationIntegrator: coordinator.db nicht verfuegbar")
            return {"integrated": 0, "skipped": 0, "errors": 0}

        try:
            pending = cdb.get_pending_for_uid(target_uid)
        except Exception as exc:
            logger.warning("CrossAnnotationIntegrator: get_pending_for_uid fehlgeschlagen: %s", exc)
            return {"integrated": 0, "skipped": 0, "errors": 1}

        if not pending:
            logger.debug("CrossAnnotationIntegrator: keine ausstehenden Eintraege fuer uid=%d", target_uid)
            return {"integrated": 0, "skipped": 0, "errors": 0}

        logger.info(
            "CrossAnnotationIntegrator: %d ausstehende Eintraege fuer uid=%d",
            len(pending), target_uid,
        )

        stats = {"integrated": 0, "skipped": 0, "errors": 0}
        for entry in pending:
            ok = self._integrate_entry(entry)
            if ok is True:
                stats["integrated"] += 1
                try:
                    cdb.mark_integrated(entry["id"])
                except Exception as exc:
                    logger.error(
                        "CrossAnnotationIntegrator: mark_integrated(%d) fehlgeschlagen: %s",
                        entry["id"], exc,
                    )
            elif ok is None:
                stats["skipped"] += 1
            else:
                stats["errors"] += 1

        logger.info(
            "CrossAnnotationIntegrator: Durchlauf abgeschlossen — "
            "integriert=%d, uebersprungen=%d, Fehler=%d",
            stats["integrated"], stats["skipped"], stats["errors"],
        )
        return stats

    def start_background_polling(self) -> None:
        """Startet den stuendlichen Hintergrundthread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._polling_loop,
            name="CrossAnnotationPoller",
            daemon=True,
        )
        self._thread.start()
        logger.info("CrossAnnotationIntegrator: Hintergrundpolling gestartet (%ds Intervall)",
                    _POLL_INTERVAL_S)

    def stop(self) -> None:
        """Stoppt den Hintergrundthread."""
        self._stop.set()

    # ------------------------------------------------------------------
    # Interne Methoden
    # ------------------------------------------------------------------

    def _polling_loop(self) -> None:
        """Hintergrundschleife: laeuft bis stop() aufgerufen wird."""
        while not self._stop.wait(timeout=_POLL_INTERVAL_S):
            try:
                self.run_once()
            except Exception as exc:
                logger.error("CrossAnnotationIntegrator: Polling-Fehler: %s", exc)

    def _integrate_entry(self, entry: dict) -> bool | None:
        """
        Integriert einen einzelnen pending_cross_annotations-Eintrag.

        Returns:
            True  — erfolgreich integriert
            None  — uebersprungen (Transportdatei fehlt oder Annotation nicht gefunden)
            False — Fehler
        """
        db_path = Path(entry["db_path"])
        local_id = entry["annotation_local_id"]

        if not db_path.exists():
            logger.warning(
                "CrossAnnotationIntegrator: Transportdatei fehlt: '%s' — uebersprungen",
                db_path,
            )
            return None

        try:
            transport_con = sqlite3.connect(str(db_path))
            transport_con.row_factory = sqlite3.Row
        except Exception as exc:
            logger.error(
                "CrossAnnotationIntegrator: Transportdatei kann nicht geoeffnet werden: %s",
                exc,
            )
            return False

        try:
            return self._copy_annotation(transport_con, local_id, db_path)
        finally:
            transport_con.close()

    def _copy_annotation(
        self,
        transport_con: sqlite3.Connection,
        local_id: str,
        db_path: Path,
    ) -> bool | None:
        """
        Liest Annotation + Page aus Transportdatei und schreibt beides
        in die lokale evidence_db.
        """
        # --- Annotation aus Transportdatei lesen ---
        ann_row = transport_con.execute(
            "SELECT page_url, element_id, category, text, ts, investigator_id, "
            "       selection_json, tags_json, local_id, post_id, created_by, actual_uid "
            "FROM annotations "
            "WHERE local_id = ? AND deleted_at IS NULL "
            "ORDER BY version_nr DESC LIMIT 1",
            (local_id,),
        ).fetchone()

        if ann_row is None:
            logger.warning(
                "CrossAnnotationIntegrator: Annotation local_id=%r nicht in '%s' — uebersprungen",
                local_id, db_path,
            )
            return None

        page_url = str(ann_row["page_url"])

        # --- Page-BLOB aus Transportdatei lesen ---
        page_row = transport_con.execute(
            "SELECT url_canonical, html_blob, http_status, scrape_context, "
            "       fetched_at, title, in_scope "
            "FROM pages WHERE url_canonical = ? LIMIT 1",
            (page_url,),
        ).fetchone()

        # Falls pages-Tabelle anders heisst (forensic_db-Kompatibilitaet)
        if page_row is None:
            try:
                page_row = transport_con.execute(
                    "SELECT url_canonical, html_blob, http_status, scrape_context, "
                    "       fetched_at, title, in_scope "
                    "FROM pages WHERE url_canonical = ? LIMIT 1",
                    (page_url,),
                ).fetchone()
            except sqlite3.OperationalError:
                pass

        # --- In lokale evidence_db schreiben ---
        edb = self._bundle.evidence

        # Page eintragen falls vorhanden und noch nicht bekannt
        if page_row is not None:
            try:
                self._ensure_page_in_evidence(edb, page_row)
            except Exception as exc:
                logger.warning(
                    "CrossAnnotationIntegrator: Page-Import fehlgeschlagen "
                    "(page_url=%r): %s — Annotation wird trotzdem importiert",
                    page_url, exc,
                )

        # Annotation eintragen
        try:
            edb.save_annotation(
                page_url=page_url,
                category=str(ann_row["category"]),
                text=str(ann_row["text"]),
                element_id=ann_row["element_id"],
                investigator_id=ann_row["investigator_id"],
                selection_json=ann_row["selection_json"],
                tags_json=ann_row["tags_json"],
                local_id=local_id,
                post_id=ann_row["post_id"],
                created_by=str(ann_row["created_by"] or ""),
                actual_uid=ann_row["actual_uid"],
            )
            logger.info(
                "CrossAnnotationIntegrator: Annotation local_id=%r integriert (page=%r)",
                local_id, page_url,
            )
            return True
        except Exception as exc:
            logger.error(
                "CrossAnnotationIntegrator: save_annotation fehlgeschlagen "
                "(local_id=%r): %s",
                local_id, exc,
            )
            return False

    def _ensure_page_in_evidence(self, edb, page_row) -> None:
        """
        Schreibt die Page in die evidence_db wenn sie noch nicht vorhanden ist.
        evidence_db hat keine eigene pages-Tabelle im Standard-Schema —
        wir legen eine an falls noetig (cross_pages).
        Beleg: Projektgespraech 2026-05-12 — voller BLOB fuer XPath-Konsistenz.
        """
        url = str(page_row["url_canonical"])

        # cross_pages-Tabelle sicherstellen (einmalig, idempotent)
        edb._con.execute(
            """
            CREATE TABLE IF NOT EXISTS cross_pages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                url_canonical   TEXT    NOT NULL UNIQUE,
                html_blob       BLOB,
                http_status     INTEGER,
                scrape_context  TEXT,
                fetched_at      INTEGER,
                title           TEXT,
                in_scope        INTEGER NOT NULL DEFAULT 1,
                imported_at     INTEGER NOT NULL
            )
            """
        )
        edb._con.execute(
            "CREATE INDEX IF NOT EXISTS cp_url_idx ON cross_pages (url_canonical)"
        )

        # Eintragen wenn noch nicht vorhanden
        existing = edb._con.execute(
            "SELECT id FROM cross_pages WHERE url_canonical = ?", (url,)
        ).fetchone()
        if existing:
            return

        edb._con.execute(
            "INSERT INTO cross_pages "
            "(url_canonical, html_blob, http_status, scrape_context, "
            " fetched_at, title, in_scope, imported_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                url,
                bytes(page_row["html_blob"]) if page_row["html_blob"] else None,
                page_row["http_status"],
                page_row["scrape_context"],
                page_row["fetched_at"],
                page_row["title"],
                page_row["in_scope"],
                int(time.time()),
            ),
        )
        edb._con.commit()
        logger.debug("CrossAnnotationIntegrator: Page importiert: %r", url)

# =============================================================================
# db/evidence_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Kapselt alle Schreiboperationen in die evidence_<uid>.db (Haupt-DB).
#   Protokolliert Seitenbesuche, Viewport-Events und Annotationen des
#   Ermittlers. Kapselt außerdem Lesezugriffe auf dieselben Tabellen
#   (für Statusanzeigen und Berichtsvorbereitung).
#
# Modi:
#   Normal (job/cli): Schreibt direkt in die Haupt-evidence_db.
#   Support:          Schreibt in die lokale TEMP-DB (Haupt-DB der Verbindung).
#                     Die Unterscheidung ist rein logisch — das Routing
#                     erfolgt durch connection_manager.py, nicht hier.
#                     evidence_db.py schreibt immer in die Haupt-DB der
#                     übergebenen Verbindung, unabhängig vom Modus.
#
# Tabellen (werden beim Init angelegt wenn nicht vorhanden):
#   page_visits     — Seitenaufrufe durch Ermittler
#   viewport_events — Welche Post-Elemente wie lange sichtbar waren
#   annotations     — Kategorisierte Ermittlungsnotizen
#
# Forensische Relevanz:
#   Diese Tabellen sind Ermittlungsdokumentation, kein Beweismittel.
#   Beweismittel liegen in forensic_<uid>.db (READ-ONLY, unveränderlich).
#   evidence_db dokumentiert, WAS der Ermittler getan und bewertet hat.
#
# Annotationskategorien (6):
#   CAT_PERSON   — Persönliche Identifikationsmerkmale
#   CAT_LOCATION — Ortsangaben
#   CAT_176      — Relevanz für §§ 176, 176a StGB
#   CAT_184      — Relevanz für §§ 184b, 184c StGB
#   CAT_VICTIM   — Hinweise auf mögliche Opfer
#   CAT_OTHER    — Sonstige ermittlungsrelevante Beobachtungen
#
# Abhängigkeiten: sqlite3, time — ausschließlich Stdlib
# Version: v0.1.0 · Build: 007 · 2026-04-10
# =============================================================================

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)

# Zulässige Annotationskategorien — unveränderliche Menge
VALID_CATEGORIES = frozenset({
    "CAT_PERSON",
    "CAT_LOCATION",
    "CAT_176",
    "CAT_184",
    "CAT_VICTIM",
    "CAT_OTHER",
})

# DDL für die evidence_db-Tabellen.
# Wird beim Init ausgeführt wenn Tabellen noch nicht existieren.
_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS page_visits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    page_url        TEXT NOT NULL,
    scrape_context  TEXT NOT NULL,
    ts              INTEGER NOT NULL,
    investigator_id INTEGER
);

CREATE TABLE IF NOT EXISTS viewport_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    page_url        TEXT NOT NULL,
    element_id      TEXT,
    visible_ms      INTEGER NOT NULL,
    ts_enter        INTEGER NOT NULL,
    ts_leave        INTEGER NOT NULL,
    investigator_id INTEGER
);

CREATE TABLE IF NOT EXISTS annotations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    page_url        TEXT NOT NULL,
    element_id      TEXT,
    category        TEXT NOT NULL,
    text            TEXT NOT NULL DEFAULT '',
    ts              INTEGER NOT NULL,
    investigator_id INTEGER
);

CREATE INDEX IF NOT EXISTS pv_url_idx   ON page_visits (page_url);
CREATE INDEX IF NOT EXISTS ve_url_idx   ON viewport_events (page_url);
CREATE INDEX IF NOT EXISTS ann_url_idx  ON annotations (page_url);
CREATE INDEX IF NOT EXISTS ann_cat_idx  ON annotations (category);
"""


@dataclass
class PageVisitRecord:
    """Repräsentiert einen Seitenbesuch-Eintrag."""
    id:              int
    page_url:        str
    scrape_context:  str
    ts:              int
    investigator_id: Optional[int]


@dataclass
class AnnotationRecord:
    """Repräsentiert eine Annotation."""
    id:              int
    page_url:        str
    element_id:      Optional[str]
    category:        str
    text:            str
    ts:              int
    investigator_id: Optional[int]


class EvidenceDbError(Exception):
    """Wird geworfen bei ungültigen Eingaben (z.B. unbekannte Kategorie)."""


class EvidenceDb:
    """
    Kapselt alle Schreib- und Lesezugriffe auf die evidence_db.

    Verwendung:
        edb = EvidenceDb(con)
        edb.log_page_visit("/forum/viewtopic.php?id=42", "user", investigator_id=3)
        edb.save_annotation(
            page_url="/forum/viewtopic.php?id=42",
            element_id="p12345",
            category="CAT_PERSON",
            text="Erwähnt Vorname 'Klaus'",
            investigator_id=3,
        )
    """

    def __init__(self, con: sqlite3.Connection) -> None:
        """
        Initialisiert EvidenceDb und legt Tabellen an falls nicht vorhanden.

        Args:
            con: Geöffnete sqlite3.Connection. Im Normalmodus zeigt das
                 auf evidence_<uid>.db als Haupt-DB. Im Support-Modus
                 auf die lokale TEMP-DB. In beiden Fällen identisch.
        """
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._setup_schema()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_schema(self) -> None:
        """Legt Tabellen und Indizes an falls nicht vorhanden. Idempotent."""
        try:
            self._con.executescript(_SCHEMA_DDL)
            self._con.commit()
            logger.debug("evidence_db Schema initialisiert (oder bereits vorhanden)")
        except sqlite3.OperationalError as exc:
            raise sqlite3.OperationalError(
                f"evidence_db Schema konnte nicht initialisiert werden: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Seitenbesuche
    # ------------------------------------------------------------------

    def log_page_visit(
        self,
        page_url: str,
        scrape_context: str,
        investigator_id: Optional[int] = None,
        ts: Optional[int] = None,
    ) -> int:
        """
        Protokolliert einen Seitenbesuch.

        Wird von blob_handler.py aufgerufen, sobald toolbar.js den BLOB
        erfolgreich geladen hat (nicht beim Shell-Load).

        Args:
            page_url:        Normalisierte kanonische URL der aufgerufenen Seite.
            scrape_context:  scrape_context der Seite (aus PageRecord).
            investigator_id: investigators.id des aktuellen Ermittlers.
            ts:              Unix-Timestamp in Sekunden. Default: jetzt.

        Returns:
            id des neuen page_visits-Eintrags.
        """
        if ts is None:
            ts = int(time.time())

        cursor = self._con.execute(
            "INSERT INTO page_visits (page_url, scrape_context, ts, investigator_id) "
            "VALUES (?, ?, ?, ?)",
            (page_url, scrape_context, ts, investigator_id),
        )
        self._con.commit()
        logger.debug(
            "page_visit protokolliert: '%s' (context=%s, investigator=%s)",
            page_url, scrape_context, investigator_id,
        )
        return cursor.lastrowid

    def get_page_visits(self, page_url: str) -> list[PageVisitRecord]:
        """
        Gibt alle Seitenbesuche für eine URL zurück.

        Args:
            page_url: Normalisierte URL.

        Returns:
            Liste von PageVisitRecord, chronologisch aufsteigend.
        """
        rows = self._con.execute(
            "SELECT id, page_url, scrape_context, ts, investigator_id "
            "FROM page_visits WHERE page_url = ? ORDER BY ts ASC",
            (page_url,),
        ).fetchall()
        return [
            PageVisitRecord(
                id=int(r["id"]),
                page_url=str(r["page_url"]),
                scrape_context=str(r["scrape_context"]),
                ts=int(r["ts"]),
                investigator_id=int(r["investigator_id"]) if r["investigator_id"] is not None else None,
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Viewport-Events
    # ------------------------------------------------------------------

    def save_viewport_event(
        self,
        page_url: str,
        element_id: Optional[str],
        visible_ms: int,
        ts_enter: int,
        ts_leave: int,
        investigator_id: Optional[int] = None,
    ) -> int:
        """
        Speichert ein Viewport-Event (Element war sichtbar).

        Wird von forensic_api/viewport.py aufgerufen, wenn toolbar.js
        Viewport-Events als Batch sendet.

        Args:
            page_url:        Normalisierte URL der Seite.
            element_id:      DOM-ID des Elements (z.B. 'p12345'), oder None.
            visible_ms:      Sichtbarkeitsdauer in Millisekunden.
            ts_enter:        Unix-Timestamp ms: Eintritt in den Viewport.
            ts_leave:        Unix-Timestamp ms: Austritt aus dem Viewport.
            investigator_id: investigators.id des Ermittlers.

        Returns:
            id des neuen viewport_events-Eintrags.
        """
        if visible_ms < 0:
            raise EvidenceDbError(
                f"visible_ms muss >= 0 sein, erhalten: {visible_ms}"
            )
        if ts_leave < ts_enter:
            raise EvidenceDbError(
                f"ts_leave ({ts_leave}) darf nicht vor ts_enter ({ts_enter}) liegen"
            )

        cursor = self._con.execute(
            "INSERT INTO viewport_events "
            "(page_url, element_id, visible_ms, ts_enter, ts_leave, investigator_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (page_url, element_id, visible_ms, ts_enter, ts_leave, investigator_id),
        )
        self._con.commit()
        logger.debug(
            "viewport_event: '%s' element=%s, %d ms sichtbar",
            page_url, element_id, visible_ms,
        )
        return cursor.lastrowid

    def save_viewport_batch(
        self,
        events: list[dict],
        investigator_id: Optional[int] = None,
    ) -> int:
        """
        Speichert mehrere Viewport-Events in einer Transaktion.

        Jedes Event-Dict muss enthalten:
          page_url, element_id (oder None), visible_ms, ts_enter, ts_leave

        Args:
            events:          Liste von Event-Dicts.
            investigator_id: investigators.id des Ermittlers.

        Returns:
            Anzahl gespeicherter Events.
        """
        if not events:
            return 0

        rows = []
        for ev in events:
            visible_ms = int(ev.get("visible_ms", 0))
            ts_enter   = int(ev.get("ts_enter", 0))
            ts_leave   = int(ev.get("ts_leave", 0))
            if visible_ms < 0 or ts_leave < ts_enter:
                logger.warning(
                    "Ungültiges Viewport-Event übersprungen: %s", ev
                )
                continue
            rows.append((
                str(ev["page_url"]),
                ev.get("element_id"),
                visible_ms,
                ts_enter,
                ts_leave,
                investigator_id,
            ))

        self._con.executemany(
            "INSERT INTO viewport_events "
            "(page_url, element_id, visible_ms, ts_enter, ts_leave, investigator_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        self._con.commit()
        logger.debug("viewport_batch: %d Events gespeichert", len(rows))
        return len(rows)

    # ------------------------------------------------------------------
    # Annotationen
    # ------------------------------------------------------------------

    def save_annotation(
        self,
        page_url: str,
        category: str,
        text: str,
        element_id: Optional[str] = None,
        investigator_id: Optional[int] = None,
        ts: Optional[int] = None,
    ) -> int:
        """
        Speichert eine Annotation.

        Args:
            page_url:        Normalisierte URL der annotierten Seite.
            category:        Eine der sechs VALID_CATEGORIES.
            text:            Freitext des Ermittlers.
            element_id:      DOM-ID des annotierten Elements (z.B. 'p12345').
            investigator_id: investigators.id des Ermittlers.
            ts:              Unix-Timestamp. Default: jetzt.

        Returns:
            id des neuen annotations-Eintrags.

        Raises:
            EvidenceDbError: Wenn category nicht in VALID_CATEGORIES.
        """
        if category not in VALID_CATEGORIES:
            raise EvidenceDbError(
                f"Ungültige Annotationskategorie: '{category}'. "
                f"Zulässige Werte: {sorted(VALID_CATEGORIES)}"
            )
        if ts is None:
            ts = int(time.time())

        cursor = self._con.execute(
            "INSERT INTO annotations "
            "(page_url, element_id, category, text, ts, investigator_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (page_url, element_id, category, text, ts, investigator_id),
        )
        self._con.commit()
        logger.debug(
            "Annotation gespeichert: '%s' [%s] element=%s",
            page_url, category, element_id,
        )
        return cursor.lastrowid

    def get_annotations(self, page_url: str) -> list[AnnotationRecord]:
        """
        Gibt alle Annotationen für eine URL zurück.

        Args:
            page_url: Normalisierte URL.

        Returns:
            Liste von AnnotationRecord, chronologisch aufsteigend.
        """
        rows = self._con.execute(
            "SELECT id, page_url, element_id, category, text, ts, investigator_id "
            "FROM annotations WHERE page_url = ? ORDER BY ts ASC",
            (page_url,),
        ).fetchall()
        return [
            AnnotationRecord(
                id=int(r["id"]),
                page_url=str(r["page_url"]),
                element_id=str(r["element_id"]) if r["element_id"] is not None else None,
                category=str(r["category"]),
                text=str(r["text"]),
                ts=int(r["ts"]),
                investigator_id=int(r["investigator_id"]) if r["investigator_id"] is not None else None,
            )
            for r in rows
        ]

    def get_all_annotations(self) -> list[AnnotationRecord]:
        """
        Gibt alle Annotationen der DB zurück. Für Berichtserstellung.

        Returns:
            Liste aller AnnotationRecord, nach URL und Timestamp sortiert.
        """
        rows = self._con.execute(
            "SELECT id, page_url, element_id, category, text, ts, investigator_id "
            "FROM annotations ORDER BY page_url ASC, ts ASC"
        ).fetchall()
        return [
            AnnotationRecord(
                id=int(r["id"]),
                page_url=str(r["page_url"]),
                element_id=str(r["element_id"]) if r["element_id"] is not None else None,
                category=str(r["category"]),
                text=str(r["text"]),
                ts=int(r["ts"]),
                investigator_id=int(r["investigator_id"]) if r["investigator_id"] is not None else None,
            )
            for r in rows
        ]

    def annotation_count(self) -> int:
        """Anzahl aller gespeicherten Annotationen. Für Statusanzeigen."""
        try:
            row = self._con.execute(
                "SELECT COUNT(*) FROM annotations"
            ).fetchone()
            return int(row[0]) if row else 0
        except sqlite3.OperationalError:
            return 0

# =============================================================================
# db/evidence_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Kapselt alle Schreiboperationen in die evidence_<uid>.db (Haupt-DB).
#
# Änderungen gegenüber Build 010 (Baustelle 3 — §13 Bauplan):
#   - annotations: Neue Spalten selection_json, tags_json, local_id,
#                  post_id, created_by (alle DEFAULT NULL / DEFAULT '').
#   - _migrate_schema(): Fügt fehlende Spalten via ALTER TABLE nach
#     (rückwärtskompatibel — vorhandene DBs werden on-the-fly migriert).
#   - save_annotation(): Nimmt neue Felder entgegen.
#   - get_annotations() / get_all_annotations(): Liefern neue Felder zurück.
#   - AnnotationRecord: Um neue Felder erweitert.
#
# Abhängigkeiten: sqlite3, time, json — ausschließlich Stdlib
# Version: v0.1.0 · Build: 011 · 2026-04-13
# =============================================================================

from __future__ import annotations

import json
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
_SCHEMA_DDL = """\
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
    investigator_id INTEGER,
    selection_json  TEXT DEFAULT NULL,
    tags_json       TEXT DEFAULT NULL,
    local_id        TEXT DEFAULT NULL,
    post_id         INTEGER DEFAULT NULL,
    created_by      TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS pv_url_idx   ON page_visits (page_url);
CREATE INDEX IF NOT EXISTS ve_url_idx   ON viewport_events (page_url);
CREATE INDEX IF NOT EXISTS ann_url_idx  ON annotations (page_url);
CREATE INDEX IF NOT EXISTS ann_cat_idx  ON annotations (category);
"""

# Spalten, die in älteren evidence_db-Instanzen (Build <= 010) fehlen können.
_MIGRATION_COLUMNS: list[tuple[str, str, str]] = [
    ("annotations", "selection_json", "TEXT DEFAULT NULL"),
    ("annotations", "tags_json",      "TEXT DEFAULT NULL"),
    ("annotations", "local_id",       "TEXT DEFAULT NULL"),
    ("annotations", "post_id",        "INTEGER DEFAULT NULL"),
    ("annotations", "created_by",     "TEXT NOT NULL DEFAULT ''"),
]


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
    """Repräsentiert eine Annotation (Build 011: erweitert um Baustelle-3-Felder)."""
    id:              int
    page_url:        str
    element_id:      Optional[str]
    category:        str
    text:            str
    ts:              int
    investigator_id: Optional[int]
    selection_json:  Optional[str] = None
    tags_json:       Optional[str] = None
    local_id:        Optional[str] = None
    post_id:         Optional[int] = None
    created_by:      str           = ""


class EvidenceDbError(Exception):
    """Wird geworfen bei ungültigen Eingaben (z.B. unbekannte Kategorie)."""


class EvidenceDb:
    """Kapselt alle Schreib- und Lesezugriffe auf die evidence_db."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._setup_schema()
        self._migrate_schema()

    # ------------------------------------------------------------------
    # Setup & Migration
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

    def _migrate_schema(self) -> None:
        """Ergänzt fehlende Spalten in älteren evidence_db-Instanzen (idempotent)."""
        for table, column, col_def in _MIGRATION_COLUMNS:
            try:
                self._con.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"
                )
                self._con.commit()
                logger.info("evidence_db Migration: Spalte '%s.%s' ergänzt", table, column)
            except sqlite3.OperationalError as exc:
                if "duplicate column" in str(exc).lower():
                    logger.debug("evidence_db Migration: '%s.%s' bereits vorhanden", table, column)
                else:
                    raise

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
        if ts is None:
            ts = int(time.time())
        cursor = self._con.execute(
            "INSERT INTO page_visits (page_url, scrape_context, ts, investigator_id) "
            "VALUES (?, ?, ?, ?)",
            (page_url, scrape_context, ts, investigator_id),
        )
        self._con.commit()
        logger.debug("page_visit protokolliert: '%s' (context=%s)", page_url, scrape_context)
        return cursor.lastrowid

    def get_page_visits(self, page_url: str) -> list[PageVisitRecord]:
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
        if visible_ms < 0:
            raise EvidenceDbError(f"visible_ms muss >= 0 sein, erhalten: {visible_ms}")
        if ts_leave < ts_enter:
            raise EvidenceDbError(f"ts_leave ({ts_leave}) darf nicht vor ts_enter ({ts_enter}) liegen")
        cursor = self._con.execute(
            "INSERT INTO viewport_events "
            "(page_url, element_id, visible_ms, ts_enter, ts_leave, investigator_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (page_url, element_id, visible_ms, ts_enter, ts_leave, investigator_id),
        )
        self._con.commit()
        logger.debug("viewport_event: '%s' element=%s, %d ms sichtbar", page_url, element_id, visible_ms)
        return cursor.lastrowid

    def save_viewport_batch(
        self,
        events: list[dict],
        investigator_id: Optional[int] = None,
    ) -> int:
        if not events:
            return 0
        rows = []
        for ev in events:
            visible_ms = int(ev.get("visible_ms", 0))
            ts_enter   = int(ev.get("ts_enter", 0))
            ts_leave   = int(ev.get("ts_leave", 0))
            if visible_ms < 0 or ts_leave < ts_enter:
                logger.warning("Ungültiges Viewport-Event übersprungen: %s", ev)
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
        selection_json: Optional[str] = None,
        tags_json: Optional[str] = None,
        local_id: Optional[str] = None,
        post_id: Optional[int] = None,
        created_by: str = "",
    ) -> int:
        """
        Speichert eine Annotation.

        Neu in Build 011: selection_json (XPath-Daten), tags_json (Tag-Array),
        local_id (Browser-UUID), post_id (Post-Markierung), created_by (SAMAccount).
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
            "(page_url, element_id, category, text, ts, investigator_id, "
            " selection_json, tags_json, local_id, post_id, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (page_url, element_id, category, text, ts, investigator_id,
             selection_json, tags_json, local_id, post_id, created_by),
        )
        self._con.commit()
        logger.debug(
            "Annotation gespeichert: '%s' [%s] element=%s post_id=%s",
            page_url, category, element_id, post_id,
        )
        return cursor.lastrowid

    def get_annotations(self, page_url: str) -> list[AnnotationRecord]:
        """Gibt alle Annotationen für eine URL zurück (chronologisch)."""
        rows = self._con.execute(
            "SELECT id, page_url, element_id, category, text, ts, investigator_id, "
            "       selection_json, tags_json, local_id, post_id, created_by "
            "FROM annotations WHERE page_url = ? ORDER BY ts ASC",
            (page_url,),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_all_annotations(self) -> list[AnnotationRecord]:
        """Gibt alle Annotationen der DB zurück. Für Berichtserstellung."""
        rows = self._con.execute(
            "SELECT id, page_url, element_id, category, text, ts, investigator_id, "
            "       selection_json, tags_json, local_id, post_id, created_by "
            "FROM annotations ORDER BY page_url ASC, ts ASC"
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def annotation_count(self) -> int:
        """Anzahl aller gespeicherten Annotationen. Für Statusanzeigen."""
        try:
            row = self._con.execute("SELECT COUNT(*) FROM annotations").fetchone()
            return int(row[0]) if row else 0
        except sqlite3.OperationalError:
            return 0

    # ------------------------------------------------------------------
    # Interne Hilfsmethoden
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_record(r: sqlite3.Row) -> AnnotationRecord:
        """Wandelt eine sqlite3.Row in ein AnnotationRecord um."""
        keys = r.keys()
        return AnnotationRecord(
            id=int(r["id"]),
            page_url=str(r["page_url"]),
            element_id=str(r["element_id"]) if r["element_id"] is not None else None,
            category=str(r["category"]),
            text=str(r["text"]),
            ts=int(r["ts"]),
            investigator_id=int(r["investigator_id"]) if r["investigator_id"] is not None else None,
            selection_json=str(r["selection_json"]) if ("selection_json" in keys and r["selection_json"] is not None) else None,
            tags_json=str(r["tags_json"]) if ("tags_json" in keys and r["tags_json"] is not None) else None,
            local_id=str(r["local_id"]) if ("local_id" in keys and r["local_id"] is not None) else None,
            post_id=int(r["post_id"]) if ("post_id" in keys and r["post_id"] is not None) else None,
            created_by=str(r["created_by"]) if ("created_by" in keys and r["created_by"] is not None) else "",
        )

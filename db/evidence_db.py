# =============================================================================
# db/evidence_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Kapselt alle Schreib- und Lesezugriffe auf die evidence_<uid>.db.
#
# Changelog:
#   Build 012 (Baustelle 4):
#     - Tabellen, Lock-Mechanismus, Annotation-Methoden.
#   Build 043 (AP-E1):
#     - Editor.js-Modell: reports, report_templates, report_blocks,
#       report_block_order, block_evidence_user.
#   Build 089 (B6 — Phase 2/3):
#     - Editor.js-Modell vollstaendig ersetzt durch Baustelle-6-Modell.
#     - Entfernte Tabellen: report_templates, report_blocks,
#       report_block_order (alt, TEXT sort_index), block_evidence_user.
#     - Neue Tabellen: report_paragraphs, report_block_order (INTEGER),
#       report_anchors, report_comments, placeholder_cache.
#     - Entfernte Dataclasses: ReportBlockRecord, ReportBlockOrderRecord,
#       BlockEvidenceRecord.
#     - Neue Dataclasses: ReportParagraphRecord, ReportAnchorRecord,
#       ReportCommentRecord.
#     - Entfernte Methoden: save_block(), delete_block(), get_blocks_ordered(),
#       get_block(), update_block_order(), get_block_order(),
#       add_block_evidence(), remove_block_evidence(),
#       get_evidence_for_block(), get_blocks_for_evidence().
#     - Neue Methoden: add_paragraph(), get_paragraph(), get_paragraphs(),
#       update_paragraph_content(), set_paragraph_status(),
#       get_block_order_for_report(), set_block_order(),
#       add_anchor(), remove_anchor(), get_anchors_for_paragraph(),
#       get_anchored_annotation_ids(),
#       add_comment(), get_comments_for_paragraph(), resolve_comment(),
#       get_cache_entry(), set_cache_entry(), clear_cache_for_uid().
#     - get_report_status() auf B6-Schema umgeschrieben.
#     - get_unreferenced_annotation_count() auf report_anchors umgeschrieben.
#     - create_report(): template_id-Parameter entfernt (kein report_templates mehr).
#     Beleg: Bauplan B6 v0.3 §2.3, Ausdefinitionsgespraech 2026-05-05
#
#   Synchronisation:
#   _SCHEMA_DDL muss mit stage2/evidence_db_init.py im Prepper synchron
#   gehalten werden. Letzte Synchronisation: Build 089 (B6), 2026-05-05.
#
# Abhaengigkeiten: sqlite3, time, json, uuid -- ausschliesslich Stdlib
# Version: v0.6.089 · Build: 089 · 2026-05-05
# =============================================================================

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)

# Zulaessige Annotationskategorien -- unveraenderliche Menge
VALID_CATEGORIES = frozenset({
    "CAT_PERSON",
    "CAT_LOCATION",
    "CAT_176",
    "CAT_184",
    "CAT_VICTIM",
    "CAT_OTHER",
})

# Zulaessige Berichtstypen
VALID_REPORT_TYPES = frozenset({
    "interim",    # Zwischenbericht
    "final",      # Abschlussbericht (max. einer pro evidence_db)
    "addendum",   # Nachtragsbericht
})

# Zulaessige Berichtsstatus
VALID_REPORT_STATUSES = frozenset({
    "draft",
    "submitted",
    "approved",
    "final",
})

# Zulaessige Paragraphen-Status (Baustelle 6)
# Beleg: Bauplan B6 v0.3 §2.3
VALID_PARAGRAPH_STATUSES = frozenset({
    "draft",
    "active",
    "omitted",
    "superseded",
    "approved",
})

# Zulaessige Kommentar-Status (Baustelle 6)
# Beleg: Bauplan B6 v0.3 §2.3
VALID_COMMENT_STATUSES = frozenset({
    "pending",
    "addressed",
    "dismissed",
    "revoked",
})

# =============================================================================
# Schema-DDL
#
# SYNCHRON HALTEN MIT: stage2/evidence_db_init.py (_FULL_SCHEMA_DDL)
# Letzte Synchronisation: Build 089 (B6-Schema), 2026-05-05
# =============================================================================
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
    investigator_id INTEGER,
    selection_json  TEXT DEFAULT NULL,
    tags_json       TEXT DEFAULT NULL,
    local_id        TEXT DEFAULT NULL,
    post_id         INTEGER DEFAULT NULL,
    created_by      TEXT NOT NULL DEFAULT ''
);

-- Berichts-Metadaten. Nur ein Bericht vom Typ 'final' zulaessig.
CREATE TABLE IF NOT EXISTS reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type     TEXT    NOT NULL
                    CHECK (report_type IN ('interim', 'final', 'addendum')),
    sequence_nr     INTEGER NOT NULL DEFAULT 1,
    title           TEXT    NOT NULL,
    created_by      TEXT    NOT NULL,
    created_at      INTEGER NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'submitted', 'approved', 'final'))
);

-- Kern: Berichts-Paragraphen (Baustelle 6).
-- Beleg: Bauplan B6 v0.3 §2.3, Ausdefinitionsgespraech 2026-05-05
CREATE TABLE IF NOT EXISTS report_paragraphs (
    block_id                TEXT    NOT NULL PRIMARY KEY,
    report_id               INTEGER NOT NULL REFERENCES reports(id),
    author                  TEXT    NOT NULL,
    created_at              INTEGER NOT NULL,
    updated_at              INTEGER NOT NULL,
    content                 TEXT    NOT NULL DEFAULT '',
    placeholder_values_json TEXT,
    status                  TEXT    NOT NULL DEFAULT 'draft'
                            CHECK (status IN (
                                'draft', 'active', 'omitted', 'superseded', 'approved'
                            )),
    omitted_by              TEXT,
    omitted_at              INTEGER,
    omitted_reason          TEXT,
    module_id               INTEGER
);

-- Reihenfolge der Paragraphen (INTEGER sort_index, B6).
-- Beleg: Bauplan B6 v0.3 §2.3
CREATE TABLE IF NOT EXISTS report_block_order (
    block_id            TEXT    NOT NULL PRIMARY KEY
                        REFERENCES report_paragraphs(block_id),
    sort_index          INTEGER NOT NULL,
    last_modified_by    TEXT    NOT NULL,
    last_modified_at    INTEGER NOT NULL
);

-- Beweisanker: Verknuepfung Paragraph <-> Annotation.
-- Beleg: Bauplan B6 v0.3 §2.3
CREATE TABLE IF NOT EXISTS report_anchors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    block_id        TEXT    NOT NULL REFERENCES report_paragraphs(block_id),
    annotation_id   INTEGER NOT NULL REFERENCES annotations(id),
    anchor_text     TEXT    NOT NULL,
    created_at      INTEGER NOT NULL
);

-- Kommentare zu fremden Paragraphen (Status One-Way, Grundregel 15).
-- Beleg: Bauplan B6 v0.3 §2.3
CREATE TABLE IF NOT EXISTS report_comments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    block_id            TEXT    NOT NULL REFERENCES report_paragraphs(block_id),
    author              TEXT    NOT NULL,
    created_at          INTEGER NOT NULL,
    comment_text        TEXT    NOT NULL,
    suggested_content   TEXT,
    status              TEXT    NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'addressed', 'dismissed', 'revoked')),
    resolved_by         TEXT,
    resolved_at         INTEGER
);

-- Cache fuer {{a:...}}-Platzhalter.
-- Beleg: Bauplan B6 v0.3 §2.3
CREATE TABLE IF NOT EXISTS placeholder_cache (
    query_id        TEXT    NOT NULL,
    uid             INTEGER NOT NULL,
    cached_value    TEXT    NOT NULL,
    cached_at       INTEGER NOT NULL,
    PRIMARY KEY (query_id, uid)
);

-- Freigabe-Tabelle (unveraendert).
CREATE TABLE IF NOT EXISTS report_approvals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id   INTEGER NOT NULL REFERENCES reports(id),
    approved_by TEXT    NOT NULL,
    approved_at INTEGER NOT NULL,
    note        TEXT    DEFAULT NULL,
    is_final    INTEGER NOT NULL DEFAULT 0
);

-- Editor-Lock (unveraendert).
CREATE TABLE IF NOT EXISTS editor_locks (
    resource    TEXT    NOT NULL PRIMARY KEY,
    locked_by   TEXT    NOT NULL,
    lock_id     TEXT    NOT NULL,
    locked_at   INTEGER NOT NULL,
    sse_client  TEXT    NOT NULL
);

-- Lock-Uebernahme-Anfragen (unveraendert).
CREATE TABLE IF NOT EXISTS lock_takeover_requests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lock_id         TEXT    NOT NULL,
    requested_by    TEXT    NOT NULL,
    requested_at    INTEGER NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'granted', 'denied', 'expired'))
);

CREATE INDEX IF NOT EXISTS pv_url_idx       ON page_visits (page_url);
CREATE INDEX IF NOT EXISTS ve_url_idx       ON viewport_events (page_url);
CREATE INDEX IF NOT EXISTS ann_url_idx      ON annotations (page_url);
CREATE INDEX IF NOT EXISTS ann_cat_idx      ON annotations (category);
CREATE INDEX IF NOT EXISTS rep_type_idx     ON reports (report_type);
CREATE INDEX IF NOT EXISTS rep_status_idx   ON reports (status);
CREATE INDEX IF NOT EXISTS rp_report_idx    ON report_paragraphs (report_id);
CREATE INDEX IF NOT EXISTS rp_author_idx    ON report_paragraphs (author);
CREATE INDEX IF NOT EXISTS rp_status_idx    ON report_paragraphs (status);
CREATE INDEX IF NOT EXISTS rbo_sort_idx     ON report_block_order (sort_index);
CREATE INDEX IF NOT EXISTS ra_block_idx     ON report_anchors (block_id);
CREATE INDEX IF NOT EXISTS ra_ann_idx       ON report_anchors (annotation_id);
CREATE UNIQUE INDEX IF NOT EXISTS ra_block_ann_uniq
    ON report_anchors (block_id, annotation_id);
CREATE INDEX IF NOT EXISTS rc_block_idx     ON report_comments (block_id);
CREATE INDEX IF NOT EXISTS rc_status_idx    ON report_comments (status);
CREATE INDEX IF NOT EXISTS rap_report_idx   ON report_approvals (report_id);

CREATE UNIQUE INDEX IF NOT EXISTS reports_one_final_idx
    ON reports (report_type)
    WHERE report_type = 'final';

-- annotations_local_id_uniq: wird in _migrate_schema() angelegt,
-- NICHT hier, weil local_id in aelteren DBs fehlen kann (T24-Migration).
-- SQLite-Einschraenkung: ON CONFLICT(col) erkennt keine partiellen Indizes.
-- UPSERT in save_annotation() nutzt daher SELECT+UPDATE/INSERT.
-- Beleg: Build 089, SQLite-Dokumentation.
"""

# Migrationsspalten fuer aeltere evidence_db-Instanzen.
# Beleg: Build 061, Build 089
_MIGRATION_COLUMNS: list[tuple[str, str, str]] = [
    ("annotations", "selection_json", "TEXT DEFAULT NULL"),
    ("annotations", "tags_json",      "TEXT DEFAULT NULL"),
    ("annotations", "local_id",       "TEXT DEFAULT NULL"),
    ("annotations", "post_id",        "INTEGER DEFAULT NULL"),
    ("annotations", "created_by",     "TEXT NOT NULL DEFAULT ''"),
]


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class PageVisitRecord:
    id:              int
    page_url:        str
    scrape_context:  str
    ts:              int
    investigator_id: Optional[int]


@dataclass
class AnnotationRecord:
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


@dataclass
class ReportRecord:
    """Berichtsmetadata.
    Beleg: AP-E1 (angelegt), unveraendert in B6
    """
    id:          int
    report_type: str
    sequence_nr: int
    title:       str
    created_by:  str
    created_at:  int
    status:      str


@dataclass
class ReportParagraphRecord:
    """Ein Berichts-Paragraph (Baustelle 6).
    Beleg: Bauplan B6 v0.3 §2.3
    """
    block_id:                str
    report_id:               int
    author:                  str
    created_at:              int
    updated_at:              int
    content:                 str
    status:                  str
    placeholder_values_json: Optional[str] = None
    omitted_by:              Optional[str] = None
    omitted_at:              Optional[int] = None
    omitted_reason:          Optional[str] = None
    module_id:               Optional[int] = None


@dataclass
class ReportAnchorRecord:
    """Beweisanker Paragraph <-> Annotation (Baustelle 6).
    Beleg: Bauplan B6 v0.3 §2.3
    """
    id:            int
    block_id:      str
    annotation_id: int
    anchor_text:   str
    created_at:    int


@dataclass
class ReportCommentRecord:
    """Kommentar zu einem Paragraphen (Baustelle 6).
    Beleg: Bauplan B6 v0.3 §2.3
    """
    id:                int
    block_id:          str
    author:            str
    created_at:        int
    comment_text:      str
    status:            str
    suggested_content: Optional[str] = None
    resolved_by:       Optional[str] = None
    resolved_at:       Optional[int] = None


@dataclass
class ReportApprovalRecord:
    """Freigabeeintrag (unveraendert)."""
    id:          int
    report_id:   Optional[int]
    approved_by: str
    approved_at: int
    note:        Optional[str]
    is_final:    bool


@dataclass
class EditorLockRecord:
    """Aktiver Editor-Lock (§8.6 Bauplan B4)."""
    resource:   str
    locked_by:  str
    lock_id:    str
    locked_at:  int
    sse_client: str


# =============================================================================
# Ausnahmen
# =============================================================================

class EvidenceDbError(Exception):
    """Wird geworfen bei ungueltigen Eingaben."""


# =============================================================================
# Hauptklasse
# =============================================================================

class EvidenceDb:
    """Kapselt alle Schreib- und Lesezugriffe auf die evidence_db."""

    _LOCK_RESOURCE = "report_editor"

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._setup_schema()
        self._migrate_schema()
        self._lock_change_event = threading.Event()

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
        """Ergaenzt fehlende Spalten in aelteren evidence_db-Instanzen."""
        for table, column, col_def in _MIGRATION_COLUMNS:
            try:
                self._con.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"
                )
                self._con.commit()
                logger.info(
                    "evidence_db Migration: Spalte '%s.%s' ergaenzt", table, column
                )
            except sqlite3.OperationalError as exc:
                if "duplicate column" in str(exc).lower():
                    logger.debug(
                        "evidence_db Migration: '%s.%s' bereits vorhanden",
                        table, column,
                    )
                else:
                    raise

        # annotations_local_id_uniq nach Spalten-Migration anlegen.
        try:
            self._con.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS annotations_local_id_uniq "
                "ON annotations (local_id) "
                "WHERE local_id IS NOT NULL"
            )
            self._con.commit()
            logger.debug("evidence_db Migration: annotations_local_id_uniq sichergestellt")
        except sqlite3.OperationalError as exc:
            logger.warning(
                "evidence_db Migration: annotations_local_id_uniq fehlgeschlagen: %s", exc
            )

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
                investigator_id=(
                    int(r["investigator_id"])
                    if r["investigator_id"] is not None else None
                ),
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
    ) -> Optional[int]:
        if ts_leave < ts_enter:
            raise EvidenceDbError(
                "ts_leave darf nicht vor ts_enter liegen."
            )
        if visible_ms < 0:
            raise EvidenceDbError(
                "visible_ms darf nicht negativ sein."
            )
        cursor = self._con.execute(
            "INSERT INTO viewport_events "
            "(page_url, element_id, visible_ms, ts_enter, ts_leave, investigator_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (page_url, element_id, visible_ms, ts_enter, ts_leave, investigator_id),
        )
        self._con.commit()
        return cursor.lastrowid

    def save_viewport_batch(
        self,
        events: list[dict],
        investigator_id: Optional[int] = None,
    ) -> int:
        saved = 0
        for ev in events:
            try:
                ts_enter = int(ev.get("ts_enter", 0))
                ts_leave = int(ev.get("ts_leave", 0))
                visible_ms = int(ev.get("visible_ms", 0))
                if ts_leave < ts_enter or visible_ms < 0:
                    continue
                self._con.execute(
                    "INSERT INTO viewport_events "
                    "(page_url, element_id, visible_ms, ts_enter, ts_leave, investigator_id) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        str(ev.get("page_url", "")),
                        ev.get("element_id"),
                        visible_ms,
                        ts_enter,
                        ts_leave,
                        investigator_id,
                    ),
                )
                saved += 1
            except (TypeError, ValueError):
                continue
        if saved:
            self._con.commit()
        return saved

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
        selection_json: Optional[str] = None,
        tags_json: Optional[str] = None,
        local_id: Optional[str] = None,
        post_id: Optional[int] = None,
        created_by: str = "",
        ts: Optional[int] = None,
    ) -> int:
        if category not in VALID_CATEGORIES:
            raise EvidenceDbError(
                f"Unbekannte Kategorie '{category}'. "
                f"Zulaessig: {sorted(VALID_CATEGORIES)}"
            )
        if ts is None:
            ts = int(time.time())

        if local_id is not None:
            # UPSERT fuer local_id: SQLite ON CONFLICT(col) unterstuetzt keine
            # partiellen Unique-Indizes. Daher: SELECT-dann-UPDATE-oder-INSERT.
            # Beleg: SQLite-Dokumentation, ON CONFLICT-Einschraenkung, Build 089.
            existing = self._con.execute(
                "SELECT id FROM annotations WHERE local_id = ?", (local_id,)
            ).fetchone()
            if existing is not None:
                # Bestehenden Eintrag aktualisieren
                self._con.execute(
                    "UPDATE annotations SET "
                    "  page_url=?, element_id=?, category=?, text=?, ts=?, "
                    "  selection_json=?, tags_json=?, post_id=?, created_by=? "
                    "WHERE local_id=?",
                    (
                        page_url, element_id, category, text, ts,
                        selection_json, tags_json, post_id, created_by,
                        local_id,
                    ),
                )
                self._con.commit()
                return int(existing["id"])
            else:
                cursor = self._con.execute(
                    "INSERT INTO annotations "
                    "(page_url, element_id, category, text, ts, investigator_id, "
                    " selection_json, tags_json, local_id, post_id, created_by) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        page_url, element_id, category, text, ts, investigator_id,
                        selection_json, tags_json, local_id, post_id, created_by,
                    ),
                )
        else:
            cursor = self._con.execute(
                "INSERT INTO annotations "
                "(page_url, element_id, category, text, ts, investigator_id, "
                " selection_json, tags_json, local_id, post_id, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    page_url, element_id, category, text, ts, investigator_id,
                    selection_json, tags_json, None, post_id, created_by,
                ),
            )
        self._con.commit()
        # Bei UPSERT gibt lastrowid die ID des betroffenen Eintrags zurueck
        if cursor.lastrowid:
            return cursor.lastrowid
        # Fallback: ID per local_id nachschlagen
        row = self._con.execute(
            "SELECT id FROM annotations WHERE local_id = ?", (local_id,)
        ).fetchone()
        return int(row["id"]) if row else 0

    def delete_annotation(self, annotation_id: int) -> bool:
        cursor = self._con.execute(
            "DELETE FROM annotations WHERE id = ?", (annotation_id,)
        )
        self._con.commit()
        return cursor.rowcount > 0

    def get_annotations(self, page_url: str) -> list[AnnotationRecord]:
        rows = self._con.execute(
            "SELECT id, page_url, element_id, category, text, ts, "
            "       investigator_id, selection_json, tags_json, local_id, "
            "       post_id, created_by "
            "FROM annotations WHERE page_url = ? ORDER BY ts ASC",
            (page_url,),
        ).fetchall()
        return [self._row_to_annotation(r) for r in rows]

    def get_all_annotations(self) -> list[AnnotationRecord]:
        rows = self._con.execute(
            "SELECT id, page_url, element_id, category, text, ts, "
            "       investigator_id, selection_json, tags_json, local_id, "
            "       post_id, created_by "
            "FROM annotations ORDER BY ts DESC"
        ).fetchall()
        return [self._row_to_annotation(r) for r in rows]

    def annotation_count(self) -> int:
        row = self._con.execute("SELECT COUNT(*) FROM annotations").fetchone()
        return int(row[0]) if row else 0

    def get_annotation_counts_by_category(self) -> dict:
        rows = self._con.execute(
            "SELECT category, COUNT(*) as cnt FROM annotations GROUP BY category"
        ).fetchall()
        return {str(r["category"]): int(r["cnt"]) for r in rows}

    def get_last_annotation_info(self) -> Optional[dict]:
        row = self._con.execute(
            "SELECT ts, category FROM annotations ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        if row:
            return {"ts": int(row["ts"]), "category": str(row["category"])}
        return None

    def get_unreferenced_annotation_count(self) -> int:
        """
        Anzahl Annotationen ohne Beweisanker in report_anchors.
        Beleg: Bauplan B6 v0.3 §4.7 (Vollstaendigkeitsanzeige)
        """
        try:
            row = self._con.execute(
                "SELECT COUNT(*) FROM annotations "
                "WHERE id NOT IN (SELECT DISTINCT annotation_id FROM report_anchors)"
            ).fetchone()
            return int(row[0]) if row else 0
        except sqlite3.OperationalError:
            return 0

    # ------------------------------------------------------------------
    # Berichte (reports)
    # ------------------------------------------------------------------

    def create_report(
        self,
        report_type: str,
        title: str,
        created_by: str,
    ) -> int:
        """
        Legt einen neuen Bericht an.

        Args:
            report_type: 'interim', 'final' oder 'addendum'.
            title:       Titel des Berichts.
            created_by:  SAMAccountName des Erstellers.

        Returns:
            id des neuen Berichts.

        Raises:
            EvidenceDbError: Bei ungueltigem Typ, leerem Titel oder
                             doppeltem Abschlussbericht.
        """
        if report_type not in VALID_REPORT_TYPES:
            raise EvidenceDbError(
                f"Ungueltiger Berichtstyp: '{report_type}'. "
                f"Zulaessig: {sorted(VALID_REPORT_TYPES)}"
            )
        if not title.strip():
            raise EvidenceDbError("Berichtstitel darf nicht leer sein.")
        if not created_by.strip():
            raise EvidenceDbError("created_by darf nicht leer sein.")

        row = self._con.execute(
            "SELECT COALESCE(MAX(sequence_nr), 0) FROM reports WHERE report_type = ?",
            (report_type,),
        ).fetchone()
        sequence_nr = int(row[0]) + 1

        now = int(time.time())
        try:
            cursor = self._con.execute(
                "INSERT INTO reports "
                "(report_type, sequence_nr, title, created_by, created_at, status) "
                "VALUES (?, ?, ?, ?, ?, 'draft')",
                (report_type, sequence_nr, title.strip(), created_by.strip(), now),
            )
            self._con.commit()
        except sqlite3.IntegrityError as exc:
            raise EvidenceDbError(
                "Es existiert bereits ein Abschlussbericht. "
                "Pro Ermittlungsakte ist nur ein Abschlussbericht zulaessig."
            ) from exc

        logger.info(
            "Bericht angelegt: id=%d type='%s' seq=%d von '%s'",
            cursor.lastrowid, report_type, sequence_nr, created_by,
        )
        return cursor.lastrowid

    def get_reports(self) -> list[ReportRecord]:
        rows = self._con.execute(
            "SELECT id, report_type, sequence_nr, title, "
            "       created_by, created_at, status "
            "FROM reports ORDER BY report_type ASC, sequence_nr ASC"
        ).fetchall()
        return [self._row_to_report(r) for r in rows]

    def get_report(self, report_id: int) -> Optional[ReportRecord]:
        row = self._con.execute(
            "SELECT id, report_type, sequence_nr, title, "
            "       created_by, created_at, status "
            "FROM reports WHERE id = ?",
            (report_id,),
        ).fetchone()
        return self._row_to_report(row) if row else None

    def update_report_status(
        self,
        report_id: int,
        status: str,
        updated_by: str,
    ) -> bool:
        if status not in VALID_REPORT_STATUSES:
            raise EvidenceDbError(
                f"Ungueltiger Berichtsstatus: '{status}'. "
                f"Zulaessig: {sorted(VALID_REPORT_STATUSES)}"
            )
        cursor = self._con.execute(
            "UPDATE reports SET status = ? WHERE id = ?",
            (status, report_id),
        )
        self._con.commit()
        if cursor.rowcount > 0:
            logger.info(
                "Berichtsstatus: id=%d status='%s' von '%s'",
                report_id, status, updated_by,
            )
        return cursor.rowcount > 0

    def get_report_status(self) -> dict:
        """
        Berichtsstatus fuer /_forensic/userinfo/data.
        Beleg: B6 Build 089 -- auf B6-Schema umgeschrieben.
        """
        try:
            para_row = self._con.execute(
                "SELECT rp.updated_at, rp.author "
                "FROM report_paragraphs rp "
                "ORDER BY rp.updated_at DESC LIMIT 1"
            ).fetchone()
            appr_row = self._con.execute(
                "SELECT approved_by FROM report_approvals "
                "ORDER BY approved_at DESC LIMIT 1"
            ).fetchone()
            count_row = self._con.execute(
                "SELECT COUNT(*) FROM reports"
            ).fetchone()
            return {
                "has_draft":    para_row is not None,
                "last_edit_ts": int(para_row["updated_at"]) if para_row else None,
                "last_editor":  str(para_row["author"]) if para_row else None,
                "approved":     appr_row is not None,
                "approved_by":  str(appr_row["approved_by"]) if appr_row else None,
                "report_count": int(count_row[0]) if count_row else 0,
            }
        except sqlite3.OperationalError as exc:
            logger.warning("get_report_status fehlgeschlagen: %s", exc)
            return {
                "has_draft": False, "last_edit_ts": None, "last_editor": None,
                "approved": False, "approved_by": None, "report_count": 0,
            }

    # ------------------------------------------------------------------
    # Paragraphen (report_paragraphs, B6)
    # Beleg: Bauplan B6 v0.3 §2.3
    # ------------------------------------------------------------------

    def add_paragraph(
        self,
        block_id: str,
        report_id: int,
        author: str,
        content: str = "",
        module_id: Optional[int] = None,
        placeholder_values_json: Optional[str] = None,
        sort_index: Optional[int] = None,
    ) -> str:
        """
        Legt einen neuen Paragraphen an (Status 'draft').

        Args:
            block_id:   UUID (clientseitig erzeugt).
            report_id:  Referenz auf reports.id.
            author:     SAMAccountName -- Owner, nie aenderbar.
            content:    Freitext (darf leer sein bei neuem Block).
            module_id:  Referenz auf templates.report_modules.id (optional).
            placeholder_values_json: JSON-String {name: value} fuer m:/o:-Felder.
            sort_index: Initiale Sortierposition. Wird in report_block_order eingetragen.

        Returns:
            block_id (unveraendert).

        Raises:
            EvidenceDbError: Bei leerem author oder ungueltigem report_id.
        """
        if not author.strip():
            raise EvidenceDbError("author darf nicht leer sein.")

        now = int(time.time())
        self._con.execute(
            "INSERT INTO report_paragraphs "
            "(block_id, report_id, author, created_at, updated_at, content, "
            " placeholder_values_json, status, module_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?)",
            (
                block_id, report_id, author.strip(), now, now,
                content, placeholder_values_json, module_id,
            ),
        )
        if sort_index is not None:
            self._con.execute(
                "INSERT OR REPLACE INTO report_block_order "
                "(block_id, sort_index, last_modified_by, last_modified_at) "
                "VALUES (?, ?, ?, ?)",
                (block_id, sort_index, author.strip(), now),
            )
        self._con.commit()
        logger.info(
            "Paragraph angelegt: block_id=%s report_id=%d von '%s'",
            block_id, report_id, author,
        )
        return block_id

    def get_paragraph(self, block_id: str) -> Optional[ReportParagraphRecord]:
        """Einzelnen Paragraphen per block_id laden."""
        row = self._con.execute(
            "SELECT block_id, report_id, author, created_at, updated_at, "
            "       content, placeholder_values_json, status, "
            "       omitted_by, omitted_at, omitted_reason, module_id "
            "FROM report_paragraphs WHERE block_id = ?",
            (block_id,),
        ).fetchone()
        return self._row_to_paragraph(row) if row else None

    def get_paragraphs(self, report_id: int) -> list[ReportParagraphRecord]:
        """
        Alle Paragraphen eines Berichts, sortiert nach sort_index ASC.
        Paragraphen ohne Sortierungseintrag werden ans Ende gestellt.
        """
        rows = self._con.execute(
            "SELECT rp.block_id, rp.report_id, rp.author, rp.created_at, "
            "       rp.updated_at, rp.content, rp.placeholder_values_json, "
            "       rp.status, rp.omitted_by, rp.omitted_at, "
            "       rp.omitted_reason, rp.module_id "
            "FROM report_paragraphs rp "
            "LEFT JOIN report_block_order rbo ON rbo.block_id = rp.block_id "
            "WHERE rp.report_id = ? "
            "ORDER BY COALESCE(rbo.sort_index, 999999) ASC, rp.created_at ASC",
            (report_id,),
        ).fetchall()
        return [self._row_to_paragraph(r) for r in rows]

    def update_paragraph_content(
        self,
        block_id: str,
        content: str,
        placeholder_values_json: Optional[str],
        requesting_author: str,
    ) -> bool:
        """
        Aktualisiert Inhalt und Platzhalter-Werte eines Paragraphen.
        Nur der Eigentuemer darf bearbeiten (Grundregel 14).
        'approved'-Paragraphen koennen nie bearbeitet werden.

        Returns:
            True wenn gespeichert, False wenn Block nicht gefunden.

        Raises:
            EvidenceDbError: Wenn nicht Eigentuemer oder Status 'approved'.
        """
        row = self._con.execute(
            "SELECT author, status FROM report_paragraphs WHERE block_id = ?",
            (block_id,),
        ).fetchone()
        if not row:
            return False
        if str(row["status"]) == "approved":
            raise EvidenceDbError(
                "Freigegebene Paragraphen koennen nicht bearbeitet werden."
            )
        if str(row["author"]) != requesting_author:
            raise EvidenceDbError(
                f"Nur der Eigentuemer darf einen Paragraphen bearbeiten. "
                f"Eigentuemer: '{row['author']}'"
            )
        now = int(time.time())
        self._con.execute(
            "UPDATE report_paragraphs "
            "SET content = ?, placeholder_values_json = ?, updated_at = ? "
            "WHERE block_id = ?",
            (content, placeholder_values_json, now, block_id),
        )
        self._con.commit()
        return True

    def set_paragraph_status(
        self,
        block_id: str,
        new_status: str,
        requesting_user: str,
        omitted_reason: Optional[str] = None,
        is_chef: bool = False,
    ) -> bool:
        """
        Setzt den Status eines Paragraphen.

        Lifecycle (Grundregel 10):
          draft <-> active   (Eigentuemer)
          active -> omitted  (nur Chef-Ermittlerin)
          active -> approved (nur Chef-Ermittlerin, One-Way)
          draft  -> omitted  (nur Chef-Ermittlerin)

        Returns True wenn gesetzt, False wenn Block nicht gefunden.
        Raises EvidenceDbError bei ungueltigem Uebergang oder fehlender Berechtigung.
        """
        if new_status not in VALID_PARAGRAPH_STATUSES:
            raise EvidenceDbError(
                f"Ungueltiger Status: '{new_status}'. "
                f"Zulaessig: {sorted(VALID_PARAGRAPH_STATUSES)}"
            )
        row = self._con.execute(
            "SELECT author, status FROM report_paragraphs WHERE block_id = ?",
            (block_id,),
        ).fetchone()
        if not row:
            return False

        current = str(row["status"])
        owner   = str(row["author"])

        # approved ist absolut einfrierend
        if current == "approved":
            raise EvidenceDbError(
                "Freigegebene Paragraphen koennen den Status nicht mehr aendern."
            )

        # Berechtigungspruefung
        chef_only = {"omitted", "approved"}
        if new_status in chef_only and not is_chef:
            raise EvidenceDbError(
                f"Status '{new_status}' kann nur durch die Chef-Ermittlerin gesetzt werden."
            )
        if new_status in ("draft", "active") and requesting_user != owner and not is_chef:
            raise EvidenceDbError(
                f"Nur der Eigentuemer oder die Chef-Ermittlerin darf "
                f"zwischen 'draft' und 'active' wechseln."
            )

        now = int(time.time())
        if new_status == "omitted":
            self._con.execute(
                "UPDATE report_paragraphs "
                "SET status=?, omitted_by=?, omitted_at=?, omitted_reason=?, updated_at=? "
                "WHERE block_id=?",
                (new_status, requesting_user, now, omitted_reason, now, block_id),
            )
        else:
            self._con.execute(
                "UPDATE report_paragraphs SET status=?, updated_at=? WHERE block_id=?",
                (new_status, now, block_id),
            )
        self._con.commit()
        logger.info(
            "Paragraph-Status: block_id=%s %s->%s von '%s'",
            block_id, current, new_status, requesting_user,
        )
        return True

    # ------------------------------------------------------------------
    # Blockreihenfolge (report_block_order, B6)
    # ------------------------------------------------------------------

    def get_block_order_for_report(self, report_id: int) -> list[dict]:
        """
        Gibt die Sortierungseintraege aller Paragraphen eines Berichts zurueck.
        Beleg: Bauplan B6 v0.3 §5 (action=reorder)
        """
        rows = self._con.execute(
            "SELECT rbo.block_id, rbo.sort_index, rbo.last_modified_by, "
            "       rbo.last_modified_at "
            "FROM report_block_order rbo "
            "JOIN report_paragraphs rp ON rp.block_id = rbo.block_id "
            "WHERE rp.report_id = ? "
            "ORDER BY rbo.sort_index ASC",
            (report_id,),
        ).fetchall()
        return [
            {
                "block_id":         str(r["block_id"]),
                "sort_index":       int(r["sort_index"]),
                "last_modified_by": str(r["last_modified_by"]),
                "last_modified_at": int(r["last_modified_at"]),
            }
            for r in rows
        ]

    def set_block_order(
        self,
        order: list[dict],
        modified_by: str,
    ) -> int:
        """
        Setzt die Sortierungsreihenfolge fuer mehrere Paragraphen.
        Jeder Ermittler darf die Reihenfolge aendern (Grundregel aus §2.3).

        Args:
            order:       Liste von {block_id, sort_index}.
            modified_by: SAMAccountName des Sortierers.

        Returns:
            Anzahl aktualisierter Eintraege.
        """
        now = int(time.time())
        updated = 0
        for entry in order:
            block_id   = str(entry.get("block_id", ""))
            sort_index = int(entry.get("sort_index", 0))
            if not block_id:
                continue
            self._con.execute(
                "INSERT OR REPLACE INTO report_block_order "
                "(block_id, sort_index, last_modified_by, last_modified_at) "
                "VALUES (?, ?, ?, ?)",
                (block_id, sort_index, modified_by, now),
            )
            updated += 1
        if updated:
            self._con.commit()
        return updated

    # ------------------------------------------------------------------
    # Beweisanker (report_anchors, B6)
    # Beleg: Bauplan B6 v0.3 §2.3, §4.7
    # ------------------------------------------------------------------

    def add_anchor(
        self,
        block_id: str,
        annotation_id: int,
        anchor_text: str,
    ) -> int:
        """
        Verknuepft einen Paragraphen mit einer Annotation.
        Wirft EvidenceDbError wenn die Verknuepfung bereits existiert.

        Returns:
            id des neuen Anker-Eintrags.
        """
        now = int(time.time())
        try:
            cursor = self._con.execute(
                "INSERT INTO report_anchors "
                "(block_id, annotation_id, anchor_text, created_at) "
                "VALUES (?, ?, ?, ?)",
                (block_id, annotation_id, anchor_text, now),
            )
            self._con.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            raise EvidenceDbError(
                f"Beweisanker fuer block_id='{block_id}', "
                f"annotation_id={annotation_id} existiert bereits."
            ) from exc

    def remove_anchor(self, anchor_id: int) -> bool:
        cursor = self._con.execute(
            "DELETE FROM report_anchors WHERE id = ?", (anchor_id,)
        )
        self._con.commit()
        return cursor.rowcount > 0

    def get_anchors_for_paragraph(self, block_id: str) -> list[ReportAnchorRecord]:
        rows = self._con.execute(
            "SELECT id, block_id, annotation_id, anchor_text, created_at "
            "FROM report_anchors WHERE block_id = ? ORDER BY created_at ASC",
            (block_id,),
        ).fetchall()
        return [
            ReportAnchorRecord(
                id=int(r["id"]),
                block_id=str(r["block_id"]),
                annotation_id=int(r["annotation_id"]),
                anchor_text=str(r["anchor_text"]),
                created_at=int(r["created_at"]),
            )
            for r in rows
        ]

    def get_anchored_annotation_ids(self) -> set[int]:
        """Menge aller annotation_ids die mindestens einmal verankert sind."""
        rows = self._con.execute(
            "SELECT DISTINCT annotation_id FROM report_anchors"
        ).fetchall()
        return {int(r[0]) for r in rows}

    # ------------------------------------------------------------------
    # Kommentare (report_comments, B6)
    # Beleg: Bauplan B6 v0.3 §2.3, Grundregel 15
    # ------------------------------------------------------------------

    def add_comment(
        self,
        block_id: str,
        author: str,
        comment_text: str,
        suggested_content: Optional[str] = None,
    ) -> int:
        """
        Fuegt einen Kommentar zu einem Paragraphen hinzu.

        Returns:
            id des neuen Kommentars.
        """
        if not author.strip():
            raise EvidenceDbError("author darf nicht leer sein.")
        if not comment_text.strip():
            raise EvidenceDbError("comment_text darf nicht leer sein.")
        now = int(time.time())
        cursor = self._con.execute(
            "INSERT INTO report_comments "
            "(block_id, author, created_at, comment_text, suggested_content, status) "
            "VALUES (?, ?, ?, ?, ?, 'pending')",
            (block_id, author.strip(), now, comment_text.strip(), suggested_content),
        )
        self._con.commit()
        return cursor.lastrowid

    def get_comments_for_paragraph(self, block_id: str) -> list[ReportCommentRecord]:
        rows = self._con.execute(
            "SELECT id, block_id, author, created_at, comment_text, "
            "       suggested_content, status, resolved_by, resolved_at "
            "FROM report_comments WHERE block_id = ? ORDER BY created_at ASC",
            (block_id,),
        ).fetchall()
        return [self._row_to_comment(r) for r in rows]

    def resolve_comment(
        self,
        comment_id: int,
        new_status: str,
        resolved_by: str,
        requesting_user: str,
        is_chef: bool = False,
    ) -> bool:
        """
        Setzt den Status eines Kommentars (One-Way, Grundregel 15).

        Berechtigungen:
          pending -> addressed: Eigentuemer des Paragraphen oder Chef
          pending -> dismissed: Eigentuemer des Paragraphen oder Chef
          pending -> revoked:   nur der Kommentator selbst

        Returns True wenn gesetzt, False wenn Kommentar nicht gefunden.
        """
        if new_status not in VALID_COMMENT_STATUSES - {"pending"}:
            raise EvidenceDbError(
                f"Ungueltiger Zielstatus: '{new_status}'. "
                f"Zulaessig: addressed, dismissed, revoked"
            )
        row = self._con.execute(
            "SELECT rc.author, rc.status, rp.author as para_author "
            "FROM report_comments rc "
            "JOIN report_paragraphs rp ON rp.block_id = rc.block_id "
            "WHERE rc.id = ?",
            (comment_id,),
        ).fetchone()
        if not row:
            return False
        if str(row["status"]) != "pending":
            raise EvidenceDbError("Kommentar-Status-Uebergaenge sind One-Way.")

        # Berechtigungspruefung
        if new_status == "revoked":
            if str(row["author"]) != requesting_user:
                raise EvidenceDbError(
                    "Nur der Kommentator selbst darf einen Kommentar zurueckziehen."
                )
        else:
            # addressed / dismissed: Eigentuemer oder Chef
            if str(row["para_author"]) != requesting_user and not is_chef:
                raise EvidenceDbError(
                    "Nur der Eigentuemer des Paragraphen oder die "
                    "Chef-Ermittlerin darf Kommentare bearbeiten."
                )

        now = int(time.time())
        self._con.execute(
            "UPDATE report_comments "
            "SET status=?, resolved_by=?, resolved_at=? WHERE id=?",
            (new_status, resolved_by, now, comment_id),
        )
        self._con.commit()
        return True

    # ------------------------------------------------------------------
    # Platzhalter-Cache (placeholder_cache, B6)
    # Beleg: Bauplan B6 v0.3 §2.3, §3.1, §3.2
    # ------------------------------------------------------------------

    def get_cache_entry(self, query_id: str, uid: int) -> Optional[str]:
        """
        Liest einen Cache-Eintrag fuer (query_id, uid).
        Returns cached_value oder None bei Cache-Miss.
        """
        row = self._con.execute(
            "SELECT cached_value FROM placeholder_cache "
            "WHERE query_id = ? AND uid = ?",
            (query_id, uid),
        ).fetchone()
        return str(row["cached_value"]) if row else None

    def set_cache_entry(self, query_id: str, uid: int, value: str) -> None:
        """
        Setzt oder aktualisiert einen Cache-Eintrag (UPSERT).
        Beleg: Bauplan B6 v0.3 §3.1 (Cache-Hit)
        """
        now = int(time.time())
        self._con.execute(
            "INSERT OR REPLACE INTO placeholder_cache "
            "(query_id, uid, cached_value, cached_at) VALUES (?, ?, ?, ?)",
            (query_id, uid, value, now),
        )
        self._con.commit()

    def clear_cache_for_uid(self, uid: int) -> int:
        """
        Loescht alle Cache-Eintraege fuer eine uid.
        Wird aufgerufen durch POST /refresh.
        Beleg: Bauplan B6 v0.3 §3.2

        Returns: Anzahl geloeschter Eintraege.
        """
        cursor = self._con.execute(
            "DELETE FROM placeholder_cache WHERE uid = ?", (uid,)
        )
        self._con.commit()
        deleted = cursor.rowcount
        logger.info(
            "placeholder_cache geleert: uid=%d, %d Eintraege entfernt", uid, deleted
        )
        return deleted

    # ------------------------------------------------------------------
    # Freigaben (report_approvals)
    # ------------------------------------------------------------------

    def add_approval(
        self,
        report_id: int,
        approved_by: str,
        note: Optional[str] = None,
        is_final: bool = False,
    ) -> int:
        now = int(time.time())
        cursor = self._con.execute(
            "INSERT INTO report_approvals "
            "(report_id, approved_by, approved_at, note, is_final) "
            "VALUES (?, ?, ?, ?, ?)",
            (report_id, approved_by, now, note, int(is_final)),
        )
        self._con.commit()
        return cursor.lastrowid

    # ------------------------------------------------------------------
    # Lock-Mechanismus (Lock-System v2, unveraendert)
    # Beleg: Bauplan B4 §8.6, Lock-System v2, Projektgespraech 2026-04-21
    # ------------------------------------------------------------------

    @property
    def lock_change_event(self) -> threading.Event:
        """Event-Signal das bei jeder Lock-Aenderung gesetzt wird."""
        return self._lock_change_event

    _LOCK_TIMEOUT_SEC = 90

    def acquire_lock(self, locked_by: str, sse_client: str) -> Optional[str]:
        now = int(time.time())
        new_lock_id = str(uuid.uuid4())
        try:
            self._con.execute(
                "DELETE FROM editor_locks WHERE resource=? AND locked_at < ?",
                (self._LOCK_RESOURCE, now - self._LOCK_TIMEOUT_SEC),
            )
        except sqlite3.OperationalError:
            pass
        try:
            self._con.execute(
                "INSERT INTO editor_locks "
                "(resource, locked_by, lock_id, locked_at, sse_client) "
                "VALUES (?, ?, ?, ?, ?)",
                (self._LOCK_RESOURCE, locked_by, new_lock_id, now, sse_client),
            )
            self._con.commit()
            self._lock_change_event.set()
            logger.info(
                "Editor-Lock erworben: '%s' (lock_id=%s)", locked_by, new_lock_id
            )
            return new_lock_id
        except sqlite3.IntegrityError:
            logger.debug(
                "acquire_lock: Lock bereits belegt fuer '%s'", self._LOCK_RESOURCE
            )
            return None

    def release_lock(self, lock_id: str) -> bool:
        cursor = self._con.execute(
            "DELETE FROM editor_locks WHERE resource=? AND lock_id=?",
            (self._LOCK_RESOURCE, lock_id),
        )
        self._con.commit()
        freed = cursor.rowcount > 0
        if freed:
            self._lock_change_event.set()
            logger.info("Editor-Lock freigegeben (lock_id=%s)", lock_id)
        return freed

    def release_lock_by_sse_client(self, sse_client: str) -> bool:
        cursor = self._con.execute(
            "DELETE FROM editor_locks WHERE resource=? AND sse_client=?",
            (self._LOCK_RESOURCE, sse_client),
        )
        self._con.commit()
        freed = cursor.rowcount > 0
        if freed:
            self._lock_change_event.set()
            logger.info(
                "Editor-Lock durch SSE-Abriss freigegeben (sse_client=%s)",
                sse_client,
            )
        return freed

    def resume_lock(self, lock_id: str, locked_by: str, new_sse_client: str) -> bool:
        try:
            cursor = self._con.execute(
                "UPDATE editor_locks "
                "SET sse_client = ?, locked_at = ? "
                "WHERE resource = ? AND lock_id = ? AND locked_by = ?",
                (
                    new_sse_client,
                    int(time.time()),
                    self._LOCK_RESOURCE,
                    lock_id,
                    locked_by,
                ),
            )
            self._con.commit()
            if cursor.rowcount > 0:
                logger.info(
                    "Lock-Resume: '%s' (lock_id=%s, neue sse_client=%s)",
                    locked_by, lock_id, new_sse_client,
                )
                return True
            return False
        except sqlite3.OperationalError as exc:
            logger.warning("resume_lock fehlgeschlagen: %s", exc)
            return False

    def request_takeover(self, lock_id: str, requested_by: str) -> int:
        now = int(time.time())
        self._con.execute(
            "DELETE FROM lock_takeover_requests "
            "WHERE lock_id=? AND requested_by=? AND status='pending'",
            (lock_id, requested_by),
        )
        cursor = self._con.execute(
            "INSERT INTO lock_takeover_requests "
            "(lock_id, requested_by, requested_at, status) VALUES (?,?,?,'pending')",
            (lock_id, requested_by, now),
        )
        self._con.commit()
        return cursor.lastrowid

    def resolve_takeover(self, request_id: int, status: str) -> bool:
        cursor = self._con.execute(
            "UPDATE lock_takeover_requests SET status=? "
            "WHERE id=? AND status='pending'",
            (status, request_id),
        )
        self._con.commit()
        return cursor.rowcount > 0

    def get_pending_takeover(self, lock_id: str) -> Optional[dict]:
        try:
            row = self._con.execute(
                "SELECT id, lock_id, requested_by, requested_at "
                "FROM lock_takeover_requests "
                "WHERE lock_id=? AND status='pending' ORDER BY requested_at ASC LIMIT 1",
                (lock_id,),
            ).fetchone()
            if row:
                return {
                    "id":           row["id"],
                    "lock_id":      row["lock_id"],
                    "requested_by": row["requested_by"],
                    "requested_at": row["requested_at"],
                }
        except sqlite3.OperationalError:
            pass
        return None

    def get_lock(self) -> Optional[EditorLockRecord]:
        try:
            row = self._con.execute(
                "SELECT resource, locked_by, lock_id, locked_at, sse_client "
                "FROM editor_locks WHERE resource=?",
                (self._LOCK_RESOURCE,),
            ).fetchone()
            if row:
                if row["locked_at"] is None or row["lock_id"] is None:
                    logger.warning(
                        "get_lock: korrupter Datensatz (NULL in Pflichtfeld) -- bereinige"
                    )
                    try:
                        self._con.execute(
                            "DELETE FROM editor_locks WHERE resource=? "
                            "AND (locked_at IS NULL OR lock_id IS NULL)",
                            (self._LOCK_RESOURCE,),
                        )
                        self._con.commit()
                    except Exception:
                        pass
                    return None
                return EditorLockRecord(
                    resource=str(row["resource"]),
                    locked_by=str(row["locked_by"] or ""),
                    lock_id=str(row["lock_id"]),
                    locked_at=int(row["locked_at"]),
                    sse_client=str(row["sse_client"] or ""),
                )
        except (sqlite3.OperationalError, sqlite3.ProgrammingError,
                sqlite3.InterfaceError, TypeError) as exc:
            logger.debug("get_lock fehlgeschlagen (ignoriert): %s", exc)
        return None

    def validate_lock(self, lock_id: str) -> bool:
        try:
            row = self._con.execute(
                "SELECT 1 FROM editor_locks WHERE resource=? AND lock_id=?",
                (self._LOCK_RESOURCE, lock_id),
            ).fetchone()
            return row is not None
        except sqlite3.OperationalError:
            return False

    # ------------------------------------------------------------------
    # Interne Hilfsmethoden
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_annotation(r: sqlite3.Row) -> AnnotationRecord:
        keys = r.keys()
        return AnnotationRecord(
            id=int(r["id"]),
            page_url=str(r["page_url"]),
            element_id=(
                str(r["element_id"]) if r["element_id"] is not None else None
            ),
            category=str(r["category"]),
            text=str(r["text"]),
            ts=int(r["ts"]),
            investigator_id=(
                int(r["investigator_id"])
                if r["investigator_id"] is not None else None
            ),
            selection_json=(
                str(r["selection_json"])
                if ("selection_json" in keys and r["selection_json"] is not None)
                else None
            ),
            tags_json=(
                str(r["tags_json"])
                if ("tags_json" in keys and r["tags_json"] is not None)
                else None
            ),
            local_id=(
                str(r["local_id"])
                if ("local_id" in keys and r["local_id"] is not None)
                else None
            ),
            post_id=(
                int(r["post_id"])
                if ("post_id" in keys and r["post_id"] is not None)
                else None
            ),
            created_by=(
                str(r["created_by"])
                if ("created_by" in keys and r["created_by"] is not None)
                else ""
            ),
        )

    @staticmethod
    def _row_to_report(r: sqlite3.Row) -> ReportRecord:
        return ReportRecord(
            id=int(r["id"]),
            report_type=str(r["report_type"]),
            sequence_nr=int(r["sequence_nr"]),
            title=str(r["title"]),
            created_by=str(r["created_by"]),
            created_at=int(r["created_at"]),
            status=str(r["status"]),
        )

    @staticmethod
    def _row_to_paragraph(r: sqlite3.Row) -> ReportParagraphRecord:
        return ReportParagraphRecord(
            block_id=str(r["block_id"]),
            report_id=int(r["report_id"]),
            author=str(r["author"]),
            created_at=int(r["created_at"]),
            updated_at=int(r["updated_at"]),
            content=str(r["content"]),
            status=str(r["status"]),
            placeholder_values_json=(
                str(r["placeholder_values_json"])
                if r["placeholder_values_json"] is not None else None
            ),
            omitted_by=(
                str(r["omitted_by"]) if r["omitted_by"] is not None else None
            ),
            omitted_at=(
                int(r["omitted_at"]) if r["omitted_at"] is not None else None
            ),
            omitted_reason=(
                str(r["omitted_reason"]) if r["omitted_reason"] is not None else None
            ),
            module_id=(
                int(r["module_id"]) if r["module_id"] is not None else None
            ),
        )

    @staticmethod
    def _row_to_comment(r: sqlite3.Row) -> ReportCommentRecord:
        return ReportCommentRecord(
            id=int(r["id"]),
            block_id=str(r["block_id"]),
            author=str(r["author"]),
            created_at=int(r["created_at"]),
            comment_text=str(r["comment_text"]),
            status=str(r["status"]),
            suggested_content=(
                str(r["suggested_content"])
                if r["suggested_content"] is not None else None
            ),
            resolved_by=(
                str(r["resolved_by"]) if r["resolved_by"] is not None else None
            ),
            resolved_at=(
                int(r["resolved_at"]) if r["resolved_at"] is not None else None
            ),
        )

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
#   Build 098: get_lock() nutzt eigene kurzlebige Connection wenn db_path gesetzt.
#     Verhindert 'bad parameter or other API misuse' im SSE-Thread.
#     EvidenceDb.__init__() bekommt optionalen db_path-Parameter.
#     Beleg: Build 098, Thread-Safety-Fix, Projektgespraech 2026-05-06
#
#   Build 099 (B6 — Phase 1: Schema bereinigen):
#     - report_paragraphs ersetzt durch report_blocks (Editor.js-Blockmodell).
#       Neues Schema: block_type (Editor.js-Tool-Name), block_data (JSON),
#       placeholder_values_json. Entfernte Felder: content, status,
#       omitted_by, omitted_at, omitted_reason.
#     - Paragraph-Lifecycle (draft/active/omitted/superseded/approved) entfernt.
#       Freigabe wird ausschliesslich auf Berichtsebene (reports.status) verwaltet.
#     - VALID_PARAGRAPH_STATUSES entfernt.
#     - Dataclass ReportParagraphRecord ersetzt durch ReportBlockRecord.
#     - Umbenennung Methoden: add_paragraph->save_block, get_paragraph->get_block,
#       get_paragraphs->get_blocks_for_report,
#       update_paragraph_content->update_block,
#       get_anchors_for_paragraph->get_anchors_for_block,
#       get_comments_for_paragraph->get_comments_for_block.
#     - set_paragraph_status() entfernt (kein Block-Status-Lifecycle mehr).
#     - get_report_status() auf report_blocks umgeschrieben.
#     - get_block_order_for_report() Join auf report_blocks umgeschrieben.
#     - resolve_comment() Join auf report_blocks umgeschrieben.
#     - _row_to_paragraph() umbenannt in _row_to_block().
#     - _MIGRATION_COLUMNS: report_paragraphs-Migration ergaenzt (Tabelle bleibt
#       fuer Altdaten erhalten, wird aber nicht mehr befuellt).
#     - Synchronisation mit stage2/evidence_db_init.py erforderlich.
#     Beleg: Bauplan B6 v0.5 §2.3, Projektgespraech 2026-05-06
#
#   Synchronisation:
#   _SCHEMA_DDL muss mit stage2/evidence_db_init.py im Prepper synchron
#   gehalten werden. Letzte Synchronisation: Build 099 (B6-Phase-1), 2026-05-06.
#
# Abhaengigkeiten: sqlite3, time, json, uuid -- ausschliesslich Stdlib
#
# Version: v0.6.178 · Build: 178 · 2026-05-12
#
#   Build 178 (BS3 — Bug 2.75):
#     - Soft-Delete + Append-only-Log für Annotationen.
#     - annotations: neue Spalten deleted_at, version_nr, prev_id.
#     - delete_annotation(): setzt deleted_at statt DELETE FROM.
#     - save_annotation(): neue Version anlegen (version_nr++, prev_id)
#       statt UPDATE; Vorgänger bekommt deleted_at=now (changed_at).
#     - get_annotations() / get_all_annotations(): WHERE deleted_at IS NULL.
#     - get_deleted_annotations(page_url): gelöschte ohne Nachfolger.
#     - restore_annotation(id): deleted_at=NULL zurücksetzen.
#     - get_annotation_history(annotation_id): Versionskette via prev_id.
#     - annotation_count(): nur aktive (deleted_at IS NULL).
#     - AnnotationRecord: neue Felder deleted_at, version_nr, prev_id.
#     - Beleg: Projektgespräch 2026-05-12 — Bug 2.75 (BS3).
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
    created_by      TEXT NOT NULL DEFAULT '',
    -- Build 178 (Bug 2.75): Soft-Delete + Append-only-Log
    deleted_at      INTEGER DEFAULT NULL,
    version_nr      INTEGER NOT NULL DEFAULT 1,
    prev_id         INTEGER DEFAULT NULL REFERENCES annotations(id),
    -- Build 182 (Bug 2.78): Forenbenutzer dem die Annotation inhaltlich gilt.
    -- NULL / fehlt = gehört zur uid dieser evidence_<uid>.db (Normalfall).
    -- Gesetzt = Ermittler hat auf Seiten von uid einen Hinweis zu uid2 gefunden;
    --   actual_uid = uid2. Trigger für Transportkopie in pending_cross_annotations.
    -- Beleg: Projektgespräch 2026-05-12.
    actual_uid      INTEGER DEFAULT NULL
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

-- Editor.js-Bloecke: ein Datensatz pro Editor.js-Block.
-- author ist unveraenderlich (Grundregel 14).
-- block_type entspricht dem Editor.js-Tool-Namen:
--   'paragraph', 'header', 'list', 'table', 'quote',
--   'image', 'delimiter', 'marker', 'evidence'.
-- block_data ist das Editor.js-Datenfeld als JSON-String.
-- placeholder_values_json speichert befuellte m:/o:-Werte: {"name": "wert"}.
-- module_id referenziert templates.report_modules.id (NULL = Freitext-Block).
--   Keine FK-Constraint, da templates.db per ATTACH eingebunden ist.
-- Freigabe liegt ausschliesslich auf Berichtsebene (reports.status).
--   Kein Block-Status-Lifecycle. Beleg: Bauplan B6 v0.5 §2.3.
CREATE TABLE IF NOT EXISTS report_blocks (
    block_id                TEXT    NOT NULL PRIMARY KEY,  -- UUID, clientseitig erzeugt
    report_id               INTEGER NOT NULL REFERENCES reports(id),
    author                  TEXT    NOT NULL,
    created_at              INTEGER NOT NULL,
    updated_at              INTEGER NOT NULL,
    block_type              TEXT    NOT NULL,
    block_data              TEXT    NOT NULL DEFAULT '{}',
    placeholder_values_json TEXT,
    module_id               INTEGER
);

-- Reihenfolge der Bloecke.
-- Jede Umsortierung wird protokolliert (last_modified_by, last_modified_at).
-- Jeder Ermittler darf die Reihenfolge aller Bloecke aendern.
-- Beleg: Bauplan B6 v0.5 §2.3
CREATE TABLE IF NOT EXISTS report_block_order (
    block_id            TEXT    NOT NULL PRIMARY KEY
                        REFERENCES report_blocks(block_id),
    sort_index          INTEGER NOT NULL,
    last_modified_by    TEXT    NOT NULL,
    last_modified_at    INTEGER NOT NULL
);

-- Beweisanker: Verknuepfung Block <-> Annotation.
-- Dokumentiert welche Annotationen im Bericht verarbeitet wurden.
-- Beleg: Bauplan B6 v0.5 §2.3
CREATE TABLE IF NOT EXISTS report_anchors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    block_id        TEXT    NOT NULL REFERENCES report_blocks(block_id),
    annotation_id   INTEGER NOT NULL REFERENCES annotations(id),
    anchor_text     TEXT    NOT NULL,
    created_at      INTEGER NOT NULL
);

-- Kommentare zu fremden Bloecken.
-- Status-Uebergaenge sind One-Way (Grundregel 15).
-- Beleg: Bauplan B6 v0.5 §2.3
CREATE TABLE IF NOT EXISTS report_comments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    block_id            TEXT    NOT NULL REFERENCES report_blocks(block_id),
    author              TEXT    NOT NULL,
    created_at          INTEGER NOT NULL,
    comment_text        TEXT    NOT NULL,
    suggested_content   TEXT,              -- Optionaler konkreter Ersatztext
    status              TEXT    NOT NULL DEFAULT 'pending'
                        CHECK (status IN (
                            'pending',     -- Offen
                            'addressed',   -- Bearbeitet (Block-Eigentuemer oder Chef)
                            'dismissed',   -- Abgelehnt (Block-Eigentuemer oder Chef)
                            'revoked'      -- Zurueckgezogen (nur Kommentator selbst)
                        )),
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

-- Ermittler-Aliasse: Suchbegriffe die auf allen Seiten gehighlightet werden.
-- Build 179 (Bug 2.79): Vom Ermittler gepflegte Liste von Begriffen,
-- die immer im Forum-Text hervorgehoben werden (z.B. Spitznamen).
-- Gehört zu evidence_<uid>.db (benutzerspezifisch).
CREATE TABLE IF NOT EXISTS investigator_aliases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    term        TEXT    NOT NULL UNIQUE,   -- Suchbegriff (case-insensitive UNIQUE)
    created_by  TEXT    NOT NULL DEFAULT '',
    created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ia_term_idx ON investigator_aliases (term);

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
-- Build 178: ann_active_url_idx und ann_prev_id_idx werden in
-- _migrate_schema() angelegt (setzen deleted_at/prev_id voraus,
-- die per ALTER TABLE ergänzt werden). Beleg: T24-Regression Build 178.
CREATE INDEX IF NOT EXISTS rep_type_idx     ON reports (report_type);
CREATE INDEX IF NOT EXISTS rep_status_idx   ON reports (status);
CREATE INDEX IF NOT EXISTS rb_report_idx    ON report_blocks (report_id);
CREATE INDEX IF NOT EXISTS rb_author_idx    ON report_blocks (author);
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

-- Build 178: annotations_local_id_uniq (UNIQUE) entfernt — Append-only-Log
-- erlaubt mehrere Datensätze mit gleicher local_id (Versionen).
-- ann_local_id_idx (nicht-unique) wird in _migrate_schema() angelegt.
-- save_annotation() sucht aktiven Eintrag via local_id + deleted_at IS NULL.
"""

# Migrationsspalten fuer aeltere evidence_db-Instanzen.
# Beleg: Build 061, Build 089
_MIGRATION_COLUMNS: list[tuple[str, str, str]] = [
    ("annotations", "selection_json", "TEXT DEFAULT NULL"),
    ("annotations", "tags_json",      "TEXT DEFAULT NULL"),
    ("annotations", "local_id",       "TEXT DEFAULT NULL"),
    ("annotations", "post_id",        "INTEGER DEFAULT NULL"),
    ("annotations", "created_by",     "TEXT NOT NULL DEFAULT ''"),
    # Build 178 (Bug 2.75): Soft-Delete + Append-only-Log
    ("annotations", "deleted_at",     "INTEGER DEFAULT NULL"),
    ("annotations", "version_nr",     "INTEGER NOT NULL DEFAULT 1"),
    ("annotations", "prev_id",        "INTEGER DEFAULT NULL"),
    # Build 182 (Bug 2.78): Forenbenutzer dem die Annotation inhaltlich gilt
    ("annotations", "actual_uid",     "INTEGER DEFAULT NULL"),
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
    # Build 178 (Bug 2.75): Soft-Delete + Versionierung
    deleted_at:  Optional[int] = None
    version_nr:  int           = 1
    prev_id:     Optional[int] = None
    # Build 182 (Bug 2.78): Forenbenutzer dem die Annotation inhaltlich gilt
    actual_uid:  Optional[int] = None  # NULL = uid dieser DB, sonst Fremd-uid


@dataclass
class AliasRecord:
    """Ermittler-Alias (Suchbegriff für dauerhaftes Highlighting).
    Beleg: Bug 2.79, Build 179.
    """
    id:         int
    term:       str
    created_by: str = ""
    created_at: int = 0


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
class ReportBlockRecord:
    """Ein Editor.js-Block im Bericht (Baustelle 6).

    block_type entspricht dem Editor.js-Tool-Namen: 'paragraph', 'header',
    'list', 'table', 'quote', 'image', 'delimiter', 'marker', 'evidence'.
    block_data ist das Editor.js-Datenfeld als JSON-String.
    author ist unveraenderlich (Grundregel 14).
    Beleg: Bauplan B6 v0.5 §2.3, Projektgespraech 2026-05-06
    """
    block_id:                str
    report_id:               int
    author:                  str
    created_at:              int
    updated_at:              int
    block_type:              str
    block_data:              str
    placeholder_values_json: Optional[str] = None
    module_id:               Optional[int] = None


@dataclass
class ReportAnchorRecord:
    """Beweisanker Block <-> Annotation (Baustelle 6).
    Beleg: Bauplan B6 v0.5 §2.3
    """
    id:            int
    block_id:      str
    annotation_id: int
    anchor_text:   str
    created_at:    int


@dataclass
class ReportCommentRecord:
    """Kommentar zu einem Block (Baustelle 6).
    Beleg: Bauplan B6 v0.5 §2.3
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

    _LOCK_RESOURCE_BASE = "report_editor"
    # Fester Fallback — wird durch _lock_resource(report_id) ersetzt.
    # Beleg: Bug 2.120 Fix Build 218, Projektgespraech 2026-05-17
    _LOCK_RESOURCE = "report_editor"  # Kompatibilitaets-Fallback

    @staticmethod
    def _lock_resource(report_id: Optional[int]) -> str:
        """Bericht-spezifischer Lock-Resource-Name.

        Bug 2.120 Fix Build 218: Der Lock war bisher global (resource=
        "report_editor") und kannte keinen Bericht-Bezug. Dadurch war
        kein gleichzeitiges Arbeiten an verschiedenen Berichten moeglich,
        und ein Bericht-Wechsel konnte Daten loeschen.
        Beleg: Bugfix Build 218, Projektgespraech 2026-05-17
        """
        if report_id is None:
            return "report_editor"
        return f"report_editor:{report_id}"

    def __init__(self, con: sqlite3.Connection, db_path: Optional[str] = None) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        # Pfad zur DB-Datei fuer get_lock() (eigene Connection, Thread-Safety).
        # Beleg: Build 098, Thread-Safety-Fix fuer SSE-Thread
        self._db_path: Optional[str] = db_path
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

        # Build 178 (Bug 2.75): annotations_local_id_uniq ENTFERNT.
        # Der eindeutige Index auf local_id verhindert mehrere Versionen
        # mit gleicher local_id (Append-only-Prinzip). Er wird durch
        # ann_local_id_idx (nicht-unique) ersetzt.
        # Beleg: Projektgespräch 2026-05-12 — T63-Regression.
        try:
            self._con.execute("DROP INDEX IF EXISTS annotations_local_id_uniq")
            self._con.execute(
                "CREATE INDEX IF NOT EXISTS ann_local_id_idx "
                "ON annotations (local_id) WHERE local_id IS NOT NULL"
            )
            self._con.commit()
            logger.debug("evidence_db Migration: ann_local_id_idx (nicht-unique) sichergestellt")
        except sqlite3.OperationalError as exc:
            logger.warning(
                "evidence_db Migration: ann_local_id_idx fehlgeschlagen: %s", exc
            )

        # Build 178 (Bug 2.75): Partielle Indizes auf new columns anlegen.
        # Müssen nach ALTER TABLE (Migration) angelegt werden, da sie
        # deleted_at / prev_id voraussetzen.
        # Beleg: T24-Regression Build 178 — partieller Index mit WHERE deleted_at
        # schlägt in _SCHEMA_DDL fehl wenn Spalte noch nicht existiert.
        _partial_indices = [
            (
                "ann_active_url_idx",
                "CREATE INDEX IF NOT EXISTS ann_active_url_idx "
                "ON annotations (page_url) WHERE deleted_at IS NULL",
            ),
            (
                "ann_prev_id_idx",
                "CREATE INDEX IF NOT EXISTS ann_prev_id_idx "
                "ON annotations (prev_id) WHERE prev_id IS NOT NULL",
            ),
        ]
        for idx_name, idx_ddl in _partial_indices:
            try:
                self._con.execute(idx_ddl)
                self._con.commit()
                logger.debug("evidence_db Migration: Index '%s' sichergestellt", idx_name)
            except sqlite3.OperationalError as exc:
                logger.warning(
                    "evidence_db Migration: Index '%s' fehlgeschlagen: %s",
                    idx_name, exc,
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
        actual_uid: Optional[int] = None,
    ) -> int:
        """
        Speichert eine Annotation nach dem Append-only-Log-Prinzip.

        Build 178 (Bug 2.75): Kein UPDATE mehr. Stattdessen:
          - Existiert bereits ein aktiver Datensatz mit gleicher local_id,
            wird dieser als Vorgänger markiert (deleted_at = now) und ein
            neuer Datensatz angelegt (version_nr++, prev_id = alter.id).
          - Existiert noch kein Datensatz für local_id, wird er neu angelegt
            (version_nr = 1, prev_id = NULL).
          - Ohne local_id: immer Insert (anonyme Einmal-Annotation).

        Semantik deleted_at beim Vorgänger:
          Vorgänger.deleted_at gesetzt + neuer Datensatz mit prev_id = Vorgänger.id
          → Bedeutung: "geändert am ts", nicht "gelöscht".
          Beleg: Projektgespräch 2026-05-12 — Bug 2.75 (BS3).
        """
        if category not in VALID_CATEGORIES:
            raise EvidenceDbError(
                f"Unbekannte Kategorie '{category}'. "
                f"Zulaessig: {sorted(VALID_CATEGORIES)}"
            )
        if ts is None:
            ts = int(time.time())

        if local_id is not None:
            # Aktiven Vorgänger suchen (deleted_at IS NULL)
            existing = self._con.execute(
                "SELECT id, version_nr FROM annotations "
                "WHERE local_id = ? AND deleted_at IS NULL",
                (local_id,),
            ).fetchone()

            if existing is not None:
                # Append-only: Vorgänger als "ersetzt" markieren (deleted_at = now)
                # und neuen Datensatz anlegen (version_nr+1, prev_id = alter.id).
                old_id      = int(existing["id"])
                new_version = int(existing["version_nr"]) + 1

                self._con.execute(
                    "UPDATE annotations SET deleted_at = ? WHERE id = ?",
                    (ts, old_id),
                )
                cursor = self._con.execute(
                    "INSERT INTO annotations "
                    "(page_url, element_id, category, text, ts, investigator_id,"
                    " selection_json, tags_json, local_id, post_id, created_by,"
                    " version_nr, prev_id, actual_uid) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        page_url, element_id, category, text, ts, investigator_id,
                        selection_json, tags_json, local_id, post_id, created_by,
                        new_version, old_id, actual_uid,
                    ),
                )
                logger.debug(
                    "save_annotation: Neue Version v%d für local_id=%s "
                    "(Vorgänger id=%d als ersetzt markiert)",
                    new_version, local_id, old_id,
                )
            else:
                # Ersteintrag für diese local_id
                cursor = self._con.execute(
                    "INSERT INTO annotations "
                    "(page_url, element_id, category, text, ts, investigator_id,"
                    " selection_json, tags_json, local_id, post_id, created_by,"
                    " version_nr, prev_id, actual_uid) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, ?)",
                    (
                        page_url, element_id, category, text, ts, investigator_id,
                        selection_json, tags_json, local_id, post_id, created_by,
                        actual_uid,
                    ),
                )
        else:
            # Ohne local_id: anonyme Einmal-Annotation, immer Insert
            cursor = self._con.execute(
                "INSERT INTO annotations "
                "(page_url, element_id, category, text, ts, investigator_id,"
                " selection_json, tags_json, local_id, post_id, created_by,"
                " version_nr, prev_id, actual_uid) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, 1, NULL, ?)",
                (
                    page_url, element_id, category, text, ts, investigator_id,
                    selection_json, tags_json, post_id, created_by, actual_uid,
                ),
            )
        self._con.commit()
        return cursor.lastrowid or 0

    def delete_annotation(self, annotation_id: int) -> bool:
        """
        Soft-Delete: setzt deleted_at statt physisch zu löschen.

        Build 178 (Bug 2.75): Kein DELETE FROM mehr.
        Semantik: Eintrag ohne Nachfolger (kein anderer Datensatz hat prev_id=this.id)
        = tatsächlich gelöscht, wiederherstellbar via restore_annotation().
        Beleg: Projektgespräch 2026-05-12 — Bug 2.75 (BS3).
        """
        ts_now = int(time.time())
        cursor = self._con.execute(
            "UPDATE annotations SET deleted_at = ? "
            "WHERE id = ? AND deleted_at IS NULL",
            (ts_now, annotation_id),
        )
        self._con.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.debug("delete_annotation: Soft-Delete id=%d (deleted_at=%d)",
                         annotation_id, ts_now)
        else:
            logger.warning(
                "delete_annotation: id=%d nicht gefunden oder bereits gelöscht",
                annotation_id,
            )
        return deleted

    def restore_annotation(self, annotation_id: int) -> bool:
        """
        Stellt eine soft-gelöschte Annotation wieder her (deleted_at = NULL).

        Nur möglich wenn kein Nachfolger existiert (kein anderer Datensatz hat
        prev_id = annotation_id) — sonst wäre es eine Vorgängerversion, keine
        echte Löschung.
        Beleg: Projektgespräch 2026-05-12 — Bug 2.75 (BS3).
        """
        # Prüfen ob ein Nachfolger existiert (dann ist dies "nur" eine alte Version)
        successor = self._con.execute(
            "SELECT id FROM annotations WHERE prev_id = ? LIMIT 1",
            (annotation_id,),
        ).fetchone()
        if successor is not None:
            logger.warning(
                "restore_annotation: id=%d ist eine Vorgängerversion "
                "(Nachfolger id=%d) — keine Wiederherstellung möglich",
                annotation_id, int(successor["id"]),
            )
            return False

        cursor = self._con.execute(
            "UPDATE annotations SET deleted_at = NULL "
            "WHERE id = ? AND deleted_at IS NOT NULL",
            (annotation_id,),
        )
        self._con.commit()
        restored = cursor.rowcount > 0
        if restored:
            logger.info("restore_annotation: Wiederhergestellt id=%d", annotation_id)
        return restored

    def get_annotation_history(self, annotation_id: int) -> list[AnnotationRecord]:
        """
        Gibt die vollständige Versionskette einer Annotation zurück,
        geordnet von ältester zu aktuellster Version.

        Startet bei annotation_id und folgt prev_id-Zeigern rückwärts bis zum
        Ersteintrag (prev_id IS NULL). Gibt alle Versionen chronologisch zurück.
        Beleg: Projektgespräch 2026-05-12 — Bug 2.75 (BS3).
        """
        # Aktuellen Datensatz laden
        current = self._con.execute(
            "SELECT id, page_url, element_id, category, text, ts, "
            "       investigator_id, selection_json, tags_json, local_id, "
            "       post_id, created_by, deleted_at, version_nr, prev_id, actual_uid "
            "FROM annotations WHERE id = ?",
            (annotation_id,),
        ).fetchone()
        if current is None:
            return []

        chain: list[AnnotationRecord] = [self._row_to_annotation(current)]

        # Vorgängerkette rückwärts traversieren
        prev_id = current["prev_id"]
        visited: set[int] = {annotation_id}
        while prev_id is not None:
            if prev_id in visited:
                logger.warning(
                    "get_annotation_history: Zyklus entdeckt bei prev_id=%d", prev_id
                )
                break
            visited.add(prev_id)
            row = self._con.execute(
                "SELECT id, page_url, element_id, category, text, ts, "
                "       investigator_id, selection_json, tags_json, local_id, "
                "       post_id, created_by, deleted_at, version_nr, prev_id, actual_uid "
                "FROM annotations WHERE id = ?",
                (prev_id,),
            ).fetchone()
            if row is None:
                break
            chain.append(self._row_to_annotation(row))
            prev_id = row["prev_id"]

        # Älteste Version zuerst
        chain.reverse()
        return chain

    def get_deleted_annotations(
        self, page_url: Optional[str] = None
    ) -> list[AnnotationRecord]:
        """
        Gibt tatsächlich gelöschte Annotationen zurück — d.h. Einträge mit
        deleted_at IS NOT NULL ohne Nachfolger (kein anderer Datensatz hat
        prev_id = this.id). Vorgängerversionen (mit Nachfolger) werden nicht
        zurückgegeben.

        Args:
            page_url: Wenn angegeben, nur Annotationen dieser Seite.
        Beleg: Projektgespräch 2026-05-12 — Bug 2.75 (BS3).
        """
        # Subquery: Alle prev_ids die als Vorgänger referenziert werden
        base_query = (
            "SELECT id, page_url, element_id, category, text, ts, "
            "       investigator_id, selection_json, tags_json, local_id, "
            "       post_id, created_by, deleted_at, version_nr, prev_id, actual_uid "
            "FROM annotations "
            "WHERE deleted_at IS NOT NULL "
            "  AND id NOT IN (SELECT prev_id FROM annotations WHERE prev_id IS NOT NULL)"
        )
        if page_url:
            rows = self._con.execute(
                base_query + " AND page_url = ? ORDER BY deleted_at DESC",
                (page_url,),
            ).fetchall()
        else:
            rows = self._con.execute(
                base_query + " ORDER BY deleted_at DESC"
            ).fetchall()
        return [self._row_to_annotation(r) for r in rows]

    def get_annotations(self, page_url: str) -> list[AnnotationRecord]:
        """Gibt aktive Annotationen für eine URL zurück (deleted_at IS NULL)."""
        rows = self._con.execute(
            "SELECT id, page_url, element_id, category, text, ts, "
            "       investigator_id, selection_json, tags_json, local_id, "
            "       post_id, created_by, deleted_at, version_nr, prev_id, actual_uid "
            "FROM annotations "
            "WHERE page_url = ? AND deleted_at IS NULL "
            "ORDER BY ts ASC",
            (page_url,),
        ).fetchall()
        return [self._row_to_annotation(r) for r in rows]

    def get_all_annotations(self) -> list[AnnotationRecord]:
        """Gibt alle aktiven Annotationen zurück (deleted_at IS NULL)."""
        rows = self._con.execute(
            "SELECT id, page_url, element_id, category, text, ts, "
            "       investigator_id, selection_json, tags_json, local_id, "
            "       post_id, created_by, deleted_at, version_nr, prev_id, actual_uid "
            "FROM annotations "
            "WHERE deleted_at IS NULL "
            "ORDER BY ts DESC"
        ).fetchall()
        return [self._row_to_annotation(r) for r in rows]

    def annotation_count(self) -> int:
        """Zählt nur aktive Annotationen (deleted_at IS NULL)."""
        row = self._con.execute(
            "SELECT COUNT(*) FROM annotations WHERE deleted_at IS NULL"
        ).fetchone()
        return int(row[0]) if row else 0

    # ------------------------------------------------------------------
    # Ermittler-Aliasse (Bug 2.79, Build 179)
    # ------------------------------------------------------------------

    def save_alias(self, term: str, created_by: str = "") -> int:
        """
        Legt einen neuen Alias-Begriff an oder gibt die ID des bestehenden zurück.
        UNIQUE auf term (COLLATE NOCASE via SQL-Vergleich).
        Beleg: Bug 2.79 — Projektgespräch 2026-05-12.
        """
        term = term.strip()
        if not term:
            raise EvidenceDbError("Alias-Begriff darf nicht leer sein")
        ts = int(time.time())
        try:
            cursor = self._con.execute(
                "INSERT INTO investigator_aliases (term, created_by, created_at) "
                "VALUES (?, ?, ?)",
                (term, created_by, ts),
            )
            self._con.commit()
            return cursor.lastrowid or 0
        except sqlite3.IntegrityError:
            # Term existiert bereits (UNIQUE-Constraint)
            row = self._con.execute(
                "SELECT id FROM investigator_aliases WHERE term = ? COLLATE NOCASE",
                (term,),
            ).fetchone()
            return int(row["id"]) if row else 0

    def delete_alias(self, alias_id: int) -> bool:
        """Löscht einen Alias-Eintrag anhand seiner ID. Physisches Delete (kein Soft-Delete)."""
        cursor = self._con.execute(
            "DELETE FROM investigator_aliases WHERE id = ?", (alias_id,)
        )
        self._con.commit()
        return cursor.rowcount > 0

    def get_aliases(self) -> list:
        """Gibt alle Aliasse alphabetisch sortiert zurück."""
        rows = self._con.execute(
            "SELECT id, term, created_by, created_at "
            "FROM investigator_aliases ORDER BY term ASC"
        ).fetchall()
        result = []
        for r in rows:
            result.append(AliasRecord(
                id=int(r["id"]),
                term=str(r["term"]),
                created_by=str(r["created_by"]) if r["created_by"] else "",
                created_at=int(r["created_at"]),
            ))
        return result

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
        Beleg: B6 Build 099 -- auf report_blocks umgeschrieben (Phase 1).
        """
        try:
            block_row = self._con.execute(
                "SELECT rb.updated_at, rb.author "
                "FROM report_blocks rb "
                "ORDER BY rb.updated_at DESC LIMIT 1"
            ).fetchone()
            appr_row = self._con.execute(
                "SELECT approved_by FROM report_approvals "
                "ORDER BY approved_at DESC LIMIT 1"
            ).fetchone()
            count_row = self._con.execute(
                "SELECT COUNT(*) FROM reports"
            ).fetchone()
            return {
                "has_draft":    block_row is not None,
                "last_edit_ts": int(block_row["updated_at"]) if block_row else None,
                "last_editor":  str(block_row["author"]) if block_row else None,
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
    # Bloecke (report_blocks, B6)
    # Beleg: Bauplan B6 v0.5 §2.3, Projektgespraech 2026-05-06
    # ------------------------------------------------------------------

    def save_block(
        self,
        block_id: str,
        report_id: int,
        author: str,
        block_type: str,
        block_data: str = "{}",
        module_id: Optional[int] = None,
        placeholder_values_json: Optional[str] = None,
        sort_index: Optional[int] = None,
    ) -> str:
        """
        Speichert einen Editor.js-Block (INSERT OR REPLACE).

        Beim ersten Anlegen: author wird dauerhaft als Eigentuemer gesetzt.
        Bei UPDATE: author-Prueefung erfolgt im Aufrufer (editor_block.py).
        sort_index: Wird in report_block_order eingetragen wenn angegeben.

        Args:
            block_id:   UUID, clientseitig erzeugt.
            report_id:  Referenz auf reports.id.
            author:     SAMAccountName -- Eigentuemer, nie aenderbar.
            block_type: Editor.js-Tool-Name (z.B. 'paragraph', 'header').
            block_data: Editor.js-Datenfeld als JSON-String.
            module_id:  Referenz auf templates.report_modules.id (optional).
            placeholder_values_json: JSON-String {name: value} fuer m:/o:-Felder.
            sort_index: Initiale Sortierposition in report_block_order.

        Returns:
            block_id (unveraendert).

        Raises:
            EvidenceDbError: Bei leerem author, leerem block_type.
        """
        if not author.strip():
            raise EvidenceDbError("author darf nicht leer sein.")
        if not block_type.strip():
            raise EvidenceDbError("block_type darf nicht leer sein.")

        now = int(time.time())
        # Bestehenden Block laden um created_at zu erhalten (autor ist unveraenderlich).
        existing = self._con.execute(
            "SELECT created_at, author FROM report_blocks WHERE block_id = ?",
            (block_id,),
        ).fetchone()
        if existing is not None:
            # UPDATE: created_at und author bleiben unveraendert.
            # Bug 2.51 Fix Build 144: placeholder_values_json nur ueberschreiben
            # wenn im Request-Payload explizit enthalten. Der normale Auto-Save
            # (_performAutoSave) sendet das Feld nicht — NULL wuerde den zuvor
            # gespeicherten Wert loeschen. Loesung: COALESCE erhalt den DB-Wert
            # wenn None uebergeben wird.
            # Beleg: Bugfix Build 144, Projektgespraech 2026-05-10
            if placeholder_values_json is not None:
                self._con.execute(
                    "UPDATE report_blocks "
                    "SET report_id=?, updated_at=?, block_type=?, block_data=?, "
                    "    placeholder_values_json=?, module_id=? "
                    "WHERE block_id=?",
                    (
                        report_id, now, block_type.strip(), block_data,
                        placeholder_values_json, module_id, block_id,
                    ),
                )
            else:
                # placeholder_values_json nicht im Request — vorhandenen DB-Wert beibehalten
                self._con.execute(
                    "UPDATE report_blocks "
                    "SET report_id=?, updated_at=?, block_type=?, block_data=?, "
                    "    module_id=? "
                    "WHERE block_id=?",
                    (
                        report_id, now, block_type.strip(), block_data,
                        module_id, block_id,
                    ),
                )
        else:
            # INSERT: neuer Block.
            self._con.execute(
                "INSERT INTO report_blocks "
                "(block_id, report_id, author, created_at, updated_at, "
                " block_type, block_data, placeholder_values_json, module_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    block_id, report_id, author.strip(), now, now,
                    block_type.strip(), block_data,
                    placeholder_values_json, module_id,
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
            "Block gespeichert: block_id=%s type=%s report_id=%d von '%s'",
            block_id, block_type, report_id, author,
        )
        return block_id

    def get_block(self, block_id: str) -> Optional[ReportBlockRecord]:
        """Einzelnen Block per block_id laden."""
        row = self._con.execute(
            "SELECT block_id, report_id, author, created_at, updated_at, "
            "       block_type, block_data, placeholder_values_json, module_id "
            "FROM report_blocks WHERE block_id = ?",
            (block_id,),
        ).fetchone()
        return self._row_to_block(row) if row else None

    def get_blocks_for_report(self, report_id: int) -> list[ReportBlockRecord]:
        """
        Alle Bloecke eines Berichts, sortiert nach sort_index ASC.
        Bloecke ohne Sortierungseintrag werden ans Ende gestellt.
        """
        rows = self._con.execute(
            "SELECT rb.block_id, rb.report_id, rb.author, rb.created_at, "
            "       rb.updated_at, rb.block_type, rb.block_data, "
            "       rb.placeholder_values_json, rb.module_id "
            "FROM report_blocks rb "
            "LEFT JOIN report_block_order rbo ON rbo.block_id = rb.block_id "
            "WHERE rb.report_id = ? "
            "ORDER BY COALESCE(rbo.sort_index, 999999) ASC, rb.created_at ASC",
            (report_id,),
        ).fetchall()
        return [self._row_to_block(r) for r in rows]

    def update_block(
        self,
        block_id: str,
        block_data: str,
        placeholder_values_json: Optional[str],
        requesting_author: str,
    ) -> bool:
        """
        Aktualisiert block_data und Platzhalter-Werte eines Blocks.
        Nur der Eigentuemer darf bearbeiten (Grundregel 14).
        Nach Berichts-Freigabe (reports.status='approved') nicht moeglich.

        Returns:
            True wenn gespeichert, False wenn Block nicht gefunden.

        Raises:
            EvidenceDbError: Wenn nicht Eigentuemer oder Bericht freigegeben.
        """
        row = self._con.execute(
            "SELECT rb.author, r.status AS report_status "
            "FROM report_blocks rb "
            "JOIN reports r ON r.id = rb.report_id "
            "WHERE rb.block_id = ?",
            (block_id,),
        ).fetchone()
        if not row:
            return False
        if str(row["report_status"]) == "approved":
            raise EvidenceDbError(
                "Freigegebene Berichte koennen nicht mehr bearbeitet werden."
            )
        if str(row["author"]) != requesting_author:
            raise EvidenceDbError(
                f"Nur der Eigentuemer darf einen Block bearbeiten. "
                f"Eigentuemer: '{row['author']}'"
            )
        now = int(time.time())
        self._con.execute(
            "UPDATE report_blocks "
            "SET block_data = ?, placeholder_values_json = ?, updated_at = ? "
            "WHERE block_id = ?",
            (block_data, placeholder_values_json, now, block_id),
        )
        self._con.commit()
        return True

    def delete_block(self, block_id: str, requesting_author: str) -> bool:
        """
        Loescht einen Block aus report_blocks.
        Nur der Eigentuemer darf loeschen (Grundregel 14).
        Nach Berichts-Freigabe nicht moeglich.

        Returns:
            True wenn geloescht, False wenn Block nicht gefunden.
        """
        row = self._con.execute(
            "SELECT rb.author, r.status AS report_status "
            "FROM report_blocks rb "
            "JOIN reports r ON r.id = rb.report_id "
            "WHERE rb.block_id = ?",
            (block_id,),
        ).fetchone()
        if not row:
            return False
        if str(row["report_status"]) == "approved":
            raise EvidenceDbError(
                "Freigegebene Berichte koennen nicht mehr veraendert werden."
            )
        if str(row["author"]) != requesting_author:
            raise EvidenceDbError(
                f"Nur der Eigentuemer darf einen Block loeschen. "
                f"Eigentuemer: '{row['author']}'"
            )
        # Kaskade: report_block_order, report_anchors, report_comments mitloeschen.
        self._con.execute(
            "DELETE FROM report_block_order WHERE block_id = ?", (block_id,)
        )
        self._con.execute(
            "DELETE FROM report_anchors WHERE block_id = ?", (block_id,)
        )
        self._con.execute(
            "DELETE FROM report_comments WHERE block_id = ?", (block_id,)
        )
        cursor = self._con.execute(
            "DELETE FROM report_blocks WHERE block_id = ?", (block_id,)
        )
        self._con.commit()
        if cursor.rowcount > 0:
            logger.info("Block geloescht: block_id=%s von '%s'", block_id, requesting_author)
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Blockreihenfolge (report_block_order, B6)
    # Beleg: Bauplan B6 v0.5 §2.3
    # ------------------------------------------------------------------

    def get_block_order_for_report(self, report_id: int) -> list[dict]:
        """
        Gibt die Sortierungseintraege aller Bloecke eines Berichts zurueck.
        Beleg: Bauplan B6 v0.5 §5 (action=reorder)
        """
        rows = self._con.execute(
            "SELECT rbo.block_id, rbo.sort_index, rbo.last_modified_by, "
            "       rbo.last_modified_at "
            "FROM report_block_order rbo "
            "JOIN report_blocks rb ON rb.block_id = rbo.block_id "
            "WHERE rb.report_id = ? "
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
        Setzt die Sortierungsreihenfolge fuer mehrere Bloecke.
        Jeder Ermittler darf die Reihenfolge aendern (Bauplan B6 v0.5 §2.3).

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

    def get_sort_index_after(self, after_block_id: str, report_id: int) -> int:
        """
        Berechnet einen sort_index fuer einen neuen Block, der nach
        after_block_id eingefuegt werden soll.

        Strategie:
          1. sort_index von after_block_id ermitteln (Basis).
          2. Alle Bloecke mit sort_index > Basis um +2 verschieben,
             damit Platz fuer den neuen Block entsteht.
          3. Neuer sort_index = Basis + 1.

        Falls after_block_id nicht gefunden: maximaler sort_index + 1000
        (Block ans Ende).

        Bug 2.114 Fix Build 206: Doppelklick fuegt Modul nach Cursor-Block ein.
        Beleg: Bugfix Build 206, Projektgespraech 2026-05-17
        """
        now = int(time.time())

        # Basis-sort_index des Vorgaengers ermitteln
        row = self._con.execute(
            "SELECT rbo.sort_index FROM report_block_order rbo "
            "WHERE rbo.block_id = ?",
            (after_block_id,),
        ).fetchone()

        if row is None:
            # after_block_id unbekannt oder ohne Sortierungseintrag →
            # maximalen sort_index des Berichts +1000 verwenden (Ende)
            max_row = self._con.execute(
                "SELECT MAX(rbo.sort_index) AS m FROM report_block_order rbo "
                "JOIN report_blocks rb ON rb.block_id = rbo.block_id "
                "WHERE rb.report_id = ?",
                (report_id,),
            ).fetchone()
            max_idx = int(max_row["m"]) if max_row and max_row["m"] is not None else 0
            return max_idx + 1000

        base = int(row["sort_index"])

        # Alle nachfolgenden Bloecke um +2 verschieben
        self._con.execute(
            "UPDATE report_block_order SET sort_index = sort_index + 2, "
            "last_modified_at = ? "
            "WHERE block_id IN ("
            "  SELECT rbo.block_id FROM report_block_order rbo "
            "  JOIN report_blocks rb ON rb.block_id = rbo.block_id "
            "  WHERE rb.report_id = ? AND rbo.sort_index > ?"
            ")",
            (now, report_id, base),
        )
        # Kein separates commit — wird vom aufrufenden save_block-commit erfasst.
        return base + 1

    # ------------------------------------------------------------------
    # Beweisanker (report_anchors, B6)
    # Beleg: Bauplan B6 v0.5 §2.3, §4.7
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

    def get_anchors_for_block(self, block_id: str) -> list[ReportAnchorRecord]:
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

    def get_blocks_for_evidence(self, annotation_id: int) -> list:
        """
        Gibt alle block_ids zurueck, die eine bestimmte annotation_id als
        Beweisanker (report_anchors) referenzieren.

        Wird von EditorEvidenceEndpoint._action_add() und ._action_remove()
        genutzt, um nach einer Aenderung die betroffenen Bloecke zu melden.

        Bug 2.10 Fix Build 160: Methode war im Changelog erwaehnt, aber nicht
        implementiert. Der fehlende Aufruf erzeugte AttributeError -> HTTP 500.
        Beleg: Projektgespraech 2026-05-11
        """
        rows = self._con.execute(
            "SELECT DISTINCT block_id FROM report_anchors WHERE annotation_id = ?",
            (annotation_id,),
        ).fetchall()
        # Gibt eine Liste von Objekten mit .block_id-Attribut zurueck,
        # kompatibel mit dem bestehenden Aufruf-Muster in editor_evidence.py
        # (r.block_id fuer r in ...).
        class _Row:
            __slots__ = ("block_id",)
            def __init__(self, bid: str) -> None:
                self.block_id = bid
        return [_Row(str(r[0])) for r in rows]

    def remove_block_evidence(self, block_id: str, evidence_id: int) -> bool:
        """
        Loescht einen Beweisanker (report_anchors) anhand block_id und
        annotation_id. Gibt True zurueck wenn ein Datensatz geloescht wurde.

        Bug 2.10 Fix Build 160: Methode war im Changelog erwaehnt, aber nicht
        implementiert. Der fehlende Aufruf erzeugte AttributeError -> HTTP 500.
        Beleg: Projektgespraech 2026-05-11
        """
        cur = self._con.execute(
            "DELETE FROM report_anchors WHERE block_id = ? AND annotation_id = ?",
            (block_id, evidence_id),
        )
        self._con.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Kommentare (report_comments, B6)
    # Beleg: Bauplan B6 v0.5 §2.3, Grundregel 15
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

    def get_comments_for_block(self, block_id: str) -> list[ReportCommentRecord]:
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
            "SELECT rc.author, rc.status, rb.author as block_author "
            "FROM report_comments rc "
            "JOIN report_blocks rb ON rb.block_id = rc.block_id "
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
            if str(row["block_author"]) != requesting_user and not is_chef:
                raise EvidenceDbError(
                    "Nur der Eigentuemer des Blocks oder die "
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
    # Beleg: Bauplan B6 v0.5 §2.3, §3.1, §3.2
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
        Beleg: Bauplan B6 v0.5 §3.1 (Cache-Hit)
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
        Beleg: Bauplan B6 v0.5 §3.2

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

    def acquire_lock(
        self, locked_by: str, sse_client: str,
        report_id: Optional[int] = None,
    ) -> Optional[str]:
        """Erwirbt den Lock fuer einen bestimmten Bericht.

        Bug 2.120 Fix Build 218: report_id als Pflichtparameter fuer
        bericht-spezifischen Lock.
        Beleg: Bugfix Build 218, Projektgespraech 2026-05-17
        """
        resource = self._lock_resource(report_id)
        now = int(time.time())
        new_lock_id = str(uuid.uuid4())
        try:
            self._con.execute(
                "DELETE FROM editor_locks WHERE resource=? AND locked_at < ?",
                (resource, now - self._LOCK_TIMEOUT_SEC),
            )
        except sqlite3.OperationalError:
            pass
        try:
            self._con.execute(
                "INSERT INTO editor_locks "
                "(resource, locked_by, lock_id, locked_at, sse_client) "
                "VALUES (?, ?, ?, ?, ?)",
                (resource, locked_by, new_lock_id, now, sse_client),
            )
            self._con.commit()
            self._lock_change_event.set()
            logger.info(
                "Editor-Lock erworben: '%s' rid=%s (lock_id=%s)",
                locked_by, report_id, new_lock_id,
            )
            return new_lock_id
        except sqlite3.IntegrityError:
            logger.debug(
                "acquire_lock: Lock bereits belegt fuer '%s'", resource
            )
            return None

    def release_lock(self, lock_id: str, report_id: Optional[int] = None) -> bool:
        resource = self._lock_resource(report_id)
        cursor = self._con.execute(
            "DELETE FROM editor_locks WHERE resource=? AND lock_id=?",
            (resource, lock_id),
        )
        self._con.commit()
        freed = cursor.rowcount > 0
        if freed:
            self._lock_change_event.set()
            logger.info("Editor-Lock freigegeben (lock_id=%s)", lock_id)
        return freed

    def release_lock_by_sse_client(
        self, sse_client: str, report_id: Optional[int] = None
    ) -> bool:
        resource = self._lock_resource(report_id)
        cursor = self._con.execute(
            "DELETE FROM editor_locks WHERE resource=? AND sse_client=?",
            (resource, sse_client),
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

    def resume_lock(
        self, lock_id: str, locked_by: str, new_sse_client: str,
        report_id: Optional[int] = None,
    ) -> bool:
        resource = self._lock_resource(report_id)
        try:
            cursor = self._con.execute(
                "UPDATE editor_locks "
                "SET sse_client = ?, locked_at = ? "
                "WHERE resource = ? AND lock_id = ? AND locked_by = ?",
                (
                    new_sse_client,
                    int(time.time()),
                    resource,
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

    def get_lock(self, report_id: Optional[int] = None) -> Optional[EditorLockRecord]:
        # Eigene kurzlebige Connection wenn _db_path gesetzt.
        # Verhindert 'bad parameter or other API misuse' wenn der SSE-Thread
        # und der Request-Thread gleichzeitig die geteilte Connection nutzen.
        # Beleg: Build 098, Thread-Safety-Fix fuer SSE-Thread
        if self._db_path:
            try:
                read_con = sqlite3.connect(
                    self._db_path,
                    timeout=5.0,
                    check_same_thread=False,
                )
                read_con.row_factory = sqlite3.Row
                row = read_con.execute(
                    "SELECT resource, locked_by, lock_id, locked_at, sse_client "
                    "FROM editor_locks WHERE resource=?",
                    (self._lock_resource(report_id),),
                ).fetchone()
                read_con.close()
                if row is None:
                    return None
                if row['locked_at'] is None or row['lock_id'] is None:
                    logger.warning(
                        'get_lock: korrupter Datensatz (NULL in Pflichtfeld) -- bereinige'
                    )
                    try:
                        self._con.execute(
                            'DELETE FROM editor_locks WHERE resource=? '
                            'AND (locked_at IS NULL OR lock_id IS NULL)',
                            (self._lock_resource(report_id),),
                        )
                        self._con.commit()
                    except Exception:
                        pass
                    return None
                return EditorLockRecord(
                    resource=str(row['resource']),
                    locked_by=str(row['locked_by'] or ''),
                    lock_id=str(row['lock_id']),
                    locked_at=int(row['locked_at']),
                    sse_client=str(row['sse_client'] or ''),
                )
            except (sqlite3.OperationalError, sqlite3.ProgrammingError,
                    sqlite3.InterfaceError, TypeError) as exc:
                logger.debug('get_lock (eigene Con) fehlgeschlagen: %s', exc)
                return None

        # Fallback: geteilte Connection (z.B. In-Memory-DB in Tests)
        try:
            row = self._con.execute(
                "SELECT resource, locked_by, lock_id, locked_at, sse_client "
                "FROM editor_locks WHERE resource=?",
                (self._lock_resource(report_id),),
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
                            (self._lock_resource(report_id),),
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

    def validate_lock(
        self, lock_id: str, report_id: Optional[int] = None
    ) -> bool:
        resource = self._lock_resource(report_id)
        try:
            row = self._con.execute(
                "SELECT 1 FROM editor_locks WHERE resource=? AND lock_id=?",
                (resource, lock_id),
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
            # Build 178 (Bug 2.75): Soft-Delete + Versionierung
            deleted_at=(
                int(r["deleted_at"])
                if ("deleted_at" in keys and r["deleted_at"] is not None)
                else None
            ),
            version_nr=(
                int(r["version_nr"])
                if ("version_nr" in keys and r["version_nr"] is not None)
                else 1
            ),
            prev_id=(
                int(r["prev_id"])
                if ("prev_id" in keys and r["prev_id"] is not None)
                else None
            ),
            # Build 182 (Bug 2.78): Forenbenutzer
            actual_uid=(
                int(r["actual_uid"])
                if ("actual_uid" in keys and r["actual_uid"] is not None)
                else None
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
    def _row_to_block(r: sqlite3.Row) -> ReportBlockRecord:
        """Konvertiert eine SQLite-Row in einen ReportBlockRecord.
        Beleg: Bauplan B6 v0.5 §2.3
        """
        return ReportBlockRecord(
            block_id=str(r["block_id"]),
            report_id=int(r["report_id"]),
            author=str(r["author"]),
            created_at=int(r["created_at"]),
            updated_at=int(r["updated_at"]),
            block_type=str(r["block_type"]),
            block_data=str(r["block_data"]),
            placeholder_values_json=(
                str(r["placeholder_values_json"])
                if r["placeholder_values_json"] is not None else None
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

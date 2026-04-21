# =============================================================================
# db/evidence_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Kapselt alle Schreiboperationen in die evidence_<uid>.db (Haupt-DB).
#
# Changelog:
#   Build 012 (Baustelle 4 — §8.2 Bauplan):
#     - Tabellen report_paragraphs, report_anchors, report_suggestions,
#       report_approvals, editor_locks hinzugefügt.
#     - Lock-Mechanismus (dreischichtig) implementiert.
#     - get_annotation_counts_by_category(), get_last_annotation_info(),
#       get_unreferenced_annotation_count(), get_report_status().
#
#   Build 043 (AP-E1 — Editor.js-Integration):
#     - report_paragraphs, report_anchors, report_suggestions ERSETZT durch:
#         reports              — Berichtsmetadata (Typ, Sequenz, Status)
#         report_templates     — Vorlagen-Stub (für spätere Berichtstyp-Vorlagen)
#         report_blocks        — Editor.js-Blöcke (JSON, Owner, Timestamps)
#         report_block_order   — Sortierung via String-based Fractional Indexing
#         block_evidence_user  — Junction Block <-> Annotation (N:M)
#     - report_approvals: Spalte report_id ergänzt.
#     - Neue Dataclasses: ReportRecord, ReportBlockRecord,
#       ReportBlockOrderRecord, BlockEvidenceRecord.
#     - Entfernte Dataclasses: ReportParagraphRecord, ReportAnchorRecord,
#       ReportSuggestionRecord.
#     - Entfernte Methoden: add_paragraph(), _extract_and_save_anchors(),
#       omit_paragraph(), get_paragraphs(), add_suggestion(), resolve_suggestion().
#     - Neue Methoden: create_report(), get_reports(), get_report(),
#       update_report_status(), save_block(), delete_block(),
#       get_blocks_ordered(), get_block(), update_block_order(),
#       get_block_order(), add_block_evidence(), remove_block_evidence(),
#       get_evidence_for_block(), get_blocks_for_evidence().
#     - get_report_status() auf neues Schema umgeschrieben.
#     - get_unreferenced_annotation_count() auf block_evidence_user umgeschrieben.
#     - root-level evidence_db.py entfernt (war versehentliche Kopie).
#     Beleg: AP-E1, Projektgespräch 2026-04-19
#
# Abhängigkeiten: sqlite3, time, json, uuid — ausschließlich Stdlib
# Version: v0.6.043 · Build: 043 · 2026-04-19
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

# Zulässige Annotationskategorien — unveränderliche Menge
VALID_CATEGORIES = frozenset({
    "CAT_PERSON",
    "CAT_LOCATION",
    "CAT_176",
    "CAT_184",
    "CAT_VICTIM",
    "CAT_OTHER",
})

# Zulässige Berichtstypen — unveränderliche Menge
# Beleg: AP-E1, Projektgespräch 2026-04-19
VALID_REPORT_TYPES = frozenset({
    "interim",    # Zwischenbericht
    "final",      # Abschlussbericht (max. einer pro evidence_db)
    "addendum",   # Nachtragsbericht
})

# Zulässige Berichtsstatus
VALID_REPORT_STATUSES = frozenset({
    "draft",
    "submitted",
    "approved",
    "final",
})

# DDL für die evidence_db-Tabellen.
# Beleg: AP-E1, Projektgespräch 2026-04-19
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

-- Berichtsmetadata.
-- Nur ein Bericht vom Typ 'final' zulässig (via Partial-Index reports_one_final_idx).
-- Beleg: AP-E1, Projektgespräch 2026-04-19
CREATE TABLE IF NOT EXISTS reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type     TEXT    NOT NULL
                    CHECK (report_type IN ('interim', 'final', 'addendum')),
    sequence_nr     INTEGER NOT NULL DEFAULT 1,
    title           TEXT    NOT NULL,
    template_id     INTEGER REFERENCES report_templates(id),
    created_by      TEXT    NOT NULL,
    created_at      INTEGER NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'submitted', 'approved', 'final'))
);

-- Vorlagen-Stub. Inhalte werden in spaeteren Baustellen definiert.
-- Beleg: AP-E1, Projektgespräch 2026-04-19
CREATE TABLE IF NOT EXISTS report_templates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    report_type TEXT    NOT NULL
                CHECK (report_type IN ('interim', 'final', 'addendum')),
    blocks_json TEXT    NOT NULL DEFAULT '[]',
    created_at  INTEGER NOT NULL
);

-- Editor.js-Blöcke: normalisiert, ein Block pro Zeile.
-- block_id: vom Editor.js-Client generierte UUID (TEXT).
-- block_type: Editor.js-Blocktyp (paragraph, header, list, table,
--             quote, image, delimiter, evidenceBlock, ...).
-- block_data: JSON-Objekt mit dem Editor.js-Datenfeld des Blocks.
-- owner: SAMAccountName des Erstellers — steuert Bearbeitungsrechte.
-- Beleg: AP-E1, Projektgespräch 2026-04-19
CREATE TABLE IF NOT EXISTS report_blocks (
    block_id    TEXT    PRIMARY KEY,
    report_id   INTEGER NOT NULL REFERENCES reports(id),
    block_type  TEXT    NOT NULL,
    block_data  TEXT    NOT NULL DEFAULT '{}',
    owner       TEXT    NOT NULL,
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL
);

-- Sortierung der Blöcke via String-based Fractional Indexing.
-- sort_index: lexikografisch sortierbar (z.B. "a0", "a0V", "b").
-- Vorteil: Verschieben eines Blocks erfordert nur UPDATE einer Zeile,
--          keine Neuvergabe aller Indizes.
-- Beleg: AP-E1, Projektgespräch 2026-04-19
CREATE TABLE IF NOT EXISTS report_block_order (
    block_id            TEXT    PRIMARY KEY
                        REFERENCES report_blocks(block_id),
    sort_index          TEXT    NOT NULL,
    last_modified_by    TEXT    NOT NULL,
    last_modified_at    INTEGER NOT NULL
);

-- Junction-Tabelle Block <-> Annotation (N:M).
-- Ein Block kann mehrere Annotationen referenzieren (Beweismittelgruppe).
-- Eine Annotation kann in mehreren Blöcken zitiert werden.
-- Referenzielle Integrität: Annotation darf nicht geloescht werden,
-- solange ein block_evidence_user-Eintrag existiert.
-- Beleg: AP-E1, Projektgespräch 2026-04-19
CREATE TABLE IF NOT EXISTS block_evidence_user (
    block_id            TEXT    NOT NULL REFERENCES report_blocks(block_id),
    evidence_id         INTEGER NOT NULL REFERENCES annotations(id),
    investigator_id     INTEGER NOT NULL,
    last_modified_at    INTEGER NOT NULL,
    PRIMARY KEY (block_id, evidence_id)
);

-- Freigabe-Tabelle. report_id ergänzt in Build 043 (AP-E1).
-- Beleg: AP-E1, Projektgespräch 2026-04-19
CREATE TABLE IF NOT EXISTS report_approvals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id   INTEGER NOT NULL REFERENCES reports(id),
    approved_by TEXT    NOT NULL,
    approved_at INTEGER NOT NULL,
    note        TEXT    DEFAULT NULL,
    is_final    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS editor_locks (
    resource    TEXT    NOT NULL PRIMARY KEY,
    locked_by   TEXT    NOT NULL,
    lock_id     TEXT    NOT NULL,
    locked_at   INTEGER NOT NULL,
    sse_client  TEXT    NOT NULL
);

-- Lock-Übernahme-Anfragen (V3: Lock-Übernahme-Dialog)
-- Beleg: Lock-System v2 V3, Projektgespraech 2026-04-21
CREATE TABLE IF NOT EXISTS lock_takeover_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lock_id      TEXT    NOT NULL,
    requested_by TEXT    NOT NULL,
    requested_at INTEGER NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'granted', 'denied', 'expired'))
);

-- Indizes: Seitenbesuche, Viewport, Annotationen
CREATE INDEX IF NOT EXISTS pv_url_idx       ON page_visits (page_url);
CREATE INDEX IF NOT EXISTS ve_url_idx       ON viewport_events (page_url);
CREATE INDEX IF NOT EXISTS ann_url_idx      ON annotations (page_url);
CREATE INDEX IF NOT EXISTS ann_cat_idx      ON annotations (category);

-- Indizes: Berichte
CREATE INDEX IF NOT EXISTS rep_type_idx     ON reports (report_type);
CREATE INDEX IF NOT EXISTS rep_status_idx   ON reports (status);

-- Indizes: Bloecke
CREATE INDEX IF NOT EXISTS rb_report_idx    ON report_blocks (report_id);
CREATE INDEX IF NOT EXISTS rb_owner_idx     ON report_blocks (owner);

-- Indizes: Blockreihenfolge (haeufig sortiert gelesen)
CREATE INDEX IF NOT EXISTS rbo_sort_idx     ON report_block_order (sort_index);

-- Indizes: Junction-Tabelle
CREATE INDEX IF NOT EXISTS beu_block_idx    ON block_evidence_user (block_id);
CREATE INDEX IF NOT EXISTS beu_evidence_idx ON block_evidence_user (evidence_id);

-- Indizes: Freigaben
CREATE INDEX IF NOT EXISTS ra_report_idx    ON report_approvals (report_id);

-- Partial-Index: Stellt sicher, dass es nur einen Abschlussbericht gibt.
-- SQLite unterstuetzt Partial-Indizes mit WHERE-Klausel.
-- Beleg: AP-E1, Projektgespräch 2026-04-19
CREATE UNIQUE INDEX IF NOT EXISTS reports_one_final_idx
    ON reports (report_type)
    WHERE report_type = 'final';
"""

# Spalten, die in aelteren evidence_db-Instanzen fehlen koennen.
_MIGRATION_COLUMNS: list[tuple[str, str, str]] = [
    ("annotations", "selection_json", "TEXT DEFAULT NULL"),
    ("annotations", "tags_json",      "TEXT DEFAULT NULL"),
    ("annotations", "local_id",       "TEXT DEFAULT NULL"),
    ("annotations", "post_id",        "INTEGER DEFAULT NULL"),
    ("annotations", "created_by",     "TEXT NOT NULL DEFAULT ''"),
    # report_approvals.report_id: in Build 012 noch nicht vorhanden.
    # Beleg: AP-E1, Projektgespräch 2026-04-19
    ("report_approvals", "report_id", "INTEGER DEFAULT NULL"),
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
    Beleg: AP-E1, Projektgespräch 2026-04-19
    """
    id:          int
    report_type: str
    sequence_nr: int
    title:       str
    template_id: Optional[int]
    created_by:  str
    created_at:  int
    status:      str


@dataclass
class ReportBlockRecord:
    """Ein Editor.js-Block. block_data ist JSON-String.
    Beleg: AP-E1, Projektgespräch 2026-04-19
    """
    block_id:   str
    report_id:  int
    block_type: str
    block_data: str
    owner:      str
    created_at: int
    updated_at: int


@dataclass
class ReportBlockOrderRecord:
    """Sortierungseintrag (Fractional Indexing).
    Beleg: AP-E1, Projektgespräch 2026-04-19
    """
    block_id:         str
    sort_index:       str
    last_modified_by: str
    last_modified_at: int


@dataclass
class BlockEvidenceRecord:
    """Junction Block <-> Annotation.
    Beleg: AP-E1, Projektgespräch 2026-04-19
    """
    block_id:         str
    evidence_id:      int
    investigator_id:  int
    last_modified_at: int


@dataclass
class ReportApprovalRecord:
    """Freigabeeintrag. report_id ab Build 043 (AP-E1).
    Beleg: AP-E1, Projektgespräch 2026-04-19
    """
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
        # Event-Signal fuer Lock-Aenderungen.
        # SSE-Threads warten darauf — werden sofort geweckt wenn
        # acquire_lock() / release_lock() aufgerufen wird.
        # Beleg: Lock-System v2, Projektgespraech 2026-04-21
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
        """Ergaenzt fehlende Spalten in aelteren evidence_db-Instanzen (idempotent)."""
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
        logger.debug(
            "page_visit protokolliert: '%s' (context=%s)", page_url, scrape_context
        )
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
    ) -> int:
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
        if not events:
            return 0
        rows = []
        for ev in events:
            visible_ms = int(ev.get("visible_ms", 0))
            ts_enter   = int(ev.get("ts_enter", 0))
            ts_leave   = int(ev.get("ts_leave", 0))
            if visible_ms < 0 or ts_leave < ts_enter:
                logger.warning("Ungueltiges Viewport-Event uebersprungen: %s", ev)
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
        if category not in VALID_CATEGORIES:
            raise EvidenceDbError(
                f"Ungueltige Annotationskategorie: '{category}'. "
                f"Zulaessige Werte: {sorted(VALID_CATEGORIES)}"
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
        rows = self._con.execute(
            "SELECT id, page_url, element_id, category, text, ts, investigator_id, "
            "       selection_json, tags_json, local_id, post_id, created_by "
            "FROM annotations WHERE page_url = ? ORDER BY ts ASC",
            (page_url,),
        ).fetchall()
        return [self._row_to_annotation(r) for r in rows]

    def get_all_annotations(self) -> list[AnnotationRecord]:
        rows = self._con.execute(
            "SELECT id, page_url, element_id, category, text, ts, investigator_id, "
            "       selection_json, tags_json, local_id, post_id, created_by "
            "FROM annotations ORDER BY page_url ASC, ts ASC"
        ).fetchall()
        return [self._row_to_annotation(r) for r in rows]

    def annotation_count(self) -> int:
        try:
            row = self._con.execute("SELECT COUNT(*) FROM annotations").fetchone()
            return int(row[0]) if row else 0
        except sqlite3.OperationalError:
            return 0

    def get_annotation_counts_by_category(self) -> dict:
        counts = {cat: 0 for cat in sorted(VALID_CATEGORIES)}
        try:
            rows = self._con.execute(
                "SELECT category, COUNT(*) AS cnt FROM annotations GROUP BY category"
            ).fetchall()
            for r in rows:
                cat = str(r["category"])
                if cat in counts:
                    counts[cat] = int(r["cnt"])
        except sqlite3.OperationalError as exc:
            logger.warning(
                "get_annotation_counts_by_category fehlgeschlagen: %s", exc
            )
        return counts

    def get_last_annotation_info(self) -> Optional[dict]:
        try:
            row = self._con.execute(
                "SELECT ts, created_by FROM annotations ORDER BY ts DESC LIMIT 1"
            ).fetchone()
            if row:
                return {
                    "ts": int(row["ts"]),
                    "investigator": str(row["created_by"]),
                }
        except sqlite3.OperationalError as exc:
            logger.warning("get_last_annotation_info fehlgeschlagen: %s", exc)
        return None

    def get_unreferenced_annotation_count(self) -> int:
        """
        Vollstaendigkeitspruefung: Annotationen ohne Berichtsbezug.
        Menge A (alle annotations) minus Menge B (referenziert in block_evidence_user).
        Beleg: AP-E1, Projektgespraech 2026-04-19
        """
        try:
            row = self._con.execute(
                "SELECT COUNT(*) FROM annotations "
                "WHERE id NOT IN ("
                "  SELECT DISTINCT evidence_id FROM block_evidence_user"
                ")"
            ).fetchone()
            return int(row[0]) if row else 0
        except sqlite3.OperationalError as exc:
            logger.warning(
                "get_unreferenced_annotation_count fehlgeschlagen: %s", exc
            )
            return 0

    # ------------------------------------------------------------------
    # Berichte — Metadata (reports)
    # Beleg: AP-E1, Projektgespraech 2026-04-19
    # ------------------------------------------------------------------

    def create_report(
        self,
        report_type: str,
        title: str,
        created_by: str,
        template_id: Optional[int] = None,
    ) -> int:
        """
        Legt einen neuen Bericht an.

        Args:
            report_type: 'interim', 'final' oder 'addendum'.
            title:       Titel des Berichts.
            created_by:  SAMAccountName des Erstellers.
            template_id: Optionale Vorlage.

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
                "(report_type, sequence_nr, title, template_id, "
                " created_by, created_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, 'draft')",
                (report_type, sequence_nr, title.strip(),
                 template_id, created_by.strip(), now),
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
            "SELECT id, report_type, sequence_nr, title, template_id, "
            "       created_by, created_at, status "
            "FROM reports ORDER BY report_type ASC, sequence_nr ASC"
        ).fetchall()
        return [self._row_to_report(r) for r in rows]

    def get_report(self, report_id: int) -> Optional[ReportRecord]:
        row = self._con.execute(
            "SELECT id, report_type, sequence_nr, title, template_id, "
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
        Beleg: AP-E1, Projektgespraech 2026-04-19
        """
        try:
            block_row = self._con.execute(
                "SELECT rb.updated_at, rb.owner "
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
                "last_editor":  str(block_row["owner"]) if block_row else None,
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
    # Editor.js-Bloecke (report_blocks)
    # Beleg: AP-E1, Projektgespraech 2026-04-19
    # ------------------------------------------------------------------

    def save_block(
        self,
        block_id: str,
        report_id: int,
        block_type: str,
        block_data: dict,
        owner: str,
        sort_index: Optional[str] = None,
    ) -> str:
        """
        Speichert oder aktualisiert einen Editor.js-Block (UPSERT).

        Bei neuem Block: Legt auch Eintrag in report_block_order an
        wenn sort_index angegeben.
        Bei Update: Aktualisiert nur block_data und updated_at.
        Owner und report_id sind unveraenderlich.

        Returns:
            block_id (unveraendert).
        """
        if not block_id.strip():
            raise EvidenceDbError("block_id darf nicht leer sein.")
        if not block_type.strip():
            raise EvidenceDbError("block_type darf nicht leer sein.")
        if not owner.strip():
            raise EvidenceDbError("owner darf nicht leer sein.")

        now = int(time.time())
        data_json = json.dumps(block_data, ensure_ascii=False)

        existing = self._con.execute(
            "SELECT block_id FROM report_blocks WHERE block_id = ?",
            (block_id,),
        ).fetchone()

        if existing:
            self._con.execute(
                "UPDATE report_blocks SET block_data = ?, updated_at = ? "
                "WHERE block_id = ?",
                (data_json, now, block_id),
            )
            logger.debug("Block aktualisiert: block_id=%s", block_id)
        else:
            self._con.execute(
                "INSERT INTO report_blocks "
                "(block_id, report_id, block_type, block_data, owner, "
                " created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (block_id, report_id, block_type, data_json, owner, now, now),
            )
            logger.info(
                "Block angelegt: block_id=%s type=%s owner=%s report_id=%d",
                block_id, block_type, owner, report_id,
            )
            if sort_index is not None:
                self._con.execute(
                    "INSERT INTO report_block_order "
                    "(block_id, sort_index, last_modified_by, last_modified_at) "
                    "VALUES (?, ?, ?, ?)",
                    (block_id, sort_index, owner, now),
                )

        self._con.commit()
        return block_id

    def delete_block(self, block_id: str, requesting_owner: str) -> bool:
        """
        Loescht einen Block und alle zugehoerigen Eintraege.
        Nur der Owner des Blocks darf loeschen.

        Returns:
            True wenn geloescht, False wenn nicht gefunden oder kein Recht.
        """
        row = self._con.execute(
            "SELECT owner FROM report_blocks WHERE block_id = ?",
            (block_id,),
        ).fetchone()

        if row is None:
            return False

        if str(row["owner"]) != requesting_owner:
            logger.warning(
                "delete_block: '%s' versucht Block von '%s' zu loeschen (block_id=%s)",
                requesting_owner, row["owner"], block_id,
            )
            return False

        self._con.execute(
            "DELETE FROM block_evidence_user WHERE block_id = ?", (block_id,)
        )
        self._con.execute(
            "DELETE FROM report_block_order WHERE block_id = ?", (block_id,)
        )
        self._con.execute(
            "DELETE FROM report_blocks WHERE block_id = ?", (block_id,)
        )
        self._con.commit()
        logger.info(
            "Block geloescht: block_id=%s von '%s'", block_id, requesting_owner
        )
        return True

    def get_blocks_ordered(self, report_id: int) -> list[ReportBlockRecord]:
        """
        Gibt alle Bloecke eines Berichts sortiert nach sort_index zurueck.
        Bloecke ohne Sortierungseintrag werden ans Ende gestellt (NULLS LAST).
        Beleg: AP-E1, Projektgespraech 2026-04-19
        """
        rows = self._con.execute(
            "SELECT rb.block_id, rb.report_id, rb.block_type, rb.block_data, "
            "       rb.owner, rb.created_at, rb.updated_at "
            "FROM report_blocks rb "
            "LEFT JOIN report_block_order rbo ON rbo.block_id = rb.block_id "
            "WHERE rb.report_id = ? "
            "ORDER BY rbo.sort_index ASC",
            (report_id,),
        ).fetchall()
        return [self._row_to_block(r) for r in rows]

    def get_block(self, block_id: str) -> Optional[ReportBlockRecord]:
        row = self._con.execute(
            "SELECT block_id, report_id, block_type, block_data, "
            "       owner, created_at, updated_at "
            "FROM report_blocks WHERE block_id = ?",
            (block_id,),
        ).fetchone()
        return self._row_to_block(row) if row else None

    # ------------------------------------------------------------------
    # Blockreihenfolge (report_block_order)
    # Beleg: AP-E1, Projektgespraech 2026-04-19
    # ------------------------------------------------------------------

    def update_block_order(
        self,
        report_id: int,
        ordered_block_ids: list[str],
        new_sort_indices: list[str],
        modified_by: str,
    ) -> int:
        """
        Aktualisiert Sortierungseintraege fuer eine Blockliste (UPSERT).

        Returns:
            Anzahl aktualisierter Eintraege.
        """
        if len(ordered_block_ids) != len(new_sort_indices):
            raise EvidenceDbError(
                f"ordered_block_ids ({len(ordered_block_ids)}) und "
                f"new_sort_indices ({len(new_sort_indices)}) muessen gleich lang sein."
            )
        now = int(time.time())
        count = 0
        for block_id, sort_index in zip(ordered_block_ids, new_sort_indices):
            cursor = self._con.execute(
                "INSERT INTO report_block_order "
                "(block_id, sort_index, last_modified_by, last_modified_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(block_id) DO UPDATE SET "
                "  sort_index = excluded.sort_index, "
                "  last_modified_by = excluded.last_modified_by, "
                "  last_modified_at = excluded.last_modified_at",
                (block_id, sort_index, modified_by, now),
            )
            count += cursor.rowcount
        self._con.commit()
        logger.debug(
            "update_block_order: %d Eintraege fuer report_id=%d", count, report_id
        )
        return count

    def get_block_order(self, report_id: int) -> list[ReportBlockOrderRecord]:
        rows = self._con.execute(
            "SELECT rbo.block_id, rbo.sort_index, "
            "       rbo.last_modified_by, rbo.last_modified_at "
            "FROM report_block_order rbo "
            "JOIN report_blocks rb ON rb.block_id = rbo.block_id "
            "WHERE rb.report_id = ? "
            "ORDER BY rbo.sort_index ASC",
            (report_id,),
        ).fetchall()
        return [
            ReportBlockOrderRecord(
                block_id=str(r["block_id"]),
                sort_index=str(r["sort_index"]),
                last_modified_by=str(r["last_modified_by"]),
                last_modified_at=int(r["last_modified_at"]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Block-Evidence-Junction (block_evidence_user)
    # Beleg: AP-E1, Projektgespraech 2026-04-19
    # ------------------------------------------------------------------

    def add_block_evidence(
        self,
        block_id: str,
        evidence_id: int,
        investigator_id: int,
    ) -> bool:
        """
        Verknuepft eine Annotation mit einem Block (idempotent UPSERT).

        Returns:
            True bei Erfolg.
        """
        now = int(time.time())
        self._con.execute(
            "INSERT INTO block_evidence_user "
            "(block_id, evidence_id, investigator_id, last_modified_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(block_id, evidence_id) DO UPDATE SET "
            "  investigator_id = excluded.investigator_id, "
            "  last_modified_at = excluded.last_modified_at",
            (block_id, evidence_id, investigator_id, now),
        )
        self._con.commit()
        logger.debug(
            "block_evidence verknuepft: block_id=%s evidence_id=%d",
            block_id, evidence_id,
        )
        return True

    def remove_block_evidence(
        self,
        block_id: str,
        evidence_id: int,
    ) -> bool:
        """
        Entfernt die Verknuepfung zwischen Block und Annotation.

        Returns:
            True wenn Eintrag gefunden und geloescht.
        """
        cursor = self._con.execute(
            "DELETE FROM block_evidence_user "
            "WHERE block_id = ? AND evidence_id = ?",
            (block_id, evidence_id),
        )
        self._con.commit()
        return cursor.rowcount > 0

    def get_evidence_for_block(
        self, block_id: str
    ) -> list[BlockEvidenceRecord]:
        rows = self._con.execute(
            "SELECT block_id, evidence_id, investigator_id, last_modified_at "
            "FROM block_evidence_user WHERE block_id = ? "
            "ORDER BY last_modified_at ASC",
            (block_id,),
        ).fetchall()
        return [self._row_to_block_evidence(r) for r in rows]

    def get_blocks_for_evidence(
        self, evidence_id: int
    ) -> list[BlockEvidenceRecord]:
        """
        Alle Block-Verknuepfungen fuer eine Annotation.
        Relevant fuer SSE block_updated-Events.
        Beleg: AP-E1, Projektgespraech 2026-04-19
        """
        rows = self._con.execute(
            "SELECT block_id, evidence_id, investigator_id, last_modified_at "
            "FROM block_evidence_user WHERE evidence_id = ? "
            "ORDER BY last_modified_at ASC",
            (evidence_id,),
        ).fetchall()
        return [self._row_to_block_evidence(r) for r in rows]

    # ------------------------------------------------------------------
    # Freigaben (report_approvals)
    # ------------------------------------------------------------------

    def add_approval(
        self,
        report_id: int,
        approved_by: str,
        is_final: bool = False,
        note: Optional[str] = None,
    ) -> int:
        """
        Speichert einen Freigabeeintrag.
        report_id ist ab Build 043 (AP-E1) Pflichtfeld.
        Beleg: AP-E1, Projektgespraech 2026-04-19
        """
        now = int(time.time())
        cursor = self._con.execute(
            "INSERT INTO report_approvals "
            "(report_id, approved_by, approved_at, note, is_final) "
            "VALUES (?, ?, ?, ?, ?)",
            (report_id, approved_by, now, note, 1 if is_final else 0),
        )
        self._con.commit()
        logger.info(
            "Bericht-Freigabe von '%s' fuer report_id=%d (final=%s)",
            approved_by, report_id, is_final,
        )
        return cursor.lastrowid

    # ------------------------------------------------------------------
    # Editor-Lock (§8.6 Bauplan B4) — unveraendert gegenueber Build 012
    # ------------------------------------------------------------------

    @property
    def lock_change_event(self) -> threading.Event:
        """Event-Signal das bei jeder Lock-Aenderung gesetzt wird."""
        return self._lock_change_event

    # Lock-Timeout: nach dieser Zeit gilt ein Lock als abgelaufen.
    # Schuetzt gegen Deadlock bei Browser-Absturz.
    # Beleg: Lock-System v2, Projektgespraech 2026-04-21
    _LOCK_TIMEOUT_SEC = 90

    def acquire_lock(self, locked_by: str, sse_client: str) -> Optional[str]:
        now = int(time.time())
        new_lock_id = str(uuid.uuid4())
        # Abgelaufene Locks loeschen bevor neuer Lock angelegt wird.
        # Verhindert Deadlock wenn Browser abgestuerzt ist und SSE-Cleanup
        # nicht rechtzeitig lief.
        # Beleg: Lock-System v2, Projektgespraech 2026-04-21
        try:
            self._con.execute(
                "DELETE FROM editor_locks WHERE resource=? AND locked_at < ?",
                (self._LOCK_RESOURCE, now - self._LOCK_TIMEOUT_SEC),
            )
        except sqlite3.OperationalError:
            pass  # Tabellle noch nicht vorhanden — ignorieren
        try:
            self._con.execute(
                "INSERT INTO editor_locks "
                "(resource, locked_by, lock_id, locked_at, sse_client) "
                "VALUES (?, ?, ?, ?, ?)",
                (self._LOCK_RESOURCE, locked_by, new_lock_id, now, sse_client),
            )
            self._con.commit()
            self._lock_change_event.set()  # SSE-Threads sofort aufwecken
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
            self._lock_change_event.set()  # SSE-Threads sofort aufwecken
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
            self._lock_change_event.set()  # SSE-Threads sofort aufwecken
            logger.info(
                "Editor-Lock durch SSE-Abriss freigegeben (sse_client=%s)",
                sse_client,
            )
        return freed

    def resume_lock(self, lock_id: str, locked_by: str, new_sse_client: str) -> bool:
        """
        Bindet einen bestehenden Lock an eine neue SSE-client_id.
        Wird aufgerufen wenn ein Browser nach SSE-Abriss reconnected
        und seinen Lock wiederherstellen moechte.

        Nur erlaubt wenn lock_id UND locked_by uebereinstimmen —
        verhindert dass ein fremder Benutzer einen Lock uebernimmt.

        Returns True wenn der Lock erfolgreich aktualisiert wurde.
        Beleg: Lock-System v2 V1, Projektgespraech 2026-04-21
        """
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
            logger.debug("Lock-Resume: Lock nicht gefunden oder falscher Benutzer")
            return False
        except sqlite3.OperationalError as exc:
            logger.warning("resume_lock fehlgeschlagen: %s", exc)
            return False

    def request_takeover(self, lock_id: str, requested_by: str) -> int:
        """
        Legt eine Lock-Übernahme-Anfrage an.
        Returns die request_id.
        Beleg: Lock-System v2 V3, Projektgespraech 2026-04-21
        """
        now = int(time.time())
        # Bestehende pending-Anfragen dieses Benutzers loeschen
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

    def resolve_takeover(
        self, request_id: int, status: str
    ) -> bool:
        """
        Setzt den Status einer Takeover-Anfrage (granted/denied/expired).
        Beleg: Lock-System v2 V3, Projektgespraech 2026-04-21
        """
        cursor = self._con.execute(
            "UPDATE lock_takeover_requests SET status=? "
            "WHERE id=? AND status='pending'",
            (status, request_id),
        )
        self._con.commit()
        return cursor.rowcount > 0

    def get_pending_takeover(self, lock_id: str) -> Optional[dict]:
        """
        Gibt die aelteste pending Takeover-Anfrage fuer diesen Lock zurueck.
        Beleg: Lock-System v2 V3, Projektgespraech 2026-04-21
        """
        try:
            row = self._con.execute(
                "SELECT id, lock_id, requested_by, requested_at FROM lock_takeover_requests "
                "WHERE lock_id=? AND status='pending' ORDER BY requested_at ASC LIMIT 1",
                (lock_id,),
            ).fetchone()
            if row:
                return {
                    "id": row["id"],
                    "lock_id": row["lock_id"],
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
                # Defensiv gegen NULL-Werte in Pflichtfeldern (alte Datensaetze)
                # Beleg: Bugfix Build 051c, Projektgespraech 2026-04-21
                if row["locked_at"] is None or row["lock_id"] is None:
                    logger.warning(
                        "get_lock: korrupter Datensatz (NULL in Pflichtfeld) — bereinige"
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
            # InterfaceError: 'bad parameter or other API misuse' tritt auf wenn
            # die Verbindung in einem inkonsistenten Zustand ist (z.B. nach commit()
            # in einem anderen Thread). Kein Lock verfuegbar — None zurueckgeben.
            # Beleg: Bugfix Build 050, Projektgespraech 2026-04-21
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
            template_id=(
                int(r["template_id"]) if r["template_id"] is not None else None
            ),
            created_by=str(r["created_by"]),
            created_at=int(r["created_at"]),
            status=str(r["status"]),
        )

    @staticmethod
    def _row_to_block(r: sqlite3.Row) -> ReportBlockRecord:
        return ReportBlockRecord(
            block_id=str(r["block_id"]),
            report_id=int(r["report_id"]),
            block_type=str(r["block_type"]),
            block_data=str(r["block_data"]),
            owner=str(r["owner"]),
            created_at=int(r["created_at"]),
            updated_at=int(r["updated_at"]),
        )

    @staticmethod
    def _row_to_block_evidence(r: sqlite3.Row) -> BlockEvidenceRecord:
        return BlockEvidenceRecord(
            block_id=str(r["block_id"]),
            evidence_id=int(r["evidence_id"]),
            investigator_id=int(r["investigator_id"]),
            last_modified_at=int(r["last_modified_at"]),
        )

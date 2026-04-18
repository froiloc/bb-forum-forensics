# =============================================================================
# db/evidence_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Kapselt alle Schreiboperationen in die evidence_<uid>.db (Haupt-DB).
#
# Änderungen gegenüber Build 011 (Baustelle 4 — §8.2 Bauplan):
#   - Neue Tabellen: report_paragraphs, report_anchors, report_suggestions,
#                    report_approvals, editor_locks (inkl. Indizes).
#   - Neue Dataclasses: ReportParagraphRecord, ReportAnchorRecord,
#                       ReportSuggestionRecord, ReportApprovalRecord,
#                       EditorLockRecord.
#   - Neue Methoden für Berichtsfeld-CRUD und Lock-Verwaltung.
#   - get_annotation_counts_by_category(): Zählt Annotationen je Kategorie.
#   - get_last_annotation_info(): Letzter Annotationszeitpunkt + Autor.
#   - get_unreferenced_annotation_count(): Vollständigkeitsprüfung (§8.4).
#   - get_report_status(): Berichtsstatus für userinfo/data-Endpoint.
#
# Änderungen gegenüber Build 012 (Projektgespräch 2026-04-18):
#   - get_lock(): Fängt zusätzlich sqlite3.ProgrammingError ab.
#     Tritt auf wenn der SSE-Thread get_lock() aufruft während die
#     DB-Verbindung bereits geschlossen ist (Race Condition bei
#     Serverbeendigung). Verhindert WARNING in forensic_api/events.py.
#     Beleg: Projektgespräch 2026-04-18
#
# Abhängigkeiten: sqlite3, time, json, uuid — ausschließlich Stdlib
# Version: v0.1.0 · Build: 029 · 2026-04-18
# =============================================================================

from __future__ import annotations

import json
import re
import sqlite3
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

CREATE TABLE IF NOT EXISTS report_paragraphs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    author          TEXT    NOT NULL,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,
    content         TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'omitted', 'superseded')),
    omitted_by      TEXT    DEFAULT NULL,
    omitted_at      INTEGER DEFAULT NULL,
    omitted_reason  TEXT    DEFAULT NULL,
    sort_order      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS report_anchors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paragraph_id    INTEGER NOT NULL REFERENCES report_paragraphs(id),
    annotation_id   INTEGER NOT NULL,
    anchor_text     TEXT    NOT NULL,
    created_at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS report_suggestions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    paragraph_id      INTEGER NOT NULL REFERENCES report_paragraphs(id),
    author            TEXT    NOT NULL,
    created_at        INTEGER NOT NULL,
    suggested_content TEXT    NOT NULL,
    status            TEXT    NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'accepted', 'rejected')),
    resolved_by       TEXT    DEFAULT NULL,
    resolved_at       INTEGER DEFAULT NULL,
    resolution_note   TEXT    DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS report_approvals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE INDEX IF NOT EXISTS pv_url_idx       ON page_visits (page_url);
CREATE INDEX IF NOT EXISTS ve_url_idx       ON viewport_events (page_url);
CREATE INDEX IF NOT EXISTS ann_url_idx      ON annotations (page_url);
CREATE INDEX IF NOT EXISTS ann_cat_idx      ON annotations (category);
CREATE INDEX IF NOT EXISTS rp_author_idx    ON report_paragraphs (author);
CREATE INDEX IF NOT EXISTS rp_sort_idx      ON report_paragraphs (sort_order);
CREATE INDEX IF NOT EXISTS ra_para_idx      ON report_anchors (paragraph_id);
CREATE INDEX IF NOT EXISTS ra_ann_idx       ON report_anchors (annotation_id);
CREATE INDEX IF NOT EXISTS rs_para_idx      ON report_suggestions (paragraph_id);
"""

# Spalten, die in älteren evidence_db-Instanzen (Build <= 010) fehlen können.
_MIGRATION_COLUMNS: list[tuple[str, str, str]] = [
    ("annotations", "selection_json", "TEXT DEFAULT NULL"),
    ("annotations", "tags_json",      "TEXT DEFAULT NULL"),
    ("annotations", "local_id",       "TEXT DEFAULT NULL"),
    ("annotations", "post_id",        "INTEGER DEFAULT NULL"),
    ("annotations", "created_by",     "TEXT NOT NULL DEFAULT ''"),
]

# Regex für Beweisanker-Syntax [BELEG:annotation_id=N]
_ANCHOR_PATTERN = re.compile(r'\[BELEG:annotation_id=(\d+)\]')


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


@dataclass
class ReportParagraphRecord:
    """Repräsentiert einen Paragraph im kollaborativen Berichtsfeld (§8.2 Bauplan B4)."""
    id:             int
    author:         str
    created_at:     int
    updated_at:     int
    content:        str
    status:         str
    sort_order:     int
    omitted_by:     Optional[str]
    omitted_at:     Optional[int]
    omitted_reason: Optional[str]


@dataclass
class ReportAnchorRecord:
    """Verknüpft einen Paragraph mit einer Annotation (§8.3 Bauplan B4)."""
    id:            int
    paragraph_id:  int
    annotation_id: int
    anchor_text:   str
    created_at:    int


@dataclass
class ReportSuggestionRecord:
    """Änderungsvorschlag zu einem fremden Paragraph (§8.5 Bauplan B4)."""
    id:                int
    paragraph_id:      int
    author:            str
    created_at:        int
    suggested_content: str
    status:            str
    resolved_by:       Optional[str]
    resolved_at:       Optional[int]
    resolution_note:   Optional[str]


@dataclass
class ReportApprovalRecord:
    """Freigabeeintrag für den Bericht (§8.5 Bauplan B4)."""
    id:          int
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


class EvidenceDbError(Exception):
    """Wird geworfen bei ungültigen Eingaben (z.B. unbekannte Kategorie)."""


class EvidenceDb:
    """Kapselt alle Schreib- und Lesezugriffe auf die evidence_db."""

    # Ressourcenname für den Editor-Lock — unveränderlich
    _LOCK_RESOURCE = "report_editor"

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

    def get_annotation_counts_by_category(self) -> dict:
        """
        Zählt Annotationen je Kategorie.
        Rückgabe: Dict {kategorie: anzahl}. Alle VALID_CATEGORIES immer enthalten.
        Verwendet für /_forensic/userinfo/data (§5.2 Bauplan B4).
        """
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
            logger.warning("get_annotation_counts_by_category fehlgeschlagen: %s", exc)
        return counts

    def get_last_annotation_info(self) -> Optional[dict]:
        """
        Gibt Timestamp und Autor der zuletzt gespeicherten Annotation zurück.
        Rückgabe: {"ts": int, "investigator": str} oder None.
        Verwendet für /_forensic/userinfo/data (§5.2 Bauplan B4).
        """
        try:
            row = self._con.execute(
                "SELECT ts, created_by FROM annotations ORDER BY ts DESC LIMIT 1"
            ).fetchone()
            if row:
                return {"ts": int(row["ts"]), "investigator": str(row["created_by"])}
        except sqlite3.OperationalError as exc:
            logger.warning("get_last_annotation_info fehlgeschlagen: %s", exc)
        return None

    def get_unreferenced_annotation_count(self) -> int:
        """
        Vollständigkeitsprüfung (§8.4 Bauplan B4):
        Anzahl Annotationen ohne Berichtsbezug.
        Menge A (alle annotations) minus Menge B (referenziert in report_anchors).
        """
        try:
            row = self._con.execute(
                "SELECT COUNT(*) FROM annotations "
                "WHERE id NOT IN (SELECT DISTINCT annotation_id FROM report_anchors)"
            ).fetchone()
            return int(row[0]) if row else 0
        except sqlite3.OperationalError as exc:
            logger.warning("get_unreferenced_annotation_count fehlgeschlagen: %s", exc)
            return 0

    # ------------------------------------------------------------------
    # Berichtsfeld — Paragraphen (§8 Bauplan B4)
    # ------------------------------------------------------------------

    def add_paragraph(
        self,
        author: str,
        content: str,
        sort_after: Optional[int] = None,
    ) -> int:
        """
        Fügt einen neuen Paragraph ein.

        Args:
            author:     SAMAccountName des Erstellers.
            content:    Fließtext (kann [BELEG:annotation_id=N]-Anker enthalten).
            sort_after: sort_order-Wert des Vorgängers. None = ans Ende anfügen.

        Returns:
            id des neuen Paragraphen.
        """
        now = int(time.time())

        if sort_after is None:
            # Am Ende anfügen: max(sort_order) + 1
            row = self._con.execute(
                "SELECT COALESCE(MAX(sort_order), 0) FROM report_paragraphs"
            ).fetchone()
            new_order = int(row[0]) + 1
        else:
            # Hinter sort_after einschieben: alle mit sort_order > sort_after um 1 verschieben
            self._con.execute(
                "UPDATE report_paragraphs SET sort_order = sort_order + 1 "
                "WHERE sort_order > ?",
                (sort_after,),
            )
            new_order = sort_after + 1

        cursor = self._con.execute(
            "INSERT INTO report_paragraphs "
            "(author, created_at, updated_at, content, status, sort_order) "
            "VALUES (?, ?, ?, ?, 'active', ?)",
            (author, now, now, content, new_order),
        )
        para_id = cursor.lastrowid
        self._con.commit()
        logger.info("Paragraph %d angelegt von '%s'", para_id, author)

        # Anker aus [BELEG:annotation_id=N]-Syntax extrahieren und speichern
        self._extract_and_save_anchors(para_id, content, now)
        return para_id

    def _extract_and_save_anchors(
        self, paragraph_id: int, content: str, now: int
    ) -> None:
        """
        Extrahiert [BELEG:annotation_id=N]-Referenzen aus dem Fließtext
        und schreibt sie in report_anchors (§8.3 Bauplan B4).
        Idempotent: Löscht zunächst alle bestehenden Anker des Paragraphen.
        """
        # Bestehende Anker dieses Paragraphen löschen (bei Updates)
        self._con.execute(
            "DELETE FROM report_anchors WHERE paragraph_id = ?",
            (paragraph_id,),
        )
        for match in _ANCHOR_PATTERN.finditer(content):
            ann_id = int(match.group(1))
            self._con.execute(
                "INSERT INTO report_anchors "
                "(paragraph_id, annotation_id, anchor_text, created_at) "
                "VALUES (?, ?, ?, ?)",
                (paragraph_id, ann_id, f"Annotation #{ann_id}", now),
            )
        self._con.commit()

    def omit_paragraph(
        self,
        paragraph_id: int,
        omitted_by: str,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Markiert einen Paragraph als 'omitted' (nur Chef-Ermittlerin, §8.1 Bauplan B4).
        Gibt True zurück wenn Paragraph gefunden und geändert.
        """
        now = int(time.time())
        cursor = self._con.execute(
            "UPDATE report_paragraphs SET status='omitted', omitted_by=?, "
            "omitted_at=?, omitted_reason=?, updated_at=? WHERE id=?",
            (omitted_by, now, reason, now, paragraph_id),
        )
        self._con.commit()
        return cursor.rowcount > 0

    def get_paragraphs(self, include_omitted: bool = False) -> list[ReportParagraphRecord]:
        """
        Gibt alle Paragraphen sortiert nach sort_order zurück.
        include_omitted=False filtert status='omitted' heraus.
        """
        if include_omitted:
            rows = self._con.execute(
                "SELECT id, author, created_at, updated_at, content, status, "
                "sort_order, omitted_by, omitted_at, omitted_reason "
                "FROM report_paragraphs ORDER BY sort_order ASC"
            ).fetchall()
        else:
            rows = self._con.execute(
                "SELECT id, author, created_at, updated_at, content, status, "
                "sort_order, omitted_by, omitted_at, omitted_reason "
                "FROM report_paragraphs WHERE status != 'omitted' "
                "ORDER BY sort_order ASC"
            ).fetchall()
        return [self._row_to_para(r) for r in rows]

    def get_report_status(self) -> dict:
        """
        Liefert den Berichtsstatus für /_forensic/userinfo/data (§5.2 Bauplan B4).
        Rückgabe-Schema: has_draft, last_edit_ts, last_editor, approved, approved_by.
        """
        try:
            para_row = self._con.execute(
                "SELECT updated_at, author FROM report_paragraphs "
                "ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            appr_row = self._con.execute(
                "SELECT approved_by FROM report_approvals "
                "ORDER BY approved_at DESC LIMIT 1"
            ).fetchone()
            return {
                "has_draft":    para_row is not None,
                "last_edit_ts": int(para_row["updated_at"]) if para_row else None,
                "last_editor":  str(para_row["author"]) if para_row else None,
                "approved":     appr_row is not None,
                "approved_by":  str(appr_row["approved_by"]) if appr_row else None,
            }
        except sqlite3.OperationalError as exc:
            logger.warning("get_report_status fehlgeschlagen: %s", exc)
            return {
                "has_draft": False, "last_edit_ts": None, "last_editor": None,
                "approved": False, "approved_by": None,
            }

    # ------------------------------------------------------------------
    # Berichtsfeld — Änderungsvorschläge
    # ------------------------------------------------------------------

    def add_suggestion(
        self,
        paragraph_id: int,
        author: str,
        suggested_content: str,
    ) -> int:
        """Speichert einen Änderungsvorschlag (§8.5 Bauplan B4)."""
        now = int(time.time())
        cursor = self._con.execute(
            "INSERT INTO report_suggestions "
            "(paragraph_id, author, created_at, suggested_content, status) "
            "VALUES (?, ?, ?, ?, 'pending')",
            (paragraph_id, author, now, suggested_content),
        )
        self._con.commit()
        return cursor.lastrowid

    def resolve_suggestion(
        self,
        suggestion_id: int,
        resolved_by: str,
        accept: bool,
        note: Optional[str] = None,
    ) -> bool:
        """
        Löst einen Änderungsvorschlag auf (accept=True: übernehmen).
        Bei Übernahme wird der Paragraph-Inhalt ersetzt und als 'superseded' markiert.
        Gibt True zurück wenn Vorschlag gefunden und aufgelöst.
        """
        now = int(time.time())
        status = "accepted" if accept else "rejected"
        cursor = self._con.execute(
            "UPDATE report_suggestions SET status=?, resolved_by=?, "
            "resolved_at=?, resolution_note=? WHERE id=? AND status='pending'",
            (status, resolved_by, now, note, suggestion_id),
        )
        self._con.commit()
        if cursor.rowcount == 0:
            return False

        if accept:
            # Akzeptiert: Inhalt des zugehörigen Paragraphen ersetzen
            row = self._con.execute(
                "SELECT paragraph_id, suggested_content FROM report_suggestions WHERE id=?",
                (suggestion_id,),
            ).fetchone()
            if row:
                new_content = str(row["suggested_content"])
                para_id = int(row["paragraph_id"])
                self._con.execute(
                    "UPDATE report_paragraphs SET content=?, updated_at=?, "
                    "status='superseded' WHERE id=?",
                    (new_content, now, para_id),
                )
                self._con.commit()
                self._extract_and_save_anchors(para_id, new_content, now)
        return True

    # ------------------------------------------------------------------
    # Berichtsfeld — Freigabe
    # ------------------------------------------------------------------

    def add_approval(
        self,
        approved_by: str,
        is_final: bool = False,
        note: Optional[str] = None,
    ) -> int:
        """Speichert einen Freigabeeintrag (§8.5 Bauplan B4)."""
        now = int(time.time())
        cursor = self._con.execute(
            "INSERT INTO report_approvals (approved_by, approved_at, note, is_final) "
            "VALUES (?, ?, ?, ?)",
            (approved_by, now, note, 1 if is_final else 0),
        )
        self._con.commit()
        logger.info("Bericht-Freigabe von '%s' (final=%s)", approved_by, is_final)
        return cursor.lastrowid

    # ------------------------------------------------------------------
    # Berichtsfeld — Editor-Lock (§8.6 Bauplan B4)
    # ------------------------------------------------------------------

    def acquire_lock(self, locked_by: str, sse_client: str) -> Optional[str]:
        """
        Versucht den Editor-Lock zu erwerben.

        Gibt die lock_id (UUID-String) zurück bei Erfolg.
        Gibt None zurück wenn der Lock bereits von jemand anderem gehalten wird.

        Dreischichtiger Lock-Mechanismus: Diese Methode implementiert Schicht 3
        (Server-Lock in editor_locks — schützt vor Race Conditions zwischen
        verschiedenen Ermittler-Rechnern, §8.6 Bauplan B4).
        """
        now = int(time.time())
        new_lock_id = str(uuid.uuid4())

        try:
            # Versuche INSERT. Bei UNIQUE-Conflict: Lock belegt.
            self._con.execute(
                "INSERT INTO editor_locks (resource, locked_by, lock_id, locked_at, sse_client) "
                "VALUES (?, ?, ?, ?, ?)",
                (self._LOCK_RESOURCE, locked_by, new_lock_id, now, sse_client),
            )
            self._con.commit()
            logger.info("Editor-Lock erworben: '%s' (lock_id=%s)", locked_by, new_lock_id)
            return new_lock_id
        except sqlite3.IntegrityError:
            logger.debug("acquire_lock: Lock bereits belegt für '%s'", self._LOCK_RESOURCE)
            return None

    def release_lock(self, lock_id: str) -> bool:
        """
        Gibt den Lock frei. Gibt True zurück wenn Lock gefunden und gelöscht.
        Aufgerufen durch: beforeunload-Event (§8.6 Bauplan B4).
        """
        cursor = self._con.execute(
            "DELETE FROM editor_locks WHERE resource=? AND lock_id=?",
            (self._LOCK_RESOURCE, lock_id),
        )
        self._con.commit()
        freed = cursor.rowcount > 0
        if freed:
            logger.info("Editor-Lock freigegeben (lock_id=%s)", lock_id)
        return freed

    def release_lock_by_sse_client(self, sse_client: str) -> bool:
        """
        Gibt den Lock anhand der SSE-Client-ID frei (Schicht 2 — §8.6 Bauplan B4).
        Wird aufgerufen wenn die SSE-Verbindung des Lock-Inhabers abreißt.
        Der Server erkennt SSE-Verbindungsabriss → gibt Lock sofort frei.
        """
        cursor = self._con.execute(
            "DELETE FROM editor_locks WHERE resource=? AND sse_client=?",
            (self._LOCK_RESOURCE, sse_client),
        )
        self._con.commit()
        freed = cursor.rowcount > 0
        if freed:
            logger.info("Editor-Lock durch SSE-Abriss freigegeben (sse_client=%s)", sse_client)
        return freed

    def get_lock(self) -> Optional[EditorLockRecord]:
        """Gibt den aktuellen Lock zurück oder None wenn kein Lock aktiv."""
        try:
            row = self._con.execute(
                "SELECT resource, locked_by, lock_id, locked_at, sse_client "
                "FROM editor_locks WHERE resource=?",
                (self._LOCK_RESOURCE,),
            ).fetchone()
            if row:
                return EditorLockRecord(
                    resource=str(row["resource"]),
                    locked_by=str(row["locked_by"]),
                    lock_id=str(row["lock_id"]),
                    locked_at=int(row["locked_at"]),
                    sse_client=str(row["sse_client"]),
                )
        except (sqlite3.OperationalError, sqlite3.ProgrammingError) as exc:
            # ProgrammingError: Verbindung bereits geschlossen (Race Condition
            # SSE-Thread vs. Serverbeendigung). Kein harter Fehler.
            # Beleg: Projektgespräch 2026-04-18
            logger.debug("get_lock: Verbindung nicht verfügbar: %s", exc)
        return None

    def validate_lock(self, lock_id: str) -> bool:
        """
        Prüft ob der angegebene lock_id-Wert den aktiven Lock hält.
        Schicht 3 des dreischichtigen Lock-Mechanismus (§8.6 Bauplan B4).
        Aufgerufen vor jedem schreibenden POST auf /_forensic/report.
        """
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

    @staticmethod
    def _row_to_para(r: sqlite3.Row) -> ReportParagraphRecord:
        """Wandelt eine sqlite3.Row in ein ReportParagraphRecord um."""
        return ReportParagraphRecord(
            id=int(r["id"]),
            author=str(r["author"]),
            created_at=int(r["created_at"]),
            updated_at=int(r["updated_at"]),
            content=str(r["content"]),
            status=str(r["status"]),
            sort_order=int(r["sort_order"]),
            omitted_by=str(r["omitted_by"]) if r["omitted_by"] else None,
            omitted_at=int(r["omitted_at"]) if r["omitted_at"] else None,
            omitted_reason=str(r["omitted_reason"]) if r["omitted_reason"] else None,
        )

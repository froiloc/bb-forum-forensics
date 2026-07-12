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
#   Build 281 (Bug 2.23, 2026-06-07):
#     - clear_stale_locks_on_startup(): Loescht alle Eintraege aus
#       editor_locks, lock_queue und lock_takeover_requests beim Serverstart.
#       Nach einem Neustart sind alle Locks veraltet (SSE-Verbindungen
#       abgebrochen, Grace-Period-Timer nicht uebertragen). Ohne Bereinigung
#       blockieren Stale Locks alle acquire()-Versuche mit HTTP 423.
#     Beleg: Bugfix-Liste 2.23, Projektgespraech 2026-06-07
#
#   Build 098: get_lock() nutzt eigene kurzlebige Connection wenn db_path gesetzt.
#     Verhindert 'bad parameter or other API misuse' im SSE-Thread.
#     EvidenceDb.__init__() bekommt optionalen db_path-Parameter.
#     Beleg: Build 098, Thread-Safety-Fix, Projektgespraech 2026-05-06
#
#   Build 249 (BS6 Paket 6 — report_opened-Tabelle):
#     - _SCHEMA_DDL: Tabelle report_opened + 2 Indizes ergänzt.
#       Audit-Trail welcher Client welchen Bericht geöffnet hat.
#     - log_report_opened(): Öffnen-Eintrag schreiben + Queue-Bereinigung
#       für andere Berichte desselben Clients.
#     - get_open_report_for_client(): aktuell geöffneter Bericht pro Client.
#     Beleg: Layer 3 States OPENING, Paket-6-Ergänzung 2026-05-24
#
#   Build 264 (Bug 2.123, 2026-05-30):
#     - _row_to_annotation(): investigator_id wird nun als str gelesen statt int.
#       SQLite erzwingt den INTEGER-Typ nicht — ein Textkuerzel wie 'nw082317'
#       wuerde int() zum Absturz bringen (ValueError) und den /annotations-
#       Endpunkt mit HTTP 500 beenden. AnnotationRecord.investigator_id
#       von Optional[int] auf Optional[str] geaendert.
#       Beleg: Serverlog 2026-05-30 — 'invalid literal for int() with base 10: nw082317'
#   Build 263 (Bug 2.122, 2026-05-30):
#     - _SCHEMA_DDL: Alle DROP TABLE IF EXISTS und DROP INDEX IF EXISTS
#       entfernt. Diese wurden bei jedem Start ausgefuehrt und vernichteten
#       alle Daten einer bestehenden evidence_db unwiederbringlich.
#       Alle CREATE TABLE/INDEX-Statements auf IF NOT EXISTS geprueft.
#       Beleg: Datenverlust evidence_2948078.db, Projektgespraech 2026-05-30.
#
#     - resume_lock(): Signatur geaendert von (report_id, lock_id, locked_by, new_sse)
#       auf (old_sse_client, new_sse_client). RESUMING ist eine Layer-2-Aktion;
#       lock_id ist Layer-4-Daten und darf Layer 2 nicht bekannt sein.
#       Beleg: Layer 2 States, Architekturentscheidung Paket-4-Review 2026-05-24
#
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
#     - # Schema v2.0: alle Spalten direkt im _SCHEMA_DDL.
# Keine Legacy-Migrationen mehr noetig.
# Beleg: Architektur-Revision 2026-05-18
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Erlaubte Annotationskategorien (forensische Grundkategorien).
# Beleg: Bauplan B4, Projektgespraech 2026-04-19
VALID_CATEGORIES: frozenset[str] = frozenset({
    "CAT_PERSON",
    "CAT_LOCATION",
    "CAT_176",
    "CAT_184",
    "CAT_VICTIM",
    "CAT_OTHER",
})

# Erlaubte Berichtstypen.
# Beleg: reports.status CHECK-Constraint, Projektgespraech 2026-04-19
VALID_REPORT_TYPES: frozenset[str] = frozenset({
    "interim",
    "final",
    "addendum",
})

# =============================================================================
# BERICHTS-STATUSMODELL (verbindlich festgelegt am 2026-07-10, mc)
# =============================================================================
# Suchbegriff: BERICHTS-STATUSMODELL
# Ausfuehrliche Fassung: documents/Berichts_Statusmodell.md
#
# Bis Build 379 waren die vier Werte NICHT definiert (nur die Konstante, ohne
# Beleg, ohne erzwungene Uebergaenge). Faktisch wurde ausser 'draft' nie ein
# Status gesetzt. Deshalb konnte das Modell frei und sauber festgelegt werden:
#
#   draft      Autor arbeitet am Bericht.
#              -> Autor darf ALLES aendern.
#
#   submitted  Autor hat den Bericht ZUR ABNAHME EINGEREICHT.
#              -> Der Bericht ist damit FUER DEN AUTOR GESPERRT.
#              -> Zurueck zu 'draft' (Nachbesserung) nur durch Lektor
#                 (reports.review) oder Chef-Ermittlerin (reports.approve).
#
#   approved   Chef-Ermittlerin hat ABGENOMMEN und VERSIEGELT (Build 377:
#              zentrales Abbild + Inhaltshash in approved_reports.db).
#              -> UNWIDERRUFLICH. Keine Rueckstufung.
#
#   final      Der abgenommene Bericht ist AN DIE STA VERSANDT / ABGESCHLOSSEN.
#              -> Endzustand. Gesetzt von der Chef-Ermittlerin.
#
# ACHTUNG, HAEUFIGE VERWECHSLUNG: 'final' existiert ZWEIMAL im Schema —
#   als STATUS (hier: versandt/abgeschlossen) UND als report_type
#   ('interim' | 'final' | 'addendum' = Abschlussbericht). Ein Abschlussbericht
#   im Entwurf ist report_type='final' MIT status='draft'.
#
# DURCHSETZUNG (Build 379): Ab 'submitted' ist der Berichtsinhalt fuer den
#   Autor gesperrt (save_block/update_block/delete_block/set_block_order/
#   add_anchor/remove_anchor -> ReportSealedError). KOMMENTARE bleiben erlaubt
#   (mc): sie stecken nicht im Siegel-Hash und helfen, die Notwendigkeit eines
#   Nachtragsberichts zu dokumentieren.
# =============================================================================

VALID_REPORT_STATUSES: frozenset[str] = frozenset({
    "draft", "submitted", "approved", "final",
})

#: Status, in denen der AUTOR den Berichtsinhalt noch aendern darf.
EDITABLE_REPORT_STATUSES: frozenset[str] = frozenset({"draft"})

#: Status, in denen der Berichtsinhalt gesperrt ist (Build 379).
LOCKED_REPORT_STATUSES: frozenset[str] = frozenset({
    "submitted", "approved", "final",
})

VALID_COMMENT_STATUSES: frozenset[str] = frozenset({
    "pending", "addressed", "dismissed", "revoked",
})

# Migrationsspalten fuer aeltere evidence_db-Instanzen.
# Auch wenn _SCHEMA_DDL alle Spalten via CREATE TABLE IF NOT EXISTS enthaelt,
# greift das nur fuer neue DBs. Aeltere DBs haben die Tabelle bereits ohne
# diese Spalten — ALTER TABLE ist die einzige Moeglichkeit sie nachzurüsten.
# ALTER TABLE mit bereits vorhandener Spalte wird via 'duplicate column'-
# Exception abgefangen und ignoriert (idempotent).
# Beleg: Regression T24, Projektgespraeche 2026-05-31.
_MIGRATION_COLUMNS: list[tuple[str, str, str]] = [
    # Build 089+: selection_json fuer Textmarkierungen (CSS Highlights API)
    ("annotations", "selection_json", "TEXT DEFAULT NULL"),
    # Build 132+: Tags-JSON fuer Schlagworte
    ("annotations", "tags_json",      "TEXT DEFAULT NULL"),
    # Build 145+: local_id fuer client-seitige Zuordnung
    ("annotations", "local_id",       "TEXT DEFAULT NULL"),
    # Build 158+: post_id fuer Beitrags-Referenz
    ("annotations", "post_id",        "INTEGER DEFAULT NULL"),
    # Build 163+: created_by fuer Ermittler-Kuerzel
    ("annotations", "created_by",     "TEXT NOT NULL DEFAULT ''"),
    # Build 178+: Soft-Delete und Versionierung
    ("annotations", "deleted_at",     "INTEGER DEFAULT NULL"),
    ("annotations", "version_nr",     "INTEGER NOT NULL DEFAULT 1"),
    ("annotations", "prev_id",        "INTEGER DEFAULT NULL"),
    # Build 239+: actual_uid fuer user_id-Zuordnung
    ("annotations", "actual_uid",     "INTEGER DEFAULT NULL"),
    # Build 284+: cooldown_until fuer Lock-Cooldown (SLA Punkt 8)
    # Aeltere DBs haben diese Spalte nicht — ALTER TABLE ergaenzt sie.
    ("editor_locks", "cooldown_until", "INTEGER DEFAULT NULL"),
]

# =============================================================================
# SYNCHRON HALTEN MIT: stage2/evidence_db_init.py (_FULL_SCHEMA_DDL)
# Letzte Synchronisation: Build 239 (Schema v2.0), 2026-05-18
# =============================================================================
# =============================================================================
# SYNCHRON HALTEN MIT: stage2/evidence_db_init.py (_FULL_SCHEMA_DDL)
# Letzte Synchronisation: Build 239 (Schema v2.0), 2026-05-18
#
# WICHTIG — Bug 2.122 (Build 263, 2026-05-30):
#   Alle DROP TABLE/INDEX IF EXISTS-Statements entfernt.
#   Begruendung: _setup_schema() wird bei JEDEM Start aufgerufen. DROP TABLE
#   vernichtet alle Daten einer bestehenden DB unwiederbringlich. Die
#   CREATE TABLE IF NOT EXISTS-Statements sind idempotent — kein DROP noetig.
#   Beleg: Datenverlust evidence_2948078.db, 2026-05-30, Projektgespraech.
# =============================================================================
_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS "scraper_log" (
	"id"	INTEGER,
	"event"	TEXT NOT NULL,
	"user_id"	INTEGER NOT NULL,
	"detail"	TEXT,
	"ts"	INTEGER NOT NULL,
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "page_visits" (
	"id"	INTEGER,
	"page_url"	TEXT NOT NULL,
	"scrape_context"	TEXT NOT NULL,
	"ts"	INTEGER NOT NULL,
	"investigator_id"	INTEGER,
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "viewport_events" (
	"id"	INTEGER,
	"page_url"	TEXT NOT NULL,
	"element_id"	TEXT,
	"visible_ms"	INTEGER NOT NULL,
	"ts_enter"	INTEGER NOT NULL,
	"ts_leave"	INTEGER NOT NULL,
	"investigator_id"	INTEGER,
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "annotations" (
	"id"	INTEGER,
	"page_url"	TEXT NOT NULL,
	"element_id"	TEXT,
	"category"	TEXT NOT NULL,
	"text"	TEXT NOT NULL DEFAULT '',
	"ts"	INTEGER NOT NULL,
	"investigator_id"	INTEGER,
	"selection_json"	TEXT DEFAULT NULL,
	"tags_json"	TEXT DEFAULT NULL,
	"local_id"	TEXT DEFAULT NULL,
	"post_id"	INTEGER DEFAULT NULL,
	"created_by"	TEXT NOT NULL DEFAULT '',
	"deleted_at"	INTEGER DEFAULT NULL,
	"version_nr"	INTEGER NOT NULL DEFAULT 1,
	"prev_id"	INTEGER DEFAULT NULL,
	"actual_uid"	INTEGER DEFAULT NULL,
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "reports" (
	"id"	INTEGER,
	"report_type"	TEXT NOT NULL CHECK("report_type" IN ('interim', 'final', 'addendum')),
	"sequence_nr"	INTEGER NOT NULL DEFAULT 1,
	"title"	TEXT NOT NULL,
	"created_by"	TEXT NOT NULL,
	"created_at"	INTEGER NOT NULL,
	"status"	TEXT NOT NULL DEFAULT 'draft' CHECK("status" IN ('draft', 'submitted', 'approved', 'final')),
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "report_blocks" (
	"block_id"	TEXT NOT NULL,
	"report_id"	INTEGER NOT NULL,
	"author"	TEXT NOT NULL,
	"created_at"	INTEGER NOT NULL,
	"updated_at"	INTEGER NOT NULL,
	"block_type"	TEXT NOT NULL,
	"block_data"	TEXT NOT NULL DEFAULT '{}',
	"placeholder_values_json"	TEXT,
	"module_id"	INTEGER,
	FOREIGN KEY("report_id") REFERENCES "reports"("id"),
	PRIMARY KEY("block_id")
);
CREATE TABLE IF NOT EXISTS "report_block_order" (
	"block_id"	TEXT NOT NULL,
	"sort_index"	INTEGER NOT NULL,
	"last_modified_by"	TEXT NOT NULL,
	"last_modified_at"	INTEGER NOT NULL,
	FOREIGN KEY("block_id") REFERENCES "report_blocks"("block_id"),
	PRIMARY KEY("block_id")
);
CREATE TABLE IF NOT EXISTS "report_anchors" (
	"id"	INTEGER,
	"block_id"	TEXT NOT NULL,
	"annotation_id"	INTEGER NOT NULL,
	"anchor_text"	TEXT NOT NULL,
	"created_at"	INTEGER NOT NULL,
	PRIMARY KEY("id" AUTOINCREMENT),
	FOREIGN KEY("annotation_id") REFERENCES "annotations"("id"),
	FOREIGN KEY("block_id") REFERENCES "report_blocks"("block_id")
);
CREATE TABLE IF NOT EXISTS "report_comments" (
	"id"	INTEGER,
	"block_id"	TEXT NOT NULL,
	"author"	TEXT NOT NULL,
	"created_at"	INTEGER NOT NULL,
	"comment_text"	TEXT NOT NULL,
	"suggested_content"	TEXT,
	"status"	TEXT NOT NULL DEFAULT 'pending' CHECK("status" IN ('pending', 'addressed', 'dismissed', 'revoked')),
	"resolved_by"	TEXT,
	"resolved_at"	INTEGER,
	FOREIGN KEY("block_id") REFERENCES "report_blocks"("block_id"),
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "placeholder_cache" (
	"query_id"	TEXT NOT NULL,
	"uid"	INTEGER NOT NULL,
	"cached_value"	TEXT NOT NULL,
	"cached_at"	INTEGER NOT NULL,
	PRIMARY KEY("query_id","uid")
);
CREATE TABLE IF NOT EXISTS "report_approvals" (
	"id"	INTEGER,
	"report_id"	INTEGER NOT NULL,
	"approved_by"	TEXT NOT NULL,
	"approved_at"	INTEGER NOT NULL,
	"note"	TEXT DEFAULT NULL,
	"is_final"	INTEGER NOT NULL DEFAULT 0,
	PRIMARY KEY("id" AUTOINCREMENT),
	FOREIGN KEY("report_id") REFERENCES "reports"("id")
);
-- 1. Das aktive Lock (Die Quelle der Wahrheit)
CREATE TABLE IF NOT EXISTS "editor_locks" (
	"report_id"	  INTEGER NOT NULL PRIMARY KEY,
        "lock_id"         TEXT    NOT NULL, -- Der "Schlüssel" für Schreibzugriffe
        "locked_by"       TEXT    NOT NULL, -- UserID
        "sse_client"      TEXT    NOT NULL, -- Eindeutige ID der SSE-Verbindung
        "locked_at"       INTEGER NOT NULL,
        "cooldown_until"  INTEGER,          -- NULL wenn kein Cooldown
        FOREIGN KEY("report_id") REFERENCES reports(id)
);
CREATE TABLE IF NOT EXISTS "lock_takeover_requests" (
    "id"            INTEGER PRIMARY KEY AUTOINCREMENT,
    "report_id"     INTEGER NOT NULL,
    "lock_id"       TEXT    NOT NULL,
    "requested_by"  TEXT    NOT NULL,
    "requested_at"  INTEGER NOT NULL,
    "responded_at"  INTEGER,
    "status"        TEXT    NOT NULL DEFAULT 'pending'
                    CHECK("status" IN ('pending', 'granted', 'denied', 'expired'))
);
CREATE TABLE IF NOT EXISTS "investigator_aliases" (
	"id"	INTEGER,
	"term"	TEXT NOT NULL UNIQUE,
	"created_by"	TEXT NOT NULL DEFAULT '',
	"created_at"	INTEGER NOT NULL,
	PRIMARY KEY("id" AUTOINCREMENT)
);
-- 2. Die Warteschlange (FIFO)
CREATE TABLE IF NOT EXISTS "lock_queue" (
        "id"              INTEGER PRIMARY KEY AUTOINCREMENT,
        "report_id"       INTEGER NOT NULL,
        "requested_by"    TEXT    NOT NULL,
        "sse_client"      TEXT    NOT NULL,
        "requested_at"    INTEGER NOT NULL,
        FOREIGN KEY("report_id") REFERENCES reports("id")
);
-- Index für schnelles Finden der Warteschlange pro Bericht
CREATE INDEX IF NOT EXISTS "idx_queue_report" ON lock_queue("report_id", "requested_at");
-- Audit-Tabelle: welcher Client hat welchen Bericht geöffnet (wächst, wird nicht bereinigt).
-- Beleg: Layer 3 States OPENING, Paket-6-Ergänzung 2026-05-24
CREATE TABLE IF NOT EXISTS "report_opened" (
        "id"         INTEGER PRIMARY KEY AUTOINCREMENT,
        "report_id"  INTEGER NOT NULL,
        "sse_client" TEXT    NOT NULL,
        "opened_by"  TEXT    NOT NULL,
        "opened_at"  INTEGER NOT NULL,
        FOREIGN KEY("report_id") REFERENCES reports("id")
);
CREATE INDEX IF NOT EXISTS "idx_report_opened_report" ON report_opened("report_id", "sse_client");
CREATE INDEX IF NOT EXISTS "idx_report_opened_client" ON report_opened("sse_client");
CREATE INDEX IF NOT EXISTS "pv_url_idx" ON "page_visits" (
	"page_url"
);
CREATE INDEX IF NOT EXISTS "ve_url_idx" ON "viewport_events" (
	"page_url"
);
CREATE INDEX IF NOT EXISTS "ann_url_idx" ON "annotations" (
	"page_url"
);
CREATE INDEX IF NOT EXISTS "ann_cat_idx" ON "annotations" (
	"category"
);
CREATE INDEX IF NOT EXISTS "rep_type_idx" ON "reports" (
	"report_type"
);
CREATE INDEX IF NOT EXISTS "rep_status_idx" ON "reports" (
	"status"
);
CREATE INDEX IF NOT EXISTS "rb_report_idx" ON "report_blocks" (
	"report_id"
);
CREATE INDEX IF NOT EXISTS "rb_author_idx" ON "report_blocks" (
	"author"
);
CREATE INDEX IF NOT EXISTS "rbo_sort_idx" ON "report_block_order" (
	"sort_index"
);
CREATE INDEX IF NOT EXISTS "ra_block_idx" ON "report_anchors" (
	"block_id"
);
CREATE INDEX IF NOT EXISTS "ra_ann_idx" ON "report_anchors" (
	"annotation_id"
);
CREATE UNIQUE INDEX IF NOT EXISTS "ra_block_ann_uniq" ON "report_anchors" (
	"block_id",
	"annotation_id"
);
CREATE INDEX IF NOT EXISTS "rc_block_idx" ON "report_comments" (
	"block_id"
);
CREATE INDEX IF NOT EXISTS "rc_status_idx" ON "report_comments" (
	"status"
);
CREATE INDEX IF NOT EXISTS "rap_report_idx" ON "report_approvals" (
	"report_id"
);
CREATE UNIQUE INDEX IF NOT EXISTS "reports_one_final_idx" ON "reports" (
	"report_type"
) WHERE "report_type" = 'final';
CREATE INDEX IF NOT EXISTS "ia_term_idx" ON "investigator_aliases" (
	"term"
);
CREATE INDEX IF NOT EXISTS "ann_local_id_idx" ON "annotations" (
	"local_id"
) WHERE "local_id" IS NOT NULL;
CREATE INDEX IF NOT EXISTS "ann_active_url_idx" ON "annotations" (
	"page_url"
) WHERE "deleted_at" IS NULL;
CREATE INDEX IF NOT EXISTS "ann_prev_id_idx" ON "annotations" (
	"prev_id"
) WHERE "prev_id" IS NOT NULL;
"""

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
    # Bug 2.123 (Build 264, 2026-05-30): investigator_id kann ein Textkuerzel sein
    # (z.B. 'nw082317'), wenn die Annotation von einem anderen Ermittler stammt
    # und dieser keinen numerischen Eintrag in coordinator.db hatte. SQLite erzwingt
    # den INTEGER-Typ nicht (type affinity). str statt int vermeidet ValueError.
    investigator_id: Optional[str]
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
    """Aktiver Editor-Lock (Schema v2.0).

    report_id statt resource-String. cooldown_until schuetzt Inhaber
    vor TAKEOVER-Anfragen (SLA Punkt 8).
    Beleg: Architektur-Revision 2026-05-18
    """
    report_id:      int
    locked_by:      str
    lock_id:        str
    locked_at:      int
    sse_client:     str
    cooldown_until: Optional[int]  # Unix-Timestamp oder None


# =============================================================================
# Ausnahmen
# =============================================================================

class EvidenceDbError(Exception):
    """Wird geworfen bei ungueltigen Eingaben."""


class ReportSealedError(EvidenceDbError):
    """
    Der Bericht ist nicht mehr aenderbar (Status submitted/approved/final).

    ERBT BEWUSST von EvidenceDbError: die bestehenden Fehlerpfade in
    forensic_api/report.py fangen EvidenceDbError bereits ab und melden 403/409
    an den Client — die Sperre wirkt damit sofort auf ALLEN Berichts-Endpunkten,
    ohne dass jeder einzeln angefasst werden muesste. Wer den Fall
    unterscheiden will, kann gezielt auf ReportSealedError pruefen.

    Beleg: BERICHTS-STATUSMODELL (siehe oben), Build 379.
    """


# =============================================================================
# Hauptklasse
# =============================================================================

class EvidenceDb:
    """Kapselt alle Schreib- und Lesezugriffe auf die evidence_db."""

    _LOCK_TIMEOUT_SEC: int = 90  # Sekunden bis automatischer Lock-Ablauf

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

    # =====================================================================
    # SCHREIBSPERRE FUER EINGEREICHTE/ABGENOMMENE BERICHTE (Build 379)
    #
    # Suchbegriff: BERICHTS-STATUSMODELL
    #
    # Ab Status 'submitted' ist der Berichtsinhalt fuer den AUTOR gesperrt.
    # Bis Build 379 war die Sperre LUECKENHAFT: update_block und delete_block
    # prueften nur auf 'approved' (nicht auf 'final'), waehrend save_block,
    # set_block_order, add_anchor und remove_anchor GAR NICHT geschuetzt waren.
    # Ein freigegebener Bericht konnte also weiterhin neue Bloecke bekommen,
    # umsortiert und mit Ankern versehen werden — alles Dinge, die im Siegel-
    # Hash stecken (Build 377). Das Siegel haette die Aenderung NACHTRAEGLICH
    # aufgedeckt; verhindert hat sie niemand.
    #
    # Die Guards sitzen ZENTRAL in dieser Klasse (eine Stelle statt sieben
    # Endpunkten). KOMMENTARE bleiben bewusst erlaubt (mc): sie stecken nicht
    # im Siegel-Hash und dokumentieren den Bedarf fuer einen Nachtragsbericht.
    # =====================================================================

    def _report_status(self, report_id: int) -> Optional[str]:
        row = self._con.execute(
            "SELECT status FROM reports WHERE id = ?", (report_id,)
        ).fetchone()
        return str(row["status"]) if row else None

    def _assert_report_editable(self, report_id: int) -> None:
        """Wirft ReportSealedError, wenn der Bericht gesperrt ist."""
        status = self._report_status(report_id)
        if status is None:
            return  # nicht vorhanden -> die Aufrufer melden das eigenstaendig
        if status in LOCKED_REPORT_STATUSES:
            raise ReportSealedError(
                f"Bericht {report_id} ist im Status '{status}' und kann nicht "
                f"mehr geaendert werden. Nur der Lektor oder die "
                f"Chef-Ermittlerin koennen ihn zur Nachbesserung "
                f"zuruecksetzen."
            )

    def _assert_block_editable(self, block_id: str) -> None:
        """Wie _assert_report_editable, ausgehend von einem Block."""
        row = self._con.execute(
            "SELECT r.id AS report_id, r.status "
            "FROM report_blocks b JOIN reports r ON r.id = b.report_id "
            "WHERE b.block_id = ?", (block_id,)
        ).fetchone()
        if not row:
            return  # unbekannter Block -> die Aufrufer melden das eigenstaendig
        status = str(row["status"])
        if status in LOCKED_REPORT_STATUSES:
            raise ReportSealedError(
                f"Bericht {row['report_id']} ist im Status '{status}' und kann "
                f"nicht mehr geaendert werden. Nur der Lektor oder die "
                f"Chef-Ermittlerin koennen ihn zur Nachbesserung "
                f"zuruecksetzen."
            )

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
        *,
        allow_reset: bool = False,
    ) -> bool:
        """
        Setzt den Berichtsstatus und ERZWINGT die Uebergaenge des
        BERICHTS-STATUSMODELLS (Build 379; vorher war JEDER Uebergang moeglich,
        auch die Rueckstufung eines freigegebenen Berichts auf 'draft' — womit
        sich die Sperre selbst haette aushebeln lassen).

        Zulaessige Uebergaenge:
            draft     -> submitted   (der AUTOR reicht zur Abnahme ein)
            submitted -> draft       (NUR Lektor/Chef-Ermittlerin, zur
                                      Nachbesserung -> allow_reset=True)
            submitted -> approved    (Abnahme; erfolgt ueber den auditierten
                                      Management-Pfad, Build 377)
            approved  -> final       (versandt/abgeschlossen; Management-Pfad)

        Alles andere wird abgewiesen — insbesondere JEDE Rueckstufung aus
        'approved' oder 'final' (unwiderruflich, mc 2026-07-10).

        allow_reset: nur der Management-Pfad (Lektor/Chefin) setzt dies auf
        True, um submitted -> draft zu erlauben. Der Ermittler-Webserver ruft
        die Methode ohne dieses Flag.
        """
        if status not in VALID_REPORT_STATUSES:
            raise EvidenceDbError(
                f"Ungueltiger Berichtsstatus: '{status}'. "
                f"Zulaessig: {sorted(VALID_REPORT_STATUSES)}"
            )

        current = self._report_status(report_id)
        if current is None:
            return False
        if current == status:
            return True  # No-op, kein Fehler

        allowed = {
            ("draft", "submitted"),
            ("submitted", "approved"),
            ("approved", "final"),
        }
        if allow_reset:
            allowed.add(("submitted", "draft"))

        if (current, status) not in allowed:
            raise ReportSealedError(
                f"Unzulaessiger Statuswechsel '{current}' -> '{status}'. "
                f"Freigegebene ('approved') und versandte ('final') Berichte "
                f"koennen nicht zurueckgestuft werden; die Rueckgabe eines "
                f"eingereichten Berichts zur Nachbesserung ist dem Lektor und "
                f"der Chef-Ermittlerin vorbehalten."
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
        # Build 379: Schreibsperre (BERICHTS-STATUSMODELL). Vorher UNGESCHUETZT
        # -> einem freigegebenen Bericht konnten neue Bloecke hinzugefuegt
        # werden, die im Siegel-Hash stecken.
        self._assert_report_editable(report_id)

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
        # Build 379: sperrt bei submitted/approved/final (vorher NUR 'approved'
        # -> 'final' war ungeschuetzt). Siehe BERICHTS-STATUSMODELL.
        if str(row["report_status"]) in LOCKED_REPORT_STATUSES:
            raise ReportSealedError(
                f"Bericht im Status '{row['report_status']}' kann nicht mehr "
                f"geaendert werden. Nur der Lektor oder die Chef-Ermittlerin "
                f"koennen ihn zur Nachbesserung zuruecksetzen."
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
        # Build 379: sperrt bei submitted/approved/final (vorher NUR 'approved'
        # -> 'final' war ungeschuetzt). Siehe BERICHTS-STATUSMODELL.
        if str(row["report_status"]) in LOCKED_REPORT_STATUSES:
            raise ReportSealedError(
                f"Bericht im Status '{row['report_status']}' kann nicht mehr "
                f"geaendert werden. Nur der Lektor oder die Chef-Ermittlerin "
                f"koennen ihn zur Nachbesserung zuruecksetzen."
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
        # Build 379: Schreibsperre (BERICHTS-STATUSMODELL). Vorher UNGESCHUETZT
        # -> die Block-REIHENFOLGE ist Teil des Berichts und steckt im Siegel.
        # set_block_order kennt keine report_id — die Pruefung erfolgt daher
        # ueber die Bloecke selbst (jeder Block gehoert zu genau einem Bericht).
        for _entry in order:
            _bid = str(_entry.get("block_id", ""))
            if _bid:
                self._assert_block_editable(_bid)

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
        # Build 379: Schreibsperre (BERICHTS-STATUSMODELL). Vorher UNGESCHUETZT
        # -> Beweisanker stecken im Siegel-Hash.
        self._assert_block_editable(block_id)

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
        # Build 379: Schreibsperre (BERICHTS-STATUSMODELL). Vorher UNGESCHUETZT.
        # Der Anker verweist auf einen Block -> ueber diesen den Bericht pruefen.
        row = self._con.execute(
            "SELECT block_id FROM report_anchors WHERE id = ?", (anchor_id,)
        ).fetchone()
        if row:
            self._assert_block_editable(str(row["block_id"]))

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

    def get_all_cache_entries(self, uid: int) -> dict:
        """
        Liest alle Cache-Eintraege fuer eine uid als Dict.

        Returns: {query_id: cached_value, ...}

        Wird beim Ausliefern von Bloecken verwendet, um auto:-Werte
        in placeholder_values_json einzuweben ohne in die DB zu schreiben.
        Beleg: Bugfix-Liste 2.17, Projektgespraech 2026-06-07
        Build 287
        """
        rows = self._con.execute(
            "SELECT query_id, cached_value FROM placeholder_cache WHERE uid = ?",
            (uid,),
        ).fetchall()
        return {str(r["query_id"]): str(r["cached_value"]) for r in rows}

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
        """Event-Signal das bei jeder Lock-Aenderung gesetzt wird (SSE-Thread)."""
        return self._lock_change_event

    # ------------------------------------------------------------------
    # Lock-Grundoperationen (SLA Punkte 1, 6, 7, 11)
    # ------------------------------------------------------------------

    def acquire_lock(
        self, report_id: int, locked_by: str, sse_client: str,
    ) -> Optional[str]:
        """Erwirbt den Lock fuer einen Bericht atomar.

        Gibt neue lock_id zurueck oder None wenn Lock bereits belegt.
        Kein Timeout-basiertes Loeschen alter Locks — das erledigt
        release_lock_with_queue_cascade() beim RELEASING.
        Beleg: SLA Punkt 6, Architektur-Revision 2026-05-18
        """
        new_lock_id = str(uuid.uuid4())
        try:
            self._con.execute(
                "INSERT INTO editor_locks "
                "(report_id, locked_by, lock_id, locked_at, sse_client) "
                "VALUES (?, ?, ?, ?, ?)",
                (report_id, locked_by, new_lock_id, int(time.time()), sse_client),
            )
            self._con.commit()
            self._lock_change_event.set()
            logger.info(
                "Lock erworben: '%s' report_id=%d lock_id=%s",
                locked_by, report_id, new_lock_id,
            )
            return new_lock_id
        except sqlite3.IntegrityError:
            logger.debug("acquire_lock: Lock bereits belegt fuer report_id=%d", report_id)
            return None

    def create_report_with_lock(
        self, report_type: str, title: str, created_by: str, sse_client: str,
    ) -> tuple[int, str]:
        """Erzeugt Bericht und Lock atomar in einer Transaktion.

        Gibt (report_id, lock_id) zurueck.
        Beleg: SLA Punkt 7, Architektur-Revision 2026-05-18
        """
        now = int(time.time())
        lock_id = str(uuid.uuid4())
        seq_nr = self._con.execute(
            "SELECT COALESCE(MAX(sequence_nr), 0) + 1 FROM reports WHERE report_type=?",
            (report_type,),
        ).fetchone()[0]
        try:
            cursor = self._con.execute(
                "INSERT INTO reports (report_type, sequence_nr, title, created_by, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (report_type, seq_nr, title, created_by, now),
            )
            report_id = cursor.lastrowid
            self._con.execute(
                "INSERT INTO editor_locks "
                "(report_id, locked_by, lock_id, locked_at, sse_client) "
                "VALUES (?, ?, ?, ?, ?)",
                (report_id, created_by, lock_id, now, sse_client),
            )
            self._con.commit()
            self._lock_change_event.set()
            logger.info(
                "Bericht+Lock atomar: report_id=%d type=%s lock_id=%s von '%s'",
                report_id, report_type, lock_id, created_by,
            )
            return report_id, lock_id
        except Exception as exc:
            self._con.rollback()
            raise exc

    def release_lock_with_queue_cascade(
        self, report_id: int, lock_id: str,
    ) -> Optional[tuple[str, str, str]]:
        """Gibt Lock frei und vergibt ihn ggf. an ersten gueltigen Queue-Eintrag.

        Fuehrt die FIFO-Kaskade durch (SLA Punkt 4):
        1. Lock loeschen
        2. Queue fuer diesen Bericht in FIFO-Reihenfolge durchgehen
        3. Eintraege ohne aktive SSE-Verbindung loeschen (lazy cleanup)
        4. Ersten gueltigen Eintrag zum neuen Inhaber machen
        5. Alles atomar in einer Transaktion

        Gibt (neuer_lock_id, neuer_locked_by, neuer_sse_client) zurueck
        wenn ein Warteschlangenkandidat gefunden wurde, sonst None.
        Beleg: SLA Punkte 3, 4, Architektur-Revision 2026-05-18
        """
        # Aktive SSE-Clients aus events.py-Kontext — wird von aussen injiziert
        # da evidence_db keine Kenntnis des SSE-Zustands hat
        raise NotImplementedError(
            "release_lock_with_queue_cascade muss von der API-Schicht aufgerufen "
            "werden die Zugriff auf aktive SSE-Clients hat. "
            "Siehe forensic_api/report.py _action_release_lock"
        )

    def release_lock(self, report_id: int, lock_id: str) -> bool:
        """Gibt Lock frei (ohne Queue-Kaskade).

        Fuer interne Verwendung wenn Queue bereits extern verarbeitet wird.
        Beleg: Architektur-Revision 2026-05-18
        """
        cursor = self._con.execute(
            "DELETE FROM editor_locks WHERE report_id=? AND lock_id=?",
            (report_id, lock_id),
        )
        self._con.commit()
        freed = cursor.rowcount > 0
        if freed:
            self._lock_change_event.set()
            logger.info("Lock freigegeben: report_id=%d lock_id=%s", report_id, lock_id)
        return freed

    def clear_stale_locks_on_startup(self) -> int:
        """Bereinigt alle Locks beim Server-Start.

        Nach einem Server-Neustart sind alle in editor_locks gespeicherten
        Locks Stale: die zugehoerigen SSE-Verbindungen existieren nicht mehr
        und die Grace-Period-Timer wurden nicht uebertragen. Ein Beibehalten
        dieser Locks wuerde alle acquire()-Versuche mit 423 blockieren, weil
        kein aktiver Client die Locks freigeben kann.

        Wird einmalig beim Serverstart aufgerufen, bevor HTTP-Verbindungen
        angenommen werden. Die Queue (lock_queue) und Takeover-Eintraege
        (lock_takeover_requests) werden ebenfalls bereinigt, da sie ohne
        aktive SSE-Verbindungen bedeutungslos sind.

        Gibt die Anzahl der geloeschten Locks zurueck.

        Beleg: Bugfix-Liste 2.23, Projektgespraech 2026-06-07
        Build 281
        """
        cursor = self._con.execute("DELETE FROM editor_locks")
        count  = cursor.rowcount
        # Queue und Takeover-Eintraege ebenfalls bereinigen
        self._con.execute("DELETE FROM lock_queue")
        self._con.execute("DELETE FROM lock_takeover_requests")
        self._con.commit()
        if count:
            logger.info(
                "Startup: %d Stale-Lock(s) aus editor_locks bereinigt.", count
            )
        return count

    def release_lock_by_sse_client(self, sse_client: str) -> list[int]:
        """Gibt alle Locks frei die zu einer SSE-Client-ID gehoeren.

        Wird aufgerufen wenn SSE-Grace-Period ablaeuft (SLA Punkt 2).
        Gibt Liste der betroffenen report_ids zurueck.
        Beleg: SLA Punkt 1, Architektur-Revision 2026-05-18
        """
        rows = self._con.execute(
            "SELECT report_id FROM editor_locks WHERE sse_client=?",
            (sse_client,),
        ).fetchall()
        report_ids = [r[0] for r in rows]
        if report_ids:
            self._con.execute(
                "DELETE FROM editor_locks WHERE sse_client=?", (sse_client,)
            )
            self._con.commit()
            self._lock_change_event.set()
            logger.info(
                "Locks durch SSE-Ablauf freigegeben: sse_client=%s report_ids=%s",
                sse_client, report_ids,
            )
        return report_ids

    def resume_lock(
        self, old_sse_client: str, new_sse_client: str,
    ) -> bool:
        """Aktualisiert SSE-Client-ID nach Reconnect innerhalb der Grace-Period.

        RESUMING ist eine Layer-2-Aktion: Es werden ausschliesslich Layer-2-Daten
        (SSE-Client-IDs) verwendet. Die lock_id ist Layer-4-Daten und darf hier
        nicht als Kriterium herangezogen werden.

        Ablauf:
          1. Suche in editor_locks nach einem Eintrag mit sse_client=old_sse_client.
          2. Wird ein Eintrag gefunden, wird sse_client auf new_sse_client gesetzt.
          3. locked_at wird aktualisiert (verhindert Timeout durch frische Aktivitaet).

        Beleg: Layer 2 States RESUMING, SLA Punkt 2,
               Architekturentscheidung Paket-4-Review 2026-05-24
        """
        cursor = self._con.execute(
            "UPDATE editor_locks "
            "SET sse_client=?, locked_at=? "
            "WHERE sse_client=?",
            (new_sse_client, int(time.time()), old_sse_client),
        )
        self._con.commit()
        ok = cursor.rowcount > 0
        if ok:
            logger.info(
                "Lock-Resume: alte_sse=%s neue_sse=%s",
                old_sse_client, new_sse_client,
            )
        return ok

    def get_lock(self, report_id: int) -> Optional[EditorLockRecord]:
        """Liest den aktiven Lock fuer einen Bericht (thread-safe).

        Verwendet eigene Connection wenn _db_path gesetzt (SSE-Thread-Safety).
        Beleg: Build 098, Thread-Safety-Fix
        """
        sql = (
            "SELECT report_id, locked_by, lock_id, locked_at, sse_client, cooldown_until "
            "FROM editor_locks WHERE report_id=?"
        )

        def _parse(row: sqlite3.Row) -> Optional[EditorLockRecord]:
            if row is None:
                return None
            return EditorLockRecord(
                report_id=int(row["report_id"]),
                locked_by=str(row["locked_by"] or ""),
                lock_id=str(row["lock_id"]),
                locked_at=int(row["locked_at"]),
                sse_client=str(row["sse_client"] or ""),
                cooldown_until=row["cooldown_until"],
            )

        if self._db_path:
            try:
                rc = sqlite3.connect(self._db_path, timeout=5.0, check_same_thread=False)
                rc.row_factory = sqlite3.Row
                row = rc.execute(sql, (report_id,)).fetchone()
                rc.close()
                return _parse(row)
            except (sqlite3.OperationalError, sqlite3.ProgrammingError,
                    sqlite3.InterfaceError, TypeError) as exc:
                logger.debug("get_lock (eigene Con) fehlgeschlagen: %s", exc)
                return None
        try:
            row = self._con.execute(sql, (report_id,)).fetchone()
            return _parse(row)
        except (sqlite3.OperationalError, sqlite3.ProgrammingError,
                sqlite3.InterfaceError, TypeError) as exc:
            logger.debug("get_lock fehlgeschlagen: %s", exc)
        return None

    def validate_lock(self, report_id: int, lock_id: str) -> bool:
        """Prueft ob lock_id fuer diesen Bericht gueltig ist.

        Schema v2.0: direkte Pruefung auf (report_id, lock_id).
        Kein resource-String-Fallback mehr.
        Beleg: SLA Punkt 11, Architektur-Revision 2026-05-18
        """
        try:
            row = self._con.execute(
                "SELECT 1 FROM editor_locks WHERE report_id=? AND lock_id=?",
                (report_id, lock_id),
            ).fetchone()
            return row is not None
        except sqlite3.OperationalError:
            return False

    def set_cooldown(self, report_id: int, seconds: int) -> bool:
        """Setzt Cooldown auf dem Lock (SLA Punkt 8).

        Schuetzt Lock-Inhaber vor TAKEOVER-Anfragen.
        Beleg: SLA Punkt 8, Layer 4 States TAKEOVER_DENIED
        """
        cooldown_until = int(time.time()) + seconds
        cursor = self._con.execute(
            "UPDATE editor_locks SET cooldown_until=? WHERE report_id=?",
            (cooldown_until, report_id),
        )
        self._con.commit()
        return cursor.rowcount > 0

    def clear_cooldown(self, report_id: int) -> bool:
        """Entfernt Cooldown vom Lock (bei RELEASING durch Inhaber)."""
        cursor = self._con.execute(
            "UPDATE editor_locks SET cooldown_until=NULL WHERE report_id=?",
            (report_id,),
        )
        self._con.commit()
        return cursor.rowcount > 0

    def get_cooldown_until(self, report_id: int) -> Optional[int]:
        """Gibt Unix-Timestamp des aktiven Cooldowns zurueck oder None."""
        try:
            row = self._con.execute(
                "SELECT cooldown_until FROM editor_locks WHERE report_id=?",
                (report_id,),
            ).fetchone()
            if row and row[0] and row[0] > int(time.time()):
                return int(row[0])
            return None
        except sqlite3.OperationalError:
            return None

    # ------------------------------------------------------------------
    # Queue-Operationen (SLA Punkte 4, 9)
    # ------------------------------------------------------------------

    def queue_add(self, report_id: int, requested_by: str, sse_client: str) -> int:
        """Fuegt Eintrag in Warteschlange ein.

        Jeder Client kann pro Bericht nur einen Eintrag haben:
        bestehender Eintrag wird zuerst entfernt.
        Beleg: SLA Punkt 9, Layer 4 States QUEUED
        """
        now = int(time.time())
        self._con.execute(
            "DELETE FROM lock_queue WHERE report_id=? AND requested_by=?",
            (report_id, requested_by),
        )
        cursor = self._con.execute(
            "INSERT INTO lock_queue (report_id, requested_by, sse_client, requested_at) "
            "VALUES (?, ?, ?, ?)",
            (report_id, requested_by, sse_client, now),
        )
        self._con.commit()
        logger.debug(
            "Queue: '%s' eingereiht fuer report_id=%d", requested_by, report_id
        )
        return cursor.lastrowid

    def queue_remove(self, report_id: int, requested_by: str) -> bool:
        """Entfernt eigenen Queue-Eintrag (QUEUED -> IDLE)."""
        cursor = self._con.execute(
            "DELETE FROM lock_queue WHERE report_id=? AND requested_by=?",
            (report_id, requested_by),
        )
        self._con.commit()
        return cursor.rowcount > 0

    def queue_next_valid(
        self, report_id: int, active_sse_clients: set[str],
    ) -> Optional[dict]:
        """Findet naechsten gueltigen Queue-Eintrag (FIFO mit lazy cleanup).

        Durchlaeuft Queue in FIFO-Reihenfolge, loescht inaktive SSE-Eintraege,
        gibt ersten Eintrag mit aktiver SSE-Verbindung zurueck.
        Beleg: SLA Punkt 4, Architektur-Revision 2026-05-18
        """
        rows = self._con.execute(
            "SELECT id, requested_by, sse_client, requested_at "
            "FROM lock_queue WHERE report_id=? ORDER BY requested_at ASC, id ASC",
            (report_id,),
        ).fetchall()

        stale_ids = []
        result = None
        for row in rows:
            if row["sse_client"] not in active_sse_clients:
                stale_ids.append(row["id"])
                logger.debug(
                    "Queue: Eintrag %d von '%s' bereinigt (SSE inaktiv)",
                    row["id"], row["requested_by"],
                )
            else:
                result = {
                    "id":           row["id"],
                    "requested_by": row["requested_by"],
                    "sse_client":   row["sse_client"],
                }
                break  # Erster gueltiger Eintrag gefunden

        if stale_ids:
            placeholders = ",".join("?" * len(stale_ids))
            self._con.execute(
                f"DELETE FROM lock_queue WHERE id IN ({placeholders})", stale_ids
            )
            self._con.commit()

        return result

    def queue_count(self, report_id: int) -> int:
        """Gibt Anzahl der Eintraege in der Queue zurueck."""
        row = self._con.execute(
            "SELECT COUNT(*) FROM lock_queue WHERE report_id=?", (report_id,)
        ).fetchone()
        return row[0] if row else 0

    def queue_remove_by_sse_client(self, sse_client: str) -> int:
        """Entfernt alle Queue-Eintraege einer SSE-Verbindung.

        Wird bei SSE-Abriss aufgerufen (lazy cleanup als Ergaenzung).
        SLA Punkt 9: Queue-Integrität.
        """
        cursor = self._con.execute(
            "DELETE FROM lock_queue WHERE sse_client=?", (sse_client,)
        )
        self._con.commit()
        return cursor.rowcount

    # ------------------------------------------------------------------
    # report_opened — Audit-Log geöffneter Berichte (Layer 3 OPENING)
    # ------------------------------------------------------------------

    def log_report_opened(
        self, report_id: int, sse_client: str, opened_by: str,
    ) -> int:
        """Schreibt einen Öffnen-Eintrag in report_opened.

        Die Tabelle wächst als Audit-Trail und wird nicht bereinigt.
        Zusätzlich werden alle Queue-Einträge des Clients für andere
        Berichte entfernt (Berichtswechsel invalidiert Warteschlangen-
        position, SLA Layer 3 OPENING).

        Gibt die neue id zurück.
        Beleg: Layer 3 States OPENING, SLA Paket-6-Ergänzung 2026-05-24
        """
        now = int(time.time())
        cursor = self._con.execute(
            "INSERT INTO report_opened (report_id, sse_client, opened_by, opened_at) "
            "VALUES (?, ?, ?, ?)",
            (report_id, sse_client, opened_by, now),
        )
        # Queue-Bereinigung: Einträge für ANDERE Berichte dieses Clients löschen.
        # Beleg: Layer 3 States OPENING: „Einträge in der Warteschlange
        # für den Client werden alle entfernt."
        self._con.execute(
            "DELETE FROM lock_queue WHERE sse_client=? AND report_id!=?",
            (sse_client, report_id),
        )
        self._con.commit()
        logger.debug(
            "report_opened: report_id=%d sse_client=%s opened_by=%s",
            report_id, sse_client, opened_by,
        )
        return cursor.lastrowid

    def get_open_report_for_client(self, sse_client: str) -> Optional[int]:
        """Gibt die report_id des zuletzt geöffneten Berichts für einen Client zurück.

        Liest den neuesten Eintrag aus report_opened für diesen sse_client.
        Gibt None zurück wenn kein Eintrag vorhanden.
        Beleg: Layer 3 States OPENED, Paket-6-Ergänzung 2026-05-24
        """
        row = self._con.execute(
            "SELECT report_id FROM report_opened "
            "WHERE sse_client=? ORDER BY opened_at DESC LIMIT 1",
            (sse_client,),
        ).fetchone()
        return int(row["report_id"]) if row else None

    # ------------------------------------------------------------------
    # Takeover-Audit-Log (SLA Punkt 10)
    # ------------------------------------------------------------------

    def log_takeover_request(
        self, report_id: int, lock_id: str, requested_by: str,
    ) -> int:
        """Schreibt Takeover-Anfrage in Audit-Log."""
        cursor = self._con.execute(
            "INSERT INTO lock_takeover_requests "
            "(report_id, lock_id, requested_by, requested_at, status) "
            "VALUES (?, ?, ?, ?, 'pending')",
            (report_id, lock_id, requested_by, int(time.time())),
        )
        self._con.commit()
        return cursor.lastrowid

    def resolve_takeover(self, request_id: int, status: str) -> bool:
        """Beantwortet Takeover-Anfrage im Audit-Log (status: granted/denied/expired)."""
        assert status in ('granted', 'denied', 'expired')
        cursor = self._con.execute(
            "UPDATE lock_takeover_requests "
            "SET status=?, responded_at=? "
            "WHERE id=? AND status='pending'",
            (status, int(time.time()), request_id),
        )
        self._con.commit()
        return cursor.rowcount > 0

    def get_pending_takeover(self, report_id: int) -> Optional[dict]:
        """Gibt aelteste offene Takeover-Anfrage fuer einen Bericht zurueck."""
        try:
            row = self._con.execute(
                "SELECT id, lock_id, requested_by, requested_at "
                "FROM lock_takeover_requests "
                "WHERE report_id=? AND status='pending' "
                "ORDER BY requested_at ASC LIMIT 1",
                (report_id,),
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
            # Bug 2.123 (Build 264): str() statt int() — investigator_id kann ein
            # Textkuerzel sein. str(None) wuerde 'None' liefern, daher explizite Pruefung.
            investigator_id=(
                str(r["investigator_id"])
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

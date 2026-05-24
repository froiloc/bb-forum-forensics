BEGIN TRANSACTION;
DROP TABLE IF EXISTS "scraper_log";
CREATE TABLE IF NOT EXISTS "scraper_log" (
	"id"	INTEGER,
	"event"	TEXT NOT NULL,
	"user_id"	INTEGER NOT NULL,
	"detail"	TEXT,
	"ts"	INTEGER NOT NULL,
	PRIMARY KEY("id" AUTOINCREMENT)
);
DROP TABLE IF EXISTS "page_visits";
CREATE TABLE IF NOT EXISTS "page_visits" (
	"id"	INTEGER,
	"page_url"	TEXT NOT NULL,
	"scrape_context"	TEXT NOT NULL,
	"ts"	INTEGER NOT NULL,
	"investigator_id"	INTEGER,
	PRIMARY KEY("id" AUTOINCREMENT)
);
DROP TABLE IF EXISTS "viewport_events";
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
DROP TABLE IF EXISTS "annotations";
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
DROP TABLE IF EXISTS "reports";
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
DROP TABLE IF EXISTS "report_blocks";
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
DROP TABLE IF EXISTS "report_block_order";
CREATE TABLE IF NOT EXISTS "report_block_order" (
	"block_id"	TEXT NOT NULL,
	"sort_index"	INTEGER NOT NULL,
	"last_modified_by"	TEXT NOT NULL,
	"last_modified_at"	INTEGER NOT NULL,
	FOREIGN KEY("block_id") REFERENCES "report_blocks"("block_id"),
	PRIMARY KEY("block_id")
);
DROP TABLE IF EXISTS "report_anchors";
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
DROP TABLE IF EXISTS "report_comments";
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
DROP TABLE IF EXISTS "placeholder_cache";
CREATE TABLE IF NOT EXISTS "placeholder_cache" (
	"query_id"	TEXT NOT NULL,
	"uid"	INTEGER NOT NULL,
	"cached_value"	TEXT NOT NULL,
	"cached_at"	INTEGER NOT NULL,
	PRIMARY KEY("query_id","uid")
);
DROP TABLE IF EXISTS "report_approvals";
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
DROP TABLE IF EXISTS "editor_locks";
CREATE TABLE IF NOT EXISTS "editor_locks" (
	"report_id"	  INTEGER NOT NULL PRIMARY KEY,
        "lock_id"         TEXT    NOT NULL, -- Der "Schlüssel" für Schreibzugriffe
        "locked_by"       TEXT    NOT NULL, -- UserID
        "sse_client"      TEXT    NOT NULL, -- Eindeutige ID der SSE-Verbindung
        "locked_at"       INTEGER NOT NULL,
        "cooldown_until"  INTEGER,          -- NULL wenn kein Cooldown
        FOREIGN KEY("report_id") REFERENCES reports(id)
);
DROP TABLE IF EXISTS "lock_takeover_requests";
CREATE TABLE IF NOT EXISTS "lock_takeover_requests" (
        "id"            INTEGER PRIMARY KEY AUTOINCREMENT,
        "report_id"     INTEGER NOT NULL, -- Hinzugefügt, um Takeover einem Bericht zuzuordnen
        "lock_id"       TEXT    NOT NULL, -- Auf welches Lock bezog sich die Anfrage?
	"requested_by"	TEXT NOT NULL,
	"requested_at"	INTEGER NOT NULL,
	"responded_at"  INTEGER,
	"status"	TEXT NOT NULL DEFAULT 'pending' CHECK("status" IN ('pending', 'granted', 'denied', 'expired'))
);
DROP TABLE IF EXISTS "investigator_aliases";
CREATE TABLE IF NOT EXISTS "investigator_aliases" (
	"id"	INTEGER,
	"term"	TEXT NOT NULL UNIQUE,
	"created_by"	TEXT NOT NULL DEFAULT '',
	"created_at"	INTEGER NOT NULL,
	PRIMARY KEY("id" AUTOINCREMENT)
);
-- 2. Die Warteschlange (FIFO)
DROP TABLE IF EXISTS "lock_queue";
CREATE TABLE "lock_queue" (
        "id"              INTEGER PRIMARY KEY AUTOINCREMENT,
        "report_id"       INTEGER NOT NULL,
        "requested_by"    TEXT    NOT NULL,
        "sse_client"      TEXT    NOT NULL,
        "requested_at"    INTEGER NOT NULL,
        FOREIGN KEY("report_id") REFERENCES reports("id")
);
-- Index für schnelles Finden der Warteschlange pro Bericht
DROP INDEX IF EXISTS "idx_queue_report";
CREATE INDEX "idx_queue_report" ON lock_queue("report_id", "requested_at");
-- Audit-Tabelle: welcher Client hat welchen Bericht geöffnet (wächst, wird nicht bereinigt).
-- Beleg: Layer 3 States OPENING, Paket-6-Ergänzung 2026-05-24
DROP TABLE IF EXISTS "report_opened";
CREATE TABLE "report_opened" (
        "id"         INTEGER PRIMARY KEY AUTOINCREMENT,
        "report_id"  INTEGER NOT NULL,
        "sse_client" TEXT    NOT NULL,
        "opened_by"  TEXT    NOT NULL,
        "opened_at"  INTEGER NOT NULL,
        FOREIGN KEY("report_id") REFERENCES reports("id")
);
DROP INDEX IF EXISTS "idx_report_opened_report";
CREATE INDEX "idx_report_opened_report" ON report_opened("report_id", "sse_client");
DROP INDEX IF EXISTS "idx_report_opened_client";
CREATE INDEX "idx_report_opened_client" ON report_opened("sse_client");
DROP INDEX IF EXISTS "pv_url_idx";
CREATE INDEX IF NOT EXISTS "pv_url_idx" ON "page_visits" (
	"page_url"
);
DROP INDEX IF EXISTS "ve_url_idx";
CREATE INDEX IF NOT EXISTS "ve_url_idx" ON "viewport_events" (
	"page_url"
);
DROP INDEX IF EXISTS "ann_url_idx";
CREATE INDEX IF NOT EXISTS "ann_url_idx" ON "annotations" (
	"page_url"
);
DROP INDEX IF EXISTS "ann_cat_idx";
CREATE INDEX IF NOT EXISTS "ann_cat_idx" ON "annotations" (
	"category"
);
DROP INDEX IF EXISTS "rep_type_idx";
CREATE INDEX IF NOT EXISTS "rep_type_idx" ON "reports" (
	"report_type"
);
DROP INDEX IF EXISTS "rep_status_idx";
CREATE INDEX IF NOT EXISTS "rep_status_idx" ON "reports" (
	"status"
);
DROP INDEX IF EXISTS "rb_report_idx";
CREATE INDEX IF NOT EXISTS "rb_report_idx" ON "report_blocks" (
	"report_id"
);
DROP INDEX IF EXISTS "rb_author_idx";
CREATE INDEX IF NOT EXISTS "rb_author_idx" ON "report_blocks" (
	"author"
);
DROP INDEX IF EXISTS "rbo_sort_idx";
CREATE INDEX IF NOT EXISTS "rbo_sort_idx" ON "report_block_order" (
	"sort_index"
);
DROP INDEX IF EXISTS "ra_block_idx";
CREATE INDEX IF NOT EXISTS "ra_block_idx" ON "report_anchors" (
	"block_id"
);
DROP INDEX IF EXISTS "ra_ann_idx";
CREATE INDEX IF NOT EXISTS "ra_ann_idx" ON "report_anchors" (
	"annotation_id"
);
DROP INDEX IF EXISTS "ra_block_ann_uniq";
CREATE UNIQUE INDEX IF NOT EXISTS "ra_block_ann_uniq" ON "report_anchors" (
	"block_id",
	"annotation_id"
);
DROP INDEX IF EXISTS "rc_block_idx";
CREATE INDEX IF NOT EXISTS "rc_block_idx" ON "report_comments" (
	"block_id"
);
DROP INDEX IF EXISTS "rc_status_idx";
CREATE INDEX IF NOT EXISTS "rc_status_idx" ON "report_comments" (
	"status"
);
DROP INDEX IF EXISTS "rap_report_idx";
CREATE INDEX IF NOT EXISTS "rap_report_idx" ON "report_approvals" (
	"report_id"
);
DROP INDEX IF EXISTS "reports_one_final_idx";
CREATE UNIQUE INDEX IF NOT EXISTS "reports_one_final_idx" ON "reports" (
	"report_type"
) WHERE "report_type" = 'final';
DROP INDEX IF EXISTS "ia_term_idx";
CREATE INDEX IF NOT EXISTS "ia_term_idx" ON "investigator_aliases" (
	"term"
);
DROP INDEX IF EXISTS "ann_local_id_idx";
CREATE INDEX IF NOT EXISTS "ann_local_id_idx" ON "annotations" (
	"local_id"
) WHERE "local_id" IS NOT NULL;
DROP INDEX IF EXISTS "ann_active_url_idx";
CREATE INDEX IF NOT EXISTS "ann_active_url_idx" ON "annotations" (
	"page_url"
) WHERE "deleted_at" IS NULL;
DROP INDEX IF EXISTS "ann_prev_id_idx";
CREATE INDEX IF NOT EXISTS "ann_prev_id_idx" ON "annotations" (
	"prev_id"
) WHERE "prev_id" IS NOT NULL;
COMMIT;

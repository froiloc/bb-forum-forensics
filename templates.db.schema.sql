BEGIN TRANSACTION;
DROP TABLE IF EXISTS "report_modules";
CREATE TABLE IF NOT EXISTS "report_modules" (
	"id"	INTEGER,
	"title"	TEXT NOT NULL,
	"description"	TEXT,
	"role"	TEXT NOT NULL CHECK("role" IN ('intro', 'conclusion', 'body', 'legal', 'appendix', 'closing')),
	"topic"	TEXT NOT NULL,
	"body"	TEXT NOT NULL,
	"sort_order"	INTEGER NOT NULL DEFAULT 0,
	"is_active"	INTEGER NOT NULL DEFAULT 1,
	"created_by"	TEXT NOT NULL,
	"created_at"	INTEGER NOT NULL,
	"updated_at"	INTEGER NOT NULL,
	"module_key"	TEXT,
	-- Build 655 (Ticket 5d81a0c7): Blocktyp und Blockdaten. Additiv
	-- nachgeruestet durch management/migrate_templates_blocktyp.py.
	-- block_data IS NULL bedeutet ausdruecklich "Bestandszeile, der Inhalt
	-- steht in body" - deshalb kein Backfill und kein veraendertes
	-- updated_at. Der CHECK ist eine Entscheidung mit Preis: SQLite kann
	-- ihn nicht aendern, ein siebter Blocktyp braucht einen Tabellen-Neubau.
	"block_type"	TEXT NOT NULL DEFAULT 'paragraph' CHECK("block_type" IN ('paragraph', 'header', 'list', 'table', 'quote', 'delimiter')),
	"block_data"	TEXT,
	PRIMARY KEY("id" AUTOINCREMENT)
);
DROP TABLE IF EXISTS "placeholders";
-- Build 489 (Platzhalter-Neuordnung): einheitliche Tabelle fuer ALLE drei
-- Platzhalter-Typen (a=automatisch, m=verpflichtend, o=optional) inkl.
-- Validierung (validation im KLARTEXT UTF-8; 'list' = JSON-Array).
-- Migration aus placeholder_queries: management/migrate_templates_placeholders.py.
CREATE TABLE IF NOT EXISTS "placeholders" (
	"id"	TEXT NOT NULL,
	"title"	TEXT NOT NULL,
	"description"	TEXT NOT NULL DEFAULT '',
	"type"	TEXT NOT NULL CHECK("type" IN ('a', 'm', 'o')),
	"sql_query"	TEXT,
	"default_value"	TEXT,
	"validation"	TEXT,
	"validation_type"	TEXT CHECK("validation_type" IN ('regex', 'list', 'like')),
	"tags"	TEXT,
	"return_type"	TEXT NOT NULL DEFAULT 'scalar' CHECK("return_type" IN ('scalar', 'list', 'table')),
	"is_active"	INTEGER NOT NULL DEFAULT 1,
	"created_by"	TEXT NOT NULL,
	"created_at"	INTEGER NOT NULL,
	"updated_at"	INTEGER NOT NULL,
	PRIMARY KEY("id"),
	CHECK("type" <> 'a' OR "sql_query" IS NOT NULL),
	CHECK("type" <> 'a' OR "validation" IS NULL),
	CHECK(("validation" IS NULL) = ("validation_type" IS NULL)),
	CHECK("type" = 'a' OR "sql_query" IS NULL OR "return_type" = 'scalar')
);
DROP TABLE IF EXISTS "templates_audit_log";
CREATE TABLE IF NOT EXISTS "templates_audit_log" (
	"id"	INTEGER,
	"action"	TEXT NOT NULL,
	"target_id"	TEXT NOT NULL,
	"target_type"	TEXT NOT NULL CHECK("target_type" IN ('module', 'query', 'template', 'placeholder')),
	"changed_by"	TEXT NOT NULL,
	"changed_at"	INTEGER NOT NULL,
	"old_value"	TEXT,
	"new_value"	TEXT,
	PRIMARY KEY("id" AUTOINCREMENT)
);
DROP TABLE IF EXISTS "report_templates";
CREATE TABLE IF NOT EXISTS "report_templates" (
	"id"	INTEGER,
	"template_key"	TEXT NOT NULL,
	"title"	TEXT NOT NULL,
	"description"	TEXT,
	"report_type"	TEXT NOT NULL CHECK("report_type" IN ('interim', 'final', 'addendum')),
	"blocks_json"	TEXT NOT NULL,
	"sort_order"	INTEGER NOT NULL DEFAULT 0,
	"is_active"	INTEGER NOT NULL DEFAULT 1,
	"created_by"	TEXT NOT NULL,
	"created_at"	INTEGER NOT NULL,
	"updated_at"	INTEGER NOT NULL,
	PRIMARY KEY("id" AUTOINCREMENT)
);
DROP INDEX IF EXISTS "rm_role_idx";
CREATE INDEX IF NOT EXISTS "rm_role_idx" ON "report_modules" (
	"role",
	"sort_order"
);
DROP INDEX IF EXISTS "rm_topic_idx";
CREATE INDEX IF NOT EXISTS "rm_topic_idx" ON "report_modules" (
	"topic",
	"sort_order"
);
DROP INDEX IF EXISTS "rm_active_idx";
CREATE INDEX IF NOT EXISTS "rm_active_idx" ON "report_modules" (
	"is_active"
);
DROP INDEX IF EXISTS "ph_type_idx";
CREATE INDEX IF NOT EXISTS "ph_type_idx" ON "placeholders" (
	"type",
	"is_active"
);
DROP INDEX IF EXISTS "ph_tags_idx";
CREATE INDEX IF NOT EXISTS "ph_tags_idx" ON "placeholders" (
	"tags"
);
DROP INDEX IF EXISTS "rt_key_idx";
CREATE UNIQUE INDEX IF NOT EXISTS "rt_key_idx" ON "report_templates" (
	"template_key"
);
DROP INDEX IF EXISTS "rt_active_idx";
CREATE INDEX IF NOT EXISTS "rt_active_idx" ON "report_templates" (
	"is_active",
	"sort_order"
);
DROP INDEX IF EXISTS "ux_report_modules_key";
CREATE UNIQUE INDEX IF NOT EXISTS "ux_report_modules_key" ON "report_modules" (
	"module_key"
) WHERE "module_key" IS NOT NULL;
COMMIT;

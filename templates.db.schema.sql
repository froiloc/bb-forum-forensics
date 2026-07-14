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
	PRIMARY KEY("id" AUTOINCREMENT)
);
DROP TABLE IF EXISTS "placeholder_queries";
CREATE TABLE IF NOT EXISTS "placeholder_queries" (
	"id"	TEXT NOT NULL,
	"title"	TEXT NOT NULL,
	"description"	TEXT NOT NULL,
	"sql_query"	TEXT NOT NULL,
	"tags"	TEXT,
	"return_type"	TEXT NOT NULL CHECK("return_type" IN ('scalar', 'list', 'table')),
	"is_active"	INTEGER NOT NULL DEFAULT 1,
	"created_by"	TEXT NOT NULL,
	"created_at"	INTEGER NOT NULL,
	"updated_at"	INTEGER NOT NULL,
	PRIMARY KEY("id")
);
DROP TABLE IF EXISTS "templates_audit_log";
CREATE TABLE IF NOT EXISTS "templates_audit_log" (
	"id"	INTEGER,
	"action"	TEXT NOT NULL,
	"target_id"	TEXT NOT NULL,
	"target_type"	TEXT NOT NULL CHECK("target_type" IN ('module', 'query')),
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
DROP INDEX IF EXISTS "pq_tags_idx";
CREATE INDEX IF NOT EXISTS "pq_tags_idx" ON "placeholder_queries" (
	"tags"
);
DROP INDEX IF EXISTS "pq_active_idx";
CREATE INDEX IF NOT EXISTS "pq_active_idx" ON "placeholder_queries" (
	"is_active"
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

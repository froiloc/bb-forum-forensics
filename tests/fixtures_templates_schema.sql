CREATE TABLE IF NOT EXISTS "report_modules" (
	"id" INTEGER, "title" TEXT NOT NULL, "description" TEXT,
	"role" TEXT NOT NULL CHECK("role" IN ('intro','conclusion','body','legal','appendix','closing')),
	"topic" TEXT NOT NULL, "body" TEXT NOT NULL,
	"sort_order" INTEGER NOT NULL DEFAULT 0, "is_active" INTEGER NOT NULL DEFAULT 1,
	"created_by" TEXT NOT NULL, "created_at" INTEGER NOT NULL, "updated_at" INTEGER NOT NULL,
	"module_key" TEXT,
	"block_type" TEXT NOT NULL DEFAULT 'paragraph' CHECK("block_type" IN ('paragraph', 'header', 'list', 'table', 'quote', 'delimiter')),
	"block_data" TEXT, PRIMARY KEY("id" AUTOINCREMENT));
CREATE TABLE IF NOT EXISTS "report_templates" (
	"id" INTEGER, "template_key" TEXT NOT NULL, "title" TEXT NOT NULL, "description" TEXT,
	"report_type" TEXT NOT NULL CHECK("report_type" IN ('interim','final','addendum')),
	"blocks_json" TEXT NOT NULL, "sort_order" INTEGER NOT NULL DEFAULT 0,
	"is_active" INTEGER NOT NULL DEFAULT 1, "created_by" TEXT NOT NULL,
	"created_at" INTEGER NOT NULL, "updated_at" INTEGER NOT NULL,
	PRIMARY KEY("id" AUTOINCREMENT));
CREATE TABLE IF NOT EXISTS "placeholders" (
	"id" TEXT NOT NULL, "title" TEXT NOT NULL, "description" TEXT NOT NULL DEFAULT '',
	"type" TEXT NOT NULL CHECK("type" IN ('a','m','o')), "sql_query" TEXT,
	"default_value" TEXT, "validation" TEXT,
	"validation_type" TEXT CHECK("validation_type" IN ('regex','list','like')),
	"tags" TEXT,
	"return_type" TEXT NOT NULL DEFAULT 'scalar' CHECK("return_type" IN ('scalar','list','table')),
	"is_active" INTEGER NOT NULL DEFAULT 1, "created_by" TEXT NOT NULL,
	"created_at" INTEGER NOT NULL, "updated_at" INTEGER NOT NULL,
	"validation_ci" INTEGER NOT NULL DEFAULT 0,
	CHECK("type" = 'a' OR "sql_query" IS NULL OR "return_type" = 'scalar'),
	PRIMARY KEY("id"),
	CHECK(("validation" IS NULL) = ("validation_type" IS NULL)),
	CHECK("type" <> 'a' OR "sql_query" IS NOT NULL),
	CHECK("type" <> 'a' OR "validation" IS NULL));
CREATE TABLE IF NOT EXISTS "templates_audit_log" (
	"id" INTEGER, "action" TEXT NOT NULL, "target_id" TEXT NOT NULL,
	"target_type" TEXT NOT NULL CHECK("target_type" IN ('module','query','template','placeholder')),
	"changed_by" TEXT NOT NULL, "changed_at" INTEGER NOT NULL,
	"old_value" TEXT, "new_value" TEXT, PRIMARY KEY("id" AUTOINCREMENT));
CREATE INDEX IF NOT EXISTS "rm_role_idx" ON "report_modules" ("role","sort_order");
CREATE INDEX IF NOT EXISTS "rm_topic_idx" ON "report_modules" ("topic","sort_order");
CREATE INDEX IF NOT EXISTS "rm_active_idx" ON "report_modules" ("is_active");
CREATE UNIQUE INDEX IF NOT EXISTS "rt_key_idx" ON "report_templates" ("template_key");
CREATE INDEX IF NOT EXISTS "rt_active_idx" ON "report_templates" ("is_active","sort_order");
CREATE UNIQUE INDEX IF NOT EXISTS "ux_report_modules_key" ON "report_modules" ("module_key") WHERE "module_key" IS NOT NULL;
CREATE INDEX IF NOT EXISTS "ph_type_idx" ON "placeholders" ("type","is_active");
CREATE INDEX IF NOT EXISTS "ph_tags_idx" ON "placeholders" ("tags");
INSERT INTO report_modules (title,role,topic,body,created_by,created_at,updated_at,module_key)
 VALUES ('Einleitung','intro','Start','Hallo {{a:username}}','seed',1,1,'intro.start');
INSERT INTO report_templates (template_key,title,report_type,blocks_json,created_by,created_at,updated_at)
 VALUES ('std','Standardbericht','final','[]','seed',1,1);
INSERT INTO placeholders (id,title,type,sql_query,return_type,created_by,created_at,updated_at)
 VALUES ('username','Benutzername','a','SELECT username FROM users','scalar','seed',1,1);

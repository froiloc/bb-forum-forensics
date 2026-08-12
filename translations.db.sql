BEGIN TRANSACTION;
DROP TABLE IF EXISTS "translations";
CREATE TABLE IF NOT EXISTS "translations" (
	"post_id"	INTEGER NOT NULL,
	"translated_text"	TEXT,
	"model_used"	TEXT,
	"created_at"	TEXT DEFAULT (datetime('now')),
	"updated_at"	TEXT DEFAULT (datetime('now')),
	"source"	TEXT NOT NULL DEFAULT 'posts',
	"topic_id"	INTEGER,
	"forum_id"	INTEGER,
	PRIMARY KEY("post_id","source")
);
DROP TABLE IF EXISTS "posts_cleaned";
CREATE TABLE IF NOT EXISTS "posts_cleaned" (
	"post_id"	INTEGER NOT NULL,
	"topic_id"	INTEGER NOT NULL,
	"forum_id"	INTEGER NOT NULL,
	"clean_text"	TEXT NOT NULL,
	"word_count"	INTEGER DEFAULT 0,
	"source_lang"	TEXT DEFAULT 'en',
	"source"	TEXT NOT NULL DEFAULT 'posts',
	PRIMARY KEY("post_id","source")
);
DROP INDEX IF EXISTS "idx_translations_topic_source";
CREATE INDEX IF NOT EXISTS "idx_translations_topic_source" ON "translations" (
	"topic_id",
	"source"
);
DROP INDEX IF EXISTS "idx_translations_source";
CREATE INDEX IF NOT EXISTS "idx_translations_source" ON "translations" (
	"source"
);
DROP INDEX IF EXISTS "idx_translations_forum_id";
CREATE INDEX IF NOT EXISTS "idx_translations_forum_id" ON "translations" (
	"forum_id"
);
DROP INDEX IF EXISTS "idx_posts_cleaned_post_source";
CREATE UNIQUE INDEX IF NOT EXISTS "idx_posts_cleaned_post_source" ON "posts_cleaned" (
	"post_id",
	"source"
);
DROP INDEX IF EXISTS "idx_posts_cleaned_topic_id";
CREATE INDEX IF NOT EXISTS "idx_posts_cleaned_topic_id" ON "posts_cleaned" (
	"topic_id"
);
DROP INDEX IF EXISTS "idx_posts_cleaned_forum_id";
CREATE INDEX IF NOT EXISTS "idx_posts_cleaned_forum_id" ON "posts_cleaned" (
	"forum_id"
);
COMMIT;

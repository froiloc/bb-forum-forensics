BEGIN TRANSACTION;
DROP TABLE IF EXISTS "assets_meta";
CREATE TABLE IF NOT EXISTS "assets_meta" (
	"key"	TEXT NOT NULL,
	"value"	TEXT,
	PRIMARY KEY("key")
);
DROP TABLE IF EXISTS "assets";
CREATE TABLE IF NOT EXISTS "assets" (
	"id"	INTEGER,
	"content_hash"	TEXT NOT NULL UNIQUE,
	"data"	BLOB,
	"mime_type"	TEXT,
	"file_size"	INTEGER,
	"source_note"	TEXT NOT NULL,
	PRIMARY KEY("id" AUTOINCREMENT)
);
DROP TABLE IF EXISTS "asset_urls";
CREATE TABLE IF NOT EXISTS "asset_urls" (
	"url"	TEXT NOT NULL,
	"asset_id"	INTEGER NOT NULL,
	"url_context"	TEXT NOT NULL,
	"page_id"	INTEGER,
	"url_hash"	TEXT NOT NULL,
	PRIMARY KEY("url"),
	FOREIGN KEY("asset_id") REFERENCES "assets"("id")
);
DROP INDEX IF EXISTS "assets_hash_idx";
CREATE INDEX IF NOT EXISTS "assets_hash_idx" ON "assets" (
	"content_hash"
);
DROP INDEX IF EXISTS "au_asset_idx";
CREATE INDEX IF NOT EXISTS "au_asset_idx" ON "asset_urls" (
	"asset_id"
);
DROP INDEX IF EXISTS "au_context_idx";
CREATE INDEX IF NOT EXISTS "au_context_idx" ON "asset_urls" (
	"url_context"
);
DROP INDEX IF EXISTS "au_hash_idx";
CREATE INDEX IF NOT EXISTS "au_hash_idx" ON "asset_urls" (
	"url_hash"
);
COMMIT;

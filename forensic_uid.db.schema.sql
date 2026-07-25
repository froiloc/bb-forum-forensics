BEGIN TRANSACTION;
DROP TABLE IF EXISTS "forensic_meta";
CREATE TABLE IF NOT EXISTS "forensic_meta" (
	"key"	TEXT NOT NULL,
	"value"	TEXT,
	PRIMARY KEY("key")
);
DROP TABLE IF EXISTS "pages";
CREATE TABLE IF NOT EXISTS "pages" (
	"id"	INTEGER,
	"url_canonical"	TEXT NOT NULL,
	"html"	BLOB,
	"title"	TEXT,
	"fetched_at"	INTEGER NOT NULL,
	"http_status"	INTEGER NOT NULL,
	"scrape_context"	TEXT NOT NULL DEFAULT 'user',
	"method"	TEXT NOT NULL DEFAULT 'GET',
	UNIQUE("url_canonical","method"),
	PRIMARY KEY("id" AUTOINCREMENT)
);
DROP TABLE IF EXISTS "page_aliases";
CREATE TABLE IF NOT EXISTS "page_aliases" (
	"url_raw"	TEXT NOT NULL,
	"page_id"	INTEGER NOT NULL,
	PRIMARY KEY("url_raw"),
	FOREIGN KEY("page_id") REFERENCES "pages"("id")
);
DROP TABLE IF EXISTS "post_aliases";
CREATE TABLE IF NOT EXISTS "post_aliases" (
	"post_id"	INTEGER NOT NULL,
	"topic_id"	INTEGER NOT NULL,
	"forum_id"	INTEGER NOT NULL,
	"page"	INTEGER,
	"page_resolved"	INTEGER NOT NULL DEFAULT 0,
	PRIMARY KEY("post_id")
);
DROP TABLE IF EXISTS "pm_aliases";
CREATE TABLE IF NOT EXISTS "pm_aliases" (
	"pm_post_id"	INTEGER NOT NULL,
	"pm_topic_id"	INTEGER NOT NULL,
	PRIMARY KEY("pm_post_id")
);
DROP TABLE IF EXISTS "notify_aliases";
CREATE TABLE IF NOT EXISTS "notify_aliases" (
	"notify_id"	INTEGER NOT NULL,
	"post_id"	INTEGER NOT NULL,
	PRIMARY KEY("notify_id")
);
DROP TABLE IF EXISTS "scrape_targets";
CREATE TABLE IF NOT EXISTS "scrape_targets" (
	"id"	INTEGER,
	"scrape_context"	TEXT NOT NULL,
	"url_type"	TEXT NOT NULL,
	"forum_id"	INTEGER,
	"topic_id"	INTEGER,
	"post_id"	INTEGER,
	"pm_topic_id"	INTEGER,
	"pm_post_id"	INTEGER,
	"thanks_post_id"	INTEGER,
	"poll_topic_id"	INTEGER,
	"actor_user_id"	INTEGER,
	"actor_username"	TEXT,
	"static_url"	TEXT,
	"source_tables"	TEXT NOT NULL,
	PRIMARY KEY("id")
);
DROP TABLE IF EXISTS "uid_profile";
CREATE TABLE IF NOT EXISTS "uid_profile" (
	"id"	INTEGER,
	"username"	TEXT NOT NULL,
	"email"	TEXT,
	"group_id"	INTEGER,
	"title"	TEXT,
	"url"	TEXT,
	"badge"	TEXT,
	"pgp"	INTEGER,
	"aoa"	TEXT,
	"pwd"	TEXT,
	"pwd_old"	TEXT,
	"invisible"	INTEGER,
	"suspicious"	INTEGER,
	"signature"	TEXT,
	"signature_html"	TEXT,
	"language"	TEXT,
	"num_posts"	INTEGER,
	"num_topics"	INTEGER,
	"num_share"	INTEGER,
	"dl_num"	INTEGER,
	"reputation"	INTEGER,
	"warning_flag"	INTEGER,
	"warning_all"	INTEGER,
	"ignore_list"	TEXT,
	"follow"	TEXT,
	"registered"	INTEGER,
	"last_active"	INTEGER,
	"last_visit"	INTEGER,
	"admin_note"	TEXT,
	"messages_new"	INTEGER,
	"messages_all"	INTEGER,
	"invite"	INTEGER,
	"donatedTS"	INTEGER,
	"team"	INTEGER,
	"gender"	INTEGER,
	"twofa"	INTEGER,
	"language_primary_code"	TEXT,
	"language_primary_confidence"	REAL,
	"language_secondary_code"	TEXT,
	"language_secondary_confidence"	REAL,
	"exported_at"	INTEGER NOT NULL,
	"badge_names"	TEXT,
	"badge_details_json"	TEXT,
	"ignore_usernames"	TEXT,
	"group_details_json"	TEXT,
	PRIMARY KEY("id")
);
DROP TABLE IF EXISTS "uid_pgp";
CREATE TABLE IF NOT EXISTS "uid_pgp" (
	"user_id"	INTEGER,
	"key_text"	TEXT NOT NULL,
	"is_pem"	INTEGER NOT NULL,
	"language_primary_code"	TEXT,
	"language_primary_confidence"	REAL,
	PRIMARY KEY("user_id")
);
DROP TABLE IF EXISTS "uid_aliases";
CREATE TABLE IF NOT EXISTS "uid_aliases" (
	"id"	INTEGER,
	"user_id"	INTEGER NOT NULL,
	"current_username"	TEXT NOT NULL,
	"historical_username"	TEXT NOT NULL,
	"source_table"	TEXT NOT NULL,
	"source_field"	TEXT NOT NULL,
	"source_id"	INTEGER,
	"not_before_ts"	INTEGER,
	"at_ts"	INTEGER,
	"not_after_ts"	INTEGER,
	"notes"	TEXT,
	"source_url"	TEXT,
	PRIMARY KEY("id" AUTOINCREMENT)
);
DROP TABLE IF EXISTS "uid_bans";
CREATE TABLE IF NOT EXISTS "uid_bans" (
	"id"	INTEGER,
	"username"	TEXT,
	"user_id"	INTEGER NOT NULL,
	"reason"	INTEGER NOT NULL,
	"message"	TEXT,
	"expire"	INTEGER,
	"ban_creator"	INTEGER,
	PRIMARY KEY("id")
);
DROP TABLE IF EXISTS "uid_promotions";
CREATE TABLE IF NOT EXISTS "uid_promotions" (
	"id"	INTEGER,
	"user_id"	INTEGER NOT NULL,
	"promoted_to"	INTEGER NOT NULL,
	"time_ts"	INTEGER,
	PRIMARY KEY("id")
);
DROP TABLE IF EXISTS "uid_logs_group_id";
CREATE TABLE IF NOT EXISTS "uid_logs_group_id" (
	"id"	INTEGER,
	"user_id"	INTEGER NOT NULL,
	"old_id"	INTEGER,
	"new_id"	INTEGER,
	"time_ts"	INTEGER,
	PRIMARY KEY("id" AUTOINCREMENT)
);
DROP TABLE IF EXISTS "uid_logs_edit";
CREATE TABLE IF NOT EXISTS "uid_logs_edit" (
	"id"	INTEGER,
	"pid"	INTEGER NOT NULL,
	"uid"	INTEGER NOT NULL,
	"editby"	TEXT,
	"likes"	INTEGER NOT NULL DEFAULT 0,
	"time_ts"	INTEGER NOT NULL,
	"diff"	INTEGER NOT NULL DEFAULT 0,
	"res"	INTEGER NOT NULL DEFAULT 0,
	"ack"	INTEGER DEFAULT 0,
	PRIMARY KEY("id")
);
DROP TABLE IF EXISTS "uid_logins";
CREATE TABLE IF NOT EXISTS "uid_logins" (
	"id"	INTEGER,
	"username"	TEXT NOT NULL,
	"logged_at"	INTEGER,
	"login_success"	INTEGER,
	PRIMARY KEY("id")
);
DROP TABLE IF EXISTS "uid_invites";
CREATE TABLE IF NOT EXISTS "uid_invites" (
	"id"	INTEGER,
	"user_id"	INTEGER NOT NULL,
	"time_ts"	INTEGER NOT NULL,
	"code"	TEXT NOT NULL,
	"is_used"	INTEGER NOT NULL DEFAULT 0,
	PRIMARY KEY("id")
);
DROP TABLE IF EXISTS "uid_topic_subs";
CREATE TABLE IF NOT EXISTS "uid_topic_subs" (
	"topic_id"	INTEGER,
	"topic_subject"	TEXT,
	"own_posts_in_topic"	INTEGER,
	PRIMARY KEY("topic_id")
);
DROP TABLE IF EXISTS "uid_forum_subs";
CREATE TABLE IF NOT EXISTS "uid_forum_subs" (
	"forum_id"	INTEGER,
	PRIMARY KEY("forum_id")
);
DROP TABLE IF EXISTS "uid_poll_votes";
CREATE TABLE IF NOT EXISTS "uid_poll_votes" (
	"topic_id"	INTEGER,
	"rez"	TEXT,
	"topic_subject"	TEXT,
	"poll_time_ts"	INTEGER,
	"poll_choices_json"	TEXT,
	PRIMARY KEY("topic_id")
);
DROP TABLE IF EXISTS "uid_surveillance";
CREATE TABLE IF NOT EXISTS "uid_surveillance" (
	"id"	INTEGER,
	"username"	TEXT NOT NULL,
	"password"	TEXT,
	"logged_at"	INTEGER,
	"login_success"	INTEGER,
	"import_note"	TEXT,
	PRIMARY KEY("id" AUTOINCREMENT)
);
DROP TABLE IF EXISTS "uid_thanks_given";
CREATE TABLE IF NOT EXISTS "uid_thanks_given" (
	"id"	INTEGER,
	"post_id"	INTEGER NOT NULL,
	"topic_id"	INTEGER,
	"source"	TEXT NOT NULL,
	"not_before_ts"	INTEGER,
	"at_ts"	INTEGER,
	PRIMARY KEY("id")
);
DROP TABLE IF EXISTS "uid_thanks_received";
CREATE TABLE IF NOT EXISTS "uid_thanks_received" (
	"post_id"	INTEGER,
	"topic_id"	INTEGER,
	"thanks_by"	INTEGER,
	"amount"	INTEGER DEFAULT 1,
	"at_ts"	INTEGER,
	PRIMARY KEY("post_id")
);
DROP TABLE IF EXISTS "uid_warnings";
CREATE TABLE IF NOT EXISTS "uid_warnings" (
	"id"	INTEGER,
	"posted"	INTEGER NOT NULL,
	"message"	TEXT,
	PRIMARY KEY("id")
);
DROP TABLE IF EXISTS "uid_reports_filed";
CREATE TABLE IF NOT EXISTS "uid_reports_filed" (
	"id"	INTEGER,
	"post_id"	INTEGER NOT NULL,
	"topic_id"	INTEGER NOT NULL,
	"forum_id"	INTEGER NOT NULL,
	"created"	INTEGER NOT NULL,
	"message"	TEXT,
	PRIMARY KEY("id")
);
DROP TABLE IF EXISTS "uid_reports_modded";
CREATE TABLE IF NOT EXISTS "uid_reports_modded" (
	"id"	INTEGER,
	"post_id"	INTEGER NOT NULL,
	"topic_id"	INTEGER NOT NULL,
	"forum_id"	INTEGER NOT NULL,
	"zapped"	INTEGER,
	"reported_by"	INTEGER,
	PRIMARY KEY("id")
);
DROP TABLE IF EXISTS "uid_downloads";
CREATE TABLE IF NOT EXISTS "uid_downloads" (
	"id"	INTEGER,
	"post_id"	INTEGER NOT NULL,
	"cat_id"	INTEGER NOT NULL,
	"group_id"	INTEGER NOT NULL,
	"time_ts"	INTEGER NOT NULL,
	"post_subject"	TEXT,
	PRIMARY KEY("id")
);
DROP TABLE IF EXISTS "uid_donations";
CREATE TABLE IF NOT EXISTS "uid_donations" (
	"id"	INTEGER,
	"post_id"	INTEGER NOT NULL,
	"topic_id"	INTEGER NOT NULL,
	"topic_subject"	TEXT,
	"posted_ts"	INTEGER NOT NULL,
	"tx_hash"	TEXT,
	"tx_hash_valid"	INTEGER,
	"comment"	TEXT,
	"raw_message"	TEXT NOT NULL,
	PRIMARY KEY("id" AUTOINCREMENT)
);
DROP TABLE IF EXISTS "uid_pn_network";
CREATE TABLE IF NOT EXISTS "uid_pn_network" (
	"id"	INTEGER,
	"partner_user_id"	INTEGER NOT NULL,
	"partner_username"	TEXT,
	"topic_count"	INTEGER NOT NULL DEFAULT 0,
	"msg_sent"	INTEGER NOT NULL DEFAULT 0,
	"msg_received"	INTEGER NOT NULL DEFAULT 0,
	"first_contact_ts"	INTEGER,
	"last_contact_ts"	INTEGER,
	"avg_msg_length_sent"	INTEGER,
	"avg_msg_length_recv"	INTEGER,
	"links_in_sent"	INTEGER NOT NULL DEFAULT 0,
	"links_in_recv"	INTEGER NOT NULL DEFAULT 0,
	"has_cracked"	INTEGER NOT NULL DEFAULT 0,
	PRIMARY KEY("id" AUTOINCREMENT)
);
DROP TABLE IF EXISTS "uid_shares";
CREATE TABLE IF NOT EXISTS "uid_shares" (
	"id"	INTEGER,
	"source_table"	TEXT NOT NULL,
	"source_id"	INTEGER NOT NULL,
	"post_id"	INTEGER NOT NULL,
	"topic_id"	INTEGER,
	"topic_subject"	TEXT,
	"posted_ts"	INTEGER,
	"is_preview"	INTEGER,
	"is_download"	INTEGER,
	"tags"	TEXT,
	"filename"	TEXT,
	"filesize"	INTEGER,
	"filepass"	TEXT,
	"age"	INTEGER,
	"is_enc"	INTEGER,
	"is_sound"	INTEGER,
	PRIMARY KEY("id" AUTOINCREMENT)
);
DROP TABLE IF EXISTS "uid_ignore_list";
CREATE TABLE IF NOT EXISTS "uid_ignore_list" (
	"user_id"	INTEGER NOT NULL,
	"username"	TEXT,
	"account_exists"	INTEGER NOT NULL,
	PRIMARY KEY("user_id")
);
DROP TABLE IF EXISTS "uid_follow_list";
CREATE TABLE IF NOT EXISTS "uid_follow_list" (
	"user_id"	INTEGER NOT NULL,
	"username"	TEXT,
	"account_exists"	INTEGER NOT NULL,
	PRIMARY KEY("user_id")
);
DROP TABLE IF EXISTS "uid_posts";
CREATE TABLE IF NOT EXISTS "uid_posts" (
	"post_id"	INTEGER,
	"topic_id"	INTEGER NOT NULL,
	"forum_id"	INTEGER NOT NULL,
	"posted_ts"	INTEGER,
	"active"	INTEGER NOT NULL DEFAULT 0 CHECK("active" IN (0, 1)),
	"is_topic_starter"	INTEGER NOT NULL DEFAULT 0 CHECK("is_topic_starter" IN (0, 1)),
	PRIMARY KEY("post_id")
);
DROP TABLE IF EXISTS "uid_topics";
CREATE TABLE IF NOT EXISTS "uid_topics" (
	"topic_id"	INTEGER,
	"subject"	TEXT,
	"forum_id"	INTEGER,
	PRIMARY KEY("topic_id")
);
DROP TABLE IF EXISTS "uid_forums";
CREATE TABLE IF NOT EXISTS "uid_forums" (
	"forum_id"	INTEGER,
	"forum_name"	TEXT,
	PRIMARY KEY("forum_id")
);
DROP TABLE IF EXISTS "uid_pms_posts";
CREATE TABLE IF NOT EXISTS "uid_pms_posts" (
	"pm_post_id"	INTEGER,
	"pm_topic_id"	INTEGER NOT NULL,
	"topic_subject"	TEXT,
	"posted_ts"	INTEGER,
	"active"	INTEGER NOT NULL DEFAULT 0 CHECK("active" IN (0, 1)),
	"is_topic_starter"	INTEGER NOT NULL DEFAULT 0 CHECK("is_topic_starter" IN (0, 1)),
	PRIMARY KEY("pm_post_id")
);
DROP TABLE IF EXISTS "uid_posts_word_count";
CREATE TABLE IF NOT EXISTS "uid_posts_word_count" (
	"post_id"	INTEGER,
	"word_count"	INTEGER,
	PRIMARY KEY("post_id")
);
DROP TABLE IF EXISTS "uid_pms_word_count";
CREATE TABLE IF NOT EXISTS "uid_pms_word_count" (
	"post_id"	INTEGER,
	"word_count"	INTEGER,
	PRIMARY KEY("post_id")
);
DROP TABLE IF EXISTS "uid_stats";
CREATE TABLE IF NOT EXISTS "uid_stats" (
	"stat_key"	TEXT NOT NULL,
	"val_reported"	INTEGER,
	"val_computed"	INTEGER,
	"discrepancy"	INTEGER,
	PRIMARY KEY("stat_key")
);
DROP TABLE IF EXISTS "uid_attestations";
CREATE TABLE IF NOT EXISTS "uid_attestations" (
	"id"	INTEGER,
	"source_table"	TEXT NOT NULL,
	"source_field"	TEXT NOT NULL,
	"source_id"	INTEGER,
	"user_id"	INTEGER,
	"username"	TEXT NOT NULL,
	"not_before_ts"	INTEGER,
	"at_ts"	INTEGER,
	"not_after_ts"	INTEGER,
	"heuristic_confidence"	INTEGER,
	"notes"	TEXT,
	"best_ts"	INTEGER,
	PRIMARY KEY("id")
);
DROP TABLE IF EXISTS "uid_surveillance_sharing";
CREATE TABLE IF NOT EXISTS "uid_surveillance_sharing" (
	"id"	INTEGER,
	"shared_password"	TEXT NOT NULL,
	"other_user_id"	INTEGER NOT NULL,
	"other_username"	TEXT,
	"logins_count_other"	INTEGER NOT NULL,
	"first_login_other"	INTEGER,
	"last_login_other"	INTEGER,
	PRIMARY KEY("id" AUTOINCREMENT)
);
DROP TABLE IF EXISTS "uid_timeline_agg";
CREATE TABLE IF NOT EXISTS "uid_timeline_agg" (
	"year"	INTEGER NOT NULL,
	"month"	INTEGER NOT NULL CHECK("month" BETWEEN 1 AND 12),
	"source_table"	TEXT NOT NULL,
	"event_count"	INTEGER NOT NULL DEFAULT 0,
	PRIMARY KEY("year","month","source_table")
);
DROP TABLE IF EXISTS "uid_heatmap";
CREATE TABLE IF NOT EXISTS "uid_heatmap" (
	"weekday"	INTEGER NOT NULL CHECK("weekday" BETWEEN 0 AND 6),
	"hour"	INTEGER NOT NULL CHECK("hour" BETWEEN 0 AND 23),
	"event_count"	INTEGER NOT NULL DEFAULT 0,
	PRIMARY KEY("weekday","hour")
);
DROP TABLE IF EXISTS "static_pages";
CREATE TABLE IF NOT EXISTS "static_pages" (
	"key"	TEXT NOT NULL,
	"html"	BLOB NOT NULL,
	"generated_at"	INTEGER NOT NULL,
	"generator_version"	TEXT NOT NULL,
	PRIMARY KEY("key")
);
DROP INDEX IF EXISTS "pages_url_idx";
CREATE INDEX IF NOT EXISTS "pages_url_idx" ON "pages" (
	"url_canonical"
);
DROP INDEX IF EXISTS "pages_method_idx";
CREATE INDEX IF NOT EXISTS "pages_method_idx" ON "pages" (
	"method"
);
DROP INDEX IF EXISTS "page_aliases_page_id_idx";
CREATE INDEX IF NOT EXISTS "page_aliases_page_id_idx" ON "page_aliases" (
	"page_id"
);
DROP INDEX IF EXISTS "pa_topic_idx";
CREATE INDEX IF NOT EXISTS "pa_topic_idx" ON "post_aliases" (
	"topic_id"
);
DROP INDEX IF EXISTS "na_post_idx";
CREATE INDEX IF NOT EXISTS "na_post_idx" ON "notify_aliases" (
	"post_id"
);
DROP INDEX IF EXISTS "fdb_st_topic_idx";
CREATE INDEX IF NOT EXISTS "fdb_st_topic_idx" ON "scrape_targets" (
	"topic_id"
);
DROP INDEX IF EXISTS "fdb_st_forum_idx";
CREATE INDEX IF NOT EXISTS "fdb_st_forum_idx" ON "scrape_targets" (
	"forum_id"
);
DROP INDEX IF EXISTS "fdb_st_pm_topic_idx";
CREATE INDEX IF NOT EXISTS "fdb_st_pm_topic_idx" ON "scrape_targets" (
	"pm_topic_id"
);
DROP INDEX IF EXISTS "fdb_st_context_idx";
CREATE INDEX IF NOT EXISTS "fdb_st_context_idx" ON "scrape_targets" (
	"scrape_context"
);
DROP INDEX IF EXISTS "fdb_st_actor_idx";
CREATE INDEX IF NOT EXISTS "fdb_st_actor_idx" ON "scrape_targets" (
	"actor_user_id"
);
DROP INDEX IF EXISTS "uid_aliases_hist_idx";
CREATE INDEX IF NOT EXISTS "uid_aliases_hist_idx" ON "uid_aliases" (
	"historical_username"
);
DROP INDEX IF EXISTS "uid_aliases_ts_idx";
CREATE INDEX IF NOT EXISTS "uid_aliases_ts_idx" ON "uid_aliases" (
	"at_ts"
);
DROP INDEX IF EXISTS "uid_lgid_ts_idx";
CREATE INDEX IF NOT EXISTS "uid_lgid_ts_idx" ON "uid_logs_group_id" (
	"time_ts"
);
DROP INDEX IF EXISTS "uid_ledit_pid_idx";
CREATE INDEX IF NOT EXISTS "uid_ledit_pid_idx" ON "uid_logs_edit" (
	"pid"
);
DROP INDEX IF EXISTS "uid_ledit_ts_idx";
CREATE INDEX IF NOT EXISTS "uid_ledit_ts_idx" ON "uid_logs_edit" (
	"time_ts"
);
DROP INDEX IF EXISTS "uid_log_ts_idx";
CREATE INDEX IF NOT EXISTS "uid_log_ts_idx" ON "uid_logins" (
	"logged_at"
);
DROP INDEX IF EXISTS "uid_log_success_idx";
CREATE INDEX IF NOT EXISTS "uid_log_success_idx" ON "uid_logins" (
	"login_success"
);
DROP INDEX IF EXISTS "uid_surv_ts_idx";
CREATE INDEX IF NOT EXISTS "uid_surv_ts_idx" ON "uid_surveillance" (
	"logged_at"
);
DROP INDEX IF EXISTS "uid_surv_success_idx";
CREATE INDEX IF NOT EXISTS "uid_surv_success_idx" ON "uid_surveillance" (
	"login_success"
);
DROP INDEX IF EXISTS "uid_dl_ts_idx";
CREATE INDEX IF NOT EXISTS "uid_dl_ts_idx" ON "uid_downloads" (
	"time_ts"
);
DROP INDEX IF EXISTS "uid_pn_partner_idx";
CREATE INDEX IF NOT EXISTS "uid_pn_partner_idx" ON "uid_pn_network" (
	"partner_user_id"
);
DROP INDEX IF EXISTS "uid_shares_ts_idx";
CREATE INDEX IF NOT EXISTS "uid_shares_ts_idx" ON "uid_shares" (
	"posted_ts"
);
DROP INDEX IF EXISTS "uid_shares_source_idx";
CREATE INDEX IF NOT EXISTS "uid_shares_source_idx" ON "uid_shares" (
	"source_table"
);
DROP INDEX IF EXISTS "uid_posts_topic_idx";
CREATE INDEX IF NOT EXISTS "uid_posts_topic_idx" ON "uid_posts" (
	"topic_id"
);
DROP INDEX IF EXISTS "uid_posts_forum_idx";
CREATE INDEX IF NOT EXISTS "uid_posts_forum_idx" ON "uid_posts" (
	"forum_id"
);
DROP INDEX IF EXISTS "uid_posts_active_idx";
CREATE INDEX IF NOT EXISTS "uid_posts_active_idx" ON "uid_posts" (
	"active"
);
DROP INDEX IF EXISTS "uid_pms_posts_topic_idx";
CREATE INDEX IF NOT EXISTS "uid_pms_posts_topic_idx" ON "uid_pms_posts" (
	"pm_topic_id"
);
DROP INDEX IF EXISTS "uid_pms_posts_active_idx";
CREATE INDEX IF NOT EXISTS "uid_pms_posts_active_idx" ON "uid_pms_posts" (
	"active"
);
DROP INDEX IF EXISTS "uid_att_best_ts_idx";
CREATE INDEX IF NOT EXISTS "uid_att_best_ts_idx" ON "uid_attestations" (
	"best_ts"
);
DROP INDEX IF EXISTS "uid_att_source_idx";
CREATE INDEX IF NOT EXISTS "uid_att_source_idx" ON "uid_attestations" (
	"source_table",
	"source_field"
);
DROP INDEX IF EXISTS "uid_att_heuristic_idx";
CREATE INDEX IF NOT EXISTS "uid_att_heuristic_idx" ON "uid_attestations" (
	"heuristic_confidence"
);
COMMIT;

# =============================================================================
# tests/test_translation_meta.py
# Build 341: Bericht-Datenquelle fuer die Uebersetzungsbehandlung.
#   - TranslationsDb.get_meta (Original-Text + Sprache + Provenienz aus trdb)
#   - TranslationMetaEndpoint (GET /_forensic/translation_meta)
#   - TemplatesDb.get_module_by_key (stabile Kennung, defensiv)
#   - migrate_templates_module_key.apply_migration (idempotent, Seed)
# Beleg: Bauplan Build 340/341 §5.
# =============================================================================

import json
import sqlite3
from unittest.mock import MagicMock

from db.translations_db import TranslationsDb, TranslationMetaRecord
from db.templates_db import TemplatesDb
from forensic_api.translation_meta import TranslationMetaEndpoint
from management.migrate_templates_module_key import apply_migration, MODULE_KEY


# ---- trdb-Fixture (posts_cleaned + translations) ----------------------------

def _make_trdb(path):
    con = sqlite3.connect(str(path))
    con.execute(
        "CREATE TABLE posts_cleaned ("
        "  post_id INTEGER PRIMARY KEY, topic_id INTEGER, forum_id INTEGER, "
        "  topic_title TEXT, poster TEXT, clean_text TEXT NOT NULL, "
        "  word_count INTEGER, source_lang TEXT DEFAULT 'en')"
    )
    con.execute(
        "CREATE TABLE translations ("
        "  post_id INTEGER PRIMARY KEY, translated_text TEXT, model_used TEXT, "
        "  created_at TEXT, source TEXT DEFAULT 'posts')"
    )
    con.execute(
        "INSERT INTO posts_cleaned (post_id, clean_text, source_lang) "
        "VALUES (705985, 'This is the original english post.', 'en')"
    )
    con.execute(
        "INSERT INTO posts_cleaned (post_id, clean_text, source_lang) "
        "VALUES (705990, 'Untranslated original.', 'ru')"  # kein translations-Eintrag
    )
    con.execute(
        "INSERT INTO translations (post_id, translated_text, model_used, created_at, source) "
        "VALUES (705985, 'Deutsche Uebersetzung.', 'ollama/x', '2026-06-20', 'posts')"
    )
    con.commit()
    con.close()


def _open_trdb(path):
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("ATTACH DATABASE ? AS trdb", (str(path),))
    return con


def test_get_meta_original_und_provenienz(tmp_path):
    p = tmp_path / "translations.db"
    _make_trdb(p)
    tdb = TranslationsDb(_open_trdb(p))
    rec = tdb.get_meta(705985)
    assert isinstance(rec, TranslationMetaRecord)
    assert rec.original_text == "This is the original english post."
    assert rec.source_lang == "en"
    assert rec.model_used == "ollama/x"
    assert rec.created_at == "2026-06-20"


def test_get_meta_original_ohne_uebersetzung(tmp_path):
    # Original vorhanden, aber (noch) keine Uebersetzung -> Provenienz None,
    # Original-Text trotzdem da (LEFT JOIN).
    p = tmp_path / "translations.db"
    _make_trdb(p)
    tdb = TranslationsDb(_open_trdb(p))
    rec = tdb.get_meta(705990)
    assert rec is not None
    assert rec.original_text == "Untranslated original."
    assert rec.source_lang == "ru"
    assert rec.model_used is None and rec.created_at is None


def test_get_meta_fehlender_post_ist_none(tmp_path):
    p = tmp_path / "translations.db"
    _make_trdb(p)
    tdb = TranslationsDb(_open_trdb(p))
    assert tdb.get_meta(999999) is None


# ---- Endpoint ---------------------------------------------------------------

def _endpoint_with_meta(rec):
    bundle = MagicMock()
    bundle.translations.get_meta.return_value = rec
    return TranslationMetaEndpoint(bundle, MagicMock(), MagicMock())


def _call(ep, params):
    handler = MagicMock()
    ep.handle(handler, params)
    args = handler.send_response_body.call_args
    code = args.args[0]
    body = json.loads(args.args[1].decode("utf-8"))
    return code, body


def test_endpoint_found():
    rec = TranslationMetaRecord(705985, "orig", "en", "ollama/x", "2026-06-20")
    ep = _endpoint_with_meta(rec)
    code, body = _call(ep, {"post_id": ["705985"]})
    assert code == 200 and body["found"] is True
    assert body["original_text"] == "orig" and body["source_lang"] == "en"
    assert body["model_used"] == "ollama/x"


def test_endpoint_not_found_ist_200_found_false():
    ep = _endpoint_with_meta(None)
    code, body = _call(ep, {"post_id": ["705985"]})
    assert code == 200 and body["found"] is False


def test_endpoint_fehlender_post_id_ist_400():
    ep = _endpoint_with_meta(None)
    code, body = _call(ep, {})
    assert code == 400 and body["status"] == "error"


# ---- templates.db: Migration + get_module_by_key ----------------------------

_REPORT_MODULES_DDL = (
    "CREATE TABLE report_modules ("
    "  id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT, "
    "  role TEXT NOT NULL CHECK(role IN ('intro','conclusion','body','legal','appendix','closing')), "
    "  topic TEXT NOT NULL, body TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0, "
    "  is_active INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL, "
    "  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)"
)


def test_migration_idempotent_und_seed():
    con = sqlite3.connect(":memory:")
    con.execute(_REPORT_MODULES_DDL)
    con.commit()
    # 1. Lauf: Spalte + Index + Seed
    r1 = apply_migration(con)
    assert r1["added_column"] is True and r1["seeded_module"] is True
    # 2. Lauf: nichts Neues (idempotent)
    r2 = apply_migration(con)
    assert r2["added_column"] is False and r2["seeded_module"] is False
    # genau EIN Seed-Eintrag
    n = con.execute(
        "SELECT COUNT(*) FROM report_modules WHERE module_key = ?", (MODULE_KEY,)
    ).fetchone()[0]
    assert n == 1
    row = con.execute(
        "SELECT role, is_active FROM report_modules WHERE module_key = ?", (MODULE_KEY,)
    ).fetchone()
    assert row[0] == "legal" and row[1] == 1


def test_get_module_by_key(tmp_path):
    # templates.db-Datei mit migriertem Schema anlegen
    tpath = tmp_path / "templates.db"
    c = sqlite3.connect(str(tpath))
    c.execute(_REPORT_MODULES_DDL)
    c.execute("CREATE TABLE placeholders (id TEXT PRIMARY KEY, type TEXT NOT NULL DEFAULT 'a')")
    c.commit()
    apply_migration(c)
    c.close()
    # als tdb anbinden
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("ATTACH DATABASE ? AS tdb", (str(tpath),))
    tdb = TemplatesDb(con)
    rec = tdb.get_module_by_key(MODULE_KEY)
    assert rec is not None and rec.role == "legal"
    assert tdb.get_module_by_key("nicht.vorhanden") is None


def test_get_module_by_key_ohne_spalte_ist_none(tmp_path):
    # Schema OHNE module_key (nicht migriert) -> defensiv None, kein Crash
    tpath = tmp_path / "templates_old.db"
    c = sqlite3.connect(str(tpath))
    c.execute(_REPORT_MODULES_DDL)
    c.execute("CREATE TABLE placeholders (id TEXT PRIMARY KEY, type TEXT NOT NULL DEFAULT 'a')")
    c.execute(
        "INSERT INTO report_modules (title, role, topic, body, created_by, created_at, updated_at) "
        "VALUES ('X','legal','T','B','system',0,0)"
    )
    c.commit()
    c.close()
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("ATTACH DATABASE ? AS tdb", (str(tpath),))
    tdb = TemplatesDb(con)
    assert tdb.get_module_by_key(MODULE_KEY) is None


# =============================================================================
# Build 398: get_meta waehlt die Quelltabelle nach source
#   source='posts' -> trdb.posts_cleaned
#   source='pms'   -> trdb.pms_cleaned   (Option B: getrennte Tabellen, weil
#                     Forenpost- und PM-IDs ueberlappende ID-Raeume sind)
# =============================================================================

def _make_trdb_mit_pms(path):
    con = sqlite3.connect(str(path))
    con.execute(
        "CREATE TABLE posts_cleaned ("
        "  post_id INTEGER PRIMARY KEY, clean_text TEXT NOT NULL, source_lang TEXT)"
    )
    con.execute(
        "CREATE TABLE pms_cleaned ("
        "  post_id INTEGER PRIMARY KEY, clean_text TEXT NOT NULL, source_lang TEXT)"
    )
    con.execute(
        "CREATE TABLE translations ("
        "  post_id INTEGER NOT NULL, source TEXT NOT NULL DEFAULT 'posts', "
        "  translated_text TEXT, model_used TEXT, created_at TEXT, "
        "  PRIMARY KEY (post_id, source))"
    )
    # IDENTISCHE post_id 705985 in BEIDEN Quellen -> der kritische Fall
    con.execute("INSERT INTO posts_cleaned VALUES (705985, 'ENGLISH FORUM POST', 'en')")
    con.execute("INSERT INTO pms_cleaned   VALUES (705985, 'ENGLISH PRIVATE MESSAGE', 'ru')")
    con.execute("INSERT INTO translations (post_id, source, translated_text, model_used, created_at) "
                "VALUES (705985, 'posts', 'UEB FORENPOST', 'llama3', '2026-07-01')")
    con.execute("INSERT INTO translations (post_id, source, translated_text, model_used, created_at) "
                "VALUES (705985, 'pms', 'UEB PM', 'llama3-pm', '2026-07-14')")
    con.commit()
    con.close()


def test_get_meta_trennt_post_und_pm_bei_gleicher_id(tmp_path):
    p = tmp_path / "translations.db"
    _make_trdb_mit_pms(p)
    tdb = TranslationsDb(_open_trdb(p))

    post = tdb.get_meta(705985, source="posts")
    pm = tdb.get_meta(705985, source="pms")

    assert post.original_text == "ENGLISH FORUM POST"
    assert post.source_lang == "en"
    assert post.model_used == "llama3"

    assert pm.original_text == "ENGLISH PRIVATE MESSAGE"
    assert pm.source_lang == "ru"
    assert pm.model_used == "llama3-pm"
    assert pm.created_at == "2026-07-14"


def test_get_meta_pms_ohne_pms_cleaned_ist_none(tmp_path):
    # pms_cleaned fehlt (PM-Extraktion noch nicht gelaufen) -> None, kein Absturz
    p = tmp_path / "translations.db"
    _make_trdb(p)  # legt NUR posts_cleaned + translations an
    tdb = TranslationsDb(_open_trdb(p))
    assert tdb.get_meta(705985, source="pms") is None
    # posts funktioniert weiterhin
    assert tdb.get_meta(705985, source="posts") is not None


def test_get_meta_unbekannte_source_ist_none(tmp_path):
    p = tmp_path / "translations.db"
    _make_trdb_mit_pms(p)
    tdb = TranslationsDb(_open_trdb(p))
    assert tdb.get_meta(705985, source="unbekannt") is None

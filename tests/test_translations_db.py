# =============================================================================
# tests/test_translations_db.py
# IT-Forensisches Ermittlungswerkzeug — Tests fuer db/translations_db.py
# =============================================================================
# Beleg: Bauplan Build 329 §6.1; Build 331 (reales Schema ohne status, source-
#        Trennung posts/pms). Reale Produktionstabelle (Projektgespraech
#        2026-07-07): post_id PK, translated_text, model_used, created_at,
#        updated_at, source ('posts'|'pms'), topic_id, forum_id — KEIN status.
# Version: v0.7.331 · Build: 331 · 2026-07-07
# =============================================================================

import sqlite3

from db.translations_db import TranslationsDb, TranslationRecord


# -----------------------------------------------------------------------------
# Hilfsfunktionen: synthetische Referenz-translations.db im REALEN Schema
# -----------------------------------------------------------------------------

def _make_trans_db(path, with_topic_id=True):
    con = sqlite3.connect(str(path))
    if with_topic_id:
        con.execute(
            "CREATE TABLE translations ("
            "  post_id INTEGER PRIMARY KEY, translated_text TEXT, model_used TEXT, "
            "  created_at TEXT DEFAULT (datetime('now')), "
            "  updated_at TEXT DEFAULT (datetime('now')), "
            "  source TEXT DEFAULT 'posts', topic_id INTEGER, forum_id INTEGER)"
        )
        con.executemany(
            "INSERT INTO translations "
            "(post_id, translated_text, model_used, created_at, source, topic_id, forum_id) "
            "VALUES (?,?,?,?,?,?,?)",
            [
                (706037, "Deutsche Uebersetzung A", "ollama/x", "2026-06-20", "posts", 69192, 12),
                (706040, "Deutsche Uebersetzung B", "ollama/x", "2026-06-20", "posts", 69192, 12),
                (706050, "",                          "ollama/x", "2026-06-20", "posts", 69192, 12),  # leer -> raus
                (800001, "anderes Topic",             "ollama/x", "2026-06-20", "posts", 70000, 12),
                # PM mit (kontriviert) gleicher topic_id -> darf bei source='posts' NICHT erscheinen
                (900001, "PM Uebersetzung",           "ollama/x", "2026-06-20", "pms",   69192, None),
            ],
        )
    else:
        # REALES Schema ohne topic_id (Spalten-Robustheit); source vorhanden.
        con.execute(
            "CREATE TABLE translations ("
            "  post_id INTEGER PRIMARY KEY, translated_text TEXT, model_used TEXT, "
            "  created_at TEXT DEFAULT (datetime('now')), source TEXT DEFAULT 'posts')"
        )
        con.execute(
            "INSERT INTO translations (post_id, translated_text, model_used, created_at, source) "
            "VALUES (706037, 'Text', 'ollama/x', '2026-06-20', 'posts')"
        )
    con.commit()
    con.close()


def _open_with_trdb(trans_path):
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("ATTACH DATABASE ? AS trdb", (str(trans_path),))
    return con


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------

def test_list_posts_filtert_leer_fremdtopic_und_pms_aus(tmp_path):
    p = tmp_path / "translations.db"
    _make_trans_db(p)
    tdb = TranslationsDb(_open_with_trdb(p))
    ids = tdb.list_translated_post_ids(69192)  # Default source='posts'
    # leer (706050) + Fremdtopic (800001) + PM (900001) ausgeschlossen
    assert sorted(ids) == [706037, 706040]


def test_list_pms_liefert_nur_pms(tmp_path):
    p = tmp_path / "translations.db"
    _make_trans_db(p)
    tdb = TranslationsDb(_open_with_trdb(p))
    assert tdb.list_translated_post_ids(69192, source="pms") == [900001]


def test_get_translation_gefunden(tmp_path):
    p = tmp_path / "translations.db"
    _make_trans_db(p)
    tdb = TranslationsDb(_open_with_trdb(p))
    rec = tdb.get_translation(706037)
    assert isinstance(rec, TranslationRecord)
    assert rec.post_id == 706037
    assert rec.translated_text == "Deutsche Uebersetzung A"
    assert rec.model_used == "ollama/x"
    assert rec.created_at == "2026-06-20"


def test_get_translation_source_trennung(tmp_path):
    p = tmp_path / "translations.db"
    _make_trans_db(p)
    tdb = TranslationsDb(_open_with_trdb(p))
    # 900001 ist eine PM -> bei Default source='posts' NICHT auffindbar
    assert tdb.get_translation(900001) is None
    # mit source='pms' sehr wohl
    rec = tdb.get_translation(900001, source="pms")
    assert rec is not None and rec.post_id == 900001


def test_get_translation_leer_und_fehlend_ist_none(tmp_path):
    p = tmp_path / "translations.db"
    _make_trans_db(p)
    tdb = TranslationsDb(_open_with_trdb(p))
    assert tdb.get_translation(706050) is None  # leerer Text
    assert tdb.get_translation(999999) is None  # nicht vorhanden


def test_trdb_nicht_angebunden_graceful():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    tdb = TranslationsDb(con)  # KEIN trdb-ATTACH
    assert tdb.list_translated_post_ids(1) == []
    assert tdb.get_translation(1) is None


def test_fehlende_topic_id_spalte_liefert_leer_kein_crash(tmp_path):
    p = tmp_path / "translations.db"
    _make_trans_db(p, with_topic_id=False)
    tdb = TranslationsDb(_open_with_trdb(p))
    assert tdb.list_translated_post_ids(69192) == []   # keine Spalte -> leer, kein Crash
    rec = tdb.get_translation(706037)                  # braucht kein topic_id
    assert rec is not None and rec.post_id == 706037

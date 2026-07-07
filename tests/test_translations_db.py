# =============================================================================
# tests/test_translations_db.py
# IT-Forensisches Ermittlungswerkzeug — Tests fuer db/translations_db.py
# =============================================================================
# Beleg: Bauplan Build 329 §6.1
# Version: v0.7.329 · Build: 329 · 2026-07-07
# =============================================================================

import sqlite3

from db.translations_db import TranslationsDb, TranslationRecord


# -----------------------------------------------------------------------------
# Hilfsfunktionen: synthetische Referenz-translations.db
# -----------------------------------------------------------------------------

def _make_trans_db(path, with_topic_id=True):
    con = sqlite3.connect(str(path))
    if with_topic_id:
        con.execute(
            "CREATE TABLE translations ("
            "  post_id INTEGER PRIMARY KEY, topic_id INTEGER, "
            "  translated_text TEXT, model_used TEXT, "
            "  status TEXT DEFAULT 'pending', created_at TEXT)"
        )
        con.executemany(
            "INSERT INTO translations "
            "(post_id, topic_id, translated_text, model_used, status, created_at) "
            "VALUES (?,?,?,?,?,?)",
            [
                (706037, 69192, "Deutsche Uebersetzung A", "ollama/x", "completed", "2026-06-20"),
                (706040, 69192, "Deutsche Uebersetzung B", "ollama/x", "completed", "2026-06-20"),
                (706050, 69192, "",            "ollama/x", "completed", "2026-06-20"),  # leer -> raus
                (706060, 69192, "noch offen",  "ollama/x", "pending",   "2026-06-20"),  # pending -> raus
                (800001, 70000, "anderes Topic", "ollama/x", "completed", "2026-06-20"),
            ],
        )
    else:
        # Wie oben, aber OHNE topic_id-Spalte (Spalten-Robustheit).
        con.execute(
            "CREATE TABLE translations ("
            "  post_id INTEGER PRIMARY KEY, translated_text TEXT, "
            "  model_used TEXT, status TEXT DEFAULT 'pending', created_at TEXT)"
        )
        con.execute(
            "INSERT INTO translations "
            "(post_id, translated_text, model_used, status, created_at) "
            "VALUES (706037, 'Text', 'ollama/x', 'completed', '2026-06-20')"
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

def test_list_translated_post_ids_filtert_korrekt(tmp_path):
    p = tmp_path / "translations.db"
    _make_trans_db(p)
    tdb = TranslationsDb(_open_with_trdb(p))
    ids = tdb.list_translated_post_ids(69192)
    # leer + pending ausgeschlossen, anderes Topic (70000) nicht enthalten
    assert sorted(ids) == [706037, 706040]


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


def test_get_translation_pending_leer_fehlend_ist_none(tmp_path):
    p = tmp_path / "translations.db"
    _make_trans_db(p)
    tdb = TranslationsDb(_open_with_trdb(p))
    assert tdb.get_translation(706060) is None  # pending
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
    # topic-basierte Liste kann ohne Spalte nicht filtern -> leer, kein Crash
    assert tdb.list_translated_post_ids(69192) == []
    # Einzelabruf braucht kein topic_id -> muss weiterhin funktionieren
    rec = tdb.get_translation(706037)
    assert rec is not None
    assert rec.post_id == 706037

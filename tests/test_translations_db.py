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


# =============================================================================
# Build 703 (Vorgang da84f94f): Uebersetzungen privater Nachrichten
#
# DER AUSGANGSPUNKT: Fuer PN fuellt der Uebersetzungslauf topic_id/forum_id
# NICHT (Datenprobe Alex, 12.08.2026 — source='pms' mit leeren Spalten). Die
# Frage 'welche Nachrichten dieses Dialogs sind uebersetzt?' ist ueber
# translations.topic_id daher gar nicht zu beantworten. Sie wird stattdessen
# gegen eine VORGEGEBENE Menge gestellt, die aus dem forensischen Bestand
# stammt (fdb.pm_aliases).
#
# FT01 — filter_translated_post_ids trennt posts und pms
# FT02 — leere Eingabe -> leere Ausgabe (keine Abfrage)
# FT03 — leerer translated_text zaehlt NICHT als Uebersetzung
# FT04 — mehr als eine Stapelgroesse (SQLite-Parametergrenze)
# FT05 — nicht angebundene trdb -> leer, kein Absturz
# FT06 — get_translation liefert updated_at mit (PN haben kein created_at)
# =============================================================================

def _make_trans_db_pn(path):
    """PN-Bestand wie in der Datenprobe: created_at/topic_id/forum_id leer."""
    con = sqlite3.connect(str(path))
    con.execute(
        "CREATE TABLE translations ("
        "  post_id INTEGER NOT NULL, translated_text TEXT, model_used TEXT, "
        "  created_at TEXT, updated_at TEXT, "
        "  source TEXT NOT NULL DEFAULT 'posts', topic_id INTEGER, "
        "  forum_id INTEGER, PRIMARY KEY(post_id, source))"
    )
    con.executemany(
        "INSERT INTO translations (post_id, translated_text, model_used, "
        "created_at, updated_at, source, topic_id, forum_id) VALUES (?,?,?,?,?,?,?,?)",
        [
            # PN — genau die Gestalt der Datenprobe.
            (44573, "Hallo mein Freund, moegen all deine Wuensche wahr werden.",
             "llama3:8b-instruct-q4_K_M", None, "2026-07-14 02:47:37", "pms", None, None),
            (44574, "Zweite Nachricht", "llama3", None, "2026-07-14 02:48:00",
             "pms", None, None),
            (44575, "", "llama3", None, "2026-07-14 02:49:00", "pms", None, None),
            # Forenbeitrag mit DERSELBEN ID wie eine PN — getrennte ID-Raeume.
            (44573, "Hola Kurzpost!", "llama3", "2026-07-05 23:39:38",
             "2026-07-05 23:39:38", "posts", 20, 29),
        ],
    )
    con.commit()
    con.close()


def test_FT01_filter_trennt_posts_und_pms(tmp_path):
    p = tmp_path / "translations.db"
    _make_trans_db_pn(p)
    tdb = TranslationsDb(_open_with_trdb(p))

    pms = tdb.filter_translated_post_ids([44573, 44574, 44575, 99999], "pms")
    assert sorted(pms) == [44573, 44574]

    # Dieselbe Menge als 'posts' gefragt: nur der Forenbeitrag 44573.
    posts = tdb.filter_translated_post_ids([44573, 44574, 44575], "posts")
    assert posts == [44573]


def test_FT02_leere_eingabe(tmp_path):
    p = tmp_path / "translations.db"
    _make_trans_db_pn(p)
    tdb = TranslationsDb(_open_with_trdb(p))
    assert tdb.filter_translated_post_ids([], "pms") == []


def test_FT03_leerer_text_zaehlt_nicht(tmp_path):
    p = tmp_path / "translations.db"
    _make_trans_db_pn(p)
    tdb = TranslationsDb(_open_with_trdb(p))
    # 44575 hat eine Zeile, aber leeren Text -> keine Uebersetzung.
    assert tdb.filter_translated_post_ids([44575], "pms") == []


def test_FT04_mehr_als_eine_stapelgroesse(tmp_path):
    """FT04: Ein Dialog kann mehrere hundert Nachrichten fuehren (gemessen:
    283 Container auf einer PN-Dialogseite). Die Abfrage wird gestapelt —
    ohne das schlaegt SQLite ab 999 Parametern fehl."""
    p = tmp_path / "translations.db"
    con = sqlite3.connect(str(p))
    con.execute(
        "CREATE TABLE translations ("
        "  post_id INTEGER NOT NULL, translated_text TEXT, model_used TEXT, "
        "  created_at TEXT, updated_at TEXT, source TEXT NOT NULL DEFAULT 'posts', "
        "  topic_id INTEGER, forum_id INTEGER, PRIMARY KEY(post_id, source))"
    )
    con.executemany(
        "INSERT INTO translations (post_id, translated_text, source) VALUES (?,?,?)",
        [(i, "Text", "pms") for i in range(1, 2001, 2)],   # nur ungerade IDs
    )
    con.commit()
    con.close()
    tdb = TranslationsDb(_open_with_trdb(p))

    alle = list(range(1, 2001))            # 2000 IDs -> drei Stapel
    treffer = tdb.filter_translated_post_ids(alle, "pms")
    assert len(treffer) == 1000
    assert all(t % 2 == 1 for t in treffer)


def test_FT05_ohne_trdb_leer():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    tdb = TranslationsDb(con)   # KEIN trdb-ATTACH
    assert tdb.filter_translated_post_ids([1, 2, 3], "pms") == []


def test_FT06_get_translation_liefert_updated_at(tmp_path):
    """FT06: Bei PN ist created_at leer. Ohne updated_at traege die
    Pflichtkopfzeile der Anzeige dort KEIN Datum."""
    p = tmp_path / "translations.db"
    _make_trans_db_pn(p)
    tdb = TranslationsDb(_open_with_trdb(p))

    pn = tdb.get_translation(44573, source="pms")
    assert pn is not None
    assert pn.created_at is None
    assert pn.updated_at == "2026-07-14 02:47:37"

    # Der gleichnamige Forenbeitrag bleibt davon unberuehrt.
    post = tdb.get_translation(44573, source="posts")
    assert post.translated_text == "Hola Kurzpost!"
    assert post.created_at == "2026-07-05 23:39:38"

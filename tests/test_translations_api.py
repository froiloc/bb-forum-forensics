# =============================================================================
# tests/test_translations_api.py
# IT-Forensisches Ermittlungswerkzeug — Tests fuer forensic_api/translations.py
# und forensic_api/translate.py
# =============================================================================
# Beleg: Bauplan Build 329 §6.1, §3.1, §3.2; Build 331 (reales Schema ohne
#        status, optionaler source-Param posts/pms).
# Version: v0.7.331 · Build: 331 · 2026-07-07
# =============================================================================

import json
import sqlite3

from db.translations_db import TranslationsDb
from forensic_api.translations import TranslationsEndpoint
from forensic_api.translate import TranslateEndpoint


class _FakeHandler:
    """Faengt send_response_body(status, body, content_type) ab."""
    def __init__(self):
        self.status = None
        self.body = None
        self.content_type = None

    def send_response_body(self, status, body, content_type=None):
        self.status = status
        self.body = body
        self.content_type = content_type

    def json(self):
        return json.loads(self.body.decode("utf-8"))


class _FakeBundle:
    def __init__(self, translations):
        self.translations = translations


def _real_translations_db(tmp_path):
    p = tmp_path / "translations.db"
    if p.exists():
        p.unlink()  # Helfer kann pro Test mehrfach aufgerufen werden
    con = sqlite3.connect(str(p))
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
            (900001, "PM Uebersetzung",         "ollama/x", "2026-06-20", "pms",   69192, None),
        ],
    )
    con.commit()
    con.close()

    main = sqlite3.connect(":memory:")
    main.row_factory = sqlite3.Row
    main.execute("ATTACH DATABASE ? AS trdb", (str(p),))
    return TranslationsDb(main)


def _translations_ep(tmp_path):
    return TranslationsEndpoint(_FakeBundle(_real_translations_db(tmp_path)), None, None)


def _translate_ep(tmp_path):
    return TranslateEndpoint(_FakeBundle(_real_translations_db(tmp_path)), None, None)


# -----------------------------------------------------------------------------
# /_forensic/translations
# -----------------------------------------------------------------------------

def test_translations_gueltige_topic_id_nur_posts(tmp_path):
    h = _FakeHandler()
    _translations_ep(tmp_path).handle(h, {"topic_id": ["69192"]})
    assert h.status == 200
    data = h.json()
    assert data["status"] == "ok"
    assert data["topic_id"] == 69192
    assert data["source"] == "posts"
    assert sorted(data["post_ids"]) == [706037, 706040]  # PM (900001) NICHT dabei
    assert data["count"] == 2


def test_translations_source_pms(tmp_path):
    h = _FakeHandler()
    _translations_ep(tmp_path).handle(h, {"topic_id": ["69192"], "source": ["pms"]})
    assert h.status == 200
    assert h.json()["post_ids"] == [900001]


def test_translations_ungueltiger_source_400(tmp_path):
    h = _FakeHandler()
    _translations_ep(tmp_path).handle(h, {"topic_id": ["69192"], "source": ["quatsch"]})
    assert h.status == 400


def test_translations_fehlende_topic_id_400(tmp_path):
    h = _FakeHandler()
    _translations_ep(tmp_path).handle(h, {})
    assert h.status == 400
    assert h.json()["status"] == "error"


def test_translations_ungueltige_topic_id_400(tmp_path):
    h = _FakeHandler()
    _translations_ep(tmp_path).handle(h, {"topic_id": ["abc"]})
    assert h.status == 400


# -----------------------------------------------------------------------------
# /_forensic/translate
# -----------------------------------------------------------------------------

def test_translate_gefunden(tmp_path):
    h = _FakeHandler()
    _translate_ep(tmp_path).handle(h, {"post_id": ["706037"]})
    assert h.status == 200
    data = h.json()
    assert data["found"] is True
    assert data["post_id"] == 706037
    assert data["translated_text"] == "Deutsche Uebersetzung A"
    assert data["model_used"] == "ollama/x"
    assert "confidence_markers" not in data
    assert "status" not in data


def test_translate_pms_nur_mit_source(tmp_path):
    # Default source='posts' -> PM 900001 nicht gefunden
    h1 = _FakeHandler()
    _translate_ep(tmp_path).handle(h1, {"post_id": ["900001"]})
    assert h1.status == 200 and h1.json()["found"] is False
    # mit source='pms' -> gefunden
    h2 = _FakeHandler()
    _translate_ep(tmp_path).handle(h2, {"post_id": ["900001"], "source": ["pms"]})
    assert h2.status == 200 and h2.json()["found"] is True


def test_translate_unbekannt_ist_found_false(tmp_path):
    h = _FakeHandler()
    _translate_ep(tmp_path).handle(h, {"post_id": ["999999"]})
    assert h.status == 200
    assert h.json()["found"] is False


def test_translate_ungueltiger_source_400(tmp_path):
    h = _FakeHandler()
    _translate_ep(tmp_path).handle(h, {"post_id": ["706037"], "source": ["quatsch"]})
    assert h.status == 400


def test_translate_fehlender_post_id_400(tmp_path):
    h = _FakeHandler()
    _translate_ep(tmp_path).handle(h, {})
    assert h.status == 400
    assert h.json()["status"] == "error"

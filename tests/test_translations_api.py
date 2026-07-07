# =============================================================================
# tests/test_translations_api.py
# IT-Forensisches Ermittlungswerkzeug — Tests fuer forensic_api/translations.py
# und forensic_api/translate.py
# =============================================================================
# Beleg: Bauplan Build 329 §6.1, §3.1, §3.2
# Version: v0.7.329 · Build: 329 · 2026-07-07
# =============================================================================

import json
import sqlite3

from db.translations_db import TranslationsDb
from forensic_api.translations import TranslationsEndpoint
from forensic_api.translate import TranslateEndpoint


# -----------------------------------------------------------------------------
# Fakes
# -----------------------------------------------------------------------------

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
    con = sqlite3.connect(str(p))
    con.execute(
        "CREATE TABLE translations ("
        "  post_id INTEGER PRIMARY KEY, topic_id INTEGER, translated_text TEXT, "
        "  model_used TEXT, status TEXT DEFAULT 'pending', created_at TEXT)"
    )
    con.executemany(
        "INSERT INTO translations "
        "(post_id, topic_id, translated_text, model_used, status, created_at) "
        "VALUES (?,?,?,?,?,?)",
        [
            (706037, 69192, "Deutsche Uebersetzung A", "ollama/x", "completed", "2026-06-20"),
            (706040, 69192, "Deutsche Uebersetzung B", "ollama/x", "completed", "2026-06-20"),
            (706060, 69192, "offen", "ollama/x", "pending", "2026-06-20"),
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

def test_translations_gueltige_topic_id(tmp_path):
    h = _FakeHandler()
    _translations_ep(tmp_path).handle(h, {"topic_id": ["69192"]})
    assert h.status == 200
    data = h.json()
    assert data["status"] == "ok"
    assert data["topic_id"] == 69192
    assert sorted(data["post_ids"]) == [706037, 706040]  # pending ausgeschlossen
    assert data["count"] == 2


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
    # confidence_markers wird bewusst NICHT geliefert
    assert "confidence_markers" not in data


def test_translate_pending_ist_found_false(tmp_path):
    h = _FakeHandler()
    _translate_ep(tmp_path).handle(h, {"post_id": ["706060"]})
    assert h.status == 200          # 'nicht gefunden' ist KEIN Fehler
    assert h.json()["found"] is False


def test_translate_unbekannt_ist_found_false(tmp_path):
    h = _FakeHandler()
    _translate_ep(tmp_path).handle(h, {"post_id": ["999999"]})
    assert h.status == 200
    assert h.json()["found"] is False


def test_translate_fehlender_post_id_400(tmp_path):
    h = _FakeHandler()
    _translate_ep(tmp_path).handle(h, {})
    assert h.status == 400
    assert h.json()["status"] == "error"

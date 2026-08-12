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


# =============================================================================
# Build 703 (Vorgang da84f94f): /_forensic/translations fuer PN-Dialoge
#
# DER PUNKT: Bei source='pms' ist 'topic_id' die DIALOG-ID (tid aus
# 'pmsnew.php?mdl=topic&tid='). Der Weg ueber trdb.translations.topic_id
# steht dort nicht zur Verfuegung — der Uebersetzungslauf laesst die Spalte
# bei PN leer (Datenprobe Alex, 12.08.2026). Aufgeloest wird ueber
# fdb.pm_aliases (Dialog -> Nachrichten) und erst dann gegen die
# Uebersetzungen geschnitten.
#
# PA01 — PN-Dialog wird ueber pm_aliases aufgeloest, resolved_via sagt das
# PA02 — nur Nachrichten DIESES Dialogs, und nur uebersetzte
# PA03 — Rueckfall auf translations.topic_id, wenn pm_aliases nichts hergibt
# PA04 — unbekannter Dialog -> leere Liste, resolved_via='keiner'
# PA05 — 'posts' bleibt unveraendert beim topic_id-Weg (Regression)
# =============================================================================

class _FakeForensic:
    """ForensicDb-Doppel: nur die hier gebrauchte Dialog-Aufloesung."""
    def __init__(self, dialoge):
        self._dialoge = dialoge          # {pm_topic_id: [pm_post_id, ...]}
        self.gefragt = []

    def list_pm_post_ids(self, pm_topic_id):
        self.gefragt.append(pm_topic_id)
        return list(self._dialoge.get(pm_topic_id, []))


class _FakeBundleMitForensic:
    def __init__(self, translations, forensic):
        self.translations = translations
        self.forensic = forensic


def _pn_translations_db(tmp_path):
    """trdb im gelieferten Aufbau: PN OHNE topic_id (wie in der Datenprobe)."""
    p = tmp_path / "translations_pn.db"
    if p.exists():
        p.unlink()
    con = sqlite3.connect(str(p))
    con.execute(
        "CREATE TABLE translations ("
        "  post_id INTEGER NOT NULL, translated_text TEXT, model_used TEXT, "
        "  created_at TEXT, updated_at TEXT, source TEXT NOT NULL DEFAULT 'posts', "
        "  topic_id INTEGER, forum_id INTEGER, PRIMARY KEY(post_id, source))"
    )
    con.executemany(
        "INSERT INTO translations (post_id, translated_text, model_used, "
        "created_at, updated_at, source, topic_id, forum_id) VALUES (?,?,?,?,?,?,?,?)",
        [
            (44573, "PN eins", "llama3", None, "2026-07-14 02:47:37", "pms", None, None),
            (44574, "PN zwei", "llama3", None, "2026-07-14 02:48:00", "pms", None, None),
            (51000, "PN eines anderen Dialogs", "llama3", None,
             "2026-07-14 02:50:00", "pms", None, None),
            (44573, "Forenbeitrag gleicher ID", "llama3", "2026-07-05", "2026-07-05",
             "posts", 20, 29),
        ],
    )
    con.commit()
    con.close()
    main = sqlite3.connect(":memory:")
    main.row_factory = sqlite3.Row
    main.execute("ATTACH DATABASE ? AS trdb", (str(p),))
    return TranslationsDb(main)


def test_PA01_pn_dialog_ueber_pm_aliases(tmp_path):
    forensic = _FakeForensic({85844: [44573, 44574, 44575]})
    ep = TranslationsEndpoint(
        _FakeBundleMitForensic(_pn_translations_db(tmp_path), forensic), None, None
    )
    h = _FakeHandler()
    ep.handle(h, {"topic_id": ["85844"], "source": ["pms"]})
    assert h.status == 200
    data = h.json()
    assert data["source"] == "pms"
    assert sorted(data["post_ids"]) == [44573, 44574]
    assert data["resolved_via"] == "pm_aliases"
    assert forensic.gefragt == [85844]


def test_PA02_nur_nachrichten_dieses_dialogs(tmp_path):
    # 51000 ist uebersetzt, gehoert aber zu einem ANDEREN Dialog.
    forensic = _FakeForensic({85844: [44573, 44574], 82544: [51000]})
    ep = TranslationsEndpoint(
        _FakeBundleMitForensic(_pn_translations_db(tmp_path), forensic), None, None
    )
    h = _FakeHandler()
    ep.handle(h, {"topic_id": ["85844"], "source": ["pms"]})
    assert 51000 not in h.json()["post_ids"]


def test_PA03_rueckfall_auf_topic_id(tmp_path):
    """PA03: Bestaende, in denen translations.topic_id auch fuer PN gefuellt
    ist, bleiben bedient — der Weg wird aber benannt (GR1)."""
    # pm_aliases kennt den Dialog nicht ...
    forensic = _FakeForensic({})
    # ... dafuer traegt die Uebersetzungs-DB eine topic_id (Aufbau des
    # bisherigen Testbestandes).
    ep = TranslationsEndpoint(
        _FakeBundleMitForensic(_real_translations_db(tmp_path), forensic), None, None
    )
    h = _FakeHandler()
    ep.handle(h, {"topic_id": ["69192"], "source": ["pms"]})
    data = h.json()
    assert data["post_ids"] == [900001]
    assert data["resolved_via"] == "topic_id"


def test_PA04_unbekannter_dialog_ist_leer_und_benannt(tmp_path):
    forensic = _FakeForensic({})
    ep = TranslationsEndpoint(
        _FakeBundleMitForensic(_pn_translations_db(tmp_path), forensic), None, None
    )
    h = _FakeHandler()
    ep.handle(h, {"topic_id": ["999999"], "source": ["pms"]})
    data = h.json()
    assert data["post_ids"] == []
    assert data["count"] == 0
    assert data["resolved_via"] == "keiner"


def test_PA05_posts_bleibt_beim_topic_id_weg(tmp_path):
    """PA05: Regression — Forenbeitraege laufen unveraendert ueber
    translations.topic_id und fragen die ForensicDb gar nicht erst."""
    forensic = _FakeForensic({})
    ep = TranslationsEndpoint(
        _FakeBundleMitForensic(_real_translations_db(tmp_path), forensic), None, None
    )
    h = _FakeHandler()
    ep.handle(h, {"topic_id": ["69192"]})
    data = h.json()
    assert sorted(data["post_ids"]) == [706037, 706040]
    assert data["resolved_via"] == "topic_id"
    assert forensic.gefragt == []

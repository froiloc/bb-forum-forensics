# =============================================================================
# tests/test_build432_pm_content_ts.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Annotationsrecherche
# -----------------------------------------------------------------------------
# Zweck:
#   Testet die PN-Inhaltszeit-Aufloesung (Build 432, E2):
#     - ForensicDb.get_pm_post_times(): fdb.uid_pms_posts(pm_post_id, posted_ts)
#       -> {pm_post_id: sek}, inkl. defensiver Faelle.
#     - annotations._is_pm_url(): erkennt PN-Seiten (pmsnew.php) vs. Forum-Posts.
#
#   Beleg Spalte: uid_pms_posts.posted_ts (Entwicklerangabe 2026-07-15);
#          PN-URL pmsnew.php (db/forensic_db.py:1248).
# =============================================================================

import os
import sqlite3
import tempfile

from db.forensic_db import ForensicDb
from forensic_api.annotations import _is_pm_url, _derive_post_id


class _Rec:
    def __init__(self, post_id=None, element_id=None, page_url=""):
        self.post_id = post_id
        self.element_id = element_id
        self.page_url = page_url


def _make_fdb(with_pms=True):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    con = sqlite3.connect(tmp.name)
    con.executescript(
        """
        CREATE TABLE forensic_meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE pages (
            id INTEGER PRIMARY KEY, url_canonical TEXT, html BLOB,
            fetched_at INTEGER, http_status INTEGER,
            scrape_context TEXT DEFAULT 'user', method TEXT DEFAULT 'GET'
        );
        CREATE TABLE page_aliases (url_raw TEXT PRIMARY KEY, page_id INTEGER);
        -- Build 528: ECHTES Schema (forensic_uid.db.schema.sql).
        CREATE TABLE uid_posts (post_id INTEGER PRIMARY KEY, topic_id INTEGER, forum_id INTEGER, posted_ts INTEGER, active INTEGER DEFAULT 1, is_topic_starter INTEGER DEFAULT 0);
        INSERT INTO uid_posts (post_id, posted_ts) VALUES (12345, 1664000000);
        """
    )
    if with_pms:
        con.executescript(
            """
            CREATE TABLE uid_pms_posts (pm_post_id INTEGER, posted_ts INTEGER);
            INSERT INTO uid_pms_posts VALUES (555, 1690000000), (556, 1690001000), (999, NULL);
            """
        )
    con.commit()
    con.close()
    return tmp.name


def _attached(path):
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute(f"ATTACH DATABASE '{path}' AS fdb")
    con.commit()
    return con


def test_get_pm_post_times_basic():
    """pm_post_id -> posted_ts; unbekannte fehlen; NULL posted_ts raus."""
    path = _make_fdb(with_pms=True)
    try:
        con = _attached(path)
        fdb = ForensicDb(con)
        result = fdb.get_pm_post_times([555, 556, 111, 999])
        assert result == {555: 1690000000, 556: 1690001000}
        con.close()
    finally:
        os.unlink(path)


def test_get_pm_post_times_missing_table_defensive():
    """Fehlt fdb.uid_pms_posts, liefert die Methode {} statt zu brechen (GR1)."""
    path = _make_fdb(with_pms=False)
    try:
        con = _attached(path)
        fdb = ForensicDb(con)
        assert fdb.get_pm_post_times([555]) == {}
        con.close()
    finally:
        os.unlink(path)


def test_get_pm_post_times_empty_input():
    path = _make_fdb(with_pms=True)
    try:
        con = _attached(path)
        fdb = ForensicDb(con)
        assert fdb.get_pm_post_times([]) == {}
        con.close()
    finally:
        os.unlink(path)


def test_is_pm_url():
    assert _is_pm_url("/forum/pmsnew.php?mdl=topic&tid=10") is True
    assert _is_pm_url("/forum/message.php?id=3") is True
    assert _is_pm_url("/forum/viewtopic.php?id=5") is False
    assert _is_pm_url("") is False
    assert _is_pm_url(None) is False


def test_pm_vs_post_id_spaces_independent():
    """Dieselbe Zahl kann in beiden ID-Raeumen existieren; die Zuordnung erfolgt
    ueber die URL. Hier: id 555 ist eine PN-ID, keine Forum-post_id."""
    path = _make_fdb(with_pms=True)
    try:
        con = _attached(path)
        fdb = ForensicDb(con)
        # 555 nur in uid_pms_posts, nicht in uid_posts
        assert fdb.get_post_times([555]) == {}
        assert fdb.get_pm_post_times([555]) == {555: 1690000000}
        con.close()
    finally:
        os.unlink(path)
    # _derive_post_id bleibt URL-unabhaengig (nur ID-Ableitung)
    assert _derive_post_id(_Rec(post_id=555, page_url="/forum/pmsnew.php?tid=1")) == 555

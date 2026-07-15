# =============================================================================
# tests/test_build430_content_ts.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Annotationsrecherche
# -----------------------------------------------------------------------------
# Zweck:
#   Testet die serverseitige, REIN LESENDE Inhaltszeit-Aufloesung fuer den
#   Zeitstrahl (Build 430):
#     - ForensicDb.get_post_times(): fdb.uid_posts(id, posted) -> {post_id: sek},
#       inkl. defensiver Faelle (unbekannte id, NULL posted, fehlende Tabelle).
#     - annotations._derive_post_id(): post_id aus post_id ODER element_id 'p<n>'.
#
#   Beleg: uid_posts(id, posted) — tests/test_build388_vorlagen.py:353;
#          Bauplan_Baustelle4_Annotationsrecherche_v0_1.md §9/§13.
# =============================================================================

import os
import sqlite3
import tempfile

from db.forensic_db import ForensicDb
from forensic_api.annotations import _derive_post_id


class _Rec:
    """Minimaler Annotationsdatensatz-Ersatz mit post_id/element_id."""
    def __init__(self, post_id=None, element_id=None):
        self.post_id = post_id
        self.element_id = element_id


def _make_fdb(with_uid_posts=True):
    """Legt eine minimale forensic_db-Datei an (Tabellen fuer den blob_lookup-View
    plus optional uid_posts) und gibt den Pfad zurueck."""
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
        """
    )
    if with_uid_posts:
        con.executescript(
            """
            CREATE TABLE uid_posts (id INTEGER, posted INTEGER);
            INSERT INTO uid_posts VALUES (12345, 1664000000), (67890, 1700000000), (500, NULL);
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


def test_get_post_times_basic():
    """Bekannte post_ids -> posted (Sekunden); unbekannte fehlen; NULL posted raus."""
    path = _make_fdb(with_uid_posts=True)
    try:
        con = _attached(path)
        fdb = ForensicDb(con)
        result = fdb.get_post_times([12345, 67890, 999, 500])
        assert result == {12345: 1664000000, 67890: 1700000000}
        con.close()
    finally:
        os.unlink(path)


def test_get_post_times_empty_input():
    """Leere Eingabe -> leeres Mapping (kein SQL)."""
    path = _make_fdb(with_uid_posts=True)
    try:
        con = _attached(path)
        fdb = ForensicDb(con)
        assert fdb.get_post_times([]) == {}
        assert fdb.get_post_times([None, None]) == {}
        con.close()
    finally:
        os.unlink(path)


def test_get_post_times_missing_table_defensive():
    """Fehlt fdb.uid_posts (aeltere DB), liefert die Methode {} statt zu brechen (GR1)."""
    path = _make_fdb(with_uid_posts=False)
    try:
        con = _attached(path)
        fdb = ForensicDb(con)
        assert fdb.get_post_times([12345]) == {}
        con.close()
    finally:
        os.unlink(path)


def test_derive_post_id_from_post_id():
    assert _derive_post_id(_Rec(post_id=42)) == 42
    assert _derive_post_id(_Rec(post_id="77")) == 77


def test_derive_post_id_from_element_id():
    assert _derive_post_id(_Rec(post_id=None, element_id="p4567")) == 4567
    # element_id gewinnt nicht ueber vorhandene post_id
    assert _derive_post_id(_Rec(post_id=10, element_id="p4567")) == 10


def test_derive_post_id_none():
    assert _derive_post_id(_Rec(post_id=None, element_id="abc")) is None
    assert _derive_post_id(_Rec(post_id=None, element_id=None)) is None
    assert _derive_post_id(_Rec(post_id=None, element_id="p")) is None

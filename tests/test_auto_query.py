# =============================================================================
# tests/test_auto_query.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6/7: Berichts-Ausgabe
# =============================================================================
# Testsuite fuer den gemeinsamen {{a:}}-Aufloesungskern report_render/auto_query.py
# (Build 403, De-Duplizierung). Tests gegen eine ECHTE EvidenceDb (Cache) und
# eine ECHTE In-Memory-fdb (SQL) — kein MagicMock an der Interface-Grenze.
#
#   AQ01 -- Cache-Hit
#   AQ02 -- resolved (nicht-leeres Query-Ergebnis)
#   AQ03 -- empty (Query lief, kein Treffer) -> "" + status 'empty'
#   AQ04 -- no_query (keine Definition / templates None)
#   AQ05 -- sql_error (fehlerhafte SQL / keine Verbindung)
#   AQ06 -- write_cache=False schreibt NICHT; True schreibt
#   AQ07 -- resolve_value_or_none: no_query/sql_error -> None, empty -> ""
#   AQ08 -- execute_query: row None -> ("",True); Fehler -> (None,False)
#
# Version: v0.7.403 · Build: 403 · 2026-07-14
# =============================================================================

import sqlite3
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.evidence_db import EvidenceDb
from report_render.auto_query import (
    AutoQueryResolver,
    STATUS_CACHE_HIT, STATUS_RESOLVED, STATUS_EMPTY,
    STATUS_NO_QUERY, STATUS_SQL_ERROR,
)


class _Templates:
    """Minimaler TemplatesDb-Ersatz: get_query liefert ein Objekt mit .sql_query."""
    def __init__(self, mapping):
        self._m = mapping

    def get_query(self, qid):
        if qid in self._m:
            return types.SimpleNamespace(id=qid, sql_query=self._m[qid])
        return None


def _fdb():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE uid_profile (id INTEGER PRIMARY KEY, username TEXT)")
    con.execute("INSERT INTO uid_profile VALUES (42, 'Alice')")
    con.commit()
    return con


def _edb():
    return EvidenceDb(sqlite3.connect(":memory:", check_same_thread=False))


_SQL_NAME = "SELECT username FROM uid_profile WHERE id = :uid"


class TestAutoQuery(unittest.TestCase):

    def setUp(self):
        self.edb = _edb()
        self.fcon = _fdb()
        self.tpl = _Templates({"user.name": _SQL_NAME,
                               "bad": "SELECT x FROM does_not_exist WHERE id=:uid"})

    def test_AQ01_cache_hit(self):
        self.edb.set_cache_entry("user.name", 42, "Cached")
        a = AutoQueryResolver(self.edb, self.tpl, self.fcon)
        res = a.resolve("user.name", 42)
        self.assertEqual(res.status, STATUS_CACHE_HIT)
        self.assertEqual(res.value, "Cached")

    def test_AQ02_resolved(self):
        a = AutoQueryResolver(self.edb, self.tpl, self.fcon)
        res = a.resolve("user.name", 42)
        self.assertEqual(res.status, STATUS_RESOLVED)
        self.assertEqual(res.value, "Alice")

    def test_AQ03_empty(self):
        a = AutoQueryResolver(self.edb, self.tpl, self.fcon)
        res = a.resolve("user.name", 99)          # uid ohne Treffer
        self.assertEqual(res.status, STATUS_EMPTY)
        self.assertEqual(res.value, "")

    def test_AQ04_no_query(self):
        a = AutoQueryResolver(self.edb, self.tpl, self.fcon)
        self.assertEqual(a.resolve("fehlt", 42).status, STATUS_NO_QUERY)
        # templates None -> ebenfalls no_query
        a2 = AutoQueryResolver(self.edb, None, self.fcon)
        self.assertEqual(a2.resolve("user.name", 42).status, STATUS_NO_QUERY)

    def test_AQ05_sql_error(self):
        a = AutoQueryResolver(self.edb, self.tpl, self.fcon)
        self.assertEqual(a.resolve("bad", 42).status, STATUS_SQL_ERROR)
        # keine forensische Verbindung -> sql_error
        a2 = AutoQueryResolver(self.edb, self.tpl, None)
        self.assertEqual(a2.resolve("user.name", 42).status, STATUS_SQL_ERROR)

    def test_AQ06_write_cache_flag(self):
        # write_cache=False: Cache bleibt leer
        a = AutoQueryResolver(self.edb, self.tpl, self.fcon, write_cache=False)
        a.resolve("user.name", 42)
        self.assertIsNone(self.edb.get_cache_entry("user.name", 42))
        # write_cache=True: Cache wird befuellt
        b = AutoQueryResolver(self.edb, self.tpl, self.fcon, write_cache=True)
        b.resolve("user.name", 42)
        self.assertEqual(self.edb.get_cache_entry("user.name", 42), "Alice")

    def test_AQ07_resolve_value_or_none(self):
        a = AutoQueryResolver(self.edb, self.tpl, self.fcon)
        self.assertEqual(a.resolve_value_or_none("user.name", 42), "Alice")
        self.assertEqual(a.resolve_value_or_none("user.name", 99), "")   # empty
        self.assertIsNone(a.resolve_value_or_none("fehlt", 42))          # no_query
        self.assertIsNone(a.resolve_value_or_none("bad", 42))            # sql_error

    def test_AQ08_execute_query(self):
        a = AutoQueryResolver(self.edb, self.tpl, self.fcon)
        val, ok = a.execute_query(_SQL_NAME, 42)
        self.assertEqual((val, ok), ("Alice", True))
        val, ok = a.execute_query(_SQL_NAME, 99)      # kein Treffer
        self.assertEqual((val, ok), ("", True))
        val, ok = a.execute_query("SELECT x FROM nope", 42)
        self.assertEqual((val, ok), (None, False))


if __name__ == "__main__":
    unittest.main()

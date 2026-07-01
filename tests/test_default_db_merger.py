# =============================================================================
# tests/test_default_db_merger.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management/Wartung
# =============================================================================
# Testsuite für management.maintenance.DefaultDbMerger
# (verlustfreie Konsolidierung mehrerer default.db).
#
# M01 — Basis-Merge zweier Quellen: Zeilen vereinigt, Bericht ausgeglichen
# M02 — asset_id-Remap korrekt: gleiche Quell-id in verschiedenen Quellen
#       zeigt NICHT auf dasselbe Ziel-Asset (kein Cross-Wiring); FK sauber
# M03 — content_hash-Dedup über Quellen hinweg -> genau ein Asset
# M04 — dieselbe URL zeigt in Quelle B auf anderes Asset -> Konflikt,
#       neueste Quelle gewinnt, protokolliert
# M05 — known_aliases: (user_id, name)-Dedup, alias_id neu vergeben
# M06 — default_meta stabiler Key divergiert -> MergeError (Abbruch)
# M07 — default_meta Lauf-Key divergiert -> neueste Quelle gewinnt
# M08 — Invariante: keine Zeile still verworfen (balanced == True je Tabelle)
# M09 — unbekannte Tabelle in Quelle -> MergeError (fail loud)
# M10 — Ziel == Quelle bzw. Ziel existiert ohne --overwrite -> MergeError
# M11 — Quellen bleiben unverändert (read-only); provenance geschrieben
#
# Version: v0.7.309 · Build: 309 · 2026-07-01
# =============================================================================

import hashlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.maintenance.default_db_merger import (
    _CANONICAL_DDL,
    DefaultDbMerger,
    MergeError,
)


def _new_source(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(_CANONICAL_DDL)
    con.commit()
    return con


def _add_asset(con, content: bytes, note="found", mime="image/png") -> int:
    ch = hashlib.md5(content).hexdigest()
    cur = con.execute(
        "INSERT INTO default_assets "
        "(content_hash, data, mime_type, file_size, source_note, fetched_at) "
        "VALUES (?,?,?,?,?,?)",
        (ch, content, mime, len(content), note, 1000),
    )
    return cur.lastrowid


def _add_url(con, url, asset_id, ctx="img"):
    con.execute(
        "INSERT INTO default_urls "
        "(url, url_hash, asset_id, url_context, http_status, added_at) "
        "VALUES (?,?,?,?,?,?)",
        (url, hashlib.md5(url.encode()).hexdigest()[:16], asset_id, ctx, 200, 1000),
    )


def _set_meta(con, key, value):
    con.execute(
        "INSERT OR REPLACE INTO default_meta (key, value) VALUES (?, ?)",
        (key, str(value)),
    )


class DefaultDbMergerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.target = self.root / "central" / "default.db"

    def tearDown(self):
        self._tmp.cleanup()

    # --------------------------------------------------------------- helpers
    def _run(self, sources, **kw):
        merger = DefaultDbMerger(
            target_path=self.target,
            source_paths=sources,
            **kw,
        )
        return merger.run()

    def _target_urls(self):
        """{url: content_hash} über den JOIN im Ziel — prüft den FK-Remap."""
        con = sqlite3.connect(self.target)
        try:
            rows = con.execute(
                "SELECT du.url AS url, da.content_hash AS ch "
                "FROM default_urls du LEFT JOIN default_assets da "
                "ON da.id = du.asset_id"
            ).fetchall()
            return {r[0]: r[1] for r in rows}
        finally:
            con.close()

    # ----------------------------------------------------------------- tests
    def test_m01_basic_merge_balanced(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        b = self.root / "b" / "default.db"; b.parent.mkdir(parents=True)
        ca = _new_source(a)
        _set_meta(ca, "last_run_ts", 100)
        ca.execute("INSERT INTO known_users (user_id, username) VALUES (5,'alice')")
        ca.commit(); ca.close()
        cb = _new_source(b)
        _set_meta(cb, "last_run_ts", 200)
        cb.execute("INSERT INTO known_users (user_id, username) VALUES (6,'bob')")
        cb.commit(); cb.close()

        report = self._run([a, b])
        con = sqlite3.connect(self.target)
        n = con.execute("SELECT COUNT(*) FROM known_users").fetchone()[0]
        con.close()
        self.assertEqual(n, 2)
        for st in report.tables.values():
            self.assertTrue(st.balanced)
        self.assertTrue(report.fk_check_ok)

    def test_m02_asset_id_remap_no_crosswire(self):
        # Quelle A: id1=hashA (/x), id2=hashB (/y)
        # Quelle B: id1=hashC (/z)  -> gleiche Quell-id 1, anderer Inhalt
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        b = self.root / "b" / "default.db"; b.parent.mkdir(parents=True)
        ca = _new_source(a); _set_meta(ca, "last_run_ts", 100)
        id1 = _add_asset(ca, b"AAAA"); id2 = _add_asset(ca, b"BBBB")
        _add_url(ca, "/x", id1); _add_url(ca, "/y", id2)
        ca.commit(); ca.close()
        cb = _new_source(b); _set_meta(cb, "last_run_ts", 200)
        idb = _add_asset(cb, b"CCCC")  # in B ebenfalls id=1
        _add_url(cb, "/z", idb)
        cb.commit(); cb.close()

        self._run([a, b])
        urls = self._target_urls()
        self.assertEqual(urls["/x"], hashlib.md5(b"AAAA").hexdigest())
        self.assertEqual(urls["/y"], hashlib.md5(b"BBBB").hexdigest())
        # KERN: /z darf NICHT auf hashA zeigen, obwohl beide Quell-id 1 hatten
        self.assertEqual(urls["/z"], hashlib.md5(b"CCCC").hexdigest())

    def test_m03_content_hash_dedup(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        b = self.root / "b" / "default.db"; b.parent.mkdir(parents=True)
        ca = _new_source(a); _set_meta(ca, "last_run_ts", 100)
        _add_url(ca, "/x", _add_asset(ca, b"SAME")); ca.commit(); ca.close()
        cb = _new_source(b); _set_meta(cb, "last_run_ts", 200)
        _add_url(cb, "/y", _add_asset(cb, b"SAME")); cb.commit(); cb.close()

        self._run([a, b])
        con = sqlite3.connect(self.target)
        n = con.execute("SELECT COUNT(*) FROM default_assets").fetchone()[0]
        con.close()
        self.assertEqual(n, 1)  # identischer Inhalt -> genau ein Asset

    def test_m04_url_conflict_newest_wins(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        b = self.root / "b" / "default.db"; b.parent.mkdir(parents=True)
        ca = _new_source(a); _set_meta(ca, "last_run_ts", 100)
        _add_url(ca, "/logo.png", _add_asset(ca, b"OLD")); ca.commit(); ca.close()
        cb = _new_source(b); _set_meta(cb, "last_run_ts", 200)
        _add_url(cb, "/logo.png", _add_asset(cb, b"NEW")); cb.commit(); cb.close()

        report = self._run([a, b])
        urls = self._target_urls()
        # neueste Quelle (ts=200) gewinnt
        self.assertEqual(urls["/logo.png"], hashlib.md5(b"NEW").hexdigest())
        self.assertTrue(any(c.table == "default_urls" for c in report.conflicts))

    def test_m05_known_aliases_composite_dedup(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        b = self.root / "b" / "default.db"; b.parent.mkdir(parents=True)
        ca = _new_source(a); _set_meta(ca, "last_run_ts", 100)
        ca.execute("INSERT INTO known_aliases (user_id, name) VALUES (5,'nick')")
        ca.commit(); ca.close()
        cb = _new_source(b); _set_meta(cb, "last_run_ts", 200)
        cb.execute("INSERT INTO known_aliases (user_id, name) VALUES (5,'nick')")
        cb.execute("INSERT INTO known_aliases (user_id, name) VALUES (5,'other')")
        cb.commit(); cb.close()

        self._run([a, b])
        con = sqlite3.connect(self.target)
        rows = con.execute(
            "SELECT user_id, name FROM known_aliases ORDER BY name"
        ).fetchall()
        con.close()
        self.assertEqual([(r[0], r[1]) for r in rows], [(5, "nick"), (5, "other")])

    def test_m06_meta_stable_key_mismatch_aborts(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        b = self.root / "b" / "default.db"; b.parent.mkdir(parents=True)
        ca = _new_source(a); _set_meta(ca, "domainname", "forumA.onion"); ca.commit(); ca.close()
        cb = _new_source(b); _set_meta(cb, "domainname", "forumB.onion"); cb.commit(); cb.close()
        with self.assertRaises(MergeError):
            self._run([a, b])

    def test_m06b_meta_stable_key_mismatch_override(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        b = self.root / "b" / "default.db"; b.parent.mkdir(parents=True)
        ca = _new_source(a); _set_meta(ca, "last_run_ts", 100)
        _set_meta(ca, "domainname", "forumA.onion"); ca.commit(); ca.close()
        cb = _new_source(b); _set_meta(cb, "last_run_ts", 200)
        _set_meta(cb, "domainname", "forumB.onion"); cb.commit(); cb.close()
        report = self._run([a, b], allow_host_mismatch=True)
        con = sqlite3.connect(self.target)
        v = con.execute(
            "SELECT value FROM default_meta WHERE key='domainname'"
        ).fetchone()[0]
        con.close()
        self.assertEqual(v, "forumB.onion")  # neueste gewinnt
        self.assertTrue(report.fk_check_ok)

    def test_m07_meta_run_key_newest_wins(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        b = self.root / "b" / "default.db"; b.parent.mkdir(parents=True)
        ca = _new_source(a); _set_meta(ca, "last_run_ts", 100)
        _set_meta(ca, "last_run_stats", "old"); ca.commit(); ca.close()
        cb = _new_source(b); _set_meta(cb, "last_run_ts", 200)
        _set_meta(cb, "last_run_stats", "new"); cb.commit(); cb.close()
        self._run([a, b])
        con = sqlite3.connect(self.target)
        v = con.execute(
            "SELECT value FROM default_meta WHERE key='last_run_stats'"
        ).fetchone()[0]
        con.close()
        self.assertEqual(v, "new")

    def test_m09_unknown_table_aborts(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        ca = _new_source(a)
        ca.execute("CREATE TABLE bogus (x INTEGER)")
        ca.commit(); ca.close()
        with self.assertRaises(MergeError):
            self._run([a])

    def test_m10_target_is_source_aborts(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        ca = _new_source(a); ca.commit(); ca.close()
        merger = DefaultDbMerger(target_path=a, source_paths=[a])
        with self.assertRaises(MergeError):
            merger.run()

    def test_m10b_target_exists_without_overwrite_aborts(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        ca = _new_source(a); ca.commit(); ca.close()
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_bytes(b"exists")
        with self.assertRaises(MergeError):
            self._run([a])
        # mit --overwrite geht es
        report = self._run([a], overwrite=True)
        self.assertTrue(report.fk_check_ok)

    def test_m11_sources_unchanged_and_provenance(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        ca = _new_source(a); _set_meta(ca, "last_run_ts", 100)
        _add_url(ca, "/x", _add_asset(ca, b"DATA")); ca.commit(); ca.close()
        before = hashlib.md5(a.read_bytes()).hexdigest()

        self._run([a])
        after = hashlib.md5(a.read_bytes()).hexdigest()
        self.assertEqual(before, after)  # Quelle unangetastet

        con = sqlite3.connect(self.target)
        prov = con.execute(
            "SELECT value FROM default_meta WHERE key='merge_provenance'"
        ).fetchone()
        con.close()
        self.assertIsNotNone(prov)


if __name__ == "__main__":
    unittest.main()

# =============================================================================
# tests/test_migrate_templates_placeholders.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Platzhalter-Neuordnung (Build 489, Slice 1): Migrationstest
# =============================================================================
# MP01 — Erster Lauf: placeholders angelegt, Daten als Typ 'a' uebernommen,
#        placeholder_queries entfernt, Audit-CHECK um 'placeholder' erweitert,
#        Audit-Historie vollstaendig + Protokollzeile.
# MP02 — CHECK-Regeln der neuen Tabelle werden erzwungen (a ohne sql, a mit
#        validation, validation ohne validation_type, m-Query mit table).
# MP03 — Idempotenz: zweiter Lauf ist ein No-op, Daten unveraendert.
# MP04 — Inkonsistenter Zustand (beide Tabellen) -> harter Abbruch, kein Raten.
# MP05 — Gueltige Eintraege aller drei Typen sind einfuegbar (Positivprobe der
#        CHECKs — die Regeln duerfen nicht STRENGER sein als beschlossen).
#
# Beleg: Bauplan management/Bauplan_Platzhalter_DB_v0_1.md §3 (mc 2026-07-21).
# Version: v0.8.489 · Build: 489 · 2026-07-21
# =============================================================================

import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.migrate_templates_placeholders import apply_migration

_DDL_OLD_QUERIES = """
CREATE TABLE placeholder_queries (
    id TEXT NOT NULL PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
    sql_query TEXT NOT NULL, tags TEXT,
    return_type TEXT NOT NULL CHECK (return_type IN ('scalar','list','table')),
    is_active INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL,
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
)
"""
# Alt-Zustand VOR Build 421 bewusst mitgetestet: CHECK nur ('module','query').
_DDL_OLD_AUDIT = """
CREATE TABLE templates_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('module','query')),
    changed_by TEXT NOT NULL, changed_at INTEGER NOT NULL,
    old_value TEXT, new_value TEXT
)
"""


def _mk_old_db() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.execute(_DDL_OLD_QUERIES)
    con.execute(_DDL_OLD_AUDIT)
    con.execute("CREATE INDEX pq_tags_idx ON placeholder_queries (tags)")
    con.execute(
        "INSERT INTO placeholder_queries VALUES "
        "('user.name','Name','','SELECT username FROM uid_profile "
        "WHERE id=:uid','identitaet','scalar',1,'seed',10,20)")
    con.execute(
        "INSERT INTO placeholder_queries VALUES "
        "('user.posts','Beitraege','x','SELECT COUNT(*) FROM uid_posts',"
        "NULL,'scalar',0,'seed',11,21)")
    con.execute(
        "INSERT INTO templates_audit_log (action, target_id, target_type, "
        "changed_by, changed_at) VALUES ('add_query','user.name','query',"
        "'seed',10)")
    con.commit()
    return con


class MigrationTests(unittest.TestCase):

    def test_mp01_erster_lauf(self):
        con = _mk_old_db()
        res = apply_migration(con, changed_by="tester", ts=99)
        self.assertTrue(res["migrated"])
        self.assertEqual(res["carried_rows"], 2)
        self.assertTrue(res["audit_widened"])

        # Datenuebernahme: alles Typ 'a', Felder erhalten (auch is_active=0).
        rows = con.execute(
            "SELECT id, type, sql_query, is_active, created_at "
            "FROM placeholders ORDER BY id").fetchall()
        self.assertEqual([(r[0], r[1], r[3]) for r in rows],
                         [("user.name", "a", 1), ("user.posts", "a", 0)])
        # Alte Tabelle weg.
        self.assertIsNone(con.execute(
            "SELECT name FROM sqlite_master WHERE name='placeholder_queries'"
        ).fetchone())
        # Audit: Historie (1) + Protokollzeile (1), CHECK erweitert.
        n = con.execute("SELECT COUNT(*) FROM templates_audit_log").fetchone()[0]
        self.assertEqual(n, 2)
        mig = con.execute(
            "SELECT target_type, changed_by, changed_at FROM "
            "templates_audit_log WHERE action='migrate'").fetchone()
        self.assertEqual(tuple(mig), ("placeholder", "tester", 99))
        ddl = con.execute(
            "SELECT sql FROM sqlite_master WHERE name='templates_audit_log'"
        ).fetchone()[0]
        self.assertIn("'placeholder'", ddl)
        con.close()

    def test_mp02_check_regeln(self):
        con = _mk_old_db()
        apply_migration(con)
        base = ("INSERT INTO placeholders (id, title, description, type, "
                "sql_query, default_value, validation, validation_type, tags, "
                "return_type, is_active, created_by, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,1,'t',0,0)")
        # a ohne sql_query.
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute(base, ("x1", "T", "", "a", None, None, None, None,
                               None, "scalar"))
        # a mit Validierung.
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute(base, ("x2", "T", "", "a", "SELECT 1", None,
                               "^\\d+$", "regex", None, "scalar"))
        # validation ohne validation_type (und umgekehrt).
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute(base, ("x3", "T", "", "m", None, None,
                               "^\\d+$", None, None, "scalar"))
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute(base, ("x4", "T", "", "m", None, None,
                               None, "regex", None, "scalar"))
        # m mit Default-Query, aber return_type 'table'.
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute(base, ("x5", "T", "", "m", "SELECT 1", None,
                               None, None, None, "table"))
        # Unbekannter Typ / unbekannter validation_type.
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute(base, ("x6", "T", "", "z", None, None, None, None,
                               None, "scalar"))
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute(base, ("x7", "T", "", "o", None, None,
                               "abc", "fuzzy", None, "scalar"))
        con.close()

    def test_mp03_idempotent(self):
        con = _mk_old_db()
        apply_migration(con)
        before = con.execute(
            "SELECT COUNT(*) FROM placeholders").fetchone()[0]
        res2 = apply_migration(con)
        self.assertFalse(res2["migrated"])
        self.assertTrue(res2["already_migrated"])
        after = con.execute(
            "SELECT COUNT(*) FROM placeholders").fetchone()[0]
        self.assertEqual(before, after)
        con.close()

    def test_mp04_beide_tabellen_ist_abbruch(self):
        con = _mk_old_db()
        # Kuenstlich einen halbfertigen Zustand simulieren.
        con.execute("CREATE TABLE placeholders (id TEXT PRIMARY KEY)")
        with self.assertRaises(SystemExit):
            apply_migration(con)
        con.close()

    def test_mp05_gueltige_eintraege_aller_typen(self):
        con = _mk_old_db()
        apply_migration(con)
        base = ("INSERT INTO placeholders (id, title, description, type, "
                "sql_query, default_value, validation, validation_type, tags, "
                "return_type, is_active, created_by, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,1,'t',0,0)")
        # a mit Query (list-Rueckgabe erlaubt).
        con.execute(base, ("ok.a", "T", "", "a", "SELECT x FROM y", None,
                           None, None, None, "list"))
        # m mit Regex-Validierung, ohne Query.
        con.execute(base, ("ok.m", "T", "", "m", None, "unbekannt",
                           "^[A-Z]{2}-\\d{4}$", "regex", None, "scalar"))
        # o mit list-Validierung UND skalarer Default-Query.
        con.execute(base, ("ok.o", "T", "", "o", "SELECT 1", None,
                           '["ja","nein"]', "list", "t", "scalar"))
        n = con.execute("SELECT COUNT(*) FROM placeholders").fetchone()[0]
        self.assertEqual(n, 5)  # 2 uebernommene + 3 neue
        con.close()


if __name__ == "__main__":
    unittest.main()

# =============================================================================
# tests/test_migration_m019_subject_id.py
# IT-Forensisches Ermittlungswerkzeug — Globale Schluesselumstellung
# =============================================================================
# Testsuite fuer Build 469: Migration M019 (user_id -> subject_id, Weg A).
#
# IM19-01 — Voller Lauf (M001..M019): alle 9 Tabellen tragen subject_id,
#           keine mehr user_id; 2. Runner-Lauf No-Op.
# IM19-02 — Datenerhalt: vor M019 eingefuegte Zeilen (ueber M001..M018 +
#           Seed) stehen nach M019 wertgleich unter subject_id.
# IM19-03 — FK-Propagation: die 4 Kinder referenzieren cases(subject_id);
#           foreign_key_check leer.
# IM19-04 — m011-Schutz intakt: illegaler UPDATE/DELETE auf
#           investigation_results wird weiter abgewiesen; die legale
#           Beleg-Kopplung audit_seq 0 -> seq funktioniert; die View liefert.
# IM19-05 — Index-Umbenennung: scrape_jobs_subject_idx und
#           case_events_subject_time_idx existieren, die alten Namen nicht.
# IM19-06 — Meta-Beleg subject_key_meta (scheme_version 1) vorhanden.
# IM19-07 — Idempotenz: direkter 2. up()-Aufruf ist ein No-op.
# IM19-08 — Geister-Schluessel: subject_id oberhalb des Realbandes (Prepper-
#           Schema) ist in forum_promotion speicherbar (kein cases-FK).
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations
from management.audit.audit_log import AuditLog
from management.migrations.coordinator import m019_subject_id_rename
from management.migrations.runner import MigrationRunner, discover

# WICHTIG — echte Historie nachspielen: Das Fixture legt 'investigators' an
# (NICHT 'person'), damit M005 den Rename investigators -> person selbst
# vollzieht und dabei die REFERENCES-Klauseln von M002-M004 nachzieht — exakt
# wie in der Produktions-coordinator.db. Ein direkt angelegtes 'person'
# liesse M005 als No-op durchlaufen und die FK-Klauseln hingen dangling auf
# 'investigators' (fixture-verursachte foreign_key_check-Treffer).
_INVESTIGATORS = """
CREATE TABLE investigators (
    id INTEGER PRIMARY KEY AUTOINCREMENT, system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL, is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0, is_support INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
)
"""

_OLD_SCRAPE_JOBS = """
CREATE TABLE scrape_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','running','done','failed')),
    manifest_path TEXT, output_path TEXT, worker_id TEXT,
    created_at INTEGER NOT NULL, started_at INTEGER, finished_at INTEGER,
    error_message TEXT, assigned_to INTEGER, note TEXT,
    FOREIGN KEY(assigned_to) REFERENCES investigators(id)
)
"""

#: Tabellen, deren Schluesselspalte M019 umbenennt (Blast-Radius, gemessen).
_AFFECTED = ("cases", "case_events", "external_matters",
             "investigation_results", "case_release", "scrape_jobs",
             "support_sessions", "evidence_scan_cache", "forum_promotion")


class MigrationM019Tests(unittest.TestCase):
    """M019: Schluesselumstellung user_id -> subject_id (Weg A)."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        now = int(time.time())
        self.con.execute(_INVESTIGATORS)
        self.con.execute(
            "INSERT INTO investigators (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (1, 'chef', 'Chefin', 1, 1, 0, ?)", (now,))
        self.con.execute(_OLD_SCRAPE_JOBS)
        self.audit = AuditLog(self.con)
        self.mods = discover(coordinator_migrations)

        # Lauf bis M018 (Alt-Schema mit user_id), dann Alt-Daten einfuegen,
        # dann M019 — so prueft der Test die Migration BESTEHENDER Daten.
        pre = [m for m in self.mods if m.VERSION <= 18]
        MigrationRunner(self.con, pre, audit=self.audit,
                        deployed_by="tester").run()
        self._seed_old_data(now)
        self.runner = MigrationRunner(
            self.con, self.mods, audit=self.audit, deployed_by="tester")
        self.applied = self.runner.run()

    def tearDown(self):
        try:
            self.con.close()
        finally:
            for fn in os.listdir(self._tmp):
                try:
                    os.remove(os.path.join(self._tmp, fn))
                except OSError:
                    pass
            os.rmdir(self._tmp)

    # ------------------------------------------------------------------ Seed
    def _seed_old_data(self, now):
        """Alt-Daten (user_id-Schema) in alle 9 betroffenen Tabellen."""
        con = self.con
        aseq = int(con.execute(
            "SELECT MAX(seq) FROM audit_log").fetchone()[0])
        self.crit = con.execute(
            "SELECT code FROM assessment_criterion LIMIT 1").fetchone()[0]
        con.execute("INSERT INTO cases (user_id, username, created_at, "
                    "updated_at) VALUES (18, 'uid18', ?, ?)", (now, now))
        con.execute("INSERT INTO cases (user_id, username, created_at, "
                    "updated_at) VALUES (42, 'uid42', ?, ?)", (now, now))
        con.execute("INSERT INTO case_events (user_id, event_kind, payload, "
                    "created_by, created_at, audit_seq) "
                    "VALUES (18, 'test', '{}', 1, ?, ?)", (now, aseq))
        con.execute("INSERT INTO external_matters (user_id, kind, betreff, "
                    "angefordert_am, wiedervorlage_am, created_by, "
                    "created_at, audit_seq, created_audit_seq) "
                    "VALUES (18, 'auskunft', 'T', '2026-07-20', '2026-08-01', "
                    "1, ?, ?, ?)", (now, aseq, aseq))
        con.execute("INSERT INTO investigation_results (user_id, "
                    "criterion_code, extrem, confidence_code, "
                    "confidence_ordinal, catalog_version, note, created_by, "
                    "created_at, audit_seq) VALUES (18, ?, 'schwerste', "
                    "'verdacht', 10, 1, 'alt', 1, ?, ?)",
                    (self.crit, now, aseq))
        con.execute("INSERT INTO case_release (user_id, recipient_kennung, "
                    "recipient_display, umfang, unbedenklichkeit_grundlage, "
                    "created_by, created_at, audit_seq, created_audit_seq) "
                    "VALUES (18, 'lka.mm', 'M. M.', 'bericht', 'Vermerk', 1, "
                    "?, ?, ?)", (now, aseq, aseq))
        con.execute("INSERT INTO scrape_jobs (user_id, username, created_at) "
                    "VALUES (42, 'uid42', ?)", (now,))
        con.execute("INSERT INTO support_sessions (user_id, supporter_id, "
                    "started_at, last_heartbeat) VALUES (18, 1, ?, ?)",
                    (now, now))
        con.execute("INSERT INTO evidence_scan_cache (user_id, fingerprint, "
                    "scanned_at) VALUES (18, 'fp', ?)", (now,))
        # Geister-Kandidat (Prepper-Schema: prefix 1e9 + mat_usernames.id).
        con.execute("INSERT INTO forum_promotion (user_id, status, "
                    "created_by, created_at, audit_seq, created_audit_seq) "
                    "VALUES (1000000123, 'gesichtet', 1, ?, ?, ?)",
                    (now, aseq, aseq))

    def _cols(self, table):
        return [r[1] for r in self.con.execute(
            "PRAGMA table_info(%s)" % table)]

    # IM19-01 ----------------------------------------------------------------
    def test_im19_01_applied_and_noop(self):
        self.assertIn(19, self.applied)
        for t in _AFFECTED:
            cols = self._cols(t)
            self.assertIn("subject_id", cols, t)
            self.assertNotIn("user_id", cols, t)
        second = MigrationRunner(
            self.con, self.mods, audit=self.audit, deployed_by="tester").run()
        self.assertEqual(second, [])

    # IM19-02 ----------------------------------------------------------------
    def test_im19_02_data_preserved(self):
        rows = self.con.execute(
            "SELECT subject_id, username FROM cases ORDER BY subject_id"
        ).fetchall()
        self.assertEqual([(r[0], r[1]) for r in rows],
                         [(18, "uid18"), (42, "uid42")])
        self.assertEqual(self.con.execute(
            "SELECT subject_id FROM evidence_scan_cache").fetchone()[0], 18)
        self.assertEqual(self.con.execute(
            "SELECT subject_id FROM forum_promotion").fetchone()[0],
            1000000123)
        for t, expected in (("case_events", 1), ("external_matters", 1),
                            ("investigation_results", 1), ("case_release", 1),
                            ("scrape_jobs", 1), ("support_sessions", 1)):
            self.assertEqual(self.con.execute(
                "SELECT COUNT(*) FROM %s" % t).fetchone()[0], expected, t)

    # IM19-03 ----------------------------------------------------------------
    def test_im19_03_fk_propagation(self):
        for t in ("case_events", "external_matters",
                  "investigation_results", "case_release"):
            fks = [fk for fk in self.con.execute(
                "PRAGMA foreign_key_list(%s)" % t) if fk[2] == "cases"]
            self.assertTrue(fks, t)
            for fk in fks:
                self.assertEqual(fk[3], "subject_id", t)
                self.assertEqual(fk[4], "subject_id", t)
        self.assertEqual(
            self.con.execute("PRAGMA foreign_key_check").fetchall(), [])

    # IM19-04 ----------------------------------------------------------------
    def test_im19_04_append_only_intact(self):
        rid = self.con.execute(
            "SELECT MIN(id) FROM investigation_results").fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "UPDATE investigation_results SET note='x' WHERE id=?", (rid,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "DELETE FROM investigation_results WHERE id=?", (rid,))
        # Legale Beleg-Kopplung 0 -> seq (Produktionszustand foreign_keys=OFF).
        aseq = int(self.con.execute(
            "SELECT MAX(seq) FROM audit_log").fetchone()[0])
        cur = self.con.execute(
            "INSERT INTO investigation_results (subject_id, criterion_code, "
            "extrem, confidence_code, confidence_ordinal, catalog_version, "
            "note, created_by, created_at, audit_seq) VALUES (18, ?, 'beste', "
            "'verdacht', 10, 1, 'neu', 1, ?, 0)",
            (self.crit, int(time.time())))
        self.con.execute(
            "UPDATE investigation_results SET audit_seq=? WHERE id=?",
            (aseq, cur.lastrowid))
        # View liefert je (Fall, Kriterium, Extrem) den juengsten Stand.
        rows = self.con.execute(
            "SELECT subject_id, extrem FROM v_investigation_current "
            "ORDER BY extrem").fetchall()
        self.assertEqual([(r[0], r[1]) for r in rows],
                         [(18, "beste"), (18, "schwerste")])

    # IM19-05 ----------------------------------------------------------------
    def test_im19_05_index_renames(self):
        def idx(n):
            return self.con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
                (n,)).fetchone()
        self.assertIsNotNone(idx("scrape_jobs_subject_idx"))
        self.assertIsNotNone(idx("case_events_subject_time_idx"))
        self.assertIsNone(idx("scrape_jobs_user_idx"))
        self.assertIsNone(idx("case_events_user_time_idx"))

    # IM19-06 ----------------------------------------------------------------
    def test_im19_06_meta_record(self):
        row = self.con.execute(
            "SELECT scheme, scheme_version, migrated_from "
            "FROM subject_key_meta WHERE id=1").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "prepper-subject-id")
        self.assertEqual(row[1], 1)
        self.assertEqual(row[2], "user_id")

    # IM19-07 ----------------------------------------------------------------
    def test_im19_07_up_idempotent(self):
        before = self.con.execute(
            "SELECT COUNT(*) FROM subject_key_meta").fetchone()[0]
        m019_subject_id_rename.up(self.con)  # direkter 2. Aufruf
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM subject_key_meta").fetchone()[0], before)
        for t in _AFFECTED:
            self.assertIn("subject_id", self._cols(t), t)

    # IM19-08 ----------------------------------------------------------------
    def test_im19_08_ghost_key_storable(self):
        # Geist im Prepper-Schema weit oberhalb des Realbandes; forum_promotion
        # hat bewusst keinen cases-FK (m015) — genau dort landen Kandidaten.
        aseq = int(self.con.execute(
            "SELECT MAX(seq) FROM audit_log").fetchone()[0])
        self.con.execute(
            "INSERT INTO forum_promotion (subject_id, status, created_by, "
            "created_at, audit_seq, created_audit_seq) "
            "VALUES (1000795972, 'gesichtet', 1, ?, ?, ?)",
            (int(time.time()), aseq, aseq))
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM forum_promotion").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()

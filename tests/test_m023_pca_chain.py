# =============================================================================
# tests/test_m023_pca_chain.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Querfunde (AP-2A)
# =============================================================================
# Testsuite fuer Build 506 / Migration M023 (Governance-Punkt A4):
# 'pending_cross_annotations' in die Migrationskette + generierte Spalte
# 'subject_id'.
#
# M2301 — frische DB: die Migration legt Tabelle + BEIDE Indizes + die
#         generierte Spalte an.
# M2302 — BESTANDSFALL (der wichtigste Test): die Tabelle existiert bereits mit
#         echten Zeilen (Laufzeit-DDL aus db/coordinator_db.py). Die Migration
#         ist VERLUSTFREI — Zeilenzahl UND Inhalte identisch, subject_id deckt
#         sich fuer JEDE Zeile mit target_uid.
# M2303 — Idempotenz: ein zweiter Lauf ist ein No-op (der Spalten-Guard nutzt
#         PRAGMA table_xinfo; mit table_info haette er die generierte Spalte
#         NICHT gefunden und der zweite ALTER TABLE waere gescheitert).
# M2304 — der ECHTE Schreibpfad (CoordinatorDb.add_pending_cross_annotation)
#         fuellt nach der Migration automatisch die korrekte subject_id — der
#         Beweis, dass eine Divergenz konstruktiv ausgeschlossen ist.
# M2305 — schema_migrations traegt Version 23 mit kind='additive'.
# M2306 — CrossfindingsRepo liefert vor UND nach der Migration die identische
#         Ausgabeform (Vertraeglichkeits-Zweig).
#
# Version: v0.8.506 · Build: 506 · 2026-07-24
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
from management.crossref.crossfindings_repo import CrossfindingsRepo
from management.migrations.runner import MigrationRunner, discover

_PERSON = """
CREATE TABLE person (
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
    FOREIGN KEY(assigned_to) REFERENCES person(id)
)
"""

# ZEICHENGENAU die Laufzeit-DDL aus db/coordinator_db.py (Build 185) — der
# Zustand, den eine produktive coordinator.db VOR M023 hat.
_LEGACY_PCA = """
CREATE TABLE pending_cross_annotations (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    source_iid           INTEGER NOT NULL,
    target_uid           INTEGER NOT NULL,
    db_path              TEXT    NOT NULL,
    annotation_local_id  TEXT    NOT NULL,
    created_at           INTEGER NOT NULL,
    integrated_at        INTEGER DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS pca_target_uid_idx
    ON pending_cross_annotations (target_uid)
    WHERE integrated_at IS NULL;
"""


class M023PcaChainTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.now = int(time.time())

    def tearDown(self):
        for fn in os.listdir(self._tmp):
            try:
                os.remove(os.path.join(self._tmp, fn))
            except OSError:
                pass
        os.rmdir(self._tmp)

    # ------------------------------------------------------------------ Hilfen
    def _base_db(self, name="coordinator.db"):
        """coordinator.db mit dem Vorschema, aber OHNE gelaufene Kette."""
        path = os.path.join(self._tmp, name)
        con = sqlite3.connect(path)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute(_PERSON)
        con.execute(
            "INSERT INTO person (id, system_username, display_name, created_at)"
            " VALUES (1, 'h001', 'Ermittler Eins', ?)", (self.now,))
        con.execute(_OLD_SCRAPE_JOBS)
        return path, con

    @staticmethod
    def _run_chain(con, upto=None):
        mods = discover(coordinator_migrations)
        if upto is not None:
            mods = [m for m in mods if m.VERSION <= upto]
        MigrationRunner(con, mods, audit=AuditLog(con),
                        deployed_by="tester").run()

    @staticmethod
    def _columns(con):
        # table_xinfo — table_info wuerde die generierte Spalte verschweigen.
        return [str(r[1]) for r in
                con.execute("PRAGMA table_xinfo(pending_cross_annotations)")]

    @staticmethod
    def _index_exists(con, name):
        return con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
            (name,)).fetchone() is not None

    # M2301 ------------------------------------------------------------------
    def test_m2301_frische_db(self):
        path, con = self._base_db()
        try:
            self._run_chain(con)
            cols = self._columns(con)
            self.assertIn("target_uid", cols)
            self.assertIn("subject_id", cols)
            self.assertTrue(self._index_exists(con, "pca_target_uid_idx"))
            self.assertTrue(self._index_exists(con, "ix_pca_subject_id"))
            # Die Spalte ist GENERIERT (nicht beschreibbar) — der Beweis, dass
            # sie nicht abdriften kann.
            with self.assertRaises(sqlite3.OperationalError):
                con.execute(
                    "INSERT INTO pending_cross_annotations "
                    "(source_iid, target_uid, db_path, annotation_local_id, "
                    " created_at, subject_id) VALUES (1, 5, 'x', 'a', 1, 99)")
        finally:
            con.close()

    # M2302 ------------------------------------------------------------------
    def test_m2302_bestandsfall_verlustfrei(self):
        """
        Der Produktivfall: die Tabelle existiert bereits mit echten, teils noch
        offenen Querfunden. Die Migration darf davon NICHTS anfassen.
        """
        path, con = self._base_db()
        try:
            con.executescript(_LEGACY_PCA)
            bestand = [
                (1, 4711, "/x/evidence_4711.db", "a1", self.now - 300, None),
                (1, 90210, "/x/evidence_90210.db", "a2", self.now - 200,
                 self.now - 100),
                (2, 4711, "/x/evidence_4711.db", "a3", self.now - 50, None),
            ]
            con.executemany(
                "INSERT INTO pending_cross_annotations "
                "(source_iid, target_uid, db_path, annotation_local_id, "
                " created_at, integrated_at) VALUES (?, ?, ?, ?, ?, ?)",
                bestand)
            vorher = con.execute(
                "SELECT id, source_iid, target_uid, db_path, "
                "annotation_local_id, created_at, integrated_at "
                "FROM pending_cross_annotations ORDER BY id").fetchall()
            self.assertEqual(len(vorher), 3)

            self._run_chain(con)

            nachher = con.execute(
                "SELECT id, source_iid, target_uid, db_path, "
                "annotation_local_id, created_at, integrated_at "
                "FROM pending_cross_annotations ORDER BY id").fetchall()
            # Zeilenzahl UND jedes einzelne Feld unveraendert.
            self.assertEqual(len(nachher), len(vorher))
            for a, b in zip(vorher, nachher):
                self.assertEqual(tuple(a), tuple(b))

            # ... und die Angleichung greift fuer JEDE Zeile.
            paare = con.execute(
                "SELECT target_uid, subject_id FROM pending_cross_annotations "
                "ORDER BY id").fetchall()
            self.assertEqual([p["subject_id"] for p in paare],
                             [4711, 90210, 4711])
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM pending_cross_annotations "
                            "WHERE subject_id IS NOT target_uid").fetchone()[0],
                0)
        finally:
            con.close()

    # M2303 ------------------------------------------------------------------
    def test_m2303_idempotenz(self):
        path, con = self._base_db()
        try:
            self._run_chain(con)
            # Zweiter Lauf ueber dieselbe DB: der Runner ueberspringt bereits
            # angewandte Versionen; up() selbst ist zusaetzlich No-op-fest.
            self._run_chain(con)
            m023 = [m for m in discover(coordinator_migrations)
                    if m.VERSION == 23][0]
            m023.up(con)          # direkter Zweitaufruf — muss No-op sein
            m023.up(con)
            self.assertEqual(self._columns(con).count("subject_id"), 1)
        finally:
            con.close()

    # M2304 ------------------------------------------------------------------
    def test_m2304_echter_schreibpfad_fuellt_subject_id(self):
        """
        Kein Nachbau: hier schreibt der ECHTE Produktivpfad
        (CoordinatorDb.add_pending_cross_annotation). Er fuellt weiterhin nur
        'target_uid' — und SQLite leitet 'subject_id' ab. Genau deshalb ist
        eine Divergenz konstruktiv ausgeschlossen.
        """
        try:
            from db.coordinator_db import CoordinatorDb
        except ImportError as exc:                     # pragma: no cover
            self.skipTest("CoordinatorDb nicht importierbar: %s" % exc)

        path, con = self._base_db()
        try:
            self._run_chain(con)
        finally:
            con.close()

        # CoordinatorDb erwartet eine Verbindung mit ANGEBUNDENER cdb — genau
        # die ATTACH-Struktur des Normalmodus (db/connection_manager.py:15).
        # Nachgebaut wie in tests/test_coordinator_db.py, damit hier der ECHTE
        # Produktivpfad laeuft und kein Nachbau.
        main_con = sqlite3.connect(":memory:")
        main_con.row_factory = sqlite3.Row
        main_con.execute("ATTACH DATABASE '%s' AS cdb" % path)
        try:
            cdb = CoordinatorDb(main_con)
            new_id = cdb.add_pending_cross_annotation(
                source_iid=1, target_uid=123456,
                db_path="/x/evidence_123456.db", annotation_local_id="neu1")
            self.assertGreater(new_id, 0)
        finally:
            main_con.close()

        chk = sqlite3.connect(path)
        try:
            chk.row_factory = sqlite3.Row
            row = chk.execute(
                "SELECT target_uid, subject_id FROM pending_cross_annotations "
                "WHERE annotation_local_id='neu1'").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["target_uid"], 123456)
            self.assertEqual(row["subject_id"], 123456)
        finally:
            chk.close()

    # M2305 ------------------------------------------------------------------
    def test_m2305_registry_eintrag(self):
        path, con = self._base_db()
        try:
            self._run_chain(con)
            row = con.execute(
                "SELECT version, name, kind FROM schema_migrations "
                "WHERE version = 23").fetchone()
            self.assertIsNotNone(row, "M023 fehlt in schema_migrations")
            self.assertEqual(row["kind"], "additive")
            self.assertIn("subject_id", row["name"])
        finally:
            con.close()

    # M2306 ------------------------------------------------------------------
    def test_m2306_ausgabeform_vor_und_nach_der_migration(self):
        """
        Die Ausgabeform des Repos darf sich durch M023 NICHT aendern — sonst
        waere das Frontend aus Build 478 still kaputtgegangen.
        """
        # (a) Alt-Zustand: Kette nur bis M022, Tabelle in der Legacy-Form.
        path_a, con_a = self._base_db("alt.db")
        try:
            self._run_chain(con_a, upto=22)
            con_a.executescript(_LEGACY_PCA)
            con_a.execute(
                "INSERT INTO pending_cross_annotations "
                "(source_iid, target_uid, db_path, annotation_local_id, "
                " created_at) VALUES (1, 4711, '/x/e.db', 'a1', ?)",
                (self.now,))
            repo_a = CrossfindingsRepo(con_a)
            self.assertEqual(repo_a._subject_column(), "target_uid")
            alt = repo_a.list()
            counts_a = repo_a.counts()
        finally:
            con_a.close()

        # (b) Neu-Zustand: volle Kette inkl. M023.
        path_b, con_b = self._base_db("neu.db")
        try:
            self._run_chain(con_b)
            con_b.execute(
                "INSERT INTO pending_cross_annotations "
                "(source_iid, target_uid, db_path, annotation_local_id, "
                " created_at) VALUES (1, 4711, '/x/e.db', 'a1', ?)",
                (self.now,))
            repo_b = CrossfindingsRepo(con_b)
            self.assertEqual(repo_b._subject_column(), "subject_id")
            neu = repo_b.list()
            counts_b = repo_b.counts()
        finally:
            con_b.close()

        self.assertEqual(sorted(alt[0].keys()), sorted(neu[0].keys()))
        self.assertEqual(alt[0]["subject_id"], neu[0]["subject_id"])
        self.assertEqual(alt[0]["status"], neu[0]["status"])
        self.assertEqual(counts_a, counts_b)


if __name__ == "__main__":
    unittest.main()

# =============================================================================
# tests/test_crossfindings_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Querfunde (AP-2A)
# =============================================================================
# Testsuite fuer Build 474: CrossfindingsRepo (rein lesende Querfund-Uebersicht).
#
# CR01 — list(): target_uid -> subject_id normalisiert; Status offen/integriert;
#        Reihenfolge offene zuerst, dann neueste zuerst.
# CR02 — only_open filtert auf noch nicht integrierte Funde.
# CR03 — Join auf person (source_name); nicht zuordenbarer source_iid ->
#        source_name None, Zeile bleibt sichtbar (Grundregel 1).
# CR04 — counts(): total/offen/integriert.
# CR05 — Substrat fehlt -> CrossrefError (kein stiller Leerbefund). SEIT
#        BUILD 506 (M023) legt die MIGRATIONSKETTE die Tabelle selbst an, der
#        Fall kann in einer migrierten coordinator.db also nicht mehr
#        eintreten. Der Waechter bleibt trotzdem noetig (und getestet) fuer
#        eine DB, die die Kette NIE gelaufen ist — der Test baut dafuer jetzt
#        ausdruecklich eine solche DB. Er wird NICHT geloescht: ein
#        entfernter Waechter waere genau der stille Leerbefund, den
#        Grundregel 1 verbietet.
# CR06 — VERTRAEGLICHKEIT (Build 506): eine coordinator.db im ALT-Zustand
#        (Tabelle ohne die generierte Spalte 'subject_id') wird weiterhin
#        gelesen; die Ausgabeform ist identisch.
#
# Version: v0.8.506 · Build: 506 · 2026-07-24 (M023: Substrat kommt aus der
#          Kette; _mk_pca ist dadurch ein No-op, CR05 baut eine eigene DB)
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
from management.crossref.identified_subject_repo import CrossrefError
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

_PCA = """
CREATE TABLE pending_cross_annotations (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    source_iid           INTEGER NOT NULL,
    target_uid           INTEGER NOT NULL,
    db_path              TEXT    NOT NULL,
    annotation_local_id  TEXT    NOT NULL,
    created_at           INTEGER NOT NULL,
    integrated_at        INTEGER DEFAULT NULL
)
"""


class CrossfindingsRepoTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        now = int(time.time())
        con.execute(_PERSON)
        con.execute(
            "INSERT INTO person (id, system_username, display_name, created_at) "
            "VALUES (1, 'h001', 'Ermittler Eins', ?)", (now,))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con
        self.now = now

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

    def _mk_pca(self):
        """
        Frueher legte dieser Helfer 'pending_cross_annotations' an. SEIT
        MIGRATION M023 (Build 506) bringt die Kette die Tabelle bereits mit —
        ein zweites CREATE liefe auf 'table already exists'. Der Helfer bleibt
        als benannte Stelle erhalten (er dokumentiert, welche Tests das
        Substrat brauchen) und stellt seine Vorbedingung jetzt nur noch SICHER,
        statt sie zu erzeugen.
        """
        present = self.con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='pending_cross_annotations'").fetchone()
        self.assertIsNotNone(
            present,
            "pending_cross_annotations fehlt — M023 haette sie anlegen muessen.")

    def _add(self, sid, iid, local_id, created, integrated=None):
        self.con.execute(
            "INSERT INTO pending_cross_annotations "
            "(source_iid, target_uid, db_path, annotation_local_id, "
            " created_at, integrated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (iid, sid, "/x/evidence_%d_%d.db" % (sid, iid), local_id,
             created, integrated))

    # CR01 -------------------------------------------------------------------
    def test_cr01_list_normalisiert_und_ordnet(self):
        self._mk_pca()
        self._add(700, 1, "a1", self.now - 100)                 # offen, aelter
        self._add(701, 1, "a2", self.now - 10)                  # offen, neuer
        self._add(702, 1, "a3", self.now - 5, self.now)         # integriert
        repo = CrossfindingsRepo(self.con)
        rows = repo.list()
        self.assertEqual(len(rows), 3)
        # target_uid -> subject_id
        self.assertTrue(all("subject_id" in r and "target_uid" not in r
                            for r in rows))
        # Offene zuerst (neueste offen vor aelterer offen), integrierte zuletzt.
        self.assertEqual([r["subject_id"] for r in rows], [701, 700, 702])
        self.assertEqual(rows[0]["status"], "offen")
        self.assertEqual(rows[2]["status"], "integriert")
        self.assertIsNone(rows[0]["integrated_at"])
        self.assertIsNotNone(rows[2]["integrated_at"])

    # CR02 -------------------------------------------------------------------
    def test_cr02_only_open(self):
        self._mk_pca()
        self._add(1, 1, "o", self.now - 10)
        self._add(2, 1, "i", self.now - 5, self.now)
        repo = CrossfindingsRepo(self.con)
        opened = repo.list(only_open=True)
        self.assertEqual([r["subject_id"] for r in opened], [1])
        self.assertEqual(len(repo.list()), 2)

    # CR03 -------------------------------------------------------------------
    def test_cr03_join_und_grundregel1(self):
        self._mk_pca()
        self._add(50, 1, "known", self.now)     # source_iid 1 -> "Ermittler Eins"
        self._add(51, 999, "orphan", self.now)  # source_iid 999 -> nicht zuordenbar
        repo = CrossfindingsRepo(self.con)
        by_sid = {r["subject_id"]: r for r in repo.list()}
        self.assertEqual(by_sid[50]["source_name"], "Ermittler Eins")
        # Verwaiste Zeile bleibt sichtbar, nur ohne Namen (Grundregel 1).
        self.assertIn(51, by_sid)
        self.assertIsNone(by_sid[51]["source_name"])
        self.assertEqual(by_sid[51]["source_iid"], 999)

    # CR04 -------------------------------------------------------------------
    def test_cr04_counts(self):
        self._mk_pca()
        self._add(1, 1, "a", self.now)
        self._add(2, 1, "b", self.now)
        self._add(3, 1, "c", self.now, self.now)
        c = CrossfindingsRepo(self.con).counts()
        self.assertEqual(c, {"total": 3, "offen": 2, "integriert": 1})

    # CR05 -------------------------------------------------------------------
    def test_cr05_substrat_fehlt_wirft(self):
        """
        Der Waechter gegen den stillen Leerbefund. Seit M023 (Build 506) legt
        die Migrationskette das Substrat selbst an — deshalb wird hier
        ausdruecklich eine coordinator.db OHNE gelaufene Kette gebaut, damit
        der Fall ueberhaupt eintreten kann. Genau so bleibt belegt, dass ein
        fehlendes Substrat als BETRIEBSFEHLER (503/Exception) und nicht als
        "keine Querfunde" erscheint.
        """
        bare_path = os.path.join(self._tmp, "bare.db")
        bare = sqlite3.connect(bare_path)
        try:
            bare.row_factory = sqlite3.Row
            repo = CrossfindingsRepo(bare)
            with self.assertRaises(CrossrefError):
                repo.list()
            with self.assertRaises(CrossrefError):
                repo.counts()
        finally:
            bare.close()

    # CR06 -------------------------------------------------------------------
    def test_cr06_vertraeglichkeit_ohne_generierte_spalte(self):
        """
        Build 506: eine coordinator.db im ALT-Zustand (Tabelle vorhanden, aber
        ohne die generierte Spalte 'subject_id') muss weiterhin lesbar sein —
        das Repo faellt belegt auf 'target_uid' zurueck. Die AUSGABEFORM ist in
        beiden Faellen identisch, damit das Frontend aus Build 478 unveraendert
        gueltig bleibt.
        """
        alt_path = os.path.join(self._tmp, "alt.db")
        alt = sqlite3.connect(alt_path)
        try:
            alt.row_factory = sqlite3.Row
            alt.execute(_PERSON)
            alt.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "created_at) VALUES (1, 'h001', 'Ermittler Eins', ?)",
                (self.now,))
            alt.execute("CREATE TABLE cases (subject_id INTEGER)")
            alt.execute(_PCA)          # ALTE Form: nur target_uid
            alt.execute(
                "INSERT INTO pending_cross_annotations "
                "(source_iid, target_uid, db_path, annotation_local_id, "
                " created_at) VALUES (1, 4711, '/x/e.db', 'a1', ?)",
                (self.now,))
            alt.commit()

            repo = CrossfindingsRepo(alt)
            self.assertEqual(repo._subject_column(), "target_uid")
            rows = repo.list()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["subject_id"], 4711)
            self.assertEqual(rows[0]["status"], "offen")
            self.assertEqual(repo.counts()["total"], 1)
        finally:
            alt.close()

        # ... und im NEUEN Zustand (Kette gelaufen) ist es die generierte
        # Spalte — derselbe Ausgabename, andere Quelle.
        self._mk_pca()
        self.assertEqual(CrossfindingsRepo(self.con)._subject_column(),
                         "subject_id")


if __name__ == "__main__":
    unittest.main()

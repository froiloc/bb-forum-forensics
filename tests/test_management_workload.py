# =============================================================================
# tests/test_management_workload.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 335: WorkloadRepo (Ermittler-Lastverteilung, Aufrollung
# der belegten Fall-Klassifikation je assigned_to + Rueckstau + Aktivitaet).
#
# WL01 — Rollup je Ermittler: 2x gruen (closed/approved) -> done=2, total=2
# WL02 — Ampel je Ermittler: rot(idle-lang)+gelb(idle-mittel)+gruen(aktiv),
#        active=3, total=3 (Ampel deckungsgleich mit Dashboard)
# WL03 — Ermittler ohne Faelle erscheint mit 0-Last (Grundregel 1)
# WL04 — Rueckstau-Zeile (is_backlog) zaehlt unzugewiesene Faelle
# WL05 — Rueckstau steht am Ende der Liste
# WL06 — Ordnung: Ermittler nach ROT absteigend, Rueckstau zuletzt
# WL07 — Aktivitaets-Beleg aus audit_log unabhaengig von der Last
# WL08 — Namensaufloesung (system_username/display_name je Ermittler)
# WL09 — fehlende Pflichttabelle -> WorkloadSchemaError (handlungsleitend)
# WL10 — kein Fall verloren: Summe total_cases (inkl. Rueckstau) == Fallzahl
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
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
from management.cases.cases_repo import CasesRepo
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.workload.investigator_load import BACKLOG_LABEL
from management.workload.workload_repo import WorkloadRepo, WorkloadSchemaError

_INVESTIGATORS = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0,
    is_support INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
)
"""
_OLD_SCRAPE_JOBS = """
CREATE TABLE scrape_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL, username TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','running','done','failed')),
    manifest_path TEXT, output_path TEXT, worker_id TEXT,
    created_at INTEGER NOT NULL, started_at INTEGER, finished_at INTEGER,
    error_message TEXT, assigned_to INTEGER, note TEXT,
    FOREIGN KEY(assigned_to) REFERENCES person(id)
)
"""
_DAY = 86400


class WorkloadRepoTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")

        self.NOW = int(time.time())
        self.con.execute(_INVESTIGATORS)
        self.con.executemany(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(1, "h001", "Alpha", 1, 0, 0, self.NOW),
             (2, "h002", "Beta", 1, 1, 0, self.NOW),
             (3, "h003", "Gamma", 0, 0, 1, self.NOW)],
        )
        self.con.execute(_OLD_SCRAPE_JOBS)
        self.audit = AuditLog(self.con)
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="t").run()
        self.writer = CoordinatorWriter(self.con, self.audit)
        self.cases = CasesRepo(self.con, self.writer)

        # Alle Schreibaktionen mit actor_id=1 -> nur h001 sammelt Audit-Aktivitaet
        # (Last und Aktivitaet sind bewusst unabhaengig testbar).
        A = 1
        # Ermittler 1 (h001): 2x gruen (closed/approved).
        self.cases.create_case(subject_id=1001, username="c_closed", actor_id=A)
        self.cases.assign(1001, 1, actor_id=A)
        self.cases.set_status(1001, "closed", actor_id=A)
        self.cases.create_case(subject_id=1002, username="c_appr", actor_id=A)
        self.cases.assign(1002, 1, actor_id=A)
        self.cases.set_status(1002, "approved", actor_id=A)

        # Ermittler 2 (h002): rot (idle-lang), gelb (idle-mittel), gruen (aktiv).
        self.cases.create_case(subject_id=2001, username="c_rot", actor_id=A)
        self.cases.assign(2001, 2, actor_id=A)               # bleibt 'open'
        self.cases.create_case(subject_id=2002, username="c_gelb", actor_id=A)
        self.cases.assign(2002, 2, actor_id=A)               # bleibt 'open'
        self.cases.create_case(subject_id=2003, username="c_prog", actor_id=A)
        self.cases.assign(2003, 2, actor_id=A)
        self.cases.set_status(2003, "in_progress", actor_id=A)

        # Rueckstau (unzugewiesen): open -> rot (Regel: open & unassigned),
        # closed -> gruen.
        self.cases.create_case(subject_id=9001, username="b_open", actor_id=A)
        self.cases.create_case(subject_id=9002, username="b_closed", actor_id=A)
        self.cases.set_status(9002, "closed", actor_id=A)

        # Zeitstempel gezielt altern, um Ampel deterministisch zu erzwingen
        # (updated_at UND case_events, da last_activity = max(beide)).
        self._age(2001, self.NOW - 30 * _DAY)   # idle 30d > red(21) -> rot
        self._age(2002, self.NOW - 10 * _DAY)   # idle 10d in [7,21) -> gelb
        self._age(2003, self.NOW)               # idle 0 -> gruen (aktiv)

    def _age(self, subject_id, ts):
        self.con.execute("UPDATE cases SET updated_at=? WHERE subject_id=?",
                         (ts, subject_id))
        self.con.execute("UPDATE case_events SET created_at=? WHERE subject_id=?",
                         (ts, subject_id))

    def tearDown(self):
        self.con.close()
        for root, _d, files in os.walk(self._tmp, topdown=False):
            for fn in files:
                try:
                    os.remove(os.path.join(root, fn))
                except OSError:
                    pass
            os.rmdir(root)

    def _load(self):
        return WorkloadRepo(self.con).list_workload(now=self.NOW)

    def _by_id(self, rows):
        return {r.investigator_id: r for r in rows}

    def test_wl01_investigator_gruen_rollup(self):
        by = self._by_id(self._load())
        h001 = by[1]
        self.assertEqual(h001.total_cases, 2)
        self.assertEqual(h001.ampel_gruen, 2)
        self.assertEqual(h001.ampel_rot, 0)
        self.assertEqual(h001.status_closed, 1)
        self.assertEqual(h001.status_approved, 1)
        self.assertEqual(h001.done_cases, 2)
        self.assertEqual(h001.active_cases, 0)

    def test_wl02_investigator_ampel_mix(self):
        h002 = self._by_id(self._load())[2]
        self.assertEqual(h002.total_cases, 3)
        self.assertEqual(h002.ampel_rot, 1)     # idle-lang
        self.assertEqual(h002.ampel_gelb, 1)    # idle-mittel
        self.assertEqual(h002.ampel_gruen, 1)   # aktiv
        self.assertEqual(h002.active_cases, 3)  # 2x open + 1x in_progress
        self.assertEqual(h002.done_cases, 0)

    def test_wl03_investigator_without_cases(self):
        h003 = self._by_id(self._load())[3]
        self.assertEqual(h003.total_cases, 0)
        self.assertEqual(h003.active_cases, 0)
        self.assertFalse(h003.is_backlog)       # echter Ermittler, nur 0-Last

    def test_wl04_backlog_counts(self):
        rows = self._load()
        backlog = [r for r in rows if r.is_backlog]
        self.assertEqual(len(backlog), 1)
        b = backlog[0]
        self.assertEqual(b.total_cases, 2)      # 9001 + 9002
        self.assertEqual(b.ampel_rot, 1)        # open & unassigned -> rot
        self.assertEqual(b.ampel_gruen, 1)      # closed -> gruen
        self.assertEqual(b.system_username, BACKLOG_LABEL)

    def test_wl05_backlog_last(self):
        rows = self._load()
        self.assertTrue(rows[-1].is_backlog)
        self.assertFalse(any(r.is_backlog for r in rows[:-1]))

    def test_wl06_order_rot_desc(self):
        rows = self._load()
        people = [r for r in rows if not r.is_backlog]
        # h002 (rot=1) muss vor h001/h003 (rot=0) stehen.
        self.assertEqual(people[0].investigator_id, 2)

    def test_wl07_activity_independent_of_load(self):
        by = self._by_id(self._load())
        # h001 war Akteur aller Schreibvorgaenge -> Aktivitaet > 0.
        self.assertGreater(by[1].audit_action_count, 0)
        self.assertIsNotNone(by[1].last_action_at)
        # h002 traegt Last, war aber NIE Akteur -> Aktivitaet 0 (unabhaengig).
        self.assertEqual(by[2].audit_action_count, 0)
        self.assertIsNone(by[2].last_action_at)
        # h003 ohne alles.
        self.assertEqual(by[3].audit_action_count, 0)

    def test_wl08_name_resolution(self):
        by = self._by_id(self._load())
        self.assertEqual(by[1].system_username, "h001")
        self.assertEqual(by[1].display_name, "Alpha")
        self.assertEqual(by[3].display_name, "Gamma")

    def test_wl09_schema_guard(self):
        p = os.path.join(self._tmp, "bare.db")
        con = sqlite3.connect(p)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        AuditLog.create_schema(con)
        with con:
            con.execute("BEGIN IMMEDIATE")
            AuditLog(con).write_genesis({"v": 1})
            con.execute("COMMIT")
        try:
            with self.assertRaises(WorkloadSchemaError):
                WorkloadRepo(con).list_workload()
        finally:
            con.close()

    def test_wl10_no_case_lost(self):
        rows = self._load()
        total = sum(r.total_cases for r in rows)
        # 2 (h001) + 3 (h002) + 0 (h003) + 2 (Rueckstau) = 7 angelegte Faelle.
        self.assertEqual(total, 7)


if __name__ == "__main__":
    unittest.main()

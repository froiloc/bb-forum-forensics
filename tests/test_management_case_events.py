# =============================================================================
# tests/test_management_case_events.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite für Build 313: M004 (case_events), CaseEventsRepo, Spiegelung
# der cases-Writes, after_audit-Hook des Gateways.
#
# E01 — M004 via discover+Runner (M001..M004) angewandt; 2. Lauf No-Op;
#       Tabelle + Index existieren
# E02 — add_manual_event: Zeitstrahl-Zeile kind='manual' + Beleg
#       CASE_EVENT_ADDED atomar; audit_seq der Zeile == Rückgabe-seq;
#       Text NICHT im Audit-Payload (nur text_len), Text IM Zeitstrahl-Payload
# E03 — create_case spiegelt 'case_created' mit audit_seq des CASE_CREATED-Belegs
# E04 — assign spiegelt 'assigned' (Payload assigned_to)
# E05 — set_status('in_progress') spiegelt 'status_changed'
# E06 — set_status('approved') spiegelt 'approved' (Payload approved_at gesetzt)
# E07 — set_priority/set_note erzeugen BEWUSST KEINE Zeitstrahl-Zeile
# E08 — Rollback (CHECK-Verletzung ungültiger Status): weder cases-Änderung
#       noch Audit-Eintrag noch Zeitstrahl-Zeile (Atomarität über den Hook)
# E09 — add_manual_event auf unbekannten Fall -> CaseEventsError, kein
#       Audit-Eintrag, keine Zeile; leerer Text -> CaseEventsError
# E10 — list_events: chronologisch (Tie-Break id), nur eigener Fall,
#       created_by als system_username aufgelöst, payload als dict
# E11 — verify_chain OK nach allen Writes (Kette unversehrt)
# E12 — insert_event_row mit unbekanntem event_kind -> CaseEventsError,
#       via Gateway-Rollback bleibt NICHTS zurück (kein Teilzustand)
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import json
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
from management.audit.event_types import EventType
from management.case_events.case_events_repo import (
    CaseEventsError,
    CaseEventsRepo,
    insert_event_row,
)
from management.cases.cases_repo import CasesError, CasesRepo
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover

_INVESTIGATORS = """
CREATE TABLE person (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    system_username TEXT    NOT NULL UNIQUE,
    display_name    TEXT    NOT NULL,
    is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor   INTEGER NOT NULL DEFAULT 0,
    is_support      INTEGER NOT NULL DEFAULT 0,
    created_at      INTEGER NOT NULL
)
"""

# Alte scrape_jobs-Form (Ausgangszustand vor M002), damit der Rebuild von
# M002 im vollen M001..M004-Lauf denselben Weg geht wie in PROD.
_OLD_SCRAPE_JOBS = """
CREATE TABLE scrape_jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    username      TEXT    NOT NULL,
    priority      INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status        TEXT    NOT NULL DEFAULT 'pending'
                  CHECK(status IN ('pending','running','done','failed')),
    manifest_path TEXT,
    output_path   TEXT,
    worker_id     TEXT,
    created_at    INTEGER NOT NULL,
    started_at    INTEGER,
    finished_at   INTEGER,
    error_message TEXT,
    assigned_to   INTEGER,
    note          TEXT,
    FOREIGN KEY(assigned_to) REFERENCES person(id)
)
"""


class ManagementCaseEventsTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")

        now = int(time.time())
        self.con.execute(_INVESTIGATORS)
        self.con.executemany(
            "INSERT INTO person "
            "(id, system_username, display_name, is_investigator, is_supervisor, "
            " is_support, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(1, "h001", "Alpha", 1, 1, 0, now),
             (2, "h002", "Beta", 1, 0, 0, now)],
        )
        self.con.execute(_OLD_SCRAPE_JOBS)

        # Vollständiger Migrationslauf über discover() — exakt der PROD-Weg
        # (migrate.py). Erwartet M001..M004.
        self.audit = AuditLog(self.con)
        self.mods = discover(coordinator_migrations)
        self.runner = MigrationRunner(
            self.con, self.mods, audit=self.audit, deployed_by="tester",
        )
        self.applied = self.runner.run()

        self.writer = CoordinatorWriter(self.con, self.audit)
        self.cases = CasesRepo(self.con, self.writer)
        self.events = CaseEventsRepo(self.con, self.writer)

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

    # Helfer -----------------------------------------------------------------
    def _rows(self, subject_id):
        return self.con.execute(
            "SELECT * FROM case_events WHERE subject_id = ? "
            "ORDER BY created_at ASC, id ASC", (subject_id,)
        ).fetchall()

    def _audit_count(self, event_type=None):
        if event_type is None:
            return self.con.execute(
                "SELECT COUNT(*) FROM audit_log").fetchone()[0]
        return self.con.execute(
            "SELECT COUNT(*) FROM audit_log WHERE event_type = ?",
            (event_type,)).fetchone()[0]

    # E01 ---------------------------------------------------------------------
    def test_e01_migration_m004_applied_idempotent(self):
        self.assertIn(4, self.applied)
        # Tabelle + Index vorhanden.
        self.assertIsNotNone(self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='case_events'").fetchone())
        self.assertIsNotNone(self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='case_events_subject_time_idx'").fetchone())
        # Zweiter Lauf: No-Op.
        second = MigrationRunner(
            self.con, self.mods, audit=self.audit, deployed_by="tester",
        ).run()
        self.assertEqual(second, [])

    # E02 ---------------------------------------------------------------------
    def test_e02_manual_event_atomic_and_sensitive(self):
        self.cases.create_case(18, "KEKa")
        seq = self.events.add_manual_event(
            18, "Hinweis: PGP-Key im Profil", actor_id=1)
        rows = [r for r in self._rows(18) if r["event_kind"] == "manual"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        # audit_seq der Zeile == zurückgegebene Beleg-seq.
        self.assertEqual(row["audit_seq"], seq)
        self.assertEqual(row["created_by"], 1)
        # Text IM Zeitstrahl-Payload ...
        self.assertEqual(json.loads(row["payload"])["text"],
                         "Hinweis: PGP-Key im Profil")
        # ... aber NICHT im Audit-Payload (nur text_len; Sensibilitätsregel).
        arow = self.con.execute(
            "SELECT content FROM audit_log WHERE seq = ?", (seq,)).fetchone()
        content = json.loads(arow["content"])
        self.assertNotIn("text", content)
        self.assertEqual(content["text_len"], len("Hinweis: PGP-Key im Profil"))
        self.assertEqual(
            self._audit_count(EventType.CASE_EVENT_ADDED), 1)

    # E03 ---------------------------------------------------------------------
    def test_e03_create_case_mirrors_timeline(self):
        seq = self.cases.create_case(18, "KEKa", actor_id=1)
        rows = self._rows(18)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_kind"], "case_created")
        self.assertEqual(rows[0]["audit_seq"], seq)
        self.assertEqual(json.loads(rows[0]["payload"])["username"], "KEKa")

    # E04 ---------------------------------------------------------------------
    def test_e04_assign_mirrors_timeline(self):
        self.cases.create_case(18, "KEKa")
        seq = self.cases.assign(18, 2, actor_id=1)
        rows = [r for r in self._rows(18) if r["event_kind"] == "assigned"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["audit_seq"], seq)
        self.assertEqual(json.loads(rows[0]["payload"])["assigned_to"], 2)

    # E05 ---------------------------------------------------------------------
    def test_e05_status_change_mirrors_timeline(self):
        self.cases.create_case(18, "KEKa")
        seq = self.cases.set_status(18, "in_progress", actor_id=1)
        rows = [r for r in self._rows(18) if r["event_kind"] == "status_changed"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["audit_seq"], seq)
        self.assertEqual(json.loads(rows[0]["payload"])["status"], "in_progress")

    # E06 ---------------------------------------------------------------------
    def test_e06_approved_mirrors_timeline(self):
        self.cases.create_case(18, "KEKa")
        seq = self.cases.set_status(18, "approved", actor_id=1)
        rows = [r for r in self._rows(18) if r["event_kind"] == "approved"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["audit_seq"], seq)
        payload = json.loads(rows[0]["payload"])
        self.assertEqual(payload["status"], "approved")
        self.assertIsInstance(payload["approved_at"], int)

    # E07 ---------------------------------------------------------------------
    def test_e07_priority_and_note_not_mirrored(self):
        self.cases.create_case(18, "KEKa")
        before = len(self._rows(18))
        self.cases.set_priority(18, 1)
        self.cases.set_note(18, "interne Notiz")
        self.assertEqual(len(self._rows(18)), before,
                         "set_priority/set_note dürfen keine Zeitstrahl-"
                         "Zeilen erzeugen (Bauplan B7 v0.8 §8.4)")

    # E08 ---------------------------------------------------------------------
    def test_e08_rollback_leaves_nothing(self):
        self.cases.create_case(18, "KEKa")
        audits = self._audit_count()
        rows = len(self._rows(18))
        with self.assertRaises(sqlite3.IntegrityError):
            self.cases.set_status(18, "kaputt")  # CHECK-Verletzung
        self.assertEqual(self._audit_count(), audits)
        self.assertEqual(len(self._rows(18)), rows)
        self.assertEqual(self.cases.get_case(18)["status"], "open")

    # E09 ---------------------------------------------------------------------
    def test_e09_manual_event_validation(self):
        audits = self._audit_count()
        with self.assertRaises(CaseEventsError):
            self.events.add_manual_event(999, "Fall existiert nicht")
        self.assertEqual(self._audit_count(), audits,
                         "abgewiesener Eintrag darf keinen Audit hinterlassen")
        self.assertEqual(self._rows(999), [])
        self.cases.create_case(18, "KEKa")
        with self.assertRaises(CaseEventsError):
            self.events.add_manual_event(18, "   ")

    # E10 ---------------------------------------------------------------------
    def test_e10_list_events_order_scope_resolution(self):
        self.cases.create_case(18, "KEKa", actor_id=1)
        self.cases.create_case(19, "LMN")
        self.cases.assign(18, 2, actor_id=1)
        self.events.add_manual_event(18, "Notiz A", actor_id=2)
        listed = self.events.list_events(18)
        # Nur Fall 18; chronologisch mit id-Tie-Break (Writes sind
        # sekundengleich möglich -> Reihenfolge über id garantiert).
        self.assertEqual([e["event_kind"] for e in listed],
                         ["case_created", "assigned", "manual"])
        self.assertTrue(all(e["subject_id"] == 18 for e in listed))
        # created_by aufgelöst; payload als dict.
        self.assertEqual(listed[0]["created_by_username"], "h001")
        self.assertEqual(listed[2]["created_by_username"], "h002")
        self.assertEqual(listed[2]["payload"], {"text": "Notiz A"})
        # limit greift.
        self.assertEqual(len(self.events.list_events(18, limit=2)), 2)
        # Fremder Fall nur mit eigenem Anker.
        self.assertEqual(len(self.events.list_events(19)), 1)

    # E11 ---------------------------------------------------------------------
    def test_e11_chain_valid_after_all_writes(self):
        self.cases.create_case(18, "KEKa", actor_id=1)
        self.cases.assign(18, 2, actor_id=1)
        self.cases.set_status(18, "in_progress", actor_id=2)
        self.cases.set_status(18, "approved", actor_id=1)
        self.events.add_manual_event(18, "Bericht begonnen", actor_id=2)
        result = self.audit.verify_chain()
        self.assertTrue(result.ok, "Audit-Kette muss nach allen Writes "
                                   "verifizierbar sein: %r" % (result,))

    # E12 ---------------------------------------------------------------------
    def test_e12_unknown_kind_rejected_atomically(self):
        self.cases.create_case(18, "KEKa")
        audits = self._audit_count()
        rows = len(self._rows(18))

        def _w(con):
            return {"probe": True}

        def _after(con, seq):
            insert_event_row(
                con, subject_id=18, event_kind="ufo", payload=None,
                created_by=None, created_at=int(time.time()), audit_seq=seq,
            )

        with self.assertRaises(CaseEventsError):
            self.writer.audited_write(
                do_write=_w, event_type=EventType.CASE_EVENT_ADDED,
                actor_id=None, target_type="case", target_id="18",
                after_audit=_after,
            )
        # Hook-Fehler rollt ALLES zurück: weder Audit noch Zeile (Grundregel 1).
        self.assertEqual(self._audit_count(), audits)
        self.assertEqual(len(self._rows(18)), rows)


if __name__ == "__main__":
    unittest.main()

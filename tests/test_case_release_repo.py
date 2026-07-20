# =============================================================================
# tests/test_case_release_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Externe Fallfreigabe (AP-2G)
# =============================================================================
# Testsuite fuer Build 462: CaseReleaseRepo (auditierter Schreibpfad, M016).
#
# CR01 — grant(): auditiert; audit_seq/created_audit_seq gesetzt; FREITEXT
#        (Grundlage) NICHT im Payload; Empfaenger via AD aufgeloest (Anzeigename).
# CR02 — AD-DENY: unbekannter Empfaenger -> Fehler, KEINE Zeile.
# CR03 — Unbedenklichkeit Pflicht: leere Grundlage -> Fehler, KEINE Zeile.
# CR04 — unbekannter Fall -> Fehler (Rollback), KEINE Zeile.
# CR05 — revoke(): freigegeben->widerrufen (Grund Pflicht); erneuter Widerruf
#        scheitert (endgueltig) und die Zeile bleibt UNVERAENDERT (Rollback).
# CR06 — kein unauditierter Schreibpfad (ohne Writer) und keine Freigabe ohne
#        AD-Schicht.
# CR07 — list_releases(): Labels + Fall-Benutzername.
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
from management.cases.cases_repo import CasesRepo
from management.external.ad_directory import ADDirectory
from management.external.case_release_repo import (
    CaseReleaseError,
    CaseReleaseRepo,
)
from management.gateway.coordinator_writer import CoordinatorWriter
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


class CaseReleaseRepoTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        now = int(time.time())
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (1, 'chef', 'Chefin', 1, 1, 0, ?)", (now,))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con
        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        # Fall 18 anlegen (auditiert), damit der FK auf cases greift.
        CasesRepo(self.con, self.writer).create_case(18, "boarder18", actor_id=1)
        self.ad = ADDirectory(
            recipients={"h0b1234": "KHK Muster, PP Musterstadt"},
            group="SEC_16_03_EK-Zarewitsch-Extern")
        self.repo = CaseReleaseRepo(self.con, self.writer, ad=self.ad)

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

    def _row(self, release_id):
        return self.con.execute(
            "SELECT * FROM case_release WHERE id=?", (release_id,)).fetchone()

    def _count(self):
        return self.con.execute(
            "SELECT COUNT(*) FROM case_release").fetchone()[0]

    # CR01 -------------------------------------------------------------------
    def test_cr01_grant_audited_no_freetext(self):
        res = self.repo.grant(
            subject_id=18, recipient_kennung="H0B1234", umfang="bericht",
            unbedenklichkeit_grundlage="Bericht geschwaerzt, LKA-Freigabe 12/26",
            actor_id=1)
        self.assertGreater(res["audit_seq"], 0)
        self.assertEqual(res["recipient_kennung"], "h0b1234")  # kanonisch
        self.assertEqual(res["recipient_display"], "KHK Muster, PP Musterstadt")

        row = self._row(res["release_id"])
        self.assertEqual(row["status"], "freigegeben")
        self.assertEqual(row["recipient_display"], "KHK Muster, PP Musterstadt")
        self.assertEqual(row["audit_seq"], res["audit_seq"])
        self.assertEqual(row["created_audit_seq"], res["audit_seq"])

        ev = self.con.execute(
            "SELECT event_type, content FROM audit_log WHERE seq=?",
            (res["audit_seq"],)).fetchone()
        self.assertEqual(ev["event_type"], "case_release_granted")
        payload = json.loads(ev["content"])
        # FAKTEN ja (inkl. Empfaenger-Kennung), FREITEXT nein.
        self.assertEqual(payload["recipient_kennung"], "h0b1234")
        self.assertEqual(payload["umfang"], "bericht")
        self.assertIn("grundlage_len", payload)
        self.assertNotIn("unbedenklichkeit_grundlage", payload)

    # CR02 -------------------------------------------------------------------
    def test_cr02_ad_deny(self):
        with self.assertRaises(CaseReleaseError):
            self.repo.grant(subject_id=18, recipient_kennung="h0xxxxx",
                            umfang="bericht",
                            unbedenklichkeit_grundlage="x", actor_id=1)
        self.assertEqual(self._count(), 0)

    # CR03 -------------------------------------------------------------------
    def test_cr03_unbedenklichkeit_required(self):
        with self.assertRaises(CaseReleaseError):
            self.repo.grant(subject_id=18, recipient_kennung="h0b1234",
                            umfang="bericht",
                            unbedenklichkeit_grundlage="   ", actor_id=1)
        self.assertEqual(self._count(), 0)

    # CR04 -------------------------------------------------------------------
    def test_cr04_unknown_case_rollback(self):
        with self.assertRaises(CaseReleaseError):
            self.repo.grant(subject_id=999, recipient_kennung="h0b1234",
                            umfang="akte",
                            unbedenklichkeit_grundlage="ok", actor_id=1)
        self.assertEqual(self._count(), 0)

    # CR05 -------------------------------------------------------------------
    def test_cr05_revoke_and_finality(self):
        res = self.repo.grant(
            subject_id=18, recipient_kennung="h0b1234", umfang="akte",
            unbedenklichkeit_grundlage="freigegeben durch StA", actor_id=1)
        rid = res["release_id"]
        # Grund Pflicht.
        with self.assertRaises(CaseReleaseError):
            self.repo.revoke(rid, grund="  ", actor_id=1)
        seq = self.repo.revoke(rid, grund="Zustaendigkeit gewechselt", actor_id=1)
        row = dict(self._row(rid))
        self.assertEqual(row["status"], "widerrufen")
        self.assertEqual(row["revoke_audit_seq"], seq)
        self.assertEqual(row["revoked_by"], 1)
        # Erneuter Widerruf -> endgueltig; Zeile bleibt unveraendert (Rollback).
        before = dict(self._row(rid))
        with self.assertRaises(CaseReleaseError):
            self.repo.revoke(rid, grund="nochmal", actor_id=1)
        self.assertEqual(dict(self._row(rid)), before)

    # CR06 -------------------------------------------------------------------
    def test_cr06_guards(self):
        # ohne Writer -> kein Schreibpfad.
        ro = CaseReleaseRepo(self.con, ad=self.ad)
        with self.assertRaises(CaseReleaseError):
            ro.grant(subject_id=18, recipient_kennung="h0b1234", umfang="bericht",
                     unbedenklichkeit_grundlage="x", actor_id=1)
        # mit Writer, aber ohne AD -> keine Freigabe.
        no_ad = CaseReleaseRepo(self.con, self.writer)
        with self.assertRaises(CaseReleaseError):
            no_ad.grant(subject_id=18, recipient_kennung="h0b1234",
                        umfang="bericht",
                        unbedenklichkeit_grundlage="x", actor_id=1)

    # CR07 -------------------------------------------------------------------
    def test_cr07_list_releases(self):
        self.repo.grant(subject_id=18, recipient_kennung="h0b1234",
                        umfang="auszug",
                        unbedenklichkeit_grundlage="Teilauszug ok", actor_id=1)
        rows = self.repo.list_releases(subject_ids=[18])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fall_username"], "boarder18")
        self.assertEqual(rows[0]["umfang"], "auszug")
        self.assertIn("Teilauszug", rows[0]["umfang_label"])
        self.assertTrue(rows[0]["status_label"])


if __name__ == "__main__":
    unittest.main()

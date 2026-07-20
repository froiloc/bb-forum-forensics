# =============================================================================
# tests/test_identified_subject_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Identitaet (AP-2A)
# =============================================================================
# Testsuite fuer Build 468: IdentifiedSubjectRepo (auditierter Schreibpfad, M018).
#
# IR01 — upsert (Erstanlage): auditiert; audit_seq gesetzt; Ereignis
#        'subject_identity_set' mit created=True; SENSIBLER FREITEXT
#        (real_identity/basis/note) NICHT im Payload, nur Fakten + Laengen.
# IR02 — upsert (Revision Konfidenz): created=False; changes.confidence {alt,neu}.
# IR03 — upsert No-Op (identische Werte) -> CrossrefError, kein neuer Beleg.
# IR04 — get()/list(): Werte korrekt; confidence_ordinal eingefroren (10/20/30);
#        list() nach Konfidenz absteigend.
# IR05 — ungueltige Konfidenzstufe / leere real_identity -> CrossrefError.
# IR06 — Freitext-Revision (nur note): im Payload NUR note_len {alt,neu}, nie
#        der Inhalt.
# IR07 — kein unauditierter Schreibpfad (ohne Writer).
#
# Version: v0.7.468 · Build: 468 · 2026-07-20
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
from management.crossref.identified_subject_repo import (
    CrossrefError, IdentifiedSubjectRepo,
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

#: Sensibler Klartext, der niemals im Audit-Payload auftauchen darf.
_SECRET_NAME = "Max Mustermann, geb. 1970, Musterstadt"
_SECRET_BASIS = "Abgleich Klarname ueber Zahlungsdaten"
_SECRET_NOTE = "Quelle vertraulich — nicht in Akte"


class IdentifiedSubjectRepoTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        now = int(time.time())
        for pid, un, sup in ((1, "chef", 1), (2, "mueller", 0)):
            con.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?, ?, ?, 1, ?, 0, ?)", (pid, un, un.title(), sup, now))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con
        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.repo = IdentifiedSubjectRepo(self.con, self.writer)

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

    def _audit(self, seq):
        row = self.con.execute(
            "SELECT event_type, content FROM audit_log WHERE seq=?",
            (seq,)).fetchone()
        return row["event_type"], row["content"], json.loads(row["content"])

    # IR01 -------------------------------------------------------------------
    def test_ir01_create_audited_no_freetext(self):
        res = self.repo.upsert(
            subject_id=993008244, real_identity=_SECRET_NAME,
            confidence_code="wahrscheinlich", basis=_SECRET_BASIS,
            note=_SECRET_NOTE, actor_id=1)
        self.assertTrue(res["created"])
        self.assertGreater(res["audit_seq"], 0)

        row = self.con.execute(
            "SELECT * FROM identified_subject WHERE subject_id=993008244"
        ).fetchone()
        self.assertEqual(row["confidence_code"], "wahrscheinlich")
        self.assertEqual(row["confidence_ordinal"], 20)
        self.assertEqual(row["audit_seq"], res["audit_seq"])
        self.assertEqual(row["created_audit_seq"], res["audit_seq"])
        self.assertEqual(row["created_by"], 1)

        etype, raw, payload = self._audit(res["audit_seq"])
        self.assertEqual(etype, "subject_identity_set")
        self.assertTrue(payload["created"])
        self.assertEqual(payload["subject_id"], 993008244)
        self.assertEqual(payload["confidence_ordinal"], 20)
        # Nur Laengen, kein Inhalt.
        self.assertIn("real_identity_len", payload)
        self.assertNotIn("real_identity", payload)
        self.assertNotIn("basis", payload)
        self.assertNotIn("note", payload)
        # Kein sensibler Klartext im ROHEN Beleg (haerteste Pruefung).
        for secret in (_SECRET_NAME, _SECRET_BASIS, _SECRET_NOTE):
            self.assertNotIn(secret, raw)

    # IR02 -------------------------------------------------------------------
    def test_ir02_update_confidence(self):
        self.repo.upsert(subject_id=5, real_identity="A",
                         confidence_code="verdacht", actor_id=1)
        res = self.repo.upsert(subject_id=5, real_identity="A",
                               confidence_code="gesichert", actor_id=2)
        self.assertFalse(res["created"])
        row = self.con.execute(
            "SELECT * FROM identified_subject WHERE subject_id=5").fetchone()
        self.assertEqual(row["confidence_code"], "gesichert")
        self.assertEqual(row["confidence_ordinal"], 30)
        self.assertEqual(row["updated_by"], 2)
        self.assertEqual(row["created_by"], 1)  # unveraendert

        etype, _raw, payload = self._audit(res["audit_seq"])
        self.assertEqual(etype, "subject_identity_set")
        self.assertFalse(payload["created"])
        self.assertEqual(payload["changes"]["confidence"]["alt"], "verdacht")
        self.assertEqual(payload["changes"]["confidence"]["neu"], "gesichert")
        self.assertEqual(payload["changes"]["confidence"]["neu_ordinal"], 30)

    # IR03 -------------------------------------------------------------------
    def test_ir03_noop_raises(self):
        self.repo.upsert(subject_id=9, real_identity="A",
                         confidence_code="verdacht", basis="b", actor_id=1)
        before = self.con.execute(
            "SELECT MAX(seq) FROM audit_log").fetchone()[0]
        with self.assertRaises(CrossrefError):
            self.repo.upsert(subject_id=9, real_identity="A",
                             confidence_code="verdacht", basis="b", actor_id=1)
        after = self.con.execute(
            "SELECT MAX(seq) FROM audit_log").fetchone()[0]
        self.assertEqual(before, after)  # kein neuer Beleg

    # IR04 -------------------------------------------------------------------
    def test_ir04_get_list_ordinal_frozen(self):
        self.repo.upsert(subject_id=11, real_identity="Schwach",
                         confidence_code="verdacht", actor_id=1)
        self.repo.upsert(subject_id=12, real_identity="Stark",
                         confidence_code="gesichert", actor_id=1)
        self.repo.upsert(subject_id=13, real_identity="Mittel",
                         confidence_code="wahrscheinlich", actor_id=1)

        got = self.repo.get(12)
        self.assertEqual(got["real_identity"], "Stark")
        self.assertEqual(got["confidence_ordinal"], 30)
        self.assertIsNone(self.repo.get(999))

        listed = self.repo.list()
        self.assertEqual([r["subject_id"] for r in listed], [12, 13, 11])
        self.assertEqual([r["confidence_ordinal"] for r in listed],
                         [30, 20, 10])

    # IR05 -------------------------------------------------------------------
    def test_ir05_invalid_inputs(self):
        with self.assertRaises(CrossrefError):
            self.repo.upsert(subject_id=1, real_identity="A",
                             confidence_code="gerichtsfest", actor_id=1)
        with self.assertRaises(CrossrefError):
            self.repo.upsert(subject_id=1, real_identity="   ",
                             confidence_code="verdacht", actor_id=1)
        # Nichts wurde angelegt.
        self.assertIsNone(self.repo.get(1))

    # IR06 -------------------------------------------------------------------
    def test_ir06_freetext_update_length_only(self):
        self.repo.upsert(subject_id=8, real_identity="A",
                         confidence_code="verdacht", note="kurz", actor_id=1)
        res = self.repo.upsert(subject_id=8, real_identity="A",
                               confidence_code="verdacht",
                               note=_SECRET_NOTE, actor_id=1)
        etype, raw, payload = self._audit(res["audit_seq"])
        self.assertEqual(etype, "subject_identity_set")
        self.assertIn("note_len", payload["changes"])
        self.assertEqual(payload["changes"]["note_len"]["alt"], len("kurz"))
        self.assertEqual(payload["changes"]["note_len"]["neu"],
                         len(_SECRET_NOTE))
        self.assertNotIn(_SECRET_NOTE, raw)
        # Konfidenz unveraendert -> nicht in changes.
        self.assertNotIn("confidence", payload["changes"])

    # IR07 -------------------------------------------------------------------
    def test_ir07_no_unaudited_write(self):
        repo = IdentifiedSubjectRepo(self.con, writer=None)
        with self.assertRaises(CrossrefError):
            repo.upsert(subject_id=1, real_identity="A",
                        confidence_code="verdacht", actor_id=1)


if __name__ == "__main__":
    unittest.main()

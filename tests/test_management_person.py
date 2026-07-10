# =============================================================================
# tests/test_management_person.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite für Build 310: PersonRepo (Anlegen/Ändern/Listen) über das
# CoordinatorWriter-Gateway mit lückenloser Audit-Kette.
#
# C01 — create → Zeile angelegt + INVESTIGATOR_CREATED atomar
# C02 — create Duplikat (system_username) → Fehler, kein Row/Audit (Rollback)
# C03 — update display_name → Änderung + INVESTIGATOR_UPDATED (alt/neu im Payload)
# C04 — update Rollen-Flags (supervisor/support) → Änderung geschrieben
# C05 — update No-Op (gleiche Werte) → Fehler, kein Audit
# C06 — update unbekannter Ermittler → Fehler
# C07 — list_persons liefert alle, sortiert nach system_username
# C08 — get per id und per system_username
# C09 — verify_chain grün nach allen Writes
# C10 — kein Löschen: Stilllegen über is_investigator=0 (Zeile bleibt Beleg)
#
# Version: v0.7.310 · Build: 310 · 2026-07-01
# =============================================================================

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.audit.audit_log import AuditLog
from management.audit.event_types import EventType
from management.gateway.coordinator_writer import CoordinatorWriter
from management.person.person_repo import (
    PersonError,
    PersonRepo,
)

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


class ManagementInvestigatorsTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")

        # person-Tabelle + Audit-Kette (Schema + Genesis) aufsetzen.
        self.con.execute(_INVESTIGATORS)
        AuditLog.create_schema(self.con)
        self.audit = AuditLog(self.con)
        self.con.execute("BEGIN IMMEDIATE")
        self.audit.write_genesis({"note": "test-genesis"})
        self.con.execute("COMMIT")

        self.writer = CoordinatorWriter(self.con, self.audit)
        self.repo = PersonRepo(self.con, self.writer)

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
    def _investigator_count(self):
        return self.con.execute(
            "SELECT COUNT(*) AS c FROM person"
        ).fetchone()["c"]

    def _audit_count(self):
        return self.con.execute(
            "SELECT COUNT(*) AS c FROM audit_log"
        ).fetchone()["c"]

    def _last_audit(self):
        return self.con.execute(
            "SELECT event_type, target_type, target_id, content "
            "FROM audit_log ORDER BY seq DESC LIMIT 1"
        ).fetchone()

    # ------------------------------------------------------------------- C01
    def test_c01_create_row_and_audit(self):
        seq = self.repo.create("h001", "Alpha, Anna", is_supervisor=True)
        self.assertEqual(seq, 2)  # genesis=1, create=2
        row = self.con.execute(
            "SELECT * FROM person WHERE system_username='h001'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["display_name"], "Alpha, Anna")
        self.assertEqual(row["is_investigator"], 1)
        self.assertEqual(row["is_supervisor"], 1)
        self.assertEqual(row["is_support"], 0)
        last = self._last_audit()
        self.assertEqual(last["event_type"], EventType.INVESTIGATOR_CREATED)
        self.assertEqual(last["target_type"], "investigator")
        self.assertEqual(last["target_id"], "h001")

    # ------------------------------------------------------------------- C02
    def test_c02_create_duplicate_rolls_back(self):
        self.repo.create("h001", "Alpha")
        n_inv = self._investigator_count()
        n_aud = self._audit_count()
        with self.assertRaises(PersonError):
            self.repo.create("h001", "Alpha Zwei")
        # Rollback: weder zusätzliche person-Zeile noch Audit-Eintrag.
        self.assertEqual(self._investigator_count(), n_inv)
        self.assertEqual(self._audit_count(), n_aud)

    # ------------------------------------------------------------------- C03
    def test_c03_update_display_name(self):
        self.repo.create("h001", "Alt Name")
        seq = self.repo.update(system_username="h001",
                               display_name="Neu Name")
        row = self.con.execute(
            "SELECT display_name FROM person WHERE system_username='h001'"
        ).fetchone()
        self.assertEqual(row["display_name"], "Neu Name")
        last = self._last_audit()
        self.assertEqual(last["event_type"], EventType.INVESTIGATOR_UPDATED)
        payload = json.loads(last["content"])
        self.assertIn("display_name", payload["changes"])
        self.assertEqual(payload["changes"]["display_name"]["alt"], "Alt Name")
        self.assertEqual(payload["changes"]["display_name"]["neu"], "Neu Name")
        self.assertEqual(seq, 3)

    # ------------------------------------------------------------------- C04
    def test_c04_update_flags(self):
        self.repo.create("h001", "Alpha")
        self.repo.update(system_username="h001",
                         is_supervisor=True, is_support=True)
        row = self.con.execute(
            "SELECT is_supervisor, is_support FROM person "
            "WHERE system_username='h001'"
        ).fetchone()
        self.assertEqual(row["is_supervisor"], 1)
        self.assertEqual(row["is_support"], 1)
        payload = json.loads(self._last_audit()["content"])
        self.assertIn("is_supervisor", payload["changes"])
        self.assertIn("is_support", payload["changes"])

    # ------------------------------------------------------------------- C05
    def test_c05_update_noop_raises_no_audit(self):
        self.repo.create("h001", "Alpha")
        n_aud = self._audit_count()
        with self.assertRaises(PersonError):
            # display_name identisch -> keine Änderung
            self.repo.update(system_username="h001", display_name="Alpha")
        self.assertEqual(self._audit_count(), n_aud)

    # ------------------------------------------------------------------- C06
    def test_c06_update_unknown_raises(self):
        with self.assertRaises(PersonError):
            self.repo.update(system_username="gibtsnicht",
                             display_name="X")

    # ------------------------------------------------------------------- C07
    def test_c07_list_sorted(self):
        self.repo.create("h003", "Cee")
        self.repo.create("h001", "Ayy")
        self.repo.create("h002", "Bee")
        rows = self.repo.list_persons()
        self.assertEqual([r["system_username"] for r in rows],
                         ["h001", "h002", "h003"])

    # ------------------------------------------------------------------- C08
    def test_c08_get_by_id_and_username(self):
        self.repo.create("h001", "Alpha")
        by_name = self.repo.get(system_username="h001")
        self.assertIsNotNone(by_name)
        by_id = self.repo.get(id=by_name["id"])
        self.assertEqual(by_id["system_username"], "h001")
        self.assertIsNone(self.repo.get(system_username="fehlt"))

    # ------------------------------------------------------------------- C09
    def test_c09_chain_verifies_after_writes(self):
        self.repo.create("h001", "Alpha")
        self.repo.update(system_username="h001", display_name="Alpha B")
        self.repo.create("h002", "Beta", is_support=True)
        result = self.audit.verify_chain()
        self.assertTrue(result.ok, msg=getattr(result, "detail", ""))

    # ------------------------------------------------------------------- C10
    def test_c10_stilllegen_statt_loeschen(self):
        # Kein Löschen vorgesehen; Stilllegen über is_investigator=0.
        self.repo.create("h001", "Alpha")
        self.repo.update(system_username="h001", is_investigator=False)
        row = self.con.execute(
            "SELECT is_investigator FROM person "
            "WHERE system_username='h001'"
        ).fetchone()
        self.assertEqual(row["is_investigator"], 0)
        # Zeile bleibt als Beleg erhalten.
        self.assertEqual(self._investigator_count(), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

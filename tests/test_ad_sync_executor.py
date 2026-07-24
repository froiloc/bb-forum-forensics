# =============================================================================
# tests/test_ad_sync_executor.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AD-Abgleich (Build 501)
# =============================================================================
# Testsuite fuer den SyncExecutor (management/ad_sync/sync_executor.py) gegen
# eine voll migrierte coordinator.db (M001..M020) mit gemocktem AD-Provider —
# KEIN Live-LDAP (Bauplan Build501_502 §3/§10).
#
# SE01 — Neuaufnahme: person angelegt (is_investigator=1, is_active=1),
#        person_role 'investigator' aktiv, Belege INVESTIGATOR_CREATED +
#        ROLE_ASSIGNED + AD_SYNC_RUN (Klammer mit Zaehlern).
# SE02 — Namensaenderung: display_name nachgezogen, INVESTIGATOR_UPDATED
#        mit Diff alt->neu.
# SE03 — Deaktivierung mit FALSCHEM Wort -> AdSyncError, KEINE Aenderung,
#        KEIN PERSON_DEACTIVATED-Beleg (auch 'entfernen' klein zaehlt nicht).
# SE04 — Deaktivierung mit exakt "Entfernen": is_active=0 + Zeitstempel +
#        Begruendung; Zeile bleibt erhalten (NIE geloescht); Beleg
#        PERSON_DEACTIVATED; IdentityResolver weist das Konto ab.
# SE05 — Protokollierter Abbruch: Beleg PERSON_DEACTIVATION_ABORTED,
#        Daten unveraendert.
# SE06 — Reaktivierung: falsches Wort -> Fehler; "Reaktivieren" -> aktiv,
#        deactivated_* geleert, Beleg PERSON_REACTIVATED; abweichender
#        AD-Anzeigename wird protokolliert nachgezogen.
# SE07 — preview: leere AD-Antwort -> AdSyncPlanError (Glitch-Schutz).
# SE08 — Audit-Kette nach allen Schreibvorgaengen intakt (verify_chain).
#
# Version: v0.8.501 · Build: 501 · 2026-07-24
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
from management.ad_sync.sync_executor import AdSyncError, SyncExecutor
from management.ad_sync.sync_plan import AdSyncPlanError
from management.audit.audit_log import AuditLog
from management.audit.event_types import EventType
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.server.identity import IdentityError, IdentityResolver

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


class FakeProvider:
    """Gemockte Mitgliederquelle (Muster F4) — .members je Test setzbar."""

    def __init__(self, members):
        self.members = members
        self.target_group = "SEC_AIW_Ermittler"

    def fetch_members(self):
        return list(self.members)


class SyncExecutorTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row

        now = int(time.time())
        self.con.execute(_PERSON)
        # Bestand: Chefin (Supervisor, id=1) + ein Ermittler (id=2).
        self.con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (1, 'h0chef', 'Chefin', 1, 1, 0, ?)", (now,))
        self.con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (2, 'h0erm', 'KHK Muster', 1, 0, 0, ?)", (now,))
        self.con.execute(_OLD_SCRAPE_JOBS)

        self.audit = AuditLog(self.con)
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester").run()
        self.writer = CoordinatorWriter(self.con, self.audit)

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

    def _executor(self, members):
        return SyncExecutor(self.con, self.writer, FakeProvider(members))

    def _events(self, event_type):
        return self.con.execute(
            "SELECT * FROM audit_log WHERE event_type=? ORDER BY seq",
            (event_type,)).fetchall()

    # SE01 -------------------------------------------------------------------
    def test_se01_create_new_member(self):
        ex = self._executor([
            {"sam": "h0chef", "display_name": "Chefin"},
            {"sam": "h0erm", "display_name": "KHK Muster"},
            {"sam": "h0neu", "display_name": "KOKin Neuling"},
        ])
        plan = ex.preview()
        summary = ex.apply_automatic(plan, actor_id=1)
        self.assertEqual(len(summary["created"]), 1)

        row = self.con.execute(
            "SELECT * FROM person WHERE system_username='h0neu'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(int(row["is_investigator"]), 1)
        self.assertEqual(int(row["is_active"]), 1)
        role = self.con.execute(
            "SELECT role_code FROM person_role WHERE person_id=? "
            "AND revoked_at IS NULL", (int(row["id"]),)).fetchone()
        self.assertEqual(role["role_code"], "investigator")

        self.assertEqual(len(self._events(EventType.INVESTIGATOR_CREATED)), 1)
        self.assertEqual(len(self._events(EventType.ROLE_ASSIGNED)), 1)
        runs = self._events(EventType.AD_SYNC_RUN)
        self.assertEqual(len(runs), 1)
        self.assertIn("SEC_AIW_Ermittler", runs[0]["content"])
        # Kanonische JSON-Ablage (canonical(), ohne Leerzeichen).
        self.assertIn('"create":1', runs[0]["content"])

    # SE02 -------------------------------------------------------------------
    def test_se02_rename(self):
        ex = self._executor([
            {"sam": "h0chef", "display_name": "Chefin"},
            {"sam": "h0erm", "display_name": "KHK Muster, PP Neustadt"},
        ])
        summary = ex.apply_automatic(ex.preview(), actor_id=1)
        self.assertEqual(len(summary["renamed"]), 1)
        row = self.con.execute(
            "SELECT display_name FROM person WHERE id=2").fetchone()
        self.assertEqual(row["display_name"], "KHK Muster, PP Neustadt")
        upd = self._events(EventType.INVESTIGATOR_UPDATED)
        self.assertEqual(len(upd), 1)
        self.assertIn("KHK Muster, PP Neustadt", upd[0]["content"])
        self.assertIn("alt", upd[0]["content"])

    # SE03 -------------------------------------------------------------------
    def test_se03_deactivate_wrong_word(self):
        ex = self._executor([{"sam": "h0chef", "display_name": "Chefin"}])
        for wrong in ("entfernen", "ENTFERNEN", "Entfernen ", "ja", ""):
            with self.assertRaises(AdSyncError):
                ex.deactivate("h0erm", confirmation=wrong, actor_id=1)
        row = self.con.execute(
            "SELECT is_active FROM person WHERE id=2").fetchone()
        self.assertEqual(int(row["is_active"]), 1)
        self.assertEqual(self._events(EventType.PERSON_DEACTIVATED), [])

    # SE04 -------------------------------------------------------------------
    def test_se04_deactivate_confirmed(self):
        ex = self._executor([{"sam": "h0chef", "display_name": "Chefin"}])
        seq = ex.deactivate("h0erm", confirmation="Entfernen", actor_id=1)
        row = self.con.execute("SELECT * FROM person WHERE id=2").fetchone()
        self.assertEqual(int(row["is_active"]), 0)
        self.assertIsNotNone(row["deactivated_at"])
        self.assertIn("Active-Directory", row["deactivated_reason"])
        # NIE geloescht — die Zeile bleibt als Beleg erhalten.
        self.assertEqual(
            int(self.con.execute(
                "SELECT COUNT(*) FROM person").fetchone()[0]), 3 if
            self.con.execute(
                "SELECT 1 FROM person WHERE system_username='h0neu'"
            ).fetchone() else 2)
        ev = self._events(EventType.PERSON_DEACTIVATED)
        self.assertEqual(len(ev), 1)
        self.assertEqual(int(ev[0]["seq"]), seq)
        self.assertIn("bestaetigungswort", ev[0]["meta"])
        # Portal-Zugang gesperrt (identity.py, Build 501).
        resolver = IdentityResolver(self.db_path)
        with self.assertRaises(IdentityError):
            resolver.resolve(system_username="h0erm")
        # Aktives Konto bleibt aufloesbar.
        self.assertEqual(
            resolver.resolve(system_username="h0chef")["id"], 1)

    # SE05 -------------------------------------------------------------------
    def test_se05_abort_logged(self):
        ex = self._executor([{"sam": "h0chef", "display_name": "Chefin"}])
        seq = ex.abort_deactivation(
            "h0erm", actor_id=1, note="Eingabe war 'nein'")
        row = self.con.execute(
            "SELECT is_active FROM person WHERE id=2").fetchone()
        self.assertEqual(int(row["is_active"]), 1)
        ev = self._events(EventType.PERSON_DEACTIVATION_ABORTED)
        self.assertEqual(len(ev), 1)
        self.assertEqual(int(ev[0]["seq"]), seq)
        self.assertIn("abgebrochen", ev[0]["content"])

    # SE06 -------------------------------------------------------------------
    def test_se06_reactivate(self):
        ex = self._executor([{"sam": "h0chef", "display_name": "Chefin"}])
        ex.deactivate("h0erm", confirmation="Entfernen", actor_id=1)
        with self.assertRaises(AdSyncError):
            ex.reactivate("h0erm", confirmation="reaktivieren", actor_id=1)
        seq = ex.reactivate(
            "h0erm", confirmation="Reaktivieren", actor_id=1,
            display_name_ad="KHK Muster, PP Rueckkehr")
        row = self.con.execute("SELECT * FROM person WHERE id=2").fetchone()
        self.assertEqual(int(row["is_active"]), 1)
        self.assertIsNone(row["deactivated_at"])
        self.assertIsNone(row["deactivated_reason"])
        self.assertEqual(row["display_name"], "KHK Muster, PP Rueckkehr")
        ev = self._events(EventType.PERSON_REACTIVATED)
        self.assertEqual(len(ev), 1)
        self.assertEqual(int(ev[0]["seq"]), seq)
        # Nachzug des Anzeigenamens ist ein EIGENER Beleg.
        self.assertEqual(len(self._events(EventType.INVESTIGATOR_UPDATED)), 1)

    # SE07 -------------------------------------------------------------------
    def test_se07_preview_empty_ad_raises(self):
        ex = self._executor([])
        with self.assertRaises(AdSyncPlanError):
            ex.preview()

    # SE08 -------------------------------------------------------------------
    def test_se08_chain_intact(self):
        ex = self._executor([
            {"sam": "h0chef", "display_name": "Chefin"},
            {"sam": "h0neu", "display_name": "KOKin Neuling"},
        ])
        plan = ex.preview()
        ex.apply_automatic(plan, actor_id=1)
        ex.abort_deactivation("h0erm", actor_id=1, note="erst pruefen")
        ex.deactivate("h0erm", confirmation="Entfernen", actor_id=1)
        ex.reactivate("h0erm", confirmation="Reaktivieren", actor_id=1)
        result = self.audit.verify_chain()
        self.assertTrue(result.ok,
                        "Audit-Kette verletzt: %r" % (result,))


if __name__ == "__main__":
    unittest.main()

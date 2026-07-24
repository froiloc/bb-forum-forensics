# =============================================================================
# tests/test_management_adsync_endpoint.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AD-Abgleich (Build 502)
# =============================================================================
# Testsuite fuer die AD-Abgleich-Endpunkte der ManagementApp (Bauplan
# Build501_502 §7/§10) — voll migrierte coordinator.db, gemockter Provider,
# KEIN Live-LDAP.
#
# AE01 — GET /api/adsync ohne personnel.sync -> 403 (kein stiller Teilinhalt).
# AE02 — GET /api/adsync mit Recht -> 200: Plan (counts/Mengen) + Gruppe +
#        SERVERSEITIGE Bestaetigungsworte; KEIN Beleg (Vorschau ist lesend).
# AE03 — Provider-Ausfall: LdapError -> 502 ldap_failed; leere AD-Antwort ->
#        502 ad_plan_invalid (Glitch-Schutz).
# AE04 — POST /api/adsync/apply -> Neuaufnahme (Flag + person_role
#        investigator) + Namensaenderung vollzogen; Belege INVESTIGATOR_CREATED,
#        ROLE_ASSIGNED, INVESTIGATOR_UPDATED, AD_SYNC_RUN; ohne Recht 403.
# AE05 — POST /api/adsync/decide deactivate: falsches Wort -> 400
#        confirmation_rejected, KEINE Aenderung, KEIN Abbruch-Beleg
#        (interaktive Oberflaeche — Abbruch ist die bewusste Aktion 'abort');
#        exakt "Entfernen" -> 200, is_active=0, Beleg PERSON_DEACTIVATED.
# AE06 — POST /api/adsync/decide abort -> Beleg PERSON_DEACTIVATION_ABORTED,
#        Daten unveraendert; decide reactivate mit "Reaktivieren" -> aktiv +
#        displayName-Nachzug.
# AE07 — decide: unbekannte action/fehlender system_username -> 400.
#
# Version: v0.8.502 · Build: 502 · 2026-07-24
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
from management.external.ldap_group_reader import LdapError
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.rbac.rbac_repo import RbacRepo
from management.server.management_app import ManagementApp

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
    def __init__(self, members):
        self.members = members
        self.target_group = "SEC_AIW_Ermittler"

    def fetch_members(self):
        if isinstance(self.members, Exception):
            raise self.members
        return list(self.members)


class ManagementAdsyncEndpointTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        now = int(time.time())
        con.execute(_PERSON)
        # id=1 Chefin (bekommt personnel.sync), id=2 Ermittler ohne Recht,
        # id=3 Ermittler, der im AD fehlen wird (Entfernungs-Kandidat).
        con.execute("INSERT INTO person VALUES (1,'h0chef','Chefin',1,1,0,?)",
                    (now,))
        con.execute("INSERT INTO person VALUES (2,'h0erm','KHK Muster',1,0,0,?)",
                    (now,))
        con.execute("INSERT INTO person VALUES (3,'h0weg','KOK Weg',1,0,0,?)",
                    (now,))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        writer = CoordinatorWriter(con, AuditLog(con))
        rbac = RbacRepo(con, writer)
        rbac.grant("supervisor", "personnel.sync", actor_id=1)
        rbac.assign_role(1, "supervisor", actor_id=1)
        rbac.assign_role(2, "investigator", actor_id=1)
        con.close()

    def tearDown(self):
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.unlink(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    def _app(self, members):
        return ManagementApp(db_path=self._db,
                             ad_members_provider=FakeProvider(members))

    def _query(self, sql, args=()):
        con = sqlite3.connect(self._db)
        con.row_factory = sqlite3.Row
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    def _count_events(self, event_type):
        return self._query(
            "SELECT COUNT(*) AS c FROM audit_log WHERE event_type=?",
            (event_type,))[0]["c"]

    _AD = (
        {"sam": "h0chef", "display_name": "Chefin"},
        {"sam": "h0erm", "display_name": "KHK Muster, PP Neustadt"},
        {"sam": "h0neu", "display_name": "KOKin Neuling"},
    )

    # AE01 -------------------------------------------------------------------
    def test_ae01_get_requires_cap(self):
        r = self._app(list(self._AD)).dispatch(2, "/api/adsync", {})
        self.assertEqual(r.status, 403)

    # AE02 -------------------------------------------------------------------
    def test_ae02_get_preview(self):
        r = self._app(list(self._AD)).dispatch(1, "/api/adsync", {})
        self.assertEqual(r.status, 200)
        data = json.loads(r.body)
        self.assertEqual(data["group"], "SEC_AIW_Ermittler")
        self.assertEqual(data["confirm"],
                         {"deactivate": "Entfernen",
                          "reactivate": "Reaktivieren"})
        self.assertEqual(data["counts"]["create"], 1)          # h0neu
        self.assertEqual(data["counts"]["rename"], 1)          # h0erm
        self.assertEqual(data["counts"]["deactivate_candidates"], 1)  # h0weg
        # Vorschau erzeugt KEINEN Beleg.
        self.assertEqual(self._count_events("ad_sync_run"), 0)

    # AE03 -------------------------------------------------------------------
    def test_ae03_provider_failures(self):
        r = self._app(LdapError("Bind fehlgeschlagen")).dispatch(
            1, "/api/adsync", {})
        self.assertEqual(r.status, 502)
        self.assertEqual(json.loads(r.body)["error"], "ldap_failed")

        r = self._app([]).dispatch(1, "/api/adsync", {})
        self.assertEqual(r.status, 502)
        self.assertEqual(json.loads(r.body)["error"], "ad_plan_invalid")

    # AE04 -------------------------------------------------------------------
    def test_ae04_apply(self):
        app = self._app(list(self._AD))
        r = app.dispatch_write(2, "/api/adsync/apply", {})
        self.assertEqual(r.status, 403)

        r = app.dispatch_write(1, "/api/adsync/apply", {})
        self.assertEqual(r.status, 200)
        data = json.loads(r.body)
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["created"]), 1)
        self.assertEqual(len(data["renamed"]), 1)

        neu = self._query(
            "SELECT * FROM person WHERE system_username='h0neu'")
        self.assertEqual(len(neu), 1)
        self.assertEqual(int(neu[0]["is_investigator"]), 1)
        role = self._query(
            "SELECT role_code FROM person_role WHERE person_id=? "
            "AND revoked_at IS NULL", (neu[0]["id"],))
        self.assertEqual(role[0]["role_code"], "investigator")
        self.assertEqual(
            self._query("SELECT display_name FROM person WHERE id=2"
                        )[0]["display_name"],
            "KHK Muster, PP Neustadt")
        # Kandidat h0weg wurde NICHT angefasst.
        self.assertEqual(
            int(self._query("SELECT is_active FROM person WHERE id=3"
                            )[0]["is_active"]), 1)
        for et in ("investigator_created", "role_assigned",
                   "investigator_updated", "ad_sync_run"):
            self.assertGreaterEqual(self._count_events(et), 1, et)

    # AE05 -------------------------------------------------------------------
    def test_ae05_decide_deactivate(self):
        app = self._app(list(self._AD))
        r = app.dispatch_write(1, "/api/adsync/decide", {
            "system_username": "h0weg", "action": "deactivate",
            "confirmation": "entfernen"})
        self.assertEqual(r.status, 400)
        self.assertEqual(json.loads(r.body)["error"], "confirmation_rejected")
        self.assertEqual(
            int(self._query("SELECT is_active FROM person WHERE id=3"
                            )[0]["is_active"]), 1)
        self.assertEqual(self._count_events("person_deactivation_aborted"), 0)

        r = app.dispatch_write(1, "/api/adsync/decide", {
            "system_username": "h0weg", "action": "deactivate",
            "confirmation": "Entfernen"})
        self.assertEqual(r.status, 200)
        data = json.loads(r.body)
        self.assertTrue(data["ok"])
        row = self._query("SELECT * FROM person WHERE id=3")[0]
        self.assertEqual(int(row["is_active"]), 0)
        self.assertIsNotNone(row["deactivated_at"])
        self.assertEqual(self._count_events("person_deactivated"), 1)

    # AE06 -------------------------------------------------------------------
    def test_ae06_decide_abort_and_reactivate(self):
        app = self._app(list(self._AD))
        r = app.dispatch_write(1, "/api/adsync/decide", {
            "system_username": "h0weg", "action": "abort",
            "note": "erst Personalstelle fragen"})
        self.assertEqual(r.status, 200)
        self.assertEqual(self._count_events("person_deactivation_aborted"), 1)
        self.assertEqual(
            int(self._query("SELECT is_active FROM person WHERE id=3"
                            )[0]["is_active"]), 1)

        # Deaktivieren, dann Reaktivieren mit Namens-Nachzug.
        app.dispatch_write(1, "/api/adsync/decide", {
            "system_username": "h0weg", "action": "deactivate",
            "confirmation": "Entfernen"})
        r = app.dispatch_write(1, "/api/adsync/decide", {
            "system_username": "h0weg", "action": "reactivate",
            "confirmation": "Reaktivieren",
            "display_name_ad": "KOK Weg, PP Rueckkehr"})
        self.assertEqual(r.status, 200)
        row = self._query("SELECT * FROM person WHERE id=3")[0]
        self.assertEqual(int(row["is_active"]), 1)
        self.assertEqual(row["display_name"], "KOK Weg, PP Rueckkehr")
        self.assertEqual(self._count_events("person_reactivated"), 1)

    # AE07 -------------------------------------------------------------------
    def test_ae07_decide_bad_request(self):
        app = self._app(list(self._AD))
        r = app.dispatch_write(1, "/api/adsync/decide", {
            "system_username": "h0weg", "action": "loeschen"})
        self.assertEqual(r.status, 400)
        r = app.dispatch_write(1, "/api/adsync/decide", {
            "action": "deactivate", "confirmation": "Entfernen"})
        self.assertEqual(r.status, 400)


if __name__ == "__main__":
    unittest.main()

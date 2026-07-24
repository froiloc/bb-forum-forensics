# =============================================================================
# tests/test_management_personnel_endpoint.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Personalverwaltung (Build 503)
# =============================================================================
# Testsuite fuer die Personalverwaltungs-Endpunkte der ManagementApp
# (Bauplan Build503 §3/§5) — voll migrierte coordinator.db (M001..M021).
#
# PN01 — GET /api/personnel ohne personnel.view -> 403.
# PN02 — GET mit Recht -> Personen inkl. is_active/Flags/Rollen
#        (person_role_id!), Rollenkatalog, can_edit/can_sync korrekt.
# PN03 — POST flags: Flag-Aenderung mit Beleg (Diff alt->neu); No-op -> 400;
#        ohne personnel.edit -> 403.
# PN04 — POST role/assign + role/revoke: Belege ROLE_ASSIGNED/ROLE_REVOKED,
#        Soft-Revoke (Zeile bleibt, revoked_at gesetzt); Doppel-Zuweisung 400.
# PN05 — SELBSTSCHUTZ: eigene Flags/eigene Rollenzuweisung -> 400 self_guard,
#        KEINE Aenderung, KEIN Beleg.
# PN06 — bad requests: person_id/person_role_id/role_code fehlt -> 400;
#        unbekannte person_role_id -> 400.
#
# Version: v0.8.503 · Build: 503 · 2026-07-24
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


class ManagementPersonnelEndpointTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        now = int(time.time())
        con.execute(_PERSON)
        # id=1 Chefin (bekommt personnel.view/edit), id=2 Ermittler ohne
        # Rechte, id=3 weiterer Ermittler (Zielperson der Schreibtests).
        con.execute("INSERT INTO person VALUES (1,'h0chef','Chefin',1,1,0,?)",
                    (now,))
        con.execute("INSERT INTO person VALUES (2,'h0erm','KHK Muster',1,0,0,?)",
                    (now,))
        con.execute("INSERT INTO person VALUES (3,'h0ziel','KOK Ziel',1,0,0,?)",
                    (now,))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        writer = CoordinatorWriter(con, AuditLog(con))
        rbac = RbacRepo(con, writer)
        rbac.grant("supervisor", "personnel.view", actor_id=1)
        rbac.grant("supervisor", "personnel.edit", actor_id=1)
        rbac.assign_role(1, "supervisor", actor_id=1)
        # Zielperson hat bereits die Rolle investigator (fuer den Widerruf).
        rbac.assign_role(3, "investigator", actor_id=1)
        con.close()

    def tearDown(self):
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.unlink(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    def _app(self):
        return ManagementApp(db_path=self._db)

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

    def _person3(self):
        for p in json.loads(self._app().dispatch(
                1, "/api/personnel", {}).body)["persons"]:
            if p["id"] == 3:
                return p
        raise AssertionError("Person 3 fehlt in der Liste.")

    # PN01 -------------------------------------------------------------------
    def test_pn01_get_requires_cap(self):
        r = self._app().dispatch(2, "/api/personnel", {})
        self.assertEqual(r.status, 403)

    # PN02 -------------------------------------------------------------------
    def test_pn02_get_list(self):
        r = self._app().dispatch(1, "/api/personnel", {})
        self.assertEqual(r.status, 200)
        data = json.loads(r.body)
        self.assertEqual(data["actor_person_id"], 1)
        self.assertTrue(data["can_edit"])
        self.assertFalse(data["can_sync"])  # personnel.sync nicht vergeben
        self.assertEqual([p["system_username"] for p in data["persons"]],
                         ["h0chef", "h0erm", "h0ziel"])
        p3 = [p for p in data["persons"] if p["id"] == 3][0]
        self.assertTrue(p3["is_active"])
        self.assertEqual(len(p3["roles"]), 1)
        self.assertEqual(p3["roles"][0]["role_code"], "investigator")
        self.assertIn("person_role_id", p3["roles"][0])
        codes = {r_["code"] for r_ in data["roles_catalog"]}
        self.assertIn("investigator", codes)
        self.assertIn("supervisor", codes)

    # PN03 -------------------------------------------------------------------
    def test_pn03_flags(self):
        app = self._app()
        r = app.dispatch_write(2, "/api/personnel/flags",
                               {"person_id": 3, "is_support": True})
        self.assertEqual(r.status, 403)

        r = app.dispatch_write(1, "/api/personnel/flags",
                               {"person_id": 3, "is_support": True})
        self.assertEqual(r.status, 200)
        row = self._query("SELECT is_support FROM person WHERE id=3")[0]
        self.assertEqual(int(row["is_support"]), 1)
        self.assertEqual(self._count_events("investigator_updated"), 1)

        # No-op (gleicher Wert) -> 400, kein weiterer Beleg.
        r = app.dispatch_write(1, "/api/personnel/flags",
                               {"person_id": 3, "is_support": True})
        self.assertEqual(r.status, 400)
        self.assertEqual(self._count_events("investigator_updated"), 1)

    # PN04 -------------------------------------------------------------------
    def test_pn04_role_assign_revoke(self):
        app = self._app()
        r = app.dispatch_write(1, "/api/personnel/role/assign",
                               {"person_id": 3, "role_code": "searchagent"})
        self.assertEqual(r.status, 200)
        self.assertGreaterEqual(self._count_events("role_assigned"), 1)

        # Doppel-Zuweisung -> 400 (RbacRepo weist ab).
        r = app.dispatch_write(1, "/api/personnel/role/assign",
                               {"person_id": 3, "role_code": "searchagent"})
        self.assertEqual(r.status, 400)

        # Widerruf der investigator-Zuweisung (person_role_id aus der Liste).
        p3 = self._person3()
        inv = [x for x in p3["roles"]
               if x["role_code"] == "investigator"][0]
        r = app.dispatch_write(1, "/api/personnel/role/revoke",
                               {"person_role_id": inv["person_role_id"]})
        self.assertEqual(r.status, 200)
        self.assertEqual(self._count_events("role_revoked"), 1)
        # Soft-Revoke: Zeile bleibt, revoked_at gesetzt.
        row = self._query("SELECT revoked_at FROM person_role WHERE id=?",
                          (inv["person_role_id"],))[0]
        self.assertIsNotNone(row["revoked_at"])
        # Liste zeigt die Rolle nicht mehr.
        p3 = self._person3()
        self.assertNotIn("investigator",
                         [x["role_code"] for x in p3["roles"]])

    # PN05 -------------------------------------------------------------------
    def test_pn05_self_guard(self):
        app = self._app()
        # Eigene Flags -> 400 self_guard, keine Aenderung, kein Beleg.
        r = app.dispatch_write(1, "/api/personnel/flags",
                               {"person_id": 1, "is_supervisor": False})
        self.assertEqual(r.status, 400)
        self.assertEqual(json.loads(r.body)["error"], "self_guard")
        self.assertEqual(
            int(self._query("SELECT is_supervisor FROM person WHERE id=1"
                            )[0]["is_supervisor"]), 1)
        self.assertEqual(self._count_events("investigator_updated"), 0)

        # Eigene Rollenzuweisung widerrufen -> 400 self_guard.
        own = self._query(
            "SELECT id FROM person_role WHERE person_id=1 "
            "AND role_code='supervisor' AND revoked_at IS NULL")[0]
        r = app.dispatch_write(1, "/api/personnel/role/revoke",
                               {"person_role_id": int(own["id"])})
        self.assertEqual(r.status, 400)
        self.assertEqual(json.loads(r.body)["error"], "self_guard")
        self.assertEqual(self._count_events("role_revoked"), 0)

        # Auch die Selbst-ZUWEISUNG faellt unter die eine Regel.
        r = app.dispatch_write(1, "/api/personnel/role/assign",
                               {"person_id": 1, "role_code": "searchagent"})
        self.assertEqual(r.status, 400)
        self.assertEqual(json.loads(r.body)["error"], "self_guard")

    # PN06 -------------------------------------------------------------------
    def test_pn06_bad_requests(self):
        app = self._app()
        r = app.dispatch_write(1, "/api/personnel/flags", {"is_support": True})
        self.assertEqual(r.status, 400)
        r = app.dispatch_write(1, "/api/personnel/role/assign",
                               {"person_id": 3})
        self.assertEqual(r.status, 400)
        r = app.dispatch_write(1, "/api/personnel/role/revoke", {})
        self.assertEqual(r.status, 400)
        r = app.dispatch_write(1, "/api/personnel/role/revoke",
                               {"person_role_id": 99999})
        self.assertEqual(r.status, 400)


if __name__ == "__main__":
    unittest.main()

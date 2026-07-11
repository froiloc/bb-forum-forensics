# =============================================================================
# tests/test_capacity_calculator.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kapazitaet (Welle 0)
# =============================================================================
# Testsuite fuer Build 358: CapacityCalculator + /api/capacity-Endpunkt.
#
# CC01 — Basis: Mo-Fr 480 min, 5 Arbeitstage -> basis 2400, netto 2400.
# CC02 — Feiertag reduziert die Basis (ein Wochentag entfaellt).
# CC03 — Arbeitszeit-Regelwechsel (append-only): Tage nehmen die aktive Regel.
# CC04 — Einschraenkung value_minutes = Total, anteilig nach Ueberlappungstagen.
# CC05 — Einschraenkung value_pct = Prozent der Basis der Ueberlappungstage.
# CC06 — Garantie-Boden: netto = max(Basis - Einschr, Garantie).
# CC07 — netto nie negativ ohne Garantie.
# EP01 — /api/capacity: 200 mit Kapazitaet (capacity.edit, scope alle).
# EP02 — ohne capacity.edit -> 403.
# EP03 — fehlende Query-Parameter -> 400.
# EP04 — scope 'eigene': fremde Person -> 403; eigene -> 200.
#
# Version: v0.7.358 · Build: 358 · 2026-07-10
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
from management.migrations.runner import MigrationRunner, discover
from management.gateway.coordinator_writer import CoordinatorWriter
from management.capacity.worktime_repo import WorktimeRepo
from management.capacity.holiday_repo import HolidayRepo
from management.capacity.availability_repo import AvailabilityRepo
from management.capacity.capacity_calculator import CapacityCalculator
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


def _build(db_path):
    con = sqlite3.connect(db_path)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(_PERSON)
    for pid, un, disp, sup in ((1, "h0a2898", "Chefin", 1),
                               (2, "h002", "Mueller", 0),
                               (3, "h003", "Gamma", 0)):
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (?, ?, ?, 1, ?, 0, ?)", (pid, un, disp, sup,
                                             int(time.time())))
    con.execute(_OLD_SCRAPE_JOBS)
    MigrationRunner(con, discover(coordinator_migrations),
                    audit=AuditLog(con), deployed_by="tester").run()
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return con


class CapacityCalculatorTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        self.con = _build(self._db)
        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.wt = WorktimeRepo(self.con, self.writer)
        self.hol = HolidayRepo(self.con, self.writer)
        self.av = AvailabilityRepo(self.con, self.writer)
        # Standard-Arbeitszeit person 2: Mo-Fr 480, Sa/So 0, ab 2026-01-01.
        self.wt.set_worktime(2, effective_from="2026-01-01",
                             mon_min=480, tue_min=480, wed_min=480,
                             thu_min=480, fri_min=480, actor_id=1)

    def tearDown(self):
        try:
            self.con.close()
        except Exception:
            pass
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    def _calc(self, start="2026-07-06", end="2026-07-10"):
        # 2026-07-06 = Montag ... 2026-07-10 = Freitag (5 Arbeitstage).
        return CapacityCalculator(self.con).compute(2, start, end)

    # CC01 -------------------------------------------------------------------
    def test_cc01_basis(self):
        r = self._calc()
        self.assertEqual(r.working_days, 5)
        self.assertEqual(r.basis, 5 * 480)
        self.assertEqual(r.netto, 2400)
        self.assertEqual(r.days, 5)

    # CC02 -------------------------------------------------------------------
    def test_cc02_holiday(self):
        self.hol.add_holiday("2026-07-08", "Testfeiertag", actor_id=1)  # Mi
        r = self._calc()
        self.assertEqual(r.working_days, 4)
        self.assertEqual(r.basis, 4 * 480)

    # CC03 -------------------------------------------------------------------
    def test_cc03_worktime_change(self):
        # Ab 2026-07-09 nur noch 300 min Mo-Fr (append-only).
        self.wt.set_worktime(2, effective_from="2026-07-09",
                             mon_min=300, tue_min=300, wed_min=300,
                             thu_min=300, fri_min=300, actor_id=1)
        r = self._calc()
        # 06,07,08 -> 480 ; 09,10 -> 300
        self.assertEqual(r.basis, 3 * 480 + 2 * 300)

    # CC04 -------------------------------------------------------------------
    def test_cc04_einschraenkung_minutes(self):
        # Total 600 ueber genau den Zeitraum -> voller Abzug.
        self.av.set_availability(2, period_start="2026-07-06",
                                 period_end="2026-07-10", kind="einschraenkung",
                                 value_minutes=600, actor_id=1)
        self.assertEqual(self._calc().netto, 2400 - 600)
        # Teil-Ueberlappung: Eintrag 10 Tage, 1000 min; Fenster 5 Tage -> 500.
        self.av.set_availability(2, period_start="2026-07-01",
                                 period_end="2026-07-10", kind="einschraenkung",
                                 value_minutes=1000, actor_id=1)
        # jetzt zwei Einschraenkungen: 600 + 500 = 1100
        self.assertEqual(self._calc().einschraenkungen, 600 + 500)

    # CC05 -------------------------------------------------------------------
    def test_cc05_einschraenkung_pct(self):
        self.av.set_availability(2, period_start="2026-07-06",
                                 period_end="2026-07-10", kind="einschraenkung",
                                 value_pct=50, actor_id=1)
        r = self._calc()
        self.assertEqual(r.einschraenkungen, 1200)  # 50% von 2400
        self.assertEqual(r.netto, 1200)

    # CC06 -------------------------------------------------------------------
    def test_cc06_garantie_floor(self):
        self.av.set_availability(2, period_start="2026-07-06",
                                 period_end="2026-07-10", kind="einschraenkung",
                                 value_minutes=2400, actor_id=1)  # Basis komplett weg
        self.av.set_availability(2, period_start="2026-07-06",
                                 period_end="2026-07-10", kind="garantie",
                                 value_minutes=2000, actor_id=1)
        r = self._calc()
        # max(2400-2400, 2000) = 2000
        self.assertEqual(r.netto, 2000)

    # CC07 -------------------------------------------------------------------
    def test_cc07_never_negative(self):
        self.av.set_availability(2, period_start="2026-07-06",
                                 period_end="2026-07-10", kind="einschraenkung",
                                 value_minutes=9999, actor_id=1)
        self.assertEqual(self._calc().netto, 0)

    # ---- Endpunkt ----------------------------------------------------------
    def _grant_capacity(self, role, scope, person_id):
        rbac = RbacRepo(self.con, self.writer)
        rbac.grant(role, "capacity.edit", scope=scope, actor_id=1)
        rbac.assign_role(person_id, role, actor_id=1)
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # EP01 -------------------------------------------------------------------
    def test_ep01_endpoint_ok(self):
        self._grant_capacity("supervisor", "alle", 1)
        app = ManagementApp(self._db)
        r = app.dispatch(1, "/api/capacity",
                         {"person_id": ["2"], "start": ["2026-07-06"],
                          "end": ["2026-07-10"]})
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["netto"], 2400)
        self.assertEqual(d["person_id"], 2)

    # EP02 -------------------------------------------------------------------
    def test_ep02_forbidden(self):
        app = ManagementApp(self._db)
        r = app.dispatch(3, "/api/capacity",
                         {"person_id": ["2"], "start": ["2026-07-06"],
                          "end": ["2026-07-10"]})
        self.assertEqual(r.status, 403)

    # EP03 -------------------------------------------------------------------
    def test_ep03_bad_request(self):
        self._grant_capacity("supervisor", "alle", 1)
        app = ManagementApp(self._db)
        r = app.dispatch(1, "/api/capacity", {"person_id": ["2"]})
        self.assertEqual(r.status, 400)

    # EP04 -------------------------------------------------------------------
    def test_ep04_scope_eigene(self):
        self._grant_capacity("investigator", "eigene", 2)
        app = ManagementApp(self._db)
        # fremde Person -> 403
        r_other = app.dispatch(2, "/api/capacity",
                               {"person_id": ["3"], "start": ["2026-07-06"],
                                "end": ["2026-07-10"]})
        self.assertEqual(r_other.status, 403)
        # eigene -> 200
        r_self = app.dispatch(2, "/api/capacity",
                              {"person_id": ["2"], "start": ["2026-07-06"],
                               "end": ["2026-07-10"]})
        self.assertEqual(r_self.status, 200)


if __name__ == "__main__":
    unittest.main()

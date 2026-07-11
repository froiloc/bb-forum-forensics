# =============================================================================
# tests/test_management_dashboard.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 314: DashboardRepo (nur-lesendes Aggregat) +
# classify_ampel (reine Ableitung). VOLLSTAENDIG automatisiert — kein Browser.
#
# D01 — Fixture via discover (M001..M004); leere Faelle -> [] ; Repo konstruiert
# D02 — offener, unzugewiesener Fall -> Ampel ROT (offen_nicht_zugewiesen);
#       Rohsignale: event_count>=1 (case_created-Spiegel), last_event_kind gesetzt
# D03 — zugewiesen + in_progress, frisch aktiv -> GRUEN (aktiv);
#       Zuweisung als system_username/display_name aufgeloest
# D04 — in_progress, idle >= amber -> GELB ; idle >= red -> ROT (now injiziert)
# D05 — approved -> GRUEN (freigegeben) trotz Inaktivitaet
# D06 — closed  -> GRUEN (abgeschlossen)
# D07 — Support-Praesenz: frische Sitzung -> support_active True/Count;
#       veraltete (stale) Sitzung wird NICHT gezaehlt; Ampel bleibt unberuehrt
# D08 — Ereignis-Aggregat: mehrere Ereignisse -> event_count,
#       last_event_kind (juengstes), last_event_at (max) korrekt
# D09 — has_note true/false ohne den Notiztext auszulesen (Sensibilitaet)
# D10 — Sortierung: Prioritaet aufsteigend, dann letzte Aktivitaet absteigend
# D11 — classify_ampel als reine Funktion mit EIGENEN Schwellen (aenderbar):
#       andere Schwellen -> andere Ampel (beweist Ein-Stellen-Justierbarkeit)
# D12 — Read-Model schreibt nichts: Zeilenzahlen in cases/audit_log/case_events
#       vor und nach list_case_overview identisch
#
# Version: v0.7.314 · Build: 314 · 2026-07-02
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
from management.case_events.case_events_repo import CaseEventsRepo
from management.cases.cases_repo import CasesRepo
from management.dashboard.dashboard_repo import (
    AMPEL_GELB,
    AMPEL_GRUEN,
    AMPEL_ROT,
    AmpelThresholds,
    DashboardConfigError,
    DashboardRepo,
    DashboardSchemaError,
    REASON_ACTIVE,
    REASON_APPROVED,
    REASON_CLOSED,
    REASON_IDLE_LONG,
    REASON_IDLE_MEDIUM,
    REASON_OPEN_UNASSIGNED,
    ampel_thresholds_from_config,
    classify_ampel,
)


class _StubCfg:
    """Minimaler ConfigLoader-Ersatz fuer Tests: get(dotted_key, default)."""

    def __init__(self, values):
        self._v = dict(values)

    def get(self, key, default=None):
        return self._v.get(key, default)
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

_DAY = 86400


class ManagementDashboardTests(unittest.TestCase):

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
             (2, "h002", "Beta", 1, 0, 1, now)],
        )
        self.con.execute(_OLD_SCRAPE_JOBS)

        self.audit = AuditLog(self.con)
        self.mods = discover(coordinator_migrations)
        self.applied = MigrationRunner(
            self.con, self.mods, audit=self.audit, deployed_by="tester",
        ).run()

        self.writer = CoordinatorWriter(self.con, self.audit)
        self.cases = CasesRepo(self.con, self.writer)
        self.events = CaseEventsRepo(self.con, self.writer)
        self.dash = DashboardRepo(self.con)

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
    def _one(self, user_id, **kw):
        for o in self.dash.list_case_overview(**kw):
            if o.user_id == user_id:
                return o
        return None

    def _count(self, table):
        return self.con.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]

    def _set_activity(self, user_id, ts):
        """
        Setzt die letzte Fall-Aktivitaet deterministisch: cases.updated_at UND
        alle case_events.created_at des Falls auf ts. Damit ist
        last_activity_at == ts (unabhaengig von der realen Uhr).
        """
        self.con.execute("UPDATE cases SET updated_at=? WHERE user_id=?",
                         (ts, user_id))
        self.con.execute("UPDATE case_events SET created_at=? WHERE user_id=?",
                         (ts, user_id))

    def _add_support(self, user_id, supporter_id, started_at, last_heartbeat,
                     ended_at=None):
        self.con.execute(
            "INSERT INTO support_sessions "
            "(user_id, supporter_id, started_at, last_heartbeat, ended_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, supporter_id, started_at, last_heartbeat, ended_at),
        )

    # D01 --------------------------------------------------------------------
    def test_d01_migrations_and_empty(self):
        self.assertEqual(self.applied, [1, 2, 4, 5, 6, 7, 8, 9] if 3 not in self.applied
                         else [1, 2, 3, 4, 5, 6, 7, 8, 9])
        # discover findet M001..M006 -> support_sessions (M003) IST dabei,
        # der person-Rename (M005, Build 342) ebenso wie das RBAC-Schema
        # (M006, Build 343).
        self.assertIn(3, self.applied)
        self.assertIn(4, self.applied)
        self.assertIn(5, self.applied)
        self.assertIn(6, self.applied)
        self.assertEqual(self.dash.list_case_overview(), [])

    # D02 --------------------------------------------------------------------
    def test_d02_open_unassigned_is_red(self):
        self.cases.create_case(18, "KEKa", actor_id=1)
        o = self._one(18)
        self.assertIsNotNone(o)
        self.assertEqual((o.ampel, o.ampel_reason),
                         (AMPEL_ROT, REASON_OPEN_UNASSIGNED))
        # case_created-Spiegel (Build 313) -> mind. 1 Ereignis.
        self.assertGreaterEqual(o.event_count, 1)
        self.assertEqual(o.last_event_kind, "case_created")
        self.assertIsNotNone(o.last_event_at)
        self.assertFalse(o.support_active)

    # D03 --------------------------------------------------------------------
    def test_d03_assigned_active_is_green(self):
        self.cases.create_case(19, "LMN", actor_id=1)
        self.cases.assign(19, 2, actor_id=1)
        self.cases.set_status(19, "in_progress", actor_id=2)
        o = self._one(19)
        self.assertEqual((o.ampel, o.ampel_reason), (AMPEL_GRUEN, REASON_ACTIVE))
        self.assertEqual(o.assigned_to, 2)
        self.assertEqual(o.assigned_system_username, "h002")
        self.assertEqual(o.assigned_display_name, "Beta")

    # D04 --------------------------------------------------------------------
    def test_d04_idle_thresholds(self):
        self.cases.create_case(20, "MNO", actor_id=1)
        self.cases.assign(20, 2, actor_id=1)
        self.cases.set_status(20, "in_progress", actor_id=2)
        base = self._one(20)
        last_act = base.last_activity_at

        # amber: idle genau amber_idle_days
        now_amber = last_act + AmpelThresholds().amber_idle_days * _DAY
        o = self._one(20, now=now_amber)
        self.assertEqual((o.ampel, o.ampel_reason),
                         (AMPEL_GELB, REASON_IDLE_MEDIUM))

        # rot: idle genau red_idle_days
        now_red = last_act + AmpelThresholds().red_idle_days * _DAY
        o = self._one(20, now=now_red)
        self.assertEqual((o.ampel, o.ampel_reason), (AMPEL_ROT, REASON_IDLE_LONG))

        # gruen: knapp unter amber
        now_ok = last_act + (AmpelThresholds().amber_idle_days * _DAY) - 1
        o = self._one(20, now=now_ok)
        self.assertEqual(o.ampel, AMPEL_GRUEN)

    # D05 --------------------------------------------------------------------
    def test_d05_approved_green_despite_idle(self):
        self.cases.create_case(21, "PQR", actor_id=1)
        self.cases.set_status(21, "approved", actor_id=1)
        base = self._one(21)
        far = base.last_activity_at + 999 * _DAY
        o = self._one(21, now=far)
        self.assertEqual((o.ampel, o.ampel_reason), (AMPEL_GRUEN, REASON_APPROVED))
        self.assertIsNotNone(o.approved_at)

    # D06 --------------------------------------------------------------------
    def test_d06_closed_green(self):
        self.cases.create_case(22, "STU", actor_id=1)
        self.cases.set_status(22, "closed", actor_id=1)
        base = self._one(22)
        far = base.last_activity_at + 999 * _DAY
        o = self._one(22, now=far)
        self.assertEqual((o.ampel, o.ampel_reason), (AMPEL_GRUEN, REASON_CLOSED))

    # D07 --------------------------------------------------------------------
    def test_d07_support_presence_fresh_vs_stale(self):
        self.cases.create_case(23, "VWX", actor_id=1)
        self.cases.assign(23, 2, actor_id=1)
        self.cases.set_status(23, "in_progress", actor_id=2)
        now = int(time.time())
        # frische Sitzung (Heartbeat jetzt) + veraltete (Heartbeat vor 60s).
        self._add_support(23, 2, started_at=now - 10, last_heartbeat=now)
        self._add_support(23, 2, started_at=now - 300, last_heartbeat=now - 60)
        o = self._one(23, now=now)
        self.assertTrue(o.support_active)
        self.assertEqual(o.support_count, 1)  # nur die frische zaehlt
        self.assertEqual(o.support_since, now - 10)
        # Ampel unberuehrt von Support (in_progress, frisch aktiv -> gruen).
        self.assertEqual(o.ampel, AMPEL_GRUEN)

    # D08 --------------------------------------------------------------------
    def test_d08_event_aggregation(self):
        self.cases.create_case(24, "YZA", actor_id=1)   # case_created
        self.cases.assign(24, 2, actor_id=1)            # assigned
        self.events.add_manual_event(24, "Notiz", actor_id=2)  # manual
        o = self._one(24)
        self.assertEqual(o.event_count, 3)
        self.assertEqual(o.last_event_kind, "manual")
        last = self.con.execute(
            "SELECT MAX(created_at) FROM case_events WHERE user_id=24"
        ).fetchone()[0]
        self.assertEqual(o.last_event_at, last)

    # D09 --------------------------------------------------------------------
    def test_d09_has_note_without_reading_text(self):
        self.cases.create_case(25, "BCD", actor_id=1)
        self.assertFalse(self._one(25).has_note)
        self.cases.set_note(25, "streng vertraulich", actor_id=1)
        o = self._one(25)
        self.assertTrue(o.has_note)
        # Das DTO hat KEIN Textfeld fuer die Notiz (Sensibilitaet).
        self.assertFalse(hasattr(o, "note"))

    # D10 --------------------------------------------------------------------
    def test_d10_sort_attention_first(self):
        # Prio 1 (soll oben), Prio 3, Prio 5.
        self.cases.create_case(30, "P3", actor_id=1)
        self.cases.set_priority(30, 3, actor_id=1)
        self.cases.create_case(31, "P1", actor_id=1)
        self.cases.set_priority(31, 1, actor_id=1)
        self.cases.create_case(32, "P5", actor_id=1)
        self.cases.set_priority(32, 5, actor_id=1)
        order = [o.user_id for o in self.dash.list_case_overview()]
        self.assertEqual(order[0], 31)          # Prio 1 zuerst
        self.assertLess(order.index(30), order.index(32))  # Prio 3 vor Prio 5

    # D11 --------------------------------------------------------------------
    def test_d11_classify_is_threshold_driven(self):
        now = 1_000_000_000
        idle_10d = now - 10 * _DAY
        # Standard (amber=7): 10 Tage idle -> GELB.
        a, _ = classify_ampel(status="in_progress", assigned_to=2,
                              last_activity_at=idle_10d, now=now)
        self.assertEqual(a, AMPEL_GELB)
        # Strengere Schwellen (amber=3, red=8): 10 Tage idle -> ROT.
        strict = AmpelThresholds(amber_idle_days=3, red_idle_days=8)
        a2, r2 = classify_ampel(status="in_progress", assigned_to=2,
                                last_activity_at=idle_10d, now=now,
                                thresholds=strict)
        self.assertEqual((a2, r2), (AMPEL_ROT, REASON_IDLE_LONG))
        # Lockerere Schwellen (amber=30): 10 Tage idle -> GRUEN.
        loose = AmpelThresholds(amber_idle_days=30, red_idle_days=60)
        a3, _ = classify_ampel(status="in_progress", assigned_to=2,
                               last_activity_at=idle_10d, now=now,
                               thresholds=loose)
        self.assertEqual(a3, AMPEL_GRUEN)

    # D12 --------------------------------------------------------------------
    def test_d12_read_only_no_writes(self):
        self.cases.create_case(40, "RO", actor_id=1)
        self.cases.assign(40, 2, actor_id=1)
        before = (self._count("cases"), self._count("audit_log"),
                  self._count("case_events"), self._count("support_sessions"))
        _ = self.dash.list_case_overview()
        _ = self.dash.list_case_overview(now=int(time.time()) + 999 * _DAY)
        after = (self._count("cases"), self._count("audit_log"),
                 self._count("case_events"), self._count("support_sessions"))
        self.assertEqual(before, after, "DashboardRepo darf NICHTS schreiben")


    # D13 --------------------------------------------------------------------
    def test_d13_thresholds_from_config(self):
        # explizite Werte aus config.yaml
        t = ampel_thresholds_from_config(_StubCfg({
            "dashboard.ampel.amber_idle_days": 3,
            "dashboard.ampel.red_idle_days": 9}))
        self.assertEqual((t.amber_idle_days, t.red_idle_days), (3, 9))
        # fehlende Schluessel -> Vorgabe 7/21
        t2 = ampel_thresholds_from_config(_StubCfg({}))
        self.assertEqual((t2.amber_idle_days, t2.red_idle_days), (7, 21))
        # None-cfg -> Vorgabe 7/21
        t3 = ampel_thresholds_from_config(None)
        self.assertEqual((t3.amber_idle_days, t3.red_idle_days), (7, 21))
        # ungueltig: amber >= red
        with self.assertRaises(DashboardConfigError):
            ampel_thresholds_from_config(_StubCfg({
                "dashboard.ampel.amber_idle_days": 21,
                "dashboard.ampel.red_idle_days": 7}))
        # ungueltig: nicht-ganzzahlig
        with self.assertRaises(DashboardConfigError):
            ampel_thresholds_from_config(_StubCfg({
                "dashboard.ampel.amber_idle_days": "sieben",
                "dashboard.ampel.red_idle_days": 21}))
        # ungueltig: amber < 1
        with self.assertRaises(DashboardConfigError):
            ampel_thresholds_from_config(_StubCfg({
                "dashboard.ampel.amber_idle_days": 0,
                "dashboard.ampel.red_idle_days": 21}))

    # D14 --------------------------------------------------------------------
    def test_d14_sort_severity_first(self):
        NOW = 2_000_000_000
        # ROT (offen/unzugewiesen), frische Aktivitaet
        self.cases.create_case(50, "R1", actor_id=1)
        self._set_activity(50, NOW - 1 * _DAY)
        # ROT (in_progress, lange inaktiv >= red)
        self.cases.create_case(53, "R2", actor_id=1)
        self.cases.assign(53, 2, actor_id=1)
        self.cases.set_status(53, "in_progress", actor_id=2)
        self._set_activity(53, NOW - 30 * _DAY)
        # GELB (in_progress, mittlere Inaktivitaet)
        self.cases.create_case(52, "Y1", actor_id=1)
        self.cases.assign(52, 2, actor_id=1)
        self.cases.set_status(52, "in_progress", actor_id=2)
        self._set_activity(52, NOW - 10 * _DAY)
        # GRUEN (in_progress, frisch)
        self.cases.create_case(51, "G1", actor_id=1)
        self.cases.assign(51, 2, actor_id=1)
        self.cases.set_status(51, "in_progress", actor_id=2)
        self._set_activity(51, NOW - 1 * _DAY)

        overview = self.dash.list_case_overview(now=NOW)
        ids = [o.user_id for o in overview]
        amp = {o.user_id: o.ampel for o in overview}
        # Ampel-Schwere zuerst: beide ROT vor GELB vor GRUEN; innerhalb ROT
        # (gleiche Prio) juengste Aktivitaet zuerst -> 50 vor 53.
        self.assertEqual(ids, [50, 53, 52, 51], overview)
        self.assertEqual(amp[50], AMPEL_ROT)
        self.assertEqual(amp[53], AMPEL_ROT)
        self.assertEqual(amp[52], AMPEL_GELB)
        self.assertEqual(amp[51], AMPEL_GRUEN)

    # D15 --------------------------------------------------------------------
    def test_d15_missing_table_actionable_error(self):
        self.cases.create_case(60, "X", actor_id=1)
        self.con.execute("DROP TABLE case_events")
        with self.assertRaises(DashboardSchemaError) as ctx:
            self.dash.list_case_overview()
        msg = str(ctx.exception)
        # Handlungsleitend: nennt die fehlende Tabelle UND den Migrationsbefehl.
        self.assertIn("case_events", msg)
        self.assertIn("migrate", msg)


if __name__ == "__main__":
    unittest.main()

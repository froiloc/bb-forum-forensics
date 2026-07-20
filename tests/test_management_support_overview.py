# =============================================================================
# tests/test_management_support_overview.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 330: SupportOverviewRepo (Rekonstruktion der Support-
# Sitzungs-Historie AUS dem audit_log).
#
# SO01 — echtes start()+end()   -> status 'beendet', duration aus Payload,
#        Supporter + Benutzer aufgeloest, Beleg-seqs gesetzt
# SO02 — echtes start()+close_orphans() -> status 'orphan_timeout',
#        ended_at == last_heartbeat, reason='orphan_timeout'
# SO03 — STARTED ohne ENDED     -> status 'offen', ended/duration None
# SO04 — ENDED ohne STARTED     -> status 'herrenlos', Supporter None, sichtbar
# SO05 — Fall ohne cases-Eintrag -> username None, Zeile bleibt sichtbar (GR 1)
# SO06 — Supporter nicht in person -> Supporter-Namen None
# SO07 — deterministische chronologische Ordnung (Anker started_at, Tiebreak id)
# SO08 — doppeltes ENDED        -> anomaly 'doppeltes_ended', erster Beleg bleibt
# SO09 — fehlende session_id im Payload -> anomaly, eigener Datensatz, nicht still
#        verworfen (Grundregel 1)
# SO10 — fehlende Pflichttabelle -> SupportOverviewSchemaError (handlungsleitend)
# SO11 — verify_chain gruen nach allen Schreibvorgaengen (Belegkette intakt)
# SO12 — Legacy-Payloads (Schluessel 'user_id', vor M019) werden per Fallback
#        weiterhin gelesen (audit_log ist append-only)
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
from management.audit.event_types import EventType
from management.cases.cases_repo import CasesRepo
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.support_overview.support_overview_repo import (
    SupportOverviewRepo,
    SupportOverviewSchemaError,
)
from management.support_overview.support_session_record import (
    ANOMALY_DOUBLE_ENDED,
    ANOMALY_MISSING_SESSION_ID,
    STATUS_DANGLING,
    STATUS_ENDED_CLEAN,
    STATUS_ENDED_ORPHAN,
    STATUS_OPEN,
)
from management.support_sessions.support_sessions_repo import SupportSessionsRepo

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
# M002 baut scrape_jobs destruktiv um -> die alte Tabelle muss vorher da sein.
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


class SupportOverviewRepoTests(unittest.TestCase):

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
            [(1, "h001", "Support Eins", 1, 0, 1, now),
             (2, "h002", "Support Zwei", 1, 0, 1, now)],
        )
        self.con.execute(_OLD_SCRAPE_JOBS)

        self.audit = AuditLog(self.con)
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="t").run()
        self.writer = CoordinatorWriter(self.con, self.audit)
        self.cases = CasesRepo(self.con, self.writer)
        self.support = SupportSessionsRepo(self.con, self.writer)

    def tearDown(self):
        self.con.close()
        for root, _d, files in os.walk(self._tmp, topdown=False):
            for fn in files:
                try:
                    os.remove(os.path.join(root, fn))
                except OSError:
                    pass
            os.rmdir(root)

    # ---- Hilfen: gezielte Belege direkt ins audit_log (kontrollierte Payloads)
    def _emit_started(self, session_id, subject_id, supporter_id, started_at,
                     actor_id=None):
        payload = {"session_id": session_id, "subject_id": subject_id,
                   "supporter_id": supporter_id, "started_at": started_at}
        self.writer.audited_write(
            do_write=lambda con: payload,
            event_type=EventType.SUPPORT_SESSION_STARTED,
            actor_id=actor_id, target_type="support_session",
            target_id=str(subject_id), meta=None)

    def _emit_ended(self, session_id, subject_id, ended_at, duration_sec,
                   reason=None, actor_id=None):
        payload = {"session_id": session_id, "subject_id": subject_id,
                   "ended_at": ended_at, "duration_sec": duration_sec}
        if reason is not None:
            payload["reason"] = reason
        self.writer.audited_write(
            do_write=lambda con: payload,
            event_type=EventType.SUPPORT_SESSION_ENDED,
            actor_id=actor_id, target_type="support_session",
            target_id=str(session_id), meta=None)

    def _emit_ended_raw(self, payload):
        """ENDED mit BELIEBIGEM Payload (z. B. ohne session_id) — fuer SO09."""
        self.writer.audited_write(
            do_write=lambda con: dict(payload),
            event_type=EventType.SUPPORT_SESSION_ENDED,
            actor_id=None, target_type="support_session",
            target_id="?", meta=None)

    def _by_session(self, records):
        return {r.session_id: r for r in records}

    # ---- SO01: echtes start()+end() ----------------------------------------
    def test_so01_real_start_end_clean(self):
        self.cases.create_case(subject_id=7001, username="beschuldigter_a",
                               actor_id=1)
        sid = self.support.start(7001, supporter_id=1, actor_id=1)
        time.sleep(0.01)
        self.support.end(sid, actor_id=1)

        recs = SupportOverviewRepo(self.con).list_support_sessions()
        by = self._by_session(recs)
        self.assertIn(sid, by)
        r = by[sid]
        self.assertEqual(r.status, STATUS_ENDED_CLEAN)
        self.assertEqual(r.subject_id, 7001)
        self.assertEqual(r.username, "beschuldigter_a")
        self.assertEqual(r.supporter_id, 1)
        self.assertEqual(r.supporter_system_username, "h001")
        self.assertEqual(r.supporter_display_name, "Support Eins")
        self.assertIsNotNone(r.started_at)
        self.assertIsNotNone(r.ended_at)
        self.assertIsNotNone(r.duration_sec)          # aus ENDED-Payload
        self.assertIsNone(r.reason)                    # sauberes Ende
        self.assertIsNotNone(r.started_seq)
        self.assertIsNotNone(r.ended_seq)
        self.assertIsNone(r.anomaly)

    # ---- SO02: echtes start()+close_orphans() ------------------------------
    def test_so02_real_orphan_timeout(self):
        self.cases.create_case(subject_id=7002, username="beschuldigter_b",
                               actor_id=1)
        sid = self.support.start(7002, supporter_id=2, actor_id=2)
        # Sitzung kuenstlich veralten lassen (Heartbeat weit in die Vergangenheit).
        stale_hb = int(time.time()) - 10000
        self.con.execute(
            "UPDATE support_sessions SET last_heartbeat = ? WHERE id = ?",
            (stale_hb, sid))
        closed = self.support.close_orphans(stale_sec=30)
        self.assertEqual(closed, 1)

        recs = SupportOverviewRepo(self.con).list_support_sessions()
        r = self._by_session(recs)[sid]
        self.assertEqual(r.status, STATUS_ENDED_ORPHAN)
        self.assertEqual(r.reason, "orphan_timeout")
        # ended_at ist der EHRLICHE letzte Heartbeat, nicht 'now'.
        self.assertEqual(r.ended_at, stale_hb)

    # ---- SO03: STARTED ohne ENDED -> offen ---------------------------------
    def test_so03_open_session(self):
        self._emit_started(session_id=51, subject_id=7003, supporter_id=1,
                          started_at=1000)
        recs = SupportOverviewRepo(self.con).list_support_sessions()
        r = self._by_session(recs)[51]
        self.assertEqual(r.status, STATUS_OPEN)
        self.assertEqual(r.started_at, 1000)
        self.assertIsNone(r.ended_at)
        self.assertIsNone(r.duration_sec)
        self.assertIsNotNone(r.started_seq)
        self.assertIsNone(r.ended_seq)

    # ---- SO04: ENDED ohne STARTED -> herrenlos -----------------------------
    def test_so04_dangling_ended(self):
        self._emit_ended(session_id=52, subject_id=7004, ended_at=2000,
                        duration_sec=120)
        recs = SupportOverviewRepo(self.con).list_support_sessions()
        r = self._by_session(recs)[52]
        self.assertEqual(r.status, STATUS_DANGLING)
        self.assertIsNone(r.started_at)
        self.assertIsNone(r.supporter_id)              # ENDED traegt keinen
        self.assertIsNone(r.supporter_system_username)
        self.assertEqual(r.ended_at, 2000)
        self.assertIsNotNone(r.ended_seq)
        self.assertIsNone(r.started_seq)

    # ---- SO05: Fall ohne cases-Eintrag -> username None, sichtbar -----------
    def test_so05_missing_case_username_none(self):
        # KEIN create_case fuer 7005.
        self._emit_started(session_id=53, subject_id=7005, supporter_id=1,
                          started_at=1500)
        recs = SupportOverviewRepo(self.con).list_support_sessions()
        r = self._by_session(recs)[53]
        self.assertIsNone(r.username)                  # kein cases-Eintrag
        self.assertEqual(r.subject_id, 7005)              # Zeile bleibt sichtbar

    # ---- SO06: Supporter nicht in person ----------------------------
    def test_so06_unknown_supporter(self):
        self._emit_started(session_id=54, subject_id=7006, supporter_id=999,
                          started_at=1600)
        recs = SupportOverviewRepo(self.con).list_support_sessions()
        r = self._by_session(recs)[54]
        self.assertEqual(r.supporter_id, 999)
        self.assertIsNone(r.supporter_system_username)
        self.assertIsNone(r.supporter_display_name)

    # ---- SO07: deterministische chronologische Ordnung ---------------------
    def test_so07_chronological_order(self):
        # Belege in NICHT-chronologischer Emit-Reihenfolge; started_at steuert.
        self._emit_started(session_id=61, subject_id=8001, supporter_id=1,
                          started_at=300)
        self._emit_started(session_id=62, subject_id=8002, supporter_id=1,
                          started_at=100)
        self._emit_started(session_id=63, subject_id=8003, supporter_id=1,
                          started_at=200)
        recs = SupportOverviewRepo(self.con).list_support_sessions()
        order = [r.session_id for r in recs]
        # Erwartet nach started_at aufsteigend: 62(100), 63(200), 61(300).
        self.assertEqual(order, [62, 63, 61])

    # ---- SO08: doppeltes ENDED -> anomaly, erster Beleg bleibt -------------
    def test_so08_double_ended_anomaly(self):
        self._emit_started(session_id=71, subject_id=8101, supporter_id=1,
                          started_at=500)
        self._emit_ended(session_id=71, subject_id=8101, ended_at=560,
                        duration_sec=60)
        self._emit_ended(session_id=71, subject_id=8101, ended_at=999,
                        duration_sec=499)   # zweites ENDED (darf nicht sein)
        recs = SupportOverviewRepo(self.con).list_support_sessions()
        r = self._by_session(recs)[71]
        self.assertEqual(r.anomaly, ANOMALY_DOUBLE_ENDED)
        self.assertEqual(r.ended_at, 560)              # erster Beleg gewinnt
        self.assertEqual(r.duration_sec, 60)

    # ---- SO09: fehlende session_id -> anomaly, eigener Datensatz ------------
    def test_so09_missing_session_id(self):
        self._emit_ended_raw({"subject_id": 8201, "ended_at": 700,
                              "duration_sec": 40})   # KEIN session_id
        recs = SupportOverviewRepo(self.con).list_support_sessions()
        hits = [r for r in recs if r.anomaly == ANOMALY_MISSING_SESSION_ID]
        self.assertEqual(len(hits), 1)                 # nicht still verworfen
        self.assertEqual(hits[0].subject_id, 8201)

    # ---- SO10: fehlende Pflichttabelle -------------------------------------
    def test_so10_schema_guard(self):
        # Frische DB nur mit audit_log-Genesis, OHNE cases/person.
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
            with self.assertRaises(SupportOverviewSchemaError):
                SupportOverviewRepo(con).list_support_sessions()
        finally:
            con.close()

    # ---- SO11: verify_chain gruen nach allen Schreibvorgaengen --------------
    def test_so11_chain_intact(self):
        self.cases.create_case(subject_id=7009, username="c", actor_id=1)
        sid = self.support.start(7009, supporter_id=1, actor_id=1)
        self.support.end(sid, actor_id=1)
        self._emit_ended(session_id=88, subject_id=7010, ended_at=10,
                        duration_sec=5)   # herrenlos, aber sauber verkettet
        vr = AuditLog(self.con).verify_chain()
        self.assertTrue(vr.ok, vr.detail)
        # Und die Uebersicht liest ueber die intakte Kette:
        recs = SupportOverviewRepo(self.con).list_support_sessions()
        self.assertTrue(any(r.session_id == sid for r in recs))

    # ---- SO12: Legacy-Payloads (Schluessel 'user_id', vor M019) ------------
    def test_so12_legacy_payload_user_id_wird_weiter_gelesen(self):
        """SO12 (Build 469): audit_log ist eine unveraenderliche Hash-Kette —
        VOR M019 geschriebene STARTED/ENDED-Payloads tragen den Schluessel
        'user_id'. Der Fallback payload.get('subject_id',
        payload.get('user_id')) im Repo muss sie weiterhin aufloesen."""
        legacy_started = {"session_id": 91, "user_id": 8301,
                          "supporter_id": 1, "started_at": 100}
        self.writer.audited_write(
            do_write=lambda con: legacy_started,
            event_type=EventType.SUPPORT_SESSION_STARTED,
            actor_id=1, target_type="support_session",
            target_id="8301", meta=None)
        legacy_ended = {"session_id": 91, "user_id": 8301,
                        "ended_at": 160, "duration_sec": 60}
        self.writer.audited_write(
            do_write=lambda con: legacy_ended,
            event_type=EventType.SUPPORT_SESSION_ENDED,
            actor_id=1, target_type="support_session",
            target_id="91", meta=None)
        recs = SupportOverviewRepo(self.con).list_support_sessions()
        r = self._by_session(recs)[91]
        self.assertEqual(r.subject_id, 8301)     # via Legacy-Fallback aufgeloest
        self.assertEqual(r.ended_at, 160)
        self.assertIsNone(r.anomaly)


if __name__ == "__main__":
    unittest.main()

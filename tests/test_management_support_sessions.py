# =============================================================================
# tests/test_management_support_sessions.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite für Build 311: SupportSessionsRepo + Migration M003.
#
# S01 — start() → Zeile angelegt + SUPPORT_SESSION_STARTED, gibt session_id
# S02 — heartbeat() aktualisiert last_heartbeat, KEIN Audit
# S03 — end() setzt ended_at + SUPPORT_SESSION_ENDED
# S04 — end() idempotent: zweites end() → None, kein zweiter Audit
# S05 — get_active() ignoriert beendete und veraltete (stale) Sitzungen
# S06 — get_active() zählt mehrere gleichzeitige Sitzungen desselben Falls
# S07 — prune() entfernt beendete/veraltete, behält aktive
# S08 — heartbeat() auf beendeter Sitzung → False
# S09 — end() unbekannte session_id → SupportSessionsError
# S10 — verify_chain grün nach start+end
#
# Version: v0.7.311 · Build: 311 · 2026-07-01
# =============================================================================

import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.audit.audit_log import AuditLog
from management.audit.event_types import EventType
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.coordinator import m003_support_sessions
from management.support_sessions.support_sessions_repo import (
    SupportSessionsError,
    SupportSessionsRepo,
)

_INVESTIGATORS = """
CREATE TABLE investigators (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    system_username TEXT    NOT NULL UNIQUE,
    display_name    TEXT    NOT NULL,
    is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor   INTEGER NOT NULL DEFAULT 0,
    is_support      INTEGER NOT NULL DEFAULT 0,
    created_at      INTEGER NOT NULL
)
"""


class ManagementSupportSessionsTests(unittest.TestCase):

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
            "INSERT INTO investigators "
            "(id, system_username, display_name, is_investigator, is_supervisor, "
            " is_support, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(1, "h001", "Support Eins", 1, 0, 1, now),
             (2, "h002", "Support Zwei", 1, 0, 1, now)],
        )
        # support_sessions via echte Migration M003 anlegen (testet die DDL mit).
        m003_support_sessions.up(self.con)

        AuditLog.create_schema(self.con)
        self.audit = AuditLog(self.con)
        self.con.execute("BEGIN IMMEDIATE")
        self.audit.write_genesis({"note": "test-genesis"})
        self.con.execute("COMMIT")

        self.writer = CoordinatorWriter(self.con, self.audit)
        self.repo = SupportSessionsRepo(self.con, self.writer)

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
    def _audit_count(self):
        return self.con.execute(
            "SELECT COUNT(*) AS c FROM audit_log"
        ).fetchone()["c"]

    def _last_audit_type(self):
        return self.con.execute(
            "SELECT event_type FROM audit_log ORDER BY seq DESC LIMIT 1"
        ).fetchone()["event_type"]

    def _row(self, session_id):
        return self.con.execute(
            "SELECT * FROM support_sessions WHERE id = ?", (session_id,)
        ).fetchone()

    def _set_heartbeat(self, session_id, ts):
        self.con.execute(
            "UPDATE support_sessions SET last_heartbeat = ? WHERE id = ?",
            (ts, session_id),
        )

    # ------------------------------------------------------------------- S01
    def test_s01_start_creates_row_and_audit(self):
        sid = self.repo.start(user_id=42, supporter_id=1, actor_id=1)
        self.assertIsInstance(sid, int)
        row = self._row(sid)
        self.assertIsNotNone(row)
        self.assertEqual(row["user_id"], 42)
        self.assertEqual(row["supporter_id"], 1)
        self.assertIsNone(row["ended_at"])
        self.assertEqual(self._last_audit_type(),
                         EventType.SUPPORT_SESSION_STARTED)

    # ------------------------------------------------------------------- S02
    def test_s02_heartbeat_updates_no_audit(self):
        sid = self.repo.start(user_id=42, supporter_id=1, actor_id=1)
        self._set_heartbeat(sid, 1000)  # künstlich alt
        n_aud = self._audit_count()
        ok = self.repo.heartbeat(sid)
        self.assertTrue(ok)
        self.assertGreater(self._row(sid)["last_heartbeat"], 1000)
        # Heartbeat erzeugt KEINEN Audit-Eintrag.
        self.assertEqual(self._audit_count(), n_aud)

    # ------------------------------------------------------------------- S03
    def test_s03_end_sets_ended_and_audit(self):
        sid = self.repo.start(user_id=42, supporter_id=1, actor_id=1)
        seq = self.repo.end(sid, actor_id=1)
        self.assertIsNotNone(seq)
        self.assertIsNotNone(self._row(sid)["ended_at"])
        self.assertEqual(self._last_audit_type(),
                         EventType.SUPPORT_SESSION_ENDED)

    # ------------------------------------------------------------------- S04
    def test_s04_end_idempotent(self):
        sid = self.repo.start(user_id=42, supporter_id=1, actor_id=1)
        self.repo.end(sid, actor_id=1)
        n_aud = self._audit_count()
        again = self.repo.end(sid, actor_id=1)
        self.assertIsNone(again)  # bereits beendet
        self.assertEqual(self._audit_count(), n_aud)  # kein zweiter Beleg

    # ------------------------------------------------------------------- S05
    def test_s05_get_active_ignores_ended_and_stale(self):
        # aktive Sitzung
        active = self.repo.start(user_id=42, supporter_id=1, actor_id=1)
        # beendete Sitzung
        ended = self.repo.start(user_id=42, supporter_id=2, actor_id=2)
        self.repo.end(ended, actor_id=2)
        # veraltete Sitzung (Heartbeat weit in der Vergangenheit)
        stale = self.repo.start(user_id=42, supporter_id=2, actor_id=2)
        self._set_heartbeat(stale, int(time.time()) - 10_000)

        rows = self.repo.get_active(user_id=42, stale_sec=30)
        ids = [r["id"] for r in rows]
        self.assertEqual(ids, [active])

    # ------------------------------------------------------------------- S06
    def test_s06_get_active_counts_multiple(self):
        self.repo.start(user_id=42, supporter_id=1, actor_id=1)
        self.repo.start(user_id=42, supporter_id=2, actor_id=2)
        # anderer Fall — darf nicht mitzählen
        self.repo.start(user_id=99, supporter_id=1, actor_id=1)
        rows = self.repo.get_active(user_id=42, stale_sec=30)
        self.assertEqual(len(rows), 2)
        # sortiert nach started_at ASC (erster zuerst)
        self.assertEqual(rows[0]["system_username"], "h001")

    # ------------------------------------------------------------------- S07
    def test_s07_prune_removes_ended_and_stale_keeps_active(self):
        active = self.repo.start(user_id=42, supporter_id=1, actor_id=1)
        ended = self.repo.start(user_id=42, supporter_id=2, actor_id=2)
        self.repo.end(ended, actor_id=2)
        # ended_at künstlich weit in die Vergangenheit setzen
        self.con.execute(
            "UPDATE support_sessions SET ended_at = ? WHERE id = ?",
            (int(time.time()) - 10_000, ended),
        )
        stale = self.repo.start(user_id=43, supporter_id=1, actor_id=1)
        self._set_heartbeat(stale, int(time.time()) - 10_000)

        deleted = self.repo.prune(older_than_sec=3600)
        self.assertEqual(deleted, 2)
        remaining = [r["id"] for r in self.con.execute(
            "SELECT id FROM support_sessions ORDER BY id"
        ).fetchall()]
        self.assertEqual(remaining, [active])

    # ------------------------------------------------------------------- S08
    def test_s08_heartbeat_on_ended_returns_false(self):
        sid = self.repo.start(user_id=42, supporter_id=1, actor_id=1)
        self.repo.end(sid, actor_id=1)
        self.assertFalse(self.repo.heartbeat(sid))

    # ------------------------------------------------------------------- S09
    def test_s09_end_unknown_raises(self):
        with self.assertRaises(SupportSessionsError):
            self.repo.end(999999, actor_id=1)

    # ------------------------------------------------------------------- S10
    def test_s10_chain_verifies(self):
        sid = self.repo.start(user_id=42, supporter_id=1, actor_id=1)
        self.repo.heartbeat(sid)  # kein Audit
        self.repo.end(sid, actor_id=1)
        result = self.audit.verify_chain()
        self.assertTrue(result.ok, msg=getattr(result, "detail", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)

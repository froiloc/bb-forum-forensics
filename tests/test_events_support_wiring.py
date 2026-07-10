# =============================================================================
# tests/test_events_support_wiring.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite für Build 312: Verdrahtung der Support-Sitzungserfassung.
#
# SupportPresenceBinder (dedizierte coordinator.db-Direktverbindung):
#   W01 — begin() legt Zeile + SUPPORT_SESSION_STARTED an, gibt session_id,
#         setzt die client_id-Bindung
#   W02 — heartbeat() aktualisiert last_heartbeat, KEIN Audit
#   W03 — end() beendet Sitzung + SUPPORT_SESSION_ENDED, loest Bindung
#   W04 — end() ohne Bindung (unbekannte client_id) -> None, kein Audit
#   W05 — resume() haengt Sitzung um: gleiche session_id, KEIN neuer Beleg
#   W06 — resume() ohne Vorgaenger -> False
#   W07 — prune() beim ersten begin() entfernt verwaiste Alt-Sitzung
#   W08 — zwei begins -> zwei aktive Sitzungen (Zaehler), ein end() -> eine
#   W09 — close() beendet offene Sitzungen und schliesst die Verbindung
#   W10 — Audit-Kette bleibt gueltig (verify_chain) nach begin+resume+end
#
# _get_support_status (Read-Pfad, mode-aware, support_count):
#   P01 — mode='job', aktiver Status -> support_active True + support_count
#   P02 — mode='support' -> immer inaktiv (keine Selbstbeobachtung)
#   P03 — coordinator None -> inaktiv
#   P04 — inaktiver Status -> support_count 0
#   P05 — Exception im Read -> inaktiv (kein Absturz)
#
# Version: v0.7.312 · Build: 312 · 2026-07-02
# Beleg: Bauplan B7 v0.6 §6/§7, mc 2026-07-01.
# =============================================================================

import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.coordinator_db import SupportStatusRecord
from forensic_api.events import _get_support_status
from forensic_api.support_presence import SupportPresenceBinder
from management.audit.audit_log import AuditLog
from management.audit.event_types import EventType
from management.migrations.coordinator import m003_support_sessions

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


def _build_coordinator_db(path):
    """Legt eine coordinator.db mit person, support_sessions und
    initialisierter Audit-Kette (Genesis) an und schliesst die Verbindung."""
    con = sqlite3.connect(path)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    now = int(time.time())
    con.execute(_INVESTIGATORS)
    con.executemany(
        "INSERT INTO person "
        "(id, system_username, display_name, is_investigator, is_supervisor, "
        " is_support, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(1, "h001", "Support Eins", 1, 0, 1, now),
         (2, "h002", "Support Zwei", 1, 0, 1, now)],
    )
    m003_support_sessions.up(con)
    AuditLog.create_schema(con)
    audit = AuditLog(con)
    con.execute("BEGIN IMMEDIATE")
    audit.write_genesis({"note": "test-genesis"})
    con.execute("COMMIT")
    con.close()


class SupportPresenceBinderTests(unittest.TestCase):

    USER_ID = 42
    SUPPORTER_ID = 1

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        _build_coordinator_db(self.db_path)
        self.binder = SupportPresenceBinder(
            self.db_path,
            user_id=self.USER_ID,
            supporter_id=self.SUPPORTER_ID,
        )
        # Separate READ-Verbindung fuer Verifikation. Autocommit
        # (isolation_level=None), damit vereinzelte Test-Writes (W02/W07) keinen
        # offenen Schreiblock halten, gegen den der Binder liefe. Der
        # Produktivpfad hat NIE eine zweite schreibende Verbindung.
        self.vcon = sqlite3.connect(self.db_path)
        self.vcon.isolation_level = None
        self.vcon.row_factory = sqlite3.Row

    def tearDown(self):
        try:
            self.binder.close()
        except Exception:
            pass
        try:
            self.vcon.close()
        finally:
            for fn in os.listdir(self._tmp):
                try:
                    os.remove(os.path.join(self._tmp, fn))
                except OSError:
                    pass
            os.rmdir(self._tmp)

    # Helfer -----------------------------------------------------------------
    def _audit_count(self):
        return self.vcon.execute(
            "SELECT COUNT(*) AS c FROM audit_log"
        ).fetchone()["c"]

    def _last_audit_type(self):
        row = self.vcon.execute(
            "SELECT event_type FROM audit_log ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return row["event_type"] if row else None

    def _session_row(self, session_id):
        return self.vcon.execute(
            "SELECT * FROM support_sessions WHERE id = ?", (session_id,)
        ).fetchone()

    def _open_session_count(self):
        return self.vcon.execute(
            "SELECT COUNT(*) AS c FROM support_sessions WHERE ended_at IS NULL"
        ).fetchone()["c"]

    def _total_session_count(self):
        return self.vcon.execute(
            "SELECT COUNT(*) AS c FROM support_sessions"
        ).fetchone()["c"]

    # W01 -------------------------------------------------------------------
    def test_w01_begin_creates_row_and_audit(self):
        sid = self.binder.begin("client-A")
        self.assertIsInstance(sid, int)
        row = self._session_row(sid)
        self.assertIsNotNone(row)
        self.assertEqual(row["user_id"], self.USER_ID)
        self.assertEqual(row["supporter_id"], self.SUPPORTER_ID)
        self.assertIsNone(row["ended_at"])
        self.assertEqual(self._last_audit_type(),
                         EventType.SUPPORT_SESSION_STARTED)
        self.assertEqual(self.binder.session_id_for("client-A"), sid)

    # W02 -------------------------------------------------------------------
    def test_w02_heartbeat_updates_no_audit(self):
        sid = self.binder.begin("client-A")
        # last_heartbeat kuenstlich altern.
        self.vcon.execute(
            "UPDATE support_sessions SET last_heartbeat = 1000 WHERE id = ?",
            (sid,),
        )
        n_aud = self._audit_count()
        ok = self.binder.heartbeat("client-A")
        self.assertTrue(ok)
        self.assertGreater(self._session_row(sid)["last_heartbeat"], 1000)
        self.assertEqual(self._audit_count(), n_aud)  # kein Audit

    # W03 -------------------------------------------------------------------
    def test_w03_end_closes_and_audits(self):
        sid = self.binder.begin("client-A")
        seq = self.binder.end("client-A")
        self.assertIsInstance(seq, int)
        self.assertIsNotNone(self._session_row(sid)["ended_at"])
        self.assertEqual(self._last_audit_type(),
                         EventType.SUPPORT_SESSION_ENDED)
        # Bindung geloest.
        self.assertIsNone(self.binder.session_id_for("client-A"))

    # W04 -------------------------------------------------------------------
    def test_w04_end_without_binding_is_noop(self):
        n_aud = self._audit_count()
        result = self.binder.end("client-unbekannt")
        self.assertIsNone(result)
        self.assertEqual(self._audit_count(), n_aud)

    # W05 -------------------------------------------------------------------
    def test_w05_resume_rebinds_same_session_no_new_audit(self):
        sid = self.binder.begin("client-old")
        n_aud = self._audit_count()
        ok = self.binder.resume("client-old", "client-new")
        self.assertTrue(ok)
        # gleiche session_id auf neuer client_id, alte weg.
        self.assertEqual(self.binder.session_id_for("client-new"), sid)
        self.assertIsNone(self.binder.session_id_for("client-old"))
        # KEIN neuer Audit-Eintrag durch resume (nur Heartbeat).
        self.assertEqual(self._audit_count(), n_aud)
        # Sitzung weiterhin offen.
        self.assertIsNone(self._session_row(sid)["ended_at"])

    # W06 -------------------------------------------------------------------
    def test_w06_resume_without_predecessor_returns_false(self):
        ok = self.binder.resume("client-nie-dagewesen", "client-neu")
        self.assertFalse(ok)
        self.assertIsNone(self.binder.session_id_for("client-neu"))

    # W07 -------------------------------------------------------------------
    def test_w07_prune_on_first_begin_removes_orphan(self):
        # Verwaiste Alt-Sitzung: last_heartbeat weit in der Vergangenheit.
        old = int(time.time()) - 100000
        self.vcon.execute(
            "INSERT INTO support_sessions "
            "(user_id, supporter_id, started_at, last_heartbeat) "
            "VALUES (?, ?, ?, ?)",
            (self.USER_ID, self.SUPPORTER_ID, old, old),
        )
        self.assertEqual(self._total_session_count(), 1)
        # Erster begin() ruft prune() -> Waise entfernt, dann neue Zeile.
        self.binder.begin("client-A")
        self.assertEqual(self._total_session_count(), 1)  # nur die neue
        self.assertEqual(self._open_session_count(), 1)

    # W08 -------------------------------------------------------------------
    def test_w08_two_sessions_counter(self):
        self.binder.begin("client-A")
        self.binder.begin("client-B")
        self.assertEqual(self._open_session_count(), 2)
        self.binder.end("client-A")
        self.assertEqual(self._open_session_count(), 1)

    # W09 -------------------------------------------------------------------
    def test_w09_close_ends_open_sessions(self):
        self.binder.begin("client-A")
        self.binder.begin("client-B")
        self.assertEqual(self._open_session_count(), 2)
        self.binder.close()
        # Nach close(): keine offene Sitzung mehr.
        self.assertEqual(self._open_session_count(), 0)
        # Erneutes close() ist idempotent (kein Fehler).
        self.binder.close()

    # W10 -------------------------------------------------------------------
    def test_w10_audit_chain_valid(self):
        self.binder.begin("client-old")
        self.binder.resume("client-old", "client-new")
        self.binder.end("client-new")
        # Kette ueber eine frische AuditLog-Instanz pruefen.
        audit = AuditLog(self.vcon)
        result = audit.verify_chain()
        self.assertTrue(result.ok, "Audit-Kette gebrochen: %r" % (result,))


# ---------------------------------------------------------------------------
# _get_support_status — Read-Pfad-Payload
# ---------------------------------------------------------------------------

class _FakeCoordinator:
    """Minimaler Ersatz fuer CoordinatorDb.get_support_status()."""

    def __init__(self, record=None, raise_exc=False):
        self._record = record
        self._raise = raise_exc
        self.calls = []

    def get_support_status(self, user_id=None, stale_sec=30):
        self.calls.append((user_id, stale_sec))
        if self._raise:
            raise RuntimeError("simulierter Lesefehler")
        return self._record


class _FakeBundle:
    def __init__(self, coordinator):
        self.coordinator = coordinator


class _FakeContext:
    def __init__(self, mode, user_id):
        self.mode = mode
        self.user_id = user_id


class GetSupportStatusPayloadTests(unittest.TestCase):

    # P01 -------------------------------------------------------------------
    def test_p01_active_status_includes_count(self):
        rec = SupportStatusRecord(active=True, username="h002",
                                  since_ms=1234000, count=3)
        bundle = _FakeBundle(_FakeCoordinator(record=rec))
        ctx = _FakeContext(mode="job", user_id=42)
        out = _get_support_status(bundle, ctx)
        self.assertTrue(out["support_active"])
        self.assertEqual(out["support_user"], "h002")
        self.assertEqual(out["since"], 1234000)
        self.assertEqual(out["support_count"], 3)
        # Fall-user_id wurde an den Read durchgereicht.
        self.assertEqual(bundle.coordinator.calls[0][0], 42)

    # P02 -------------------------------------------------------------------
    def test_p02_support_mode_is_never_self_observing(self):
        rec = SupportStatusRecord(active=True, username="h002",
                                  since_ms=1, count=1)
        coord = _FakeCoordinator(record=rec)
        bundle = _FakeBundle(coord)
        ctx = _FakeContext(mode="support", user_id=42)
        out = _get_support_status(bundle, ctx)
        self.assertFalse(out["support_active"])
        self.assertEqual(out["support_count"], 0)
        # Im Support-Modus wird gar nicht erst gelesen.
        self.assertEqual(coord.calls, [])

    # P03 -------------------------------------------------------------------
    def test_p03_coordinator_none_is_inactive(self):
        bundle = _FakeBundle(None)
        ctx = _FakeContext(mode="cli", user_id=42)
        out = _get_support_status(bundle, ctx)
        self.assertFalse(out["support_active"])
        self.assertEqual(out["support_count"], 0)

    # P04 -------------------------------------------------------------------
    def test_p04_inactive_status_zero_count(self):
        rec = SupportStatusRecord(active=False, username=None,
                                  since_ms=None, count=0)
        bundle = _FakeBundle(_FakeCoordinator(record=rec))
        ctx = _FakeContext(mode="job", user_id=42)
        out = _get_support_status(bundle, ctx)
        self.assertFalse(out["support_active"])
        self.assertIsNone(out["support_user"])
        self.assertEqual(out["support_count"], 0)

    # P05 -------------------------------------------------------------------
    def test_p05_read_exception_is_inactive(self):
        bundle = _FakeBundle(_FakeCoordinator(raise_exc=True))
        ctx = _FakeContext(mode="job", user_id=42)
        out = _get_support_status(bundle, ctx)
        self.assertFalse(out["support_active"])
        self.assertEqual(out["support_count"], 0)


if __name__ == "__main__":
    unittest.main()

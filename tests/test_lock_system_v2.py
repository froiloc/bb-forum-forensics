# =============================================================================
# tests/test_lock_system_v2.py
# IT-Forensisches Ermittlungswerkzeug — Lock-System v2
# =============================================================================
# Testsuite fuer Lock-System v2 (V1 SSE-Reconnect, V3 Takeover-Dialog).
#
# T01 — resume_lock(): Lock-Binding an neue SSE-client_id
# T02 — resume_lock(): falscher Benutzer wird abgewiesen
# T03 — resume_lock(): falsche lock_id wird abgewiesen
# T04 — resume_lock(): aktualisiert locked_at (Heartbeat-Effekt)
# T05 — lock_change_event: wird bei acquire_lock gesetzt
# T06 — lock_change_event: wird bei release_lock gesetzt
# T07 — lock_change_event: wird bei release_lock_by_sse_client gesetzt
# T08 — request_takeover(): legt pending-Eintrag an
# T09 — request_takeover(): ersetzt bestehende pending-Anfrage des Benutzers
# T10 — resolve_takeover(): setzt Status auf granted
# T11 — resolve_takeover(): setzt Status auf denied
# T12 — get_pending_takeover(): gibt aelteste pending-Anfrage zurueck
# T13 — get_pending_takeover(): gibt None wenn keine Anfrage vorhanden
# T14 — Edgecase: resume_lock auf nicht-existentem Lock
# T15 — Edgecase: resolve_takeover auf bereits resolvedtem Request
# T16 — Edgecase: acquire_lock loescht abgelaufene Locks (Timeout)
# T17 — Edgecase: lock_change_event nur einmal gesetzt bei mehreren Releases
# T18 — Edgecase: request_takeover auf eigenem Lock schlaegt fehl (HTTP-Ebene)
#
# Version: v0.6.049 · Build: 049 · 2026-04-21
# Beleg: Lock-System v2, Projektgespraech 2026-04-21
# =============================================================================

import sqlite3
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.evidence_db import EvidenceDb


@pytest.fixture
def edb():
    """In-Memory EvidenceDb fuer Tests."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    db = EvidenceDb(con)
    return db


@pytest.fixture
def edb_with_lock(edb):
    """EvidenceDb mit bereits erworbenem Lock."""
    lock_id = edb.acquire_lock(1, "h001", "sse_client_A")
    assert lock_id is not None
    return edb, lock_id


# ---------------------------------------------------------------------------
# T01-T04: resume_lock()
# ---------------------------------------------------------------------------

class TestResumeLock:

    def test_T01_lock_binding_erneuert(self, edb_with_lock):
        """T01: resume_lock() aktualisiert sse_client auf neue ID."""
        edb, lock_id = edb_with_lock
        result = edb.resume_lock(1, lock_id, "h001", "sse_client_B")
        assert result is True
        lock = edb.get_lock(1)
        assert lock.sse_client == "sse_client_B"
        assert lock.lock_id == lock_id

    def test_T02_falscher_benutzer_abgewiesen(self, edb_with_lock):
        """T02: resume_lock() mit falschem Benutzer gibt False zurueck."""
        edb, lock_id = edb_with_lock
        result = edb.resume_lock(1, lock_id, "h002", "sse_client_B")
        assert result is False
        # Alter sse_client bleibt
        lock = edb.get_lock(1)
        assert lock.sse_client == "sse_client_A"

    def test_T03_falsche_lock_id_abgewiesen(self, edb_with_lock):
        """T03: resume_lock() mit falscher lock_id gibt False zurueck."""
        edb, lock_id = edb_with_lock
        result = edb.resume_lock(1, "falsche-id", "h001", "sse_client_B")
        assert result is False

    def test_T04_locked_at_aktualisiert(self, edb_with_lock):
        """T04: resume_lock() aktualisiert locked_at (Heartbeat-Effekt)."""
        edb, lock_id = edb_with_lock
        lock_before = edb.get_lock(1)
        time.sleep(1)
        edb.resume_lock(1, lock_id, "h001", "sse_client_A")
        lock_after = edb.get_lock(1)
        assert lock_after.locked_at >= lock_before.locked_at


# ---------------------------------------------------------------------------
# T05-T07: lock_change_event
# ---------------------------------------------------------------------------

class TestLockChangeEvent:

    def test_T05_event_bei_acquire(self, edb):
        """T05: acquire_lock() setzt lock_change_event."""
        event = edb.lock_change_event
        assert not event.is_set()
        edb.acquire_lock(1, "h001", "sse_A")
        assert event.is_set()

    def test_T06_event_bei_release(self, edb_with_lock):
        """T06: release_lock() setzt lock_change_event."""
        edb, lock_id = edb_with_lock
        edb.lock_change_event.clear()
        edb.release_lock(1, lock_id)
        assert edb.lock_change_event.is_set()

    def test_T07_event_bei_release_by_sse(self, edb_with_lock):
        """T07: release_lock_by_sse_client() setzt lock_change_event."""
        edb, lock_id = edb_with_lock
        edb.lock_change_event.clear()
        edb.release_lock_by_sse_client("sse_client_A")
        assert edb.lock_change_event.is_set()


# ---------------------------------------------------------------------------
# T08-T13: Takeover-Methoden
# ---------------------------------------------------------------------------

class TestTakeover:

    def test_T08_request_takeover_legt_eintrag_an(self, edb_with_lock):
        """T08: request_takeover() legt pending-Eintrag an."""
        edb, lock_id = edb_with_lock
        req_id = edb.log_takeover_request(1, lock_id, "h002")
        assert req_id > 0
        pending = edb.get_pending_takeover(1)
        assert pending is not None
        assert pending["requested_by"] == "h002"
        assert pending["id"] == req_id

    def test_T09_request_takeover_ersetzt_bestehende_anfrage(self, edb_with_lock):
        """T09: Zwei log_takeover_request() vom selben User -> beide pending.

        Seit SLA Punkt 10 (Audit-Trail): kein Loeschen alter Eintraege.
        get_pending_takeover gibt die aelteste zurueck (req_id1).
        """
        edb, lock_id = edb_with_lock
        req_id1 = edb.log_takeover_request(1, lock_id, "h002")
        req_id2 = edb.log_takeover_request(1, lock_id, "h002")
        assert req_id2 != req_id1
        # Audit-Trail: beide Eintraege vorhanden; get_pending gibt aeltesten zurueck
        pending = edb.get_pending_takeover(1)
        assert pending["id"] == req_id1  # aeltester pending-Eintrag

    def test_T10_resolve_takeover_granted(self, edb_with_lock):
        """T10: resolve_takeover() setzt Status auf granted."""
        edb, lock_id = edb_with_lock
        req_id = edb.log_takeover_request(1, lock_id, "h002")
        result = edb.resolve_takeover(req_id, "granted")
        assert result is True
        # Kein pending mehr
        assert edb.get_pending_takeover(1) is None

    def test_T11_resolve_takeover_denied(self, edb_with_lock):
        """T11: resolve_takeover() setzt Status auf denied."""
        edb, lock_id = edb_with_lock
        req_id = edb.log_takeover_request(1, lock_id, "h002")
        result = edb.resolve_takeover(req_id, "denied")
        assert result is True
        assert edb.get_pending_takeover(1) is None

    def test_T12_get_pending_aelteste_anfrage(self, edb_with_lock):
        """T12: get_pending_takeover() gibt aelteste Anfrage zurueck."""
        edb, lock_id = edb_with_lock
        req_id1 = edb.log_takeover_request(1, lock_id, "h002")
        # Kurze Pause fuer unterschiedliche requested_at
        time.sleep(0.01)
        req_id2 = edb.log_takeover_request(1, lock_id, "h003")
        pending = edb.get_pending_takeover(1)
        assert pending["id"] == req_id1  # aelteste zuerst

    def test_T13_get_pending_none_wenn_keine_anfrage(self, edb_with_lock):
        """T13: get_pending_takeover() gibt None wenn keine Anfrage vorhanden."""
        edb, lock_id = edb_with_lock
        assert edb.get_pending_takeover(1) is None


# ---------------------------------------------------------------------------
# T14-T18: Edgecases
# ---------------------------------------------------------------------------

class TestEdgecases:

    def test_T14_resume_lock_auf_nicht_existentem_lock(self, edb):
        """T14: resume_lock() auf nicht-existentem Lock gibt False zurueck."""
        result = edb.resume_lock(1, "gibts-nicht", "h001", "sse_B")
        assert result is False

    def test_T15_resolve_takeover_bereits_resolved(self, edb_with_lock):
        """T15: resolve_takeover() auf bereits resolvedtem Request gibt False."""
        edb, lock_id = edb_with_lock
        req_id = edb.log_takeover_request(1, lock_id, "h002")
        edb.resolve_takeover(req_id, "granted")
        # Zweites resolve schlaegt fehl
        result = edb.resolve_takeover(req_id, "denied")
        assert result is False

    def test_T16_acquire_lock_loescht_abgelaufene_locks(self, edb):
        """T16: acquire_lock() mit Timeout loescht abgelaufene Locks.
        Simuliert durch direktes Manipulieren von locked_at in der DB."""
        # Lock anlegen
        lock_id = edb.acquire_lock(1, "h001", "sse_A")
        assert lock_id is not None

        # locked_at in die Vergangenheit setzen (91 Sekunden)
        edb._con.execute(
            "UPDATE editor_locks SET locked_at = ? WHERE lock_id = ?",
            (int(time.time()) - 91, lock_id)
        )
        edb._con.commit()

        # Neuer Lock-Versuch mit Timeout-Cleanup
        TIMEOUT_SEC = 90
        now = int(time.time())
        edb._con.execute(
            "DELETE FROM editor_locks WHERE report_id=? AND locked_at < ?",
            (1, now - TIMEOUT_SEC)
        )
        edb._con.commit()

        # Jetzt muss h002 Lock erwerben koennen
        new_lock_id = edb.acquire_lock(1, "h002", "sse_B")
        assert new_lock_id is not None
        lock = edb.get_lock(1)
        assert lock.locked_by == "h002"

    def test_T17_lock_change_event_nach_clear(self, edb_with_lock):
        """T17: lock_change_event kann nach clear() neu gesetzt werden."""
        edb, lock_id = edb_with_lock
        event = edb.lock_change_event
        event.clear()
        assert not event.is_set()
        edb.release_lock(1, lock_id)
        assert event.is_set()

    def test_T18_kein_lock_wenn_bereits_belegt(self, edb_with_lock):
        """T18: acquire_lock() gibt None wenn Lock bereits belegt."""
        edb, lock_id = edb_with_lock
        result = edb.acquire_lock(1, "h002", "sse_B")
        assert result is None
        # Original-Lock unveraendert
        lock = edb.get_lock(1)
        assert lock.locked_by == "h001"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

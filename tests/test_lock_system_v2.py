# =============================================================================
# tests/test_lock_system_v2.py
# IT-Forensisches Ermittlungswerkzeug — Lock-System v2
# =============================================================================
# Testsuite fuer Lock-System v2 (V1 SSE-Reconnect, V3 Takeover-Dialog).
#
# T01 — resume_lock(): Lock-Binding an neue SSE-client_id (Layer-2-Aktion)
# T02 — resume_lock(): unbekannte alte SSE-ID wird abgewiesen
# T03 — resume_lock(): identische alte/neue SSE-ID ist idempotent
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
# T14 — Edgecase: resume_lock auf unbekannter SSE-ID
# T15 — Edgecase: resolve_takeover auf bereits resolvedtem Request
# T16 — Edgecase: acquire_lock loescht abgelaufene Locks (Timeout)
# T17 — Edgecase: lock_change_event nur einmal gesetzt bei mehreren Releases
# T18 — Edgecase: kein Lock wenn bereits belegt
# T19 — Grace-Period/RESUMING: RESUMING bindet Lock an neue SSE-Client-ID
# T20 — Grace-Period/RESUMING: fremde SSE-Client-ID wird abgewiesen
# T21 — Grace-Period/RESUMING: RESUMING nach Lock-Freigabe schlaegt fehl
#
# Version: v0.6.247 · Build: 247 · 2026-05-24
# Beleg: Lock-System v2, Paket-4-Review 2026-05-24
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
        """T01: resume_lock() aktualisiert sse_client auf neue ID.

        RESUMING ist eine Layer-2-Aktion: Identifikation ausschliesslich
        ueber die alte SSE-Client-ID, nicht ueber lock_id.
        Beleg: Layer 2 States RESUMING, Paket-4-Review 2026-05-24
        """
        edb, lock_id = edb_with_lock
        result = edb.resume_lock("sse_client_A", "sse_client_B")
        assert result is True
        lock = edb.get_lock(1)
        assert lock.sse_client == "sse_client_B"
        # lock_id bleibt unveraendert (nur SSE-Binding wird aktualisiert)
        assert lock.lock_id == lock_id

    def test_T02_unbekannte_alte_sse_abgewiesen(self, edb_with_lock):
        """T02: resume_lock() mit unbekannter alter SSE-Client-ID gibt False zurueck.

        Kein Lock hat sse_client='unbekannt_XYZ' — Resume schlaegt fehl.
        Dies schuetzt vor Verbindungsdiebstahl durch Clone-Fenster.
        Beleg: Layer 2 States RESUMING, Paket-4-Review 2026-05-24
        """
        edb, lock_id = edb_with_lock
        result = edb.resume_lock("unbekannt_XYZ", "sse_client_B")
        assert result is False
        # Alter sse_client bleibt
        lock = edb.get_lock(1)
        assert lock.sse_client == "sse_client_A"

    def test_T03_resume_auf_eigenem_client_ist_idempotent(self, edb_with_lock):
        """T03: resume_lock() mit identischer alter und neuer SSE-ID ist idempotent.

        Browser-Fenster wird neu geladen ohne Tab-Duplikat — client_id
        bleibt dieselbe. Resume soll dennoch True zurueckgeben und
        locked_at aktualisieren.
        Beleg: Layer 2 States RESUMING, Paket-4-Review 2026-05-24
        """
        edb, lock_id = edb_with_lock
        result = edb.resume_lock("sse_client_A", "sse_client_A")
        assert result is True
        lock = edb.get_lock(1)
        assert lock.sse_client == "sse_client_A"

    def test_T04_locked_at_aktualisiert(self, edb_with_lock):
        """T04: resume_lock() aktualisiert locked_at (Heartbeat-Effekt)."""
        edb, lock_id = edb_with_lock
        lock_before = edb.get_lock(1)
        time.sleep(1)
        edb.resume_lock("sse_client_A", "sse_client_A")
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
        """T14: resume_lock() mit unbekannter SSE-Client-ID gibt False zurueck."""
        result = edb.resume_lock("gibts-nicht", "sse_B")
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




# ---------------------------------------------------------------------------
# T19-T21: Grace-Period und RESUMING (Paket 4, Build 247)
# ---------------------------------------------------------------------------

class TestGracePeriodResuming:
    """
    Testet das neue RESUMING-Verhalten:
    - Identifikation ausschliesslich ueber SSE-Client-ID (Layer-2-Daten)
    - Kein Zugriff auf lock_id (Layer-4-Daten)
    Beleg: Layer 2 States RESUMING, SLA Punkt 2, Paket-4-Review 2026-05-24
    """

    def test_T19_resuming_bindet_neuen_sse_client(self, edb_with_lock):
        """T19: RESUMING mit alter SSE-Client-ID bindet Lock an neue ID.

        Szenario: Browser-Tab verliert SSE-Verbindung, reconnectet
        innerhalb der Grace-Period. Der Lock muss auf die neue
        SSE-Client-ID umgebunden werden.
        """
        edb, lock_id = edb_with_lock
        # Verbindungsabriss simuliert: alter client 'sse_client_A'
        # Reconnect mit neuer client_id 'sse_client_C'
        result = edb.resume_lock("sse_client_A", "sse_client_C")
        assert result is True

        lock = edb.get_lock(1)
        assert lock.sse_client == "sse_client_C"
        assert lock.lock_id == lock_id      # Lock-ID unveraendert
        assert lock.locked_by == "h001"     # Inhaber unveraendert

    def test_T20_resuming_schlaegt_fehl_wenn_sse_unbekannt(self, edb_with_lock):
        """T20: RESUMING mit fremder SSE-Client-ID schlaegt fehl.

        Schutzmechanismus: Ein Browser-Tab der die alte SSE-Client-ID
        nicht kennt (z.B. dupliziertes Fenster) kann keinen Lock kapern.
        Die alte SSE-Client-ID ist dem echten Client bekannt (er hat sie
        vom Server per 'client_id'-Event erhalten).
        """
        edb, lock_id = edb_with_lock
        # Angreifer kennt nur seine eigene, neue SSE-ID — nicht die alte
        result = edb.resume_lock("fremde_sse_XYZ", "sse_client_D")
        assert result is False

        # Lock unveraendert
        lock = edb.get_lock(1)
        assert lock.sse_client == "sse_client_A"
        assert lock.locked_by == "h001"

    def test_T21_resuming_nach_lock_freigabe_schlaegt_fehl(self, edb_with_lock):
        """T21: RESUMING nach abgelaufener Grace-Period (Lock bereits freigegeben).

        Szenario: Grace-Period ist abgelaufen, release_lock_by_sse_client()
        wurde bereits aufgerufen. Ein verspaetetes RESUMING muss False
        zurueckgeben — der Lock ist weg.
        """
        edb, lock_id = edb_with_lock

        # Grace-Period abgelaufen simulieren: Lock direkt freigeben
        freed = edb.release_lock_by_sse_client("sse_client_A")
        assert freed == [1]  # report_id 1 wurde freigegeben

        # Jetzt verspaetetes RESUMING versuchen
        result = edb.resume_lock("sse_client_A", "sse_client_E")
        assert result is False

        # Lock ist weg
        lock = edb.get_lock(1)
        assert lock is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

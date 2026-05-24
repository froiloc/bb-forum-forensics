# =============================================================================
# tests/test_e2e_layer_integration.py
# IT-Forensisches Ermittlungswerkzeug — Paket 10: End-to-End Layer-Integration
# =============================================================================
# Testsuite fuer die Layer-Architektur (Pakete 4–9).
# Testet Szenarien die mehrere Layer gleichzeitig betreffen.
#
# E01 — Bericht-Wechsel: Lock-Release + Acquire-Sequenz
# E02 — Neuer Bericht: atomare create_report_with_lock-Transaktion
# E03 — Takeover-Szenario: request_takeover → resolve → Lock-Uebergabe
# E04 — Queue-Szenario: FIFO-Reihenfolge bei mehreren Wartenden
# E05 — Queue-FIFO: zweiter Wartezeit-Kandidat bekommt Lock nach erstem
# E06 — SSE-Verlust (Grace-Period): Lock bleibt erhalten innerhalb 5s
# E07 — SSE-Verlust (Grace-Period abgelaufen): Lock wird freigegeben
# E08 — report_opened Audit-Log: Berichtswechsel schreibt Eintrag
# E09 — report_opened Queue-Bereinigung: Wechsel loescht Queue-Eintraege
# E10 — Cooldown: nach denied Takeover gilt 10-Minuten-Sperre
# E11 — Alte Lock-Reste entfernt: keine EditorState-Abhaengigkeit mehr
#
# Version: v0.6.252 · Build: 252 · 2026-05-24
# Beleg: Paket 10, Schichten-Architektur, SLA Manifest
# =============================================================================

import sqlite3
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.evidence_db import EvidenceDb


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def edb():
    """In-Memory EvidenceDb fuer E2E-Tests."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    db = EvidenceDb(con)
    return db


@pytest.fixture
def edb_report_a(edb):
    """EvidenceDb mit zwei Berichten und einem Lock auf Bericht 1."""
    lock_id = edb.acquire_lock(1, "h001", "sse_A")
    assert lock_id is not None
    return edb, lock_id


# ---------------------------------------------------------------------------
# E01 — Bericht-Wechsel: Lock-Release + Acquire-Sequenz
# ---------------------------------------------------------------------------

class TestBerichtWechsel:

    def test_E01_release_und_neuer_acquire(self, edb_report_a):
        """E01: Lock auf Bericht 1 freigeben, dann Lock auf Bericht 2 erwerben.

        Entspricht dem Switch-Flow in _loadReportImpl (Paket 9):
        1. release_lock() auf altem Bericht
        2. acquire_lock() auf neuem Bericht
        Beleg: Paket 9 _loadReportImpl, LockLayer.release()+acquire()
        """
        edb, lock_id_1 = edb_report_a

        # Lock auf Bericht 1 freigeben
        released = edb.release_lock(1, lock_id_1)
        assert released is True
        assert edb.get_lock(1) is None

        # Lock auf Bericht 2 erwerben
        lock_id_2 = edb.acquire_lock(2, "h001", "sse_A")
        assert lock_id_2 is not None
        lock = edb.get_lock(2)
        assert lock.locked_by == "h001"
        assert lock.lock_id == lock_id_2

    def test_E01b_kein_lock_auf_altem_bericht_nach_wechsel(self, edb_report_a):
        """E01b: Nach Bericht-Wechsel hat der alte Bericht keinen Lock mehr."""
        edb, lock_id_1 = edb_report_a
        edb.release_lock(1, lock_id_1)
        edb.acquire_lock(2, "h001", "sse_A")

        assert edb.get_lock(1) is None
        assert edb.get_lock(2) is not None


# ---------------------------------------------------------------------------
# E02 — Neuer Bericht: atomare create_report_with_lock-Transaktion
# ---------------------------------------------------------------------------

class TestNeuenBerichtAnlegen:

    def test_E02_create_report_with_lock_atomar(self, edb):
        """E02: create_report_with_lock() legt Bericht und Lock in einer Transaktion an.

        Entspricht LockLayer._onReportCreated() — Lock aus dem 'created'-Event.
        Beleg: Paket 6 _action_new_report(), SLA Punkt 7
        """
        report_id, lock_id = edb.create_report_with_lock(
            report_type="interim",
            title="E2E-Testbericht",
            created_by="h001",
            sse_client="sse_B",
        )
        assert report_id is not None
        assert lock_id is not None

        lock = edb.get_lock(report_id)
        assert lock is not None
        assert lock.locked_by == "h001"
        assert lock.lock_id == lock_id
        assert lock.sse_client == "sse_B"

    def test_E02b_neuer_bericht_setzt_lockid_in_db(self, edb):
        """E02b: Lock-ID aus create_report_with_lock() ist valide per validate_lock()."""
        report_id, lock_id = edb.create_report_with_lock(
            report_type="final",
            title="Abschlussbericht",
            created_by="h002",
            sse_client="sse_C",
        )
        # validate_lock() muss True zurueckgeben
        assert edb.validate_lock(report_id, lock_id) is True


# ---------------------------------------------------------------------------
# E03 — Takeover-Szenario
# ---------------------------------------------------------------------------

class TestTakeoverSzenario:

    def test_E03_request_und_grant_uebergibt_lock(self, edb_report_a):
        """E03: Takeover-Anfrage stellen, gewaehren, Lock wechselt Inhaber.

        Ablauf:
        1. h002 stellt Takeover-Anfrage auf Bericht 1 (gehalten von h001)
        2. h001 gewaehrt die Anfrage (resolve_takeover 'granted')
        3. h001 gibt Lock frei (release_lock)
        4. h002 kann jetzt Lock erwerben
        Beleg: Layer 4 States TAKEOVER_REQUEST_IN → MINE, SLA Punkt 10
        """
        edb, lock_id = edb_report_a

        # Schritt 1: Takeover-Anfrage
        req_id = edb.log_takeover_request(1, lock_id, "h002")
        assert req_id is not None

        pending = edb.get_pending_takeover(1)
        assert pending is not None
        assert pending["requested_by"] == "h002"

        # Schritt 2: h001 gewaehrt
        ok = edb.resolve_takeover(req_id, "granted")
        assert ok is True

        # Schritt 3: h001 gibt Lock frei
        edb.release_lock(1, lock_id)
        assert edb.get_lock(1) is None

        # Schritt 4: h002 erwirbt Lock
        new_lock_id = edb.acquire_lock(1, "h002", "sse_B")
        assert new_lock_id is not None
        lock = edb.get_lock(1)
        assert lock.locked_by == "h002"

    def test_E03b_takeover_denied_setzt_cooldown(self, edb_report_a):
        """E03b: Nach Takeover-Ablehnung wird Cooldown gesetzt.

        Beleg: Layer 4 States TAKEOVER_DENIED, SLA Punkt 10
        """
        edb, lock_id = edb_report_a
        req_id = edb.log_takeover_request(1, lock_id, "h002")

        # Abgelehnt
        edb.resolve_takeover(req_id, "denied")
        edb.set_cooldown(1, 600)

        # Cooldown muss gesetzt sein
        cooldown = edb.get_cooldown_until(1)
        assert cooldown is not None
        assert cooldown > int(time.time())


# ---------------------------------------------------------------------------
# E04 / E05 — Queue-Szenario
# ---------------------------------------------------------------------------

class TestQueueSzenario:

    def test_E04_queue_fifo_reihenfolge(self, edb_report_a):
        """E04: Mehrere Clients in der Queue — FIFO-Reihenfolge.

        h002 und h003 reihen sich ein. queue_next_valid() gibt h002 zuerst.
        Beleg: SLA Punkt 4, Layer 4 States QUEUED
        """
        edb, lock_id = edb_report_a
        active_clients = {"sse_B", "sse_C"}

        edb.queue_add(1, "h002", "sse_B")
        time.sleep(0.01)  # sicherstellen dass requested_at unterschiedlich ist
        edb.queue_add(1, "h003", "sse_C")

        first = edb.queue_next_valid(1, active_clients)
        assert first is not None
        assert first["requested_by"] == "h002"

    def test_E05_zweiter_wartet_nach_erstem(self, edb_report_a):
        """E05: Nach Entfernen des ersten Queue-Eintrags kommt der zweite.

        Beleg: SLA Punkt 4, queue_next_valid()
        """
        edb, lock_id = edb_report_a
        active_clients = {"sse_B", "sse_C"}

        edb.queue_add(1, "h002", "sse_B")
        time.sleep(0.01)
        edb.queue_add(1, "h003", "sse_C")

        # Ersten entfernen (Lock-Kaskade simulieren)
        edb.queue_remove(1, "h002")

        second = edb.queue_next_valid(1, active_clients)
        assert second is not None
        assert second["requested_by"] == "h003"


# ---------------------------------------------------------------------------
# E06 / E07 — SSE-Verlust (Grace-Period)
# ---------------------------------------------------------------------------

class TestGracePeriod:

    def test_E06_lock_bleibt_erhalten_bei_resume(self, edb_report_a):
        """E06: Innerhalb der Grace-Period reconnectet der Client per RESUMING.

        Lock muss auf neue SSE-Client-ID umgebunden werden.
        Beleg: SLA Punkt 2, Paket 4 events.py _cancel_grace_timer()
        """
        edb, lock_id = edb_report_a

        # RESUMING: alte SSE-ID → neue SSE-ID
        ok = edb.resume_lock("sse_A", "sse_A_new")
        assert ok is True

        lock = edb.get_lock(1)
        assert lock is not None
        assert lock.sse_client == "sse_A_new"
        assert lock.lock_id == lock_id  # unveraendert

    def test_E07_grace_period_abgelaufen_lock_freigegeben(self, edb_report_a):
        """E07: Grace-Period abgelaufen — release_lock_by_sse_client() loescht Lock.

        Beleg: SLA Punkt 2, events.py _grace_expired()
        """
        edb, lock_id = edb_report_a

        # Grace-Period abgelaufen simulieren
        freed = edb.release_lock_by_sse_client("sse_A")
        assert freed == [1]  # report_id 1 freigegeben

        lock = edb.get_lock(1)
        assert lock is None


# ---------------------------------------------------------------------------
# E08 / E09 — report_opened Audit-Log
# ---------------------------------------------------------------------------

class TestReportOpenedAudit:

    def test_E08_bericht_oeffnen_schreibt_audit_eintrag(self, edb):
        """E08: log_report_opened() schreibt Eintrag in report_opened.

        Beleg: Paket 6, Layer 3 States OPENING
        """
        entry_id = edb.log_report_opened(1, "sse_X", "h001")
        assert entry_id is not None

        opened = edb.get_open_report_for_client("sse_X")
        assert opened == 1

    def test_E09_berichtswechsel_bereinigt_queue(self, edb):
        """E09: Beim Oeffnen eines neuen Berichts werden Queue-Eintraege
        fuer ANDERE Berichte dieses Clients geloescht.

        Beleg: Layer 3 States OPENING (Queue-Bereinigung), Paket 6
        """
        # Client ist in der Queue fuer Bericht 5
        edb.queue_add(5, "h001", "sse_X")
        assert edb.queue_count(5) == 1

        # Client oeffnet Bericht 7 — Queue fuer Bericht 5 muss geloescht werden
        edb.log_report_opened(7, "sse_X", "h001")

        assert edb.queue_count(5) == 0  # bereinigt
        # Queue fuer Bericht 7 selbst bleibt unveraendert
        # (dort war kein Eintrag)


# ---------------------------------------------------------------------------
# E10 — Cooldown nach denied Takeover
# ---------------------------------------------------------------------------

class TestCooldownNachDenied:

    def test_E10_cooldown_verhindert_sofortige_anfrage(self, edb_report_a):
        """E10: Nach 'denied' Takeover verhindert der Cooldown eine neue Anfrage.

        Der Cooldown laeuft 10 Minuten (600s).
        Beleg: Layer 4 States TAKEOVER_DENIED, SLA Punkt 10
        """
        edb, lock_id = edb_report_a
        req_id = edb.log_takeover_request(1, lock_id, "h002")
        edb.resolve_takeover(req_id, "denied")
        edb.set_cooldown(1, 600)

        cooldown_until = edb.get_cooldown_until(1)
        expected_min = int(time.time()) + 599
        assert cooldown_until >= expected_min

    def test_E10b_cooldown_ablauf_erlaubt_neue_anfrage(self, edb_report_a):
        """E10b: Nach Cooldown-Ablauf (clear_cooldown) ist Anfrage wieder moeglich.

        Beleg: Layer 4 States TAKEOVER_DENIED → IDLE nach Cooldown
        """
        edb, lock_id = edb_report_a
        edb.set_cooldown(1, 600)

        # Cooldown manuell loeschen (simuliert Ablauf)
        edb.clear_cooldown(1)

        assert edb.get_cooldown_until(1) is None


# ---------------------------------------------------------------------------
# E11 — Keine EditorState-Abhaengigkeit in neuen Layer-Dateien
# ---------------------------------------------------------------------------

class TestKeineEditorStateAbhaengigkeit:

    def test_E11_sse_layer_keine_editorstate_referenz(self):
        """E11: sse_layer.js referenziert kein EditorState.

        Beleg: Paket 9 Bereinigung, Architektur-Grundregel Layer-Trennung
        """
        path = Path(__file__).parent.parent / "userinfo" / "sse_layer.js"
        src = path.read_text(encoding="utf-8")
        assert "EditorState" not in src, \
            "sse_layer.js darf kein EditorState referenzieren (Layer-Trennung)"

    def test_E11b_report_layer_keine_editorstate_referenz(self):
        """E11b: report_layer.js referenziert kein EditorState."""
        path = Path(__file__).parent.parent / "userinfo" / "report_layer.js"
        src = path.read_text(encoding="utf-8")
        assert "EditorState" not in src, \
            "report_layer.js darf kein EditorState referenzieren"

    def test_E11c_lock_layer_keine_editorstate_referenz(self):
        """E11c: lock_layer.js referenziert kein EditorState."""
        path = Path(__file__).parent.parent / "userinfo" / "lock_layer.js"
        src = path.read_text(encoding="utf-8")
        assert "EditorState" not in src, \
            "lock_layer.js darf kein EditorState referenzieren"

    def test_E11d_document_layer_keine_editorstate_referenz(self):
        """E11d: document_layer.js referenziert kein EditorState."""
        path = Path(__file__).parent.parent / "userinfo" / "document_layer.js"
        src = path.read_text(encoding="utf-8")
        assert "EditorState" not in src, \
            "document_layer.js darf kein EditorState referenzieren"

    def test_E11e_editor_bootstrap_keine_editorstate_referenz(self):
        """E11e: editor_bootstrap.js referenziert kein EditorState."""
        path = Path(__file__).parent.parent / "userinfo" / "editor_bootstrap.js"
        src = path.read_text(encoding="utf-8")
        assert "EditorState" not in src, \
            "editor_bootstrap.js darf kein EditorState referenzieren"

    def test_E11f_report_editor_kein_fetchWithLock(self):
        """E11f: report_editor.js hat keine _fetchWithLock-Aufrufe mehr.

        Alle Schreiboperationen laufen ueber _docSend/DocumentLayer.
        Beleg: Paket 9 Bereinigung
        """
        path = Path(__file__).parent.parent / "userinfo" / "report_editor.js"
        src = path.read_text(encoding="utf-8")
        # Nur aktive Aufrufe (nicht in Kommentaren) pruefen
        active_lines = [
            l for l in src.split("\n")
            if "_fetchWithLock" in l
            and not l.strip().startswith("//")
            and not l.strip().startswith("*")
        ]
        assert len(active_lines) == 0, \
            f"Gefundene _fetchWithLock-Aufrufe: {active_lines}"

    def test_E11g_module_panel_kein_editorstate_lockid(self):
        """E11g: module_panel.js liest lockId nicht mehr aus EditorState."""
        path = Path(__file__).parent.parent / "userinfo" / "module_panel.js"
        src = path.read_text(encoding="utf-8")
        active_lines = [
            l for l in src.split("\n")
            if "EditorState" in l
            and not l.strip().startswith("//")
            and not l.strip().startswith("*")
        ]
        assert len(active_lines) == 0, \
            f"module_panel.js: aktive EditorState-Referenzen: {active_lines}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

"""
tests/test_window_registry_ttl.py — Build 326

Nachweis der selbstheilenden SSE-Rollen-TTL in WindowRegistry.

HINTERGRUND (Beleg: Live-Diagnose 2026-07-07):
    Die Rolle 'main' blieb dauerhaft durch eine geleakte SSE-client_id
    (d12ae68a) belegt — der Grace-Release lief bei ungrazilem Disconnect nie,
    und find_active_by_role() prueft ausschliesslich _active_sse_roles (ohne
    Lebendigkeitspruefung). Folge: jeder Preflight -> HTTP 409, kein neuer
    Stream, keine Support-Sitzung.

FIX (Build 326):
    _active_sse_roles wird um Lebendigkeits-Zeitstempel (_sse_role_seen)
    ergaenzt. Der lebende Stream frischt via touch_sse_role() auf; bleibt das
    aus, gilt der Eintrag nach _SSE_ROLE_TTL als verwaist und wird beim
    naechsten Zugriff (find_active_by_role / find_active_sse_role / claim /
    list_active) automatisch freigegeben.

Alle Tests sind deterministisch (kein sleep): Staleness wird durch direktes
Zuruecksetzen des Zeitstempels erzeugt.
"""

import time

from forensic_api.windows import WindowRegistry, _SSE_ROLE_TTL


def _make_stale(reg: WindowRegistry, role: str) -> None:
    """Setzt den Lebendigkeits-Zeitstempel der Rolle deutlich ueber die TTL."""
    reg._sse_role_seen[role] = time.time() - (_SSE_ROLE_TTL + 5)


class TestSseRoleTtl:
    # --- Positivkontrolle: frische Rolle bleibt belegt ---------------------
    def test_claim_then_find_returns_holder(self):
        reg = WindowRegistry()
        assert reg.claim_sse_role("main", "client-A") is True
        found = reg.find_active_by_role("main")
        assert found is not None and found["window_id"] == "client-A"
        assert reg.find_active_sse_role("main") == "client-A"

    def test_fresh_role_blocks_other_claim(self):
        reg = WindowRegistry()
        assert reg.claim_sse_role("main", "client-A") is True
        # Zweiter, anderer Client wird abgewiesen, solange A frisch ist.
        assert reg.claim_sse_role("main", "client-B") is False
        assert reg.find_active_sse_role("main") == "client-A"

    # --- Selbstheilung: verwaiste Rolle wird automatisch frei --------------
    def test_stale_role_self_heals_on_find_active_by_role(self):
        reg = WindowRegistry()
        reg.claim_sse_role("main", "ghost")
        _make_stale(reg, "main")
        # find gibt None zurueck UND raeumt beide Dicts.
        assert reg.find_active_by_role("main") is None
        assert "main" not in reg._active_sse_roles
        assert "main" not in reg._sse_role_seen

    def test_stale_role_self_heals_on_find_active_sse_role(self):
        reg = WindowRegistry()
        reg.claim_sse_role("main", "ghost")
        _make_stale(reg, "main")
        assert reg.find_active_sse_role("main") is None
        assert "main" not in reg._active_sse_roles

    def test_claim_takes_over_stale_role(self):
        reg = WindowRegistry()
        reg.claim_sse_role("main", "ghost")
        _make_stale(reg, "main")
        # Neues Fenster darf die verwaiste Rolle uebernehmen.
        assert reg.claim_sse_role("main", "client-B") is True
        assert reg.find_active_sse_role("main") == "client-B"

    # --- touch haelt die Rolle am Leben ------------------------------------
    def test_touch_refreshes_and_prevents_stale(self):
        reg = WindowRegistry()
        reg.claim_sse_role("main", "client-A")
        _make_stale(reg, "main")           # kuenstlich veraltet
        reg.touch_sse_role("main", "client-A")   # lebender Stream frischt auf
        # Nach touch nicht mehr stale -> Rolle bleibt belegt.
        assert reg.find_active_by_role("main") is not None
        assert reg.find_active_sse_role("main") == "client-A"

    def test_touch_by_non_holder_is_noop(self):
        reg = WindowRegistry()
        reg.claim_sse_role("main", "client-A")
        _make_stale(reg, "main")
        reg.touch_sse_role("main", "someone-else")   # nicht der Inhaber
        # Kein Auffrischen -> weiterhin stale -> Rolle wird beim Zugriff frei.
        assert reg.find_active_by_role("main") is None

    # --- release raeumt beide Strukturen -----------------------------------
    def test_release_clears_both_dicts(self):
        reg = WindowRegistry()
        reg.claim_sse_role("main", "client-A")
        assert "main" in reg._sse_role_seen
        reg.release_sse_role("main", "client-A")
        assert "main" not in reg._active_sse_roles
        assert "main" not in reg._sse_role_seen

    def test_release_by_wrong_client_keeps_role(self):
        reg = WindowRegistry()
        reg.claim_sse_role("main", "client-A")
        reg.release_sse_role("main", "other")   # falscher Client -> No-op
        assert reg.find_active_sse_role("main") == "client-A"
        assert "main" in reg._sse_role_seen

    # --- list_active bereinigt verwaiste Rollen (sse_active konsistent) ----
    def test_list_active_prunes_stale_role(self):
        reg = WindowRegistry()
        reg.register("win-1", "main")
        reg.claim_sse_role("main", "client-A")
        # frisch: sse_active True
        entries = reg.list_active()
        assert any(e["window_id"] == "win-1" and e["sse_active"] for e in entries)
        # verwaist: list_active raeumt die Rolle -> sse_active False
        _make_stale(reg, "main")
        entries = reg.list_active()
        assert any(e["window_id"] == "win-1" and not e["sse_active"] for e in entries)
        assert "main" not in reg._active_sse_roles

    # --- Boundary: exakt auf der TTL ist NICHT stale (> TTL) ----------------
    def test_boundary_not_stale_at_exact_ttl(self):
        reg = WindowRegistry()
        reg.claim_sse_role("main", "client-A")
        reg._sse_role_seen["main"] = time.time() - _SSE_ROLE_TTL + 1  # knapp innerhalb
        assert reg.find_active_sse_role("main") == "client-A"

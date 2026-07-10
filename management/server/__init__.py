# =============================================================================
# management/server/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Eigenstaendiger Management-Server (Welle 0, Schritt 3). Read-only-first.
# Getrennt vom Forensik-Webserver (server/). Beleg: Bauplan B7 v1.1 §11.2.
#
# Build 346 liefert das BACKEND (Request-Dispatch, JSON-Endpunkte, SSE-Tick,
# Identitaets-/Policy-Aufloesung, Start-Checks) — vollstaendig pytest-testbar.
# Die gerenderte Cockpit-Oberflaeche (policy-getriebene Navigation) folgt in
# einem browser-verifizierbaren Build (Split analog Build 314/315).
#
# Version: v0.7.346 · Build: 346 · 2026-07-10
# =============================================================================

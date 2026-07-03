# =============================================================================
# management/dashboard/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Paket: Read-Model fuer das Ampel-Dashboard (Tag 3).
#   - dashboard_repo.py  : DashboardRepo (nur lesend), CaseOverview,
#                          AmpelThresholds, classify_ampel()
#   - dashboard_admin.py : Konsolen-Uebersicht (read-only)
#
# WICHTIG (Aufteilung Build 314/315): Dieses Paket ist der VOLLSTAENDIG
# automatisiert testbare BACKEND-Teil des Ampel-Dashboards. Der browser-
# basierte FRONTEND-Teil (Anzeige fuer die Chef-Ermittlerin) folgt als
# eigener Build, sobald er live im Browser abgenommen werden kann.
#
# Beleg: Bauplan B7 v0.9 Paragraph 9, Projektgespraech/mc 2026-07-02.
# Version: v0.7.315 · Build: 315 · 2026-07-03
# =============================================================================

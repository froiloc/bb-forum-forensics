# =============================================================================
# management/rbac/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# RBAC-Paket (Rollenbasierte Zugriffssteuerung fuer die Verwaltungsoberflaeche).
#
# Aufbau in drei Schnitten (Beleg: Bauplan_Baustelle7_Management_v1_1.md
# §11.1/§11.3/§11.7, Welle 0):
#   (a) Schema + Seed  — DIESER Build (343): Migration m006 legt die Matrix-
#       Tabellen an und seedet den Katalog (Rollen + Faehigkeiten). 'catalog.py'
#       ist die Wahrheitsquelle IM CODE; die Migration haelt einen EINGEFRORENEN
#       Seed (importiert 'catalog.py' bewusst NICHT — angewandte Migrationen
#       duerfen ihr Laufzeitverhalten nie aendern, m005-Prinzip).
#   (b) Schreibpfad + policy_admin-CLI (Katalog-Validierung) — Folge-Build.
#   (c) Lese-/Durchsetzungsschicht (Resolver, Start-Check 'Code-Capability
#       existiert in der DB') — Folge-Build.
#
# Version: v0.7.343 · Build: 343 · 2026-07-10
# =============================================================================

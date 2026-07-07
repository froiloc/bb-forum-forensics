# =============================================================================
# management/workload/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Paketmarker fuer die Ermittler-Lastverteilungs-Uebersicht (Build 335,
#   P2 Tag 7 Teil-Umfang). Reiner Lesezugriff auf coordinator.db; KEINE
#   Schemaaenderung, KEINE Migration.
#
#   Die Uebersicht ist die REVIEW-/VERTEILUNGS-Ebene ueber der bereits
#   vorhandenen, auditierten Einzelfall-Zuweisung (cases_repo.assign /
#   cases_admin --assign): sie zeigt der Chef-Ermittlerin je Ermittler die
#   getragene Last (nach Dringlichkeit/Status) und den unzugewiesenen
#   Rueckstau als Verteilungs-Pool. Sie rollt dazu die BELEGTE Fall-
#   Klassifikation aus dem Ampel-Dashboard (DashboardRepo) je Ermittler auf
#   — eine Wahrheitsquelle, keine Ampel-Drift.
#
# Version: v0.7.335 · Build: 335 · 2026-07-07
# =============================================================================

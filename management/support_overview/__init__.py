# =============================================================================
# management/support_overview/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Paketmarker fuer die dedizierte Support-Sitzungs-Uebersicht/-Historie
#   (Build 330). Reiner Lesezugriff auf coordinator.db; KEINE Schemaaenderung,
#   KEINE Migration, KEIN Anfassen von evidence_/forensic_/assets_-DB.
#
#   Das Modul rekonstruiert die permanente 'wer sah wann welchen Fall'-Historie
#   AUS dem hash-verketteten audit_log (SUPPORT_SESSION_STARTED/ENDED), NICHT
#   aus der fluechtigen (prunebaren) support_sessions-Praesenztabelle.
#
# Version: v0.7.330 · Build: 330 · 2026-07-07
# =============================================================================

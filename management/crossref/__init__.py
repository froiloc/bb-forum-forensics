# =============================================================================
# management/crossref/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Identitaet (AP-2A)
# =============================================================================
# Paket fuer den Kreuzbezugs-/Identitaets-Block (Ideen 6-11). Build 468 legt den
# ersten Baustein an: den globalen Katalog identifizierter Personen
# (identified_subject, Migration M018) samt auditiertem Repo.
#
# Spaetere Builds dieses Pakets (Reihenfolge s. Uebergabe AP-2A):
#   Alias-Katalog, Querfund-Erfassung/-Rueckkanal, Identitaets-Merge/Split,
#   jeweils Backend + Cockpit-Sicht. Sie setzen — wo vorhanden — auf die
#   bestehende forensic_api-Klempnerei auf (aliases.py, cross_annotation_
#   integrator.py) STATT zu duplizieren (belegte Reconciliation, mc 2026-07-20).
#
# Version: v0.7.468 · Build: 468 · 2026-07-20
# =============================================================================

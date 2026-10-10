# =============================================================================
# management/bildschleier/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Bildschleier (Build 771)
# =============================================================================
# Zweck:
#   Paket fuer den Bildschleier im Forenviewer: den Zustand je Person
#   (BildschleierZustand), das Lesen und auditierte Schreiben der Wahl
#   (BildschleierRepo). Die Regel, WELCHE Bilder verschleiert werden, liegt
#   nicht hier, sondern beim Webserver (core/bildschleier_regel.py, ab Build
#   772) — sie haengt an URLs und Konfiguration, nicht an coordinator.db.
#
#   Bauplan: management/Bauplan_Builds771-773_Bildschleier_v0_5.md
#
# Version: v0.8.771 · Build: 771 · 2026-10-09
# =============================================================================

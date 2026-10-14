# =============================================================================
# db/reparatur/reparatur_ziel_fehler.py
# IT-Forensisches Ermittlungswerkzeug — Ordner fuer beschaedigte Dateien
# =============================================================================
# Zweck:
#   Fehlerklasse von ReparaturZiel: Zielordner nicht ermittelbar oder nicht
#   zulaessig — erkannt VOR jedem Schreiben. Eigene Datei nach Grundregel 10
#   (Befund der unabhaengigen Durchsicht, Build 778); db/reparatur/
#   reparatur_ziel.py fuehrt den Namen weiter, bestehende Importe gelten.
#
# Version: v0.8.778 · Build: 778 · 2026-10-14
# =============================================================================

from __future__ import annotations


class ReparaturZielFehler(Exception):
    """Zielordner nicht ermittelbar oder nicht zulaessig — VOR jedem Schreiben."""

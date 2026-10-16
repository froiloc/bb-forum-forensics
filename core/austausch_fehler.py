# =============================================================================
# core/austausch_fehler.py
# IT-Forensisches Ermittlungswerkzeug — Startpruefung der evidence_<uid>.db
# =============================================================================
# Zweck:
#   Fehlerklasse von EvidenceAustausch (core/evidence_austausch.py). Eigene
#   Datei nach Grundregel 10 (Befund der unabhaengigen Durchsicht, Build 778).
#
#   ersetzt — True, wenn das Original zum Zeitpunkt des Fehlers BEREITS durch
#             die neue Datei ersetzt war (Kontrolle nach dem Ersetzen
#             gescheitert). Die Meldung an Register und Fehlerseite darf dann
#             nicht behaupten, die Datei sei unveraendert.
#
# Version: v0.8.778 · Build: 778 · 2026-10-14
# =============================================================================

from __future__ import annotations


class AustauschFehler(Exception):
    """Der Austausch wurde abgebrochen."""

    def __init__(self, meldung: str, *, ersetzt: bool = False) -> None:
        super().__init__(meldung)
        self.ersetzt = bool(ersetzt)

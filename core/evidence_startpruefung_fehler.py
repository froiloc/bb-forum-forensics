# =============================================================================
# core/evidence_startpruefung_fehler.py
# IT-Forensisches Ermittlungswerkzeug — Startpruefung der evidence_<uid>.db
# =============================================================================
# Zweck:
#   Die Startpruefung der evidence_<uid>.db verweigert den Start. Unterklasse
#   von StartupCheckError, damit main.py sie wie jede Startpruefung behandelt
#   (Meldung, Fehlerseite, sys.exit(1)) — sie traegt zusaetzlich die
#   Hilfeabsaetze fuer die Fehlerseite und den Ausgang der Meldung ins
#   Register.
#
# Version: v0.8.778 · Build: 778 · 2026-10-14
# =============================================================================

from __future__ import annotations

from typing import Any, List, Optional

from core.startup_checks import StartupCheckError


class EvidenceStartpruefungFehler(StartupCheckError):
    """Start verweigert durch die Startpruefung der evidence_<uid>.db."""

    def __init__(self, meldung: str, *, hilfe: Optional[List[str]] = None,
                 melde_ergebnis: Optional[Any] = None) -> None:
        super().__init__(meldung)
        self.hilfe = list(hilfe or [])
        self.melde_ergebnis = melde_ergebnis

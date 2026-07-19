# =============================================================================
# maintenance/errors.py
# IT-Forensisches Ermittlungswerkzeug — Wartungsmodus (Build 435, Fundament)
# =============================================================================
# Zweck:
#   Gemeinsame Ausnahme des Wartungs-Dateiprotokolls.
#
# Intention:
#   Eine defekte oder unvollstaendige Steuerdatei (window.json, presence, ack,
#   servers) darf NIE still verschluckt werden (Grundregel 1). Statt None oder
#   einer stillen Annahme wird eine sprechende Ausnahme geworfen, die der
#   Aufrufer laut protokollieren kann.
#
# Version: v0.7.435 · Build: 435 · 2026-07-19
# =============================================================================

from __future__ import annotations


class MaintenanceProtocolError(RuntimeError):
    """
    Eine Steuerdatei des Wartungsmodus ist vorhanden, aber nicht interpretierbar
    (kaputtes JSON, kein Objekt, fehlendes Pflichtfeld, ungueltiger Wert).

    Bewusst KEINE Rueckgabe von None in diesen Faellen: Ein leeres/None-Ergebnis
    bedeutet an anderer Stelle 'nicht vorhanden'. Eine BESCHAEDIGTE Datei ist
    aber ein anderer, meldepflichtiger Zustand.
    """

# =============================================================================
# management/capacity/capacity_errors.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kapazitaet (Welle 0)
# =============================================================================
# Gemeinsame Ausnahme der Kapazitaets-Schreibpfade. Klarer Fehler statt stillem
# No-op (Grundregel 1) — z.B. bei ungueltigen Werten oder beim Entfernen einer
# nicht (mehr) vorhandenen Zeile.
# Version: v0.7.356 · Build: 356 · 2026-07-10
# =============================================================================


class CapacityError(Exception):
    """Ungueltige Kapazitaets-Operation (Validierung / nicht vorhanden)."""

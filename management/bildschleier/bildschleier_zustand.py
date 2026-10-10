# =============================================================================
# management/bildschleier/bildschleier_zustand.py
# IT-Forensisches Ermittlungswerkzeug — Bildschleier (Build 771)
# =============================================================================
# Zweck:
#   Der Zustand des Bildschleiers fuer EINE Person zu EINEM Zeitpunkt:
#     veiled  — wirkt der Schleier?
#     locked  — ist die Schaltflaeche gesperrt?
#     reason  — WARUM ist es so (maschinenlesbar, englisch: externe
#               Schnittstelle, JSON-Schluessel und -Werte englisch)
#
# ── DIE GRUENDE UND IHRE RICHTUNG ───────────────────────────────────────────
#
#   Jeder Grund, der NICHT aus einer bewussten Wahl einer berechtigten Person
#   stammt, endet VERSCHLEIERT UND GESPERRT. Das ist die sichere Richtung des
#   Selbstschutzes (Bauplan §4.1): ein Fehler darf nie dazu fuehren, dass ein
#   Bild unverschleiert erscheint, das verschleiert sein sollte.
#
#   Der Grund wird nicht verschluckt: er steht im Log und im Tooltip der
#   Schaltflaeche (Grundregel 1). Fuer jeden Grund gibt es deshalb hier GENAU
#   EINEN Tooltip-Text — die Oberflaeche erfindet keinen eigenen.
#
# Version: v0.8.771 · Build: 771 · 2026-10-09
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

# --- Gruende ----------------------------------------------------------------
#: Person traegt die Rolle 'researcher'. Hat VORRANG vor dem Recht (Kopf von
#: management/rbac/catalog.py, Rolle 'researcher').
GRUND_ROLLE = "required_by_role"
#: Recht 'imageveil.lift' nicht zugeteilt (auch: unmittelbar nach M040, vor
#: der Vergabe im Wartungsfenster).
GRUND_RECHT_FEHLT = "no_capability"
#: Der Systembenutzer ist nicht als Person in coordinator.db hinterlegt.
GRUND_KEINE_PERSON = "no_investigator"
#: Die Rechteverwaltung ist nicht lesbar (coordinator.db fehlt/gesperrt).
GRUND_RBAC_FEHLT = "rbac_unavailable"
#: Das Recht ist da, aber die gespeicherte Wahl ist nicht lesbar (z. B. M040
#: noch nicht angewandt).
GRUND_SPEICHER_FEHLT = "store_unavailable"
#: Unerwarteter Fehler im Programm — eigener Grund, damit ein
#: Programmierfehler nicht als Betriebsstoerung erscheint (Lehre Build 769:
#: ein pauschaler Fehlerabfang verschluckte einen Programmierfehler).
GRUND_INTERN = "internal_error"
#: Berechtigte Person, gespeicherte Wahl.
GRUND_GEWAEHLT = "chosen"
#: Berechtigte Person, nie umgeschaltet: Voreinstellung KLAR (Alex,
#: 09.10.2026).
GRUND_VORGABE = "default"

#: Gruende, die eine gesperrte Schaltflaeche bedeuten.
GESPERRTE_GRUENDE = frozenset({
    GRUND_ROLLE, GRUND_RECHT_FEHLT, GRUND_KEINE_PERSON, GRUND_RBAC_FEHLT,
    GRUND_SPEICHER_FEHLT, GRUND_INTERN,
})
#: Alle Gruende — fuer Tests und die Pruefung der Tooltip-Texte.
ALLE_GRUENDE = GESPERRTE_GRUENDE | {GRUND_GEWAEHLT, GRUND_VORGABE}

# --- Tooltip-Texte (Endnutzer, Deutsch) -------------------------------------
#   Bauplan §5.5. Ein Text je Grund; fuer die beiden freien Gruende haengt er
#   zusaetzlich am Zustand (verschleiert/klar), weil der Tooltip dann sagt,
#   was ein Klick bewirkt.
_TEXTE_GESPERRT = {
    GRUND_ROLLE:
        "Für Ihre Rolle ist die Bildverschleierung vorgeschrieben.",
    GRUND_RECHT_FEHLT:
        "Das Recht ‚Bildschleier aufheben‘ ist Ihnen nicht zugeteilt. "
        "Bitte an die Chef-Ermittlerin wenden.",
    GRUND_KEINE_PERSON:
        "Ihr Benutzerkonto ist nicht als Person hinterlegt. "
        "Bilder bleiben verschleiert.",
    GRUND_RBAC_FEHLT:
        "Die Rechteverwaltung ist nicht erreichbar. "
        "Bilder bleiben verschleiert.",
    GRUND_SPEICHER_FEHLT:
        "Ihre gespeicherte Einstellung ist nicht lesbar. "
        "Bilder bleiben verschleiert.",
    GRUND_INTERN:
        "Interner Fehler beim Ermitteln der Einstellung (siehe Serverprotokoll). "
        "Bilder bleiben verschleiert.",
}
_TEXT_FREI_VERSCHLEIERT = "Bilder sind verschleiert. Klicken zum Aufheben."
_TEXT_FREI_KLAR = "Bilder werden unverschleiert gezeigt. Klicken zum Verschleiern."


@dataclass(frozen=True)
class BildschleierZustand:
    """Unveraenderlicher Zustand des Bildschleiers fuer eine Person."""

    veiled: bool
    locked: bool
    reason: str

    def __post_init__(self) -> None:
        # Die Invariante wird HIER durchgesetzt und nicht beim Aufrufer:
        # ein gesperrter Grund ohne Schleier waere genau der Fehler, gegen den
        # das ganze Merkmal gebaut ist.
        if self.reason not in ALLE_GRUENDE:
            raise ValueError("Unbekannter Bildschleier-Grund: %r" % self.reason)
        if self.reason in GESPERRTE_GRUENDE and not (self.veiled and self.locked):
            raise ValueError(
                "Grund %r verlangt veiled=True und locked=True "
                "(erhalten: veiled=%r, locked=%r)."
                % (self.reason, self.veiled, self.locked))
        if self.reason not in GESPERRTE_GRUENDE and self.locked:
            raise ValueError(
                "Grund %r ist ein freier Grund und darf nicht gesperrt sein."
                % self.reason)

    @classmethod
    def gesperrt(cls, reason: str) -> "BildschleierZustand":
        """Verschleiert und gesperrt — fuer jeden nicht freien Grund."""
        return cls(veiled=True, locked=True, reason=reason)

    @property
    def tooltip(self) -> str:
        if self.locked:
            return _TEXTE_GESPERRT[self.reason]
        return _TEXT_FREI_VERSCHLEIERT if self.veiled else _TEXT_FREI_KLAR

    def to_dict(self) -> Dict[str, Any]:
        """JSON-Form fuer Endpunkt und Shell (englische Schluessel)."""
        return {
            "veiled": self.veiled,
            "locked": self.locked,
            "reason": self.reason,
            "tooltip": self.tooltip,
        }

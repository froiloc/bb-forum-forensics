# =============================================================================
# management/mentoring_notes/note_colors.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Das FARBVOKABULAR der Betreuungs-Notizen (Build 401). Bewusst im CODE
#   gehalten (nicht als DB-CHECK), damit die Palette spaeter ADDITIV erweiterbar
#   bleibt — genau wie matter_kinds.py fuer die Vorgangsarten. Ein Tabellen-
#   Rebuild an produktiven Daten waere so nie noetig.
#
#   Das Backend validiert AUSSCHLIESSLICH den stabilen Code (z. B. 'gelb').
#   Die konkrete Darstellung (Hex-Ton, Kontrast) ist Sache des Frontends
#   (cockpit_notes.css) — die Trennung haelt die Datenhaltung UI-unabhaengig.
#
#   Grundregel 10 (jede Klasse/Zustaendigkeit in eine eigene Datei): das
#   Farbvokabular ist eine eigenstaendige Zustaendigkeit und liegt hier.
#
# Version: v0.7.401 · Build: 401 · 2026-07-13
# =============================================================================

from typing import Dict, FrozenSet, List, Tuple

#: Standardfarbe, wenn keine gewaehlt wird (klassisches Post-it-Gelb).
DEFAULT_COLOR: str = "gelb"

# -----------------------------------------------------------------------------
# Palette als (code, label)-Paare. Die REIHENFOLGE bestimmt die Anzeige-Folge
# der Farbwahl im Frontend. Codes sind STABIL und werden NIE umbenannt/entfernt
# (nur additiv erweitert) — sonst wuerden bestehende Notizen ihre Farbe
# verlieren. Bewusst knapp/deutsch, konsistent zum uebrigen Vokabular.
# -----------------------------------------------------------------------------
_PALETTE: Tuple[Tuple[str, str], ...] = (
    ("gelb", "Gelb"),
    ("rosa", "Rosa"),
    ("gruen", "Gruen"),
    ("blau", "Blau"),
    ("orange", "Orange"),
    ("lila", "Lila"),
    ("grau", "Grau"),
)

#: Nur die Codes — fuer schnelle Konsistenz-/Gueltigkeitspruefungen.
COLOR_CODES: FrozenSet[str] = frozenset(code for code, _label in _PALETTE)

#: Reihenfolge der Codes (fuer determinierte Ausgaben/Tests).
COLOR_ORDER: Tuple[str, ...] = tuple(code for code, _label in _PALETTE)

#: code -> label (Anzeigename), fuer Kataloge.
_LABELS: Dict[str, str] = {code: label for code, label in _PALETTE}


def is_valid(color: str) -> bool:
    """True, wenn 'color' ein bekannter Farbcode ist."""
    return color in COLOR_CODES


def label(color: str) -> str:
    """Anzeigename zu einem Farbcode (oder der Code selbst, falls unbekannt)."""
    return _LABELS.get(color, color)


def catalog() -> List[Dict[str, str]]:
    """
    Der Farb-Katalog als DATEN (kein Code) fuer die UI:
    [{'code': 'gelb', 'label': 'Gelb'}, ...] in Anzeige-Reihenfolge.
    """
    return [{"code": code, "label": lbl} for code, lbl in _PALETTE]

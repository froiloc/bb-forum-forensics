# =============================================================================
# management/external/matter_kinds.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   EINGEFRORENES Vokabular der Vorgangsarten externer Vorgaenge. Die Werte
#   stehen dauerhaft in coordinator.db und spaeter in Berichten und StA-Exporten
#   — ein Wert bedeutet in zehn Jahren noch genau das, was er heute bedeutet.
#
#   Daher: ERWEITERN ist erlaubt (additiv), UMBENENNEN und ENTFERNEN nicht.
#   Gleiche Regel wie EventType.ALL und CaseEvents.EVENT_KINDS.
#
#   Die Validierung liegt bewusst HIER (im Code) und nicht als CHECK-Constraint
#   in der DDL: eine neue Vorgangsart soll ein Einzeiler sein und kein
#   Tabellen-Rebuild an produktiven Ermittlungsdaten.
#
#   Katalog (mc 2026-07-12; 'osint' und 'auswertung' auf Wunsch ergaenzt):
#     bestandsdaten  — Bestandsdatenauskunft (Provider: wer steckt hinter der Kennung)
#     verkehrsdaten  — Verkehrsdatenauskunft (Provider: Verbindungsdaten)
#     beschluss      — Beschluss bei StA / Ermittlungsrichter
#     durchsuchung   — Durchsuchung / Beschlagnahme
#     rechtshilfe    — Rechtshilfeersuchen (Ausland)
#     amtshilfe      — Amtshilfe (LKA, BKA, andere Behoerde)
#     bankauskunft   — Kontenabruf / Bankauskunft
#     gutachten      — Sachverstaendigengutachten
#     osint          — offene Quellen (Recherche-Auftrag)
#     auswertung     — technische Auswertung (Asservat, Datentraeger)
#     sonstiges      — alles Uebrige (Freitext im Betreff)
#
# Version: v0.7.385 · Build: 385 · 2026-07-12
# =============================================================================

from typing import Dict, FrozenSet, Tuple

#: Reihenfolge fuer Auswahllisten (fachlich gruppiert, nicht alphabetisch).
KIND_ORDER: Tuple[str, ...] = (
    "bestandsdaten",
    "verkehrsdaten",
    "beschluss",
    "durchsuchung",
    "rechtshilfe",
    "amtshilfe",
    "bankauskunft",
    "gutachten",
    "osint",
    "auswertung",
    "sonstiges",
)

#: Klartext fuer Oberflaeche, CLI und Bericht.
KIND_LABEL: Dict[str, str] = {
    "bestandsdaten": "Bestandsdatenauskunft",
    "verkehrsdaten": "Verkehrsdatenauskunft",
    "beschluss": "Beschluss (StA / Ermittlungsrichter)",
    "durchsuchung": "Durchsuchung / Beschlagnahme",
    "rechtshilfe": "Rechtshilfeersuchen",
    "amtshilfe": "Amtshilfe (LKA / BKA / andere Behoerde)",
    "bankauskunft": "Kontenabruf / Bankauskunft",
    "gutachten": "Sachverstaendigengutachten",
    "osint": "OSINT / offene Quellen",
    "auswertung": "Technische Auswertung (Asservat)",
    "sonstiges": "Sonstiges",
}

#: Menge der gueltigen Werte (Validierung im Repo).
KINDS: FrozenSet[str] = frozenset(KIND_ORDER)


def is_valid(kind: str) -> bool:
    """True, wenn 'kind' eine bekannte Vorgangsart ist."""
    return kind in KINDS


def label(kind: str) -> str:
    """Klartext zur Vorgangsart; unbekannte Werte werden NICHT verschluckt."""
    return KIND_LABEL.get(kind, kind)


def catalog() -> Tuple[Dict[str, str], ...]:
    """Katalog fuer Oberflaeche/CLI: (code, label) in fachlicher Reihenfolge."""
    return tuple({"code": k, "label": KIND_LABEL[k]} for k in KIND_ORDER)

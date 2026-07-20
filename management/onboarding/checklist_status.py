# =============================================================================
# management/onboarding/checklist_status.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Onboarding/Offboarding (AP-2G)
# =============================================================================
# Zweck (Idee 31):
#   Das VOKABULAR der Onboarding-/Offboarding-Schritte und die ZUSTANDSLOGIK je
#   Schritt — reine Logik, keine DB, keine Uhr. Vollstaendig in pytest pruefbar.
#
#   Es gibt ZWEI Checklisten-ARTEN mit je einem FESTEN, GEORDNETEN Schritt-
#   Katalog. Das Vokabular liegt IM CODE (nicht in der DDL): Erweitern ist additiv
#   und ein Einzeiler, kein Tabellen-Rebuild an produktiven Daten (gleiche Linie
#   wie matter_kinds/EventType). ENTFERNEN/UMBENENNEN von Schritt-Codes ist nicht
#   zulaessig — ein Code bedeutet in Jahren noch genau dasselbe.
#
# ZUSTAND JE SCHRITT (mc-Freigabe 2026-07-20):
#   'offen'           — implizit; NICHT gespeichert (Abwesenheit einer Zeile).
#   'erledigt'        — der Schritt ist getan.
#   'nicht_zutreffend'— der Schritt entfaellt begruendet.
#
#   Uebergaenge sind FREI unter den drei Zustaenden (eine Checkliste ist ein
#   operatives Arbeitsmittel; eine Fehleingabe muss KORRIGIERBAR sein) — aber
#   JEDE Aenderung wird auditiert. GRUND (Notiz) ist PFLICHT bei
#   'nicht_zutreffend': ein STILL uebersprungener Schritt waere genau die Luecke,
#   die die Checkliste schliessen soll (Grundregel 1). 'erledigt'/'offen'
#   verlangen keinen Grund.
#
# Version: v0.7.464 · Build: 464 · 2026-07-20
# =============================================================================

from typing import Dict, FrozenSet, Optional, Tuple

#: Checklisten-Arten.
KIND_ONBOARDING = "onboarding"
KIND_OFFBOARDING = "offboarding"
KINDS: Tuple[str, ...] = (KIND_ONBOARDING, KIND_OFFBOARDING)

KIND_LABEL: Dict[str, str] = {
    KIND_ONBOARDING: "Onboarding (Aufnahme in die EK)",
    KIND_OFFBOARDING: "Offboarding (Ausscheiden aus der EK)",
}

#: Feste, GEORDNETE Schritt-Kataloge je Art: (code, label). Reihenfolge = Anzeige.
STEPS: Dict[str, Tuple[Tuple[str, str], ...]] = {
    KIND_ONBOARDING: (
        ("person_angelegt", "Personendatensatz angelegt (SAMAccountName)"),
        ("ad_gruppe_geprueft", "AD-Gruppenmitgliedschaft (EK) geprueft"),
        ("rolle_zugewiesen", "Rolle(n) zugewiesen (RBAC)"),
        ("einweisung", "Einweisung/Schulung Werkzeug erfolgt"),
        ("zugang_bestaetigt", "Zugang zum System bestaetigt"),
    ),
    KIND_OFFBOARDING: (
        ("rollen_entzogen", "Rollen/Rechte entzogen (RBAC)"),
        ("faelle_umverteilt", "Offene Faelle umverteilt (Uebergabe-Protokoll)"),
        ("zugang_gesperrt", "Systemzugang gesperrt"),
        ("ad_gruppe_entfernt", "AD-Gruppenmitgliedschaft (EK) entfernt"),
        ("uebergabe_notizen", "Betreuungs-/Arbeitsnotizen uebergeben"),
    ),
}

#: Implizite Eingangslage — NIE gespeichert.
INITIAL: str = "offen"

#: Gespeicherte Zustaende — deckungsgleich mit dem CHECK in M017.
STORED_STATUSES: Tuple[str, ...] = ("erledigt", "nicht_zutreffend")

#: Alle benennbaren Zustaende (inkl. der impliziten Eingangslage).
STATUS_ORDER: Tuple[str, ...] = ("offen", "erledigt", "nicht_zutreffend")

STATUS_LABEL: Dict[str, str] = {
    "offen": "offen",
    "erledigt": "erledigt",
    "nicht_zutreffend": "nicht zutreffend",
}

#: Zustaende, die einen Grund (Notiz) verlangen.
REASON_REQUIRED: Tuple[str, ...] = ("nicht_zutreffend",)

_ALL_STATES: FrozenSet[str] = frozenset(STATUS_ORDER)


class ChecklistStatusError(Exception):
    """Unbekannte Art/Schritt/Zustand oder fehlender Pflicht-Grund."""


class ChecklistStatus:
    """Vokabular + Zustandslogik der Checklisten (reine Logik)."""

    # ------------------------------------------------------------------ Arten
    @staticmethod
    def is_valid_kind(kind: str) -> bool:
        return kind in KINDS

    @staticmethod
    def kind_label(kind: str) -> str:
        return KIND_LABEL.get(kind, kind)

    @staticmethod
    def require_kind(kind: str) -> None:
        if kind not in KINDS:
            raise ChecklistStatusError(
                "Unbekannte Checklisten-Art '%s' (gueltig: %s)."
                % (kind, ", ".join(KINDS)))

    # --------------------------------------------------------------- Schritte
    @classmethod
    def steps(cls, kind: str) -> Tuple[Tuple[str, str], ...]:
        cls.require_kind(kind)
        return STEPS[kind]

    @classmethod
    def step_codes(cls, kind: str) -> Tuple[str, ...]:
        return tuple(code for code, _l in cls.steps(kind))

    @classmethod
    def is_valid_step(cls, kind: str, step_code: str) -> bool:
        return kind in KINDS and step_code in dict(STEPS[kind])

    @classmethod
    def step_label(cls, kind: str, step_code: str) -> str:
        return dict(STEPS.get(kind, ())).get(step_code, step_code)

    @classmethod
    def require_step(cls, kind: str, step_code: str) -> None:
        cls.require_kind(kind)
        if step_code not in dict(STEPS[kind]):
            raise ChecklistStatusError(
                "Unbekannter Schritt '%s' fuer '%s' (gueltig: %s)."
                % (step_code, kind, ", ".join(cls.step_codes(kind))))

    # --------------------------------------------------------------- Zustaende
    @staticmethod
    def is_stored(status: str) -> bool:
        """True, wenn 'status' gespeichert wird (nicht die Eingangslage 'offen')."""
        return status in STORED_STATUSES

    @staticmethod
    def is_known(status: str) -> bool:
        return status in _ALL_STATES

    @staticmethod
    def label(status: str) -> str:
        return STATUS_LABEL.get(status, status)

    @staticmethod
    def requires_reason(status: str) -> bool:
        return status in REASON_REQUIRED

    @classmethod
    def require_status(cls, status: str) -> None:
        """Ein Zielzustand MUSS bekannt sein ('offen' ist als RESET zulaessig)."""
        if status not in _ALL_STATES:
            raise ChecklistStatusError(
                "Unbekannter Zustand '%s' (gueltig: %s)."
                % (status, ", ".join(STATUS_ORDER)))

    @classmethod
    def check_reason(cls, status: str, note: Optional[str]) -> None:
        """Grund-Pflicht durchsetzen (nur 'nicht_zutreffend')."""
        if cls.requires_reason(status) and not (note or "").strip():
            raise ChecklistStatusError(
                "Grund ist Pflicht: der Schritt darf nicht ohne "
                "nachvollziehbaren Grund auf '%s' gesetzt werden." % status)

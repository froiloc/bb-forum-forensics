# =============================================================================
# management/ops/promotion_status.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Betrieb/Governance (AP-2G)
# =============================================================================
# Zweck (Idee 25, Fundament F3 "Fremdforum-Promotion"):
#   Die ZUSTANDSMASCHINE der Fremdforum-Promotion — als REINE Logik, ohne
#   Datenbank, ohne Uhr. Damit vollstaendig in pytest pruefbar.
#
#   Ein FREMDFORUM-KANDIDAT ist ein Fall, dessen forensic_<uid>.db der Prepper
#   geliefert hat, fuer den aber (noch) KEINE evidence_<uid>.db existiert — d.h.
#   der Fall EXISTIERT, hat aber noch KEINEN Arbeitsstand (Beleg:
#   storage_overview.py:9-13,155-163; case_detector.py: forensic = Existenz-
#   kriterium, evidence = Arbeitsstand). Solche Kandidaten muessen eine
#   bewusste, BELEGTE Entscheidung durchlaufen — sonst bliebe die Entscheidung
#   implizit, und genau das verbietet Grundregel 1 ("kein Beleg still
#   uebersprungen").
#
# STATUSMODELL (vorgeschlagen mc-Freigabe 2026-07-20 "wie vorgeschlagen"):
#
#   (kein Eintrag = implizit 'offen'/unentschieden)
#        │  erste Entscheidung
#        ▼
#   gesichtet ──(uebernehmen)─────────► uebernommen        ✔ endgueltig
#        │                              (Fall wird via CaseImporter aktiv)
#        ├──(zurueckstellen + GRUND)──► zurueckgestellt
#        │                                   │
#        │      (wieder aufgreifen) ◄────────┘   (reversibel — Zurueckstellung
#        │                                        ist KEIN forensischer Abschluss)
#        └──(fremdzustaendig + GRUND)─► fremdzustaendig     ✔ endgueltig
#
#   - 'offen' ist ein PSEUDO-Zustand: er wird NIE gespeichert (die Abwesenheit
#     einer Zeile IST 'offen'). Erst die erste Entscheidung materialisiert eine
#     Zeile mit einem der vier gespeicherten Zustaende (deckt sich mit dem CHECK
#     in M015).
#   - 'uebernommen' und 'fremdzustaendig' sind ENDGUELTIG (✔). Kein Weg zurueck.
#     Ein Irrtum wird durch eine NEUE, belegte Entscheidung an einem NEU
#     erkannten Kandidaten korrigiert — nicht durch Zurueckdrehen (gleiche Linie
#     wie MatterStatus/Build 385 und das Berichts-Statusmodell/Build 377).
#   - 'zurueckgestellt' -> 'gesichtet' ist ERLAUBT (Wiederaufgriff): eine
#     Zurueckstellung ist eine operative Pause, kein Ergebnis.
#   - GRUND ist PFLICHT bei 'zurueckgestellt' und 'fremdzustaendig'. Ein stilles
#     Zurueckstellen/Aussortieren waere genau die Luecke, die dieses System
#     schliessen soll (Grundregel 1).
#
# VOKABULAR IM CODE, nicht in der DDL (fuer die Uebergaenge/Labels): wie bei
#   matter_status/matter_kinds. AUSNAHME: 'status' bekommt in M015 dennoch einen
#   CHECK, weil die Zustandsmenge abgeschlossen ist und ein Tippfehler dort eine
#   Zeile aus jedem Filter fallen liesse (stiller Beweisverlust).
#
# Version: v0.7.460 · Build: 460 · 2026-07-20
# =============================================================================

from typing import Dict, FrozenSet, Tuple

#: Implizite Eingangslage — NIE gespeichert (Abwesenheit einer Zeile).
INITIAL: str = "offen"

#: Gespeicherte Zustaende — deckungsgleich mit dem CHECK in M015.
STORED_STATUSES: Tuple[str, ...] = (
    "gesichtet",
    "uebernommen",
    "zurueckgestellt",
    "fremdzustaendig",
)

#: Endzustaende — unwiderruflich.
FINAL_STATUSES: Tuple[str, ...] = ("uebernommen", "fremdzustaendig")

#: Zielzustaende, die einen GRUND verlangen.
REASON_REQUIRED: Tuple[str, ...] = ("zurueckgestellt", "fremdzustaendig")

#: Reihenfolge fuer Filter/Anzeige: das Handlungsbeduerftige zuerst.
STATUS_ORDER: Tuple[str, ...] = (
    "offen",
    "gesichtet",
    "zurueckgestellt",
    "uebernommen",
    "fremdzustaendig",
)

STATUS_LABEL: Dict[str, str] = {
    "offen": "offen (unentschieden)",
    "gesichtet": "gesichtet (Entscheidung ausstehend)",
    "uebernommen": "in Ermittlung uebernommen",
    "zurueckgestellt": "zurueckgestellt",
    "fremdzustaendig": "fremdzustaendig (nicht unsere Zustaendigkeit)",
}

#: Erlaubte Uebergaenge (exakt das vereinbarte Modell). 'offen' ist die
#: implizite Eingangslage und darf in jeden gespeicherten Zustand uebergehen.
#: Endzustaende haben KEINE ausgehende Kante.
ALLOWED_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "offen": ("gesichtet", "uebernommen", "zurueckgestellt", "fremdzustaendig"),
    "gesichtet": ("uebernommen", "zurueckgestellt", "fremdzustaendig"),
    "zurueckgestellt": ("gesichtet", "uebernommen", "fremdzustaendig"),
    "uebernommen": (),
    "fremdzustaendig": (),
}

#: Alle in einem Uebergang benennbaren Quell-/Zielzustaende (inkl. 'offen').
_ALL_STATES: FrozenSet[str] = frozenset(ALLOWED_TRANSITIONS.keys())


class PromotionStatusError(Exception):
    """Unzulaessiger Zustandsuebergang, unbekannter Zustand oder fehlender Grund."""


class PromotionStatus:
    """Zustandsmaschine der Fremdforum-Promotion (reine Logik)."""

    # ------------------------------------------------------------ Zustaende
    @staticmethod
    def is_stored(status: str) -> bool:
        """True, wenn 'status' ein SPEICHERBARER Zustand ist (nicht 'offen')."""
        return status in STORED_STATUSES

    @staticmethod
    def is_known(status: str) -> bool:
        """True fuer jeden benennbaren Zustand inkl. der Eingangslage 'offen'."""
        return status in _ALL_STATES

    @staticmethod
    def is_final(status: str) -> bool:
        return status in FINAL_STATUSES

    @staticmethod
    def requires_reason(target: str) -> bool:
        """True, wenn der Zielzustand einen Pflicht-Grund verlangt."""
        return target in REASON_REQUIRED

    @staticmethod
    def label(status: str) -> str:
        return STATUS_LABEL.get(status, status)

    @staticmethod
    def allowed_next(status: str) -> Tuple[str, ...]:
        """Zulaessige Folgezustaende. Unbekannter Zustand -> Fehler, nie ()."""
        if status not in ALLOWED_TRANSITIONS:
            raise PromotionStatusError(
                "Unbekannter Zustand '%s' (gueltig: %s)."
                % (status, ", ".join(STATUS_ORDER)))
        return ALLOWED_TRANSITIONS[status]

    @classmethod
    def check_transition(cls, current: str, target: str) -> None:
        """
        Prueft den Uebergang current -> target. Verstoss -> PromotionStatusError.
        'current' darf die implizite Eingangslage 'offen' sein (noch keine
        Zeile). 'target' MUSS ein gespeicherter Zustand sein — 'offen' ist kein
        gueltiges ZIEL (man kehrt nicht in die Unentschiedenheit zurueck; das
        waere ein stilles Verwerfen der bisherigen Entscheidung).
        """
        if target not in STORED_STATUSES:
            raise PromotionStatusError(
                "Unbekannter/ungueltiger Zielzustand '%s' (gueltig: %s)."
                % (target, ", ".join(STORED_STATUSES)))
        allowed = cls.allowed_next(current)
        if target in allowed:
            return
        if cls.is_final(current):
            raise PromotionStatusError(
                "Kandidat ist mit '%s' ENDGUELTIG entschieden und kann nicht "
                "nach '%s' gefuehrt werden. Ein Irrtum wird durch eine NEUE, "
                "belegte Entscheidung korrigiert, nicht durch Zurueckdrehen."
                % (current, target))
        raise PromotionStatusError(
            "Uebergang '%s' -> '%s' ist nicht vorgesehen (zulaessig: %s)."
            % (current, target, ", ".join(allowed) or "keiner"))

    @classmethod
    def check_reason(cls, target: str, grund: str) -> None:
        """Grund-Pflicht durchsetzen. Fehlt der Grund -> PromotionStatusError."""
        if cls.requires_reason(target) and not (grund or "").strip():
            raise PromotionStatusError(
                "Grund ist Pflicht: der Uebergang nach '%s' darf nicht ohne "
                "nachvollziehbaren Grund erfolgen." % target)

    @staticmethod
    def rank(status: str) -> int:
        """Sortierrang fuer Anzeige: Unentschiedenes/Offenes zuerst."""
        return {
            "offen": 0,
            "gesichtet": 1,
            "zurueckgestellt": 2,
            "uebernommen": 3,
            "fremdzustaendig": 4,
        }.get(status, 9)

# =============================================================================
# management/external/matter_status.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Die ZUSTANDSMASCHINE der externen Vorgaenge und die WIEDERVORLAGE-AMPEL —
#   als REINE Logik, ohne Datenbank, ohne Uhr. Beides ist damit vollstaendig in
#   pytest pruefbar (der Stichtag wird UEBERGEBEN, nicht aus der Systemuhr
#   gelesen — sonst haetten wir Tests, die abhaengig vom Testtag kippen).
#
# STATUSMODELL (verbindlich, mc 2026-07-12):
#
#        ┌──── Wiedervorlage verschoben (neues Datum + GRUND) ────┐
#        ▼                                                        │
#   offen ──(Antwort eingegangen)──► beantwortet ──(ausgewertet)──► erledigt ✔
#     │                                   │
#     └────(ohne Ergebnis)────────────────┴──────────────────────► erfolglos ✔
#
#   - 'erledigt' und 'erfolglos' sind ENDGUELTIG (✔). Es gibt keinen Weg zurueck.
#     Ein Irrtum wird durch einen NEUEN Vorgang korrigiert, nicht durch
#     Zurueckdrehen — die Historie eines Ermittlungsvorgangs wird nicht
#     umgeschrieben (gleiche Linie wie das Berichts-Statusmodell, Build 377).
#   - Verschieben (defer) ist nur in den OFFENEN Zustaenden moeglich und
#     verlangt einen GRUND. Ein stilles Verschieben waere genau die Luecke,
#     die die Wiedervorlage verhindern soll (Grundregel 1).
#
# AMPEL (nur fuer offene Zustaende; abgeschlossene Vorgaenge sind 'neutral'):
#   rot    wiedervorlage_am <= Stichtag                      (faellig/ueberfaellig)
#   gelb   Stichtag < wiedervorlage_am <= Stichtag + Vorwarnfrist
#   gruen  sonst
#
#   SONDERFALL 'verwaist' (mc 2026-07-12): Ist der FALL bereits geschlossen
#   ('approved'/'closed'), der Vorgang aber noch offen, ist das IMMER ROT —
#   unabhaengig vom Datum. Es wird NICHTS automatisch geschlossen (kein stiller
#   Eingriff in Ermittlungsdaten); ein Mensch muss entscheiden.
#
# Version: v0.7.385 · Build: 385 · 2026-07-12
# =============================================================================

from datetime import date, timedelta
from typing import Dict, FrozenSet, Optional, Tuple

#: Standard-Vorwarnfrist in Kalendertagen (je Vorgang ueberschreibbar, mc).
DEFAULT_VORWARNFRIST_TAGE: int = 7

#: Offene Zustaende — nur hier ist der Vorgang "im Wartestand".
OPEN_STATUSES: Tuple[str, ...] = ("offen", "beantwortet")

#: Endzustaende — unwiderruflich.
FINAL_STATUSES: Tuple[str, ...] = ("erledigt", "erfolglos")

#: Reihenfolge fuer Filter/Anzeige: das Handlungsbeduerftige zuerst.
STATUS_ORDER: Tuple[str, ...] = ("offen", "beantwortet", "erledigt", "erfolglos")

STATUS_LABEL: Dict[str, str] = {
    "offen": "offen (Antwort steht aus)",
    "beantwortet": "beantwortet (Auswertung steht aus)",
    "erledigt": "erledigt",
    "erfolglos": "ohne Ergebnis abgeschlossen",
}

#: Erlaubte Uebergaenge (exakt das vereinbarte Modell, mc 2026-07-12).
#: Endzustaende haben KEINE ausgehende Kante.
#:
#: BEWUSST NICHT enthalten: 'offen' -> 'erledigt'. 'erledigt' heisst
#: "Antwort da UND ausgewertet". Wer einen Vorgang ohne eingegangene Antwort
#: schliesst, schliesst ihn OHNE ERGEBNIS — das ist 'erfolglos'. Diese
#: Unterscheidung ist keine Formalie: sie ist der Unterschied zwischen einer
#: beantworteten und einer unbeantworteten Ermittlungsfrage, und sie muss im
#: Bericht stehen.
ALLOWED_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "offen": ("beantwortet", "erfolglos"),
    "beantwortet": ("erledigt", "erfolglos"),
    "erledigt": (),
    "erfolglos": (),
}

#: Alle gueltigen Zustaende (deckt sich mit dem CHECK in M010).
STATUSES: FrozenSet[str] = frozenset(STATUS_ORDER)

#: Fallzustaende, die den Fall als abgeschlossen gelten lassen (cases.status).
CLOSED_CASE_STATUSES: Tuple[str, ...] = ("approved", "closed")


class MatterStatusError(Exception):
    """Unzulaessiger Zustandsuebergang oder unbekannter Zustand."""


class MatterStatus:
    """Zustandsmaschine + Ampel externer Vorgaenge (reine Logik)."""

    # ------------------------------------------------------------ Zustaende
    @staticmethod
    def is_valid(status: str) -> bool:
        return status in STATUSES

    @staticmethod
    def is_open(status: str) -> bool:
        return status in OPEN_STATUSES

    @staticmethod
    def is_final(status: str) -> bool:
        return status in FINAL_STATUSES

    @staticmethod
    def label(status: str) -> str:
        return STATUS_LABEL.get(status, status)

    @staticmethod
    def allowed_next(status: str) -> Tuple[str, ...]:
        """Zulaessige Folgezustaende. Unbekannter Zustand -> Fehler, nie ()."""
        if status not in STATUSES:
            raise MatterStatusError(
                "Unbekannter Zustand '%s' (gueltig: %s)."
                % (status, ", ".join(STATUS_ORDER)))
        return ALLOWED_TRANSITIONS[status]

    @classmethod
    def check_transition(cls, current: str, target: str) -> None:
        """
        Prueft den Uebergang current -> target. Verstoss -> MatterStatusError.
        Der Fehlertext nennt AUSDRUECKLICH die Endgueltigkeit, damit niemand
        einen Abschluss versehentlich als Bedienfehler missversteht.
        """
        if target not in STATUSES:
            raise MatterStatusError(
                "Unbekannter Zielzustand '%s' (gueltig: %s)."
                % (target, ", ".join(STATUS_ORDER)))
        allowed = cls.allowed_next(current)
        if target in allowed:
            return
        if cls.is_final(current):
            raise MatterStatusError(
                "Vorgang ist mit '%s' ENDGUELTIG abgeschlossen und kann nicht "
                "nach '%s' zurueckgefuehrt werden. Ein Irrtum wird durch einen "
                "NEUEN Vorgang korrigiert, nicht durch Zurueckdrehen."
                % (current, target))
        raise MatterStatusError(
            "Uebergang '%s' -> '%s' ist nicht vorgesehen (zulaessig: %s)."
            % (current, target, ", ".join(allowed) or "keiner"))

    @classmethod
    def check_deferrable(cls, current: str) -> None:
        """Verschieben der Wiedervorlage: nur in offenen Zustaenden."""
        if not cls.is_open(current):
            raise MatterStatusError(
                "Vorgang ist mit '%s' abgeschlossen — die Wiedervorlage kann "
                "nicht mehr verschoben werden." % current)

    # ----------------------------------------------------------------- Ampel
    @staticmethod
    def parse_date(iso: str) -> date:
        """ISO-Datum -> date. Ein kaputtes Datum wird NICHT stillschweigend
        auf 'heute' gesetzt, sondern schlaegt fehl (Grundregel 1)."""
        try:
            return date.fromisoformat(iso)
        except (TypeError, ValueError) as exc:
            raise MatterStatusError(
                "Ungueltiges Datum '%s' (erwartet YYYY-MM-DD)." % iso) from exc

    @classmethod
    def ampel(
        cls,
        *,
        status: str,
        wiedervorlage_am: str,
        stichtag: str,
        vorwarnfrist_tage: int = DEFAULT_VORWARNFRIST_TAGE,
        case_status: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Liefert (ampel, begruendung).

        ampel: 'rot' | 'gelb' | 'gruen' | 'neutral'
        Die BEGRUENDUNG wird immer mitgeliefert — eine Ampel ohne Grund ist im
        forensischen Kontext wertlos (sie muss im Bericht erklaerbar sein).
        """
        if not cls.is_valid(status):
            raise MatterStatusError("Unbekannter Zustand '%s'." % status)

        if cls.is_final(status):
            return "neutral", "Abgeschlossen (%s)." % cls.label(status)

        due = cls.parse_date(wiedervorlage_am)
        today = cls.parse_date(stichtag)

        # SONDERFALL: verwaister Vorgang. Immer rot, unabhaengig vom Datum.
        if case_status in CLOSED_CASE_STATUSES:
            return "rot", (
                "Fall ist geschlossen (%s), der Vorgang ist aber noch offen "
                "(%s). Es wurde nichts automatisch geschlossen — bitte "
                "entscheiden." % (case_status, cls.label(status)))

        if due <= today:
            tage = (today - due).days
            if tage == 0:
                return "rot", "Heute faellig (%s)." % wiedervorlage_am
            return "rot", ("Ueberfaellig seit %d Tag(en) (war faellig am %s)."
                           % (tage, wiedervorlage_am))

        frist = max(0, int(vorwarnfrist_tage))
        if due <= today + timedelta(days=frist):
            rest = (due - today).days
            return "gelb", ("Faellig in %d Tag(en) am %s (Vorwarnfrist %d Tage)."
                            % (rest, wiedervorlage_am, frist))

        rest = (due - today).days
        return "gruen", ("Faellig in %d Tag(en) am %s." % (rest,
                                                           wiedervorlage_am))

    @staticmethod
    def rank(ampel: str) -> int:
        """Sortierrang: rot vor gelb vor gruen vor neutral (Handlungsbedarf zuerst)."""
        return {"rot": 0, "gelb": 1, "gruen": 2, "neutral": 3}.get(ampel, 9)

# =============================================================================
# management/external/release_status.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Externe Fallfreigabe (AP-2G)
# =============================================================================
# Zweck (Idee 26):
#   Die ZUSTANDSMASCHINE der externen Fallfreigabe und das VOKABULAR des
#   Freigabe-UMFANGS — reine Logik, keine DB, keine Uhr. Vollstaendig in pytest
#   pruefbar.
#
# STATUSMODELL (verbindlich, mc-Freigabe 2026-07-20):
#
#   freigegeben ──(widerrufen + GRUND)──► widerrufen   ✔ endgueltig
#
#   - 'freigegeben' = die aktive externe Freigabe (der NRW-Ermittler hat Zugriff
#     erhalten). 'widerrufen' = zurueckgezogen, ENDGUELTIG. Eine erneute Freigabe
#     ist ein NEUER Record — die Historie einer Weitergabe wird nicht
#     umgeschrieben (gleiche Linie wie MatterStatus/Build 385, Berichts-Siegel/
#     Build 377).
#   - GRUND ist PFLICHT beim Widerruf: warum ein einmal gewaehrter externer
#     Zugriff zurueckgezogen wird, muss belegt sein (Grundregel 1).
#
# UMFANG (was freigegeben wird) — Vokabular IM CODE, nicht in der DDL (additiv,
#   kein CHECK; eine spaetere Umfangsart bleibt ein Einzeiler, kein Tabellen-
#   Rebuild an produktiven Daten — gleiche Linie wie matter_kinds):
#     bericht  — der (gesiegelte) Ermittlungsbericht
#     akte     — die vollstaendige Ermittlungsakte (Bericht + Belege)
#     auszug   — ein geprueft-unverfaenglicher Teilauszug
#
# Version: v0.7.462 · Build: 462 · 2026-07-20
# =============================================================================

from typing import Dict, FrozenSet, Tuple

#: Zustaende — deckungsgleich mit dem CHECK in M016.
STATUSES: Tuple[str, ...] = ("freigegeben", "widerrufen")

#: Endzustand — unwiderruflich.
FINAL_STATUSES: Tuple[str, ...] = ("widerrufen",)

STATUS_LABEL: Dict[str, str] = {
    "freigegeben": "freigegeben (aktiver externer Zugriff)",
    "widerrufen": "widerrufen (Zugriff zurueckgezogen)",
}

#: Erlaubte Uebergaenge. Der Endzustand hat KEINE ausgehende Kante.
ALLOWED_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "freigegeben": ("widerrufen",),
    "widerrufen": (),
}

# --- Freigabe-Umfang ---------------------------------------------------------
UMFANG_ORDER: Tuple[str, ...] = ("bericht", "akte", "auszug")

UMFANG_LABEL: Dict[str, str] = {
    "bericht": "Ermittlungsbericht (gesiegelt)",
    "akte": "vollstaendige Ermittlungsakte",
    "auszug": "geprüfter Teilauszug",
}

UMFANG: FrozenSet[str] = frozenset(UMFANG_ORDER)


class ReleaseStatusError(Exception):
    """Unzulaessiger Zustandsuebergang, unbekannter Zustand/Umfang oder
    fehlender Grund."""


class ReleaseStatus:
    """Zustandsmaschine der externen Fallfreigabe (reine Logik)."""

    @staticmethod
    def is_valid(status: str) -> bool:
        return status in STATUSES

    @staticmethod
    def is_final(status: str) -> bool:
        return status in FINAL_STATUSES

    @staticmethod
    def label(status: str) -> str:
        return STATUS_LABEL.get(status, status)

    @staticmethod
    def allowed_next(status: str) -> Tuple[str, ...]:
        if status not in ALLOWED_TRANSITIONS:
            raise ReleaseStatusError(
                "Unbekannter Zustand '%s' (gueltig: %s)."
                % (status, ", ".join(STATUSES)))
        return ALLOWED_TRANSITIONS[status]

    @classmethod
    def check_transition(cls, current: str, target: str) -> None:
        """Prueft current -> target. Verstoss -> ReleaseStatusError."""
        if target not in STATUSES:
            raise ReleaseStatusError(
                "Unbekannter Zielzustand '%s' (gueltig: %s)."
                % (target, ", ".join(STATUSES)))
        if target in cls.allowed_next(current):
            return
        if cls.is_final(current):
            raise ReleaseStatusError(
                "Freigabe ist mit '%s' ENDGUELTIG abgeschlossen und kann nicht "
                "nach '%s' zurueckgefuehrt werden. Eine erneute Freigabe ist ein "
                "NEUER Vorgang." % (current, target))
        raise ReleaseStatusError(
            "Uebergang '%s' -> '%s' ist nicht vorgesehen (zulaessig: %s)."
            % (current, target, ", ".join(cls.allowed_next(current)) or "keiner"))


# --------------------------------------------------------------- Umfang-Helfer
def umfang_is_valid(umfang: str) -> bool:
    """True, wenn 'umfang' eine bekannte Umfangsart ist."""
    return umfang in UMFANG


def umfang_label(umfang: str) -> str:
    """Klartext zur Umfangsart; unbekannte Werte werden NICHT verschluckt."""
    return UMFANG_LABEL.get(umfang, umfang)


def umfang_catalog() -> Tuple[Dict[str, str], ...]:
    """Katalog fuer Oberflaeche/CLI: (code, label) in fachlicher Reihenfolge."""
    return tuple({"code": u, "label": UMFANG_LABEL[u]} for u in UMFANG_ORDER)

# =============================================================================
# management/crossref/crossfinding_channel_status.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Querfunde (AP-2A)
# =============================================================================
# Zweck (Idee 7, Build 507 — der QUERFUND-RUECKKANAL):
#   Die ZUSTANDSMASCHINE ueber den MENSCHLICHEN UMGANG mit einem Querfund —
#   als REINE Logik, ohne Datenbank, ohne Uhr. Damit vollstaendig in pytest
#   pruefbar (Muster promotion_status.py, matter_status.py, checklist_status.py).
#
# DAS PROBLEM, DAS SIE LOEST:
#   Ein Querfund ist die Lage "Ermittlerin A stoesst im Fall A auf eine
#   Erkenntnis ueber Konto B, das Ermittler B bearbeitet". Der TRANSPORT laeuft
#   bereits vollautomatisch (forensic_api/cross_annotation_integrator.py ->
#   pending_cross_annotations -> Ziel-evidence_<uid>.db), und Build 474/478
#   machen ihn SICHTBAR.
#   Was fehlte: 'integrated_at' belegt nur, dass die TECHNIK die Annotation
#   kopiert hat. Ob ein MENSCH sie je gesehen, verwertet oder als irrelevant
#   bewertet hat, war UNBELEGT — ein still uebergangener Beleg (Grundregel 1).
#   Dieser Zustand aendert NICHTS am Transport; er legt den Nachweis darueber,
#   was mit dem Fund geschehen ist, daneben.
#
# ZUSTANDSMODELL:
#
#   (kein Eintrag = implizit 'offen' — der Fund liegt vor, niemand hat quittiert)
#        │
#        ├──(zustellen)──────────────► zugestellt
#        │                                  │
#        ├──(quittieren)─────────────► quittiert   (B hat den Fund GESEHEN)
#        │                                  │
#        ├──(verwerten + BASIS)──────► verwertet          ✔ endgueltig
#        │
#        └──(nicht relevant + GRUND)─► nicht_relevant     ✔ endgueltig
#
#   - 'offen' ist ein PSEUDO-Zustand: er wird NIE gespeichert (die Abwesenheit
#     einer Zeile IST 'offen'). Deckt sich mit dem CHECK in M024.
#   - 'verwertet' und 'nicht_relevant' sind ENDGUELTIG. Gleiche Linie wie
#     MatterStatus (385), Berichts-Statusmodell (377), PromotionStatus (460):
#     ein Irrtum wird durch eine NEUE, belegte Erkenntnis korrigiert, nicht
#     durch Zurueckdrehen.
#   - 'zugestellt' ist UEBERSPRINGBAR: wer den Fund im Cockpit unmittelbar
#     sieht, soll ihn direkt quittieren koennen ('offen' -> 'quittiert').
#     Ein erzwungener Zwischenschritt haette nur Klicks erzeugt, keinen Beleg.
#   - 'quittiert' -> 'zugestellt' ist VERBOTEN: man kann nicht ungesehen
#     machen, was gesehen wurde.
#
# PFLICHTFELDER (der eigentliche forensische Kern):
#   - GRUND ist Pflicht bei 'nicht_relevant'. Ein stilles Wegwischen eines
#     Querfundes ist exakt die Luecke, die dieses System schliesst.
#   - BASIS ist Pflicht bei 'verwertet'. "Verwertet" ist eine Tatsachen-
#     behauptung ueber die Ermittlung — sie braucht ihren Beleg (wo ist die
#     Erkenntnis eingeflossen?).
#   Beide teilen sich das Feld 'reason' in M024; welcher Sinn gemeint ist,
#   ergibt sich aus dem Zielzustand. Zwei getrennte Spalten haetten dieselbe
#   Sache doppelt modelliert.
#
# VOKABULAR IM CODE, zusaetzlich CHECK in der DDL: die Zustandsmenge ist
#   abgeschlossen, und ein Tippfehler liesse eine Zeile aus jedem Filter fallen
#   (stiller Beweisverlust) — gleiche Abwaegung wie in M015/M018.
#
# Beleg: mc 2026-07-24 (Auftrag "A1 bis A4"); Bauplan
#   claude_Bauplan_A2_QuerfundRueckkanal_v0_1.md Par. 2.1.
# Version: v0.8.507 · Build: 507 · 2026-07-24
# =============================================================================

from typing import Dict, FrozenSet, Tuple

#: Implizite Eingangslage — NIE gespeichert (Abwesenheit einer Zeile).
INITIAL: str = "offen"

#: Gespeicherte Zustaende — deckungsgleich mit dem CHECK in M024.
STORED_STATUSES: Tuple[str, ...] = (
    "zugestellt",
    "quittiert",
    "verwertet",
    "nicht_relevant",
)

#: Endzustaende — unwiderruflich.
FINAL_STATUSES: Tuple[str, ...] = ("verwertet", "nicht_relevant")

#: Zielzustaende, die einen Pflichttext verlangen (Grund bzw. Basis).
REASON_REQUIRED: Tuple[str, ...] = ("verwertet", "nicht_relevant")

#: Was der Pflichttext im jeweiligen Zielzustand BEDEUTET — fuer sprechende
#  Fehlermeldungen und als Beschriftung in der Oberflaeche.
REASON_MEANING: Dict[str, str] = {
    "verwertet": "Basis (wo ist die Erkenntnis eingeflossen?)",
    "nicht_relevant": "Grund (warum traegt der Fund nicht?)",
}

#: Reihenfolge fuer Filter/Anzeige: das Handlungsbeduerftige zuerst.
STATUS_ORDER: Tuple[str, ...] = (
    "offen",
    "zugestellt",
    "quittiert",
    "verwertet",
    "nicht_relevant",
)

STATUS_LABEL: Dict[str, str] = {
    "offen": "offen (noch nicht quittiert)",
    "zugestellt": "zugestellt (Kenntnisnahme ausstehend)",
    "quittiert": "quittiert (zur Kenntnis genommen)",
    "verwertet": "verwertet",
    "nicht_relevant": "nicht relevant",
}

#: Erlaubte Uebergaenge. 'offen' ist die implizite Eingangslage und darf in
#: jeden gespeicherten Zustand uebergehen. Endzustaende haben KEINE ausgehende
#: Kante. 'quittiert' -> 'zugestellt' fehlt bewusst (nicht ungesehen machbar).
ALLOWED_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "offen": ("zugestellt", "quittiert", "verwertet", "nicht_relevant"),
    "zugestellt": ("quittiert", "verwertet", "nicht_relevant"),
    "quittiert": ("verwertet", "nicht_relevant"),
    "verwertet": (),
    "nicht_relevant": (),
}

_ALL_STATES: FrozenSet[str] = frozenset(ALLOWED_TRANSITIONS.keys())


class CrossfindingChannelError(Exception):
    """Unzulaessiger Uebergang, unbekannter Zustand oder fehlender Pflichttext."""


class CrossfindingChannelStatus:
    """Zustandsmaschine des Querfund-Rueckkanals (reine Logik)."""

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
        """True, wenn der Zielzustand einen Pflichttext verlangt."""
        return target in REASON_REQUIRED

    @staticmethod
    def reason_meaning(target: str) -> str:
        """Was der Pflichttext im Zielzustand bedeutet (leer, wenn keiner)."""
        return REASON_MEANING.get(target, "")

    @staticmethod
    def label(status: str) -> str:
        return STATUS_LABEL.get(status, status)

    @staticmethod
    def allowed_next(status: str) -> Tuple[str, ...]:
        """Zulaessige Folgezustaende. Unbekannter Zustand -> Fehler, nie ()."""
        if status not in ALLOWED_TRANSITIONS:
            raise CrossfindingChannelError(
                "Unbekannter Zustand '%s' (gueltig: %s)."
                % (status, ", ".join(STATUS_ORDER)))
        return ALLOWED_TRANSITIONS[status]

    @classmethod
    def check_transition(cls, current: str, target: str) -> None:
        """
        Prueft den Uebergang current -> target. Verstoss ->
        CrossfindingChannelError. 'current' darf die implizite Eingangslage
        'offen' sein (noch keine Zeile). 'target' MUSS ein gespeicherter
        Zustand sein — 'offen' ist kein gueltiges ZIEL (man kehrt nicht in die
        Unentschiedenheit zurueck; das waere ein stilles Verwerfen der
        bisherigen Kenntnisnahme).
        """
        if target not in STORED_STATUSES:
            raise CrossfindingChannelError(
                "Unbekannter/ungueltiger Zielzustand '%s' (gueltig: %s)."
                % (target, ", ".join(STORED_STATUSES)))
        allowed = cls.allowed_next(current)
        if target in allowed:
            return
        if cls.is_final(current):
            raise CrossfindingChannelError(
                "Der Querfund ist mit '%s' ENDGUELTIG bewertet und kann nicht "
                "nach '%s' gefuehrt werden. Ein Irrtum wird durch eine NEUE, "
                "belegte Erkenntnis korrigiert, nicht durch Zurueckdrehen."
                % (current, target))
        if current == "quittiert" and target == "zugestellt":
            raise CrossfindingChannelError(
                "Ein bereits quittierter Querfund kann nicht wieder auf "
                "'zugestellt' gesetzt werden — was gesehen wurde, laesst sich "
                "nicht ungesehen machen.")
        raise CrossfindingChannelError(
            "Uebergang '%s' -> '%s' ist nicht vorgesehen (zulaessig: %s)."
            % (current, target, ", ".join(allowed) or "keiner"))

    @classmethod
    def check_reason(cls, target: str, reason: str) -> None:
        """Pflichttext durchsetzen. Fehlt er -> CrossfindingChannelError."""
        if cls.requires_reason(target) and not (reason or "").strip():
            raise CrossfindingChannelError(
                "Pflichtangabe fehlt: der Uebergang nach '%s' verlangt eine "
                "Angabe — %s." % (target, cls.reason_meaning(target)))

    @staticmethod
    def rank(status: str) -> int:
        """Sortierrang fuer die Anzeige: Handlungsbeduerftiges zuerst."""
        return {
            "offen": 0,
            "zugestellt": 1,
            "quittiert": 2,
            "verwertet": 3,
            "nicht_relevant": 4,
        }.get(status, 9)

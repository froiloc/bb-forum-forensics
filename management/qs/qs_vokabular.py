# =============================================================================
# management/qs/qs_vokabular.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3C (Build 540)
# =============================================================================
# Zweck:
#   Die kontrollierten Vokabulare der QS-Stichprobe. EINE Datei, EINE
#   Wahrheitsquelle — die Migration M034 fuehrt eine EINGEFRORENE Kopie der
#   Codes in ihren CHECK-Bedingungen (m005-Prinzip: eine angewandte Migration
#   darf ihr Verhalten nie aendern), und ein Test haelt beide gegeneinander.
#
# ── DIE ZWECKBINDUNG ─────────────────────────────────────────────────────────
#
#   AUSWERTUNGSQUALITAET, KEIN MITARBEITER-BEWERTUNGSINSTRUMENT.
#
#   Sie steht hier im Code, weil sie in JEDE Antwort gehoert und es genau eine
#   Formulierung geben darf. Jede Entwurfsentscheidung dieser Datei ist daran
#   gemessen — insbesondere die Ergebniscodes.
#
# ── WARUM 'ergebnis' KEINE NOTE IST ──────────────────────────────────────────
#
#   Die vier Codes tragen bewusst KEINEN Punktwert und keine Rangfolge im Sinne
#   von 'gut/mittel/schlecht'. 'mangelhaft' kommt nicht vor. Geprueft wird die
#   AUSWERTUNG eines Falls, nicht die Person, die sie gemacht hat — und eine
#   Skala mit einem schlechten Ende waere genau das
#   Mitarbeiter-Bewertungsinstrument, das dieses Paket nicht sein darf.
#
#   'nicht_beurteilbar' ist ausdruecklich dabei. Ohne diesen Code wuerde ein
#   unklarer Fall in eine der drei anderen Kategorien GEDRUECKT, und die Zahlen
#   saehen genauer aus, als die Pruefung war. Dieselbe Ueberlegung wie beim
#   fuenften Feld der Matrix (Build 536) und beim Befund 'nicht_geprueft' des
#   Fristenmonitors (Build 535).
#
# ── DIE SCHICHTEN ────────────────────────────────────────────────────────────
#
#   Entscheidung mc (Uebergabe §2.3, bestaetigt 2026-07-26): GESCHICHTETE
#   Ziehung. Die Schichten kommen aus der Abdeckung der Bewertungskriterien
#   (coverage_repo), weil die BLINDEN FLECKEN ueberproportional geprueft werden
#   sollen. Eine einfache Zufallsstichprobe haette bei 84.328 Themen und
#   wenigen Prueflingen die interessanten Faelle fast nie erwischt.
#
# Version: v0.8.540 · Build: 540 · 2026-07-26
# =============================================================================

from __future__ import annotations

from typing import Dict, FrozenSet, Tuple

#: Die Zweckbindung. EINE Formulierung, die in jede Antwort mitfaehrt.
#  Sie wird NICHT im Frontend und NICHT im Endpunkt zweitformuliert (Muster:
#  'zweckbindung' des Matrix-Gewichtungssatzes, Build 536).
ZWECKBINDUNG: str = (
    "AUSWERTUNGSQUALITAET, KEIN MITARBEITER-BEWERTUNGSINSTRUMENT. Die "
    "QS-Stichprobe prueft die AUSWERTUNG eines Falls — ob die Belege gesichtet, "
    "die Kriterien bewertet und die Schluesse belegt sind. Sie erhebt keine "
    "Leistungsdaten, bildet keine Rangfolge zwischen Personen und darf zu "
    "keiner dienstlichen Beurteilung herangezogen werden. Ein Pruefergebnis "
    "ist ein Befund zur Sache, kein Urteil ueber eine Ermittlerin."
)

#: Die Ergebniscodes je geprueftem Fall. Reihenfolge = Darstellungsreihenfolge,
#  NICHT eine Rangfolge von gut nach schlecht.
ERGEBNIS_CODES: Tuple[str, ...] = (
    "in_ordnung",
    "nachzuarbeiten",
    "ruecklauf_erforderlich",
    "nicht_beurteilbar",
)

ERGEBNIS_LABEL: Dict[str, str] = {
    "in_ordnung": "in Ordnung",
    "nachzuarbeiten": "nachzuarbeiten",
    "ruecklauf_erforderlich": "Ruecklauf erforderlich",
    "nicht_beurteilbar": "nicht beurteilbar",
}

ERGEBNIS_BEDEUTUNG: Dict[str, str] = {
    "in_ordnung":
        "Die Auswertung traegt. Kein Handlungsbedarf an der Sache.",
    "nachzuarbeiten":
        "Die Auswertung ist unvollstaendig; die fehlenden Schritte sind in der "
        "Begruendung benannt. KEINE Aussage ueber die bearbeitende Person.",
    "ruecklauf_erforderlich":
        "Die Auswertung kann so nicht in die Akte. Der Fall geht zurueck; die "
        "Begruendung nennt, was fehlt oder nicht traegt.",
    "nicht_beurteilbar":
        "Die Pruefung konnte zu keinem Befund kommen — etwa weil Unterlagen "
        "fehlen oder die Datenlage keine Beurteilung zulaesst. Das ist ein "
        "eigener Befund und ausdruecklich NICHT 'in Ordnung'.",
}

#: Die Ziehungsverfahren. 'geschichtet' ist die Festlegung von mc; 'einfach'
#  bleibt vorgesehen, weil eine Grundgesamtheit ohne Bewertungsdaten sich nicht
#  schichten laesst — dann WIRD das Verfahren gewechselt und das steht in der
#  Ziehung, statt dass eine leere Schicht stillschweigend uebersprungen wird.
VERFAHREN_CODES: Tuple[str, ...] = ("geschichtet", "einfach")

VERFAHREN_LABEL: Dict[str, str] = {
    "geschichtet": "geschichtete Zufallsstichprobe (nach Abdeckung)",
    "einfach": "einfache Zufallsstichprobe",
}

#: Die Schichten der geschichteten Ziehung, in der Reihenfolge ihrer
#  Prueflast. Die BLINDEN FLECKEN zuerst — das ist der Grund fuer die
#  Schichtung ueberhaupt.
SCHICHT_CODES: Tuple[str, ...] = (
    "nie_bewertet",       # kein einziges Kriterium bewertet
    "abdeckung_niedrig",  # Abdeckung unter der Schwelle
    "rest",               # alles uebrige
)

SCHICHT_LABEL: Dict[str, str] = {
    "nie_bewertet": "nie bewertet (kein Kriterium)",
    "abdeckung_niedrig": "Abdeckung unter der Schwelle",
    "rest": "uebrige Faelle",
}

#: DIE UEBERGEWICHTUNG DER BLINDEN FLECKEN.
#
#  DIESE ZAHLEN SIND DER EIGENTLICHE INHALT DER ENTSCHEIDUNG 'GESCHICHTET'.
#  Eine Schichtung, die PROPORTIONAL zieht, prueft die blinden Flecken genau so
#  oft wie ihr Anteil an der Grundgesamtheit — sie leistet damit nichts, was
#  eine einfache Zufallsstichprobe nicht auch leistete, und der ganze Aufwand
#  waere Zierrat. mcs Vorgabe lautet ausdruecklich 'ueberproportional'
#  (Bauplan AP-3C §3 Nr. 1). Erst diese Gewichte setzen sie um.
#
#  Gerechnet wird ueber die GEWICHTETE MASSE einer Schicht (Zahl der Faelle mal
#  Gewicht); ein Fall der Schicht 'nie bewertet' zaehlt bei der Aufteilung also
#  dreifach. Die Gewichte fahren in 'filter_json' mit, damit eine spaetere
#  Aenderung alte Ziehungen nicht unnachvollziehbar macht, sondern beim
#  Nachziehen ALS ABWEICHUNG auffaellt.
#
#  DIE GEWICHTE SIND EINE LEITUNGSENTSCHEIDUNG, keine Rechengroesse. Wer sie
#  aendert, aendert, wessen Arbeit wie oft geprueft wird.
SCHICHT_GEWICHT: Dict[str, float] = {
    "nie_bewertet": 3.0,
    "abdeckung_niedrig": 2.0,
    "rest": 1.0,
}

#: Die Abdeckungsschwelle, unterhalb derer ein Fall in die zweite Schicht faellt.
#  Sie steht HIER und nicht im Aufrufer, damit die Schichtung einer Ziehung
#  reproduzierbar bleibt: der Wert wird in 'filter_json' mitgeschrieben, und
#  eine spaetere Aenderung dieser Konstante macht alte Ziehungen deshalb nicht
#  unnachvollziehbar — sie wuerde beim Nachziehen ALS ABWEICHUNG auffallen.
ABDECKUNG_SCHWELLE: float = 0.5

ERGEBNIS_SET: FrozenSet[str] = frozenset(ERGEBNIS_CODES)
VERFAHREN_SET: FrozenSet[str] = frozenset(VERFAHREN_CODES)
SCHICHT_SET: FrozenSet[str] = frozenset(SCHICHT_CODES)


def ergebnis_gueltig(code: str) -> bool:
    return code in ERGEBNIS_SET


def verfahren_gueltig(code: str) -> bool:
    return code in VERFAHREN_SET


def schicht_gueltig(code: str) -> bool:
    return code in SCHICHT_SET


def ergebnis_label(code: str) -> str:
    """Klartext. Ein unbekannter Code wird BENANNT, nicht abgebildet."""
    return ERGEBNIS_LABEL.get(code, "unbekanntes Ergebnis (%s)" % code)


def schicht_label(code: str) -> str:
    return SCHICHT_LABEL.get(code, "unbekannte Schicht (%s)" % code)

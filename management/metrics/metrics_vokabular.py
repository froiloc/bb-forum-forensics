# =============================================================================
# management/metrics/metrics_vokabular.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3C (Build 542)
# =============================================================================
# Zweck:
#   Die Zweckbindung der Ermittler-Metriken, die Liste der ZULAESSIGEN
#   Kennzahlen und — genauso wichtig — die Liste dessen, was AUSDRUECKLICH
#   NICHT erhoben wird.
#
# ── WARUM DIE VERBOTSLISTE IM CODE STEHT ────────────────────────────────────
#
#   Eine Zweckbindung, die nur im Fliesstext einer Antwort steht, ist eine
#   Absichtserklaerung. Eine, gegen die ein TEST laeuft, ist eine Zusicherung.
#   VERBOTENE_KENNZAHLEN wird deshalb von einem Test gegen die tatsaechlich
#   gelieferten Schluessel gehalten: taucht eine davon je in einer Antwort auf,
#   bricht die Suite. Das ist der Unterschied zwischen 'wir wollen das nicht'
#   und 'das kann nicht passieren'.
#
#   DIE GEFAEHRLICHSTE KENNZAHL WAERE NICHT DIE BOESARTIGE, SONDERN DIE
#   BEILAEUFIGE: 'Beitraege je Stunde' liesse sich aus vorhandenen Daten in
#   fuenf Zeilen rechnen und saehe wie ein Fortschrittsmass aus. Sie waere eine
#   Leistungskennzahl je Person, und die erhebt dieses Werkzeug nicht.
#
# ── WAS ERHOBEN WIRD, UND WARUM ES ZULAESSIG IST ────────────────────────────
#
#   Jede Kennzahl unten beantwortet eine Frage ueber die AUSWERTUNG oder ueber
#   die VERTEILUNG DER ARBEIT — keine ueber die Leistung einer Person:
#
#     bestand      Faelle je Bearbeitungsstand — ein Lastbild der Dienststelle.
#     abdeckung    Abdeckung der Bewertungskriterien — Qualitaet der AUSWERTUNG.
#     anlaufzeit   Zuweisung bis zum ersten inhaltlichen Ereignis — sie zeigt
#                  LIEGEZEITEN, also ein Verteilungsproblem, und ausdruecklich
#                  kein Tempo: eine lange Anlaufzeit kann an Urlaub, an einer
#                  Ueberlast oder an einer fehlenden Zuarbeit liegen.
#     substanz     Faelle mit Zuweisung, aber ohne Annotation — sie zeigt
#                  FEHLENDE SUBSTANZ, nicht fehlenden Fleiss.
#
#   AGGREGIERT WIRD UEBER FAELLE, NICHT UEBER PERSONEN. Es gibt in dieser
#   Antwort keine Gruppierung nach person_id und keine Sortierung, aus der sich
#   eine Rangfolge zwischen Personen ablesen liesse.
#
# ── AUSREISSER WERDEN BENANNT, NICHT BEWERTET ───────────────────────────────
#
#   Ein 'Ausreisser' ist ein HINWEIS AUF PRUEFBEDARF AN DER AUSWERTUNG. Der
#   Text sagt das woertlich, in jeder Antwort — sonst wird aus einem
#   auffaelligen Fall eine auffaellige Person.
#
# Version: v0.8.542 · Build: 542 · 2026-07-26
# =============================================================================

from __future__ import annotations

from typing import Dict, FrozenSet, Tuple

#: Die Zweckbindung. EINE Formulierung, die in jede Antwort mitfaehrt.
#  Sie ist bewusst NICHT dieselbe wie die der QS-Stichprobe
#  (qs_vokabular.ZWECKBINDUNG): dort geht es um ein Pruefergebnis zu EINEM
#  Fall, hier um Aggregate ueber viele. Zwei Sachverhalte, zwei Saetze —
#  eine gemeinsame Formulierung waere fuer beide ungenau.
ZWECKBINDUNG: str = (
    "AUSWERTUNGSQUALITAET, KEIN MITARBEITER-BEWERTUNGSINSTRUMENT. Diese "
    "Kennzahlen beschreiben den Zustand der AUSWERTUNG und die VERTEILUNG der "
    "Arbeit in der Dienststelle. Sie erheben keine Leistungsdaten, bilden "
    "keine Rangfolge zwischen Personen und duerfen zu keiner dienstlichen "
    "Beurteilung herangezogen werden. Eine lange Liegezeit ist ein Hinweis auf "
    "ein Verteilungsproblem, nicht auf mangelnden Fleiss; ein Ausreisser ist "
    "ein Hinweis auf PRUEFBEDARF AN DER AUSWERTUNG und kein Befund ueber eine "
    "Person."
)

#: Die zulaessigen Kennzahlenblöcke (= die Top-Level-Schluessel der Antwort,
#  die Zahlen tragen). Jeder ist oben begruendet.
KENNZAHLEN: Tuple[str, ...] = (
    "bestand", "abdeckung", "anlaufzeit", "substanz",
)

KENNZAHL_BEDEUTUNG: Dict[str, str] = {
    "bestand":
        "Faelle je Bearbeitungsstand. Lastbild der Dienststelle — keine "
        "Leistungsaussage.",
    "abdeckung":
        "Verteilung der Abdeckung der Bewertungskriterien ueber die Faelle. "
        "Sie misst die AUSWERTUNG, nicht die auswertende Person.",
    "anlaufzeit":
        "Zeit von der Zuweisung bis zum ersten INHALTLICHEN Ereignis. Sie "
        "zeigt Liegezeiten und damit ein Verteilungsproblem; sie ist "
        "ausdruecklich kein Tempomass.",
    "substanz":
        "Faelle mit Zuweisung, aber ohne eine einzige Annotation. Sie zeigt "
        "fehlende SUBSTANZ in der Akte, nicht fehlenden Fleiss.",
}

#: WAS AUSDRUECKLICH NICHT ERHOBEN WIRD. Ein Test haelt diese Liste gegen die
#  tatsaechlichen Schluessel jeder Antwort (s. Kopf). Erweitern, nie kuerzen.
VERBOTENE_KENNZAHLEN: Tuple[str, ...] = (
    "beitraege_je_stunde",
    "annotationen_je_stunde",
    "faelle_je_stunde",
    "durchsatz_je_person",
    "rangliste",
    "ranking",
    "bestenliste",
    "leistung",
    "produktivitaet",
    "je_ermittler",
    "je_person",
    "pro_person",
    "person_ranking",
)

#: Die Klassengrenzen des Abdeckungs-Histogramms. Sie stehen HIER und nicht im
#  Aufrufer, damit zwei Abrufe dieselbe Einteilung haben — eine verschobene
#  Klassengrenze veraendert das Bild, ohne dass sich ein Wert geaendert haette.
ABDECKUNG_KLASSEN: Tuple[Tuple[str, float, float], ...] = (
    ("nie_bewertet", -0.01, 0.0),
    ("bis_25", 0.0, 0.25),
    ("bis_50", 0.25, 0.50),
    ("bis_75", 0.50, 0.75),
    ("ueber_75", 0.75, 1.01),
)

KENNZAHLEN_SET: FrozenSet[str] = frozenset(KENNZAHLEN)
VERBOTEN_SET: FrozenSet[str] = frozenset(VERBOTENE_KENNZAHLEN)


def kennzahl_bedeutung(code: str) -> str:
    """Klartext. Ein unbekannter Block wird BENANNT, nicht abgebildet."""
    return KENNZAHL_BEDEUTUNG.get(
        code, "unbekannter Kennzahlenblock (%s)" % code)

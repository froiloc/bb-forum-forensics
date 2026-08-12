# =============================================================================
# management/person/sichtbarkeitsbefund.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Ruhestand von Hand
# =============================================================================
# Zweck:
#   Reines Lese-DTO (frozen dataclass) EINES Ausblende-Befundes. Eigene Datei
#   gemaess Grundregel 10 (jede Klasse in eine eigene Datei).
#
#   WARUM ES DIESES DTO GIBT — UND WARUM ES NICHT EINFACH EINE LISTE IST:
#   Ticket 95139d2a verlangt, dass inaktive Personen "per Default in normalen
#   Tabellen nicht mehr angezeigt" werden. Eine Funktion, die dafuer nur die
#   gefilterte Liste zurueckgibt, macht aus dem Ausblenden ein STILLES
#   Ausblenden — und genau das verbietet Grundregel 1 ("Kein Beleg darf je
#   still uebersprungen werden"). Wer eine Tabelle mit 12 statt 14 Zeilen
#   sieht, muss erfahren, dass zwei Zeilen ausgeblendet wurden und warum.
#   Deshalb tragen ALLE Filterwege dieses DTO: die Zeilen UND die Rechenschaft
#   darueber, was nicht in ihnen steht.
#
#   VIER VONEINANDER UNABHAENGIGE ANGABEN, DIE MAN NICHT ZUSAMMENFASSEN DARF:
#     1. 'ausgeblendet'         — wieviele Zeilen fehlen (Zahl fuer die Sicht).
#     2. 'behalten_mit_arbeit'  — wer trotz Inaktivitaet STEHENGEBLIEBEN ist,
#        weil er noch offene Faelle traegt (Entscheidung Alex, 12.08.2026).
#        Ohne diese Angabe waere die Zeile eines Ausgeschiedenen in der
#        Arbeitslast nicht von der eines Aktiven zu unterscheiden.
#     3. 'behalten_referenziert' — wer trotz Inaktivitaet STEHENGEBLIEBEN ist,
#        weil ein BESTEHENDER Datensatz dieser Sicht ihn bereits nennt. Das
#        ist ein ANDERER Grund als (2) und darf nicht mit ihm verschmelzen:
#        hier geht es nicht um Arbeitslast, sondern darum, dass eine
#        Auswahlliste, aus der die aktuell gewaehlte Person fehlt, beim
#        naechsten Speichern deren Zuordnung STILL fallen liesse.
#     4. 'hinweis'              — die Ausblendung konnte NICHT verlaesslich
#        entschieden werden (z. B. Tabelle 'cases' nicht lesbar). Dann wird
#        NICHTS ausgeblendet, und der Grund steht hier. Ein Filter, der bei
#        Unsicherheit ausblendet, verschweigt im Zweifel Belege.
#
# Version: v0.8.701 · Build: 701 · 2026-08-12
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Sichtbarkeitsbefund:
    """
    Ergebnis EINER Ausblende-Entscheidung ueber eine Personenliste.

    zeilen              — die verbleibenden Zeilen, Reihenfolge unveraendert
                          (der Filter sortiert NICHT um; die aufrufende Sicht
                          behaelt ihre eigene Ordnung).
    ausgeblendet        — Anzahl entfernter Zeilen (0, wenn nichts entfernt
                          wurde).
    ausgeblendete_kennungen
                        — system_username der entfernten Zeilen, aufsteigend.
                          Fuer die Rueckmeldung "ausgeblendet: a.muster,
                          b.beispiel" — eine Zahl allein laesst offen, WEN es
                          betrifft.
    behalten_mit_arbeit — system_username der inaktiven Personen, die
                          STEHENGEBLIEBEN sind, weil sie noch offene Faelle
                          tragen (nur bei Grundmengen-Sichten belegt).
    behalten_referenziert
                        — system_username der inaktiven Personen, die
                          STEHENGEBLIEBEN sind, weil ein bestehender Datensatz
                          dieser Sicht sie bereits nennt (nur bei
                          Auswahllisten mit Ausnahmen belegt).
    inaktive_gezeigt    — True, wenn der Aufrufer die Ausblendung ausdruecklich
                          abgeschaltet hat (Umschalter "Inaktive einblenden").
                          Dann ist 'ausgeblendet' immer 0.
    hinweis             — Klartext, falls die Entscheidung nicht verlaesslich
                          getroffen werden konnte; sonst None. Ist er gesetzt,
                          wurde NICHTS ausgeblendet.
    """

    zeilen: List[Any] = field(default_factory=list)
    ausgeblendet: int = 0
    ausgeblendete_kennungen: Tuple[str, ...] = ()
    behalten_mit_arbeit: Tuple[str, ...] = ()
    behalten_referenziert: Tuple[str, ...] = ()
    inaktive_gezeigt: bool = False
    hinweis: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Der Rechenschafts-Block fuer das JSON-Paket — OHNE die Zeilen (die
        stehen im Paket bereits an ihrer fachlichen Stelle und duerfen nicht
        doppelt uebertragen werden).

        Die Schluessel sind bewusst deutsch benannt wie die uebrigen Bloecke
        der jungeren Endpunkte; ein einziger Block 'inaktive' in jedem
        betroffenen Paket macht die Auswertung im Browser einheitlich.
        """
        return {
            "ausgeblendet": int(self.ausgeblendet),
            "ausgeblendete_kennungen": list(self.ausgeblendete_kennungen),
            "behalten_mit_arbeit": list(self.behalten_mit_arbeit),
            "behalten_referenziert": list(self.behalten_referenziert),
            "gezeigt": bool(self.inaktive_gezeigt),
            "hinweis": self.hinweis,
        }

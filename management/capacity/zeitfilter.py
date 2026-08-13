# =============================================================================
# management/capacity/zeitfilter.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kapazitaetspflege
# =============================================================================
# ZWECK: Entscheidet, welche Zeilen der Kapazitaetspflege HISTORISCH sind —
#   also vor dem laufenden Monat abgelaufen und deshalb standardmaessig
#   ausgeblendet.
#
# DER ANLASS (Vorgang 75f84fee, Alex): "In der Liste der Kapazitaetspflege
#   ... werden aeltere Daten aus der Vergangenheit angezeigt." Gewuenscht:
#   standardmaessig erst ab dem laufenden Monat, mit einer Umschaltung
#   'auch historische Daten anzeigen'.
#
# =============================================================================
# DIE ENTSCHEIDENDE FRAGE WAR: WORAN MISST MAN 'VERGANGENHEIT'?
#
# Am ANFANG einer Zeile zu messen waere der naheliegende, aber FALSCHE Weg.
# Eine Abwesenheit vom 20.07. bis zum 20.09. hat ihren Anfang in der
# Vergangenheit und laeuft trotzdem HEUTE noch. Wer sie ausblendet, verliert
# eine Angabe, die die Rechnung des laufenden Monats bestimmt — und zwar
# lautlos.
#
# Gemessen wird deshalb am ENDE: historisch ist, was VOR dem Monatsersten
# ABGELAUFEN ist. Alles, was in den laufenden Monat hineinreicht oder in der
# Zukunft liegt, bleibt sichtbar. Eine Zeile ohne Ende (offen) ist NIE
# historisch — sie gilt bis auf weiteres.
#
# DIE GRENZE IST DER MONATSERSTE, nicht der heutige Tag: der Vorgang nennt
# den Monat als Einheit, und die Kapazitaet wird ohnehin monatsweise
# betrachtet. Der Erste selbst gehoert dazu (>=), nicht dahinter.
#
# =============================================================================
# WARUM EIN EIGENES MODUL UND NICHT DREI ZEILEN IM ENDPUNKT:
# Die Regel ist die einzige Stelle, an der ueber SICHTBARKEIT VON BELEGEN
# entschieden wird. Sie gehoert dorthin, wo man sie ohne Datenbank, ohne
# Rechte und ohne HTTP pruefen kann — mit festen Datumsangaben statt mit dem
# heutigen Tag. Ein Fehler in dieser Regel waere sonst nur an einem Tag im
# Monat zu sehen.
#
# Abhaengigkeiten: datetime — ausschliesslich Stdlib.
# Version: v0.8.709 · Build: 709 · 2026-08-13
# =============================================================================

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple


def monatsbeginn(heute: date) -> str:
    """
    Liefert den Ersten des Monats von 'heute' als ISO-Datum (YYYY-MM-DD).

    Die Grenze wird als ZEICHENKETTE geliefert, weil die Datumsangaben der
    Kapazitaet im Schema ebenfalls als ISO-Text stehen (m008: period_start,
    period_end, day sind TEXT). Ein Vergleich Text gegen Text ist bei
    ISO-Datumsangaben zeichenweise identisch mit dem Vergleich der Kalender-
    tage — und erspart ein Zerlegen jeder einzelnen Zeile, das an einer
    unerwarteten Schreibweise scheitern koennte.
    """
    return heute.replace(day=1).isoformat()


def ist_historisch(datumswert: Optional[str], grenze: str) -> bool:
    """
    True, wenn dieser Zeitpunkt VOR der Grenze liegt.

    Args:
        datumswert: ISO-Datum (Ende eines Zeitraums oder der Tag selbst).
                    None/leer heisst OFFEN — dann NIE historisch: eine Regel
                    ohne Ende gilt bis auf weiteres.
        grenze:     ISO-Datum des Monatsersten.

    Ein unlesbarer Wert (falsche Laenge, fremdes Format) gilt AUSDRUECKLICH
    NICHT als historisch. Eine Zeile, deren Datum man nicht versteht, wird
    angezeigt und nicht weggeblendet — sie ist ein Befund und gehoert vor
    Augen (Grundregel 1).
    """
    if not datumswert:
        return False
    text = str(datumswert).strip()
    if len(text) < 10 or text[4] != "-" or text[7] != "-":
        return False
    return text[:10] < grenze


def teile_historisch(
    zeilen: List[Dict[str, Any]], feld: str, grenze: str
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Trennt eine Liste in (sichtbare Zeilen, Zahl der historischen).

    Args:
        zeilen: Datensaetze der Pflegeliste.
        feld:   Name des massgeblichen ENDdatums ('period_end', 'day',
                'effective_to').
        grenze: ISO-Datum des Monatsersten.

    Die ZAHL wird immer mitgegeben, auch wenn nicht ausgeblendet wird. Ohne
    sie koennte niemand wissen, dass es etwas einzublenden GIBT — dieselbe
    Ueberlegung wie bei den entfernten Zeilen (Build 562/563).
    """
    sichtbar: List[Dict[str, Any]] = []
    anzahl = 0
    # EINE Entscheidung je Zeile, und die Zeile wandert genau in einen der
    # beiden Zweige. Ein Vergleich der Datensaetze untereinander (z not in
    # historisch) waere hier ein Fehler: zwei inhaltsgleiche Zeilen wuerden
    # sich gegenseitig mitreissen.
    for z in zeilen:
        if ist_historisch(z.get(feld), grenze):
            anzahl += 1
        else:
            sichtbar.append(z)
    return sichtbar, anzahl

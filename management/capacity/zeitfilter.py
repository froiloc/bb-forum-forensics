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
# =============================================================================
# NACHTRAG BUILD 714 — DIE REGEL-ARBEITSZEITEN (Vorgang 75f84fee, zweiter
# Teil; Entscheidung Alex, 13.08.2026).
#
# Build 709 hat die Arbeitszeiten ausdruecklich ausgenommen. Das war fuer die
# ENDE-Regel zwingend richtig und traegt trotzdem nicht weit genug:
#
#   person_worktime ist APPEND-ONLY. Eine neue Regel schliesst die alte NICHT
#   per effective_to (Kopf worktime_repo.py); die geltende Regel ist die mit
#   dem groessten effective_from <= Stichtag (capacity_calculator.py:130-136).
#   GEMESSEN am 13.08.2026 auf einem eigens aufgebauten Bestand: von vier
#   Regeln trug KEINE ein effective_to.
#
#   Auf ein Enddatum zu pruefen ist dort also nicht falsch, sondern
#   WIRKUNGSLOS - 'ist_historisch' liefert fuer eine Arbeitszeitregel praktisch
#   nie True. Die Liste waechst weiter, und der Schalter, der sie kuerzen
#   soll, tut an dieser Stelle nichts.
#
# DAS ENDE EINER ARBEITSZEITREGEL ENTSTEHT NICHT DURCH EIN DATUM, SONDERN
# DURCH IHRE ABLOESUNG. Genau das misst 'teile_abgeloeste_worktime': eine
# Regel ist historisch, wenn es eine JUENGERE aktive Regel derselben Person
# gibt, deren effective_from <= Grenze liegt - erst dann kann die aeltere ab
# dem Monatsersten nie wieder gelten. Ein gesetztes effective_to VOR der
# Grenze wirkt daneben unveraendert ueber 'ist_historisch'.
#
# DAS IST DERSELBE GEDANKE WIE OBEN, nicht ein zweiter: "vor dem Monatsersten
# abgelaufen". Nur der Nachweis des Ablaufs sieht bei einer append-only-Kette
# anders aus. DIE GELTENDE REGEL BLEIBT DAMIT IMMER STEHEN, auch wenn sie
# Jahre alt ist - das war und bleibt der Kern von Build 709.
#
# DER BEGRIFF 'BELEGKETTE' AUS BUILD 709 GILT WEITER und wird nicht
# unterlaufen: die abgeloesten Zeilen sind nicht weg, sondern eine
# Umschaltung entfernt. Es ist dieselbe Zusicherung wie bei den entfernten
# Zeilen - ausgeblendet, gezaehlt, auf Wunsch wieder da.
# =============================================================================
#
# Abhaengigkeiten: datetime — ausschliesslich Stdlib.
# Build 714: teile_abgeloeste_worktime (Vorgang 75f84fee, zweiter Teil).
# Version: v0.8.714 · Build: 714 · 2026-08-13
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


# =============================================================================
# REGEL-ARBEITSZEITEN (Build 714) — siehe Nachtrag im Modulkopf.
# =============================================================================

def spaetester_start_je_person(
    zeilen: List[Dict[str, Any]], grenze: str
) -> Dict[Any, str]:
    """
    person_id -> groesstes effective_from, das NICHT hinter der Grenze liegt.

    Das ist die Regel, die am Monatsersten gilt; alles Aeltere derselben
    Person ist ab dann unerreichbar. Zeilen, die ERST IM LAUFENDEN MONAT
    beginnen, bleiben ausdruecklich unberuecksichtigt: beginnt die
    Nachfolgerin am 05., gilt die Vorgaengerin vom 01. bis zum 04. noch, und
    sie darf nicht verschwinden.

    Uebergeben werden sollten nur die NICHT entfernten Zeilen — eine
    soft-geloeschte Nachfolgeregel gilt fuer niemanden und darf ihre
    Vorgaengerin nicht verdraengen.
    """
    raus: Dict[Any, str] = {}
    for z in zeilen:
        start = z.get("effective_from")
        if not start:
            continue
        start = str(start)[:10]
        if start > grenze:
            continue
        pid = z.get("person_id")
        if pid not in raus or start > raus[pid]:
            raus[pid] = start
    return raus


def ist_abgeloest(
    zeile: Dict[str, Any], gueltig_ab: Dict[Any, str], grenze: str
) -> bool:
    """
    True, wenn diese Arbeitszeitregel ab dem Monatsersten nie wieder gelten
    kann — entweder weil ihr Ende vor der Grenze liegt (dann greift schon
    'ist_historisch') oder weil eine juengere Regel derselben Person sie
    abgeloest hat.

    OHNE LESBAREN STICHTAG GILT SIE NICHT ALS ABGELOEST. Eine Zeile, deren
    Datum man nicht versteht, wird angezeigt und nicht weggeblendet — dieselbe
    Linie wie in 'ist_historisch'.
    """
    if ist_historisch(zeile.get("effective_to"), grenze):
        return True
    start = zeile.get("effective_from")
    if not start:
        return False
    jung = gueltig_ab.get(zeile.get("person_id"))
    if jung is None:
        return False
    return str(start)[:10] < jung


def teile_abgeloeste_worktime(
    zeilen: List[Dict[str, Any]], grenze: str,
    aktive_zeilen: Optional[List[Dict[str, Any]]] = None
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Trennt Arbeitszeitregeln in (sichtbare Zeilen, Zahl der abgeloesten).

    aktive_zeilen — die Menge, aus der Nachfolger bestimmt werden. Ohne
    Angabe werden die nicht entfernten aus 'zeilen' genommen.

    Wie 'teile_historisch' gibt auch diese Funktion die ZAHL immer mit: ohne
    sie koennte niemand wissen, dass es etwas einzublenden gibt.
    """
    basis = (aktive_zeilen if aktive_zeilen is not None
             else [z for z in zeilen if not z.get("deleted_at")])
    gueltig_ab = spaetester_start_je_person(basis, grenze)
    sichtbar: List[Dict[str, Any]] = []
    anzahl = 0
    for z in zeilen:
        if ist_abgeloest(z, gueltig_ab, grenze):
            anzahl += 1
        else:
            sichtbar.append(z)
    return sichtbar, anzahl

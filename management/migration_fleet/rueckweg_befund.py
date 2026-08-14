# =============================================================================
# management/migration_fleet/rueckweg_befund.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Das Ergebnis EINES Rueckweg-Versuchs (Wiederherstellung einer Beweis-DB
#   aus der Pflicht-Sicherung nach einer gescheiterten Migration).
#
#   Diese Datei enthaelt NUR die Datenklasse (Projektregel 10). Der Vorgang
#   selbst steht in management/migration_fleet/rueckweg.py.
#
# WARUM ES DIESEN BEFUND UEBERHAUPT GIBT (Vorgang 69ede1c7):
#   Bis Build 720 hat der Rueckweg die Sicherung BEDINGUNGSLOS ueber die
#   Originaldatei kopiert. Der Quelltext nannte die Voraussetzung ausdruecklich
#   — "keine offene Verbindung auf path" — und PRUEFTE sie nicht. Damit gab es
#   auch nichts zu berichten: der Rueckweg konnte nur gelingen, notfalls eben
#   auf eine geoeffnete Datei, und das Ergebnis waere dann weder der alte noch
#   der neue Stand gewesen.
#
#   Sobald der Rueckweg NEIN sagen darf, muss er auch sagen koennen, WARUM und
#   WAS ZU TUN IST. Genau dafuer ist diese Klasse da. Sie transportiert keine
#   Wahrheitswerte, sondern eine Lage:
#
#     ausgefuehrt=True   Die Sicherung liegt wieder an ihrem Platz. Der alte
#                        Stand ist hergestellt.
#     ausgefuehrt=False  Es wurde NICHTS kopiert. Die Zieldatei ist unberuehrt
#                        geblieben (Zustand 'verweigert') oder der Kopiervorgang
#                        ist gescheitert (Zustand 'kopierfehler'); die Sicherung
#                        liegt in beiden Faellen unveraendert an ihrem Ort.
#
#   Die Unterscheidung der beiden Nein-Faelle ist nicht kosmetisch: Bei
#   'verweigert' ist die Zieldatei nachweislich NICHT angefasst worden, bei
#   'kopierfehler' ist ihr Zustand UNBESTIMMT. Das sind zwei sehr verschiedene
#   Nachrichten fuer den Menschen, der danach aufraeumen muss.
#
# Beleg: Vorgang 69ede1c7-3fe1-47eb-9d9a-f0cf6468f7dc, Befund 3 der
#        Wartungsanalyse (Vermerk_Wartungsvorbehalt_Analyse_K1_K8_v1_0.md §3),
#        maintenance/exklusiv_befund.py (Vorbild fuer die Dreiwertigkeit).
# Version: v0.8.723 · Build: 723 · 2026-08-14
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

#: Die drei Ausgaenge eines Rueckweg-Versuchs.
#: Als Zeichenketten und nicht als Wahrheitswerte — aus demselben Grund wie in
#: maintenance/exklusiv_befund.py: Zweiwertigkeit war der urspruengliche Fehler.
ZURUECKGESPIELT = "zurueckgespielt"   # kopiert; alter Stand steht wieder
VERWEIGERT = "verweigert"             # NICHT kopiert; Zieldatei unberuehrt
KOPIERFEHLER = "kopierfehler"         # Kopie begonnen und gescheitert

ZUSTAENDE: Tuple[str, ...] = (ZURUECKGESPIELT, VERWEIGERT, KOPIERFEHLER)


class RueckwegBefundError(Exception):
    """Ein Rueckweg-Befund ist in sich unstimmig."""


@dataclass(frozen=True)
class RueckwegBefund:
    """
    Das Ergebnis eines Rueckweg-Versuchs.

    zustand    — einer aus ZUSTAENDE.
    pfad       — die Zieldatei (die Beweis-DB, die wiederhergestellt werden
                 sollte).
    sicherung  — die Pflicht-Sicherung, aus der zurueckgespielt werden sollte.
                 Sie wird in KEINEM Fall geloescht oder veraendert; bei einem
                 Nein ist sie das Einzige, was den alten Stand noch traegt.
    grund      — Klartext, EINZEILIG. Bei 'verweigert' die Messung der
                 Sperrprobe, bei 'kopierfehler' die Fehlermeldung des
                 Betriebssystems. Ohne ihn waere die Lage nicht zu beheben.
    klartext   — die MEHRZEILIGE Ansage fuer den Menschen: welche Datei, welche
                 Sicherung, was von Hand zu tun ist. Sie geht auf die Konsole
                 und in das Protokoll.

    Bewusst KEIN Feld fuer "wurde die Sicherung veraendert": der Rueckweg
    schreibt niemals in die Sicherung. Ein Feld, das immer denselben Wert
    traegt, ist keine Auskunft, sondern eine Einladung zum Missverstaendnis.
    """
    pfad: str
    sicherung: str
    zustand: str
    grund: str
    klartext: str

    def __post_init__(self) -> None:
        if self.zustand not in ZUSTAENDE:
            raise RueckwegBefundError(
                "Unbekannter Zustand '%s' (zulaessig: %s)."
                % (self.zustand, ", ".join(ZUSTAENDE)))
        if not str(self.grund).strip():
            raise RueckwegBefundError(
                "Rueckweg-Befund ohne Grund. Bei einem Nein ist er das "
                "Einzige, woraus der Betrieb ableiten kann, was zu tun ist.")
        if not str(self.klartext).strip():
            raise RueckwegBefundError(
                "Rueckweg-Befund ohne Klartext. Die Ansage an den Menschen "
                "ist Teil des Ergebnisses und nicht ihr Beiwerk "
                "(Grundregel 1: kein Beleg wird still uebersprungen).")

    @property
    def ausgefuehrt(self) -> bool:
        """
        NUR 'zurueckgespielt' ist ein ausgefuehrter Rueckweg.

        AUSDRUECKLICH: 'kopierfehler' ist hier False. Ein halb ausgefuehrter
        Rueckweg ist kein ausgefuehrter — und er darf im Laufbuch nicht als
        'restored' erscheinen, sonst belegt das Laufbuch etwas, das nicht
        geschehen ist.
        """
        return self.zustand == ZURUECKGESPIELT

    @property
    def zieldatei_unberuehrt(self) -> bool:
        """
        Wurde die Zieldatei nachweislich NICHT angefasst?

        True nur bei 'verweigert'. Bei 'kopierfehler' ist der Zustand der
        Zieldatei UNBESTIMMT — und Unbestimmtheit darf nicht als Unberuehrtheit
        durchgehen.
        """
        return self.zustand == VERWEIGERT

    @property
    def marke(self) -> str:
        """Zehn Zeichen fuer die Konsolenausgabe — eine Spalte, die steht."""
        return {ZURUECKGESPIELT: "ZURUECK   ",
                VERWEIGERT: "VERWEIGERT",
                KOPIERFEHLER: "KOPIERFEHL"}[self.zustand]

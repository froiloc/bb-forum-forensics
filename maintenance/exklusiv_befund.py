# =============================================================================
# maintenance/exklusiv_befund.py
# IT-Forensisches Ermittlungswerkzeug — Wartungsmodus (Build 648)
# =============================================================================
# Zweck:
#   Das Ergebnis EINER Sperrprobe - und zwar mit DREI Zustaenden statt zwei.
#
#   Der Wartungsmodus stuetzt seinen ganzen Nachweis auf einen Satz:
#   "Die Bestaetigung allein ist nicht der Beweis - der Exklusiv-Lock-Erwerb
#   ist es." (tools/maintenance.py, Dateikopf seit Build 438.)
#
#   Ein Beweis, der auch dann gelingt, wenn gar nicht gemessen wurde, ist
#   keiner. Genau das war der Zustand bis Build 647 (Vorgang 96f2b18f).
#
# DIE DREI ZUSTAENDE:
#
#   RUHIG          Der Exklusiv-Lock wurde ERWORBEN. Niemand haelt die Datei.
#                  Das ist der einzige Zustand, der als Nachweis taugt.
#
#   BELEGT         Der Erwerb ist gescheitert, weil jemand sie haelt. Auch das
#                  ist eine MESSUNG - sie sagt: hier ist noch etwas los.
#
#   NICHT_MESSBAR  Es konnte nicht gemessen werden. Der haeufigste Fall: Der
#                  ausfuehrende Benutzer darf die Datei nicht BESCHREIBEN.
#                  SQLite oeffnet sie dann still nur lesend, und eine nur
#                  lesende Verbindung nimmt beim 'BEGIN EXCLUSIVE' UEBERHAUPT
#                  KEINE SPERRE - der Befehl gelingt folgenlos.
#
#                  BIS BUILD 647 WURDE DIESER FALL ALS 'RUHIG' VERBUCHT.
#
# WARUM DAS NICHT NUR VERSIEGELTE DATEIEN TRIFFT - der Punkt, der ueber die
# urspruengliche Meldung hinausgeht und am 2026-08-01 gemessen wurde:
#
#   Datei 0444 (versiegelt),           gemessen als Fremdbenutzer -> 'ruhig'
#   Datei 0644 (voellig gewoehnlich),  gemessen als Fremdbenutzer -> 'ruhig'
#
#   Beide Male hielt NIEMAND die Datei; beide Male war die Meldung 'exklusiv
#   erhalten' unverdient. Entscheidend ist nicht die Versiegelung, sondern ob
#   der MESSENDE PROZESS Schreibrecht hat. Auf einem geteilten Laufwerk, auf
#   dem der Dienst unter einem anderen Konto laeuft als die Wartung, ist das
#   der Normalfall und nicht die Ausnahme.
#
#   GEGENPROBE, ebenfalls gemessen: Haelt ein SCHREIBER eine EXCLUSIVE-Sperre,
#   meldet die Probe auch ohne Schreibrecht 'belegt' - eine EXCLUSIVE-Sperre
#   blockiert schon das Lesen. Haelt dagegen ein LESER eine SHARED-Sperre,
#   bleibt sie unbemerkt: eine nur lesende Verbindung stoert ihn nicht.
#   Ausgerechnet der haeufigste Fall - jemand liest noch - ist damit der, den
#   die Probe uebersah.
#
# Diese Datei enthaelt nur die Datenklasse (Grundregel 10). Die Messung steht
# in maintenance/cli_support.py.
#
# Version: v0.8.648 · Build: 648 · 2026-08-01
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

#: Die drei Zustaende. Als Zeichenketten und nicht als Wahrheitswerte, weil
#: genau die Zweiwertigkeit der Fehler war.
RUHIG = "ruhig"
BELEGT = "belegt"
NICHT_MESSBAR = "nicht_messbar"

ZUSTAENDE: Tuple[str, ...] = (RUHIG, BELEGT, NICHT_MESSBAR)


class ExklusivBefundError(Exception):
    """Ein Sperrbefund ist in sich unstimmig."""


@dataclass(frozen=True)
class ExklusivBefund:
    """
    Das Ergebnis einer Sperrprobe.

    zustand — einer aus ZUSTAENDE.
    grund   — Klartext. Bei NICHT_MESSBAR sagt er, WORAN es lag; ohne das
              waere der Zustand fuer den Betrieb nicht zu beheben.
    pfad    — die gepruefte Datei.
    """
    pfad: str
    zustand: str
    grund: str

    def __post_init__(self) -> None:
        if self.zustand not in ZUSTAENDE:
            raise ExklusivBefundError(
                "Unbekannter Zustand '%s' (zulaessig: %s)."
                % (self.zustand, ", ".join(ZUSTAENDE)))
        if not str(self.grund).strip():
            raise ExklusivBefundError(
                "Sperrbefund ohne Grund. Bei 'nicht messbar' ist er das "
                "Einzige, woraus der Betrieb ableiten kann, was zu tun ist.")

    @property
    def ist_ruhig(self) -> bool:
        """
        NUR 'ruhig' ist Ruhe.

        AUSDRUECKLICH: 'nicht messbar' ist hier False. Das ist die ganze
        Behebung von 96f2b18f in einer Zeile - vorher hat der unmessbare Fall
        als Ruhe gezaehlt, und der Wartungsmodus gab ein Fenster frei, dessen
        Nachweis nie erbracht worden war.
        """
        return self.zustand == RUHIG

    @property
    def marke(self) -> str:
        """Sechs Zeichen fuer die Konsolenausgabe - eine Spalte, die steht."""
        return {RUHIG: "FREI  ", BELEGT: "BELEGT",
                NICHT_MESSBAR: "UNKLAR"}[self.zustand]

    def als_tupel(self) -> Tuple[bool, str]:
        """
        Die alte Form '(ok, grund)' - fuer Aufrufer, die es noch so erwarten.

        'nicht messbar' wird dabei zu False. Das ist die sichere Seite: Wer
        die Dreiwertigkeit nicht auswertet, bekommt lieber ein 'nicht frei'
        zu viel als eine Ruhe, die nie gemessen wurde.
        """
        return (self.ist_ruhig, self.grund)

# =============================================================================
# management/search/index_ort.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche
# =============================================================================
# ZWECK: Beantwortet die Frage "wo liegt der Suchindex?" — EINMAL, fuer das
#   Werkzeug (index_cli) UND fuer den Verwaltungsserver.
#
# =============================================================================
# DER BEFUND, DER ZU DIESER DATEI GEFUEHRT HAT (Ticket 5a7e93b1)
#
# Bis Build 718 gab es fuer denselben Index ZWEI Vorgabewerte:
#   * management/search/index_cli.py: STANDARD_INDEX_PFAD = "./data/search_index.db"
#   * management/server/management_app.py: der gerechnete Ort NEBEN der
#     coordinator.db (Path(db_path).parent / "search_index.db").
# und NUR der Server las dabei 'paths.search_index_db'.
#
# Der Befund steht seit Build 641 woertlich im Quelltext von index_cli.py:
# "Wer den Index per config.yaml verlegt, verlegt ihn also nur fuer den
# Server." Das Werkzeug schrieb weiter an die alte Stelle.
#
# GEMESSEN am 13.08.2026: Bei unveraenderter config.yaml sind beide
# Vorgabewerte IDENTISCH ('./data/search_index.db' gegen
# './data' + '/search_index.db'). Sie laufen erst auseinander, sobald
# 'paths.coordinator_db' verlegt ist — also genau in dem Betrieb, fuer den
# die Verlegbarkeit gedacht war. Deshalb war der Fehler so lange unsichtbar.
#
# =============================================================================
# WARUM DIE UMZUGSMELDUNG DAZUGEHOERT
#
# Mit der Vereinheitlichung kann sich der Ort auf einer Anlage AENDERN, auf
# der die coordinator.db verlegt ist. Der bestehende Index bleibt dabei
# unangetastet liegen — er wird nur nicht mehr gefunden. Ohne Meldung sieht
# das aus wie eine kaputte Volltextsuche: sie liefert nichts, und niemand
# weiss warum.
#
# Der Index ist KEIN Beweismittel (er laesst sich jederzeit neu aufbauen), es
# geht hier also nicht um Beweisverlust. Es geht darum, dass ein Leerbefund
# und ein umgezogener Index nicht gleich aussehen duerfen — dieselbe
# Ueberlegung wie ueberall sonst (Grundregel 1).
#
# ES WIRD NICHTS VERSCHOBEN UND NICHTS GELOESCHT. Das Werkzeug sagt, was es
# sieht; das Verschieben oder Neuaufbauen entscheidet ein Mensch.
#
# Abhaengigkeiten: pathlib, logging — Stdlib; core.config_loader.
# Version: v0.8.720 · Build: 720 · 2026-08-14
# =============================================================================

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

#: Der Konfigurationsschluessel des Suchindex — an EINER Stelle.
SCHLUESSEL = "paths.search_index_db"


class IndexOrt:
    """
    Loest den Ort des Suchindex auf und erkennt einen moeglichen Umzug.

    REIN LESEND: legt nichts an, verschiebt nichts, loescht nichts.
    """

    def __init__(self, pfad: str, herkunft: str,
                 alt_pfad: Optional[str] = None) -> None:
        """
        pfad     — der geltende Ort.
        herkunft — woher er stammt ('argument' | 'config.yaml' | 'vorgabe').
                   Sie wandert in die Protokollzeile; ein Werkzeug, das seine
                   Werte belegen soll, darf die Herkunft nicht verschweigen.
        alt_pfad — der Ort, an dem der Index VOR Build 720 gelegen haette,
                   sofern er ein anderer ist. None heisst: kein Umzug moeglich.
        """
        self.pfad = pfad
        self.herkunft = herkunft
        self.alt_pfad = alt_pfad

    # ---------------------------------------------------------------- Bau
    @classmethod
    def bestimmen(cls, *, arg_wert: Optional[str] = None,
                  coordinator_db: Optional[str] = None) -> "IndexOrt":
        """
        Die Vorrangregel des Projekts, unveraendert:
            CLI-Argument  >  config.yaml  >  Coded Default

        coordinator_db — nur fuer die Umzugserkennung: der ALTE Ort des
        Servers war 'neben der coordinator.db'. Ohne Angabe wird der alte
        Ort des WERKZEUGS angenommen (das fruehere STANDARD_INDEX_PFAD, das
        mit dem heutigen Vorgabewert uebereinstimmt — dann gibt es nichts zu
        melden).
        """
        from core.config_loader import ConfigLoader, coded_default

        vorgabe = coded_default(SCHLUESSEL)

        if arg_wert:
            pfad, herkunft = str(arg_wert), "argument"
        else:
            aus_datei = None
            try:
                loader = ConfigLoader()
                # NUR was WIRKLICH in der Datei steht, zaehlt als 'aus
                # config.yaml' - get() lieferte sonst auch den Vorgabewert
                # und die Herkunftsangabe waere falsch (Build 638).
                if loader.stammt_aus_datei(SCHLUESSEL):
                    aus_datei = loader.get(SCHLUESSEL)
            except Exception as exc:            # pragma: no cover
                # KEIN Abbruch: der Suchindex ist ein Hilfsmittel. Der
                # Rueckfall wird aber protokolliert und nicht verschluckt.
                logger.warning(
                    "%s nicht aus config.yaml lesbar (%s) - Vorgabewert %s.",
                    SCHLUESSEL, exc, vorgabe)
            if aus_datei:
                pfad, herkunft = str(aus_datei), "config.yaml"
            else:
                pfad, herkunft = str(vorgabe), "vorgabe"

        alt = None
        if coordinator_db:
            frueher = str(Path(coordinator_db).parent / "search_index.db")
            if not cls._gleich(frueher, pfad):
                alt = frueher
        return cls(pfad, herkunft, alt)

    # ------------------------------------------------------------ Meldung
    def umzugsmeldung(self, *, existiert=None) -> Optional[str]:
        """
        Klartext, wenn am ALTEN Ort ein Index liegt und am neuen nicht —
        sonst None.

        'existiert' ist injizierbar (Callable pfad -> bool), damit der Fall
        ohne Dateisystem pruefbar ist. Ohne Angabe wird das Dateisystem
        gefragt.

        DIE BEDINGUNG IST ABSICHTLICH ENG. Gemeldet wird nur die Lage, in der
        die Meldung etwas nuetzt: alt vorhanden, neu nicht. Liegt an beiden
        Orten einer, ist der neue in Gebrauch und der alte eine Altlast —
        darueber hier zu reden waere Rauschen. Liegt nirgends einer, ist
        schlicht noch nicht indiziert worden.
        """
        if not self.alt_pfad:
            return None
        da = existiert if existiert is not None else (
            lambda p: Path(p).exists())
        if not da(self.alt_pfad) or da(self.pfad):
            return None
        return (
            "HINWEIS ZUM SUCHINDEX: Der Index wird ab Build 720 unter %s "
            "gefuehrt (Herkunft: %s). Am bisherigen Ort %s liegt noch eine "
            "Datei, am neuen noch keine. Es wurde NICHTS verschoben und "
            "NICHTS geloescht - bis zum naechsten Aufbau des Index findet "
            "die Volltextsuche nichts. Entweder die alte Datei an den neuen "
            "Ort kopieren oder den Index neu aufbauen."
            % (self.pfad, self.herkunft, self.alt_pfad))

    def protokollzeile(self) -> str:
        """Eine Zeile fuer das Herkunftsprotokoll der Werkzeuge."""
        return "search_index_db = %s (%s)" % (self.pfad, self.herkunft)

    # ------------------------------------------------------------- intern
    @staticmethod
    def _gleich(a: str, b: str) -> bool:
        """
        Zwei Pfadangaben auf denselben Ort pruefen.

        './data/x.db' und 'data/x.db' meinen dasselbe; ein reiner
        Zeichenkettenvergleich haette hier eine Umzugsmeldung erzeugt, wo
        gar nichts umzieht. resolve() ohne strict: die Datei muss dafuer
        nicht existieren.
        """
        try:
            return Path(a).resolve() == Path(b).resolve()
        except OSError:                         # pragma: no cover
            return str(a) == str(b)

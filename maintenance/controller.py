# =============================================================================
# maintenance/controller.py
# IT-Forensisches Ermittlungswerkzeug — Wartungsmodus (Build 436, Webserver)
# =============================================================================
# Zweck:
#   Reine Entscheidungslogik des Wartungsmodus fuer EINEN Server. Liest den
#   Fensterzustand (ueber das getestete Dateiprotokoll) und liefert die naechste
#   auszufuehrende Aktion. KEINE Seiteneffekte auf Server/DB — die fuehrt der
#   Aufrufer (Poller-Callbacks) aus. So bleibt die Logik vollstaendig testbar.
#
# Zwei Rollen:
#   * Normalserver: laeuft; erscheint ein Fenster -> QUIESCE (pause|beenden);
#     verschwindet das Fenster -> RESUME, oder (Versions-Waechter) BEENDEN, wenn
#     der eigene Build kleiner als min_build des Fensters ist.
#   * --maintenance-Test-Server: laeuft normal (als gaebe es keine Wartung),
#     beendet sich aber bei Fensterende (SELBSTBEENDIGUNG) oder auf Kill (KILL).
#
# Version: v0.7.436 · Build: 436 · 2026-07-19
# =============================================================================

from __future__ import annotations

from typing import Optional

from maintenance.paths import MaintenancePaths
from maintenance.server_registration import ServerRegistration
from maintenance.window_flag import WindowFlag


class Aktion:
    """Moegliche Aktionen, die der Controller vorgibt."""
    KEINE = "keine"
    QUIESCE_PAUSE = "quiesce_pause"
    QUIESCE_BEENDEN = "quiesce_beenden"
    RESUME = "resume"
    BEENDEN_VERSIONSWAECHTER = "beenden_versionswaechter"
    SELBSTBEENDIGUNG_FENSTERENDE = "selbstbeendigung_fensterende"
    KILL = "kill"


class MaintenanceController:
    """Entscheidet, was ein Server als naechstes tun soll (reine Logik)."""

    LAEUFT = "laeuft"
    QUIESCED = "quiesced"

    def __init__(self, paths: MaintenancePaths, own_build: int,
                 im_wartungsmodus_gestartet: bool = False,
                 registration: Optional[ServerRegistration] = None) -> None:
        self._paths = paths
        self._own_build = int(own_build)
        self._im_wartungsmodus = bool(im_wartungsmodus_gestartet)
        self._registration = registration
        self._state = self.LAEUFT
        self._quiesced_min_build = 0

    @property
    def state(self) -> str:
        return self._state

    def naechste_aktion(self, jetzt: Optional[int] = None) -> str:
        fenster = WindowFlag.aktives_fenster(self._paths, jetzt)

        # --- Rolle: --maintenance-Test-Server -------------------------------
        if self._im_wartungsmodus:
            if fenster is None:
                # Fenster beendet -> Test-Server hat seinen Zweck erfuellt.
                return Aktion.SELBSTBEENDIGUNG_FENSTERENDE
            if (self._registration is not None
                    and self._registration.ist_kill_angefordert(self._paths)):
                return Aktion.KILL
            return Aktion.KEINE

        # --- Rolle: Normalserver --------------------------------------------
        if self._state == self.LAEUFT:
            if fenster is not None:
                self._quiesced_min_build = fenster.min_build
                self._state = self.QUIESCED
                return (Aktion.QUIESCE_BEENDEN
                        if fenster.bei_aktivierung == "beenden"
                        else Aktion.QUIESCE_PAUSE)
            return Aktion.KEINE

        # self._state == QUIESCED
        if fenster is None:
            self._state = self.LAEUFT
            if self._own_build < self._quiesced_min_build:
                # Versions-Waechter: keine alte Version auf neue Daten lassen.
                return Aktion.BEENDEN_VERSIONSWAECHTER
            return Aktion.RESUME
        return Aktion.KEINE

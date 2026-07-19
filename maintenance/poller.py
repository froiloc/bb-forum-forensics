# =============================================================================
# maintenance/poller.py
# IT-Forensisches Ermittlungswerkzeug — Wartungsmodus (Build 436, Webserver)
# =============================================================================
# Zweck:
#   Hintergrund-Thread, der periodisch den MaintenanceController befragt und die
#   passende Aktion ueber Callbacks ausloest. Der Poller selbst enthaelt KEINE
#   Wartungslogik — er ist nur das Uhrwerk. Dadurch ist die Logik (Controller)
#   getrennt und rein testbar; der Poller wird ueber tick() ohne echten Thread
#   geprueft.
#
# Version: v0.7.436 · Build: 436 · 2026-07-19
# =============================================================================

from __future__ import annotations

import threading
from typing import Callable, Dict, Optional

from maintenance.controller import Aktion, MaintenanceController


class MaintenancePoller:
    """Periodischer Poller, der Controller-Aktionen ueber Callbacks ausfuehrt."""

    def __init__(self, controller: MaintenanceController, intervall_s: float,
                 aktionen: Dict[str, Callable[[], None]],
                 logger=None,
                 on_touch: Optional[Callable[[], None]] = None) -> None:
        self._controller = controller
        self._intervall = float(intervall_s)
        self._aktionen = dict(aktionen)
        self._logger = logger
        self._on_touch = on_touch
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # --- Steuerung -----------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="maintenance-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # --- Kernschritt (ohne Thread testbar) ----------------------------------
    def tick(self) -> str:
        """Fuehrt genau einen Poll-Zyklus aus und liefert die Aktion zurueck."""
        if self._on_touch is not None:
            try:
                self._on_touch()
            except Exception as exc:                       # pragma: no cover
                self._warn("Praesenz-Touch fehlgeschlagen: %s", exc)

        aktion = self._controller.naechste_aktion()
        if aktion == Aktion.KEINE:
            return aktion

        cb = self._aktionen.get(aktion)
        if cb is None:
            self._warn("Keine Callback fuer Aktion '%s' — uebersprungen "
                       "(gemeldet, nicht still).", aktion)
            return aktion
        cb()
        return aktion

    # --- interne Schleife ----------------------------------------------------
    def _loop(self) -> None:
        while not self._stop.wait(self._intervall):
            try:
                self.tick()
            except Exception as exc:                       # pragma: no cover
                self._warn("Poll-Zyklus fehlgeschlagen: %s", exc)

    def _warn(self, msg: str, *args) -> None:
        if self._logger is not None:
            self._logger.warning(msg, *args)

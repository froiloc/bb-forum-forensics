# =============================================================================
# maintenance/gate.py
# IT-Forensisches Ermittlungswerkzeug — Wartungsmodus (Build 436, Webserver)
# =============================================================================
# Zweck:
#   Request-Gate mit Drain fuer den mehrthreadigen Webserver
#   (ForensicHTTPServer = ThreadingMixIn). Waehrend einer Wartung muessen die
#   DB-Verbindungen geschlossen werden (Sperren freigeben). Das darf aber erst
#   geschehen, wenn KEIN Handler-Thread mehr die DB benutzt.
#
# Verfahren:
#   * Jeder Request ruft am Anfang enter() auf. Ist das Gate blockiert
#     (Wartung), liefert enter() False -> der Handler antwortet mit HTTP 503 und
#     fasst die DB NICHT an. Sonst wird ein In-Flight-Zaehler erhoeht.
#   * leave() im finally senkt den Zaehler und weckt Warter.
#   * block_and_drain() setzt 'blockiert' (neue Requests -> 503) und wartet, bis
#     der In-Flight-Zaehler 0 ist (laufende Requests sind ausgetrudelt). Erst
#     danach ist es sicher, das Bundle zu schliessen.
#   * unblock() gibt den Betrieb wieder frei (nach dem Wiederoeffnen des Bundles).
#
# Grenze (bewusst dokumentiert): Ein langlebiger Request (z.B. eine offene
#   SSE-Verbindung fuer Editor-Locks) trudelt nicht von selbst aus. block_and_drain
#   kehrt dann nach dem Timeout mit False zurueck; der Aufrufer protokolliert das
#   und faehrt fort. Fuer Operationen, die garantierten Exklusivzugriff brauchen,
#   ist daher 'bei_aktivierung=beenden' der verlaessliche Weg.
#
# Version: v0.7.436 · Build: 436 · 2026-07-19
# =============================================================================

from __future__ import annotations

import threading
import time
from typing import Optional


class MaintenanceGate:
    """Thread-sicheres Request-Gate mit Drain."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._blockiert = False
        self._inflight = 0

    def enter(self) -> bool:
        """
        Versucht, einen Request zuzulassen.
        Returns True (zugelassen, In-Flight erhoeht) oder False (Wartung aktiv).
        """
        with self._cond:
            if self._blockiert:
                return False
            self._inflight += 1
            return True

    def leave(self) -> None:
        """Beendet einen zugelassenen Request; weckt ggf. den Drain-Warter."""
        with self._cond:
            if self._inflight > 0:
                self._inflight -= 1
            if self._inflight == 0:
                self._cond.notify_all()

    def block_and_drain(self, timeout: Optional[float] = None) -> bool:
        """
        Blockiert neue Requests und wartet, bis alle laufenden ausgetrudelt sind.

        Returns:
            True  = In-Flight ist 0 (sauber ausgetrudelt).
            False = Timeout erreicht, es liefen noch Requests (Aufrufer meldet das).
        """
        with self._cond:
            self._blockiert = True
            frist = None if timeout is None else time.monotonic() + timeout
            while self._inflight > 0:
                if frist is None:
                    self._cond.wait()
                else:
                    rest = frist - time.monotonic()
                    if rest <= 0:
                        return False
                    self._cond.wait(timeout=rest)
            return True

    def unblock(self) -> None:
        """Gibt den Betrieb wieder frei (neue Requests werden wieder zugelassen)."""
        with self._cond:
            self._blockiert = False

    def is_blocked(self) -> bool:
        with self._cond:
            return self._blockiert

    @property
    def inflight(self) -> int:
        with self._cond:
            return self._inflight

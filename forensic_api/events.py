# =============================================================================
# forensic_api/events.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 3: Forensischer Werkzeugbalken
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/events (GET, text/event-stream)
#   SSE-Stream für den Support-Status-Indikator in Sektion 5 der Toolbar.
#   Sendet im konfigurierbaren Intervall den aktuellen Support-Status
#   aus coordinator.db an den verbundenen Browser (§11.5 Bauplan).
#
# Request:
#   GET /_forensic/events
#   (Browser hält Verbindung offen via EventSource-API)
#
# Events:
#   event: support_status
#   data: {"support_active": true, "support_user": "h067890", "since": 1744300000000}
#
#   event: support_status
#   data: {"support_active": false, "support_user": null, "since": null}
#
# Datenquelle:
#   coordinator.db → investigators (is_support=1) JOIN scrape_jobs (status='running').
#   Implementiert in db/coordinator_db.get_support_status() → SupportStatusRecord.
#   Liegt coordinator.db nicht vor oder ist kein Support-Nutzer aktiv, wird
#   support_active=false gesendet — kein Absturz, kein stilles Versagen (Grundregel 1).
#
# HTTP-Verhalten:
#   - Content-Type: text/event-stream; charset=utf-8
#   - Cache-Control: no-cache
#   - Verbindung bleibt offen (keine Content-Length)
#   - Transfer-Encoding: chunked (via flush nach jedem Event)
#   - Bei Verbindungsabbruch des Clients: sauberes Beenden der Schleife
#
# Konfiguration:
#   SSE_INTERVAL_SEC (config.yaml): Sendeintervall in Sekunden. Default: 15.
#
# Neue Datei — Baustelle 3, vierte Server-Erweiterung (§11.5 Bauplan).
# Version: v0.1.0 · Build: 001 · 2026-04-13
# =============================================================================

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

# Standard-Sendeintervall in Sekunden (überschreibbar via config.yaml)
_DEFAULT_INTERVAL_SEC = 15


def _get_support_status(bundle: "DatabaseBundle") -> dict:
    """
    Liest den aktuellen Support-Status aus coordinator.db.

    Gibt {"support_active": False, "support_user": None, "since": None} zurück
    wenn kein Support-Nutzer aktiv ist oder coordinator_db nicht verfügbar.

    Returns:
        Dict mit Schlüsseln: support_active, support_user, since
    """
    empty = {"support_active": False, "support_user": None, "since": None}

    if bundle.coordinator is None:
        return empty

    try:
        # coordinator_db liefert Support-Status über get_support_status().
        # Rückgabe ist ein SupportStatusRecord-Dataclass (db/coordinator_db.py).
        if hasattr(bundle.coordinator, "get_support_status"):
            status = bundle.coordinator.get_support_status()
            if status.active:
                return {
                    "support_active": True,
                    "support_user":   status.username,
                    "since":          status.since_ms,
                }
    except Exception as exc:
        logger.warning("Support-Status konnte nicht gelesen werden: %s", exc)

    return empty


class EventsEndpoint:
    """
    Endpunkt /_forensic/events — SSE-Stream für Support-Status.

    Der Stream sendet im konfigurierbaren Intervall den Support-Status.
    Die HTTP-Verbindung bleibt so lange offen, bis der Client die Verbindung
    trennt (EventSource-Browser-API). Das automatische Browser-Reconnect
    bei Verbindungsabbruch ist in EventSource eingebaut — kein zusätzlicher Code.
    """

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        self._bundle   = bundle
        self._context  = context
        self._interval = int(getattr(config, "get", lambda k, d: d)("sse_interval_sec", _DEFAULT_INTERVAL_SEC))

    def handle(
        self,
        handler: "ForensicRequestHandler",
    ) -> None:
        """
        Verarbeitet GET /_forensic/events

        Öffnet einen SSE-Stream. Sendet mindestens ein Event sofort,
        danach alle self._interval Sekunden.

        Args:
            handler: ForensicRequestHandler-Instanz.
        """
        wfile = handler.wfile

        # SSE-Header senden
        try:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
            handler.send_header("Cache-Control", "no-cache")
            handler.send_header("X-Accel-Buffering", "no")  # Nginx: Buffering deaktivieren
            handler.send_header("Connection", "keep-alive")
            handler.end_headers()
        except Exception as exc:
            logger.debug("SSE-Stream: Header konnte nicht gesendet werden: %s", exc)
            return

        # Kommentar als Keepalive-Basis senden (Browser erwartet mindestens ein Byte)
        def _send_event(event_name: str, data: dict) -> bool:
            """Sendet ein SSE-Event. Gibt False zurück bei Verbindungsabbruch."""
            try:
                line = (
                    f"event: {event_name}\n"
                    f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                )
                wfile.write(line.encode("utf-8"))
                wfile.flush()
                return True
            except (BrokenPipeError, ConnectionResetError, OSError):
                logger.debug("SSE-Stream: Client hat Verbindung getrennt")
                return False

        # Sofort ersten Status senden
        status = _get_support_status(self._bundle)
        if not _send_event("support_status", status):
            return

        # Polling-Schleife
        while True:
            # Intervall in 1-Sekunden-Schritten abwarten (ermöglicht sauberes Beenden)
            for _ in range(self._interval):
                time.sleep(1)

            status = _get_support_status(self._bundle)
            if not _send_event("support_status", status):
                return

        # Hinweis: Diese Methode kehrt erst zurück wenn der Client die Verbindung
        # trennt oder ein Fehler auftritt. Der HTTP-Server muss dafür sorgen, dass
        # dieser Handler in einem eigenen Thread läuft (nicht blockend).

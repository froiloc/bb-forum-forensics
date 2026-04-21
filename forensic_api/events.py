# =============================================================================
# forensic_api/events.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 3: Forensischer Werkzeugbalken
# Erweitert in Baustelle 4: Nutzerinfo-Tab
# =============================================================================
# Zweck:
#   Endpunkt GET /_forensic/events (text/event-stream).
#   SSE-Stream für Support-Status-Indikator (Baustelle 3) und
#   Nutzerinfo-Tab-Events (Baustelle 4).
#
# Event-Typen:
#   support_status         (B3) — Support-Benutzer aktiv/inaktiv
#   annotation_added       (B4) — Neue Annotation, inkl. Kategorie
#   report_updated         (B4) — Neuer Paragraph im Berichtsfeld
#   status_changed         (B4) — Ermittlungsstatus geändert
#   editor_lock_acquired   (B4) — Editor-Lock erworben
#   editor_lock_released   (B4) — Editor-Lock freigegeben oder abgelaufen
#
# SSE-Client-ID (NEU Build 012):
#   Jede SSE-Verbindung erhält beim Aufbau eine eindeutige client_id (UUID).
#   Diese wird als erstes Event "client_id" an den Browser gesendet.
#   Der Browser verwendet sie bei acquire_lock, damit der Server bei
#   SSE-Verbindungsabriss den Lock automatisch freigeben kann (Schicht 2,
#   §8.6 Bauplan B4).
#
# Datenbankzugriff:
#   coordinator.db (READ-ONLY) — Support-Status
#   evidence_<uid>.db (READ/WRITE) — Lock-Freigabe bei Verbindungsabriss
#
# Version: v0.1.0 · Build: 012 · 2026-04-14
# =============================================================================

from __future__ import annotations

import json
import time
import uuid
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
    Gibt inaktiven Status zurück wenn coordinator_db nicht verfügbar.
    """
    empty = {"support_active": False, "support_user": None, "since": None}

    if bundle.coordinator is None:
        return empty

    try:
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
    Endpunkt /_forensic/events — SSE-Stream.

    Sendet im konfigurierbaren Intervall:
    - support_status (Baustelle 3)
    - editor_lock_acquired / editor_lock_released (Baustelle 4)

    Bei Verbindungsabriss: Editor-Lock des Clients automatisch freigeben
    (Schicht 2 des dreischichtigen Lock-Mechanismus, §8.6 Bauplan B4).

    Die Verbindung bleibt offen bis der Client trennt.
    Browser-seitiges automatisches Reconnect via EventSource-API.
    """

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        self._bundle   = bundle
        self._context  = context
        self._interval = int(
            getattr(config, "get", lambda k, d: d)("sse_interval_sec", _DEFAULT_INTERVAL_SEC)
        )

    def handle(
        self,
        handler: "ForensicRequestHandler",
        params: dict | None = None,
    ) -> None:
        """
        Verarbeitet GET /_forensic/events.
        Oeffnet SSE-Stream, sendet sofort erste Events, dann im Intervall.

        Args:
            handler: ForensicRequestHandler-Instanz.
            params:  URL-Query-Parameter (aus urllib.parse.parse_qs).
                     resume_lock_id: Lock-ID fuer SSE-Reconnect (V1).
        """
        wfile = handler.wfile

        # Eindeutige SSE-Client-ID fuer diesen Verbindungsaufbau (§8.6 Bauplan B4)
        client_id = str(uuid.uuid4())

        # V1: Resume-Lock — Browser reconnected nach SSE-Abriss und moechte
        # seinen Lock an die neue client_id binden.
        # Query-Parameter: ?resume_lock_id=<lock_id>
        # Beleg: Lock-System v2 V1, Projektgespraech 2026-04-21
        resume_lock_id = (params or {}).get("resume_lock_id", [None])[0]
        if resume_lock_id:
            username = self._context.username or f"uid_{self._context.user_id}"
            resumed = self._bundle.evidence.resume_lock(
                lock_id=resume_lock_id,
                locked_by=username,
                new_sse_client=client_id,
            )
            if resumed:
                logger.info(
                    "SSE-Resume: Lock wiederhergestellt fuer '%s' (lock_id=%s)",
                    username, resume_lock_id,
                )
            else:
                logger.debug(
                    "SSE-Resume: Lock nicht wiederherstellbar (lock_id=%s)",
                    resume_lock_id,
                )

        # SSE-Header senden
        try:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
            handler.send_header("Cache-Control", "no-cache")
            handler.send_header("X-Accel-Buffering", "no")
            handler.send_header("Connection", "keep-alive")
            handler.end_headers()
        except Exception as exc:
            logger.debug("SSE-Stream: Header konnte nicht gesendet werden: %s", exc)
            return

        def _send_event(event_name: str, data: dict) -> bool:
            """
            Sendet ein SSE-Event. Gibt False zurück bei Verbindungsabbruch.
            Formatierung nach RFC 8895: "event: ...\ndata: ...\n\n"
            """
            try:
                line = (
                    f"event: {event_name}\n"
                    f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                )
                wfile.write(line.encode("utf-8"))
                wfile.flush()
                return True
            except (BrokenPipeError, ConnectionResetError, OSError):
                logger.debug("SSE-Stream: Client hat Verbindung getrennt (client_id=%s)", client_id)
                return False

        # Sofort: Client-ID senden — Browser speichert sie für acquire_lock
        if not _send_event("client_id", {"client_id": client_id}):
            return

        # Sofort: ersten Support-Status senden
        status = _get_support_status(self._bundle)
        if not _send_event("support_status", status):
            self._cleanup_lock(client_id)
            return

        # Sofort: aktuellen Lock-Status senden (Fenster 3 informieren)
        self._send_lock_status(_send_event)

        # Letzten gesendeten Lock-Zustand merken — nur bei Aenderung senden.
        # Verhindert dass editor_lock_released periodisch gesendet wird
        # wenn schlicht kein Lock vorhanden ist.
        # Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-19
        _initial_lock = self._bundle.evidence.get_lock()
        _last_lock_id: str | None = _initial_lock.lock_id if _initial_lock else None

        # Warte-Event vom EvidenceDb — wird bei Lock-Aenderungen sofort gesetzt.
        # Beleg: Lock-System v2, Projektgespraech 2026-04-21
        lock_event = self._bundle.evidence.lock_change_event

        # Polling-Schleife
        try:
            while True:
                # Schlaeft interval Sekunden ODER wird sofort geweckt
                # wenn acquire_lock() / release_lock() aufgerufen wird.
                lock_event.wait(timeout=self._interval)

                # Lock-Zustand lesen, DANN Event loeschen.
                # Reihenfolge wichtig: zwischen clear() und get_lock() koennte
                # sonst eine Aenderung verloren gehen.
                current_lock = self._bundle.evidence.get_lock()
                lock_event.clear()

                # Support-Status senden
                status = _get_support_status(self._bundle)
                if not _send_event("support_status", status):
                    break

                # Lock-Status nur bei Aenderung senden
                current_lock_id = current_lock.lock_id if current_lock else None
                if current_lock_id != _last_lock_id:
                    _last_lock_id = current_lock_id
                    if not self._send_lock_status(_send_event):
                        break

                # V3: Takeover-Event senden falls pending
                # Beleg: Lock-System v2 V3, Projektgespraech 2026-04-21
                pending = getattr(
                    self._bundle.evidence, '_pending_takeover', None
                )
                if pending:
                    self._bundle.evidence._pending_takeover = None
                    if not _send_event("lock_takeover_request", pending):
                        break

                # V3: Takeover-Ergebnis senden (granted/denied)
                takeover_result = getattr(
                    self._bundle.evidence, '_takeover_result', None
                )
                if takeover_result:
                    self._bundle.evidence._takeover_result = None
                    if not _send_event("lock_takeover_result", takeover_result):
                        break

        finally:
            # Verbindung abgerissen: Lock des Clients freigeben (Schicht 2, §8.6 B4)
            self._cleanup_lock(client_id)

    def _send_lock_status(self, send_fn) -> bool:
        """
        Sendet den aktuellen Editor-Lock-Status.
        Gibt False zurueck wenn Verbindung abgebrochen ist.

        Defensiv gegen korrupte Altdatensaetze mit locked_at=NULL:
        int(None) wuerde TypeError werfen — wird abgefangen.
        Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-19
        """
        try:
            lock = self._bundle.evidence.get_lock()
            if lock and lock.locked_by and lock.lock_id:
                return send_fn(
                    "editor_lock_acquired",
                    {"locked_by": lock.locked_by, "lock_id": lock.lock_id},
                )
            else:
                return send_fn("editor_lock_released", {})
        except (TypeError, ValueError) as exc:
            # Korrupter Lock-Datensatz (z.B. locked_at=NULL) — als 'kein Lock' behandeln
            logger.warning("_send_lock_status: Korrupter Lock-Datensatz — bereinige: %s", exc)
            try:
                self._bundle.evidence._con.execute(
                    "DELETE FROM editor_locks WHERE locked_at IS NULL"
                )
                self._bundle.evidence._con.commit()
            except Exception:
                pass
            return send_fn("editor_lock_released", {})
        except Exception as exc:
            logger.warning("_send_lock_status: Fehler: %s", exc)
            return True  # Kein Verbindungsabbruch — anderer Fehler

    def _cleanup_lock(self, client_id: str) -> None:
        """
        Gibt den Editor-Lock frei, falls er von dieser SSE-Client-ID gehalten wird.
        Implementiert Schicht 2 des dreischichtigen Lock-Mechanismus (§8.6 Bauplan B4).
        """
        try:
            freed = self._bundle.evidence.release_lock_by_sse_client(client_id)
            if freed:
                logger.info(
                    "SSE-Verbindungsabriss: Editor-Lock freigegeben (client_id=%s)", client_id
                )
        except Exception as exc:
            logger.warning("_cleanup_lock: Fehler: %s", exc)

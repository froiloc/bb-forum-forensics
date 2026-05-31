# =============================================================================
# forensic_api/windows.py
# IT-Forensisches Ermittlungswerkzeug — Fenster-Registrierung
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/windows — Fenster melden sich beim Server an/ab.
#   Ermöglicht Navigation-Fallback wenn BroadcastChannel nicht greift
#   (z.B. verschiedene Browser-Profile, obwohl in der Praxis selten).
#
#   Unterstützte Rollen: 'main', 'userinfo', 'report'
#
# Methoden:
#   POST   — Fenster registrieren { role, window_id }
#   GET    — Aktive Fenster abfragen (als JSON-Liste)
#   DELETE — Fenster abmelden { window_id }
#
# Speicherung:
#   In-Memory (dict) — keine Persistenz nötig, da Registrierungen
#   nur für die Laufzeit des Servers relevant sind.
#   TTL: 60 Sekunden — Fenster müssen sich regelmäßig erneuern (Heartbeat).
#
# Build 173: Erstimplementierung.
# Beleg: Projektgespräch 2026-05-11
#
# Build 265 (2026-05-31):
#   - find_active_by_role(): liefert das erste aktive Fenster einer Rolle.
#     Wird von events.py genutzt um Duplikat-SSE-Verbindungen abzuweisen (HTTP 409).
#   - WindowRegistry._lock ist jetzt über get_lock() von außen zugreifbar
#     damit events.py atomic prüfen und eintragen kann.
#   Beleg: Projektgespräch 2026-05-31.
# =============================================================================

from __future__ import annotations

import json
import threading
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler

import logging
logger = logging.getLogger("forensic.forensic_api.windows")

# Erlaubte Rollen
_ALLOWED_ROLES = {"main", "userinfo", "report"}

# TTL in Sekunden: Fenster müssen sich innerhalb dieser Zeit erneuern
_WINDOW_TTL = 60


def _json_ok(data: dict) -> bytes:
    return json.dumps({"ok": True, **data}).encode("utf-8")


def _json_err(msg: str) -> bytes:
    return json.dumps({"ok": False, "error": msg}).encode("utf-8")


class WindowRegistry:
    """
    In-Memory-Registrierung aktiver Browser-Fenster.

    Thread-sicher via Lock.
    Einträge haben einen TTL — abgelaufene werden beim nächsten Zugriff bereinigt.

    Beleg: Projektgespräch 2026-05-11
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # { window_id: { role, registered_at, last_seen } }
        self._windows: dict[str, dict] = {}

    def register(self, window_id: str, role: str) -> None:
        """Fenster registrieren oder Zeitstempel erneuern."""
        now = time.time()
        with self._lock:
            self._windows[window_id] = {
                "window_id":     window_id,
                "role":          role,
                "registered_at": self._windows.get(window_id, {}).get(
                    "registered_at", now
                ),
                "last_seen":     now,
            }

    def unregister(self, window_id: str) -> bool:
        """Fenster abmelden. Gibt True zurück wenn es existierte."""
        with self._lock:
            return self._windows.pop(window_id, None) is not None

    def list_active(self) -> list[dict]:
        """Aktive (nicht abgelaufene) Fenster als Liste zurückgeben."""
        now = time.time()
        with self._lock:
            # Abgelaufene Einträge bereinigen
            expired = [
                wid for wid, w in self._windows.items()
                if now - w["last_seen"] > _WINDOW_TTL
            ]
            for wid in expired:
                del self._windows[wid]
                logger.debug("WindowRegistry: Fenster '%s' abgelaufen und entfernt", wid)

            return [
                {
                    "window_id":     w["window_id"],
                    "role":          w["role"],
                    "registered_at": int(w["registered_at"]),
                    "last_seen":     int(w["last_seen"]),
                }
                for w in self._windows.values()
            ]


    def find_active_by_role(self, role: str) -> Optional[dict]:
        """
        Gibt das erste aktive Fenster mit der angegebenen Rolle zurück,
        oder None wenn keins gefunden.

        Wird von events.py verwendet um zu prüfen ob bereits eine
        SSE-Verbindung für diese Rolle besteht (Duplikat-Schutz).
        Beleg: Projektgespräch 2026-05-31.
        """
        now = time.time()
        with self._lock:
            for wid, w in self._windows.items():
                if w["role"] == role and (now - w["last_seen"] <= _WINDOW_TTL):
                    return {
                        "window_id":     wid,
                        "role":          w["role"],
                        "registered_at": int(w["registered_at"]),
                        "last_seen":     int(w["last_seen"]),
                    }
        return None

    @property
    def lock(self) -> threading.Lock:
        """Zugriff auf den internen Lock fuer atomare check-and-set Operationen."""
        return self._lock


# Globale Registry-Instanz (Singleton pro Prozess)
_registry = WindowRegistry()


def get_registry() -> WindowRegistry:
    """Gibt die globale WindowRegistry-Instanz zurück.
    Beleg: Projektgespräch 2026-05-31.
    """
    return _registry


class WindowsEndpoint:
    """
    Endpunkt /_forensic/windows.

    GET    — Aktive Fenster abfragen
    POST   — Fenster registrieren / Heartbeat senden
    DELETE — Fenster abmelden

    Beleg: Projektgespräch 2026-05-11
    """

    def handle(
        self,
        handler: "ForensicRequestHandler",
        method: str,
        body: Optional[bytes],
    ) -> None:
        if method == "GET":
            self._handle_get(handler)
        elif method == "POST":
            self._handle_post(handler, body)
        elif method == "DELETE":
            self._handle_delete(handler, body)
        else:
            handler.send_response_body(
                405, b"Method Not Allowed",
                content_type="text/plain",
            )

    def _handle_get(self, handler: "ForensicRequestHandler") -> None:
        """Aktive Fenster als JSON-Liste zurückgeben."""
        windows = _registry.list_active()
        body = json.dumps({"ok": True, "windows": windows}).encode("utf-8")
        handler.send_response_body(
            200, body,
            content_type="application/json; charset=utf-8",
            extra_headers={"Cache-Control": "no-store"},
        )
        logger.debug("/_forensic/windows GET: %d aktive Fenster", len(windows))

    def _handle_post(
        self, handler: "ForensicRequestHandler", body: Optional[bytes]
    ) -> None:
        """Fenster registrieren oder Heartbeat erneuern."""
        try:
            data = json.loads(body or b"{}")
        except json.JSONDecodeError:
            handler.send_response_body(
                400, _json_err("Ungültiges JSON"),
                content_type="application/json; charset=utf-8",
            )
            return

        window_id = str(data.get("window_id", "")).strip()
        role      = str(data.get("role", "")).strip()

        if not window_id:
            handler.send_response_body(
                400, _json_err("window_id erforderlich"),
                content_type="application/json; charset=utf-8",
            )
            return

        if role not in _ALLOWED_ROLES:
            handler.send_response_body(
                400, _json_err(f"Ungültige Rolle '{role}'. Erlaubt: {sorted(_ALLOWED_ROLES)}"),
                content_type="application/json; charset=utf-8",
            )
            return

        _registry.register(window_id, role)
        logger.debug(
            "/_forensic/windows POST: Fenster '%s' (Rolle '%s') registriert",
            window_id, role,
        )
        handler.send_response_body(
            200, _json_ok({"window_id": window_id, "role": role, "ttl": _WINDOW_TTL}),
            content_type="application/json; charset=utf-8",
        )

    def _handle_delete(
        self, handler: "ForensicRequestHandler", body: Optional[bytes]
    ) -> None:
        """Fenster abmelden."""
        try:
            data = json.loads(body or b"{}")
        except json.JSONDecodeError:
            handler.send_response_body(
                400, _json_err("Ungültiges JSON"),
                content_type="application/json; charset=utf-8",
            )
            return

        window_id = str(data.get("window_id", "")).strip()
        if not window_id:
            handler.send_response_body(
                400, _json_err("window_id erforderlich"),
                content_type="application/json; charset=utf-8",
            )
            return

        removed = _registry.unregister(window_id)
        logger.debug(
            "/_forensic/windows DELETE: Fenster '%s' %s",
            window_id, "entfernt" if removed else "nicht gefunden",
        )
        handler.send_response_body(
            200, _json_ok({"window_id": window_id, "removed": removed}),
            content_type="application/json; charset=utf-8",
        )

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
#
# Build 267 (2026-05-31):
#   - Separates _active_sse_roles-Dict in WindowRegistry (role → client_id).
#     claim_sse_role() / release_sse_role() werden von events.py
#     beim Stream-Start bzw. im finally-Block aufgerufen.
#     find_active_by_role() prüft nur noch _active_sse_roles, nicht mehr
#     den Fenster-Heartbeat. Verhindert Falsch-Positiv nach Tab-Schließen.
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

# Build 326: TTL fuer aktive SSE-Rollen (Selbstheilung gegen geleakte Rollen).
# Ein lebender SSE-Stream frischt seinen Rolleneintrag pro Poll-Iteration
# (<= _DEFAULT_INTERVAL_SEC = 15s, events.py) via touch_sse_role() auf. Bleibt die
# Auffrischung aus (ungrazilder Disconnect, Grace-Pfad lief nicht, Prozess weg),
# gilt der Eintrag nach _SSE_ROLE_TTL als verwaist und wird beim naechsten Zugriff
# automatisch freigegeben -> das naechste Fenster kann die Rolle uebernehmen.
# INVARIANTE: _SSE_ROLE_TTL MUSS groesser als SSE-Poll-Intervall (15s) + Grace (5s)
# sein, sonst wuerde ein noch lebender, nur langsamer Stream faelschlich verdraengt.
# 60s (= 4x Intervall, konsistent mit _WINDOW_TTL) haelt sicheren Abstand.
# Beleg: Live-Diagnose 2026-07-07 — geleakte Rolle 'main' (client_id d12ae68a)
# blockierte jeden Preflight dauerhaft mit HTTP 409 (kein Grace-Release erfolgt).
_SSE_ROLE_TTL = 60


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
        # { role: client_id } — aktive SSE-Verbindungen pro Rolle.
        # Wird von events.py via claim_sse_role() / release_sse_role()
        # gepflegt. Unabhängig vom Fenster-Heartbeat-TTL.
        # Beleg: Projektgespräch 2026-05-31.
        self._active_sse_roles: dict[str, str] = {}
        # Build 326: { role: last_seen (time.time()) } — Lebendigkeits-Zeitstempel
        # der aktiven SSE-Rolle, parallel zu _active_sse_roles gepflegt
        # (claim/touch/release). Ermoeglicht Selbstheilung geleakter Rollen:
        # ein lebender Stream frischt via touch_sse_role() auf; bleibt das aus,
        # gilt der Eintrag nach _SSE_ROLE_TTL als verwaist (siehe dort).
        self._sse_role_seen: dict[str, float] = {}

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

            # Build 326: verwaiste SSE-Rollen mitbereinigen, damit sse_active
            # unten nicht falsch-positiv ist (Konsistenz mit find_active_by_role).
            for _role in [r for r in self._sse_role_seen
                          if (now - self._sse_role_seen[r]) > _SSE_ROLE_TTL]:
                self._drop_stale_sse_role(_role)

            # sse_active: True wenn fuer diese Rolle ein aktiver SSE-Stream
            # laeuft (_active_sse_roles). Wird von der Toolbar genutzt um
            # zu entscheiden ob Fokussieren oder Neu-Oeffnen.
            # Beleg: Projektgespräch 2026-05-31.
            return [
                {
                    "window_id":     w["window_id"],
                    "role":          w["role"],
                    "registered_at": int(w["registered_at"]),
                    "last_seen":     int(w["last_seen"]),
                    "sse_active":    w["role"] in self._active_sse_roles,
                }
                for w in self._windows.values()
            ]


    def _sse_role_is_stale(self, role: str) -> bool:
        """
        Build 326: True, wenn fuer die Rolle ein Eintrag existiert, dessen
        letzter Lebendigkeits-Zeitstempel aelter als _SSE_ROLE_TTL ist
        (geleakte Rolle — der Stream hat sie nie via release_sse_role
        freigegeben und frischt sie nicht mehr auf).
        MUSS unter self._lock aufgerufen werden.
        """
        seen = self._sse_role_seen.get(role)
        if seen is None:
            # Kein Zeitstempel: entweder Rolle frei oder (Alt-Eintrag ohne
            # Zeitstempel) — nicht als stale werten, um Live-Streams nicht zu
            # verdraengen. claim/touch setzen den Zeitstempel stets.
            return False
        return (time.time() - seen) > _SSE_ROLE_TTL

    def _drop_stale_sse_role(self, role: str) -> None:
        """
        Build 326: Entfernt einen als verwaist erkannten Rolleneintrag
        (beide Dicts). MUSS unter self._lock aufgerufen werden.
        """
        cid = self._active_sse_roles.pop(role, None)
        self._sse_role_seen.pop(role, None)
        if cid is not None:
            logger.warning(
                "SSE-Rolle '%s' als verwaist erkannt (kein Heartbeat > %ds) — "
                "automatisch freigegeben (war client_id=%s).",
                role, _SSE_ROLE_TTL, cid,
            )

    def find_active_by_role(self, role: str) -> Optional[dict]:
        """
        Gibt einen Stub-Dict zurueck wenn fuer die Rolle ein aktiver
        SSE-Stream laeuft, sonst None.

        Seit Build 267 wird _active_sse_roles geprueft (gepflegt von
        events.py via claim/release), nicht mehr der Fenster-Heartbeat.
        Das verhindert Falsch-Positiv nach Tab-Schliessen (TTL noch aktiv,
        SSE-Thread aber bereits beendet).
        Beleg: Projektgespräch 2026-05-31.

        Build 326: Zusaetzlich Selbstheilung — ist der Rolleneintrag verwaist
        (kein Heartbeat > _SSE_ROLE_TTL, z. B. ungrazilder Disconnect ohne
        Grace-Release), wird er hier automatisch freigegeben und None
        zurueckgegeben, sodass ein neues Fenster die Rolle uebernehmen kann.
        Beleg: Live-Diagnose 2026-07-07 (geleakte Rolle 'main' -> Dauer-409).
        """
        with self._lock:
            if self._sse_role_is_stale(role):
                self._drop_stale_sse_role(role)
            client_id = self._active_sse_roles.get(role)
            if client_id:
                return {
                    "window_id": client_id,
                    "role":      role,
                }
        return None

    def claim_sse_role(self, role: str, client_id: str) -> bool:
        """
        Beansprucht einen SSE-Slot fuer eine Rolle.

        Gibt True zurueck wenn der Slot erfolgreich beansprucht wurde,
        False wenn die Rolle bereits von einer anderen client_id belegt ist
        (Race-Condition zwischen Preflight-Check und Stream-Start).

        Thread-sicher: Lock wird gehalten waehrend geprueft und eingetragen.
        Beleg: Projektgespräch 2026-05-31.
        """
        with self._lock:
            # Build 326: verwaisten Eintrag vorher raeumen, damit ein neues
            # Fenster eine geleakte Rolle uebernehmen kann.
            if self._sse_role_is_stale(role):
                self._drop_stale_sse_role(role)
            existing = self._active_sse_roles.get(role)
            if existing and existing != client_id:
                return False
            self._active_sse_roles[role] = client_id
            self._sse_role_seen[role] = time.time()   # Build 326: Lebendigkeit
            return True

    def release_sse_role(self, role: str, client_id: str) -> None:
        """
        Gibt den SSE-Slot fuer eine Rolle frei.

        Nur der Client der den Slot beansprucht hat darf ihn freigeben
        (client_id-Pruefung). Verhindert dass ein RESUMING-Reconnect
        (neue client_id) den noch aktiven Slot des Vorgaengers loescht.
        Beleg: Projektgespräch 2026-05-31.
        """
        with self._lock:
            if self._active_sse_roles.get(role) == client_id:
                del self._active_sse_roles[role]
                self._sse_role_seen.pop(role, None)   # Build 326
                logger.debug(
                    "SSE-Rolle '%s' freigegeben (client_id=%s)", role, client_id
                )

    def find_active_sse_role(self, role: str) -> Optional[str]:
        """
        Gibt die client_id des aktiven SSE-Clients fuer eine Rolle zurueck,
        oder None wenn kein aktiver SSE-Stream fuer diese Rolle laeuft.
        Beleg: Projektgespräch 2026-05-31.

        Build 326: Selbstheilung — verwaiste Rollen (kein Heartbeat >
        _SSE_ROLE_TTL) werden vor der Abfrage entfernt.
        """
        with self._lock:
            if self._sse_role_is_stale(role):
                self._drop_stale_sse_role(role)
            return self._active_sse_roles.get(role)

    def touch_sse_role(self, role: str, client_id: str) -> None:
        """
        Build 326: Frischt den Lebendigkeits-Zeitstempel der SSE-Rolle auf,
        sofern client_id noch der Inhaber ist. Wird vom LEBENDEN SSE-Stream
        pro Poll-Iteration (<= 15s) aufgerufen. Ohne diese Auffrischung gilt
        der Eintrag nach _SSE_ROLE_TTL als verwaist und wird automatisch
        freigegeben (Selbstheilung gegen geleakte Rollen).
        Beleg: Live-Diagnose 2026-07-07 (Dauer-409 durch geleakte Rolle 'main').
        """
        with self._lock:
            if self._active_sse_roles.get(role) == client_id:
                self._sse_role_seen[role] = time.time()

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

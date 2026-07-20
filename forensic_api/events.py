# =============================================================================
# forensic_api/events.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 3: Forensischer Werkzeugbalken
# Erweitert in Baustelle 4: Nutzerinfo-Tab
# =============================================================================
# Zweck:
#   Endpunkt GET /_forensic/events (text/event-stream).
#   SSE-Stream fuer Support-Status-Indikator (Baustelle 3) und
#   Nutzerinfo-Tab-Events (Baustelle 4).
#
# Event-Typen (ausgehend an Browser):
#   client_id              — Wird sofort beim Verbindungsaufbau gesendet.
#                            Enthaelt die neue SSE-Client-ID. Der Browser
#                            speichert diese fuer spaetere Lock-Operationen.
#   support_status         (B3) — Support-Benutzer aktiv/inaktiv
#   editor_lock_acquired   (B4) — Ein Lock wurde erworben (inkl. locked_by, lock_id)
#   editor_lock_released   (B4) — Ein Lock wurde freigegeben oder abgelaufen
#   lock_acquired          (B4) — Nur an den neuen Inhaber: Lock-Uebergabe aus Queue
#                                 oder Takeover. Enthaelt neue lock_id.
#   lock_takeover_request  (B4) — An den aktuellen Lock-Inhaber: Anfrage eines
#                                 anderen Clients auf Uebergabe des Locks.
#   lock_takeover_result   (B4) — An den anfragenden Client: Ergebnis (granted/denied)
#
# SSE-Client-ID (Build 012):
#   Jede SSE-Verbindung erhaelt beim Aufbau eine eindeutige client_id (UUID).
#   Diese wird als erstes Event "client_id" an den Browser gesendet.
#   Der Browser verwendet sie bei RESUMING (Layer 2) um die Verbindung
#   zu heilen. Die lock_id ist Layer-4-Daten und wird hier nicht verwendet.
#   Beleg: Layer 2 States, SLA Punkt 2, Paket-4-Review 2026-05-24
#
# Grace-Period (SLA Punkt 2):
#   Nach SSE-Verbindungsabriss wird ein threading.Timer(5s) gestartet.
#   Innerhalb dieser 5 Sekunden kann der Client mit RESUMING (Layer 2)
#   seine alte SSE-Client-ID an die neue binden — der Lock bleibt erhalten.
#   Erst nach Ablauf des Timers wird release_lock_by_sse_client() aufgerufen
#   und die Queue-Kaskade gestartet.
#   Beleg: SLA Punkte 2, 3, 4, Paket-4-Review 2026-05-24
#
# Takeover-Events (Option B — DB-Abfrage):
#   events.py praesentiert Takeover-Anfragen NICHT ueber Instanz-Attribute
#   auf evidence_db (Option A war ein Polling-Hack der bei mehreren gleichzeitigen
#   SSE-Verbindungen zu Race-Conditions fuehren kann).
#   Stattdessen liest jede SSE-Verbindung pro Wakeup aus lock_takeover_requests
#   genau die Zeilen, die fuer die eigene client_id relevant sind.
#   Beleg: Architekturentscheidung Paket-4-Review 2026-05-24
#
# Datenbankzugriff:
#   coordinator.db (READ-ONLY) — Support-Status
#   evidence_<uid>.db (READ/WRITE) — Lock-Freigabe bei Grace-Period-Ablauf
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
#
# Changelog Build 278 (2026-06-07):
#   - Preflight-Request-Erkennung: X-Forensic-Preflight: 1.
#     handle() erkennt diesen Header und behandelt den Request als reinen
#     Slot-Verfuegbarkeitscheck: 200 (frei) oder 409 (belegt), ohne
#     claim_sse_role() aufzurufen oder einen Stream zu oeffnen.
#     Damit entsteht kein Konflikt zwischen Preflight-GET und der
#     nachfolgenden echten EventSource-Verbindung (Bug 2.23).
#     Beleg: Bugfix-Liste 2.23, Projektgespraech 2026-06-07
# =============================================================================
#
# Changelog Build 265 (2026-05-31):
#   - Duplikat-SSE-Schutz: handle() prüft ob für die Fenster-Rolle bereits
#     eine aktive SSE-Verbindung existiert. Wenn ja → HTTP 409.
#   - _edb_lock: Klassen-Lock gegen SQLITE_MISUSE.
#     Beleg: Diagnose freeze_dump 2026-05-31.
#
# Changelog Build 267 (2026-05-31) — korrigiert in Build 268:
#   - claim_sse_role beim Stream-Start.
#   - release_sse_role im finally-Block war falsch (zu früh, vor Grace-Period).
#
# Changelog Build 268 (2026-05-31):
#   - release_sse_role aus finally-Block entfernt.
#     Stattdessen: _start_grace_timer() erhält role-Parameter.
#     _grace_expired() ruft release_sse_role() auf — Slot wird erst
#     nach Ablauf der Grace-Period freigegeben.
#     Beim RESUMING (_cancel_grace_timer): Slot via claim_sse_role() auf
#     neue client_id umgeschrieben — Verbindungsheilung ohne 409-Risiko.
#     Beleg: Projektgespräch 2026-05-31.
#
# Changelog Build 247 (Paket 4 — SSE Grace-Period, RESUMING, Takeover-Events):
#   - Grace-Period (5s): threading.Timer ersetzt den direkten _cleanup_lock()-Aufruf
#     in finally{}. Der Timer wird beim RESUMING (SSE-Reconnect) geloescht.
#     Beleg: SLA Punkte 2, 3, Paket-4-Review 2026-05-24
#   - RESUMING via client_id: ?resume_client_id=<alte_client_id> statt
#     ?resume_lock_id=<lock_id>. Lock-ID ist Layer-4-Daten, darf in Layer 2
#     nicht bekannt sein.
#     Beleg: Layer 2 States RESUMING, Paket-4-Review 2026-05-24
#   - Takeover-Events via DB (Option B): Kein Polling auf _pending_takeover /
#     _takeover_result Instanz-Attributen. Jede SSE-Verbindung liest ihre eigene
#     relevante Zeile aus lock_takeover_requests.
#     Beleg: Architekturentscheidung Paket-4-Review 2026-05-24
#   - lock_acquired-Event: Wenn ein Client in der Queue ist und der Lock frei
#     wird, sendet der Server nur an ihn ein lock_acquired-Event mit neuer lock_id.
#     Beleg: Layer 4 States QUEUED->MINE, SLA Punkt 4
#
# Changelog Build 013 (Bugfix: Socket-Backlog-Erschoepfung durch SSE-Verbindungen):
#   - SSE-Semaphore-Guard eingefuehrt: Vor dem Betreten der Polling-Schleife
#     wird ForensicHTTPServer.sse_semaphore.acquire(blocking=False) aufgerufen.
#     Wenn das Limit (SSE_MAX_CONNECTIONS=20) erreicht ist, antwortet der Server
#     sofort mit HTTP 503 statt den Thread dauerhaft zu blockieren.
#     Beleg: Bugfix Build 030 (http_server.py), Projektgespraech 2026-05-07.
#   TODO (Multiplexing): Semaphore-Guard entfaellt wenn SSE-Multiplexing
#     implementiert ist (ein Kanal pro Tab statt mehrere).
#     Beleg: Projektgespraech 2026-05-07.
# =============================================================================

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from core.logger import get_logger
from forensic_api.windows import get_registry as _get_window_registry
from forensic_api.support_presence import SupportPresenceBinder  # NEU Build 312

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

# Standard-Sendeintervall in Sekunden (ueberschreibbar via config.yaml)
_DEFAULT_INTERVAL_SEC = 15

# Grace-Period in Sekunden (SLA Punkt 2): Wie lange nach SSE-Abriss bleibt
# der Lock noch erhalten bevor er freigegeben wird.
# Beleg: SLA Punkt 2, Paket-4-Review 2026-05-24
_GRACE_PERIOD_SEC = 5

# Stale-Schwelle fuer Support-Sitzungen (Sekunden). Eine Sitzung gilt als
# aktiv, solange ihr letzter Heartbeat juenger als dieser Wert ist. 30 s ~=
# 2x SSE-Tick (Default 15 s) + Puffer.
# Beleg: Bauplan B7 v0.6 §6.4 (mc: Frage 1), db.coordinator_db.DEFAULT_SUPPORT_STALE_SEC.
_SUPPORT_STALE_SEC = 30

# Einmal-Bereinigung verwaister Support-Sitzungen beim Support-Start (Sekunden).
# Beleg: Bauplan B7 v0.6 §7.2 (prune(older_than_sec=3600)).
_SUPPORT_PRUNE_OLDER_THAN_SEC = 3600


def _get_support_status(
    bundle: "DatabaseBundle",
    context: "ResolvedContext",
    stale_sec: int = _SUPPORT_STALE_SEC,
) -> dict:
    """
    Liest den Live-Support-Status des Falls (context.subject_id) aus
    coordinator.db (ATTACHed 'cdb', Leseverbindung). Gibt inaktiven Status
    zurueck wenn coordinator_db nicht verfuegbar oder keine aktive Sitzung.

    Build 312:
    - Reicht die Fall-subject_id an get_support_status(subject_id, stale_sec) —
      erst dadurch wird der in Build 311 angelegte Read scharf geschaltet
      (ohne subject_id war er bewusst inaktiv).
    - Nimmt support_count (Anzahl gleichzeitig aktiver Support-Sitzungen)
      in die Nutzlast auf.
    - Im Support-Modus wird KEIN Status gelesen: der Supporter ist der
      Zugreifende, nicht der Beobachtete — er soll sich nicht selbst als
      "Support aktiv" angezeigt bekommen. Der Read ist Sache des
      Ermittler-Fensters (Modus 'job'/'cli').
    Beleg: Bauplan B7 v0.6 §6.4/§7.2, mc 2026-07-01 (Entscheidung 3).
    """
    empty = {
        "support_active": False,
        "support_user": None,
        "since": None,
        "support_count": 0,
    }

    # Support-Modus: keine Selbstbeobachtung.
    if getattr(context, "mode", None) == "support":
        return empty

    if bundle.coordinator is None:
        return empty

    try:
        if hasattr(bundle.coordinator, "get_support_status"):
            status = bundle.coordinator.get_support_status(
                context.subject_id, stale_sec
            )
            if status.active:
                return {
                    "support_active": True,
                    "support_user":   status.username,
                    "since":          status.since_ms,
                    "support_count":  status.count,
                }
    except Exception as exc:
        logger.warning("Support-Status konnte nicht gelesen werden: %s", exc)

    return empty


class EventsEndpoint:
    """
    Endpunkt /_forensic/events — SSE-Stream.

    Sendet im konfigurierbaren Intervall:
    - client_id (sofort, einmalig beim Verbindungsaufbau)
    - support_status (Baustelle 3)
    - editor_lock_acquired / editor_lock_released (Baustelle 4)
    - lock_acquired (nur an neuen Lock-Inhaber nach Queue-Kaskade / Takeover)
    - lock_takeover_request (an aktuellen Lock-Inhaber)
    - lock_takeover_result (an anfragenden Client)

    Grace-Period (SLA Punkt 2):
    Bei Verbindungsabriss wird ein threading.Timer(_GRACE_PERIOD_SEC=5) gestartet.
    Erst nach Ablauf des Timers wird der Lock freigegeben und die Queue-Kaskade
    gestartet. Reconnectet der Client innerhalb der Grace-Period (RESUMING),
    wird der Timer geloescht und der Lock bleibt erhalten.

    Takeover-Events (Option B):
    Jede Polling-Schleife liest pro Wakeup aus lock_takeover_requests die
    Zeilen die fuer die eigene SSE-Client-ID relevant sind. Kein Seitenkanal
    ueber Instanz-Attribute.
    Beleg: SLA Punkte 1-4, Layer 2/4 States, Paket-4-Review 2026-05-24
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
        # Support-Praesenz-Verdrahtung (Build 312). Nur im Support-Modus aktiv;
        # lazy aufgebaut beim ersten Support-Stream (siehe _get_support_binder).
        # Klassen-Attribut, damit der Grace-Timer-Thread (end()) denselben
        # Binder erreicht wie der Stream-Thread (begin()/heartbeat()).
        self._support_binder: Optional[SupportPresenceBinder] = None
        self._support_binder_lock = threading.Lock()

    def _get_support_binder(self) -> Optional[SupportPresenceBinder]:
        """
        Liefert den SupportPresenceBinder — nur im Support-Modus und nur wenn
        coordinator.db existiert. Baut ihn beim ersten Aufruf auf (lazy, damit
        job-/cli-Modus keine zusaetzliche coordinator.db-Schreibverbindung
        oeffnet). Gibt None zurueck, wenn keine Praesenz-Erfassung moeglich ist
        (dann laeuft der Stream ganz normal, nur ohne Support-Sitzung).
        Beleg: Bauplan B7 v0.6 §6.5/§7.2.
        """
        ctx = self._context
        if getattr(ctx, "mode", None) != "support":
            return None

        with self._support_binder_lock:
            if self._support_binder is not None:
                return self._support_binder

            coordinator_path = getattr(ctx, "coordinator_db", None)
            if coordinator_path is None or not Path(coordinator_path).exists():
                logger.warning(
                    "Support-Modus, aber coordinator.db nicht verfuegbar "
                    "('%s') — keine Support-Sitzungserfassung.", coordinator_path,
                )
                return None
            try:
                self._support_binder = SupportPresenceBinder(
                    coordinator_path,
                    subject_id=ctx.subject_id,
                    supporter_id=getattr(ctx, "investigator_id", None),
                    stale_sec=_SUPPORT_STALE_SEC,
                    prune_older_than_sec=_SUPPORT_PRUNE_OLDER_THAN_SEC,
                )
            except Exception as exc:
                logger.error(
                    "Support-Binder konnte nicht aufgebaut werden: %s", exc
                )
                self._support_binder = None
            return self._support_binder

    def close(self) -> None:
        """
        Gibt Endpunkt-Ressourcen frei (Support-Binder-Verbindung). Wird beim
        Serverende aufgerufen; idempotent.
        """
        with self._support_binder_lock:
            if self._support_binder is not None:
                self._support_binder.close()
                self._support_binder = None

    def handle(
        self,
        handler: "ForensicRequestHandler",
        params: dict | None = None,
    ) -> None:
        """
        Verarbeitet GET /_forensic/events.
        Oeffnet SSE-Stream, sendet sofort erste Events, dann im Intervall.

        Vor dem Betreten der Polling-Schleife wird der SSE-Semaphore des
        Servers erworben. Ist das Limit erreicht, antwortet der Server sofort
        mit HTTP 503 statt den Thread dauerhaft zu blockieren.
        Beleg: Bugfix Build 013, Projektgespraech 2026-05-07.

        Args:
            handler: ForensicRequestHandler-Instanz.
            params:  URL-Query-Parameter (aus urllib.parse.parse_qs).
                     resume_client_id: Alte SSE-Client-ID fuer Grace-Period-RESUMING.
                     Beleg: Layer 2 States RESUMING, Paket-4-Review 2026-05-24
        """
        # Bug 2.23 Fix Build 278: Preflight-Request-Erkennung.
        #
        # Der SSE-Layer sendet vor dem Öffnen der echten EventSource einen
        # GET-Request mit dem Header X-Forensic-Preflight: 1. Dieser Request
        # darf den SSE-Slot NICHT beanspruchen und keinen Stream öffnen —
        # er soll nur den Slot-Status abfragen (frei oder belegt).
        #
        # Ohne diese Unterscheidung behandelte der Server den Preflight-GET
        # als vollständigen SSE-Stream-Aufbau, beanspruchte den Slot via
        # claim_sse_role(), sendete 200 OK und wartete auf Daten. Die danach
        # kommende echte EventSource-Verbindung bekam dann 409 weil der Slot
        # bereits durch den Preflight-Request belegt war.
        #
        # Verhalten: Preflight-Request gibt 200 (Slot frei) oder 409
        # (Slot belegt — identische JSON-Antwort wie beim normalen 409).
        # In keinem Fall wird claim_sse_role() aufgerufen oder der Stream geöffnet.
        # Beleg: Bugfix-Liste 2.23, Projektgespraech 2026-06-07
        _is_preflight = (
            handler.headers.get("X-Forensic-Preflight", "").strip() == "1"
        )
        if _is_preflight:
            _pf_role = ((params or {}).get("role") or [None])[0]
            if _pf_role:
                _pf_reg = _get_window_registry()
                _pf_existing = _pf_reg.find_active_by_role(_pf_role)
                if _pf_existing:
                    import json as _pf_json
                    _pf_body = _pf_json.dumps({
                        "duplicate":        True,
                        "role":             _pf_role,
                        "active_window_id": _pf_existing["window_id"],
                    }).encode("utf-8")
                    logger.warning(
                        "SSE-Preflight: Rolle '%s' bereits belegt durch "
                        "Fenster '%s' — HTTP 409.",
                        _pf_role, _pf_existing["window_id"],
                    )
                    handler.send_response_body(
                        409, _pf_body,
                        content_type="application/json; charset=utf-8",
                        extra_headers={"Cache-Control": "no-store"},
                    )
                    return
                # Slot frei — 200 OK ohne Stream zu öffnen
                logger.debug(
                    "SSE-Preflight: Rolle '%s' frei — 200 OK (kein Stream).",
                    _pf_role,
                )
                handler.send_response_body(
                    200,
                    b"{}",
                    content_type="application/json; charset=utf-8",
                    extra_headers={"Cache-Control": "no-store"},
                )
            else:
                # Kein role-Parameter — Preflight ohne Rolle, einfach 200
                handler.send_response_body(200, b"{}")
            return  # Preflight komplett behandelt — kein Stream, kein claim

        # Duplikat-SSE-Schutz: Prüfen ob für diese Fenster-Rolle bereits eine
        # aktive SSE-Verbindung läuft. Wenn ja → HTTP 409 damit der Browser
        # das Duplikat-Tab schließen oder ignorieren kann.
        # Die Rolle kommt als ?role=<main|userinfo|report> im Query-String.
        # Beleg: Projektgespräch 2026-05-31.
        _role = ((params or {}).get("role") or [None])[0]
        if _role:
            _reg = _get_window_registry()
            _existing = _reg.find_active_by_role(_role)
            if _existing:
                import json as _json
                _body = _json.dumps({
                    "duplicate":        True,
                    "role":             _role,
                    "active_window_id": _existing["window_id"],
                }).encode("utf-8")
                logger.warning(
                    "SSE-Duplikat abgewiesen: Rolle '%s' bereits belegt durch "
                    "Fenster '%s' — HTTP 409.",
                    _role, _existing["window_id"],
                )
                handler.send_response_body(
                    409, _body,
                    content_type="application/json; charset=utf-8",
                    extra_headers={"Cache-Control": "no-store"},
                )
                return

        # SSE-Semaphore erwerben — verhindert Thread-Pool-Blockade.
        # non-blocking: sofortiger 503 statt unendliches Warten.
        # Beleg: Bugfix Build 013, Projektgespraech 2026-05-07.
        sse_semaphore = getattr(handler.server, "sse_semaphore", None)
        if sse_semaphore is not None and not sse_semaphore.acquire(blocking=False):
            logger.warning(
                "SSE-Verbindungslimit erreicht (max=%d) — HTTP 503 fuer client.",
                getattr(handler.server, "SSE_MAX_CONNECTIONS", "?"),
            )
            handler.send_response_body(
                503,
                b"<html><body><p>SSE-Verbindungslimit erreicht. "
                b"Bitte Seite neu laden.</p></body></html>",
            )
            return

        try:
            self._handle_stream(handler, params)
        finally:
            if sse_semaphore is not None:
                sse_semaphore.release()

    def _handle_stream(
        self,
        handler: "ForensicRequestHandler",
        params: dict | None = None,
    ) -> None:
        """
        Innere Implementierung des SSE-Streams (nach Semaphore-Erwerb).
        Ausgelagert aus handle() fuer Uebersichtlichkeit.
        """
        wfile = handler.wfile

        # Eindeutige SSE-Client-ID fuer diesen Verbindungsaufbau
        # Beleg: SLA Punkt 1, Build 012
        client_id = str(uuid.uuid4())

        # Aktive Clients tracken fuer Queue-Kaskade (SLA Punkt 4)
        if self._bundle._active_sse_clients is None:
            self._bundle._active_sse_clients = set()
        self._bundle._active_sse_clients.add(client_id)

        # SSE-Rolle beanspruchen — Duplikat-Schutz (Build 267).
        # Wird im finally-Block wieder freigegeben damit der Slot
        # exakt mit dem Stream-Thread-Ende freigegeben wird.
        # _role wurde bereits in handle() aus params gelesen — hier
        # nochmals lesen da _handle_stream params eigenstaendig bekommt.
        # Beleg: Projektgespräch 2026-05-31.
        _stream_role: Optional[str] = ((params or {}).get("role") or [None])[0]
        if _stream_role:
            _get_window_registry().claim_sse_role(_stream_role, client_id)
            logger.debug(
                "SSE-Rolle '%s' beansprucht: client_id=%s", _stream_role, client_id
            )

        # RESUMING (Layer 2): Alte SSE-Client-ID aus Query-Parameter.
        # Falls vorhanden: Lock des alten Clients auf neue client_id umschreiben
        # und einen laufenden Grace-Timer loeschen.
        # Beleg: Layer 2 States RESUMING, SLA Punkt 2, Paket-4-Review 2026-05-24
        resume_client_id: Optional[str] = (params or {}).get("resume_client_id", [None])[0]
        if resume_client_id:
            # Grace-Timer fuer die alte client_id loeschen — Verbindung geheilt.
            # new_client_id mitsenden damit SSE-Slot auf neue ID umgeschrieben wird.
            # Beleg: SLA Punkt 2 (Grace-Period-Heilung), Paket-4-Review 2026-05-24
            # Beleg Build 268: Projektgespräch 2026-05-31.
            self._cancel_grace_timer(resume_client_id, new_client_id=client_id)

            resumed = self._bundle.evidence.resume_lock(
                old_sse_client=resume_client_id,
                new_sse_client=client_id,
            )
            if resumed:
                logger.info(
                    "SSE-RESUMING: Lock umgebunden alte_sse=%s neue_sse=%s",
                    resume_client_id, client_id,
                )
            else:
                logger.debug(
                    "SSE-RESUMING: Kein Lock gefunden (Grace-Period bereits abgelaufen?) "
                    "alte_sse=%s",
                    resume_client_id,
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
            self._bundle._active_sse_clients.discard(client_id)
            return

        def _send_event(event_name: str, data: dict) -> bool:
            """
            Sendet ein SSE-Event. Gibt False zurueck bei Verbindungsabbruch.
            Formatierung nach RFC 8895: "event: ...\\ndata: ...\\n\\n"
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
                logger.debug(
                    "SSE-Stream: Client hat Verbindung getrennt (client_id=%s)", client_id
                )
                return False

        # Sofort: Client-ID senden — Browser speichert sie fuer RESUMING
        if not _send_event("client_id", {"client_id": client_id}):
            self._bundle._active_sse_clients.discard(client_id)
            return

        # Sofort: ersten Support-Status senden
        status = _get_support_status(self._bundle, self._context)
        if not _send_event("support_status", status):
            self._bundle._active_sse_clients.discard(client_id)
            self._start_grace_timer(client_id)
            return

        # ------------------------------------------------------------------
        # Build 312: Support-Praesenz-Sitzung etablieren (NUR im Support-Modus).
        # Bei RESUMING wird die bestehende Sitzung der alten client_id auf die
        # neue umgehaengt (kein neuer Audit-Beleg). Ist die Sitzung inzwischen
        # (Grace abgelaufen) beendet, wird eine neue gestartet. In job/cli-Modus
        # ist _support_binder None -> kein Effekt.
        # Der Grace-Timer beendet die Sitzung spaeter (mc: Entscheidung 1).
        # Beleg: Bauplan B7 v0.6 §6/§7.2, mc 2026-07-01.
        # ------------------------------------------------------------------
        _support_binder = self._get_support_binder()
        if _support_binder is not None:
            _resumed_session = False
            if resume_client_id:
                _resumed_session = _support_binder.resume(resume_client_id, client_id)
            if not _resumed_session:
                _support_binder.begin(client_id)
            # Erster Heartbeat direkt nach dem Etablieren.
            _support_binder.heartbeat(client_id)

        # Sofort: aktuellen Lock-Status senden (Fenster 3 informieren)
        self._send_lock_status(_send_event)

        # Letzten gesendeten Lock-Zustand merken — nur bei Aenderung senden.
        # Verhindert dass editor_lock_released periodisch gesendet wird
        # wenn schlicht kein Lock vorhanden ist.
        # Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-19
        with EventsEndpoint._edb_lock:
            _initial_lock = self._bundle.evidence._con.execute(
                "SELECT lock_id FROM editor_locks ORDER BY locked_at DESC LIMIT 1"
            ).fetchone()
        _last_lock_id: Optional[str] = (
            str(_initial_lock["lock_id"]) if _initial_lock else None
        )

        # Warte-Event vom EvidenceDb — wird bei Lock-Aenderungen sofort gesetzt.
        # Beleg: Lock-System v2, Projektgespraech 2026-04-21
        lock_event = self._bundle.evidence.lock_change_event

        # Polling-Schleife
        try:
            while True:
                # Schlaeft interval Sekunden ODER wird sofort geweckt
                # wenn acquire_lock() / release_lock() aufgerufen wird.
                lock_event.wait(timeout=self._interval)

                # Build 326: Lebendigkeits-Signal der SSE-Rolle auffrischen.
                # Solange dieser Stream laeuft, bleibt sein Rolleneintrag frisch;
                # bricht er ungrazilger ab (Grace-Pfad laeuft nicht, Prozess weg),
                # verwaist der Eintrag nach _SSE_ROLE_TTL und das naechste Fenster
                # kann die Rolle uebernehmen (Selbstheilung gegen Dauer-409).
                # Beleg: Live-Diagnose 2026-07-07 (geleakte Rolle 'main' d12ae68a).
                if _stream_role:
                    _get_window_registry().touch_sse_role(_stream_role, client_id)

                # Lock-Zustand lesen, DANN Event loeschen.
                # Reihenfolge wichtig: zwischen clear() und dem DB-Zugriff koennte
                # sonst eine Aenderung verloren gehen.
                with EventsEndpoint._edb_lock:
                    _cl_row = self._bundle.evidence._con.execute(
                        "SELECT lock_id FROM editor_locks ORDER BY locked_at DESC LIMIT 1"
                    ).fetchone()
                current_lock_id: Optional[str] = (
                    str(_cl_row["lock_id"]) if _cl_row else None
                )
                lock_event.clear()

                # Build 312: Heartbeat der Support-Sitzung (nur Support-Modus).
                # Haelt die Praesenz frisch (last_heartbeat), damit sie beim
                # Ermittler nicht als stale (>_SUPPORT_STALE_SEC) verschwindet.
                # KEIN Audit (nur Praesenz). In job/cli-Modus No-op.
                if _support_binder is not None:
                    _support_binder.heartbeat(client_id)

                # Support-Status senden
                status = _get_support_status(self._bundle, self._context)
                if not _send_event("support_status", status):
                    break

                # Lock-Status nur bei Aenderung senden
                if current_lock_id != _last_lock_id:
                    _last_lock_id = current_lock_id
                    if not self._send_lock_status(_send_event):
                        break

                # Takeover-Benachrichtigungen (Option B — DB-Abfrage).
                # Jede SSE-Verbindung liest nur die Zeilen, die an sie adressiert sind.
                # Beleg: Architekturentscheidung Paket-4-Review 2026-05-24
                if not self._send_takeover_events(_send_event, client_id):
                    break

                # Lock-Uebergabe: Wurde diesem Client ein Lock aus der Queue zugeteilt?
                # Beleg: Layer 4 States QUEUED->MINE, SLA Punkt 4
                if not self._send_lock_acquired_if_mine(_send_event, client_id):
                    break

        finally:
            # Verbindung abgerissen: Grace-Timer starten.
            # Erst nach _GRACE_PERIOD_SEC Sekunden wird der Lock freigegeben.
            # Reconnectet der Client innerhalb dieser Zeit (RESUMING), wird
            # der Timer geloescht und der Lock bleibt erhalten.
            # Beleg: SLA Punkt 2, Paket-4-Review 2026-05-24
            self._bundle._active_sse_clients.discard(client_id)
            # SSE-Slot wird NICHT sofort freigegeben — erst nach Ablauf der
            # Grace-Period (_grace_expired). Damit kann ein RESUMING-Reconnect
            # innerhalb von _GRACE_PERIOD_SEC den Slot heilen ohne 409.
            # Beleg: Projektgespräch 2026-05-31.
            self._start_grace_timer(client_id, _stream_role)

    # ------------------------------------------------------------------
    # Grace-Period-Verwaltung
    # ------------------------------------------------------------------

    # Klassen-Dictionary fuer laufende Grace-Timer (client_id -> threading.Timer).
    # Beleg: SLA Punkt 2, Paket-4-Review 2026-05-24
    _grace_timers: dict[str, threading.Timer] = {}
    _grace_timers_lock: threading.Lock = threading.Lock()

    # Klassen-Lock fuer serialisierten Zugriff auf edb._con aus mehreren
    # SSE-Threads. SQLite erlaubt check_same_thread=False, aber concurrent
    # execute()-Aufrufe aus verschiedenen Threads fuehren zu SQLITE_MISUSE.
    # Beleg: Diagnose freeze_dump 2026-05-31, SQLITE_MISUSE (error 21).
    _edb_lock: threading.Lock = threading.Lock()

    def _start_grace_timer(self, client_id: str, role: Optional[str] = None) -> None:
        """
        Startet den Grace-Period-Timer fuer eine SSE-Client-ID.

        Nach _GRACE_PERIOD_SEC Sekunden wird _grace_expired() aufgerufen
        wenn der Timer nicht vorher durch _cancel_grace_timer() geloescht wurde.
        role: optionale Fenster-Rolle — wenn gesetzt, gibt _grace_expired()
        den SSE-Slot via release_sse_role() frei.

        Beleg: SLA Punkt 2, Paket-4-Review 2026-05-24
        Beleg Build 268: Projektgespräch 2026-05-31.
        """
        timer = threading.Timer(
            _GRACE_PERIOD_SEC,
            self._grace_expired,
            args=(client_id, role),
        )
        timer.daemon = True  # Kein Blockieren des Server-Shutdowns
        with EventsEndpoint._grace_timers_lock:
            # Sicherheit: existierenden Timer fuer dieselbe client_id abbrechen
            old = EventsEndpoint._grace_timers.get(client_id)
            if old:
                old.cancel()
            EventsEndpoint._grace_timers[client_id] = timer
        timer.start()
        logger.debug(
            "Grace-Timer gestartet: client_id=%s (%.0fs)", client_id, _GRACE_PERIOD_SEC
        )

    def _cancel_grace_timer(
        self, client_id: str, new_client_id: Optional[str] = None
    ) -> bool:
        """
        Loescht einen laufenden Grace-Period-Timer (RESUMING — Verbindung geheilt).

        new_client_id: wenn angegeben, wird der SSE-Slot der alten client_id
        auf die neue client_id umgeschrieben (claim_sse_role). Damit bleibt
        der Duplikat-Schutz aktiv ohne dass der neue Stream einen 409 bekommt.
        Beleg: Layer 2 States RESUMING, SLA Punkt 2, Paket-4-Review 2026-05-24
        Beleg Build 268: Projektgespräch 2026-05-31.
        """
        with EventsEndpoint._grace_timers_lock:
            timer = EventsEndpoint._grace_timers.pop(client_id, None)
        if timer:
            timer.cancel()
            logger.debug("Grace-Timer geloescht (RESUMING): client_id=%s", client_id)
            # Slot auf neue client_id umschreiben damit kein Fenster-Loch entsteht.
            # _active_sse_roles: alte_id → neue_id (claim ueberschreibt sicher).
            # Beleg: Build 268, Projektgespräch 2026-05-31.
            if new_client_id:
                reg = _get_window_registry()
                # Alle Rollen prüfen ob alte client_id einen Slot hält
                # (wir kennen die Rolle hier nicht direkt — über find suchen)
                with reg.lock:
                    for role, cid in list(reg._active_sse_roles.items()):
                        if cid == client_id:
                            reg._active_sse_roles[role] = new_client_id
                            # Build 326: Lebendigkeits-Zeitstempel mitfuehren,
                            # sonst koennte der frisch uebernommene Slot faelschlich
                            # als verwaist gelten, bevor der neue Stream touch't.
                            reg._sse_role_seen[role] = time.time()
                            logger.debug(
                                "SSE-Slot RESUMING: Rolle '%s' %s → %s",
                                role, client_id, new_client_id,
                            )
            return True
        return False

    def _grace_expired(self, client_id: str, role: Optional[str] = None) -> None:
        """
        Callback: Grace-Period abgelaufen — Lock freigeben und Queue-Kaskade.

        Wird vom threading.Timer-Thread aufgerufen nach _GRACE_PERIOD_SEC Sekunden.
        Atomaritaetsanforderung (SLA Punkt 3): release_lock_by_sse_client() und
        queue_next_valid() werden in derselben DB-Transaktion durchgefuehrt
        (sichergestellt durch release_lock_by_sse_client() + Commit vor
        queue_next_valid()).

        role: wenn gesetzt, wird der SSE-Slot via release_sse_role() freigegeben.
        Das ist der korrekte Zeitpunkt — erst nach Ablauf der Grace-Period.
        Beleg: SLA Punkte 2, 3, 4, Paket-4-Review 2026-05-24
        Beleg Build 268: Projektgespräch 2026-05-31.
        """
        with EventsEndpoint._grace_timers_lock:
            EventsEndpoint._grace_timers.pop(client_id, None)

        logger.info(
            "Grace-Period abgelaufen — Lock wird freigegeben: client_id=%s", client_id
        )
        # SSE-Slot freigeben — jetzt erst, nach Grace-Period.
        # Beleg: Build 268, Projektgespräch 2026-05-31.
        if role:
            _get_window_registry().release_sse_role(role, client_id)
            logger.debug(
                "SSE-Rolle '%s' freigegeben nach Grace-Period: client_id=%s",
                role, client_id,
            )

        # Build 312: Support-Praesenz-Sitzung beenden — grace-gekoppelt
        # (mc: Entscheidung 1). Ein RESUMING innerhalb der Grace-Period haette
        # den Timer geloescht (kein _grace_expired) und die Sitzung per resume()
        # weitergefuehrt; kommt der Callback dagegen zum Zug, ist die Verbindung
        # endgueltig weg -> Sitzung schliessen + SUPPORT_SESSION_ENDED auditieren.
        # end() ist idempotent und fehlertolerant (bricht den Lock-Pfad nie ab).
        if self._support_binder is not None:
            self._support_binder.end(client_id)

        try:
            edb = self._bundle.evidence
            freed_report_ids = edb.release_lock_by_sse_client(client_id)

            # Queue-Kaskade fuer jeden freigegebenen Bericht (SLA Punkt 4)
            if freed_report_ids:
                active_clients = self._bundle.get_active_sse_clients()
                for report_id in freed_report_ids:
                    self._process_queue_cascade(report_id, active_clients)
        except Exception as exc:
            logger.error("_grace_expired: Fehler bei Lock-Freigabe: %s", exc)

    def _process_queue_cascade(self, report_id: int, active_clients: set) -> None:
        """
        FIFO-Queue-Kaskade nach Lock-Freigabe (SLA Punkt 4).

        Sucht den ersten gueltigen Queue-Eintrag (mit aktiver SSE-Verbindung),
        vergibt den Lock an diesen Client und benachrichtigt ihn per
        lock_change_event (der SSE-Thread des neuen Inhabers sendet dann
        ein lock_acquired-Event).

        Beleg: SLA Punkte 3, 4, Paket-4-Review 2026-05-24
        """
        try:
            edb = self._bundle.evidence
            next_candidate = edb.queue_next_valid(report_id, active_clients)
            if next_candidate:
                new_lock_id = edb.acquire_lock(
                    report_id,
                    next_candidate["requested_by"],
                    next_candidate["sse_client"],
                )
                if new_lock_id:
                    edb.queue_remove(report_id, next_candidate["requested_by"])
                    logger.info(
                        "Queue-Kaskade: '%s' erhaelt Lock report_id=%d lock_id=%s",
                        next_candidate["requested_by"], report_id, new_lock_id,
                    )
                    # lock_change_event weckt alle SSE-Polling-Schleifen.
                    # Der SSE-Thread des neuen Inhabers sendet lock_acquired.
                    edb.lock_change_event.set()
        except Exception as exc:
            logger.error("_process_queue_cascade: Fehler: %s", exc)

    # ------------------------------------------------------------------
    # Takeover-Events (Option B — DB-Abfrage pro Polling-Wakeup)
    # ------------------------------------------------------------------

    def _send_takeover_events(self, send_fn, client_id: str) -> bool:
        """
        Prueeft ob Takeover-Events fuer diese SSE-Verbindung anstehen.

        Zwei Szenarien:
        A) Diese SSE-Verbindung haelt einen Lock und jemand hat eine
           Takeover-Anfrage gestellt: lock_takeover_request senden.
        B) Diese SSE-Verbindung hat eine Takeover-Anfrage gestellt und
           diese wurde resolved (granted/denied): lock_takeover_result senden.

        Gibt False zurueck wenn die SSE-Verbindung abgebrochen ist.
        Beleg: Layer 4 States TAKEOVER_PENDING / TAKEOVER_REQUEST_IN,
               Architekturentscheidung Paket-4-Review 2026-05-24
        """
        try:
            edb = self._bundle.evidence

            # Szenario A: Bin ich Lock-Inhaber mit einer pending Takeover-Anfrage?
            # Suche den Lock der zu meiner client_id gehoert.
            with EventsEndpoint._edb_lock:
                my_lock_row = edb._con.execute(
                    "SELECT report_id, lock_id FROM editor_locks WHERE sse_client=?",
                    (client_id,),
                ).fetchone()
            if my_lock_row:
                report_id = int(my_lock_row["report_id"])
                pending = edb.get_pending_takeover(report_id)
                if pending:
                    if not send_fn("lock_takeover_request", {
                        "report_id":    report_id,
                        "request_id":   pending["id"],
                        "requested_by": pending["requested_by"],
                        "requested_at": pending["requested_at"],
                    }):
                        return False

            # Szenario B: Habe ich eine Takeover-Anfrage gestellt, die resolved wurde?
            # Suche nach Eintraegen in lock_takeover_requests mit meiner client_id
            # die noch nicht an den Client gesendet wurden.
            # Identifikation: requested_by des anfragenden Clients ist in der DB,
            # aber wir brauchen die sse_client des Anfragenden.
            # Da lock_takeover_requests keine sse_client-Spalte fuer den Anfragenden
            # speichert, lesen wir ueber queue-Eintrag oder direkt ueber den
            # aktuellen sse_client des Anfragenden.
            # Pragmatische Loesung: Wir suchen ob es fuer unsere client_id einen
            # queue-Eintrag gibt und ob der zugehoerige Lock resolved wurde.
            with EventsEndpoint._edb_lock:
                my_queue_row = edb._con.execute(
                    "SELECT report_id, requested_by FROM lock_queue WHERE sse_client=?",
                    (client_id,),
                ).fetchone()
            if my_queue_row:
                report_id    = int(my_queue_row["report_id"])
                requested_by = str(my_queue_row["requested_by"])
                # Gibt es ein resolved Takeover-Ergebnis fuer diesen Benutzer?
                with EventsEndpoint._edb_lock:
                    result_row = edb._con.execute(
                        "SELECT id, status FROM lock_takeover_requests "
                        "WHERE report_id=? AND requested_by=? AND status IN ('granted','denied') "
                        "AND responded_at IS NOT NULL "
                        "ORDER BY responded_at DESC LIMIT 1",
                        (report_id, requested_by),
                    ).fetchone()
                if result_row:
                    if not send_fn("lock_takeover_result", {
                        "report_id":  report_id,
                        "request_id": int(result_row["id"]),
                        "result":     str(result_row["status"]),
                    }):
                        return False

        except Exception as exc:
            logger.warning("_send_takeover_events: Fehler: %s", exc)
        return True

    def _send_lock_acquired_if_mine(self, send_fn, client_id: str) -> bool:
        """
        Sendet lock_acquired an einen Client dem soeben ein Lock aus der
        Queue-Kaskade zugeteilt wurde.

        Prueft ob in editor_locks ein Eintrag fuer diese client_id existiert.
        Wenn ja, sendet es ein lock_acquired-Event mit report_id und lock_id.
        Dieses Event ist der direkte Kanal von Layer 4 QUEUED -> MINE.

        Das Event wird nur gesendet wenn der Lock innerhalb der letzten
        (interval * 2 + 2) Sekunden erworben wurde — als Schutz davor dass
        ein bestehendes Lock bei jedem Polling-Wakeup erneut gemeldet wird.
        Layer 4 im Frontend behandelt lock_acquired idempotent.

        Gibt False zurueck bei Verbindungsabbruch.
        Beleg: Layer 4 States QUEUED->MINE, SLA Punkt 4, Paket-4-Review 2026-05-24
        """
        try:
            edb = self._bundle.evidence
            row = edb._con.execute(
                "SELECT report_id, lock_id, locked_at FROM editor_locks "
                "WHERE sse_client=?",
                (client_id,),
            ).fetchone()
            if not row:
                return True  # Kein Lock fuer diese Verbindung — nichts zu senden

            age_sec = time.time() - int(row["locked_at"])
            # Schwellwert: 2 * Polling-Intervall + 2s Toleranz.
            # Darueberhinaus ist der Lock bereits "bekannt" und wurde beim
            # Verbindungsaufbau per editor_lock_acquired / _send_lock_status gemeldet.
            threshold = self._interval * 2 + 2
            if age_sec <= threshold:
                if not send_fn("lock_acquired", {
                    "report_id": int(row["report_id"]),
                    "lock_id":   str(row["lock_id"]),
                }):
                    return False
        except Exception as exc:
            logger.warning("_send_lock_acquired_if_mine: Fehler: %s", exc)
        return True

    # ------------------------------------------------------------------
    # Lock-Status-Event
    # ------------------------------------------------------------------

    def _send_lock_status(self, send_fn) -> bool:
        """
        Sendet den aktuellen Editor-Lock-Status (editor_lock_acquired /
        editor_lock_released) an alle Clients.

        Gibt False zurueck wenn Verbindung abgebrochen ist.
        Defensiv gegen korrupte Altdatensaetze mit locked_at=NULL.
        Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-19
        """
        from db.evidence_db import EditorLockRecord as _ELR
        try:
            _lk_row = self._bundle.evidence._con.execute(
                "SELECT report_id, locked_by, lock_id, locked_at, sse_client "
                "FROM editor_locks ORDER BY locked_at DESC LIMIT 1"
            ).fetchone()
            lock = (
                _ELR(
                    report_id=int(_lk_row["report_id"]),
                    locked_by=str(_lk_row["locked_by"]),
                    lock_id=str(_lk_row["lock_id"]),
                    locked_at=int(_lk_row["locked_at"]),
                    sse_client=str(_lk_row["sse_client"]),
                    cooldown_until=None,
                ) if _lk_row else None
            )
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

    # ------------------------------------------------------------------
    # Direkte Lock-Benachrichtigung (Queue-Kaskade -> neuer Inhaber)
    # ------------------------------------------------------------------

    def notify_lock_acquired(self, sse_client: str, report_id: int, lock_id: str) -> None:
        """
        Wird von report.py aufgerufen wenn einem Client per Queue-Kaskade oder
        Takeover ein Lock zugeteilt wurde. Loest lock_change_event aus.

        Der SSE-Thread des neuen Inhabers sendet dann bei naechster Gelegenheit
        ein lock_acquired-Event.

        Beleg: Layer 4 States QUEUED->MINE, SLA Punkt 4, Paket-4-Review 2026-05-24
        """
        self._bundle.evidence.lock_change_event.set()
        logger.debug(
            "notify_lock_acquired: sse_client=%s report_id=%d lock_id=%s",
            sse_client, report_id, lock_id,
        )

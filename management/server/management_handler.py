# =============================================================================
# management/server/management_handler.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Duenne HTTP-Huelle um ManagementApp. Nur GET (read-only-first). Nicht-SSE-
#   Requests werden an app.dispatch() delegiert; /events liefert den SSE-Tick.
#   Der Server bindet AUSSCHLIESSLICH localhost (Beleg: Bauplan B7 v1.1 §11.2).
#
# Nebenlaeufigkeit: ThreadingHTTPServer, ABER jeder Request oeffnet seine eigene
#   kurzlebige read-only Verbindung in ManagementApp (Build-325-Lehre: keine
#   geteilte SQLite-Connection -> kein Win32-Mutex-Deadlock).
#
# SSE (/events): sendet sofort ein 'hello' mit der aktuellen audit_log-Spitze,
#   danach pollt der Stream die Spitze; steigt sie -> 'changed' (neue seq), sonst
#   'keepalive'. Kein Wiederverwenden der B3/4-SSE-Maschinerie, nur ihr RFC-8895-
#   Rahmenformat (format_sse_event).
#
# Build 503: Cache-Control 'no-cache' fuer ALLE Nicht-SSE-Antworten
#   (_send_bytes) — Vorfall 2026-07-24: veraltete cockpit.html im Browser-Cache.
# Build 522 (AP-3F): _send_bytes gibt zusaetzlich die 'extra_headers' der
#   Antwort aus (heute nur 'Content-Disposition' fuer den Prognose-PDF). Die
#   Pruefung auf Zeilenumbrueche (Response Splitting) sitzt HIER, an der Stelle,
#   die die Kopfzeile schreibt — nicht bei den Aufrufern.
# Version: v0.8.522 · Build: 522 · 2026-07-25
# =============================================================================

import http.server
import json
import logging
import socketserver
import time
from typing import Optional
from urllib.parse import parse_qs, urlsplit

from management.server.management_app import ManagementApp, format_sse_event

logger = logging.getLogger(__name__)

#: Poll-Intervall des SSE-Ticks in Sekunden (konfigurierbar am Server).
DEFAULT_SSE_POLL_SEC = 2.0


class ManagementRequestHandler(http.server.BaseHTTPRequestHandler):
    """GET-only Handler; delegiert an die ManagementApp des Servers."""

    server_version = "AIWManagement/0.7"

    # Standardausgaben von BaseHTTPRequestHandler unterdruecken (eigenes Logging).
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        logger.debug("mgmt %s - %s", self.address_string(), format % args)

    def do_GET(self) -> None:
        parts = urlsplit(self.path)
        path = parts.path
        query = parse_qs(parts.query)

        if path == "/events":
            self._handle_sse()   # SSE prueft das Gate selbst (langlebige Route)
            return

        # Wartungsmodus (Build 437): bei blockiertem Gate HTTP 503 OHNE DB-Zugriff.
        gate = getattr(self.server, "maintenance_gate", None)
        if gate is not None and not gate.enter():
            self._send_503_wartung()
            return
        try:
            app: ManagementApp = self.server.app  # type: ignore[attr-defined]
            person_id: int = self.server.person_id  # type: ignore[attr-defined]
            try:
                resp = app.dispatch(person_id, path, query)
            except Exception:
                logger.exception("mgmt dispatch-Fehler fuer %s", path)
                self._send_bytes(500, "application/json; charset=utf-8",
                                 b'{"error":"internal"}')
                return
            self._send_bytes(resp.status, resp.content_type, resp.body,
                             getattr(resp, "extra_headers", ()))
        finally:
            if gate is not None:
                gate.leave()

    # AUDITIERTER SCHREIBPFAD (Build 372). Der Server bleibt fuer alles ausser
    # den in ManagementApp.dispatch_write gelisteten Routen read-only.
    # Haertung (localhost-only ist bereits durch das Binding gegeben):
    #   1) Content-Type MUSS application/json sein -> verhindert einfache
    #      Cross-Origin-Formular-POSTs (die nur form-encoded senden koennen).
    #   2) Origin (falls gesetzt) muss localhost sein -> blockt fremde Seiten.
    #   3) X-AIW-Token muss dem Schreib-Token des Serverlaufs entsprechen
    #      (konstantzeitlicher Vergleich). Das Token gibt es nur ueber den
    #      authentifizierten GET /api/whoami -> wer die Antwort nicht lesen
    #      kann (Bridge/Tunnel/CSRF), kann nicht schreiben.
    # Fehler werden explizit beantwortet, nie still verschluckt (Grundregel 1).
    _MAX_BODY = 64 * 1024

    def do_POST(self) -> None:
        # Wartungsmodus (Build 437): bei blockiertem Gate HTTP 503, kein Schreibpfad.
        gate = getattr(self.server, "maintenance_gate", None)
        if gate is not None and not gate.enter():
            self._send_503_wartung()
            return
        try:
            self._do_POST_impl()
        finally:
            if gate is not None:
                gate.leave()

    def _do_POST_impl(self) -> None:
        app: ManagementApp = self.server.app  # type: ignore[attr-defined]
        person_id: int = self.server.person_id  # type: ignore[attr-defined]
        path = urlsplit(self.path).path

        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        if ctype != "application/json":
            self._send_json(415, {"error": "unsupported_media_type",
                                  "detail": "application/json erforderlich."})
            return

        origin = self.headers.get("Origin")
        if origin and not self._origin_is_local(origin):
            logger.warning("mgmt POST mit fremdem Origin abgewiesen: %s", origin)
            self._send_json(403, {"error": "bad_origin"})
            return

        if not app.check_write_token(self.headers.get("X-AIW-Token")):
            logger.warning("mgmt POST ohne/mit falschem Schreib-Token: %s", path)
            self._send_json(403, {"error": "bad_token",
                                  "detail": "X-AIW-Token fehlt oder ungueltig."})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_json(400, {"error": "bad_request",
                                  "detail": "Content-Length ungueltig."})
            return
        if length <= 0 or length > self._MAX_BODY:
            self._send_json(413, {"error": "bad_body_length"})
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": "bad_json", "detail": str(exc)})
            return

        try:
            resp = app.dispatch_write(person_id, path, payload)
        except Exception:
            logger.exception("mgmt dispatch_write-Fehler fuer %s", path)
            self._send_bytes(500, "application/json; charset=utf-8",
                             b'{"error":"internal"}')
            return
        self._send_bytes(resp.status, resp.content_type, resp.body)

    @staticmethod
    def _origin_is_local(origin: str) -> bool:
        host = urlsplit(origin).hostname or ""
        return host in ("127.0.0.1", "localhost", "::1")

    def _send_json(self, status: int, payload) -> None:
        self._send_bytes(status, "application/json; charset=utf-8",
                         json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    # Uebrige schreibende Methoden bleiben abgewiesen.
    def _reject(self) -> None:
        self._send_bytes(405, "application/json; charset=utf-8",
                         b'{"error":"method_not_allowed"}')

    do_PUT = _reject
    do_DELETE = _reject
    do_PATCH = _reject

    # ------------------------------------------------------------------- SSE
    def _handle_sse(self) -> None:
        app: ManagementApp = self.server.app  # type: ignore[attr-defined]
        poll: float = getattr(self.server, "sse_poll_sec", DEFAULT_SSE_POLL_SEC)
        gate = getattr(self.server, "maintenance_gate", None)
        # Waehrend der Wartung keine NEUE SSE-Verbindung annehmen (DB-Zugriff).
        if gate is not None and not gate.enter():
            self._send_503_wartung()
            return
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            last = app.audit_tip_seq()
            self.wfile.write(format_sse_event("hello", {"tip_seq": last}))
            self.wfile.flush()

            while True:
                time.sleep(poll)
                # Beginnt eine Wartung, die SSE sauber beenden — sonst haelt diese
                # langlebige Verbindung eine In-Flight-Zaehlung und der Drain
                # kaeme nie durch (Build 437).
                if gate is not None and gate.is_blocked():
                    return
                current = app.audit_tip_seq()
                if current != last:
                    self.wfile.write(
                        format_sse_event("changed", {"tip_seq": current}))
                    last = current
                else:
                    self.wfile.write(format_sse_event("keepalive", {}))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            # Client (Browser-Tab) hat getrennt — kein Fehler.
            return
        except Exception:
            logger.exception("mgmt SSE-Fehler")
            return
        finally:
            if gate is not None:
                gate.leave()

    def _send_503_wartung(self) -> None:
        """HTTP 503 (JSON) waehrend des Wartungsmodus."""
        try:
            body = b'{"error":"maintenance","detail":"Wartungsmodus aktiv."}'
            self.send_response(503)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Retry-After", "30")
            self.send_header("X-Forensic-Status", "MAINTENANCE")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    # --------------------------------------------------------------- Senden
    def _send_bytes(self, status: int, content_type: str, body: bytes,
                    extra_headers=()) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            # Build 522 (AP-3F): Zusatz-Kopfzeilen der Antwort (heute nur
            # 'Content-Disposition' fuer den Prognose-PDF).
            #
            # HAERTUNG AN DIESER STELLE, nicht beim Aufrufer: Ein '\r' oder '\n'
            # in Name oder Wert waere eine Kopfzeilen-Injektion (Response
            # Splitting). Die Werte kommen zwar aus dem eigenen Code
            # (Response.pdf begrenzt den Dateinamen bereits), aber die Pruefung
            # gehoert dorthin, wo die Kopfzeile TATSAECHLICH geschrieben wird —
            # sonst haengt die Sicherheit daran, dass jeder kuenftige Aufrufer
            # daran denkt. Eine verdaechtige Kopfzeile wird VERWORFEN und
            # PROTOKOLLIERT (nicht stillschweigend gesaeubert: eine veraenderte
            # Kopfzeile waere ein anderer Beleg als der beabsichtigte).
            for name, value in (extra_headers or ()):
                sname, svalue = str(name), str(value)
                if any(c in sname or c in svalue for c in ("\r", "\n")):
                    logger.warning("Zusatz-Kopfzeile verworfen (Zeilenumbruch "
                                   "im Namen oder Wert): %r", sname)
                    continue
                self.send_header(sname, svalue)
            # Build 503 (Vorfall 2026-07-24): OHNE Cache-Control hielt der
            # Browser eine veraltete cockpit.html im Cache — die neue Sicht
            # 'AD-Abgleich' meldete "Modul nicht geladen", weil die alte HTML
            # cockpit_adsync.js nie referenzierte (und der Server folglich
            # auch keinen 404 loggte). 'no-cache' erzwingt die Revalidierung
            # bei JEDEM Zugriff; ohne Validatoren (ETag/Last-Modified —
            # bewusst nicht ausgebaut) ist das ein frischer Abruf. Der Server
            # laeuft lokal (127.0.0.2), der Overhead ist bedeutungslos;
            # dafuer greifen Deploys sofort. Gilt fuer ALLE Nicht-SSE-
            # Antworten (SSE setzt no-cache bereits selbst).
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return


class ManagementHTTPServer(socketserver.ThreadingMixIn,
                           http.server.HTTPServer):
    """
    Threading-Server fuer das Management-Backend. Bindet nur localhost. Haelt die
    ManagementApp und die beim Start aufgeloeste person_id.
    """

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self, host: str, port: int, app: ManagementApp, person_id: int, *,
        sse_poll_sec: float = DEFAULT_SSE_POLL_SEC,
    ) -> None:
        self.app = app
        self.person_id = person_id
        self.sse_poll_sec = sse_poll_sec
        # Wartungsmodus (Build 437): wird von management.py gesetzt. Ist es None,
        # bleibt der Request-Pfad unveraendert.
        self.maintenance_gate = None
        super().__init__((host, port), ManagementRequestHandler)

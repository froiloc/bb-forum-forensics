# =============================================================================
# server/http_server.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Basiert auf http.server.HTTPServer aus der Python-Standardbibliothek.
#   Lauscht auf der konfigurierten IP (Standard: 127.0.0.2) und leitet
#   alle Requests an router.py weiter.
#
# Two-Phase-Load-Prinzip:
#   Beim ersten Aufruf einer Forum-URL liefert shell_handler.py eine leere
#   Shell-HTML aus. toolbar.js lädt den BLOB-Inhalt danach per AJAX nach.
#   Alle weiteren Navigationen laufen ausschließlich über AJAX.
#   Unterscheidung Shell vs. AJAX: Header "X-Forensic-Request: ajax"
#
# POST-Requests:
#   Alle POST-Requests außerhalb von /_forensic/ → HTTP 404. Keine Ausnahmen.
#   Formulare im Forum dürfen nicht ausgeführt werden.
#
# Threading:
#   ThreadingHTTPServer wird verwendet, damit mehrere Browser-Tabs
#   gleichzeitig bedient werden können. check_same_thread=False in
#   connection_manager.py ermöglicht dies.
#
# Fehlerbehandlung beim Binden (ForensicHTTPServerBindError):
#   Der Konstruktor fängt OSError beim Binden des Server-Sockets differenziert ab:
#   - EADDRINUSE / WinError 10048: Port bereits belegt.
#     Windows-Diagnosebefehl wird ausgegeben: netstat -ano | findstr ":<port>"
#   - PermissionError / EACCES / WinError 10013: Fehlende Rechte für Port < 1024.
#     Hinweis auf "Als Administrator ausführen" oder Port-Änderung.
#   - WSAEADDRNOTAVAIL / WinError 10049: Ungültige Bind-Adresse (IP nicht aktiv).
#     Hinweis auf Loopback-Adapter-Konfiguration.
#   Alle drei Fälle werfen ForensicHTTPServerBindError — main.py behandelt sie
#   einheitlich mit benutzerfreundlicher Konsolenausgabe.
#
# Abhängigkeiten: http.server, socketserver, errno — ausschließlich Stdlib
# Version: v0.1.0 · Build: 029 · 2026-04-15
# =============================================================================

from __future__ import annotations

import errno
import http.server
import socketserver
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

# Header-Name zur Unterscheidung Shell-Request vs. AJAX-Request
AJAX_HEADER = "X-Forensic-Request"
AJAX_HEADER_VALUE = "ajax"

# Windows-spezifische Socket-Fehlercodes (winsock2)
# Quelle: https://docs.microsoft.com/en-us/windows/win32/winsock/windows-sockets-error-codes-2
_WINERR_ADDR_IN_USE    = 10048  # WSAEADDRINUSE    — Port bereits belegt
_WINERR_ACCESS_DENIED  = 10013  # WSAEACCES        — Fehlende Rechte
_WINERR_ADDR_NOT_AVAIL = 10049  # WSAEADDRNOTAVAIL — IP nicht lokal verfügbar


class ForensicHTTPServerBindError(Exception):
    """
    Wird geworfen, wenn der Server-Socket nicht gebunden werden kann.

    Kapselt die ursprüngliche OSError mit einer benutzerfreundlichen Meldung,
    die den Ermittelnden konkrete Handlungsoptionen gibt. Wird in main.py
    abgefangen und auf stderr ausgegeben.

    Typische Ursachen (alle Windows-PROD-relevant):
    - Port belegt (EADDRINUSE / WinError 10048)
    - Fehlende Administratorrechte für Port < 1024 (EACCES / WinError 10013)
    - IP-Adresse nicht aktiv (WSAEADDRNOTAVAIL / WinError 10049)
    """


class ForensicRequestHandler(http.server.BaseHTTPRequestHandler):
    """
    HTTP-Request-Handler für den forensischen Webserver.

    Instanzvariablen die vom Server gesetzt werden (über server-Attribut):
        self.server.bundle   — DatabaseBundle
        self.server.context  — ResolvedContext
        self.server.config   — ConfigLoader
        self.server.router   — Router-Instanz
    """

    # Unterdrückt die Standard-Konsolenausgabe von BaseHTTPRequestHandler
    # — Logging übernimmt logger.py
    def log_message(self, format: str, *args) -> None:
        logger.debug("HTTP %s", format % args)

    def log_error(self, format: str, *args) -> None:
        logger.warning("HTTP-Fehler: %s", format % args)

    def address_string(self) -> str:
        """
        Überschreibt BaseHTTPRequestHandler.address_string() um den
        Reverse-DNS-Lookup zu deaktivieren.

        Der Standard-Handler macht einen PTR-Lookup auf die Client-IP.
        Bei 127.0.0.2 gibt es keinen PTR-Record — das führt zu einem
        ~20s Timeout beim ersten Request bis der negative Cache-Eintrag
        gesetzt ist. Wir geben direkt die IP zurück.
        """
        return self.client_address[0]

    def do_GET(self) -> None:
        """Beantwortet GET-Requests."""
        self._handle_request("GET")

    def do_POST(self) -> None:
        """
        Beantwortet POST-Requests.
        Außerhalb von /_forensic/ immer HTTP 404.
        """
        self._handle_request("POST")

    def do_HEAD(self) -> None:
        """HEAD-Requests werden wie GET behandelt, aber ohne Body."""
        self._handle_request("HEAD")

    def _handle_request(self, method: str) -> None:
        """
        Zentrale Request-Verarbeitung.
        Delegiert an router.py, fängt alle unerwarteten Ausnahmen ab.
        """
        try:
            is_ajax = (
                self.headers.get(AJAX_HEADER, "").lower() == AJAX_HEADER_VALUE.lower()
            )
            self.server.router.dispatch(
                handler=self,
                method=method,
                path=self.path,
                is_ajax=is_ajax,
            )
        except Exception as exc:
            logger.error(
                "Unbehandelte Ausnahme bei Request %s %s: %s",
                method, self.path, exc, exc_info=True,
            )
            self._send_500()

    # ------------------------------------------------------------------
    # Hilfsme thoden für Response-Ausgabe
    # ------------------------------------------------------------------

    def send_response_body(
        self,
        status: int,
        body: bytes,
        content_type: str = "text/html; charset=utf-8",
        extra_headers: dict | None = None,
    ) -> None:
        """
        Sendet eine vollständige HTTP-Response mit Body.

        Args:
            status:        HTTP-Statuscode (200, 404, etc.)
            body:          Response-Body als bytes.
            content_type:  Content-Type-Header.
            extra_headers: Zusätzliche Header als Dict.
        """
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_not_in_scope(self) -> None:
        """
        Sendet HTTP 404 mit X-Forensic-Status: NOT_IN_SCOPE.
        Wird für URLs aufgerufen, die nicht in der forensic_db liegen.
        Kein stiller Fehler — Grundregel 1.
        """
        body = (
            b"<html><body><p>Diese Seite liegt nicht im Umfang "
            b"der Ermittlungen.</p></body></html>"
        )
        self.send_response_body(
            status=404,
            body=body,
            extra_headers={"X-Forensic-Status": "NOT_IN_SCOPE"},
        )

    def _send_500(self) -> None:
        """Sendet HTTP 500 bei internen Serverfehlern."""
        body = b"<html><body><p>Interner Serverfehler.</p></body></html>"
        try:
            self.send_response_body(500, body)
        except Exception:
            pass  # Verbindung bereits geschlossen


class ForensicHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """
    Forensischer HTTP-Server mit Threading-Unterstützung.

    ThreadingMixIn ermöglicht gleichzeitige Bedienung mehrerer Browser-Tabs.
    Wird von main.py initialisiert und mit Bundle/Context/Config befüllt.

    Fehler beim Binden des Sockets werden als ForensicHTTPServerBindError
    mit benutzerfreundlicher Diagnose weitergegeben (nie als nackte OSError).
    """
    daemon_threads  = True   # Threads enden automatisch wenn Hauptprozess endet
    block_on_close  = False  # Nicht auf SSE-Threads warten beim Schließen —
                             # verhindert Hänger beim ersten Browser-Request wenn
                             # ein SSE-Stream-Thread offen ist

    def __init__(
        self,
        host: str,
        port: int,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        from server.router import Router
        try:
            super().__init__((host, port), ForensicRequestHandler)
        except OSError as exc:
            raise _make_bind_error(exc, host, port) from exc

        self.bundle  = bundle
        self.context = context
        self.config  = config
        self.router  = Router(bundle, context, config)
        logger.info(
            "ForensicHTTPServer initialisiert: http://%s:%d", host, port
        )

    def serve_forever_logged(self) -> None:
        """
        Startet den Server und protokolliert Start und Stop.
        Fängt KeyboardInterrupt sauber ab.
        """
        logger.info("Server läuft. Strg+C zum Beenden.")
        try:
            self.serve_forever()
        except KeyboardInterrupt:
            logger.info("Server durch Benutzer gestoppt (KeyboardInterrupt).")
        finally:
            self.server_close()
            logger.info("Server-Socket geschlossen.")


# ---------------------------------------------------------------------------
# Hilfsfunktion: Benutzerfreundliche Bind-Fehlermeldungen
# ---------------------------------------------------------------------------

def _make_bind_error(exc: OSError, host: str, port: int) -> ForensicHTTPServerBindError:
    """
    Erzeugt aus einer OSError beim Socket-Binden eine ForensicHTTPServerBindError
    mit benutzerfreundlicher, Windows-orientierter Fehlermeldung.

    Unterschiedene Fälle:
    - Port belegt       → netstat-Diagnosebefehl
    - Kein Zugriff      → Hinweis auf Administratorrechte oder Port-Änderung
    - Adresse ungültig  → Hinweis auf Loopback-Adapter

    Args:
        exc:  Die ursprüngliche OSError vom socket.bind()-Aufruf.
        host: Konfigurierte Bind-Adresse (z.B. "127.0.0.2").
        port: Konfigurierter Port (z.B. 80).

    Returns:
        ForensicHTTPServerBindError mit sprechender Meldung.
    """
    # Windows liefert winerror, Linux errno — beide prüfen.
    winerr = getattr(exc, "winerror", None)
    err    = exc.errno

    # --- Fall 1: Port bereits belegt ---
    # Windows: WinError 10048 (WSAEADDRINUSE), Linux: errno.EADDRINUSE (98)
    if winerr == _WINERR_ADDR_IN_USE or err == errno.EADDRINUSE:
        msg = (
            f"Port {port} ist bereits belegt — der Server kann nicht starten.\n"
            f"\n"
            f"Diagnose (Eingabeaufforderung als Administrator):\n"
            f"    netstat -ano | findstr \":{port}\"\n"
            f"\n"
            f"Die Ausgabe zeigt die PID des belegenden Prozesses.\n"
            f"Mit 'tasklist /fi \"PID eq <PID>\"' kann der Prozessname ermittelt\n"
            f"und im Task-Manager beendet werden.\n"
            f"\n"
            f"Alternativ: einen anderen Port in config.yaml eintragen:\n"
            f"    server:\n"
            f"      port: 8080"
        )
        logger.error("Port %d bereits belegt (OSError: %s).", port, exc)
        return ForensicHTTPServerBindError(msg)

    # --- Fall 2: Fehlende Berechtigungen ---
    # Windows: WinError 10013 (WSAEACCES), Linux: errno.EACCES (13)
    if winerr == _WINERR_ACCESS_DENIED or err == errno.EACCES or isinstance(exc, PermissionError):
        if port < 1024:
            hinweis = (
                f"Port {port} ist ein privilegierter Port (< 1024).\n"
                f"Lösung A: Server als Administrator starten\n"
                f"          (Rechtsklick auf Eingabeaufforderung → Als Administrator).\n"
                f"Lösung B: Einen ungeschützten Port in config.yaml verwenden:\n"
                f"    server:\n"
                f"      port: 8080"
            )
        else:
            hinweis = (
                f"Zugriff auf Port {port} verweigert.\n"
                f"Bitte den Server als Administrator starten\n"
                f"(Rechtsklick auf Eingabeaufforderung → Als Administrator ausführen)."
            )
        msg = f"Fehlende Berechtigungen zum Binden an {host}:{port}.\n\n{hinweis}"
        logger.error("Fehlende Rechte für Port %d (OSError: %s).", port, exc)
        return ForensicHTTPServerBindError(msg)

    # --- Fall 3: IP-Adresse nicht verfügbar ---
    # Windows: WinError 10049 (WSAEADDRNOTAVAIL), Linux: errno.EADDRNOTAVAIL (99)
    if winerr == _WINERR_ADDR_NOT_AVAIL or err == errno.EADDRNOTAVAIL:
        msg = (
            f"Die Bind-Adresse '{host}' ist auf diesem System nicht aktiv.\n"
            f"\n"
            f"Mögliche Ursachen:\n"
            f"  - Der Loopback-Adapter für 127.0.0.2 ist nicht eingerichtet.\n"
            f"  - Die Adresse ist in config.yaml falsch konfiguriert.\n"
            f"\n"
            f"Loopback-Adapter unter Windows prüfen:\n"
            f"    netsh interface ipv4 show addresses\n"
            f"\n"
            f"Alternativ: Adresse in config.yaml ändern (z.B. 127.0.0.1):\n"
            f"    server:\n"
            f"      host: 127.0.0.1"
        )
        logger.error("Bind-Adresse '%s' nicht verfügbar (OSError: %s).", host, exc)
        return ForensicHTTPServerBindError(msg)

    # --- Fallback: unbekannter Socket-Fehler ---
    msg = (
        f"Server-Socket konnte nicht gebunden werden ({host}:{port}).\n"
        f"Systemfehler: {exc}\n"
        f"\n"
        f"Bitte Netzwerkkonfiguration und config.yaml prüfen."
    )
    logger.error("Unbekannter Bind-Fehler für %s:%d (OSError: %s).", host, port, exc)
    return ForensicHTTPServerBindError(msg)

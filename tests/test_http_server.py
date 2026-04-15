# =============================================================================
# tests/test_http_server.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite für server/http_server.py
#
# Strategie:
#   Die differenzierte Bind-Fehlerbehandlung wird durch direkte Aufrufe
#   von _make_bind_error() mit konstruierten OSError-Instanzen getestet.
#   So sind keine echten Netzwerk-Sockets erforderlich — die Tests laufen
#   vollständig isoliert und ohne Portbelegung.
#
# Abgedeckte Testfälle:
#   T01 — Port belegt (WinError 10048) → ForensicHTTPServerBindError,
#          Meldung enthält "netstat" und Portnummer
#   T02 — Port belegt (errno.EADDRINUSE) → ForensicHTTPServerBindError,
#          Meldung enthält "netstat" (Linux-Pfad)
#   T03 — Fehlende Rechte (WinError 10013), Port < 1024 → "Administrator"
#          und Hinweis auf Port-Änderung in Meldung
#   T04 — Fehlende Rechte (PermissionError), Port < 1024 → "Administrator"
#   T05 — Fehlende Rechte (WinError 10013), Port >= 1024 → "Administrator",
#          kein Hinweis auf Port-Änderung nötig
#   T06 — Ungültige Bind-Adresse (WinError 10049) → "Loopback" und "netsh"
#          in Meldung
#   T07 — Ungültige Bind-Adresse (errno.EADDRNOTAVAIL) → "Loopback"
#   T08 — Unbekannter OSError → generische Fehlermeldung, kein Absturz
#   T09 — ForensicHTTPServerBindError ist Unterklasse von Exception
#   T10 — _make_bind_error() gibt immer ForensicHTTPServerBindError zurück
#
# Version: v0.1.0 · Build: 015 · 2026-04-15
# =============================================================================

import errno
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.http_server import ForensicHTTPServerBindError, _make_bind_error


def _win_oserror(winerror: int, msg: str = "Simulierter Fehler") -> OSError:
    """
    Erstellt eine OSError-Instanz mit gesetztem winerror-Attribut.
    Simuliert Windows-Socket-Fehlercodes ohne echten Socket.
    """
    exc = OSError(msg)
    exc.winerror = winerror
    exc.errno    = None
    return exc


def _posix_oserror(err: int, msg: str = "Simulierter Fehler") -> OSError:
    """
    Erstellt eine OSError-Instanz mit gesetztem errno-Attribut.
    Simuliert POSIX-Socket-Fehlercodes.
    """
    exc = OSError(err, msg)
    # winerror explizit None setzen (nicht gesetzt auf nicht-Windows)
    exc.winerror = None
    return exc


class TestMakeBindErrorPortBelegt(unittest.TestCase):
    """T01–T02: Port bereits belegt"""

    def test_T01_port_belegt_winerror(self):
        """T01: WinError 10048 → Meldung enthält 'netstat' und Portnummer."""
        exc = _win_oserror(10048)
        result = _make_bind_error(exc, "127.0.0.2", 80)

        self.assertIsInstance(result, ForensicHTTPServerBindError)
        meldung = str(result)
        self.assertIn("netstat", meldung,
                      "Diagnosbefehl 'netstat' fehlt in der Fehlermeldung")
        self.assertIn("80", meldung,
                      "Portnummer fehlt in der Fehlermeldung")
        self.assertIn("findstr", meldung,
                      "Windows-Befehl 'findstr' fehlt in der Fehlermeldung")

    def test_T02_port_belegt_errno(self):
        """T02: errno.EADDRINUSE → Meldung enthält 'netstat' (Linux-Pfad)."""
        exc = _posix_oserror(errno.EADDRINUSE)
        result = _make_bind_error(exc, "127.0.0.1", 8080)

        self.assertIsInstance(result, ForensicHTTPServerBindError)
        meldung = str(result)
        self.assertIn("netstat", meldung)
        self.assertIn("8080", meldung)


class TestMakeBindErrorKeinZugriff(unittest.TestCase):
    """T03–T05: Fehlende Berechtigungen"""

    def test_T03_kein_zugriff_winerror_port_klein(self):
        """T03: WinError 10013, Port < 1024 → Hinweis auf Admin und Port-Änderung."""
        exc = _win_oserror(10013)
        result = _make_bind_error(exc, "127.0.0.2", 80)

        self.assertIsInstance(result, ForensicHTTPServerBindError)
        meldung = str(result)
        self.assertIn("Administrator", meldung,
                      "Admin-Hinweis fehlt bei Port < 1024")
        self.assertIn("8080", meldung,
                      "Port-Alternativvorschlag fehlt bei privilegiertem Port")

    def test_T04_permission_error_port_klein(self):
        """T04: PermissionError, Port < 1024 → Hinweis auf Admin."""
        exc = PermissionError("Zugriff verweigert")
        exc.winerror = None
        exc.errno    = errno.EACCES
        result = _make_bind_error(exc, "127.0.0.2", 443)

        self.assertIsInstance(result, ForensicHTTPServerBindError)
        meldung = str(result)
        self.assertIn("Administrator", meldung)

    def test_T05_kein_zugriff_port_gross(self):
        """T05: WinError 10013, Port >= 1024 → Admin-Hinweis, kein 8080-Vorschlag."""
        exc = _win_oserror(10013)
        result = _make_bind_error(exc, "127.0.0.2", 8080)

        self.assertIsInstance(result, ForensicHTTPServerBindError)
        meldung = str(result)
        self.assertIn("Administrator", meldung)
        # Bei Port >= 1024 ist kein alternativer Port nötig
        self.assertNotIn("port: 8080", meldung,
                         "Kein redundanter Port-Hinweis bei bereits hohem Port erwartet")


class TestMakeBindErrorUngueltigeAdresse(unittest.TestCase):
    """T06–T07: IP-Adresse nicht verfügbar"""

    def test_T06_adresse_nicht_verfuegbar_winerror(self):
        """T06: WinError 10049 → Meldung enthält Loopback-Hinweis und 'netsh'."""
        exc = _win_oserror(10049)
        result = _make_bind_error(exc, "127.0.0.2", 80)

        self.assertIsInstance(result, ForensicHTTPServerBindError)
        meldung = str(result)
        self.assertIn("127.0.0.2", meldung,
                      "Konfigurierte Adresse fehlt in Fehlermeldung")
        self.assertIn("netsh", meldung,
                      "Windows-Netzwerkdiagnose 'netsh' fehlt in Fehlermeldung")

    def test_T07_adresse_nicht_verfuegbar_errno(self):
        """T07: errno.EADDRNOTAVAIL → Loopback-Hinweis."""
        exc = _posix_oserror(errno.EADDRNOTAVAIL)
        result = _make_bind_error(exc, "127.0.0.2", 80)

        self.assertIsInstance(result, ForensicHTTPServerBindError)
        meldung = str(result)
        self.assertIn("127.0.0.2", meldung)


class TestMakeBindErrorFallback(unittest.TestCase):
    """T08–T10: Robustheit und Typsicherheit"""

    def test_T08_unbekannter_fehler_kein_absturz(self):
        """T08: Unbekannter OSError → generische Meldung, kein Absturz."""
        exc = OSError("Unbekannter Socket-Fehler")
        exc.winerror = None
        exc.errno    = 9999  # unbekannter Fehlercode

        # Darf keine Exception werfen
        result = _make_bind_error(exc, "127.0.0.2", 80)

        self.assertIsInstance(result, ForensicHTTPServerBindError)
        meldung = str(result)
        self.assertIn("127.0.0.2", meldung)
        self.assertIn("80", meldung)

    def test_T09_ist_exception_unterklasse(self):
        """T09: ForensicHTTPServerBindError ist Unterklasse von Exception."""
        self.assertTrue(issubclass(ForensicHTTPServerBindError, Exception))

    def test_T10_gibt_immer_bind_error_zurueck(self):
        """T10: _make_bind_error() gibt in allen Fällen ForensicHTTPServerBindError zurück."""
        for winerr in [10048, 10013, 10049, 99999]:
            exc = _win_oserror(winerr)
            result = _make_bind_error(exc, "127.0.0.2", 80)
            self.assertIsInstance(
                result, ForensicHTTPServerBindError,
                f"WinError {winerr} ergab kein ForensicHTTPServerBindError"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)

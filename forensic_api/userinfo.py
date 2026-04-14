# =============================================================================
# forensic_api/userinfo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Nutzerinfo-Tab
# =============================================================================
# Zweck:
#   Endpunkt GET /_forensic/userinfo — Auslieferung des Nutzerinfo-Tabs (Fenster 2).
#
# Ablauf (§5.1 Bauplan B4):
#   1. BLOB aus forensic_<uid>.db → static_pages WHERE key='userinfo' lesen
#      (Zugriff via ATTACH-Alias fdb auf der Haupt-Verbindung).
#   2. Vollständigen HTML-Rahmen aufbauen (inkl. <head> mit userinfo.css/js).
#   3. BLOB-Inhalt in <div id="userinfo-static"> einsetzen.
#   4. Leere Container für dynamische Bereiche und Read-Only-Berichtsreiter
#      vor </body> einsetzen.
#   5. HTTP 200 mit Content-Type: text/html; charset=utf-8 antworten.
#
# Fehlerfall:
#   BLOB fehlt in static_pages → HTTP 503 mit Fehlermeldung.
#   Kein stilles Versagen — forensische Grundregel 1.
#
# Datenbankzugriff:
#   fdb (forensic_<uid>.db, READ-ONLY) via ATTACH auf bundle.forensic._con.
#   Keine Schreibzugriffe — forensische Integrität (Grundregel 10 Bauplan B4).
#
# Neue Datei — Baustelle 4.
# Version: v0.1.0 · Build: 012 · 2026-04-14
# =============================================================================

from __future__ import annotations

import html as html_module
import sqlite3
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

# HTML-Rahmen für Fenster 2 (§6.1 Bauplan B4).
# Platzhalter: {username}, {user_id}, {static_content}
_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="de">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Nutzerinfo \u00b7 {username} \u00b7 ID: {user_id}</title>
    <link rel="stylesheet" href="/_forensic/userinfo.css">
  </head>
  <body>
    <div id="userinfo-static">
{static_content}
    </div>

    <!-- Chirurgisch eingesetzt beim Ausliefern \u2014 nicht im BLOB (§6.1 Bauplan B4) -->
    <div id="userinfo-dynamic" aria-live="polite">
      <!-- Ermittlungsstand \u2014 per AJAX/SSE bef\u00fcllt (§7.9 Bauplan B4) -->
    </div>
    <div id="userinfo-report-readonly">
      <!-- Read-Only-Reiter: gerenderter Berichtsstand (§8 Bauplan B4) -->
    </div>
    <script src="/_forensic/userinfo.js" defer></script>
  </body>
</html>"""

# Fehlermeldung wenn BLOB noch nicht generiert wurde (§5.1 Bauplan B4)
_ERROR_BLOB_MISSING = """\
<!DOCTYPE html>
<html lang="de">
  <head><meta charset="utf-8"><title>Nutzerinfo \u2014 Fehler</title></head>
  <body>
    <h1>Nutzerinfo-BLOB nicht generiert</h1>
    <p>B0-Phase-B f\u00fcr diesen Nutzer ausf\u00fchren.</p>
    <p>Benutzer-ID: {user_id}</p>
  </body>
</html>"""


class UserinfoEndpoint:
    """
    Endpunkt GET /_forensic/userinfo

    Liefert den statischen HTML-Rahmen mit eingebettetem BLOB aus
    forensic_<uid>.db → static_pages['userinfo'].
    Schreibt nicht — forensische Integrität gewahrt (Grundregel 10 Bauplan B4).
    """

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        self._bundle  = bundle
        self._context = context
        self._config  = config

    def handle(self, handler: "ForensicRequestHandler") -> None:
        """
        Verarbeitet GET /_forensic/userinfo.

        Args:
            handler: ForensicRequestHandler-Instanz.
        """
        user_id  = self._context.user_id
        username = self._context.username

        # BLOB aus fdb.static_pages lesen
        blob_html = self._load_blob()

        if blob_html is None:
            # 503: BLOB nicht vorhanden — B0-Phase-B noch nicht ausgeführt
            logger.warning(
                "userinfo BLOB fehlt für user_id=%d — HTTP 503 gesendet", user_id
            )
            body = _ERROR_BLOB_MISSING.format(user_id=user_id).encode("utf-8")
            handler.send_response_body(
                503, body, content_type="text/html; charset=utf-8"
            )
            return

        # Vollständige HTML-Seite zusammenbauen
        safe_username = html_module.escape(username or f"uid_{user_id}")
        page_html = _HTML_TEMPLATE.format(
            username=safe_username,
            user_id=user_id,
            static_content=blob_html,
        )

        body = page_html.encode("utf-8")
        handler.send_response_body(200, body, content_type="text/html; charset=utf-8")
        logger.debug(
            "/_forensic/userinfo ausgeliefert: user_id=%d (%d bytes)", user_id, len(body)
        )

    def _load_blob(self) -> "str | None":
        """
        Liest den HTML-BLOB aus fdb.static_pages (key='userinfo').

        Zugriff erfolgt über die ATTACH-Verbindung von ForensicDb._con,
        die das Alias fdb für forensic_<uid>.db enthält.

        Gibt None zurück wenn Tabelle fehlt oder kein Eintrag vorhanden.
        Kein stilles Versagen — None wird als HTTP 503 gemeldet (Grundregel 1).
        """
        try:
            # Zugriff via fdb-Alias der ATTACH-Verbindung
            con: sqlite3.Connection = self._bundle.forensic._con
            row = con.execute(
                "SELECT html FROM fdb.static_pages WHERE key = 'userinfo'"
            ).fetchone()
            if row is None:
                logger.info("fdb.static_pages: kein 'userinfo'-Eintrag für user_id=%d",
                            self._context.user_id)
                return None
            return str(row[0]) if row[0] else None
        except sqlite3.OperationalError as exc:
            # Tabelle static_pages existiert noch nicht (B0-Phase-B nicht ausgeführt)
            logger.warning(
                "fdb.static_pages nicht lesbar (B0-Phase-B ausstehend?): %s", exc
            )
            return None
        except Exception as exc:
            logger.error("_load_blob: unerwarteter Fehler: %s", exc)
            return None

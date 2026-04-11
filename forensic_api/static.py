# =============================================================================
# forensic_api/static.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkte /_forensic/toolbar.js und /_forensic/toolbar.css
#   Liefert die Werkzeugbalken-Ressourcen aus toolbar/ aus.
#
# Liest die Dateien aus dem toolbar/-Verzeichnis relativ zum Skript-
# verzeichnis. Falls eine Datei nicht gefunden wird, wird ein leerer
# Platzhalter ausgeliefert (kein 404 — der Toolbar muss immer laden).
#
# Version: v0.1.0 · Build: 010 · 2026-04-10
# =============================================================================

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler

logger = get_logger(__name__)

# Verzeichnis der Toolbar-Ressourcen relativ zu diesem Modul
_TOOLBAR_DIR = Path(__file__).resolve().parent.parent / "toolbar"

_RESOURCES = {
    "/_forensic/toolbar.js":  ("toolbar.js",  "application/javascript; charset=utf-8"),
    "/_forensic/toolbar.css": ("toolbar.css", "text/css; charset=utf-8"),
}


class StaticEndpoint:
    """Liefert toolbar.js und toolbar.css aus."""

    def handle(
        self,
        handler: "ForensicRequestHandler",
        url_path: str,
    ) -> None:
        """
        Verarbeitet GET /_forensic/toolbar.js oder /_forensic/toolbar.css

        Args:
            handler:  ForensicRequestHandler-Instanz.
            url_path: Angeforderter Pfad.
        """
        entry = _RESOURCES.get(url_path)
        if entry is None:
            handler.send_response_body(404, b"")
            return

        filename, mime_type = entry
        file_path = _TOOLBAR_DIR / filename

        try:
            data = file_path.read_bytes()
            logger.debug("Static: '%s' ausgeliefert (%d bytes)", url_path, len(data))
        except FileNotFoundError:
            logger.warning(
                "Toolbar-Ressource nicht gefunden: '%s' — leerer Platzhalter",
                file_path,
            )
            data = b""

        handler.send_response_body(200, data, content_type=mime_type)

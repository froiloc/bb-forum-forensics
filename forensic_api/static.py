# =============================================================================
# forensic_api/static.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkte für statische Frontend-Ressourcen:
#     /_forensic/toolbar.js   (GET)  → toolbar/toolbar.js
#     /_forensic/toolbar.css  (GET)  → toolbar/toolbar.css
#     /_forensic/userinfo.js  (GET)  → userinfo/userinfo.js   [NEU Build 012]
#     /_forensic/userinfo.css (GET)  → userinfo/userinfo.css  [NEU Build 012]
#
# Falls eine Datei nicht gefunden wird, wird ein leerer Platzhalter ausgeliefert
# (kein 404 — der Toolbar und der Nutzerinfo-Tab müssen immer laden).
#
# Änderungen gegenüber Build 010:
#   - _USERINFO_DIR: Neues Verzeichnis userinfo/ für Baustelle-4-Ressourcen.
#   - _RESOURCES: Zwei neue Einträge für userinfo.js und userinfo.css.
#
# Version: v0.1.0 · Build: 012 · 2026-04-14
# =============================================================================

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler

logger = get_logger(__name__)

# Verzeichnisse relativ zu diesem Modul
_BASE_DIR     = Path(__file__).resolve().parent.parent
_TOOLBAR_DIR  = _BASE_DIR / "toolbar"
_USERINFO_DIR = _BASE_DIR / "userinfo"   # NEU Build 012 — Baustelle 4

# Ressourcen-Registry: Pfad → (Dateiname, MIME-Type, Verzeichnis)
_RESOURCES: dict[str, tuple[str, str, Path]] = {
    "/_forensic/toolbar.js":   ("toolbar.js",   "application/javascript; charset=utf-8", _TOOLBAR_DIR),
    "/_forensic/toolbar.css":  ("toolbar.css",  "text/css; charset=utf-8",               _TOOLBAR_DIR),
    "/_forensic/userinfo.js":  ("userinfo.js",  "application/javascript; charset=utf-8", _USERINFO_DIR),
    "/_forensic/userinfo.css": ("userinfo.css", "text/css; charset=utf-8",               _USERINFO_DIR),
}


class StaticEndpoint:
    """
    Liefert statische Frontend-Ressourcen für Toolbar (Baustelle 3)
    und Nutzerinfo-Tab (Baustelle 4) aus.

    Kein 404 bei fehlenden Dateien — leerer Platzhalter wird ausgeliefert,
    damit der Browser nicht blockiert.
    """

    def handle(
        self,
        handler: "ForensicRequestHandler",
        url_path: str,
    ) -> None:
        """
        Verarbeitet GET-Request für eine statische Ressource.

        Args:
            handler:  ForensicRequestHandler-Instanz.
            url_path: Angeforderter Pfad (z.B. /_forensic/toolbar.js).
        """
        entry = _RESOURCES.get(url_path)
        if entry is None:
            logger.warning("StaticEndpoint: unbekannter Pfad '%s'", url_path)
            handler.send_response_body(404, b"")
            return

        filename, mime_type, directory = entry
        file_path = directory / filename

        try:
            data = file_path.read_bytes()
            logger.debug("Static: '%s' ausgeliefert (%d bytes)", url_path, len(data))
        except FileNotFoundError:
            logger.warning(
                "Statische Ressource nicht gefunden: '%s' — leerer Platzhalter",
                file_path,
            )
            data = b""

        handler.send_response_body(200, data, content_type=mime_type)

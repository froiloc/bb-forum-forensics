# =============================================================================
# forensic_api/status.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/status (GET)
#   Liefert den aktuellen Serverstatus als JSON.
#   Wird von toolbar.js beim Start geladen und für Diagnosezwecke verwendet.
#
# Response (JSON):
#   {
#     "mode":             "job|cli|support",
#     "subject_id":       42,
#     "username":         "beschuldigter42",
#     "investigator_id":  3,
#     "page_count":       1234,
#     "annotation_count": 17,
#     "scrape_context_warning": false,
#     "ts":               1700000000,
#     "version":          "v0.1.0-build010"
#   }
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# =============================================================================

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

# Build 190: SERVER_VERSION dynamisch aus build.json laden.
# War hartcodiert "v0.1.0-build042" — blieb immer auf Build 042 egal welche
# build.json deployed wurde. Toolbar.js loggt diesen Wert und zeigte daher
# immer "build042" in der Console, obwohl neuere Builds liefen.
# Beleg: Projektgespraech 2026-05-12.
def _load_server_version() -> str:
    """Liest build-Nummer aus build.json neben dieser Datei."""
    import json as _json
    from pathlib import Path as _Path
    try:
        build_file = _Path(__file__).parent.parent / "build.json"
        data = _json.loads(build_file.read_text(encoding="utf-8"))
        build = data.get("build", "?")
        return f"v0.1.0-build{build:03d}" if isinstance(build, int) else f"v0.1.0-build{build}"
    except Exception:
        return "v0.1.0-buildUNKNOWN"

SERVER_VERSION = _load_server_version()


class StatusEndpoint:
    """Endpunkt /_forensic/status — liefert Serverstatus als JSON."""

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        self._bundle  = bundle
        self._context = context

    def handle(self, handler: "ForensicRequestHandler") -> None:
        """Verarbeitet GET /_forensic/status"""
        try:
            page_count       = self._bundle.forensic.page_count()
            annotation_count = self._bundle.evidence.annotation_count()
            # Bug 2.86 (Build 176): Forum-Username des Beschuldigten aus forensic_meta.
            # forensic_meta.key='username' enthält den echten Forum-Benutzernamen.
            # context.username ist ein Fallback (z.B. "uid_538299"), der greift wenn
            # forensic_meta keinen Eintrag hat.
            # Beleg: forensic_db.get_meta() + Projektgespräch 2026-05-12.
            forum_username = self._bundle.forensic.get_meta("username") or \
                             self._context.username or ""
            forum_user_id  = self._bundle.forensic.get_meta("user_id") or \
                             str(self._context.subject_id or "")
        except Exception as exc:
            logger.warning("Statusabfrage: DB-Zugriff fehlgeschlagen: %s", exc)
            page_count       = -1
            annotation_count = -1
            forum_username   = self._context.username or ""
            forum_user_id    = str(self._context.subject_id or "")

        # Beleg: Projektgespräch — Bug 2.67: investigator_username war nicht im
        # Status-Response enthalten. toolbar.js nutzte fälschlicherweise
        # s.username (= Beschuldigter) als investigatorUsername statt
        # s.investigator_username (= Ermittler, z.B. paul).
        # Build 175: investigator_username aus context.investigator_username ergänzt.
        # Build 176 (Bug 2.86): forum_username + forum_user_id ergänzt.
        status = {
            "mode":                  self._context.mode,
            "subject_id":            self._context.subject_id,
            "username":              self._context.username,
            "investigator_id":       self._context.investigator_id,
            "investigator_username": getattr(self._context, "investigator_username", ""),
            "forum_username":        forum_username,
            "forum_user_id":         forum_user_id,
            "page_count":            page_count,
            "annotation_count":      annotation_count,
            "forum_hostname":        self._bundle.forensic.get_meta("domainname") or "",
            "ts":                    int(time.time()),
            "version":               SERVER_VERSION,
        }

        body = json.dumps(status, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(
            200, body, content_type="application/json; charset=utf-8"
        )
        logger.debug("/_forensic/status ausgeliefert")

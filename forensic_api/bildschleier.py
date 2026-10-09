# =============================================================================
# forensic_api/bildschleier.py
# IT-Forensisches Ermittlungswerkzeug — Bildschleier (Build 772)
# =============================================================================
# Zweck:
#   Endpunkte des Bildschleiers im Forenviewer:
#
#     GET  /_forensic/image-veil       -> {veiled, locked, reason, tooltip}
#     POST /_forensic/image-veil       Rumpf {"veiled": true|false}
#                                      -> 200 neuer Zustand
#                                      -> 400 Rumpf unbrauchbar
#                                      -> 403 Umschalten nicht zulaessig
#                                         (gesperrt; Grund im Rumpf)
#     GET  /_forensic/image-veil.css   -> die Grundregel (alles verschleiern)
#
#   Die Person kommt AUSSCHLIESSLICH aus dem Kontext des Webservers
#   (context.investigator_id) — ein Rumpf kann keine andere Person nennen.
#   Das Recht prueft der Schreibweg selbst (BildschleierRepo.setzen); hier
#   wird vorab gelesen, um 403 statt 500 zu antworten.
#
#   Die Antwort-Schluessel sind englisch (externe Schnittstelle), die Texte
#   fuer die Anwendung deutsch.
#
# Version: v0.8.772 · Build: 772 · 2026-10-09
# =============================================================================

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any, Dict

from core.bildschleier_dienst import dienst
from core.logger import get_logger
from management.bildschleier.bildschleier_repo import BildschleierFehler

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)


def _json(handler: "ForensicRequestHandler", status: int,
          daten: Dict[str, Any]) -> None:
    handler.send_response_body(
        status, json.dumps(daten, ensure_ascii=False).encode("utf-8"),
        content_type="application/json; charset=utf-8",
        extra_headers={"Cache-Control": "no-store"})


class BildschleierEndpoint:
    """GET/POST /_forensic/image-veil und GET /_forensic/image-veil.css."""

    def __init__(self, bundle: "DatabaseBundle", context: "ResolvedContext",
                 config: "ConfigLoader") -> None:
        self._bundle = bundle
        self._context = context
        self._config = config

    def _dienst(self):
        return dienst(self._config, self._context)

    # ------------------------------------------------------------------ GET
    def handle_get(self, handler: "ForensicRequestHandler") -> None:
        _json(handler, 200, self._dienst().aktualisieren().to_dict())

    # ----------------------------------------------------------------- POST
    def handle_post(self, handler: "ForensicRequestHandler",
                    body: bytes) -> None:
        try:
            daten = json.loads(body.decode("utf-8")) if body else None
        except (ValueError, UnicodeDecodeError) as exc:
            _json(handler, 400, {"error": "bad_json", "detail": str(exc)})
            return
        if not isinstance(daten, dict) or not isinstance(daten.get("veiled"), bool):
            _json(handler, 400, {
                "error": "bad_request",
                "detail": "Erwartet wird {\"veiled\": true|false}."})
            return

        d = self._dienst()
        vorher = d.aktualisieren()
        if vorher.locked:
            logger.info("Bildschleier: Umschalten abgewiesen (Grund %s).",
                        vorher.reason)
            antwort = vorher.to_dict()
            antwort.update({"error": "forbidden",
                            "capability": "imageveil.lift"})
            _json(handler, 403, antwort)
            return
        try:
            nachher = d.setzen(daten["veiled"])
        except BildschleierFehler as exc:
            # Zwischen Lesen und Schreiben kann das Recht entzogen worden sein.
            logger.warning("Bildschleier: Umschalten abgewiesen: %s", exc)
            antwort = d.aktualisieren().to_dict()
            antwort.update({"error": "forbidden", "detail": str(exc),
                            "capability": "imageveil.lift"})
            _json(handler, 403, antwort)
            return
        except sqlite3.Error as exc:
            logger.error("Bildschleier: Speichern fehlgeschlagen: %s", exc)
            _json(handler, 500, {"error": "store_failed", "detail": str(exc)})
            return
        _json(handler, 200, nachher.to_dict())

    # ------------------------------------------------------------------ CSS
    def handle_css(self, handler: "ForensicRequestHandler") -> None:
        handler.send_response_body(
            200, self._dienst().grundregel.stylesheet().encode("utf-8"),
            content_type="text/css; charset=utf-8",
            extra_headers={"Cache-Control": "no-store"})

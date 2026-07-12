# =============================================================================
# forensic_api/validation_rules_ep.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# =============================================================================
# Zweck:
#   GET /_forensic/validation_rules
#     Liefert den zentralen Katalog der Formatregeln fuer Eingabefelder
#     (config.yaml -> validation.rules) an den Client.
#
#   Der Client (placeholder_wizard.js, Build 389) loest damit den Verweis
#   'rule:<name>' im 5. Feld eines Platzhalters auf und prueft SCHON WAEHREND
#   DER EINGABE. Dieselben Regeln werden beim Einreichen serverseitig noch
#   einmal geprueft (forensic_api/report.py -> _validate_report_fields):
#   der Client-Check ist Bedienkomfort, der Server-Check ist die Zusicherung.
#
# Antwort:
#   { "rules": { "spurennummer": { "pattern": "...", "transform": "upper",
#                                  "hint": "..." } } }
#
# WARUM PRO ANFRAGE NEU AUFGEBAUT:
#   ValidationRules liest aus der bereits geladenen ConfigLoader-Instanz
#   (kein Dateizugriff). Der Aufbau ist damit billig, und eine per
#   apply_cli_overrides geaenderte Konfiguration schlaegt sofort durch.
#
# Beleg: Bauplan Build 388 §3, Projektgespraech 2026-07-12
# Version: v0.7.388 · Build: 388 · 2026-07-12
# =============================================================================

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from core.logger import get_logger
from core.validation_rules import ValidationRules

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from core.config_loader import ConfigLoader

logger = get_logger(__name__)


class ValidationRulesEndpoint:
    """Endpunkt fuer GET /_forensic/validation_rules."""

    def __init__(self, config: "ConfigLoader") -> None:
        self._config = config

    def handle_get(self, handler: "ForensicRequestHandler") -> None:
        rules = ValidationRules(self._config).as_public_dict()

        if not rules:
            # GRUNDREGEL 1: Ein leerer Katalog ist ein Missstand, kein
            # Normalzustand — sonst pruefen Bausteine mit 'rule:'-Verweis
            # klammheimlich gar nichts mehr.
            logger.warning(
                "GET /_forensic/validation_rules: Der Regel-Katalog ist LEER. "
                "Bausteine mit einem 'rule:'-Verweis koennen im Browser nicht "
                "geprueft werden (die Serverpruefung beim Einreichen lehnt sie "
                "dann ab). Bitte 'validation.rules' in config.yaml pruefen."
            )

        handler.send_response_body(
            200,
            json.dumps({"rules": rules}, ensure_ascii=False).encode("utf-8"),
            content_type="application/json; charset=utf-8",
        )

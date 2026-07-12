# =============================================================================
# core/validation_rules.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# =============================================================================
# Zweck:
#   ZENTRALER Katalog der Formatregeln fuer Platzhalter-Eingabefelder
#   ({{m:...}} / {{o:...}}), gelesen aus config.yaml -> validation.rules.
#
#   Warum zentral und nicht im Baustein-Text (Alt-Form: Base64-Regex als
#   5. Feld des Platzhalters)?
#     Die Base64-Form vergraebt die Regex im Modultext in templates.db.
#     Ein neues Spurennummern-Format haette bedeutet: Modultext aendern,
#     Base64 neu kodieren, Seed-Skript nachziehen. Der Katalog erlaubt es,
#     ein weiteres Format aufzunehmen, indem NUR config.yaml erweitert und
#     der Server neu gestartet wird — ohne Code- und ohne DB-Aenderung.
#     Beleg: Entwicklervorgabe Projektgespraech 2026-07-12.
#
#   Der Baustein verweist dann nur noch symbolisch:
#     {{m:spurennummer||Spurennummer der Vorgangsverwaltung|rule:spurennummer}}
#
# config.yaml:
#   validation:
#     rules:
#       spurennummer:
#         pattern:   "^(AIW|R3X|FBL|AMZ|BRU)\\d+$"
#         transform: "upper"        # 'upper' | 'lower' | 'strip' | 'none'
#         hint:      "AIW/R3X/FBL/AMZ/BRU gefolgt von Ziffern, z. B. AIW12345"
#
# GRUNDREGEL 1 (kein stilles Uebergehen):
#   - Ein Baustein, der auf eine NICHT existierende Regel verweist, ist ein
#     Missstand. validate() liefert dafuer eine klare Fehlermeldung und laesst
#     die Eingabe NICHT stillschweigend durchgehen.
#   - Eine Regel mit fehlerhafter Regex wird beim Laden protokolliert und als
#     unbrauchbar markiert — sie taeuscht keine Pruefung vor.
#
# Beleg: Bauplan Build 388 §3, Projektgespraech 2026-07-12
# Version: v0.7.388 · Build: 388 · 2026-07-12
# =============================================================================

from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple, Optional

from core.logger import get_logger

if TYPE_CHECKING:
    from core.config_loader import ConfigLoader

logger = get_logger(__name__)

_VALID_TRANSFORMS = ("none", "upper", "lower", "strip")


class RuleResult(NamedTuple):
    """Ergebnis einer Pruefung."""
    ok: bool
    value: str      # der NORMALISIERTE Wert (nach transform) — so wird gespeichert
    message: str    # leer wenn ok


class ValidationRules:
    """
    Katalog der Formatregeln. Wird einmalig aus der ConfigLoader-Instanz
    aufgebaut (Serverstart) und ist danach unveraenderlich.
    """

    def __init__(self, config: "ConfigLoader") -> None:
        self._rules: dict[str, dict] = {}
        raw = config.get("validation.rules", {}) or {}

        if not isinstance(raw, dict):
            logger.error(
                "validation.rules in config.yaml ist kein Abbildungsknoten "
                "(gefunden: %s) — es werden KEINE Regeln geladen.", type(raw).__name__
            )
            raw = {}

        for name, spec in raw.items():
            if not isinstance(spec, dict):
                logger.error(
                    "Validierungsregel '%s' ist fehlerhaft aufgebaut und wird "
                    "VERWORFEN (erwartet: pattern/transform/hint).", name
                )
                continue

            pattern = str(spec.get("pattern", "") or "")
            if not pattern:
                logger.error(
                    "Validierungsregel '%s' hat kein 'pattern' und wird VERWORFEN.",
                    name,
                )
                continue

            try:
                compiled = re.compile(pattern)
            except re.error as exc:
                # Eine kaputte Regex darf keine Pruefung VORTAEUSCHEN.
                logger.error(
                    "Validierungsregel '%s' enthaelt eine ungueltige Regex "
                    "(%s) und wird VERWORFEN: %s", name, pattern, exc,
                )
                continue

            transform = str(spec.get("transform", "none") or "none").lower()
            if transform not in _VALID_TRANSFORMS:
                logger.error(
                    "Validierungsregel '%s': transform='%s' ist unbekannt "
                    "(erlaubt: %s). Es wird 'none' verwendet.",
                    name, transform, ", ".join(_VALID_TRANSFORMS),
                )
                transform = "none"

            self._rules[name] = {
                "pattern":   pattern,
                "compiled":  compiled,
                "transform": transform,
                "hint":      str(spec.get("hint", "") or ""),
            }
            logger.info(
                "Validierungsregel geladen: '%s' pattern=%s transform=%s",
                name, pattern, transform,
            )

        logger.info("ValidationRules: %d Regel(n) geladen.", len(self._rules))

    # ------------------------------------------------------------------
    # Lesen
    # ------------------------------------------------------------------

    def has(self, name: str) -> bool:
        return name in self._rules

    def get(self, name: str) -> Optional[dict]:
        return self._rules.get(name)

    def as_public_dict(self) -> dict:
        """
        Katalog fuer den Client (GET /_forensic/validation_rules).
        Das kompilierte Regex-Objekt wird nicht uebertragen; der Client
        kompiliert 'pattern' selbst mit JS-RegExp.

        ACHTUNG (bewusste Festlegung): Die Muster sind so gehalten, dass sie
        in Python UND JavaScript gleich bedeuten (keine Lookbehinds, keine
        benannten Gruppen). Wer eine Regel ergaenzt, muss das einhalten —
        sonst weichen Client- und Serverpruefung voneinander ab.
        """
        return {
            name: {
                "pattern":   spec["pattern"],
                "transform": spec["transform"],
                "hint":      spec["hint"],
            }
            for name, spec in self._rules.items()
        }

    # ------------------------------------------------------------------
    # Anwenden
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_transform(value: str, transform: str) -> str:
        if transform == "upper":
            return value.strip().upper()
        if transform == "lower":
            return value.strip().lower()
        if transform == "strip":
            return value.strip()
        return value

    def normalize(self, rule_name: str, value: str) -> str:
        """
        Wendet NUR die Normalisierung an (ohne Pruefung). Wird beim Speichern
        gebraucht, damit in der Akte einheitlich z. B. Grossschreibung steht.
        Unbekannte Regel -> Wert unveraendert (die Pruefung meldet den Missstand).
        """
        spec = self._rules.get(rule_name)
        if spec is None:
            return value
        return self._apply_transform(value, spec["transform"])

    def validate(self, rule_name: str, value: str) -> RuleResult:
        """
        Prueft einen Wert gegen die benannte Regel.

        Reihenfolge (Entwicklervorgabe): ERST normalisieren (z. B. Uppercase),
        DANN gegen das Muster pruefen. Der zurueckgegebene Wert ist der
        normalisierte — der Aufrufer speichert diesen.
        """
        spec = self._rules.get(rule_name)
        if spec is None:
            # GRUNDREGEL 1: Nicht still durchwinken.
            return RuleResult(
                ok=False,
                value=value,
                message=(
                    "Der Baustein verweist auf die Formatregel '%s', die in "
                    "der Serverkonfiguration (validation.rules) nicht "
                    "existiert. Der Wert kann nicht geprueft werden."
                    % rule_name
                ),
            )

        normalized = self._apply_transform(value, spec["transform"])

        if spec["compiled"].match(normalized) is None:
            hint = spec["hint"] or ("erwartetes Muster: %s" % spec["pattern"])
            return RuleResult(
                ok=False,
                value=normalized,
                message="Der Wert «%s» entspricht nicht dem geforderten Format (%s)."
                        % (normalized, hint),
            )

        return RuleResult(ok=True, value=normalized, message="")

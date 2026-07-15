# =============================================================================
# management/templates_admin/module_validator.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — W1 (Build 426): Validierung der Baustein-Module
# =============================================================================
# Zweck:
#   Prueft ein BAUSTEIN-MODUL (templates.db.report_modules) VOR dem Schreiben.
#   Ein Modul ist ein wiederverwendbarer Textbaustein (Freitext-body), den der
#   Berichtseditor ueber seine STABILE Kennung module_key einfuegt (Build 341:
#   reorganisationssicher, anders als die AUTOINCREMENT-id). Der body ist
#   FREITEXT und darf Platzhalter {{a:}}/{{m:}}/{{o:}} enthalten, die erst beim
#   RENDERN des konkreten Berichts aufgeloest werden — hier NICHT.
#
#   Regeln (deckungsgleich mit dem report_modules-Schema):
#     module_key : Pflicht + Zeichenraum [A-Za-z0-9._-] (stabiler Schluessel,
#                  wird programmatisch geladen -> enger, kollisionsarmer Raum;
#                  deckungsgleich mit Query-/Vorlagen-Kennungen).
#     title      : Pflicht (NOT NULL).
#     role       : Pflicht, aus ROLES (CHECK des Schemas).
#     topic      : Pflicht (NOT NULL) — Gruppierung im Auswahl-Panel.
#     body       : Pflicht (NOT NULL) — der eigentliche Bausteintext.
#     description: NULLABLE (leer/NULL erlaubt).
#
#   HINWEIS zum module_key: das Schema erlaubt NULL (Altbestand vor der
#   module_key-Migration). Fuer NEU AUTORIERTE Module verlangen wir den Schluessel
#   dennoch verbindlich — nur so ist der Baustein spaeter stabil referenzierbar
#   (get_module_by_key). Kein stiller Baustein ohne Kennung.
#
# Version: v0.7.426 · Build: 426 · 2026-07-15
# =============================================================================

from __future__ import annotations

import re
from typing import Any, Dict, List

# Stabiler Schluessel-Zeichenraum (deckungsgleich mit Query-/Vorlagen-Kennungen).
_KEY_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# Zulaessige Rollen (CHECK von report_modules.role).
ROLES = ("intro", "conclusion", "body", "legal", "appendix", "closing")

# Platzhalter-Regex — ZEICHENGLEICH zu report_render.placeholder_resolver._CHIP_RE
# bzw. userinfo/placeholder_chips.js:73 (dort ist die Wahrheit). Bewusste,
# belegte Doppelung (wie schon zwischen JS und Resolver): dieser Validator ist
# read-only und darf den Resolver nicht importieren (privates Symbol). Gruppe 1 =
# Typ, Gruppe 2 = name.
_CHIP_RE = re.compile(
    r"\{\{(a|auto|m|mandatory|o|optional):([A-Za-z0-9._-]+)"
    r"(?:\|([^|}\n]*))?(?:\|([^|}\n]*))?(?:\|([^|}\n]*))?\}\}"
)

# Normalisierung der Platzhalter-Typen auf die drei Kanonischen (fuer die
# Vorschau-Zaehlung).
_KIND = {"a": "auto", "auto": "auto",
         "m": "mandatory", "mandatory": "mandatory",
         "o": "optional", "optional": "optional"}


class ModuleValidationError(Exception):
    """Ein Baustein-Modul verletzt die Regeln (Liste in .errors)."""

    def __init__(self, errors: List[str]) -> None:
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def validate_static(m: Dict[str, Any]) -> List[str]:
    """Statische Pruefung eines Bausteins. Gibt Fehlerliste zurueck (kein raise)."""
    errors: List[str] = []

    key = str(m.get("module_key") or "").strip()
    if not key:
        errors.append("module_key fehlt.")
    elif not _KEY_RE.match(key):
        errors.append("module_key enthaelt unzulaessige Zeichen "
                      "(erlaubt: A-Z a-z 0-9 . _ -).")

    if not str(m.get("title") or "").strip():
        errors.append("title fehlt.")

    role = m.get("role")
    if role not in ROLES:
        errors.append("role '%s' ungueltig (erlaubt: %s)."
                      % (role, ", ".join(ROLES)))

    if not str(m.get("topic") or "").strip():
        errors.append("topic fehlt.")

    if not str(m.get("body") or "").strip():
        errors.append("body fehlt (der Bausteintext darf nicht leer sein).")

    # description ist NULLABLE -> keine Pruefung.

    return errors


def placeholder_summary(body: Any) -> List[Dict[str, Any]]:
    """
    Zaehlt die Platzhalter im body nach kanonischem Typ (auto/mandatory/optional)
    — fuer die schreibfreie Vorschau ("welche Platzhalter stecken im Baustein?").
    Reihenfolge: erstes Auftreten des Typs. REIN und ohne Seiteneffekt.
    """
    text = "" if body is None else str(body)
    order: List[str] = []
    counts: Dict[str, int] = {}
    for match in _CHIP_RE.finditer(text):
        kind = _KIND.get(match.group(1), match.group(1))
        if kind not in counts:
            counts[kind] = 0
            order.append(kind)
        counts[kind] += 1
    return [{"kind": k, "count": counts[k]} for k in order]

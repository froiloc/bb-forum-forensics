# =============================================================================
# core/typed_validation.py
# IT-Forensisches Ermittlungswerkzeug — gemeinsame typisierte Validierung
# =============================================================================
# Zweck (Build 498):
#   SERVERSEITIGE, verbindliche Pruefung von m/o-Feldwerten gegen die
#   DB-Platzhalterdefinition (templates.placeholders.validation /
#   validation_type / validation_ci). Das ist die ZUSICHERUNG beim Einreichen —
#   der Browser (validation_rules.js::checkTyped, Build 494/497) ist nur der
#   Komfort; ein direkter POST wuerde ihn umgehen. Fuer ein gerichtsverwertbares
#   Dokument muss die Pruefung serverseitig stattfinden.
#
# DECKUNGSGLEICHHEIT (WICHTIG):
#   Diese Funktion MUSS dasselbe Ergebnis liefern wie
#   userinfo/validation_rules.js::checkTyped und die Management-Vorschau
#   (cockpit_templates.js::testRule). Deshalb:
#     - regex: SUCHE (nicht verankert) — genau wie JS RegExp.test(); Anker ^/$
#       setzt die Autor:in selbst. re.IGNORECASE bei ci.
#     - list:  exakte Mitgliedschaft; bei ci Vergleich in Kleinschreibung.
#     - like:  SQL-LIKE -> verankerte RegExp (Full-Match). % = beliebig viele,
#       _ = genau ein Zeichen; uebrige Regex-Metazeichen maskiert (identische
#       Zeichenmenge wie die JS-Implementierung). re.IGNORECASE bei ci.
#   Muster duerfen keine in Python/JS unterschiedlich bedeutenden Konstrukte
#   nutzen (keine Lookbehinds, keine benannten Gruppen) — dieselbe Vorgabe wie
#   fuer den rule:-Katalog (core/validation_rules.py).
#
# Version: v0.8.498 · Build: 498 · 2026-07-22
# Beleg: mc-Wunsch harte Server-Pruefung 2026-07-22; Bauplan Platzhalter_DB §2.3.
# =============================================================================

from __future__ import annotations

import json
import re
from typing import Tuple

# Regex-Metazeichen, die im LIKE-Muster woertlich gemeint sind und daher
# maskiert werden muessen. IDENTISCHE Menge wie userinfo/validation_rules.js
# und cockpit_templates.js (Build 490/497): [.*+?^${}()|[\]\\]
_LIKE_META_RE = re.compile(r"[.*+?^${}()|[\]\\]")


def like_to_regex(pattern: str, ci: bool = False) -> "re.Pattern":
    """
    Uebersetzt ein SQL-LIKE-Muster in eine verankerte RegExp.
    % = beliebig viele Zeichen, _ = genau ein Zeichen; alles andere woertlich.
    ci=True -> re.IGNORECASE.
    """
    esc = _LIKE_META_RE.sub(lambda m: "\\" + m.group(0),
                            "" if pattern is None else str(pattern))
    esc = esc.replace("%", "[\\s\\S]*").replace("_", "[\\s\\S]")
    return re.compile("^" + esc + "$", re.IGNORECASE if ci else 0)


def check_typed(validation_type, validation, value,
                ci: bool = False) -> Tuple[bool, str]:
    """
    Prueft einen Wert gegen eine DB-Definition. Reine Funktion.

    Args:
        validation_type: '' | 'regex' | 'list' | 'like'
        validation:      KLARTEXT-Regel (Regex / JSON-Array / LIKE-Muster)
        value:           zu pruefender Wert
        ci:              case-insensitive (validation_ci)

    Returns:
        (ok, message). Ohne Pruefart/Regel -> (True, ''). Eine fehlerhafte
        hinterlegte Regel oder eine unbekannte Pruefart wird NICHT als gueltig
        durchgewunken (Grundregel 1).
    """
    raw  = "" if value is None else str(value)
    vt   = str(validation_type or "")
    rule = "" if validation is None else str(validation)
    insens = bool(ci)

    if vt == "" or rule.strip() == "":
        return True, ""

    if vt == "regex":
        try:
            rx = re.compile(rule, re.IGNORECASE if insens else 0)
        except re.error:
            return False, "Die hinterlegte Formatregel ist fehlerhaft."
        # SUCHE (wie JS RegExp.test) — nicht fullmatch.
        return (True, "") if rx.search(raw) is not None \
            else (False, "Eingabe entspricht nicht dem geforderten Format.")

    if vt == "list":
        try:
            arr = json.loads(rule)
        except (ValueError, TypeError):
            return False, "Die hinterlegte Werteliste ist fehlerhaft."
        if not isinstance(arr, list):
            return False, "Die hinterlegte Werteliste ist fehlerhaft."
        needle = raw.lower() if insens else raw
        found = any(
            (str(x).lower() if insens else str(x)) == needle for x in arr)
        return (True, "") if found \
            else (False, "Eingabe ist kein zulaessiger Wert aus der Liste.")

    if vt == "like":
        try:
            rx = like_to_regex(rule, insens)
        except re.error:
            return False, "Das hinterlegte Muster ist fehlerhaft."
        return (True, "") if rx.search(raw) is not None \
            else (False, "Eingabe entspricht nicht dem geforderten Muster.")

    return False, "Unbekannte Pruefart: " + vt

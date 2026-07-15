# =============================================================================
# management/templates_admin/template_validator.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — W3 (Build 424): Validierung der Dokumentvorlagen
# =============================================================================
# Zweck:
#   Prueft eine DOKUMENTVORLAGE (templates.db.report_templates) VOR dem Schreiben.
#   Eine Vorlage ist eine benannte, wiederverwendbare Block-Struktur, die der
#   forensische Webserver spaeter ueber ihren STABILEN template_key laedt und je
#   Block eine frische UUID vergibt (Beleg: forensic_api/report.py::insert_template,
#   Zeilen ~765-863). Deshalb ist die STRUKTUR der Bloecke hier entscheidend:
#
#     blocks : Liste von {block_type, block_data}
#       - block_type MUSS einer der NEUN bekannten Editor.js-Blocktypen sein
#         (report_render.report_source.KNOWN_BLOCK_TYPES — EINZIGE Wahrheit; kein
#         zweiter, divergierender Katalog).
#       - block_data MUSS ein Objekt (dict) sein (wird beim Einfuegen als JSON-
#         String in report_blocks.block_data abgelegt).
#
#   Jeder fehlerhafte Block wird EINZELN und mit seinem Index gemeldet — kein
#   Block wird still uebersprungen (Grundregel 1/3). Eine leere Vorlage ist
#   unzulaessig (forensic_api meldet sonst TEMPLATE_EMPTY erst zur Laufzeit).
#
#   Warum template_key-Zeichenraum [A-Za-z0-9._-]: der Schluessel wird program-
#   matisch zum Laden benutzt (get_template_by_key); ein enger, stabiler
#   Zeichenraum schuetzt vor Tippfehlern/Kollisionen und ist deckungsgleich mit
#   dem der Baustein-/Query-Kennungen.
#
#   ABGRENZUNG: Die Platzhalter IN den Bloecken ({{a:}}/{{m:}}/{{o:}}) werden
#   hier NICHT aufgeloest — das geschieht erst beim Rendern des konkreten
#   Berichts (report_render). Die Vorlage traegt nur die Struktur.
#
# Version: v0.7.424 · Build: 424 · 2026-07-15
# =============================================================================

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

# Einzige Wahrheit fuer die zulaessigen Blocktypen (kein Duplikat-Katalog).
from report_render.report_source import KNOWN_BLOCK_TYPES

# Stabiler Schluessel-Zeichenraum (deckungsgleich mit Query-/Baustein-Kennungen).
_KEY_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# Zulaessige Berichtstypen (deckungsgleich mit dem CHECK von report_templates
# und report_modules-Konsumenten).
VALID_REPORT_TYPES = ("interim", "final", "addendum")


class TemplateValidationError(Exception):
    """Eine Dokumentvorlage verletzt die Regeln (Liste in .errors)."""

    def __init__(self, errors: List[str]) -> None:
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def coerce_blocks(t: Dict[str, Any]) -> Tuple[Optional[List[Any]], Optional[str]]:
    """
    Liefert die Blockliste einer Vorlage als (blocks, error). Akzeptiert
    ENTWEDER t['blocks'] als native Liste ODER t['blocks_json'] als JSON-String
    (z.B. beim Laden aus der DB). Gibt (None, fehlermeldung) bei kaputtem JSON
    oder falschem Grundtyp zurueck — NIE eine stille Teilmenge.
    """
    if isinstance(t.get("blocks"), list):
        return t["blocks"], None
    raw = t.get("blocks_json")
    if raw is None:
        return None, "blocks fehlen (weder 'blocks' noch 'blocks_json')."
    if not isinstance(raw, str):
        return None, "blocks_json muss ein JSON-String sein."
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        return None, "blocks_json ist kein gueltiges JSON: %s" % exc
    if not isinstance(parsed, list):
        return None, "blocks_json muss eine JSON-Liste von Bloecken sein."
    return parsed, None


def validate_blocks(blocks: Any) -> List[str]:
    """
    Prueft die Blockstruktur. Meldet JEDEN fehlerhaften Block einzeln mit Index
    (kein stiller Uebersprung). Gibt eine (leere) Fehlerliste zurueck.
    """
    errors: List[str] = []
    if not isinstance(blocks, list):
        return ["blocks muss eine Liste sein."]
    if not blocks:
        return ["blocks ist leer — eine Vorlage muss mindestens einen Block "
                "enthalten."]
    for idx, blk in enumerate(blocks):
        if not isinstance(blk, dict):
            errors.append("Block %d ist kein Objekt." % idx)
            continue
        bt = blk.get("block_type")
        if not bt:
            errors.append("Block %d: block_type fehlt." % idx)
        elif bt not in KNOWN_BLOCK_TYPES:
            errors.append(
                "Block %d: unbekannter block_type '%s' (erlaubt: %s)."
                % (idx, bt, ", ".join(sorted(KNOWN_BLOCK_TYPES))))
        bd = blk.get("block_data")
        if not isinstance(bd, dict):
            errors.append("Block %d: block_data muss ein Objekt sein." % idx)
    return errors


def validate_static(t: Dict[str, Any]) -> List[str]:
    """Statische Pruefung einer Dokumentvorlage. Gibt Fehlerliste (kein raise)."""
    errors: List[str] = []

    key = str(t.get("template_key") or "").strip()
    if not key:
        errors.append("template_key fehlt.")
    elif not _KEY_RE.match(key):
        errors.append("template_key enthaelt unzulaessige Zeichen "
                      "(erlaubt: A-Z a-z 0-9 . _ -).")

    if not str(t.get("title") or "").strip():
        errors.append("title fehlt.")

    # description ist in report_templates NULLABLE -> leer/NULL beide erlaubt.

    rt = t.get("report_type")
    if rt not in VALID_REPORT_TYPES:
        errors.append("report_type '%s' ungueltig (erlaubt: %s)."
                      % (rt, ", ".join(VALID_REPORT_TYPES)))

    blocks, berr = coerce_blocks(t)
    if berr:
        errors.append(berr)
    else:
        errors.extend(validate_blocks(blocks))

    return errors


def block_type_summary(blocks: Any) -> List[Dict[str, Any]]:
    """
    Zaehlt die Blocktypen (fuer die schreibfreie Vorschau: "was steckt in der
    Vorlage?"). Reihenfolge = erstes Auftreten. REIN und ohne Seiteneffekt.
    """
    order: List[str] = []
    counts: Dict[str, int] = {}
    if isinstance(blocks, list):
        for blk in blocks:
            bt = blk.get("block_type") if isinstance(blk, dict) else None
            bt = str(bt) if bt else "?"
            if bt not in counts:
                counts[bt] = 0
                order.append(bt)
            counts[bt] += 1
    return [{"block_type": bt, "count": counts[bt]} for bt in order]

# =============================================================================
# management/templates_admin/placeholder_validator.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Platzhalter-Neuordnung (Build 489, Slice 1): Validierung der Platzhalter
# =============================================================================
# Zweck:
#   Prueft einen Platzhalter (templates.db.placeholders) VOR dem Schreiben.
#   Nachfolger des query_validator (Build 422), erweitert um die Typregeln der
#   Platzhalter-Neuordnung (Bauplan Platzhalter_DB v0.1 §3.1/§4, mc 2026-07-21):
#
#     type 'a'  (automatisch, {{a:}}):  sql_query PFLICHT (read-only SELECT,
#               nur :uid); KEINE Validierung (der Ermittler hat keinen Einfluss
#               auf eine Korrektur; DB-Werte gelten als geprueft — mc).
#     type 'm'/'o' (verpflichtend/optional, {{m:}}/{{o:}}): sql_query OPTIONAL
#               als Default-Quelle (dann dieselben SQL-Regeln + return_type
#               'scalar' — genau EIN Wert); Validierung OPTIONAL.
#
#   Validierungsarten (validation im KLARTEXT UTF-8; Base64 nur im
#   Token-Transport — mc-Entscheid §2.2):
#     'regex' — regulaerer Ausdruck im JAVASCRIPT-Dialekt (ECMAScript). Die
#               VERBINDLICHE Syntaxpruefung macht die Management-Maske per
#               `new RegExp(...)`; serverseitig wird best-effort mit Python-`re`
#               kompiliert und ein Scheitern NUR ALS WARNUNG gemeldet, weil
#               beide Dialekte auseinanderlaufen koennen (z.B. benannte Gruppen
#               (?<name>...) vs. (?P<name>...)). Kein stilles Schlucken, kein
#               falsches Blockieren.
#     'list'  — JSON-Array erlaubter Werte (nicht leer, nur Strings).
#     'like'  — SQL-LIKE-artiges Muster (% = beliebig, _ = ein Zeichen);
#               nicht leer.
#
#   Rueckgabe von validate_static: (errors, warnings). errors blockieren das
#   Speichern (HTTP 400); warnings werden angezeigt, blockieren aber nicht
#   (Grundregel 11: Warnung statt Blockade, wo die Sache nicht eindeutig ist).
#
#   Der fdb-Dry-Run (dry_run) ist unveraendert zum query_validator: die
#   (Default-)Query wird READ-ONLY gegen eine Beispiel-forensic_<uid>.db
#   ausgefuehrt.
#
# Version: v0.8.489 · Build: 489 · 2026-07-21
# =============================================================================

from __future__ import annotations

import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

# id-Zeichenraum (deckungsgleich mit der Chip-Regex-Klasse _CHIP_RE — nur dann
# ist der Platzhalter im Token {{typ:id}} ueberhaupt referenzierbar).
_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
# Benannte Parameter (:name). Erlaubt ist ausschliesslich :uid.
_NAMED_PARAM_RE = re.compile(r":([A-Za-z_]\w*)")
# Schreibende / strukturaendernde Schluesselwoerter -> verboten (read-only).
_FORBIDDEN_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|PRAGMA|REPLACE|"
    r"VACUUM|REINDEX|BEGIN|COMMIT|ROLLBACK|TRIGGER)\b", re.IGNORECASE)

VALID_TYPES = ("a", "m", "o")
VALID_VALIDATION_TYPES = ("regex", "list", "like")
VALID_RETURN_TYPES = ("scalar", "list", "table")


class PlaceholderValidationError(Exception):
    """Ein Platzhalter verletzt die Regeln (Liste in .errors)."""

    def __init__(self, errors: List[str]) -> None:
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _check_sql(sql: str, errors: List[str]) -> None:
    """SQL-Regeln (unveraendert aus query_validator Build 422): genau EIN
    read-only SELECT/WITH, ausschliesslich der benannte Parameter :uid."""
    body = sql.rstrip(";").strip()
    if ";" in body:
        errors.append("sql_query darf nur EIN Statement enthalten (kein ';').")
    low = body.lstrip().lower()
    if not (low.startswith("select") or low.startswith("with")):
        errors.append("sql_query muss ein SELECT (oder WITH ... SELECT) sein.")
    if _FORBIDDEN_RE.search(body):
        errors.append("sql_query enthaelt ein schreibendes/strukturaenderndes "
                      "Schluesselwort (nur read-only SELECT erlaubt).")
    if "?" in body:
        errors.append("sql_query darf nur den benannten Parameter ':uid' "
                      "verwenden (kein '?').")
    bad = sorted(set(_NAMED_PARAM_RE.findall(body)) - {"uid"})
    if bad:
        errors.append("sql_query verwendet unerlaubte Parameter: %s "
                      "(nur ':uid' erlaubt)." % ", ".join(":" + b for b in bad))


def _check_validation(vtype: str, value: str,
                      errors: List[str], warnings: List[str]) -> None:
    """Prueft das validation-Feld je validation_type (Klartext, s. Kopf)."""
    if vtype == "regex":
        # Best-effort mit Python-re: ein Scheitern ist nur eine WARNUNG, weil
        # der JS-Dialekt (Maske/Editor) massgeblich ist und Konstrukte kennt,
        # die Python-re ablehnt (und umgekehrt). Beleg: Kopfkommentar.
        try:
            re.compile(value)
        except re.error as exc:
            warnings.append(
                "validation (regex) liess sich mit Python-re nicht "
                "kompilieren (%s). Massgeblich ist der JavaScript-Dialekt — "
                "bitte die Gueltigkeitspruefung der Maske beachten." % exc)
    elif vtype == "list":
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError) as exc:
            errors.append("validation (list) ist kein gueltiges JSON: %s" % exc)
            return
        if not isinstance(parsed, list) or not parsed:
            errors.append("validation (list) muss ein NICHT-leeres JSON-Array "
                          "erlaubter Werte sein.")
        elif not all(isinstance(x, str) for x in parsed):
            errors.append("validation (list) darf nur Zeichenketten enthalten.")
    elif vtype == "like":
        if not value.strip():
            errors.append("validation (like) darf nicht leer sein.")


def validate_static(p: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """Statische Pruefung eines Platzhalters. Gibt (errors, warnings) zurueck
    (kein raise). errors blockieren, warnings nicht (Grundregel 11)."""
    errors: List[str] = []
    warnings: List[str] = []

    pid = str(p.get("id") or "").strip()
    if not pid:
        errors.append("id fehlt.")
    elif not _ID_RE.match(pid):
        errors.append("id enthaelt unzulaessige Zeichen "
                      "(erlaubt: A-Z a-z 0-9 . _ -).")

    if not str(p.get("title") or "").strip():
        errors.append("title fehlt.")
    if p.get("description") is None:
        # description ist NOT NULL in der DB; leerer String ist zulaessig.
        errors.append("description fehlt (leerer String ist erlaubt, "
                      "aber nicht NULL).")

    ptype = str(p.get("type") or "").strip()
    if ptype not in VALID_TYPES:
        errors.append("type '%s' ungueltig (erlaubt: a, m, o)." % ptype)
        # Ohne gueltigen Typ sind die Folgeregeln nicht entscheidbar.
        return errors, warnings

    sql = str(p.get("sql_query") or "").strip()
    validation = p.get("validation")
    validation = None if validation in (None, "") else str(validation)
    vtype = p.get("validation_type")
    vtype = None if vtype in (None, "") else str(vtype)

    rt = p.get("return_type") or "scalar"
    if rt not in VALID_RETURN_TYPES:
        errors.append("return_type '%s' ungueltig (erlaubt: %s)."
                      % (rt, ", ".join(VALID_RETURN_TYPES)))

    if ptype == "a":
        if not sql:
            errors.append("sql_query fehlt (fuer Typ 'a' Pflicht).")
        else:
            _check_sql(sql, errors)
        if validation is not None or vtype is not None:
            errors.append("Typ 'a' traegt KEINE Validierung (der Ermittler "
                          "kann den Wert nicht korrigieren; mc 2026-07-21).")
    else:  # 'm' / 'o'
        if sql:
            _check_sql(sql, errors)
        if rt != "scalar":
            errors.append("return_type fuer Typ '%s' muss 'scalar' sein "
                          "(die Default-Quelle liefert genau EINEN Wert)."
                          % ptype)
        if (validation is None) != (vtype is None):
            errors.append("validation und validation_type treten nur "
                          "PAARWEISE auf.")
        elif vtype is not None:
            if vtype not in VALID_VALIDATION_TYPES:
                errors.append("validation_type '%s' ungueltig (erlaubt: %s)."
                              % (vtype, ", ".join(VALID_VALIDATION_TYPES)))
            else:
                _check_validation(vtype, validation or "", errors, warnings)

    return errors, warnings


def dry_run(sql_query: str, test_subject_id: int, forensic_db_path: str,
            *, return_type: str = "scalar") -> Dict[str, Any]:
    """
    Fuehrt die (Default-)Query READ-ONLY gegen die Beispiel-fdb aus. Wirft
    PlaceholderValidationError bei SQL-Fehler oder verletzter Spaltenzahl
    (scalar). Gibt {ran, columns, sample} zurueck. Fehlt die fdb, wird der
    Dry-Run UEBERSPRUNGEN (ran=False) — die statische Pruefung bleibt
    massgeblich. (Unveraendert aus query_validator Build 422.)
    """
    path = os.path.abspath(forensic_db_path)
    if not os.path.exists(path):
        return {"ran": False,
                "reason": "keine Beispiel-forensic_<uid>.db verfuegbar."}

    uri = "file:%s?mode=ro" % path
    con = sqlite3.connect(uri, uri=True)
    try:
        # fdb zusaetzlich unter dem Alias 'fdb' anbinden, damit sowohl bare
        # Tabellennamen als auch 'fdb.'-praefixierte Queries laufen.
        con.execute("ATTACH DATABASE ? AS fdb", (uri,))
        cur = con.execute(sql_query, {"uid": int(test_subject_id)})
        row = cur.fetchone()
        ncols = len(cur.description) if cur.description else 0
    except sqlite3.Error as exc:
        raise PlaceholderValidationError(
            ["Dry-Run gegen die fdb schlug fehl: %s" % exc])
    finally:
        con.close()

    if return_type == "scalar" and ncols != 1:
        raise PlaceholderValidationError([
            "return_type 'scalar' erwartet genau EINE Ergebnisspalte, die "
            "Query liefert %d." % ncols])

    return {"ran": True, "columns": ncols,
            "sample": (row[0] if row is not None else None)}

# =============================================================================
# management/templates_admin/query_validator.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — W2 (Build 422): Validierung der Einzeldaten-Platzhalter-Queries
# =============================================================================
# Zweck:
#   Prueft eine Platzhalter-Query (placeholder_queries) VOR dem Schreiben in
#   templates.db. Zwei Stufen:
#     1. STATISCH (immer): id-Zeichenraum, Pflichtfelder, read-only SELECT,
#        genau EIN Parameter ':uid', keine schreibenden/mehrfachen Statements,
#        gueltiger return_type.
#     2. DRY-RUN (optional, wenn eine Beispiel-forensic_<uid>.db vorliegt): die
#        Query wird READ-ONLY gegen die fdb ausgefuehrt und - bei return_type
#        'scalar' - auf genau EINE Ergebnisspalte geprueft. So faellt eine
#        kaputte Query auf, BEVOR sie im Bericht eine falsche/leere Zahl liefert
#        (Grundregel: Ueberpruefbarkeit; keine stille Fehlaufloesung).
#
#   Warum ':uid' der einzige Parameter: der AutoQueryResolver (report_render/
#   auto_query.py) fuehrt die Query mit exakt {"uid": <user_id>} aus. Ein
#   weiterer Parameter wuerde zur Laufzeit fehlschlagen.
#   Warum id-Zeichenraum [A-Za-z0-9._-]: nur damit greift die Chip-Regex
#   (_CHIP_RE), sonst waere der Platzhalter nie aufloesbar.
#
# Version: v0.7.422 · Build: 422 · 2026-07-14
# =============================================================================

from __future__ import annotations

import os
import re
import sqlite3
from typing import Any, Dict, List, Optional

# id-Zeichenraum (deckungsgleich mit der Chip-Regex-Klasse).
_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
# Benannte Parameter (:name). Erlaubt ist ausschliesslich :uid.
_NAMED_PARAM_RE = re.compile(r":([A-Za-z_]\w*)")
# Schreibende / strukturaendernde Schluesselwoerter -> verboten (read-only).
_FORBIDDEN_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|PRAGMA|REPLACE|"
    r"VACUUM|REINDEX|BEGIN|COMMIT|ROLLBACK|TRIGGER)\b", re.IGNORECASE)

VALID_RETURN_TYPES = ("scalar", "list", "table")


class QueryValidationError(Exception):
    """Eine Platzhalter-Query verletzt die Regeln (Liste in .errors)."""

    def __init__(self, errors: List[str]) -> None:
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def validate_static(q: Dict[str, Any]) -> List[str]:
    """Statische Pruefung. Gibt eine (leere) Fehlerliste zurueck (kein raise)."""
    errors: List[str] = []

    qid = str(q.get("id") or "").strip()
    if not qid:
        errors.append("id fehlt.")
    elif not _ID_RE.match(qid):
        errors.append("id enthaelt unzulaessige Zeichen (erlaubt: A-Z a-z 0-9 . _ -).")

    if not str(q.get("title") or "").strip():
        errors.append("title fehlt.")
    if q.get("description") is None:
        # description ist NOT NULL in der DB; leerer String ist zulaessig.
        errors.append("description fehlt (leerer String ist erlaubt, aber nicht NULL).")

    sql = str(q.get("sql_query") or "").strip()
    if not sql:
        errors.append("sql_query fehlt.")
    else:
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

    rt = q.get("return_type") or "scalar"
    if rt not in VALID_RETURN_TYPES:
        errors.append("return_type '%s' ungueltig (erlaubt: %s)."
                      % (rt, ", ".join(VALID_RETURN_TYPES)))

    return errors


def dry_run(sql_query: str, test_user_id: int, forensic_db_path: str,
            *, return_type: str = "scalar") -> Dict[str, Any]:
    """
    Fuehrt die Query READ-ONLY gegen die Beispiel-fdb aus. Wirft
    QueryValidationError bei SQL-Fehler oder verletzter Spaltenzahl (scalar).
    Gibt {ran, columns, sample} zurueck. Fehlt die fdb, wird der Dry-Run
    UEBERSPRUNGEN (ran=False) — die statische Pruefung bleibt maßgeblich.
    """
    path = os.path.abspath(forensic_db_path)
    if not os.path.exists(path):
        return {"ran": False,
                "reason": "keine Beispiel-forensic_<uid>.db verfuegbar."}

    uri = "file:%s?mode=ro" % path
    con = sqlite3.connect(uri, uri=True)
    try:
        # fdb zusaetzlich unter dem Alias 'fdb' anbinden, damit sowohl bare
        # Tabellennamen (SQLite loest ueber angebundene DBs auf) als auch
        # 'fdb.'-praefixierte Queries laufen.
        con.execute("ATTACH DATABASE ? AS fdb", (uri,))
        cur = con.execute(sql_query, {"uid": int(test_user_id)})
        row = cur.fetchone()
        ncols = len(cur.description) if cur.description else 0
    except sqlite3.Error as exc:
        raise QueryValidationError(["Dry-Run gegen die fdb schlug fehl: %s" % exc])
    finally:
        con.close()

    if return_type == "scalar" and ncols != 1:
        raise QueryValidationError([
            "return_type 'scalar' erwartet genau EINE Ergebnisspalte, die Query "
            "liefert %d." % ncols])

    return {"ran": True, "columns": ncols,
            "sample": (row[0] if row is not None else None)}

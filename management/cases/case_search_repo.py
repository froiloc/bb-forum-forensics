# =============================================================================
# management/cases/case_search_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fallsteuerung (AP-2G)
# =============================================================================
# Zweck (Idee 28 — Kommandopalette, Fall-/Nutzer-Sprung; Backend):
#   Leichter, NUR-LESENDER Suchpfad ueber die Faelle (Tabelle cases) fuer die
#   Kommandopalette. Numerische Eingabe -> user_id-Treffer (plus username-
#   Teiltreffer); sonst username-Teilstring (case-insensitiv). SCOPE-BEWUSST:
#   'alle' -> alle Faelle, 'eigene' -> nur die dem/der Ermittler:in zugewiesenen.
#
#   BELEGTREUE (GR1): liefert ausschliesslich real vorhandene cases-Zeilen;
#   Ergebnis ist begrenzt (limit) und die Begrenzung wird ueber 'truncated'
#   ausgewiesen (kein stilles Abschneiden).
#
#   Rein lesend; keine Aenderung an cases.
#
# Version: v0.7.458 · Build: 458 · 2026-07-19
# =============================================================================

from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 50


class CaseSearchRepo:
    """Read-only Fall-/Nutzer-Suche fuer die Kommandopalette."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def search(self, *, q: str, scope: str = "alle",
               person_id: Optional[int] = None,
               limit: int = _DEFAULT_LIMIT) -> Dict[str, object]:
        term = (q or "").strip()
        limit = max(1, min(int(limit or _DEFAULT_LIMIT), _MAX_LIMIT))
        result: Dict[str, object] = {
            "q": term, "scope": ("eigene" if scope == "eigene" else "alle"),
            "count": 0, "truncated": False, "results": [],
        }
        if not term:
            return result

        where = []
        params: List[object] = []

        # Numerische Eingabe: user_id ODER username-Teilstring.
        if term.isdigit():
            where.append("(c.user_id = ? OR c.username LIKE ? ESCAPE '\\')")
            params.append(int(term))
            params.append("%" + _like_escape(term) + "%")
        else:
            where.append("c.username LIKE ? ESCAPE '\\'")
            params.append("%" + _like_escape(term) + "%")

        if scope == "eigene":
            where.append("c.assigned_to = ?")
            params.append(person_id)

        sql = (
            "SELECT c.user_id, c.username, c.status, i.system_username "
            "FROM cases c LEFT JOIN person i ON i.id = c.assigned_to "
            "WHERE " + " AND ".join(where) +
            # Exakte user_id-Treffer zuerst (bei numerischer Suche), dann uid.
            " ORDER BY (CASE WHEN c.user_id = ? THEN 0 ELSE 1 END), c.user_id "
            "LIMIT ?"
        )
        params.append(int(term) if term.isdigit() else -1)
        params.append(limit + 1)   # +1, um Abschneidung zu erkennen

        rows = self._con.execute(sql, params).fetchall()
        truncated = len(rows) > limit
        rows = rows[:limit]
        results = [
            {"user_id": int(r[0]), "username": r[1], "status": r[2],
             "assigned_system_username": r[3]}
            for r in rows
        ]
        result["results"] = results
        result["count"] = len(results)
        result["truncated"] = truncated
        return result


def _like_escape(s: str) -> str:
    """Escaped LIKE-Sonderzeichen (\\, %, _), damit die Suche woertlich ist."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

# =============================================================================
# management/personal/myhistory_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Persoenliche Sichten
# =============================================================================
# MyHistoryRepo — REIN LESENDE, kombinierte persoenliche Historie eines
# Ermittlers aus dem hash-verketteten audit_log (coordinator.db):
#
#   (a) MEINE AKTIONEN      — audit_log.actor_id == person_id
#   (b) HISTORIE MEINER FAELLE — Fall-Ereignisse (target_type='case') zu den
#       mir aktuell zugewiesenen Faellen (cases.assigned_to == person_id).
#       Fall-Ereignisse adressieren den Fall ueber target_id = str(subject_id)
#       (Konvention aus cases_repo).
#
# Beide Mengen werden vereinigt (ein Eintrag kann beides sein: von mir UND zu
# meinem Fall), neueste zuerst (seq DESC), limitiert. Jeder Eintrag ist mit
# 'mine'/'mycase' markiert, damit die Sicht die Herkunft zeigen kann.
#
# Zweckbindung: Arbeits-/Statusuebersicht der eigenen Faelle — kein
# Bewertungsinstrument.
#
# Beleg: Bauplan B7 v1.1 §11; mc 2026-07-10 (kombinierte Historie).
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import sqlite3
from typing import Any, Dict, List

_DEFAULT_LIMIT = 200
_MAX_LIMIT = 1000


class MyHistoryRepo:
    """Liest die kombinierte persoenliche Historie (read-only)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def my_history(self, person_id: int, *,
                   limit: int = _DEFAULT_LIMIT) -> Dict[str, Any]:
        limit = max(1, min(int(limit), _MAX_LIMIT))

        # Meine aktuell zugewiesenen Faelle (target_id ist TEXT im audit_log).
        my_case_ids = {
            str(r[0]) for r in self._con.execute(
                "SELECT subject_id FROM cases WHERE assigned_to = ?",
                (person_id,)).fetchall()
        }

        # Vereinigung: eigene Aktionen ODER Fall-Ereignis zu einem meiner Faelle.
        # Die Fall-Bedingung nutzt eine Unterabfrage (kein String-Bau aus IDs).
        cur = self._con.execute(
            "SELECT seq, ts, actor_id, event_type, target_type, target_id "
            "FROM audit_log "
            "WHERE actor_id = ? "
            "   OR (target_type = 'case' AND target_id IN "
            "        (SELECT CAST(subject_id AS TEXT) FROM cases "
            "         WHERE assigned_to = ?)) "
            "ORDER BY seq DESC LIMIT ?",
            (person_id, person_id, limit))
        cols = [c[0] for c in cur.description]

        events: List[Dict[str, Any]] = []
        for row in cur.fetchall():
            e = dict(zip(cols, row))
            e["mine"] = (e["actor_id"] == person_id)
            e["mycase"] = (e["target_type"] == "case"
                           and e["target_id"] in my_case_ids)
            events.append(e)

        return {
            "person_id": person_id,
            "limit": limit,
            "count": len(events),
            "my_case_count": len(my_case_ids),
            "events": events,
        }

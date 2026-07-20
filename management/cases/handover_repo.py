# =============================================================================
# management/cases/handover_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fallsteuerung (AP-2G)
# =============================================================================
# Zweck:
#   Liest die CASE_ASSIGNED-Ereignisse aus dem audit_log (permanenter Beleg) und
#   die Namensaufloesung aus person, uebergibt beides an die reine
#   build_handovers (management.cases.handover_log). DB-Zugriff hier, Logik dort.
#
# Version: v0.7.455 · Build: 455 · 2026-07-19
# =============================================================================

from __future__ import annotations

import json
import sqlite3
import time
from typing import Dict, List, Optional

from management.audit.event_types import EventType
from management.cases.handover_log import build_handovers, HandoverReport


class HandoverRepo:
    """Read-Model: Uebergabe-/Umverteilungshistorie je Fall (read-only)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def _names(self) -> Dict[int, str]:
        out: Dict[int, str] = {}
        try:
            cur = self._con.execute(
                "SELECT id, display_name, system_username FROM person")
            for pid, disp, sysu in cur.fetchall():
                out[int(pid)] = disp or sysu or ("#%d" % int(pid))
        except sqlite3.OperationalError:
            pass  # person fehlt -> nur IDs (kein Absturz, GR1)
        return out

    def compute(self, *, user_id: Optional[int] = None,
                now: Optional[int] = None) -> HandoverReport:
        now = int(time.time()) if now is None else int(now)

        sql = ("SELECT seq, ts, actor_id, target_id, content FROM audit_log "
               "WHERE event_type = ?")
        params: list = [EventType.CASE_ASSIGNED]
        if user_id is not None:
            sql += " AND target_id = ?"
            params.append(str(user_id))
        sql += " ORDER BY seq ASC"

        events: List[dict] = []
        for seq, ts, actor_id, target_id, content in self._con.execute(sql, params):
            try:
                data = json.loads(content) if content else {}
            except (ValueError, TypeError):
                data = {}
            # user_id bevorzugt aus target_id (kanonisch), sonst aus content.
            try:
                uid = int(target_id) if target_id is not None \
                    else int(data.get("user_id"))
            except (TypeError, ValueError):
                continue  # ohne Fallbezug nicht auswertbar
            events.append({
                "user_id": uid, "seq": int(seq), "ts": int(ts),
                "actor_id": actor_id, "assigned_to": data.get("assigned_to"),
            })

        return build_handovers(events, self._names(), now)

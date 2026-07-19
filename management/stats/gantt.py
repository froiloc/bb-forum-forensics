# =============================================================================
# management/stats/gantt.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-2C)
# =============================================================================
# Zweck (Idee 19 — Gantt-Chart / Ressourcenplanung):
#   Rein lesendes Read-Model fuer eine Termin-/Ressourcenuebersicht: je Fall ein
#   Balken (Beginn -> Ende), gruppiert in Spuren (Lanes) je Ermittler. Grundlage
#   der spaeteren ECharts-Sicht (B448); hier NUR die belegte Datenaufbereitung.
#
#   ZEITANKER (belegt, keine Erfindung — Grundregel 1):
#     * Beginn = fruehestes case_events.event_kind='assigned' (Zuweisung) des
#       Falls; fehlt eine Zuweisung -> cases.created_at (Anlage).
#     * Ende   = spaetestes case_events.event_kind='approved' (Abschluss); fehlt
#       es, ist der Fall OFFEN (ongoing=True); als Anzeige-Ende dient dann now_ts
#       (klar als laufend gekennzeichnet, nicht als Abschluss behauptet).
#     * Lane   = zugewiesener Ermittler (cases.assigned_to -> person). Ohne
#       Zuweisung: Sammel-Lane 'Rueckstau' (assignee_id=None).
#
#   KEIN Fall geht verloren (GR1): jeder cases-Datensatz ergibt genau einen
#   Balken. now_ts wird injiziert -> deterministisch/testbar. Nur lesend.
#
# Version: v0.7.447 · Build: 447 · 2026-07-19
# =============================================================================

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional

_ASSIGN_KIND = "assigned"     # case_events.event_kind (Beleg case_events_repo.py:46)
_APPROVE_KIND = "approved"    # case_events.event_kind (Beleg case_events_repo.py:48)
_BACKLOG_LABEL = "Rueckstau"  # Sammel-Lane fuer unzugewiesene Faelle


@dataclass(frozen=True)
class GanttBar:
    user_id: int
    username: str
    status: str
    assignee_id: Optional[int]
    assignee_name: Optional[str]
    start_ts: int              # belegter Beginn
    end_ts: int                # Anzeige-Ende (Abschluss oder now bei ongoing)
    ongoing: bool              # True = offener Fall (kein Abschluss-Beleg)
    completed_ts: Optional[int]  # tatsaechlicher Abschluss (None = offen)


@dataclass(frozen=True)
class GanttLane:
    assignee_id: Optional[int]
    assignee_name: str
    bars: List[GanttBar]


@dataclass(frozen=True)
class GanttResult:
    now_ts: int
    range_start: Optional[int]
    range_end: Optional[int]
    lanes: List[GanttLane]
    total_bars: int


class GanttModel:
    """Baut das Gantt-Read-Model (Faelle -> Balken -> Ermittler-Spuren)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def build(self, *, now_ts: int) -> GanttResult:
        # Zeitanker je user_id in EINER Abfrage (kein N+1): fruehester assign,
        # spaetester approve.
        anchors: Dict[int, Dict[str, Optional[int]]] = {}
        for uid, kind, ts in self._con.execute(
                "SELECT user_id, event_kind, "
                "  CASE WHEN event_kind=? THEN MIN(created_at) "
                "       ELSE MAX(created_at) END AS ts "
                "FROM case_events WHERE event_kind IN (?, ?) "
                "GROUP BY user_id, event_kind",
                (_ASSIGN_KIND, _ASSIGN_KIND, _APPROVE_KIND)):
            a = anchors.setdefault(int(uid), {"assign": None, "approve": None})
            if kind == _ASSIGN_KIND:
                a["assign"] = int(ts)
            elif kind == _APPROVE_KIND:
                a["approve"] = int(ts)

        rows = self._con.execute(
            "SELECT c.user_id, c.username, c.status, c.assigned_to, "
            "       c.created_at, i.display_name, i.system_username "
            "FROM cases c LEFT JOIN person i ON i.id = c.assigned_to "
            "ORDER BY c.user_id ASC").fetchall()

        # Lanes vorbereiten (stabile Reihenfolge: Ermittler nach Name, Rueckstau
        # zuletzt). Zwischenspeicher {assignee_id: (name, [bars])}.
        lane_bars: Dict[Optional[int], List[GanttBar]] = {}
        lane_name: Dict[Optional[int], str] = {}
        starts: List[int] = []
        ends: List[int] = []

        for r in rows:
            uid = int(r[0])
            username = r[1]
            status = r[2]
            assigned_to = r[3]
            created_at = int(r[4])
            display_name = r[5]
            system_username = r[6]

            a = anchors.get(uid, {})
            start_ts = a.get("assign") or created_at
            completed_ts = a.get("approve")
            ongoing = completed_ts is None
            end_ts = completed_ts if completed_ts is not None else now_ts
            # Belegtreue: Anzeige-Ende nie vor Beginn (Null-Laenge statt negativ).
            if end_ts < start_ts:
                end_ts = start_ts

            assignee_id = int(assigned_to) if assigned_to is not None else None
            if assignee_id is None:
                name = _BACKLOG_LABEL
            else:
                name = display_name or system_username or ("#%d" % assignee_id)

            bar = GanttBar(
                user_id=uid, username=username, status=status,
                assignee_id=assignee_id, assignee_name=(
                    None if assignee_id is None else name),
                start_ts=start_ts, end_ts=end_ts, ongoing=ongoing,
                completed_ts=completed_ts)

            lane_bars.setdefault(assignee_id, []).append(bar)
            lane_name[assignee_id] = name
            starts.append(start_ts)
            ends.append(end_ts)

        # Lanes ordnen: benannte Ermittler alphabetisch, Rueckstau (None) zuletzt.
        assignee_ids = [k for k in lane_bars.keys() if k is not None]
        assignee_ids.sort(key=lambda k: (lane_name[k].lower(), k))
        ordered_keys = assignee_ids + ([None] if None in lane_bars else [])

        lanes = [
            GanttLane(assignee_id=k, assignee_name=lane_name[k],
                      bars=sorted(lane_bars[k], key=lambda b: (b.start_ts, b.user_id)))
            for k in ordered_keys
        ]

        total = sum(len(l.bars) for l in lanes)
        return GanttResult(
            now_ts=now_ts,
            range_start=min(starts) if starts else None,
            range_end=max(ends) if ends else None,
            lanes=lanes, total_bars=total)


def gantt_to_dict(result: GanttResult) -> dict:
    """Serialisierung fuer die Sicht/Pruefsumme (stabile Schluessel)."""
    return {
        "now_ts": result.now_ts,
        "range_start": result.range_start,
        "range_end": result.range_end,
        "total_bars": result.total_bars,
        "lanes": [
            {"assignee_id": l.assignee_id, "assignee_name": l.assignee_name,
             "bars": [
                 {"user_id": b.user_id, "username": b.username, "status": b.status,
                  "assignee_id": b.assignee_id, "assignee_name": b.assignee_name,
                  "start_ts": b.start_ts, "end_ts": b.end_ts,
                  "ongoing": b.ongoing, "completed_ts": b.completed_ts}
                 for b in l.bars]}
            for l in result.lanes
        ],
    }

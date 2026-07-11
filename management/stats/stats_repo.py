# =============================================================================
# management/stats/stats_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistiken (StA/Fuehrung)
# =============================================================================
# StatsRepo — REIN LESENDE Kennzahl-Matrizen fuer die Auswertungs-Sicht
# (StA / Fuehrung). Basis: das vorhandene DashboardRepo-Fallaggregat + das
# audit_log (fuer den Durchsatz ueber die Zeit). Kein Schreibpfad.
#
# Kennzahlen (MVP, spaeter erweiterbar):
#   totals            — cases, assigned, unassigned, events (Summe event_count)
#   by_status         — {open, in_progress, approved, closed -> Anzahl}
#   by_priority       — {'1'..'5' -> Anzahl}
#   by_ampel          — {Ampelwert -> Anzahl}
#   by_assignee       — [{person_id, display_name, count}] (zugewiesene Faelle)
#   throughput_by_day — [{day 'YYYY-MM-DD', count}] : Fall-Ereignisse je Tag aus
#                       dem audit_log (target_type='case') = Auswertungs-Durchsatz
#
# Scope (im Endpunkt genutzt):
#   compute()               -> alle Faelle (Fuehrungssicht)
#   compute(person_id=<id>) -> nur die dem Aufrufer zugewiesenen Faelle; der
#       Durchsatz zaehlt dann nur Ereignisse zu genau diesen Faellen.
#
# Export: to_csv() liefert ein maschinenlesbares Langformat
#   (abschnitt,schluessel,wert) fuer die Weitergabe an Dritte.
#
# Beleg: Ideen §2.4 (Auswertung & Statistik StA/Fuehrung); DashboardRepo.
# Version: v0.7.370 · Build: 370 · 2026-07-10
# =============================================================================

import csv
import io
import sqlite3
import time
from typing import Any, Dict, Optional

from management.dashboard.dashboard_repo import DashboardRepo

_STATUSES = ("open", "in_progress", "approved", "closed")
_PRIORITIES = ("1", "2", "3", "4", "5")


class StatsRepo:
    """Berechnet Kennzahl-Matrizen (read-only)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def compute(self, person_id: Optional[int] = None) -> Dict[str, Any]:
        cases = DashboardRepo(self._con).list_case_overview()
        if person_id is not None:
            cases = [c for c in cases if c.assigned_to == person_id]

        totals = {
            "cases": len(cases),
            "assigned": sum(1 for c in cases if c.assigned_to is not None),
            "unassigned": sum(1 for c in cases if c.assigned_to is None),
            "events": sum(c.event_count for c in cases),
        }

        by_status = {s: 0 for s in _STATUSES}
        for c in cases:
            by_status[c.status] = by_status.get(c.status, 0) + 1

        by_priority = {p: 0 for p in _PRIORITIES}
        for c in cases:
            key = str(c.priority)
            by_priority[key] = by_priority.get(key, 0) + 1

        by_ampel: Dict[str, int] = {}
        for c in cases:
            by_ampel[c.ampel] = by_ampel.get(c.ampel, 0) + 1

        acc: Dict[int, int] = {}
        names: Dict[int, Optional[str]] = {}
        for c in cases:
            if c.assigned_to is not None:
                acc[c.assigned_to] = acc.get(c.assigned_to, 0) + 1
                names[c.assigned_to] = c.assigned_display_name
        by_assignee = sorted(
            [{"person_id": pid, "display_name": names.get(pid), "count": n}
             for pid, n in acc.items()],
            key=lambda x: (-x["count"], x["person_id"]))

        throughput = self._throughput(person_id)

        return {
            "scope": "alle" if person_id is None else "eigene",
            "generated_at": int(time.time()),
            "totals": totals,
            "by_status": by_status,
            "by_priority": by_priority,
            "by_ampel": by_ampel,
            "by_assignee": by_assignee,
            "throughput_by_day": throughput,
        }

    # ------------------------------------------------------------- internals
    def _throughput(self, person_id: Optional[int]):
        # Fall-Ereignisse je Kalendertag aus dem audit_log (target_type='case').
        # date(ts,'unixepoch') -> 'YYYY-MM-DD'. Fuer 'eigene' auf die eigenen
        # Faelle eingeschraenkt (target_id ist TEXT der user_id).
        if person_id is None:
            cur = self._con.execute(
                "SELECT date(ts,'unixepoch') AS day, COUNT(*) AS n "
                "FROM audit_log WHERE target_type='case' "
                "GROUP BY day ORDER BY day ASC")
        else:
            cur = self._con.execute(
                "SELECT date(ts,'unixepoch') AS day, COUNT(*) AS n "
                "FROM audit_log WHERE target_type='case' AND target_id IN "
                "  (SELECT CAST(user_id AS TEXT) FROM cases WHERE assigned_to=?) "
                "GROUP BY day ORDER BY day ASC", (person_id,))
        return [{"day": r[0], "count": r[1]} for r in cur.fetchall()]

    # -------------------------------------------------------------- CSV/Export
    @staticmethod
    def to_csv(stats: Dict[str, Any]) -> str:
        """Maschinenlesbares Langformat: abschnitt,schluessel,wert."""
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["abschnitt", "schluessel", "wert"])
        for k, v in stats["totals"].items():
            w.writerow(["totals", k, v])
        for k, v in stats["by_status"].items():
            w.writerow(["by_status", k, v])
        for k, v in stats["by_priority"].items():
            w.writerow(["by_priority", k, v])
        for k, v in stats["by_ampel"].items():
            w.writerow(["by_ampel", k, v])
        for a in stats["by_assignee"]:
            label = a["display_name"] or ("#%s" % a["person_id"])
            w.writerow(["by_assignee", label, a["count"]])
        for t in stats["throughput_by_day"]:
            w.writerow(["throughput", t["day"], t["count"]])
        return buf.getvalue()

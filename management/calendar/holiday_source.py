# =============================================================================
# management/calendar/holiday_source.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Kalenderquelle fuer die FEIERTAGE (M008: holiday). Sie ist der dritte Beleg
#   dafuer, dass die Leseschicht traegt: eine weitere Zeitquelle, KEINE
#   Schema-Aenderung, kein zweites System.
#
#   Fachlich ist sie kein Beiwerk: faellt eine Wiedervorlage auf einen Feiertag,
#   ist die Frist faktisch schon am Vortag zu bearbeiten. Ohne die Feiertage im
#   selben Kalender sieht man das nicht.
#
# RBAC: KEINES. Ein Feiertag enthaelt weder Fall- noch Personendaten. Er ist
#   fuer jeden sichtbar, der das Cockpit ueberhaupt oeffnen darf.
#
# Version: v0.7.385 · Build: 385 · 2026-07-12
# =============================================================================

import logging
import sqlite3
from typing import List, Optional

from management.calendar.calendar_entry import CalendarEntry
from management.calendar.calendar_source import CalendarSource

logger = logging.getLogger(__name__)


class HolidaySource(CalendarSource):
    """Feiertage (M008) als globale Zeitpunkte."""

    key = "holiday"
    label = "Feiertage"

    def __init__(self, con: sqlite3.Connection, policy=None) -> None:
        self._con = con
        self._hinweis: Optional[str] = None

    def entries(self, *, von: str, bis: str,
                stichtag: str) -> List[CalendarEntry]:
        self._hinweis = None
        try:
            rows = self._con.execute(
                "SELECT id, day, label, region FROM holiday "
                "WHERE deleted_at IS NULL AND day BETWEEN ? AND ? "
                "ORDER BY day ASC, id ASC", (von, bis)).fetchall()
        except sqlite3.OperationalError as exc:
            self._hinweis = ("Feiertage nicht lesbar (%s). Migration anwenden: "
                             "python -m management.migrate" % exc)
            logger.warning("HolidaySource: %s", exc)
            return []

        out: List[CalendarEntry] = []
        for r in rows:
            region = r["region"] if "region" in r.keys() else None
            titel = r["label"] + ((" (%s)" % region) if region else "")
            out.append(CalendarEntry(
                source=self.key,
                ref_id=int(r["id"]),
                von=r["day"], bis=r["day"],
                titel=titel,
                subject_kind="global",
                subject_id=None,
                subject_label="",
                ampel="neutral",
                ampel_grund="",
                ziel="capacity",
            ))
        logger.debug("HolidaySource: %d Eintraege", len(out))
        return out

    def hinweis(self) -> Optional[str]:
        return self._hinweis

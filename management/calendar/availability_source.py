# =============================================================================
# management/calendar/availability_source.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Kalenderquelle fuer die PERSONALPLANUNG (M008: availability_entry).
#   Liefert je Eintrag EINEN Zeitraum-Eintrag [period_start .. period_end].
#
#   Diese Quelle SCHREIBT NICHT und AENDERT NICHTS an M008. Sie liest ueber den
#   bestehenden AvailabilityRepo (writer=None) — der Kalender ist eine reine
#   Leseschicht ueber unveraenderten Schreibmodellen (mc 2026-07-12).
#
# AMPEL: bewusst 'neutral'. Eine Abwesenheit ist kein Missstand und darf im
#   Kalender nicht wie eine ueberfaellige Wiedervorlage schreien. Die
#   Ueberlast-Bewertung ist Sache der Kapazitaets-Rechnung (CapacityCalculator),
#   nicht des Kalenders — der Kalender ZEIGT, er BEWERTET nicht.
#
# RBAC: 'capacity.edit' (mc 2026-07-12). Wer die Kapazitaetsdaten nicht pflegen
#   darf, sieht auch keine fremden Abwesenheiten im Kalender. Ohne das Recht:
#   LEERE Liste + Hinweis.
#
# Version: v0.7.385 · Build: 385 · 2026-07-12
# =============================================================================

import logging
import sqlite3
from typing import Dict, List, Optional

from management.calendar.calendar_entry import CalendarEntry
from management.calendar.calendar_source import CalendarSource
from management.capacity.availability_repo import AvailabilityRepo

logger = logging.getLogger(__name__)

CAP_CAPACITY = "capacity.edit"


class AvailabilitySource(CalendarSource):
    """Verfuegbarkeiten/Abwesenheiten (M008) als Kalender-Zeitraeume."""

    key = "availability"
    label = "Verfuegbarkeit / Abwesenheit"

    def __init__(self, con: sqlite3.Connection, policy) -> None:
        self._con = con
        self._policy = policy
        self._hinweis: Optional[str] = None

    def _person_labels(self) -> Dict[int, str]:
        rows = self._con.execute(
            "SELECT id, COALESCE(display_name, system_username) AS n "
            "FROM person").fetchall()
        return {int(r[0]): (r[1] or "") for r in rows}

    def entries(self, *, von: str, bis: str,
                stichtag: str) -> List[CalendarEntry]:
        self._hinweis = None
        if not self._policy.can(CAP_CAPACITY):
            self._hinweis = ("Abwesenheiten werden NICHT angezeigt: die "
                             "Faehigkeit '%s' fehlt." % CAP_CAPACITY)
            return []

        try:
            rows = AvailabilityRepo(self._con, None).list_availability()
            names = self._person_labels()
        except sqlite3.OperationalError as exc:
            self._hinweis = ("Verfuegbarkeiten nicht lesbar (%s). Migration "
                             "anwenden: python -m management.migrate" % exc)
            logger.warning("AvailabilitySource: %s", exc)
            return []

        out: List[CalendarEntry] = []
        for r in rows:
            start, end = r["period_start"], r["period_end"]
            # Ueberlappung mit [von, bis] — ein Zeitraum zaehlt, sobald er den
            # Ausschnitt BERUEHRT (nicht erst, wenn er ganz darin liegt).
            if end < von or start > bis:
                continue
            if r["value_pct"] is not None:
                menge = "%d %%" % r["value_pct"]
            else:
                menge = "%d min" % (r["value_minutes"] or 0)
            art = ("Garantie" if r["kind"] == "garantie" else "Einschraenkung")
            grund = r.get("reason_code") or ""
            titel = "%s %s%s" % (art, menge,
                                 (" (%s)" % grund) if grund else "")
            out.append(CalendarEntry(
                source=self.key,
                ref_id=int(r["id"]),
                von=start, bis=end,
                titel=titel,
                subject_kind="person",
                subject_id=int(r["person_id"]),
                subject_label=names.get(int(r["person_id"]), ""),
                ampel="neutral",
                ampel_grund=(r.get("note") or ""),
                ziel="capacity",
            ))
        logger.debug("AvailabilitySource: %d Eintraege (%s..%s)",
                     len(out), von, bis)
        return out

    def hinweis(self) -> Optional[str]:
        return self._hinweis

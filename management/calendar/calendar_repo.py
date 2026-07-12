# =============================================================================
# management/calendar/calendar_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Die GEMEINSAME SICHT. Fuehrt alle Zeitquellen (externe Vorgaenge M010,
#   Verfuegbarkeiten M008, Feiertage M008) zu EINER chronologischen Liste
#   zusammen — ohne dass eines der Schreibmodelle davon etwas wissen muss.
#
#   Das ist die Antwort auf die Frage, wie Personalplanung und Wiedervorlage
#   zusammenkommen (mc 2026-07-12): NICHT ueber einen gemeinsamen Speicher,
#   sondern ueber den gemeinsamen Verknuepfungspunkt ZEIT.
#
# DREI EIGENSCHAFTEN, DIE NICHT VERHANDELBAR SIND:
#
#   1) DIE QUELLEN KAPSELN SELBST. Der Aggregator prueft keine Rechte — er
#      koennte die Semantik der Quellen gar nicht korrekt beurteilen. Jede
#      Quelle liefert bereits gefiltert (CalendarSource, Pflicht 1).
#
#   2) SCHWEIGEN WIRD GEMELDET. Liefert eine Quelle nichts, weil ein Recht oder
#      eine Tabelle fehlt, steht das als HINWEIS in der Antwort. Ein Kalender,
#      der unvollstaendig ist, ohne es zu sagen, ist gefaehrlicher als keiner:
#      der Ermittler schliesst aus der Leere, es stuende nichts an
#      (Grundregel 1).
#
#   3) DIE RECHENGRUNDLAGE STEHT DABEI. Jede Antwort traegt den Stichtag samt
#      Zeitzone (stichtag.py). Eine falsche Uhr faellt so einem Menschen auf.
#
# SORTIERUNG: Handlungsbedarf zuerst — rot vor gelb vor gruen vor neutral,
#   innerhalb dessen chronologisch. Wer den Kalender oeffnet, soll das
#   Ueberfaellige sehen, nicht danach suchen.
#
# Version: v0.7.385 · Build: 385 · 2026-07-12
# =============================================================================

import logging
import sqlite3
from typing import Any, Dict, List, Optional, Sequence

from management.calendar.availability_source import AvailabilitySource
from management.calendar.calendar_entry import CalendarEntry
from management.calendar.calendar_source import CalendarSource
from management.calendar.external_source import ExternalSource
from management.calendar.holiday_source import HolidaySource
from management.calendar import stichtag as stichtag_mod
from management.external.matter_status import MatterStatus, MatterStatusError

logger = logging.getLogger(__name__)

#: Rang der Ampel fuer die Sortierung (identisch zu MatterStatus.rank).
_RANK = MatterStatus.rank


class CalendarError(Exception):
    """Ungueltiger Zeitraum o. Ae."""


class CalendarRepo:
    """Aggregiert alle CalendarSources zu einer Sicht."""

    def __init__(self, con: sqlite3.Connection, policy,
                 sources: Optional[Sequence[CalendarSource]] = None) -> None:
        self._con = con
        self._policy = policy
        # Die Quellenliste ist INJIZIERBAR — so kann pytest eine einzelne
        # Quelle pruefen, und Welle 2 haengt Fristen/Gantt an, ohne diese
        # Klasse zu aendern.
        self._sources: List[CalendarSource] = list(sources) if sources else [
            ExternalSource(con, policy),
            AvailabilitySource(con, policy),
            HolidaySource(con, policy),
        ]

    @staticmethod
    def _check_range(von: str, bis: str) -> None:
        try:
            d_von = MatterStatus.parse_date(von)
            d_bis = MatterStatus.parse_date(bis)
        except MatterStatusError as exc:
            raise CalendarError(str(exc)) from exc
        if d_bis < d_von:
            raise CalendarError(
                "Zeitraum verkehrt herum: bis (%s) liegt vor von (%s)."
                % (bis, von))

    def view(self, *, von: str, bis: str,
             stichtag: Optional[str] = None) -> Dict[str, Any]:
        """
        Gesamtsicht fuer [von, bis] (beide inklusiv).

        stichtag=None -> aus der Systemuhr (Europe/Berlin, mit Herkunftsvermerk).
        Ein UEBERGEBENER Stichtag ist ausdruecklich erlaubt (pytest, Vorschau);
        er wird im Vermerk genauso ausgewiesen.
        """
        self._check_range(von, bis)

        if stichtag is None:
            info = stichtag_mod.heute()
        else:
            MatterStatus.parse_date(stichtag)      # validiert, wirft sonst
            info = {"stichtag": stichtag, "zeitzone": "vorgegeben",
                    "warnung": None}
        tag = info["stichtag"]

        entries: List[CalendarEntry] = []
        quellen: List[Dict[str, Any]] = []
        hinweise: List[str] = []

        for src in self._sources:
            try:
                got = src.entries(von=von, bis=bis, stichtag=tag)
            except Exception as exc:               # noqa: BLE001
                # Eine kaputte Quelle darf den GESAMTEN Kalender nicht
                # umbringen — aber sie darf auch nicht still ausfallen.
                logger.exception("Kalenderquelle '%s' fehlgeschlagen", src.key)
                quellen.append({"key": src.key, "label": src.label,
                                "count": 0, "ok": False})
                hinweise.append("Quelle '%s' konnte nicht gelesen werden: %s"
                                % (src.label, exc))
                continue

            entries.extend(got)
            quellen.append({"key": src.key, "label": src.label,
                            "count": len(got), "ok": True})
            h = src.hinweis()
            if h:
                hinweise.append(h)

        entries.sort(key=lambda e: (_RANK(e.ampel), e.von, e.source, e.ref_id))

        if info.get("warnung"):
            hinweise.append(info["warnung"])

        result = {
            "von": von,
            "bis": bis,
            "stichtag": tag,
            "zeitzone": info.get("zeitzone"),
            "stichtag_text": stichtag_mod.stichtag_text(info),
            "quellen": quellen,
            "hinweise": hinweise,
            "count": len(entries),
            "counts": self._counts(entries),
            "entries": [e.as_dict() for e in entries],
        }
        logger.debug("Kalender %s..%s: %d Eintraege aus %d Quellen",
                     von, bis, len(entries), len(quellen))
        return result

    @staticmethod
    def _counts(entries: Sequence[CalendarEntry]) -> Dict[str, int]:
        out = {"rot": 0, "gelb": 0, "gruen": 0, "neutral": 0}
        for e in entries:
            if e.ampel in out:
                out[e.ampel] += 1
        return out

# =============================================================================
# management/calendar/calendar_source.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Die SCHNITTSTELLE, an der sich jede zeitbezogene Quelle in den gemeinsamen
#   Kalender einhaengt. Heute: externe Vorgaenge (M010), Verfuegbarkeiten (M008),
#   Feiertage (M008). Morgen: Fristen, Berichts-Deadlines, Gantt (Welle 2) —
#   ohne dass eine bestehende Tabelle angefasst werden muss.
#
# ZWEI PFLICHTEN JEDER QUELLE (beide sind forensisch begruendet):
#
#   1) SIE PRUEFT SELBST DIE RECHTE. Der Kalender aggregiert nur; er kennt die
#      Semantik der Quelle nicht und koennte sie nicht korrekt kapseln. Eine
#      Quelle, die nichts liefern darf, liefert eine LEERE Liste — nicht etwa
#      "alles", weil ein Scope-Wert None war.
#
#   2) SIE SAGT, WENN SIE SCHWEIGT. Liefert eine Quelle nichts, weil die
#      Berechtigung fehlt oder ihre Tabellen fehlen, meldet sie das ueber
#      'hinweis()'. Ein Kalender, der unvollstaendig ist, ohne es zu sagen,
#      ist gefaehrlicher als gar keiner — der Ermittler wuerde annehmen, es
#      stuende nichts an (Grundregel 1: kein stilles Auslassen).
#
# Version: v0.7.385 · Build: 385 · 2026-07-12
# =============================================================================

from abc import ABC, abstractmethod
from typing import List, Optional

from management.calendar.calendar_entry import CalendarEntry


class CalendarSource(ABC):
    """Basisklasse aller Kalenderquellen."""

    #: Stabiler Quellenschluessel ('external', 'availability', 'holiday').
    key: str = "unbekannt"
    #: Klartext fuer die Oberflaeche.
    label: str = "Unbekannte Quelle"

    @abstractmethod
    def entries(self, *, von: str, bis: str, stichtag: str) -> List[CalendarEntry]:
        """
        Alle Eintraege der Quelle im Zeitraum [von, bis] (beide inklusiv),
        bereits RBAC-gefiltert. Ampeln werden gegen 'stichtag' berechnet.
        """
        raise NotImplementedError

    def hinweis(self) -> Optional[str]:
        """
        Warum liefert die Quelle (teilweise) nichts? None = nichts zu melden.
        Wird NACH entries() abgefragt (die Quelle darf den Hinweis dort setzen).
        """
        return None

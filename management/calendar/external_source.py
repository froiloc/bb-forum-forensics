# =============================================================================
# management/calendar/external_source.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Kalenderquelle fuer die WIEDERVORLAGE EXTERNER VORGAENGE (M010).
#   Liefert je Vorgang EINEN Zeitpunkt-Eintrag am Tag 'wiedervorlage_am'.
#
# WAS BEWUSST NICHT ERSCHEINT:
#   Abgeschlossene Vorgaenge ('erledigt'/'erfolglos') sind KEINE Wiedervorlage
#   mehr — sie stehen nicht im Kalender. Ihre Historie liegt im Zeitstrahl des
#   Falls (case_events) und im audit_log; sie ist damit nicht verloren, sie
#   verstopft nur nicht die Arbeitsliste.
#
# WAS BEWUSST AUCH AUSSERHALB DES ZEITRAUMS ERSCHEINT:
#   UEBERFAELLIGE Vorgaenge (wiedervorlage_am < von). Ein ueberfaelliger Vorgang
#   verschwindet sonst aus dem Blick, sobald man in den naechsten Monat
#   blaettert — genau das Versaeumnis, das dieses System verhindern soll
#   (Grundregel 1). Sie werden mit ihrem echten (vergangenen) Datum geliefert
#   und sind rot.
#
# RBAC (Pflicht 1 der CalendarSource): 'external.view'.
#   Scope 'alle'   -> alle Faelle.
#   Scope 'eigene' -> nur die dem Ermittler ZUGEWIESENEN Faelle (cases.assigned_to).
#   kein Recht     -> LEERE Liste + Hinweis (die Quelle schweigt nicht stumm).
#
# Version: v0.7.385 · Build: 385 · 2026-07-12
# =============================================================================

import logging
import sqlite3
from typing import List, Optional

from management.calendar.calendar_entry import CalendarEntry
from management.calendar.calendar_source import CalendarSource
from management.external.external_matters_repo import ExternalMattersRepo
from management.external.matter_status import OPEN_STATUSES, MatterStatus
from management.external import matter_kinds

logger = logging.getLogger(__name__)

CAP_EXTERNAL_VIEW = "external.view"


class ExternalSource(CalendarSource):
    """Externe Vorgaenge als Kalender-Zeitpunkte."""

    key = "external"
    label = "Externe Vorgaenge (Wiedervorlage)"

    def __init__(self, con: sqlite3.Connection, policy) -> None:
        self._con = con
        self._policy = policy
        self._hinweis: Optional[str] = None

    # --- Scope-Aufloesung ---------------------------------------------------
    def _allowed_case_ids(self) -> Optional[List[int]]:
        """
        None  -> alle Faelle (Scope 'alle').
        Liste -> genau diese Faelle (Scope 'eigene'; ggf. LEER).
        Wirft PermissionError, wenn die Faehigkeit ganz fehlt.
        """
        if not self._policy.can(CAP_EXTERNAL_VIEW):
            raise PermissionError(CAP_EXTERNAL_VIEW)
        scope = self._policy.scope(CAP_EXTERNAL_VIEW)
        if scope == "alle":
            return None
        # Scope 'eigene': nur zugewiesene Faelle. Ein Ermittler OHNE Zuweisung
        # bekommt eine leere Liste — und NICHT etwa 'alle' (das waere der
        # klassische Kapselungsbruch durch einen None-Wert).
        pid = getattr(self._policy, "person_id", None)
        if pid is None:
            return []
        rows = self._con.execute(
            "SELECT user_id FROM cases WHERE assigned_to = ?", (pid,)
        ).fetchall()
        return [int(r[0]) for r in rows]

    # --- CalendarSource -----------------------------------------------------
    def entries(self, *, von: str, bis: str,
                stichtag: str) -> List[CalendarEntry]:
        self._hinweis = None
        try:
            case_ids = self._allowed_case_ids()
        except PermissionError:
            self._hinweis = ("Externe Vorgaenge werden NICHT angezeigt: die "
                             "Faehigkeit '%s' fehlt." % CAP_EXTERNAL_VIEW)
            return []

        repo = ExternalMattersRepo(self._con)   # rein lesend (kein Writer)
        try:
            rows = repo.list_matters(user_ids=case_ids,
                                     statuses=list(OPEN_STATUSES))
        except sqlite3.OperationalError as exc:
            # Tabelle fehlt (Migration M010 nicht angewandt) -> MELDEN, nicht
            # verschweigen. Ein leerer Kalender ohne Grund waere eine Falle.
            self._hinweis = ("Externe Vorgaenge nicht lesbar (%s). Migration "
                             "anwenden: python -m management.migrate" % exc)
            logger.warning("ExternalSource: %s", exc)
            return []

        rows = repo.with_ampel(rows, stichtag)

        out: List[CalendarEntry] = []
        for r in rows:
            wv = r["wiedervorlage_am"]
            # Ueberfaellige IMMER mitnehmen (s. Kopfkommentar), sonst Zeitraum.
            ueberfaellig = MatterStatus.parse_date(wv) < MatterStatus.parse_date(stichtag)
            if not ueberfaellig and not (von <= wv <= bis):
                continue
            out.append(CalendarEntry(
                source=self.key,
                ref_id=int(r["id"]),
                von=wv, bis=wv,                     # Zeitpunkt
                titel="%s: %s" % (matter_kinds.label(r["kind"]), r["betreff"]),
                subject_kind="case",
                subject_id=int(r["user_id"]),
                subject_label=r.get("fall_username") or "",
                ampel=r["ampel"],
                ampel_grund=r["ampel_grund"],
                ziel="external",
            ))
        logger.debug("ExternalSource: %d Eintraege (%s..%s)", len(out), von, bis)
        return out

    def hinweis(self) -> Optional[str]:
        return self._hinweis

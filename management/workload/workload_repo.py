# =============================================================================
# management/workload/workload_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   NUR-LESENDES Read-Model der Ermittler-Lastverteilung (Build 335). Zeigt der
#   Chef-Ermittlerin je Ermittler die getragene Fall-Last (nach Ampel/Status)
#   und den unzugewiesenen Rueckstau als Verteilungs-Pool.
#
#   AUFROLLUNG (mc 2026-07-07): Die je Fall BELEGTE Klassifikation stammt aus
#   dem Ampel-Dashboard (DashboardRepo.list_case_overview -> CaseOverview mit
#   .ampel/.status/.assigned_to). Diese wird je assigned_to aufgezaehlt. Damit
#   ist die Ampel je Ermittler GARANTIERT deckungsgleich mit dem Dashboard —
#   eine Wahrheitsquelle, kein dupliziertes Ampel-Regelwerk (keine Drift).
#
#   Zusaetzlich: ALLE Ermittler erscheinen (auch mit 0 Faellen; person-
#   Liste ist die Grundmenge), und je Akteur ein Aktivitaets-Beleg aus dem
#   audit_log (Anzahl auditierter Aktionen + letzter Zeitpunkt).
#
#   KEIN Schreibpfad, KEINE Migration. coordinator.db ist nur-lesend
#   (Produktivbetrieb-Regel) -> KEIN Datenverlust-Risiko.
#
# GRUNDREGEL 1: Ermittler ohne Faelle werden mit 0 gefuehrt (nicht ausgelassen);
#   der unzugewiesene Rueckstau wird als eigene, markierte Zeile sichtbar
#   gemacht (nie still weggelassen).
#
# Build 701 (Ticket 95139d2a): is_active wandert je Zeile mit; GEFILTERT
#   wird hier NICHT (siehe _load_investigators).
# Version: v0.8.701 · Build: 701 · 2026-08-12
# =============================================================================

import logging
import sqlite3
from typing import Dict, List, Optional, Tuple

from management.dashboard.dashboard_repo import (
    AMPEL_GELB,
    AMPEL_GRUEN,
    AMPEL_ROT,
    DEFAULT_AMPEL_THRESHOLDS,
    AmpelThresholds,
    DashboardRepo,
)
from management.workload.investigator_load import BACKLOG_LABEL, InvestigatorLoad

logger = logging.getLogger(__name__)

# Fallstatus-Werte (Beleg: cases_admin --status open|in_progress|approved|closed).
_STATUS_OPEN = "open"
_STATUS_IN_PROGRESS = "in_progress"
_STATUS_APPROVED = "approved"
_STATUS_CLOSED = "closed"

# Pflichttabellen. Union aus dem, was WorkloadRepo direkt nutzt (person,
# audit_log), und dem, was die aufgerollte DashboardRepo braucht (cases,
# case_events, support_sessions). Fehlt eine, wird NICHT still degradiert,
# sondern handlungsleitend abgebrochen (Grundregel 1).
REQUIRED_TABLES = (
    "cases", "case_events", "support_sessions", "person", "audit_log",
)


class WorkloadSchemaError(Exception):
    """
    Erforderliche coordinator.db-Tabelle fehlt. Traegt eine handlungsleitende
    Meldung (welche Tabelle, was zu tun ist).
    """


class _LoadAccumulator:
    """
    Interner, veraenderlicher Sammler der Fall-Zaehlungen EINER Last-Zeile
    (ein Ermittler oder der Rueckstau). Modul-privat, kein Teil der API.
    """

    __slots__ = ("total", "rot", "gelb", "gruen",
                 "s_open", "s_prog", "s_appr", "s_closed")

    def __init__(self) -> None:
        self.total = 0
        self.rot = 0
        self.gelb = 0
        self.gruen = 0
        self.s_open = 0
        self.s_prog = 0
        self.s_appr = 0
        self.s_closed = 0

    def add(self, ampel: str, status: str) -> None:
        self.total += 1
        if ampel == AMPEL_ROT:
            self.rot += 1
        elif ampel == AMPEL_GELB:
            self.gelb += 1
        elif ampel == AMPEL_GRUEN:
            self.gruen += 1
        # Unbekannte Ampel bewusst NICHT still einordnen: sie zaehlt in total,
        # aber in keinen Farbtopf (waere sonst eine Fehlbehauptung). Sichtbar
        # bleibt sie ueber die Differenz total - (rot+gelb+gruen).
        if status == _STATUS_OPEN:
            self.s_open += 1
        elif status == _STATUS_IN_PROGRESS:
            self.s_prog += 1
        elif status == _STATUS_APPROVED:
            self.s_appr += 1
        elif status == _STATUS_CLOSED:
            self.s_closed += 1

    @property
    def active(self) -> int:
        return self.s_open + self.s_prog

    @property
    def done(self) -> int:
        return self.s_appr + self.s_closed


class WorkloadRepo:
    """NUR-LESENDES Aggregat ueber coordinator.db fuer die Lastverteilung."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row

    def _check_required_tables(self) -> None:
        have = {
            row[0] for row in self._con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        missing = [t for t in REQUIRED_TABLES if t not in have]
        if missing:
            raise WorkloadSchemaError(
                "Erforderliche Tabelle(n) fehlen in coordinator.db: %s. "
                "Bitte ausstehende Migrationen anwenden: "
                "python -m management.migrate" % ", ".join(missing)
            )

    def _load_investigators(self) -> List[sqlite3.Row]:
        """
        Alle Ermittler (Grundmenge — auch die ohne zugewiesene Faelle), direkt
        gelesen. Bewusst KEIN InvestigatorsRepo: dessen Konstruktor verlangt
        einen CoordinatorWriter (Schreibpfad), den dieses reine Lese-Werkzeug
        nicht braucht. Der SELECT spiegelt PersonRepo.list_persons() 1:1.
        """
        # Build 701 (Ticket 95139d2a): is_active wandert MIT, wenn die Spalte
        # da ist. DEFENSIV wie PersonRepo._select_cols: auf einem Bestand vor
        # M020 gibt es sie nicht, und dieses reine Lesewerkzeug darf daran
        # nicht brechen — es gilt dann jede Person als aktiv.
        #
        # GEFILTERT WIRD HIER NICHT. Das Repo liefert die GRUNDMENGE; wer
        # ausgeblendet wird, entscheidet die Sicht (PersonSichtbarkeit im
        # Endpunkt) — sonst haette der Umschalter "Inaktive einblenden" keine
        # Daten, aus denen er waehlen koennte, und der Aktenexport bekaeme
        # stillschweigend eine beschnittene Liste.
        spalten = ("id, system_username, display_name, is_investigator, "
                   "is_supervisor, is_support")
        if self._hat_is_active():
            spalten += ", is_active"
        return self._con.execute(
            "SELECT %s FROM person ORDER BY system_username ASC" % spalten
        ).fetchall()

    def _hat_is_active(self) -> bool:
        """True, wenn person.is_active existiert (Migration M020)."""
        return "is_active" in {
            r[1] for r in self._con.execute("PRAGMA table_info(person)")}

    def _audit_activity(self) -> Dict[int, Tuple[int, int]]:
        """
        actor_id -> (Anzahl auditierter Aktionen, letzter ts). System-Eintraege
        (actor_id IS NULL, z. B. Genesis/Migrationen/orphan_timeout) zaehlen
        bewusst NICHT als Ermittler-Aktivitaet.
        """
        out: Dict[int, Tuple[int, int]] = {}
        for r in self._con.execute(
            "SELECT actor_id, COUNT(*) AS c, MAX(ts) AS m FROM audit_log "
            "WHERE actor_id IS NOT NULL GROUP BY actor_id"
        ):
            out[int(r["actor_id"])] = (int(r["c"]), int(r["m"]))
        return out

    def list_workload(
        self,
        *,
        thresholds: AmpelThresholds = DEFAULT_AMPEL_THRESHOLDS,
        now: Optional[int] = None,
    ) -> List[InvestigatorLoad]:
        """
        Liefert je Ermittler eine InvestigatorLoad-Zeile (auch bei 0 Faellen)
        plus eine abschliessende Rueckstau-Zeile (is_backlog=True) fuer die
        unzugewiesenen Faelle.

        Ordnung (Verteilungs-Sicht 'was am dringlichsten Aufmerksamkeit braucht,
        steht oben'): Ermittler nach ROT absteigend, dann aktive Last
        absteigend, dann system_username; die Rueckstau-Zeile wird ANS ENDE
        gestellt (sie ist kein Ermittler-Rang). Das Frontend erlaubt
        Umsortierung.

        'thresholds'/'now' werden an DashboardRepo durchgereicht
        (deterministische Tests, Config-Schwellen).
        """
        self._check_required_tables()

        overviews = DashboardRepo(self._con).list_case_overview(
            thresholds=thresholds, now=now)
        investigators = self._load_investigators()
        activity = self._audit_activity()

        # Fall-Klassifikation je assigned_to aufrollen (None -> Rueckstau).
        buckets: Dict[Optional[int], _LoadAccumulator] = {}
        for ov in overviews:
            key = ov.assigned_to  # int oder None
            acc = buckets.get(key)
            if acc is None:
                acc = _LoadAccumulator()
                buckets[key] = acc
            acc.add(ov.ampel, ov.status)

        def _row(inv_id: int, sysname: str, disp: str,
                 is_inv: bool, is_sup: bool, is_supp: bool,
                 is_backlog: bool, acc: Optional[_LoadAccumulator],
                 act: Tuple[int, Optional[int]],
                 is_active: bool = True) -> InvestigatorLoad:
            a = acc if acc is not None else _LoadAccumulator()
            count, last = act
            return InvestigatorLoad(
                investigator_id=inv_id,
                system_username=sysname,
                display_name=disp,
                is_investigator=is_inv,
                is_supervisor=is_sup,
                is_support=is_supp,
                is_backlog=is_backlog,
                total_cases=a.total,
                ampel_rot=a.rot,
                ampel_gelb=a.gelb,
                ampel_gruen=a.gruen,
                status_open=a.s_open,
                status_in_progress=a.s_prog,
                status_approved=a.s_appr,
                status_closed=a.s_closed,
                active_cases=a.active,
                done_cases=a.done,
                audit_action_count=count,
                last_action_at=last,
                is_active=is_active,
            )

        loads: List[InvestigatorLoad] = []
        for inv in investigators:
            inv_id = int(inv["id"])
            count, last = activity.get(inv_id, (0, None))
            # Build 701: Altbestand ohne M020 gilt als aktiv (siehe
            # _load_investigators) — 'in inv.keys()' statt eines try/except,
            # damit die Annahme im Quelltext sichtbar ist.
            aktiv = (bool(inv["is_active"])
                     if "is_active" in inv.keys() else True)
            loads.append(_row(
                inv_id, inv["system_username"], inv["display_name"],
                bool(inv["is_investigator"]), bool(inv["is_supervisor"]),
                bool(inv["is_support"]), False, buckets.get(inv_id),
                (count, last), aktiv))

        # Ermittler nach Dringlichkeit ordnen (ROT desc, aktive Last desc,
        # system_username asc). Der Rueckstau wird NICHT mit einsortiert.
        loads.sort(key=lambda l: (-l.ampel_rot, -l.active_cases,
                                  l.system_username))

        # Rueckstau-Zeile ans Ende (unzugewiesene Faelle; Verteilungs-Pool).
        loads.append(_row(
            0, BACKLOG_LABEL, BACKLOG_LABEL, False, False, False, True,
            buckets.get(None), (0, None)))

        return loads

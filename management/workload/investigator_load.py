# =============================================================================
# management/workload/investigator_load.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Reines Lese-DTO (frozen dataclass) EINER Last-Zeile der Ermittler-
#   Lastverteilungs-Uebersicht (Build 335). Eigene Datei gemaess Grundregel 10
#   (jede Klasse in eine eigene Datei).
#
#   Eine Zeile ist ENTWEDER ein Ermittler (mit seiner getragenen Fall-Last)
#   ODER der unzugewiesene Rueckstau-Pool (is_backlog=True). Der Rueckstau ist
#   kein Ermittler; er wird bewusst in DERSELBEN flachen Liste gefuehrt (leicht
#   zu rendern/exportieren) und ueber is_backlog markiert/gesondert dargestellt.
#
# ZAEHLUNGEN ('messen, nicht rechnen'): total_cases sowie die Ampel- und
#   Status-Zaehler sind reine Auszaehlungen der je Fall BELEGTEN Klassifikation
#   (DashboardRepo.list_case_overview -> CaseOverview.ampel/.status), je
#   assigned_to aufgerollt. Es wird nichts geschaetzt oder hochgerechnet
#   (keine Aufwands-/Stundenbilanz — die Daten dafuer existieren nicht).
#
# AKTIVITAETS-BELEG: audit_action_count/last_action_at kommen aus dem audit_log
#   (Anzahl auditierter Aktionen dieses Akteurs + Zeitpunkt der letzten). Ein
#   ehrlicher Aktivitaets-Indikator, KEIN Durchsatz-/Qualitaetsmass.
#
# Version: v0.7.335 · Build: 335 · 2026-07-07
# =============================================================================

from dataclasses import dataclass
from typing import Optional

#: Anzeigename der Rueckstau-Zeile (unzugewiesene Faelle).
BACKLOG_LABEL: str = "(nicht zugewiesen)"


@dataclass(frozen=True)
class InvestigatorLoad:
    """
    Aggregierte Last-Zeile fuer die Verteilungs-Uebersicht (reines Lese-DTO).

    Identitaet:
        investigator_id — investigators.id; 0 fuer die Rueckstau-Zeile.
        system_username — Windows-SAMAccountName bzw. BACKLOG_LABEL.
        display_name    — Anzeigename bzw. BACKLOG_LABEL.
        is_investigator/is_supervisor/is_support — Rollenflags (bei Rueckstau
                          alle False).
        is_backlog      — True fuer die unzugewiesene Rueckstau-Zeile.

    Last (reine Auszaehlung der belegten Fall-Klassifikation):
        total_cases                 — Faelle in dieser Zeile insgesamt.
        ampel_rot/gelb/gruen        — Anzahl je Ampel (DashboardRepo-Semantik).
        status_open/in_progress/approved/closed — Anzahl je Fallstatus.
        active_cases                — open + in_progress.
        done_cases                  — approved + closed.

    Aktivitaets-Beleg (aus audit_log; bei Rueckstau 0/None):
        audit_action_count — Anzahl auditierter Aktionen dieses Akteurs.
        last_action_at     — Unix-Sekunden der letzten auditierten Aktion.
    """
    investigator_id: int
    system_username: str
    display_name: str
    is_investigator: bool
    is_supervisor: bool
    is_support: bool
    is_backlog: bool

    total_cases: int
    ampel_rot: int
    ampel_gelb: int
    ampel_gruen: int
    status_open: int
    status_in_progress: int
    status_approved: int
    status_closed: int
    active_cases: int
    done_cases: int

    audit_action_count: int
    last_action_at: Optional[int]

# =============================================================================
# management/cases/escalation.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fallsteuerung (AP-2F)
# =============================================================================
# Zweck (Idee 23 — Eskalations-/Benachrichtigungsregeln):
#   Wertet den Fallzustand gegen TRANSPARENTE, konfigurierbare Regeln aus und
#   erhebt daraus belegte Eskalationen (fuer die Chef-Ermittlerin). Rein lesende
#   AUSWERTUNG/Anzeige; das auditierte BESTAETIGEN/Handeln einer Eskalation ist
#   bewusst ein spaeterer, schreibender Schritt (F3) — hier NICHT enthalten.
#
#   REGELN (Code = Wahrheit, Schwellen aus config.yaml):
#     R1 fall_ueberfaellig  — offener Fall, Ampel rot UND seit >= red_overdue_days
#                             inaktiv. Severity 'hoch'.
#     R2 fall_unbearbeitet  — zugewiesener Fall im Status 'open' seit
#                             >= stale_open_days inaktiv. Severity 'mittel'.
#                             (Uebersprungen, wenn R1 fuer den Fall schon greift
#                             — keine Doppelmeldung.)
#     R3 rueckstau_hoch     — unzugewiesener Rueckstau >= backlog_high (systemisch,
#                             subject_id None). Severity 'hoch'.
#
#   BELEGTREUE (GR1): jede Eskalation nennt die konkreten Signale (Tage inaktiv,
#   Status, Zahl). Keine Regel feuert ohne belegte Bedingung. now injizierbar.
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

_DAY = 86400
_DONE_STATUSES = ("approved", "closed")
_SEVERITY_RANK = {"hoch": 0, "mittel": 1, "niedrig": 2}


@dataclass(frozen=True)
class EscalationThresholds:
    red_overdue_days: int = 30     # rote Faelle: ab so vielen Tagen Inaktivitaet
    stale_open_days: int = 14      # offene zugewiesene Faelle: Inaktivitaets-Grenze
    backlog_high: int = 10         # unzugewiesener Rueckstau: systemische Grenze


@dataclass(frozen=True)
class EscalationItem:
    rule_code: str
    label: str
    severity: str                  # 'hoch' | 'mittel' | 'niedrig'
    subject_id: Optional[int]         # None = systemisch (kein Einzelfall)
    message: str                   # belegte Begruendung
    days_inactive: Optional[int]


@dataclass(frozen=True)
class EscalationReport:
    generated_at: int
    total_cases: int
    items: List[EscalationItem]
    count_hoch: int
    count_mittel: int
    count_niedrig: int


def _days_inactive(ov: dict, now: int) -> Optional[int]:
    la = ov.get("last_activity_at")
    if la is None:
        return None
    return max(0, (int(now) - int(la)) // _DAY)


def evaluate_escalations(overviews: List[dict],
                         thresholds: EscalationThresholds,
                         now: int) -> EscalationReport:
    """
    REINE Regel-Auswertung ueber CaseOverview-dicts (dateilos testbar).
    """
    items: List[EscalationItem] = []
    overdue_uids = set()
    unassigned = 0

    for ov in overviews:
        status = ov.get("status")
        if ov.get("assigned_to") is None:
            unassigned += 1
        if status in _DONE_STATUSES:
            continue
        uid = int(ov.get("subject_id"))
        ampel = ov.get("ampel") or "gruen"
        di = _days_inactive(ov, now)

        # R1 fall_ueberfaellig
        if ampel == "rot" and di is not None and di >= thresholds.red_overdue_days:
            overdue_uids.add(uid)
            items.append(EscalationItem(
                rule_code="fall_ueberfaellig", label="Fall ueberfaellig",
                severity="hoch", subject_id=uid,
                message="Fall %d (%s): rote Ampel, %d Tage inaktiv (>= %d)."
                        % (uid, ov.get("username") or "?", di,
                           thresholds.red_overdue_days),
                days_inactive=di))

    # R2 fall_unbearbeitet (nach R1, damit Doppelmeldung entfaellt)
    for ov in overviews:
        status = ov.get("status")
        if status != "open" or ov.get("assigned_to") is None:
            continue
        uid = int(ov.get("subject_id"))
        if uid in overdue_uids:
            continue
        di = _days_inactive(ov, now)
        if di is not None and di >= thresholds.stale_open_days:
            items.append(EscalationItem(
                rule_code="fall_unbearbeitet", label="Fall unbearbeitet",
                severity="mittel", subject_id=uid,
                message="Fall %d (%s): zugewiesen, Status open, %d Tage inaktiv "
                        "(>= %d)." % (uid, ov.get("username") or "?", di,
                                      thresholds.stale_open_days),
                days_inactive=di))

    # R3 rueckstau_hoch (systemisch)
    if unassigned >= thresholds.backlog_high:
        items.append(EscalationItem(
            rule_code="rueckstau_hoch", label="Rueckstau hoch",
            severity="hoch", subject_id=None,
            message="Unzugewiesener Rueckstau: %d Faelle (>= %d)."
                    % (unassigned, thresholds.backlog_high),
            days_inactive=None))

    # Ordnung: Severity (hoch>mittel>niedrig), dann meiste Inaktivitaet, dann uid.
    items.sort(key=lambda i: (_SEVERITY_RANK.get(i.severity, 9),
                              -(i.days_inactive or 0),
                              (i.subject_id if i.subject_id is not None else -1)))

    return EscalationReport(
        generated_at=int(now), total_cases=len(overviews), items=items,
        count_hoch=sum(1 for i in items if i.severity == "hoch"),
        count_mittel=sum(1 for i in items if i.severity == "mittel"),
        count_niedrig=sum(1 for i in items if i.severity == "niedrig"))


def escalation_thresholds_from_config(cfg) -> EscalationThresholds:
    """Schwellen aus config.yaml (escalation.*), sonst Vorgaben. None-sicher."""
    d = EscalationThresholds()
    if cfg is None:
        return d
    try:
        node = cfg.get("escalation", {}) or {}
        return EscalationThresholds(
            red_overdue_days=int(node.get("red_overdue_days", d.red_overdue_days)),
            stale_open_days=int(node.get("stale_open_days", d.stale_open_days)),
            backlog_high=int(node.get("backlog_high", d.backlog_high)))
    except Exception:
        return d


def escalation_to_dict(report: EscalationReport) -> dict:
    return {
        "generated_at": report.generated_at,
        "total_cases": report.total_cases,
        "count_hoch": report.count_hoch,
        "count_mittel": report.count_mittel,
        "count_niedrig": report.count_niedrig,
        "items": [
            {"rule_code": i.rule_code, "label": i.label, "severity": i.severity,
             "subject_id": i.subject_id, "message": i.message,
             "days_inactive": i.days_inactive}
            for i in report.items
        ],
    }

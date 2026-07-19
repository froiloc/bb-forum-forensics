# =============================================================================
# management/cases/next_actions.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fallsteuerung (AP-2F)
# =============================================================================
# Zweck (Idee 22 — "Naechstbeste Aktion"-Warteschlange):
#   Eine priorisierte, BELEGTE To-do-Liste je Ermittler (Scope 'eigene') bzw.
#   falluebergreifend (Scope 'alle'). Fuer jeden offenen Fall wird die naechste
#   sinnvolle Handlung als KATEGORIE abgeleitet; die Begruendung zitiert die
#   TATSAECHLICHEN Signale (Ampel-Begruendung aus DashboardRepo, Status,
#   Zuweisung) — KEIN erfundener Rat (GR1: keine Behauptung ohne Beleg).
#
#   Datenquelle: DashboardRepo.CaseOverview (Ampel/last_activity/ampel_reason
#   sind dort bereits belegt berechnet). Rein lesend; now injizierbar.
#
#   Abgeschlossene Faelle (status approved/closed) brauchen keine Aktion und
#   werden NICHT in die Schlange aufgenommen — aber GEZAEHLT (done_excluded),
#   nicht stillschweigend verschluckt.
#
# Version: v0.7.452 · Build: 452 · 2026-07-19
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

_DONE_STATUSES = ("approved", "closed")

# Dringlichkeitsstufen (Ordnung: dringend < bald < routine).
_URGENCY_RANK = {"dringend": 0, "bald": 1, "routine": 2}


@dataclass(frozen=True)
class NextAction:
    user_id: int
    username: str
    action: str            # Handlungs-Kategorie
    reason: str            # belegte Begruendung (zitiert echte Signale)
    urgency: str           # 'dringend' | 'bald' | 'routine'
    priority: int
    ampel: str
    status: str
    assigned: bool
    last_activity_at: Optional[int]


@dataclass(frozen=True)
class QueueResult:
    generated_at: int
    scope: str
    total_cases: int
    actionable: int
    done_excluded: int
    items: List[NextAction]


def derive_action(ov: dict, scope: str) -> Optional[NextAction]:
    """
    REINE Ableitung der naechsten Aktion aus EINER CaseOverview (als dict).
    None -> Fall ist abgeschlossen (keine Aktion). Die Aktion ist eine
    Kategorie; die Begruendung nennt die belegten Signale.
    """
    status = ov.get("status")
    if status in _DONE_STATUSES:
        return None

    ampel = ov.get("ampel") or "gruen"
    ampel_reason = ov.get("ampel_reason") or ""
    assigned = ov.get("assigned_to") is not None
    priority = int(ov.get("priority") or 3)

    if not assigned:
        # Nur im Scope 'alle' relevant (Scope 'eigene' liefert nur zugewiesene).
        action = "Fall zuweisen"
        urgency = "dringend" if ampel == "rot" else "bald"
        reason = "unzugewiesen" + (("; " + ampel_reason) if ampel_reason else "")
    elif ampel == "rot":
        action = "ueberfaellig — sichten/bearbeiten"
        urgency = "dringend"
        reason = "Status %s; %s" % (status, ampel_reason or "rote Ampel")
    elif ampel == "gelb":
        action = "bald bearbeiten"
        urgency = "bald"
        reason = "Status %s; %s" % (status, ampel_reason or "gelbe Ampel")
    else:
        if status == "open":
            action = "Bearbeitung beginnen"
        else:
            action = "weiter bearbeiten"
        urgency = "routine"
        reason = "Status %s; %s" % (status, ampel_reason or "aktiv")

    return NextAction(
        user_id=int(ov.get("user_id")), username=ov.get("username") or "?",
        action=action, reason=reason, urgency=urgency, priority=priority,
        ampel=ampel, status=status, assigned=assigned,
        last_activity_at=ov.get("last_activity_at"))


def build_queue(overviews: List[dict], scope: str, now: int) -> QueueResult:
    """
    REINE Warteschlangen-Bildung aus CaseOverview-dicts (dateilos testbar).
    Ordnung: Dringlichkeit (dringend>bald>routine), dann Prioritaet (1 zuerst),
    dann laengste Inaktivitaet (aeltestes last_activity zuerst), dann user_id.
    """
    items: List[NextAction] = []
    done = 0
    for ov in overviews:
        act = derive_action(ov, scope)
        if act is None:
            done += 1
        else:
            items.append(act)

    def _key(a: NextAction):
        # last_activity None -> als 0 (sehr alt) behandelt -> zuerst.
        la = a.last_activity_at if a.last_activity_at is not None else 0
        return (_URGENCY_RANK.get(a.urgency, 9), a.priority, la, a.user_id)

    items.sort(key=_key)

    return QueueResult(
        generated_at=int(now), scope=("eigene" if scope == "eigene" else "alle"),
        total_cases=len(overviews), actionable=len(items), done_excluded=done,
        items=items)


def queue_to_dict(result: QueueResult) -> dict:
    """Serialisierung fuer Sicht/CLI (stabile Schluessel)."""
    return {
        "generated_at": result.generated_at,
        "scope": result.scope,
        "total_cases": result.total_cases,
        "actionable": result.actionable,
        "done_excluded": result.done_excluded,
        "items": [
            {"user_id": a.user_id, "username": a.username, "action": a.action,
             "reason": a.reason, "urgency": a.urgency, "priority": a.priority,
             "ampel": a.ampel, "status": a.status, "assigned": a.assigned,
             "last_activity_at": a.last_activity_at}
            for a in result.items
        ],
    }

# =============================================================================
# management/cases/handover_log.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fallsteuerung (AP-2G)
# =============================================================================
# Zweck (Idee 30 — Uebergabe-Protokoll bei Fall-Umverteilung):
#   Rekonstruiert je Fall, WER wann VON WEM einen Fall uebernommen hat. Quelle
#   ist das hash-verkettete audit_log (permanenter Beleg): jede Zuweisung wird
#   als CASE_ASSIGNED mit content {"assigned_to": <person_id|null>} und actor_id
#   (wer die Zuweisung ausfuehrte) festgehalten (Beleg cases_repo.py: assign).
#
#   DER VORHERIGE STAND ('von wem') steht NICHT im einzelnen Ereignis, sondern
#   ergibt sich aus der CHRONOLOGISCHEN ABFOLGE je Fall — genau darum wird hier
#   je Fall nach seq geordnet und der jeweils vorherige assigned_to als 'from'
#   uebernommen (kein erfundener Verlauf, GR1). Klassifikation je Uebergang:
#     initial       — None -> X   (erste Zuweisung)
#     reassignment  — X -> Y       (echte Umverteilung; das eigentliche Protokoll)
#     unassignment  — X -> None    (Zuruecknahme in den Rueckstau)
#
#   REINE Rekonstruktion (build_handovers) -> dateilos testbar. Rein lesend.
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class HandoverEntry:
    subject_id: int
    seq: int
    ts: int
    kind: str                       # 'initial' | 'reassignment' | 'unassignment'
    from_person_id: Optional[int]
    from_name: Optional[str]
    to_person_id: Optional[int]
    to_name: Optional[str]
    by_person_id: Optional[int]     # actor (wer die Zuweisung ausfuehrte)
    by_name: Optional[str]


@dataclass(frozen=True)
class HandoverReport:
    generated_at: int
    entries: List[HandoverEntry]
    reassignment_count: int
    cases_with_handover: int


def _name(pid: Optional[int], names: Dict[int, str]) -> Optional[str]:
    if pid is None:
        return None
    return names.get(pid) or ("#%d" % pid)


def build_handovers(assign_events: List[dict], names: Dict[int, str],
                    now: int) -> HandoverReport:
    """
    REINE Rekonstruktion. assign_events: Liste von
    {subject_id, seq, ts, actor_id, assigned_to} — muss NICHT vorsortiert sein;
    wird hier je Fall nach seq geordnet. names: {person_id: Anzeigename}.
    """
    # Je Fall chronologisch (seq) ordnen.
    by_case: Dict[int, List[dict]] = {}
    for ev in assign_events:
        by_case.setdefault(int(ev["subject_id"]), []).append(ev)
    for lst in by_case.values():
        lst.sort(key=lambda e: int(e["seq"]))

    entries: List[HandoverEntry] = []
    cases_with_reassign = set()
    for uid, lst in by_case.items():
        prev: Optional[int] = None
        for ev in lst:
            to = ev.get("assigned_to")
            to = int(to) if to is not None else None
            actor = ev.get("actor_id")
            actor = int(actor) if actor is not None else None
            if prev is None and to is not None:
                kind = "initial"
            elif prev is not None and to is None:
                kind = "unassignment"
            elif prev is not None and to is not None and prev != to:
                kind = "reassignment"
                cases_with_reassign.add(uid)
            elif prev is not None and to is not None and prev == to:
                # Re-Zuweisung an dieselbe Person -> kein echter Uebergang;
                # dennoch als Beleg gefuehrt (kein stilles Verschlucken, GR1).
                kind = "reassignment"
            else:
                kind = "initial"
            entries.append(HandoverEntry(
                subject_id=uid, seq=int(ev["seq"]), ts=int(ev["ts"]), kind=kind,
                from_person_id=prev, from_name=_name(prev, names),
                to_person_id=to, to_name=_name(to, names),
                by_person_id=actor, by_name=_name(actor, names)))
            prev = to

    # Chronologische Gesamtordnung (seq absteigend = neueste zuerst).
    entries.sort(key=lambda e: e.seq, reverse=True)
    reassignments = sum(1 for e in entries if e.kind == "reassignment")
    return HandoverReport(
        generated_at=int(now), entries=entries,
        reassignment_count=reassignments,
        cases_with_handover=len(cases_with_reassign))


def handover_to_dict(report: HandoverReport) -> dict:
    return {
        "generated_at": report.generated_at,
        "reassignment_count": report.reassignment_count,
        "cases_with_handover": report.cases_with_handover,
        "entries": [
            {"subject_id": e.subject_id, "seq": e.seq, "ts": e.ts, "kind": e.kind,
             "from_person_id": e.from_person_id, "from_name": e.from_name,
             "to_person_id": e.to_person_id, "to_name": e.to_name,
             "by_person_id": e.by_person_id, "by_name": e.by_name}
            for e in report.entries
        ],
    }

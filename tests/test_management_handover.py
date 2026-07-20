# =============================================================================
# tests/test_management_handover.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fallsteuerung (AP-2G)
# =============================================================================
# Testsuite fuer Build 455: Uebergabe-Protokoll (handover_log + handover_repo).
#
# HO01 — build_handovers: erste Zuweisung -> 'initial' (from None)
# HO02 — build_handovers: X->Y -> 'reassignment' mit korrektem from/to
# HO03 — build_handovers: X->None -> 'unassignment' (Rueckstau)
# HO04 — build_handovers: Namensaufloesung von/an/durch; unbekannt -> #id
# HO05 — build_handovers: reassignment_count + cases_with_handover korrekt
# HO06 — build_handovers: chronologische Rekonstruktion aus unsortierter Eingabe
# HO07 — HandoverRepo: liest CASE_ASSIGNED aus audit_log; content.assigned_to
# HO08 — HandoverRepo: Filter subject_id; handover_to_dict serialisierbar
# HO09 — HandoverRepo: Legacy-Payloads (Schluessel 'user_id', vor M019)
#        werden per Fallback weiterhin gelesen (audit_log ist append-only)
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.cases.handover_log import (          # noqa: E402
    build_handovers, handover_to_dict,
)
from management.cases.handover_repo import HandoverRepo   # noqa: E402
from management.audit.event_types import EventType        # noqa: E402

_NAMES = {1: "Chefin", 2: "Mueller", 3: "Gamma"}


def _ev(subject_id, seq, assigned_to, actor_id, ts=1000):
    return {"subject_id": subject_id, "seq": seq, "ts": ts,
            "actor_id": actor_id, "assigned_to": assigned_to}


def test_ho01_initial():
    rep = build_handovers([_ev(18, 1, 2, 1)], _NAMES, 999)
    assert rep.entries[0].kind == "initial"
    assert rep.entries[0].from_person_id is None
    assert rep.entries[0].to_name == "Mueller"


def test_ho02_reassignment():
    evs = [_ev(18, 1, 2, 1), _ev(18, 2, 3, 1)]
    rep = build_handovers(evs, _NAMES, 999)
    re_entry = [e for e in rep.entries if e.kind == "reassignment"][0]
    assert re_entry.from_person_id == 2 and re_entry.to_person_id == 3
    assert re_entry.from_name == "Mueller" and re_entry.to_name == "Gamma"


def test_ho03_unassignment():
    evs = [_ev(18, 1, 2, 1), _ev(18, 2, None, 1)]
    rep = build_handovers(evs, _NAMES, 999)
    un = [e for e in rep.entries if e.kind == "unassignment"][0]
    assert un.from_person_id == 2 and un.to_person_id is None


def test_ho04_names_and_unknown():
    rep = build_handovers([_ev(18, 1, 99, 1)], _NAMES, 999)   # 99 unbekannt
    assert rep.entries[0].to_name == "#99"
    assert rep.entries[0].by_name == "Chefin"


def test_ho05_counts():
    evs = [_ev(18, 1, 2, 1), _ev(18, 2, 3, 1),        # 1 reassignment
           _ev(19, 3, 2, 1)]                           # nur initial
    rep = build_handovers(evs, _NAMES, 999)
    assert rep.reassignment_count == 1
    assert rep.cases_with_handover == 1


def test_ho06_chronological_from_unsorted():
    # bewusst unsortiert eingegeben
    evs = [_ev(18, 2, 3, 1), _ev(18, 1, 2, 1)]
    rep = build_handovers(evs, _NAMES, 999)
    # nach seq geordnet rekonstruiert: seq1 initial(->2), seq2 reassignment(2->3)
    seq1 = [e for e in rep.entries if e.seq == 1][0]
    seq2 = [e for e in rep.entries if e.seq == 2][0]
    assert seq1.kind == "initial" and seq2.from_person_id == 2


# -- Repo-Integration ---------------------------------------------------------

def _audit_db():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE person(id INTEGER PRIMARY KEY, display_name TEXT, "
                "system_username TEXT)")
    con.executemany("INSERT INTO person VALUES(?,?,?)",
                    [(1, "Chefin", "h001"), (2, "Mueller", "h002"),
                     (3, "Gamma", "h003")])
    con.execute("CREATE TABLE audit_log(seq INTEGER PRIMARY KEY AUTOINCREMENT, "
                "ts INTEGER, actor_id INTEGER, event_type TEXT, target_type TEXT, "
                "target_id TEXT, content TEXT)")
    return con


def _log(con, seq, actor, uid, assigned_to, ts=1000):
    con.execute("INSERT INTO audit_log(seq,ts,actor_id,event_type,target_type,"
                "target_id,content) VALUES(?,?,?,?,?,?,?)",
                (seq, ts, actor, EventType.CASE_ASSIGNED, "case", str(uid),
                 json.dumps({"subject_id": uid, "assigned_to": assigned_to})))


def test_ho07_repo_reads_audit():
    con = _audit_db()
    _log(con, 1, 1, 18, 2)
    _log(con, 2, 1, 18, 3)      # reassignment 2->3
    con.commit()
    rep = HandoverRepo(con).compute(now=999)
    assert rep.reassignment_count == 1
    re_entry = [e for e in rep.entries if e.kind == "reassignment"][0]
    assert re_entry.from_name == "Mueller" and re_entry.to_name == "Gamma"


def test_ho08_repo_filter_and_dict():
    con = _audit_db()
    _log(con, 1, 1, 18, 2)
    _log(con, 2, 1, 19, 3)
    con.commit()
    rep = HandoverRepo(con).compute(subject_id=18, now=999)
    assert all(e.subject_id == 18 for e in rep.entries)
    d = handover_to_dict(rep)
    assert json.dumps(d, ensure_ascii=False) and "entries" in d


def test_ho09_legacy_payload_user_id_wird_weiter_gelesen():
    """HO09 (Build 469): audit_log ist append-only — VOR M019 geschriebene
    CASE_ASSIGNED-Payloads tragen den Schluessel 'user_id'. Der Repo-Fallback
    payload.get('subject_id', payload.get('user_id')) muss sie weiterhin
    lesen; Alt- und Neu-Payloads desselben Falls bilden EINE Historie."""
    con = _audit_db()
    # Alt-Payload (Stand vor M019): Schluessel 'user_id'.
    con.execute("INSERT INTO audit_log(seq,ts,actor_id,event_type,target_type,"
                "target_id,content) VALUES(?,?,?,?,?,?,?)",
                (1, 1000, 1, EventType.CASE_ASSIGNED, "case", "18",
                 json.dumps({"user_id": 18, "assigned_to": 2})))
    # Neu-Payload (Stand ab M019): Schluessel 'subject_id'.
    _log(con, 2, 1, 18, 3)
    con.commit()
    rep = HandoverRepo(con).compute(subject_id=18, now=999)
    # Beide Eintraege gelesen: seq1 initial(->2), seq2 reassignment(2->3).
    assert rep.reassignment_count == 1
    re_entry = [e for e in rep.entries if e.kind == "reassignment"][0]
    assert re_entry.from_person_id == 2 and re_entry.to_person_id == 3
    assert all(e.subject_id == 18 for e in rep.entries)

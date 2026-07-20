# =============================================================================
# management/case_events/case_events_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Zugriffsschicht auf den Ereigniszeitstrahl 'case_events' (Idee 11) in
#   coordinator.db — das Lesemodell für Ampel-Dashboard (Tag 3) und
#   Nutzerinfo-Tab.
#
#   Zwei Entstehungswege für Zeitstrahl-Zeilen (Beleg: mc 2026-07-02):
#     1. AUTOMATISCHE SPIEGELUNG fachlicher cases-Writes — Fallanlage,
#        Zuweisung, Statuswechsel, Freigabe. Der Beleg ist der ohnehin
#        geschriebene CASE_*-audit_log-Eintrag; die Zeitstrahl-Zeile
#        entsteht IM SELBEN Transaktionsrahmen über den after_audit-Hook
#        des CoordinatorWriter und trägt dessen seq in 'audit_seq'.
#        (Implementiert in CasesRepo via insert_event_row(), unten.)
#     2. MANUELLE EINTRÄGE der Ermittler (add_manual_event) — eigener
#        Beleg CASE_EVENT_ADDED. Der Eintragstext liegt NUR im
#        case_events.payload; der Audit-Payload enthält nur Faktum +
#        Textlänge (Sensibilitätsregel analog cases.note, B7 §3.4).
#
#   event_kind-Vokabular wird hier im CODE validiert (EVENT_KINDS, analog
#   audit_log.event_type via EventType.ALL) — bewusst kein CHECK-Constraint
#   in der DDL, damit neue kinds additiv bleiben (kein Tabellen-Rebuild).
#
# Beleg: Bauplan B7 v0.8 §8, Roadmap "Tag 2+" (v0.1), mc 2026-07-02.
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import json
import logging
import sqlite3
import time
from typing import Any, Dict, FrozenSet, List, Optional

from management.audit.event_types import EventType
from management.gateway.coordinator_writer import CoordinatorWriter

logger = logging.getLogger(__name__)

#: Eingefrorenes Zeitstrahl-Vokabular. Erweitern, nie entfernen/umbenennen
#: (Werte stehen dauerhaft in coordinator.db und in Berichten).
EVENT_KINDS: FrozenSet[str] = frozenset(
    {
        "case_created",    # Spiegel: CasesRepo.create_case  (Beleg CASE_CREATED)
        "assigned",        # Spiegel: CasesRepo.assign       (Beleg CASE_ASSIGNED)
        "status_changed",  # Spiegel: CasesRepo.set_status   (Beleg CASE_STATUS_CHANGED)
        "approved",        # Spiegel: CasesRepo.set_status('approved') (Beleg CASE_APPROVED)
        "manual",          # manueller Ermittler-Eintrag     (Beleg CASE_EVENT_ADDED)
        # Build 385: Spiegel der externen Vorgaenge (ExternalMattersRepo;
        # Belege EXTERNAL_MATTER_CREATED/_DEFERRED/_ANSWERED/_CLOSED).
        # payload.action in {created, deferred, answered, closed} — damit macht
        # der Zeitstrahl das WARTEN eines Falls sichtbar: wer wann worauf
        # gewartet und wie oft er die Wiedervorlage verschoben hat.
        "external_matter",
        # Build 387: Spiegel der Ergebnisbewertung (ResultsRepo; Beleg
        # ASSESSMENT_RECORDED). Der Zeitstrahl macht den ERKENNTNISGEWINN
        # sichtbar: aus 'Verdacht' wird 'wahrscheinlich' wird 'gerichtsfest'.
        "assessment",
    }
)


class CaseEventsError(Exception):
    """Fachlicher Fehler (z. B. Fall nicht vorhanden, ungültiger event_kind)."""


def _canonical_json(obj: Any) -> str:
    """
    Kanonische JSON-Serialisierung — identische Konvention wie audit/hashing.py
    (sort_keys, kompakt, ensure_ascii=False), damit Zeitstrahl-Payloads
    byte-stabil und diff-freundlich sind.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def insert_event_row(
    con: sqlite3.Connection,
    *,
    subject_id: int,
    event_kind: str,
    payload: Optional[Dict[str, Any]],
    created_by: Optional[int],
    created_at: int,
    audit_seq: int,
) -> None:
    """
    Fügt eine Zeitstrahl-Zeile ein. Muss in der aktiven Schreibtransaktion
    des zugehörigen audited_write laufen (after_audit-Hook), damit
    Fach-Write, Audit-Beleg und Zeitstrahl-Zeile atomar committen.

    Modul-Funktion (keine Repo-Methode), damit CasesRepo sie ohne
    Zirkularität nutzen kann: case_events -> gateway/audit, cases ->
    case_events. Wirft CaseEventsError bei ungültigem event_kind — das
    rollt via Gateway die GESAMTE Transaktion zurück (kein Teilzustand).
    """
    if event_kind not in EVENT_KINDS:
        raise CaseEventsError("Unbekannter event_kind: %r" % event_kind)
    con.execute(
        "INSERT INTO case_events "
        "(subject_id, event_kind, payload, created_by, created_at, audit_seq) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            subject_id,
            event_kind,
            _canonical_json(payload) if payload else "",
            created_by,
            created_at,
            audit_seq,
        ),
    )


class CaseEventsRepo:
    """Lese- und (auditierte) Schreibmethoden auf dem Ereigniszeitstrahl."""

    def __init__(self, con: sqlite3.Connection, writer: CoordinatorWriter) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._writer = writer

    # ------------------------------------------------------------------- Lesen
    def list_events(
        self, subject_id: int, *, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Chronologischer Zeitstrahl eines Falls (älteste zuerst; id als
        Tie-Breaker bei sekundengleichen Einträgen). created_by wird zum
        system_username aufgelöst (NULL -> None = System). payload wird
        als dict zurückgegeben (leerer payload -> {}).
        """
        sql = (
            "SELECT e.id, e.subject_id, e.event_kind, e.payload, "
            "       e.created_by, i.system_username AS created_by_username, "
            "       e.created_at, e.audit_seq "
            "FROM case_events e "
            "LEFT JOIN person i ON i.id = e.created_by "
            "WHERE e.subject_id = ? "
            "ORDER BY e.created_at ASC, e.id ASC"
        )
        params: tuple = (subject_id,)
        if limit is not None:
            sql += " LIMIT ?"
            params = (subject_id, int(limit))
        out: List[Dict[str, Any]] = []
        for row in self._con.execute(sql, params):
            d = dict(row)
            d["payload"] = json.loads(d["payload"]) if d["payload"] else {}
            out.append(d)
        return out

    # --------------------------------------------------------------- Schreiben
    def add_manual_event(
        self, subject_id: int, text: str, *,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> int:
        """
        Manueller Zeitstrahl-Eintrag eines Ermittlers. Beleg CASE_EVENT_ADDED;
        der Text selbst liegt nur im case_events.payload (Audit nur Faktum +
        Länge). Gibt die audit_log-seq zurück (== audit_seq der Zeile).
        """
        if not text or not text.strip():
            raise CaseEventsError("Leerer Eintragstext ist nicht zulässig.")
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            # Fall-Existenz INNERHALB der Schreibsperre prüfen (kein TOCTOU).
            if con.execute(
                "SELECT 1 FROM cases WHERE subject_id = ?", (subject_id,)
            ).fetchone() is None:
                raise CaseEventsError("Kein Fall subject_id=%s." % subject_id)
            # Audit-Payload: Faktum + Länge, NICHT der Text (Sensibilität).
            return {"subject_id": subject_id, "event_kind": "manual",
                    "text_len": len(text)}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            insert_event_row(
                con,
                subject_id=subject_id,
                event_kind="manual",
                payload={"text": text},
                created_by=actor_id,
                created_at=now,
                audit_seq=seq,
            )

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.CASE_EVENT_ADDED,
            actor_id=actor_id, target_type="case", target_id=str(subject_id),
            meta=meta, after_audit=_after,
        )

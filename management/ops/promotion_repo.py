# =============================================================================
# management/ops/promotion_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Betrieb/Governance (AP-2G)
# =============================================================================
# Zweck:
#   Zugriffsschicht auf 'forum_promotion' (M015). SCHREIBEN ausschliesslich
#   ueber das CoordinatorWriter-Gateway: fachlicher Write + audit_log-Beleg
#   committen in EINER Transaktion oder gar nicht. Es gibt damit keine
#   Promotions-Entscheidung ohne lueckenlosen Beleg (Grundregel 1).
#
#   KEIN case_events-Zeitstrahl-Spiegel (mc 2026-07-20): ein 'neu'-Kandidat hat
#   noch keine cases-Zeile; ein Spiegel-Insert mit FK subject_id -> cases braeche.
#   Der Beleg liegt vollstaendig im hash-verketteten audit_log.
#
# SENSIBILITAETSREGEL (uebernommen von CasesRepo.set_note / ExternalMattersRepo):
#   Freitexte (grund, herkunft) gehen NICHT in den audit_log-Payload. Dort
#   stehen nur FAKTEN (subject_id, von-Zustand, auf-Zustand) und die TEXTLAENGE.
#   Der Text selbst lebt in forum_promotion, wo die RBAC-Kapselung (ops.view)
#   greift. Das Audit-Log ist ein Beleg, kein Aktenordner.
#
# EXISTENZPRUEFUNG DES KANDIDATEN:
#   'forum_promotion' hat bewusst KEINEN FK auf cases (der Kandidat ist ggf.
#   noch 'neu'). Ob ein subject_id ueberhaupt ein GUELTIGER Fremdforum-Kandidat
#   ist (forensic_<uid>.db vorhanden, evidence fehlt), weiss nur die
#   Dateisystem-Sicht (StorageOverview) — nicht diese DB-Verbindung. Der
#   Server-Endpunkt ermittelt die aktuell gueltigen Kandidaten und uebergibt
#   sie als 'allowed_uids'; record_decision weist eine Entscheidung fuer einen
#   Nicht-Kandidaten laut ab (kein Beleg fuer einen nicht existierenden Fall).
#
# UNWIDERRUFLICHKEIT:
#   'uebernommen'/'fremdzustaendig' sind Endzustaende (PromotionStatus). Es gibt
#   bewusst KEINE reopen()- (ausser dem erlaubten zurueckgestellt->gesichtet)
#   und KEINE delete()-Methode.
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional, Sequence, Set

from management.audit.event_types import EventType
from management.gateway.coordinator_writer import CoordinatorWriter
from management.ops.promotion_status import (
    INITIAL,
    PromotionStatus,
    PromotionStatusError,
)

logger = logging.getLogger(__name__)


class PromotionError(Exception):
    """Fachlicher Fehler (unbekannter/ungueltiger Kandidat, ungueltige Eingabe)."""


class PromotionRepo:
    """Auditierte Lese-/Schreibmethoden auf 'forum_promotion'."""

    def __init__(self, con: sqlite3.Connection,
                 writer: Optional[CoordinatorWriter] = None) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        # writer=None ist zulaessig fuer REIN LESENDE Nutzung (mode=ro). Jeder
        # Schreibweg prueft das ausdruecklich und scheitert laut, statt still
        # zu wirken.
        self._writer = writer

    # ------------------------------------------------------------------ Hilfen
    def _require_writer(self) -> CoordinatorWriter:
        if self._writer is None:
            raise PromotionError(
                "Schreibzugriff ohne CoordinatorWriter — kein unauditierter "
                "Schreibpfad zulaessig.")
        return self._writer

    @staticmethod
    def _tlen(text: Optional[str]) -> int:
        return len(text or "")

    def _row(self, con: sqlite3.Connection,
             subject_id: int) -> Optional[sqlite3.Row]:
        return con.execute(
            "SELECT * FROM forum_promotion WHERE subject_id = ?", (subject_id,)
        ).fetchone()

    # ------------------------------------------------------------------- Lesen
    def get(self, subject_id: int) -> Optional[Dict[str, Any]]:
        """Die Entscheidungszeile eines Kandidaten (oder None = implizit 'offen')."""
        row = self._row(self._con, int(subject_id))
        return dict(row) if row is not None else None

    def states_for(self,
                   subject_ids: Sequence[int]) -> Dict[int, Dict[str, Any]]:
        """
        Batch-Lesung: {subject_id: zeile} fuer die uebergebenen Kandidaten. Fehlt
        ein subject_id im Ergebnis, hat er (noch) KEINE Zeile -> implizit 'offen'.
        Leere Eingabe -> leeres Dict (kein Full-Table-Scan).
        """
        uids = [int(u) for u in subject_ids]
        if not uids:
            return {}
        marks = ",".join("?" for _ in uids)
        rows = self._con.execute(
            "SELECT * FROM forum_promotion WHERE subject_id IN (%s)" % marks,
            uids,
        ).fetchall()
        return {int(r["subject_id"]): dict(r) for r in rows}

    def list_all(self) -> List[Dict[str, Any]]:
        """
        ALLE Entscheidungszeilen (auch solche, deren Kandidat inzwischen
        Arbeitsstand hat und damit kein Fremdforum-Kandidat mehr ist — die
        Entscheidung bleibt als Beleg sichtbar). Sortiert: Handlungsbedarf
        zuerst (Rang der Zustandsmaschine), dann subject_id.
        """
        rows = self._con.execute(
            "SELECT * FROM forum_promotion").fetchall()
        out = [dict(r) for r in rows]
        out.sort(key=lambda d: (PromotionStatus.rank(d["status"]),
                                int(d["subject_id"])))
        return out

    def annotate(self, subject_ids: Sequence[int]) -> List[Dict[str, Any]]:
        """
        Liste je Kandidat mit seinem (impliziten) Zustand + Klartext-Label,
        fuer die data/-Uebersicht (Build 461). Kandidaten OHNE Zeile erscheinen
        als 'offen' — sie werden NICHT verschluckt (Grundregel 1).
        """
        states = self.states_for(subject_ids)
        out: List[Dict[str, Any]] = []
        for uid in (int(u) for u in subject_ids):
            row = states.get(uid)
            status = row["status"] if row is not None else INITIAL
            out.append({
                "subject_id": uid,
                "status": status,
                "status_label": PromotionStatus.label(status),
                "grund": (row["grund"] if row is not None else None),
                "herkunft": (row["herkunft"] if row is not None else None),
                "decided_at": (row["decided_at"] if row is not None else None),
                "decided_by": (row["decided_by"] if row is not None else None),
                "is_final": PromotionStatus.is_final(status),
            })
        out.sort(key=lambda d: (PromotionStatus.rank(d["status"]),
                                d["subject_id"]))
        return out

    # --------------------------------------------------------------- Schreiben
    def record_decision(
        self, *, subject_id: int, target_status: str, grund: str = "",
        herkunft: Optional[str] = None, actor_id: Optional[int] = None,
        allowed_uids: Optional[Set[int]] = None, meta: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Erfasst eine Promotions-Entscheidung fuer einen Kandidaten (anlegen ODER
        weiterfuehren). Prueft Uebergang + Grund-Pflicht, schreibt auditiert.

        allowed_uids: Menge der AKTUELL gueltigen Fremdforum-Kandidaten (vom
          Server aus StorageOverview). Ist sie gesetzt und subject_id NICHT
          enthalten, wird die Entscheidung laut abgewiesen (kein Beleg fuer
          einen nicht existierenden Kandidaten). None = keine Kandidatenpruefung
          (z. B. reine Repo-Tests).

        -> {'subject_id', 'von', 'auf', 'audit_seq', 'created'}.
        """
        writer = self._require_writer()
        uid = int(subject_id)

        if allowed_uids is not None and uid not in allowed_uids:
            raise PromotionError(
                "subject_id=%s ist kein aktueller Fremdforum-Kandidat "
                "(forensic_<uid>.db fehlt oder evidence_<uid>.db existiert "
                "bereits)." % uid)

        # Grund-Pflicht VOR der Transaktion pruefen (fail-fast, klare Meldung).
        try:
            PromotionStatus.check_reason(target_status, grund)
        except PromotionStatusError as exc:
            raise PromotionError(str(exc)) from exc

        now = int(time.time())
        state: Dict[str, Any] = {}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._row(con, uid)
            current = row["status"] if row is not None else INITIAL
            try:
                PromotionStatus.check_transition(current, target_status)
            except PromotionStatusError as exc:
                raise PromotionError(str(exc)) from exc

            state["von"] = current
            if row is None:
                # Erste Entscheidung: Zeile materialisieren. audit_seq/
                # created_audit_seq sind NOT NULL -> Platzhalter 0, im
                # after_audit-Hook derselben Transaktion ueberschrieben (es kann
                # keine Zeile mit audit_seq=0 committen).
                con.execute(
                    "INSERT INTO forum_promotion "
                    "(subject_id, status, grund, herkunft, created_by, "
                    " created_at, decided_by, decided_at, audit_seq, "
                    " created_audit_seq) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0)",
                    (uid, target_status, (grund or None), herkunft,
                     actor_id, now, actor_id, now),
                )
                state["created"] = True
            else:
                # Weiterfuehren: herkunft nur ueberschreiben, wenn ausdruecklich
                # ein neuer Wert kommt (kein stiller Textverlust).
                neu_herkunft = (herkunft if herkunft is not None
                                else row["herkunft"])
                con.execute(
                    "UPDATE forum_promotion SET status = ?, grund = ?, "
                    "herkunft = ?, decided_by = ?, decided_at = ? "
                    "WHERE subject_id = ?",
                    (target_status, (grund or None), neu_herkunft,
                     actor_id, now, uid),
                )
                state["created"] = False

            # Audit-Payload: FAKTEN, keine Freitexte (Sensibilitaetsregel).
            return {
                "subject_id": uid, "von": current, "auf": target_status,
                "grund_len": self._tlen(grund),
                "herkunft_len": self._tlen(herkunft),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            if state.get("created"):
                con.execute(
                    "UPDATE forum_promotion SET audit_seq = ?, "
                    "created_audit_seq = ? WHERE subject_id = ?",
                    (seq, seq, uid),
                )
            else:
                con.execute(
                    "UPDATE forum_promotion SET audit_seq = ? WHERE subject_id = ?",
                    (seq, uid),
                )

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.PROMOTION_DECIDED,
            actor_id=actor_id, target_type="forum_promotion",
            target_id=str(uid), meta=meta, after_audit=_after,
        )
        logger.info("Promotion Kandidat %s: %s -> %s (Beleg seq=%d).",
                    uid, state.get("von"), target_status, seq)
        return {"subject_id": uid, "von": state.get("von"),
                "auf": target_status, "audit_seq": seq,
                "created": state.get("created", False)}

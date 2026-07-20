# =============================================================================
# management/external/case_release_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Externe Fallfreigabe (AP-2G)
# =============================================================================
# Zweck (Idee 26):
#   Zugriffsschicht auf 'case_release' (M016). SCHREIBEN ausschliesslich ueber
#   das CoordinatorWriter-Gateway: fachlicher Write + audit_log-Beleg committen
#   in EINER Transaktion oder gar nicht. Es gibt damit keine externe Freigabe
#   und keinen Widerruf ohne lueckenlosen Beleg (Grundregel 1).
#
#   DREI-FACHE PRUEFUNG BEIM FREIGEBEN (Idee 26):
#     1) AD-ACL  — der Empfaenger MUSS ueber die AD-Schicht (F4, ad_directory.py)
#        als Mitglied der berechtigten Gruppe aufloesbar sein; sonst
#        ADDirectoryError (Default-Deny). Der Anzeigename kommt aus F4.
#     2) UNBEDENKLICHKEIT — die Pflicht-Grundlage (Fallregel 3) darf NICHT leer
#        sein; sonst CaseReleaseError. Gleiche Linie wie export/staging.py.
#     3) FALL EXISTIERT — user_id muss ein aufgenommener Fall sein (FK + Pruefung).
#
# SENSIBILITAETSREGEL (uebernommen von CasesRepo.set_note / ExternalMattersRepo):
#   Freitexte (unbedenklichkeit_grundlage, grund_widerruf) gehen NICHT in den
#   audit_log-Payload — nur FAKTEN (user_id, recipient_kennung, umfang, von->auf)
#   und die Textlaenge. Die Empfaenger-Kennung IST ein Fakt (WER externen Zugriff
#   erhielt) und gehoert ausdruecklich in den Beleg.
#
# UNWIDERRUFLICHKEIT:
#   'widerrufen' ist ein Endzustand (ReleaseStatus). Es gibt bewusst KEINE
#   reopen()- und KEINE delete()-Methode; eine erneute Freigabe ist ein NEUER
#   Record.
#
# Version: v0.7.462 · Build: 462 · 2026-07-20
# =============================================================================

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional, Sequence

from management.audit.event_types import EventType
from management.external.ad_directory import ADDirectory, ADDirectoryError
from management.external.release_status import (
    ReleaseStatus,
    ReleaseStatusError,
    umfang_is_valid,
    umfang_label,
    UMFANG_ORDER,
)
from management.external.release_status import STATUS_LABEL
from management.gateway.coordinator_writer import CoordinatorWriter

logger = logging.getLogger(__name__)


class CaseReleaseError(Exception):
    """Fachlicher Fehler (unbekannter Fall/Freigabe, ungueltige Eingabe)."""


class CaseReleaseRepo:
    """Auditierte Lese-/Schreibmethoden auf 'case_release'."""

    def __init__(self, con: sqlite3.Connection,
                 writer: Optional[CoordinatorWriter] = None,
                 ad: Optional[ADDirectory] = None) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        # writer=None -> rein lesende Nutzung (mode=ro). ad=None -> keine
        # Freigabe moeglich (die AD-Pruefung ist Pflicht). Jeder Weg prueft das
        # ausdruecklich und scheitert laut, statt still zu wirken.
        self._writer = writer
        self._ad = ad

    # ------------------------------------------------------------------ Hilfen
    def _require_writer(self) -> CoordinatorWriter:
        if self._writer is None:
            raise CaseReleaseError(
                "Schreibzugriff ohne CoordinatorWriter — kein unauditierter "
                "Schreibpfad zulaessig.")
        return self._writer

    def _require_ad(self) -> ADDirectory:
        if self._ad is None:
            raise CaseReleaseError(
                "Freigabe ohne AD-Schicht nicht moeglich (Empfaenger-Pruefung "
                "ist Pflicht).")
        return self._ad

    @staticmethod
    def _tlen(text: Optional[str]) -> int:
        return len(text or "")

    def _case_exists(self, con: sqlite3.Connection, user_id: int) -> bool:
        return con.execute(
            "SELECT 1 FROM cases WHERE user_id = ?", (user_id,)
        ).fetchone() is not None

    def _row(self, con: sqlite3.Connection, release_id: int) -> sqlite3.Row:
        row = con.execute(
            "SELECT * FROM case_release WHERE id = ?", (release_id,)
        ).fetchone()
        if row is None:
            raise CaseReleaseError("Keine Freigabe mit id=%s." % release_id)
        return row

    # ------------------------------------------------------------------- Lesen
    def get(self, release_id: int) -> Dict[str, Any]:
        return dict(self._row(self._con, release_id))

    def list_releases(
        self, *,
        user_ids: Optional[Sequence[int]] = None,
        statuses: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Freigaben lesen, angereichert um den Fall-Benutzernamen und Klartext-
        Labels (Umfang/Status).

        user_ids=None -> alle Faelle. user_ids=[] -> KEINE (korrekte Antwort fuer
        einen Scope ohne Zuweisung; NICHT dasselbe wie 'alle').
        """
        sql = ("SELECT r.*, c.username AS fall_username "
               "FROM case_release r JOIN cases c ON c.user_id = r.user_id")
        clauses: List[str] = []
        params: List[Any] = []

        if user_ids is not None:
            if not user_ids:
                return []
            marks = ",".join("?" for _ in user_ids)
            clauses.append("r.user_id IN (%s)" % marks)
            params.extend(int(u) for u in user_ids)

        if statuses:
            for s in statuses:
                if not ReleaseStatus.is_valid(s):
                    raise CaseReleaseError("Unbekannter Zustand '%s'." % s)
            marks = ",".join("?" for _ in statuses)
            clauses.append("r.status IN (%s)" % marks)
            params.extend(statuses)

        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY r.status ASC, r.user_id ASC, r.id ASC"

        out: List[Dict[str, Any]] = []
        for r in self._con.execute(sql, params).fetchall():
            d = dict(r)
            d["umfang_label"] = umfang_label(d["umfang"])
            d["status_label"] = STATUS_LABEL.get(d["status"], d["status"])
            out.append(d)
        return out

    # --------------------------------------------------------------- Schreiben
    def grant(
        self, *, user_id: int, recipient_kennung: str, umfang: str,
        unbedenklichkeit_grundlage: str, actor_id: Optional[int] = None,
        meta: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Erteilt eine externe Fallfreigabe. -> {'release_id', 'audit_seq',
        'recipient_kennung', 'recipient_display'}.
        """
        writer = self._require_writer()
        ad = self._require_ad()

        if not umfang_is_valid(umfang):
            raise CaseReleaseError(
                "Unbekannter Umfang '%s' (gueltig: %s)."
                % (umfang, ", ".join(UMFANG_ORDER)))
        if not (unbedenklichkeit_grundlage or "").strip():
            raise CaseReleaseError(
                "Unbedenklichkeits-Grundlage ist Pflicht: eine Freigabe ohne "
                "belegte Pruefung auf Unverfaenglichkeit ist nicht zulaessig "
                "(Fallregel 3).")

        # AD-ACL: Empfaenger MUSS aufloesbar sein (Default-Deny). Dies vor der
        # Transaktion — ein unbekannter Empfaenger ist ein Aufruf-, kein
        # Schreibfehler.
        try:
            resolved = ad.resolve_recipient(recipient_kennung)
        except ADDirectoryError as exc:
            raise CaseReleaseError(str(exc)) from exc
        kennung = resolved["kennung"]
        display = resolved["display_name"]

        now = int(time.time())
        state: Dict[str, Any] = {}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            if not self._case_exists(con, int(user_id)):
                raise CaseReleaseError("Kein Fall user_id=%s." % user_id)
            cur = con.execute(
                "INSERT INTO case_release "
                "(user_id, recipient_kennung, recipient_display, umfang, "
                " status, unbedenklichkeit_grundlage, created_by, created_at, "
                " audit_seq, created_audit_seq) "
                "VALUES (?, ?, ?, ?, 'freigegeben', ?, ?, ?, 0, 0)",
                (int(user_id), kennung, display, umfang,
                 unbedenklichkeit_grundlage, actor_id, now),
            )
            state["release_id"] = int(cur.lastrowid)
            # Audit-Payload: FAKTEN, keine Freitexte (Sensibilitaetsregel).
            return {
                "release_id": state["release_id"], "user_id": int(user_id),
                "recipient_kennung": kennung, "umfang": umfang,
                "status": "freigegeben",
                "grundlage_len": self._tlen(unbedenklichkeit_grundlage),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute(
                "UPDATE case_release SET audit_seq = ?, created_audit_seq = ? "
                "WHERE id = ?", (seq, seq, state["release_id"]),
            )

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.CASE_RELEASE_GRANTED,
            actor_id=actor_id, target_type="case_release",
            target_id=None, meta=meta, after_audit=_after,
        )
        logger.info("Fall %s an %s (%s) freigegeben — Umfang %s (Beleg #%d).",
                    user_id, kennung, display, umfang, seq)
        return {"release_id": state["release_id"], "audit_seq": seq,
                "recipient_kennung": kennung, "recipient_display": display}

    def revoke(
        self, release_id: int, *, grund: str,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> int:
        """
        Widerruft eine aktive Freigabe: 'freigegeben' -> 'widerrufen'. GRUND ist
        Pflicht — warum ein gewaehrter externer Zugriff zurueckgezogen wird, muss
        belegt sein. UNWIDERRUFLICH.
        """
        writer = self._require_writer()
        if not (grund or "").strip():
            raise CaseReleaseError(
                "Grund ist Pflicht: ein Widerruf darf nicht ohne "
                "nachvollziehbaren Grund erfolgen.")
        now = int(time.time())
        ctx: Dict[str, Any] = {}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._row(con, release_id)
            try:
                ReleaseStatus.check_transition(row["status"], "widerrufen")
            except ReleaseStatusError as exc:
                raise CaseReleaseError(str(exc)) from exc
            ctx["user_id"] = row["user_id"]
            ctx["kennung"] = row["recipient_kennung"]
            ctx["von"] = row["status"]
            con.execute(
                "UPDATE case_release SET status = 'widerrufen', "
                "grund_widerruf = ?, revoked_by = ?, revoked_at = ? "
                "WHERE id = ?",
                (grund, actor_id, now, release_id),
            )
            return {
                "release_id": release_id, "user_id": row["user_id"],
                "recipient_kennung": row["recipient_kennung"],
                "umfang": row["umfang"], "von": row["status"],
                "auf": "widerrufen", "grund_len": self._tlen(grund),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute(
                "UPDATE case_release SET audit_seq = ?, revoke_audit_seq = ? "
                "WHERE id = ?", (seq, seq, release_id),
            )

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.CASE_RELEASE_REVOKED,
            actor_id=actor_id, target_type="case_release",
            target_id=str(release_id), meta=meta, after_audit=_after,
        )
        logger.info("Freigabe %s (Fall %s, %s) widerrufen (Beleg #%d).",
                    release_id, ctx.get("user_id"), ctx.get("kennung"), seq)
        return seq

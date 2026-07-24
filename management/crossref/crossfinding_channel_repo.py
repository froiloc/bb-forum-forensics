# =============================================================================
# management/crossref/crossfinding_channel_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Querfunde (AP-2A)
# =============================================================================
# Zweck (Idee 7, Build 507):
#   Zugriffsschicht auf 'crossfinding_feedback' (M024) — den QUERFUND-
#   RUECKKANAL. Sie beantwortet die Frage, die 'integrated_at' NICHT beantwortet:
#   hat ein MENSCH den Fund gesehen, und was ist daraus geworden?
#
#   SCHREIBEN ausschliesslich ueber das CoordinatorWriter-Gateway (Write +
#   audit_log-Beleg in EINER Transaktion oder gar nicht). Die Zustandslogik
#   liegt vollstaendig in crossfinding_channel_status.py (reine Logik, ohne DB) —
#   dieses Repo verbindet sie mit dem Substrat, dupliziert sie aber nicht.
#
# LESEN: list_with_status() fuehrt die Querfunde (pending_cross_annotations,
#   seit M023 in der Kette und mit generierter Spalte 'subject_id') per LEFT
#   JOIN mit ihrem Rueckkanal-Zustand zusammen. Faehrt ein Fund KEINE
#   Feedback-Zeile, ist sein Zustand 'offen' — der Pseudo-Zustand, den die
#   Abwesenheit ausdrueckt. GRUNDREGEL 1: solche Funde werden nicht
#   verschluckt, sondern stehen als handlungsbeduerftig GANZ OBEN.
#
# SUBSTRAT-WAECHTER: fehlt 'pending_cross_annotations', ist das ein
#   Betriebsfehler und KEIN Leerbefund -> CrossrefError (Linie Build 474).
#
# EXISTENZPRUEFUNG STATT FK (Bauplan A2 Par. 2.2 Nr. 2): decide() prueft
#   INNERHALB der Transaktion, ob der Querfund ueberhaupt existiert. Ein FK
#   haette die Migration hart an die laufzeitverwaltete Zieltabelle gekoppelt;
#   die Pruefung hier ist genauso streng, aber ohne Kopplungsrisiko fuer die
#   produktive Pipeline.
#
# SENSIBILITAET: 'reason' (Grund bei 'nicht_relevant', Basis bei 'verwertet')
#   ist Freitext und geht NIE als Klartext ins Audit-Payload — dort stehen
#   FAKTEN (finding_id, subject_id, von, nach) + TEXTLAENGE. Regel wie M018.
#
# Version: v0.8.507 · Build: 507 · 2026-07-24
# =============================================================================

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.crossref.crossfinding_channel_status import (
    CrossfindingChannelError,
    CrossfindingChannelStatus,
    INITIAL,
    STATUS_ORDER,
)
from management.crossref.identified_subject_repo import CrossrefError
from management.gateway.coordinator_writer import CoordinatorWriter

logger = logging.getLogger(__name__)


class CrossfindingChannelRepo:
    """Auditierte Lese-/Schreibmethoden auf 'crossfinding_feedback' (M024)."""

    def __init__(self, con: sqlite3.Connection,
                 writer: Optional[CoordinatorWriter] = None) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._writer = writer

    # ------------------------------------------------------------------ Hilfen
    def _require_writer(self) -> CoordinatorWriter:
        if self._writer is None:
            raise CrossrefError(
                "Schreibzugriff ohne CoordinatorWriter — kein unauditierter "
                "Schreibpfad zulaessig.")
        return self._writer

    @staticmethod
    def _table_present(con: sqlite3.Connection, name: str) -> bool:
        return con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,)).fetchone() is not None

    def _require_substrate(self) -> None:
        if not self._table_present(self._con, "pending_cross_annotations"):
            raise CrossrefError(
                "pending_cross_annotations fehlt — coordinator.db nicht "
                "vollstaendig initialisiert. Kein stiller Leerbefund.")

    def _subject_column(self, con: Optional[sqlite3.Connection] = None) -> str:
        """
        Spaltenname des Ziel-Subjekts: 'subject_id' (kanonisch ab M023) oder
        'target_uid' (Alt-Stand). PRAGMA table_xinfo — table_info verschweigt
        generierte Spalten.
        """
        c = con or self._con
        try:
            rows = c.execute(
                "PRAGMA table_xinfo(pending_cross_annotations)").fetchall()
        except sqlite3.DatabaseError:
            rows = []
        names = {str(r[1]) for r in rows}
        return "subject_id" if "subject_id" in names else "target_uid"

    @staticmethod
    def _tlen(text: Optional[str]) -> int:
        return len(text or "")

    # ------------------------------------------------------------------- Lesen
    def status_of(self, finding_id: int) -> str:
        """Ist-Zustand eines Querfundes; ohne Zeile die Eingangslage 'offen'."""
        row = self._con.execute(
            "SELECT status_code FROM crossfinding_feedback WHERE finding_id = ?",
            (int(finding_id),)).fetchone()
        return row["status_code"] if row is not None else INITIAL

    def list_with_status(self, only_open: bool = False,
                         only_unacknowledged: bool = False
                         ) -> List[Dict[str, Any]]:
        """
        Querfunde INKLUSIVE Rueckkanal-Zustand.

        Zwei UNABHAENGIGE Filter — sie meinen bewusst Verschiedenes und werden
        in der Oberflaeche auch getrennt beschriftet:
          only_open            -> TRANSPORTstand (integrated_at IS NULL)
          only_unacknowledged  -> RUECKKANALstand (noch nicht quittiert oder
                                  bewertet, also 'offen'/'zugestellt')
        Sortierung: Handlungsbeduerftiges zuerst (Rueckkanal-Rang), dann
        neueste zuerst.
        """
        self._require_substrate()
        col = self._subject_column()
        # 'col' stammt ausschliesslich aus _subject_column() (zwei feste
        # Literale) — keine Fremdeingabe, keine Injektionsflaeche.
        sql = (
            "SELECT pca.id, pca.source_iid, pca.%s AS target_subject, "
            "       pca.db_path, pca.annotation_local_id, pca.created_at, "
            "       pca.integrated_at, "
            "       p.display_name AS source_name, "
            "       c.subject_id AS case_subject, "
            "       f.status_code, f.reason, f.decided_by, f.updated_at "
            "         AS decided_at, f.audit_seq AS decided_audit_seq, "
            "       dp.display_name AS decided_name "
            "FROM pending_cross_annotations pca "
            "LEFT JOIN person p  ON p.id = pca.source_iid "
            "LEFT JOIN cases  c  ON c.subject_id = pca.%s "
            "LEFT JOIN crossfinding_feedback f ON f.finding_id = pca.id "
            "LEFT JOIN person dp ON dp.id = f.decided_by "
            % (col, col)
        )
        where: List[str] = []
        if only_open:
            where.append("pca.integrated_at IS NULL")
        if only_unacknowledged:
            # NULL (keine Zeile) = 'offen' -> gehoert ausdruecklich dazu.
            where.append("(f.status_code IS NULL "
                         "OR f.status_code = 'zugestellt')")
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY pca.created_at DESC, pca.id DESC"

        rows = [self._as_dict(r) for r in self._con.execute(sql)]
        # Rang-Sortierung in Python: die Reihenfolge steht in der
        # Zustandsmaschine (STATUS_ORDER) und soll NICHT als CASE-Ausdruck im
        # SQL dupliziert werden — sonst gaebe es zwei Wahrheiten.
        #
        # DREISTUFIGER SCHLUESSEL, bewusst in dieser Reihenfolge:
        #   1. RUECKKANAL-Rang. Das ist die Dimension, die einen MENSCHEN
        #      braucht: ein unquittierter Fund ist Arbeit, ein verwerteter
        #      nicht. Der Transportstand loest sich dagegen von selbst (die
        #      Pipeline arbeitet ihn ab).
        #   2. TRANSPORTstand (nicht integriert vor integriert) — exakt die
        #      Reihenfolge aus Build 474. Dadurch aendert sich fuer jeden
        #      Bestand OHNE Rueckkanal-Eintraege (alle Raenge gleich) die
        #      Anzeige NICHT: die Sicht aus Build 478 bleibt Zeile fuer Zeile
        #      wie gehabt. Der neue Schluessel greift erst, sobald der
        #      Rueckkanal tatsaechlich benutzt wird.
        #   3. neueste zuerst, dann id — wie bisher.
        rows.sort(key=lambda r: (
            CrossfindingChannelStatus.rank(r["feedback_status"]),
            1 if r["integrated_at"] is not None else 0,
            -int(r["created_at"]),
            -int(r["id"]),
        ))
        return rows

    def counts(self) -> Dict[str, int]:
        """Anzahl je Rueckkanal-Zustand, inkl. des Pseudo-Zustands 'offen'."""
        self._require_substrate()
        out = {s: 0 for s in STATUS_ORDER}
        rows = self._con.execute(
            "SELECT COALESCE(f.status_code, 'offen') AS st, COUNT(*) AS n "
            "FROM pending_cross_annotations pca "
            "LEFT JOIN crossfinding_feedback f ON f.finding_id = pca.id "
            "GROUP BY st").fetchall()
        for r in rows:
            out[str(r["st"])] = out.get(str(r["st"]), 0) + int(r["n"])
        out["gesamt"] = sum(out[s] for s in STATUS_ORDER)
        return out

    def allowed_next_for(self, finding_id: int) -> List[Dict[str, Any]]:
        """
        Die laut Zustandsmaschine zulaessigen Folgezustaende eines Fundes,
        mitsamt Beschriftung und Pflichttext-Bedarf. Der SERVER liefert das
        mit, damit die Oberflaeche keine Uebergaenge erfinden kann.
        """
        cur = self.status_of(finding_id)
        return [
            {
                "code": s,
                "label": CrossfindingChannelStatus.label(s),
                "reason_required": CrossfindingChannelStatus.requires_reason(s),
                "reason_meaning": CrossfindingChannelStatus.reason_meaning(s),
            }
            for s in CrossfindingChannelStatus.allowed_next(cur)
        ]

    # --------------------------------------------------------------- Schreiben
    def decide(self, *, finding_id: int, target_status: str,
               reason: str = "", actor_id: Optional[int] = None,
               meta: Optional[Any] = None) -> Dict[str, Any]:
        """
        Fuehrt den Querfund in den Zielzustand. Prueft IN der Transaktion:
        existiert der Fund? ist der Uebergang erlaubt? ist der Pflichttext da?
        Auditiert. -> {'finding_id','status_code','audit_seq','created'}.
        """
        writer = self._require_writer()
        fid = int(finding_id)
        reason_txt = (reason or "").strip()

        # Frueh und OHNE DB: unbekannter Zielzustand / fehlender Pflichttext.
        # (Der Uebergang selbst braucht den Ist-Zustand und wird unten geprueft.)
        CrossfindingChannelStatus.check_reason(target_status, reason_txt)

        now = int(time.time())
        state: Dict[str, Any] = {"created": False, "row_id": None,
                                 "from": INITIAL, "subject_id": None}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            if not self._table_present(con, "pending_cross_annotations"):
                raise CrossrefError(
                    "pending_cross_annotations fehlt — der Rueckkanal hat kein "
                    "Substrat. Kein stiller Leerbefund.")
            col = self._subject_column(con)
            found = con.execute(
                "SELECT id, %s AS target_subject FROM "
                "pending_cross_annotations WHERE id = ?" % col,
                (fid,)).fetchone()
            if found is None:
                # Existenzpruefung statt FK — sichtbar statt still.
                raise CrossrefError(
                    "Unbekannter Querfund #%d — es gibt keine solche "
                    "Transportnotiz." % fid)
            subject_id = int(found["target_subject"])
            state["subject_id"] = subject_id

            row = con.execute(
                "SELECT * FROM crossfinding_feedback WHERE finding_id = ?",
                (fid,)).fetchone()
            current = row["status_code"] if row is not None else INITIAL
            state["from"] = current

            # Der eigentliche Waechter — die Logik liegt in der
            # Zustandsmaschine, nicht hier.
            CrossfindingChannelStatus.check_transition(current, target_status)

            if row is None:
                con.execute(
                    "INSERT INTO crossfinding_feedback "
                    "(finding_id, subject_id, status_code, reason, decided_by, "
                    " created_at, updated_at, audit_seq, created_audit_seq) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0)",
                    (fid, subject_id, target_status, reason_txt, actor_id,
                     now, now))
                state["created"] = True
                state["row_id"] = int(con.execute(
                    "SELECT id FROM crossfinding_feedback WHERE finding_id = ?",
                    (fid,)).fetchone()["id"])
            else:
                con.execute(
                    "UPDATE crossfinding_feedback SET status_code = ?, "
                    "reason = ?, decided_by = ?, updated_at = ? WHERE id = ?",
                    (target_status, reason_txt, actor_id, now,
                     int(row["id"])))
                state["row_id"] = int(row["id"])

            # Payload: FAKTEN + Textlaenge, KEIN Freitext.
            return {
                "finding_id": fid,
                "subject_id": subject_id,
                "von": current,
                "nach": target_status,
                "created": state["created"],
                "reason_len": self._tlen(reason_txt),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            if state["created"]:
                con.execute(
                    "UPDATE crossfinding_feedback SET audit_seq = ?, "
                    "created_audit_seq = ? WHERE id = ?",
                    (seq, seq, state["row_id"]))
            else:
                con.execute(
                    "UPDATE crossfinding_feedback SET audit_seq = ? "
                    "WHERE id = ?", (seq, state["row_id"]))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.CROSSFINDING_FEEDBACK_SET,
            actor_id=actor_id, target_type="crossfinding_feedback",
            target_id=str(fid), meta=meta, after_audit=_after,
        )
        logger.info("Querfund #%d: %s -> %s (Beleg #%d).",
                    fid, state["from"], target_status, seq)
        return {"finding_id": fid, "status_code": target_status,
                "audit_seq": seq, "created": state["created"],
                "subject_id": state["subject_id"]}

    # ------------------------------------------------------------------ intern
    @staticmethod
    def _as_dict(r: sqlite3.Row) -> Dict[str, Any]:
        integ = r["integrated_at"]
        status = r["status_code"] or INITIAL
        return {
            "id": int(r["id"]),
            # Ausgabename immer 'subject_id' (Prepper-Schema) — unabhaengig
            # davon, ob die Quelle die generierte Spalte oder target_uid war.
            "subject_id": int(r["target_subject"]),
            "source_iid": int(r["source_iid"]),
            "source_name": r["source_name"],
            "has_case": r["case_subject"] is not None,
            "annotation_local_id": r["annotation_local_id"],
            "db_path": r["db_path"],
            "created_at": int(r["created_at"]),
            "integrated_at": (int(integ) if integ is not None else None),
            # TRANSPORTstand (Technik) — unveraendert aus Build 474.
            "status": ("integriert" if integ is not None else "offen"),
            # RUECKKANALstand (Mensch) — neu in Build 507.
            "feedback_status": status,
            "feedback_label": CrossfindingChannelStatus.label(status),
            "feedback_final": CrossfindingChannelStatus.is_final(status),
            "feedback_reason": r["reason"],
            "decided_by": (int(r["decided_by"])
                           if r["decided_by"] is not None else None),
            "decided_name": r["decided_name"],
            "decided_at": (int(r["decided_at"])
                           if r["decided_at"] is not None else None),
            "decided_audit_seq": (int(r["decided_audit_seq"])
                                  if r["decided_audit_seq"] is not None
                                  else None),
            "allowed_next": [
                {
                    "code": s,
                    "label": CrossfindingChannelStatus.label(s),
                    "reason_required":
                        CrossfindingChannelStatus.requires_reason(s),
                    "reason_meaning":
                        CrossfindingChannelStatus.reason_meaning(s),
                }
                for s in CrossfindingChannelStatus.allowed_next(status)
            ],
        }

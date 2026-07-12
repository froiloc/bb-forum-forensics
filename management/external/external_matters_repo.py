# =============================================================================
# management/external/external_matters_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Zugriffsschicht auf 'external_matters' (M010). SCHREIBEN ausschliesslich
#   ueber das CoordinatorWriter-Gateway: fachlicher Write + audit_log-Beleg +
#   Zeitstrahl-Spiegel (case_events) committen in EINER Transaktion oder gar
#   nicht. Es gibt damit keine Aenderung an einem externen Vorgang ohne
#   lueckenlosen Beleg (Grundregel 1).
#
# SENSIBILITAETSREGEL (uebernommen von CasesRepo.set_note):
#   Freitexte (betreff, ergebnis, grund) gehen NICHT in den audit_log-Payload.
#   Dort stehen nur FAKTEN (matter_id, Fall, Art, Datum, Zustand) und die
#   TEXTLAENGE. Der Text selbst lebt in external_matters bzw. im
#   case_events-Payload — dort, wo er fachlich hingehoert und wo die
#   RBAC-Kapselung greift. Das Audit-Log ist ein Beleg, kein Aktenordner.
#
# UNWIDERRUFLICHKEIT:
#   'erledigt'/'erfolglos' sind Endzustaende (MatterStatus). Es gibt bewusst
#   KEINE reopen()-Methode und KEIN delete(). Ein Irrtum wird durch einen NEUEN
#   Vorgang korrigiert — die Historie eines Ermittlungsvorgangs wird nicht
#   umgeschrieben.
#
# Beleg: mc 2026-07-12.
# Version: v0.7.385 · Build: 385 · 2026-07-12
# =============================================================================

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional, Sequence

from management.audit.event_types import EventType
from management.case_events.case_events_repo import insert_event_row
from management.external import matter_kinds
from management.external.matter_status import (
    DEFAULT_VORWARNFRIST_TAGE,
    MatterStatus,
    MatterStatusError,
)
from management.gateway.coordinator_writer import CoordinatorWriter

logger = logging.getLogger(__name__)

#: Zeitstrahl-Vokabular dieses Moduls (case_events.event_kind).
EVENT_KIND = "external_matter"


class ExternalMattersError(Exception):
    """Fachlicher Fehler (unbekannter Vorgang/Fall, ungueltige Eingabe)."""


class ExternalMattersRepo:
    """Auditierte Lese-/Schreibmethoden auf 'external_matters'."""

    def __init__(self, con: sqlite3.Connection,
                 writer: Optional[CoordinatorWriter] = None) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        # writer=None ist zulaessig fuer REIN LESENDE Nutzung (z. B. die
        # Kalender-Leseschicht auf einer mode=ro-Verbindung). Jeder Schreibweg
        # prueft das ausdruecklich und scheitert laut, statt still zu wirken.
        self._writer = writer

    # ------------------------------------------------------------------ Hilfen
    def _require_writer(self) -> CoordinatorWriter:
        if self._writer is None:
            raise ExternalMattersError(
                "Schreibzugriff ohne CoordinatorWriter — kein unauditierter "
                "Schreibpfad zulaessig.")
        return self._writer

    def _case_exists(self, con: sqlite3.Connection, user_id: int) -> bool:
        return con.execute(
            "SELECT 1 FROM cases WHERE user_id = ?", (user_id,)
        ).fetchone() is not None

    def _row(self, con: sqlite3.Connection, matter_id: int) -> sqlite3.Row:
        row = con.execute(
            "SELECT * FROM external_matters WHERE id = ?", (matter_id,)
        ).fetchone()
        if row is None:
            raise ExternalMattersError(
                "Kein externer Vorgang mit id=%s." % matter_id)
        return row

    @staticmethod
    def _check_date(iso: str, feld: str) -> str:
        """ISO-Datum validieren. Ein kaputtes Datum wird NIE stillschweigend
        korrigiert — es macht den Vorgang unauffindbar (Grundregel 1)."""
        try:
            MatterStatus.parse_date(iso)
        except MatterStatusError as exc:
            raise ExternalMattersError("%s: %s" % (feld, exc)) from exc
        return iso

    @staticmethod
    def _tlen(text: Optional[str]) -> int:
        return len(text or "")

    # ------------------------------------------------------------------- Lesen
    def get(self, matter_id: int) -> Dict[str, Any]:
        """Einen Vorgang lesen (ohne Ampel — die braucht einen Stichtag)."""
        return dict(self._row(self._con, matter_id))

    def list_matters(
        self, *,
        user_ids: Optional[Sequence[int]] = None,
        statuses: Optional[Sequence[str]] = None,
        bis: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Vorgaenge lesen, angereichert um Fall-Benutzernamen und cases.status
        (Letzterer wird fuer die 'verwaist'-Erkennung gebraucht).

        user_ids=None  -> alle Faelle (Scope 'alle').
        user_ids=[]    -> KEINE Faelle. Das ist die korrekte Antwort fuer einen
                          Ermittler ohne Zuweisung — und ausdruecklich NICHT
                          dasselbe wie 'alle' (ein Scope-Fehler, der hier still
                          alles freigeben wuerde, waere ein Kapselungsbruch).
        bis            -> nur Vorgaenge mit wiedervorlage_am <= bis.
        """
        sql = (
            "SELECT m.*, c.username AS fall_username, c.status AS case_status "
            "FROM external_matters m "
            "JOIN cases c ON c.user_id = m.user_id"
        )
        clauses: List[str] = []
        params: List[Any] = []

        if user_ids is not None:
            if not user_ids:
                return []
            marks = ",".join("?" for _ in user_ids)
            clauses.append("m.user_id IN (%s)" % marks)
            params.extend(int(u) for u in user_ids)

        if statuses:
            for s in statuses:
                if not MatterStatus.is_valid(s):
                    raise ExternalMattersError("Unbekannter Zustand '%s'." % s)
            marks = ",".join("?" for _ in statuses)
            clauses.append("m.status IN (%s)" % marks)
            params.extend(statuses)

        if bis:
            clauses.append("m.wiedervorlage_am <= ?")
            params.append(self._check_date(bis, "bis"))

        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY m.wiedervorlage_am ASC, m.id ASC"

        return [dict(r) for r in self._con.execute(sql, params).fetchall()]

    def with_ampel(self, rows: Sequence[Dict[str, Any]],
                   stichtag: str) -> List[Dict[str, Any]]:
        """
        Reichert Zeilen um Ampel + Begruendung + Klartext-Beschriftungen an.
        Die Ampel wird NIE gespeichert — sie ist eine Funktion des Stichtags und
        muesste sonst jede Nacht nachgezogen werden (und koennte veralten).
        """
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            ampel, grund = MatterStatus.ampel(
                status=d["status"],
                wiedervorlage_am=d["wiedervorlage_am"],
                stichtag=stichtag,
                vorwarnfrist_tage=d.get("vorwarnfrist_tage",
                                        DEFAULT_VORWARNFRIST_TAGE),
                case_status=d.get("case_status"),
            )
            d["ampel"] = ampel
            d["ampel_grund"] = grund
            d["kind_label"] = matter_kinds.label(d["kind"])
            d["status_label"] = MatterStatus.label(d["status"])
            out.append(d)
        out.sort(key=lambda x: (MatterStatus.rank(x["ampel"]),
                               x["wiedervorlage_am"], x["id"]))
        return out

    # --------------------------------------------------------------- Schreiben
    def create(
        self, *, user_id: int, kind: str, betreff: str,
        angefordert_am: str, wiedervorlage_am: str,
        adressat: str = "", aktenzeichen: Optional[str] = None,
        vorwarnfrist_tage: int = DEFAULT_VORWARNFRIST_TAGE,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Legt einen externen Vorgang an. -> {'matter_id', 'audit_seq'}."""
        writer = self._require_writer()

        if not matter_kinds.is_valid(kind):
            raise ExternalMattersError(
                "Unbekannte Vorgangsart '%s' (gueltig: %s)."
                % (kind, ", ".join(matter_kinds.KIND_ORDER)))
        if not (betreff or "").strip():
            raise ExternalMattersError("Betreff ist Pflicht.")
        self._check_date(angefordert_am, "angefordert_am")
        self._check_date(wiedervorlage_am, "wiedervorlage_am")
        try:
            frist = int(vorwarnfrist_tage)
        except (TypeError, ValueError) as exc:
            raise ExternalMattersError(
                "vorwarnfrist_tage muss eine ganze Zahl sein.") from exc
        if frist < 0:
            raise ExternalMattersError(
                "vorwarnfrist_tage darf nicht negativ sein.")

        now = int(time.time())
        state: Dict[str, Any] = {}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            if not self._case_exists(con, user_id):
                raise ExternalMattersError("Kein Fall user_id=%s." % user_id)
            # audit_seq/created_audit_seq sind NOT NULL — sie werden erst im
            # after_audit-Hook bekannt. Platzhalter 0 wird DORT ueberschrieben;
            # beides liegt in derselben Transaktion, es kann keine Zeile mit
            # audit_seq=0 committen (gleiche Kopplung wie case_events).
            cur = con.execute(
                "INSERT INTO external_matters "
                "(user_id, kind, betreff, adressat, aktenzeichen, "
                " angefordert_am, wiedervorlage_am, vorwarnfrist_tage, "
                " status, created_by, created_at, audit_seq, created_audit_seq) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'offen', ?, ?, 0, 0)",
                (user_id, kind, betreff, adressat or "", aktenzeichen,
                 angefordert_am, wiedervorlage_am, frist, actor_id, now),
            )
            state["matter_id"] = int(cur.lastrowid)
            # Audit-Payload: FAKTEN, keine Freitexte (Sensibilitaetsregel).
            return {
                "matter_id": state["matter_id"], "user_id": user_id,
                "kind": kind, "wiedervorlage_am": wiedervorlage_am,
                "vorwarnfrist_tage": frist, "status": "offen",
                "betreff_len": self._tlen(betreff),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute(
                "UPDATE external_matters SET audit_seq = ?, "
                "created_audit_seq = ? WHERE id = ?",
                (seq, seq, state["matter_id"]),
            )
            insert_event_row(
                con, user_id=user_id, event_kind=EVENT_KIND,
                payload={
                    "action": "created", "matter_id": state["matter_id"],
                    "kind": kind, "betreff": betreff, "adressat": adressat or "",
                    "wiedervorlage_am": wiedervorlage_am, "status": "offen",
                },
                created_by=actor_id, created_at=now, audit_seq=seq,
            )

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.EXTERNAL_MATTER_CREATED,
            actor_id=actor_id, target_type="external_matter",
            target_id=None, meta=meta, after_audit=_after,
        )
        logger.info("Externer Vorgang %s angelegt (Fall %s, %s, WV %s).",
                    state["matter_id"], user_id, kind, wiedervorlage_am)
        return {"matter_id": state["matter_id"], "audit_seq": seq}

    def defer(
        self, matter_id: int, *, wiedervorlage_am: str, grund: str,
        vorwarnfrist_tage: Optional[int] = None,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> int:
        """
        Wiedervorlage verschieben. GRUND ist Pflicht — ein stilles Verschieben
        waere genau die Luecke, die dieses System schliessen soll.
        """
        writer = self._require_writer()
        self._check_date(wiedervorlage_am, "wiedervorlage_am")
        if not (grund or "").strip():
            raise ExternalMattersError(
                "Grund ist Pflicht: eine Wiedervorlage darf nicht ohne "
                "nachvollziehbaren Grund verschoben werden.")
        now = int(time.time())
        ctx: Dict[str, Any] = {}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._row(con, matter_id)
            MatterStatus.check_deferrable(row["status"])
            ctx["user_id"] = row["user_id"]
            ctx["alt"] = row["wiedervorlage_am"]
            frist = (row["vorwarnfrist_tage"] if vorwarnfrist_tage is None
                     else int(vorwarnfrist_tage))
            if frist < 0:
                raise ExternalMattersError(
                    "vorwarnfrist_tage darf nicht negativ sein.")
            ctx["frist"] = frist
            con.execute(
                "UPDATE external_matters SET wiedervorlage_am = ?, "
                "vorwarnfrist_tage = ? WHERE id = ?",
                (wiedervorlage_am, frist, matter_id),
            )
            return {
                "matter_id": matter_id, "user_id": row["user_id"],
                "von": row["wiedervorlage_am"], "auf": wiedervorlage_am,
                "vorwarnfrist_tage": frist, "grund_len": self._tlen(grund),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE external_matters SET audit_seq = ? WHERE id = ?",
                        (seq, matter_id))
            insert_event_row(
                con, user_id=ctx["user_id"], event_kind=EVENT_KIND,
                payload={
                    "action": "deferred", "matter_id": matter_id,
                    "von": ctx["alt"], "auf": wiedervorlage_am,
                    "grund": grund,
                },
                created_by=actor_id, created_at=now, audit_seq=seq,
            )

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.EXTERNAL_MATTER_DEFERRED,
            actor_id=actor_id, target_type="external_matter",
            target_id=str(matter_id), meta=meta, after_audit=_after,
        )
        logger.info("Vorgang %s wiedervorgelegt: %s -> %s.",
                    matter_id, ctx.get("alt"), wiedervorlage_am)
        return seq

    def answer(
        self, matter_id: int, *, ergebnis: str = "",
        wiedervorlage_am: Optional[str] = None,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> int:
        """
        Antwort eingegangen: 'offen' -> 'beantwortet'. Der Vorgang bleibt OFFEN
        im Sinne der Wiedervorlage (die Auswertung steht ja noch aus); optional
        kann dabei ein neues Wiedervorlagedatum gesetzt werden.
        """
        writer = self._require_writer()
        if wiedervorlage_am is not None:
            self._check_date(wiedervorlage_am, "wiedervorlage_am")
        now = int(time.time())
        ctx: Dict[str, Any] = {}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._row(con, matter_id)
            MatterStatus.check_transition(row["status"], "beantwortet")
            ctx["user_id"] = row["user_id"]
            neu_wv = wiedervorlage_am or row["wiedervorlage_am"]
            ctx["wv"] = neu_wv
            con.execute(
                "UPDATE external_matters SET status = 'beantwortet', "
                "ergebnis = ?, wiedervorlage_am = ? WHERE id = ?",
                (ergebnis or None, neu_wv, matter_id),
            )
            return {
                "matter_id": matter_id, "user_id": row["user_id"],
                "von": row["status"], "auf": "beantwortet",
                "wiedervorlage_am": neu_wv,
                "ergebnis_len": self._tlen(ergebnis),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE external_matters SET audit_seq = ? WHERE id = ?",
                        (seq, matter_id))
            insert_event_row(
                con, user_id=ctx["user_id"], event_kind=EVENT_KIND,
                payload={
                    "action": "answered", "matter_id": matter_id,
                    "status": "beantwortet", "ergebnis": ergebnis or "",
                    "wiedervorlage_am": ctx["wv"],
                },
                created_by=actor_id, created_at=now, audit_seq=seq,
            )

        return writer.audited_write(
            do_write=_w, event_type=EventType.EXTERNAL_MATTER_ANSWERED,
            actor_id=actor_id, target_type="external_matter",
            target_id=str(matter_id), meta=meta, after_audit=_after,
        )

    def close(
        self, matter_id: int, *, status: str, ergebnis: str = "",
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> int:
        """
        Endgueltiger Abschluss: 'erledigt' (Antwort da UND ausgewertet) oder
        'erfolglos' (ohne Ergebnis abgeschlossen). UNWIDERRUFLICH.
        """
        writer = self._require_writer()
        if status not in ("erledigt", "erfolglos"):
            raise ExternalMattersError(
                "Abschluss nur nach 'erledigt' oder 'erfolglos' (nicht '%s')."
                % status)
        now = int(time.time())
        ctx: Dict[str, Any] = {}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._row(con, matter_id)
            MatterStatus.check_transition(row["status"], status)
            ctx["user_id"] = row["user_id"]
            ctx["von"] = row["status"]
            # Ein bereits erfasstes Ergebnis wird NICHT ueberschrieben, wenn
            # beim Abschluss keines mitkommt (kein stiller Textverlust).
            neu_erg = ergebnis if (ergebnis or "").strip() else row["ergebnis"]
            con.execute(
                "UPDATE external_matters SET status = ?, ergebnis = ?, "
                "closed_by = ?, closed_at = ? WHERE id = ?",
                (status, neu_erg, actor_id, now, matter_id),
            )
            return {
                "matter_id": matter_id, "user_id": row["user_id"],
                "von": row["status"], "auf": status,
                "ergebnis_len": self._tlen(neu_erg),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE external_matters SET audit_seq = ? WHERE id = ?",
                        (seq, matter_id))
            insert_event_row(
                con, user_id=ctx["user_id"], event_kind=EVENT_KIND,
                payload={
                    "action": "closed", "matter_id": matter_id,
                    "von": ctx["von"], "status": status,
                    "ergebnis": ergebnis or "",
                },
                created_by=actor_id, created_at=now, audit_seq=seq,
            )

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.EXTERNAL_MATTER_CLOSED,
            actor_id=actor_id, target_type="external_matter",
            target_id=str(matter_id), meta=meta, after_audit=_after,
        )
        logger.info("Vorgang %s endgueltig abgeschlossen (%s -> %s).",
                    matter_id, ctx.get("von"), status)
        return seq

# =============================================================================
# management/cases/escalation_ack_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Eskalationen (AP-2G)
# =============================================================================
# Zweck (Build 517, Befund Uebergabe 440-453 §3.3):
#   Der AUDITIERTE SCHREIBPFAD zur Eskalation. Bis Build 516 war die Sicht
#   rein auswertend — eine Leitung konnte eine Eskalation sehen, aber nirgends
#   festhalten, dass sie sie gesehen und was sie veranlasst hat. Damit fehlte
#   genau der Beleg, der eine Aufsichtsentscheidung nachvollziehbar macht.
#
# WAS EINE QUITTIERUNG IST — UND WAS SIE NICHT IST:
#   Sie ist ein VERMERK ("gesehen am ..., von ..., veranlasst wurde ...").
#   Sie ist KEIN Erledigen. Die Eskalation verschwindet NICHT: der zugrunde
#   liegende Zustand besteht fort. Wuerde ein Vermerk die Meldung ausblenden,
#   liesse sich ein liegengebliebener Fall per Klick unsichtbar machen, ohne
#   dass sich an ihm etwas aendert — die gefaehrlichste Form eines stillen
#   Beweisverlusts (Grundregel 1). Das Ausblenden ist deshalb NICHT nur nicht
#   eingebaut, es ist ausdruecklich ausgeschlossen: dieses Repo liefert
#   Vermerke, es filtert keine Meldungen.
#
# SCHLUESSEL (rule_code, subject_id):
#   Eskalationen sind ABGELEITET und haben keine dauerhafte eigene ID. Der
#   einzige stabile Bezug ist "diese Regel an diesem Fall". subject_id IST
#   NULL fuer die systemische Regel 'rueckstau_hoch' — NULL ist hier eine
#   AUSSAGE ("gehoert zu keinem Fall"), kein fehlender Wert. Alle Vergleiche
#   in diesem Modul behandeln NULL deshalb ausdruecklich ('IS NULL' statt
#   '= ?'); ein '= NULL' waere in SQL immer unwahr und der systemische
#   Vermerk waere still nie wiedergefunden worden.
#
# FACHREGEL: hoechstens EIN gueltiger Vermerk je (rule_code, subject_id).
#   Sie wird INNERHALB der Schreibtransaktion (BEGIN IMMEDIATE ueber
#   CoordinatorWriter) geprueft, nicht ueber einen UNIQUE-Index — in SQLite
#   gelten zwei NULL in einem UNIQUE-Index als verschieden, ein Index haette
#   fuer die systemische Regel also nicht gegriffen und dabei falsche
#   Sicherheit vorgetaeuscht.
#
# WIDERRUF STATT LOESCHUNG (Linie M022/Build 504):
#   Ein Vermerk wird NIE geloescht. Ein irrtuemlicher oder ueberholter Vermerk
#   wird mit Pflichtgrund widerrufen; die Zeile bleibt als Beleg stehen.
#   Danach darf dieselbe Eskalation erneut quittiert werden.
#
# SENSIBILITAET: 'reason'/'revoke_reason' sind Freitexte und stehen NIE im
#   audit_log-Payload — dort nur FAKTEN und Textlaengen (Muster M018/M022).
#
# Grundregel 10: eine Klasse, eine Datei.
# Version: v0.8.517 · Build: 517 · 2026-07-24
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType

logger = logging.getLogger(__name__)


class EscalationAckError(Exception):
    """Fachlicher Fehler beim Quittieren (handlungsleitende Klartextmeldung)."""


class EscalationAckRepo:
    """Vermerke zu Eskalationen — lesend und (mit Writer) auditiert schreibend."""

    #: Spaltenliste der Lesezugriffe (an EINER Stelle, damit Lesen und
    #  Serialisieren nicht auseinanderlaufen koennen).
    _COLS = ("id, rule_code, subject_id, reason, days_inactive_at_ack, "
             "acknowledged_by, acknowledged_at, audit_seq, is_active, "
             "revoked_at, revoked_by, revoke_reason, revoke_audit_seq")

    def __init__(self, con: sqlite3.Connection, writer: Optional[Any] = None) -> None:
        self._con = con
        self._writer = writer

    # ------------------------------------------------------------- Helfer
    def _require_writer(self):
        if self._writer is None:
            raise EscalationAckError(
                "Kein Schreibpfad verfuegbar (read-only Verbindung).")
        return self._writer

    @staticmethod
    def _tlen(text: Optional[str]) -> int:
        """Textlaenge fuer den Audit-Payload (statt des Freitexts selbst)."""
        return len(text or "")

    @staticmethod
    def _norm_subject(subject_id: Optional[Any]) -> Optional[int]:
        """
        subject_id normalisieren. None bleibt None (systemische Regel) — es
        wird BEWUSST nicht auf 0 abgebildet: 0 waere eine Fallnummer.
        """
        if subject_id is None or subject_id == "":
            return None
        return int(subject_id)

    @staticmethod
    def table_exists(con: sqlite3.Connection) -> bool:
        """
        Ob M027 angewandt ist. Die Lesesicht fragt das, um bei einer noch
        nicht migrierten Datenbank 'keine Vermerke moeglich' zu MELDEN statt
        eine leere Vermerkliste zu zeigen (die wie 'nichts quittiert' laese).
        """
        return con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='escalation_ack'").fetchone() is not None

    # -------------------------------------------------------------- Lesen
    def _row_by_id(self, con: sqlite3.Connection, ack_id: int):
        return con.execute(
            "SELECT %s FROM escalation_ack WHERE id = ?" % self._COLS,
            (int(ack_id),)).fetchone()

    def _active_for(self, con: sqlite3.Connection, rule_code: str,
                    subject_id: Optional[int]):
        """
        Der gueltige Vermerk zu (rule_code, subject_id) — oder None.
        NULL wird ausdruecklich mit 'IS NULL' geprueft (siehe Kopfkommentar).
        """
        if subject_id is None:
            return con.execute(
                "SELECT %s FROM escalation_ack WHERE rule_code = ? "
                "AND subject_id IS NULL AND is_active = 1" % self._COLS,
                (rule_code,)).fetchone()
        return con.execute(
            "SELECT %s FROM escalation_ack WHERE rule_code = ? "
            "AND subject_id = ? AND is_active = 1" % self._COLS,
            (rule_code, int(subject_id))).fetchone()

    @staticmethod
    def _to_dict(row) -> Dict[str, Any]:
        return {
            "ack_id": int(row["id"]),
            "rule_code": row["rule_code"],
            "subject_id": (None if row["subject_id"] is None
                           else int(row["subject_id"])),
            "reason": row["reason"],
            "days_inactive_at_ack": (None if row["days_inactive_at_ack"] is None
                                     else int(row["days_inactive_at_ack"])),
            "acknowledged_by": int(row["acknowledged_by"]),
            "acknowledged_at": int(row["acknowledged_at"]),
            "audit_seq": int(row["audit_seq"]),
            "is_active": int(row["is_active"]) == 1,
            "revoked_at": (None if row["revoked_at"] is None
                           else int(row["revoked_at"])),
            "revoked_by": (None if row["revoked_by"] is None
                           else int(row["revoked_by"])),
            "revoke_reason": row["revoke_reason"],
            "revoke_audit_seq": (None if row["revoke_audit_seq"] is None
                                 else int(row["revoke_audit_seq"])),
        }

    def list_active(self) -> List[Dict[str, Any]]:
        """
        Alle GUELTIGEN Vermerke. Die Lesesicht ordnet sie ihren Meldungen zu.
        """
        if not self.table_exists(self._con):
            return []
        rows = self._con.execute(
            "SELECT %s FROM escalation_ack WHERE is_active = 1 "
            "ORDER BY acknowledged_at DESC, id DESC" % self._COLS).fetchall()
        return [self._to_dict(r) for r in rows]

    def names(self) -> Dict[int, str]:
        """
        person_id -> Anzeigename. Faellt die Tabelle aus, bleibt es bei den
        IDs — ein Vermerk ohne aufloesbaren Namen ist immer noch ein Beleg
        (und der Ausfall wird protokolliert, kein stiller Zustand).
        """
        out: Dict[int, str] = {}
        try:
            for r in self._con.execute(
                    "SELECT id, display_name, system_username FROM person"):
                out[int(r["id"])] = (r["display_name"] or r["system_username"]
                                     or ("#%d" % int(r["id"])))
        except sqlite3.OperationalError as exc:  # pragma: no cover
            logger.warning("Namen der Quittierenden nicht aufloesbar (%s) — "
                           "es bleibt bei den IDs.", exc)
        return out

    # ----------------------------------------------------------- Schreiben
    def acknowledge(self, *, rule_code: str, subject_id: Optional[Any],
                    reason: str, days_inactive: Optional[Any] = None,
                    actor_id: Optional[int] = None,
                    meta: Optional[Any] = None) -> Dict[str, Any]:
        """
        Eskalation quittieren. Auditiert (EIN Beleg je Vermerk).

        BEGRUENDUNG IST PFLICHT. Ein Vermerk ohne Begruendung wuerde nur
        belegen, dass jemand geklickt hat — nicht, dass eine Entscheidung
        getroffen wurde. Genau letzteres ist der Zweck dieses Schreibpfads.

        'days_inactive' haelt den BEOBACHTETEN STAND fest. Ohne ihn waere ein
        Vermerk von vor einem halben Jahr nicht von einem heutigen zu
        unterscheiden. None ist zulaessig (die systemische Regel kennt keine
        Inaktivitaet) und heisst 'nicht erhoben', NICHT '0 Tage'.
        """
        writer = self._require_writer()
        code = (rule_code or "").strip()
        if not code:
            raise EscalationAckError("rule_code ist Pflicht.")
        sid = self._norm_subject(subject_id)
        reason_txt = (reason or "").strip()
        if not reason_txt:
            raise EscalationAckError(
                "Begruendung ist Pflicht: ein Vermerk ohne Begruendung belegt "
                "nur einen Klick, keine Entscheidung.")
        di = (None if days_inactive is None or days_inactive == ""
              else int(days_inactive))
        now = int(time.time())
        state: Dict[str, Any] = {"row_id": None}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            # Fachregel INNERHALB der Transaktion (BEGIN IMMEDIATE) pruefen.
            vorhanden = self._active_for(con, code, sid)
            if vorhanden is not None:
                raise EscalationAckError(
                    "Zu dieser Eskalation (%s / %s) besteht bereits ein "
                    "gueltiger Vermerk (#%d). Er ist zuerst zu widerrufen."
                    % (code, "systemisch" if sid is None else sid,
                       int(vorhanden["id"])))
            cur = con.execute(
                "INSERT INTO escalation_ack "
                "(rule_code, subject_id, reason, days_inactive_at_ack, "
                " acknowledged_by, acknowledged_at, audit_seq, is_active) "
                "VALUES (?, ?, ?, ?, ?, ?, 0, 1)",
                (code, sid, reason_txt, di, actor_id, now),
            )
            state["row_id"] = int(cur.lastrowid or 0)
            # Payload: FAKTEN + Textlaenge, KEIN Freitext.
            return {
                "ack_id": state["row_id"],
                "rule_code": code,
                "subject_id": sid,
                "days_inactive_at_ack": di,
                "reason_len": self._tlen(reason_txt),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE escalation_ack SET audit_seq = ? WHERE id = ?",
                        (seq, state["row_id"]))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.ESCALATION_ACKNOWLEDGED,
            actor_id=actor_id, target_type="escalation_ack",
            target_id=(None if sid is None else str(sid)), meta=meta,
            after_audit=_after,
        )
        logger.info("Eskalation %s/%s quittiert (Vermerk #%s, Beleg #%d).",
                    code, sid, state["row_id"], seq)
        return {"ack_id": state["row_id"], "rule_code": code,
                "subject_id": sid, "audit_seq": seq}

    def revoke(self, *, ack_id: int, reason: str,
               actor_id: Optional[int] = None,
               meta: Optional[Any] = None) -> Dict[str, Any]:
        """
        Vermerk WIDERRUFEN (soft): is_active=0 + Pflichtgrund. Die Zeile
        BLEIBT — ein stilles Loeschen wuerde die Erkenntnis "es wurde einmal
        quittiert" vernichten, und gerade die ist die aufsichtsrelevante
        (Grundregel 1). Danach darf dieselbe Eskalation erneut quittiert
        werden.
        """
        writer = self._require_writer()
        aid = int(ack_id)
        reason_txt = (reason or "").strip()
        if not reason_txt:
            raise EscalationAckError(
                "Grund ist Pflicht: ein Vermerk darf nicht ohne "
                "nachvollziehbaren Grund widerrufen werden.")
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._row_by_id(con, aid)
            if row is None:
                raise EscalationAckError("Unbekannter Vermerk #%d." % aid)
            if int(row["is_active"]) != 1:
                raise EscalationAckError(
                    "Vermerk #%d ist bereits widerrufen — ein zweiter "
                    "Widerruf erzeugte einen irrefuehrenden Beleg." % aid)
            con.execute(
                "UPDATE escalation_ack SET is_active = 0, revoked_at = ?, "
                "revoked_by = ?, revoke_reason = ? WHERE id = ?",
                (now, actor_id, reason_txt, aid))
            return {
                "ack_id": aid,
                "rule_code": row["rule_code"],
                "subject_id": (None if row["subject_id"] is None
                               else int(row["subject_id"])),
                "revoke_reason_len": self._tlen(reason_txt),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute(
                "UPDATE escalation_ack SET revoke_audit_seq = ? WHERE id = ?",
                (seq, aid))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.ESCALATION_ACK_REVOKED,
            actor_id=actor_id, target_type="escalation_ack",
            target_id=str(aid), meta=meta, after_audit=_after,
        )
        logger.info("Vermerk #%d widerrufen (Beleg #%d).", aid, seq)
        return {"ack_id": aid, "audit_seq": seq}


def annotate_items(items: List[Dict[str, Any]],
                   acks: List[Dict[str, Any]],
                   names: Optional[Dict[int, str]] = None
                   ) -> List[Dict[str, Any]]:
    """
    REINE Zuordnung von Vermerken zu Meldungen (dateilos testbar).

    Jede Meldung bekommt den Schluessel 'ack':
      None                      — nicht quittiert
      {..., 'outdated': bool}   — quittiert

    'outdated' ist eine reine TATSACHE ohne zusaetzliche Schwelle: der Fall
    ist heute laenger inaktiv als zum Zeitpunkt der Quittierung. Die Sicht
    kann daran zeigen, dass sich die Lage seit dem Vermerk VERSCHLECHTERT hat.
    Fehlt einer der beiden Werte, ist 'outdated' False — 'nicht vergleichbar'
    darf nicht als 'verschlechtert' erscheinen.

    KEINE Meldung wird entfernt oder umsortiert. Quittieren ist kein
    Erledigen (siehe Kopfkommentar).
    """
    names = names or {}
    index: Dict[Any, Dict[str, Any]] = {}
    for a in acks:
        index[(a.get("rule_code"), a.get("subject_id"))] = a

    out: List[Dict[str, Any]] = []
    for it in items:
        row = dict(it)
        a = index.get((row.get("rule_code"), row.get("subject_id")))
        if a is None:
            row["ack"] = None
        else:
            di_now = row.get("days_inactive")
            di_ack = a.get("days_inactive_at_ack")
            outdated = (di_now is not None and di_ack is not None
                        and int(di_now) > int(di_ack))
            row["ack"] = {
                "ack_id": a.get("ack_id"),
                "reason": a.get("reason"),
                "acknowledged_by": a.get("acknowledged_by"),
                "acknowledged_by_name": names.get(a.get("acknowledged_by")),
                "acknowledged_at": a.get("acknowledged_at"),
                "days_inactive_at_ack": di_ack,
                "audit_seq": a.get("audit_seq"),
                "outdated": outdated,
            }
        out.append(row)
    return out

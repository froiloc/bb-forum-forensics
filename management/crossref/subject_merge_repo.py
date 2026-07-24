# =============================================================================
# management/crossref/subject_merge_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Identitaet (AP-2A)
# =============================================================================
# Zweck (Idee 11, Build 509):
#   Zugriffsschicht auf 'subject_merge' (M025) — das UMKEHRBARE, auditierte
#   Zusammenfuehren und Trennen von Identitaeten: "Konto 4711 und Konto 90210
#   werden von DERSELBEN natuerlichen Person betrieben".
#
#   SCHREIBEN ausschliesslich ueber das CoordinatorWriter-Gateway (Write +
#   audit_log-Beleg in EINER Transaktion oder gar nicht).
#
# ABGRENZUNG zu den Nachbarn im selben Paket:
#   identified_subject (M018) — "Konto -> REALE PERSON" (wer ist das?)
#   subject_alias      (M022) — "Konto -> WEITERER NAME" (wie nennt er sich?)
#   subject_merge      (M025) — "Konto A und Konto B sind DIESELBE Person"
#                               (auch wenn wir noch nicht wissen, WER)
#   Der letzte Fall ist gerade der haeufige: man erkennt ein Zweitkonto lange
#   bevor man einen Klarnamen hat. Deshalb ist er eigenstaendig modelliert und
#   nicht als Sonderfall von M018.
#
# FLACHE ZWEIEBENEN-STRUKTUR (E1, die zentrale Entwurfsentscheidung):
#   Eine Zeile verbindet ein PRIMAER-Konto mit einem EINGEGLIEDERTEN Konto.
#   KETTEN sind verboten (A<-B und gleichzeitig B<-C). Wer C an B haengen will,
#   waehrend B schon zu A gehoert, bekommt einen sprechenden Fehler MIT den
#   beteiligten subject_ids und den Hinweis, C direkt an A zu haengen.
#   Begruendung: Ketten machen die Umkehrung MEHRDEUTIG — loest man B->A auf,
#   wohin gehoert dann C? Ein Werkzeug, das diese Frage nicht eindeutig
#   beantwortet, erzeugt in einem Strafverfahren angreifbare Aussagen.
#
# TRENNUNG IST EIN SOFT-WIDERRUF (E2): is_active=0 + Pflicht-Grund. Die Zeile
#   bleibt. "Wir hielten das mal fuer dieselbe Person, und hier steht, warum
#   wir es nicht mehr tun" ist SELBST ein Ermittlungsergebnis (Grundregel 1).
#
# KONFIDENZ (E4): dieselbe Achse wie identified_subject — verdacht (10) <
#   wahrscheinlich (20) < gesichert (30), beim Schreiben eingefroren
#   (Muster m011: Code + eingefrorener Zahlenwert).
#
# SENSIBILITAET (streng, Muster M018): 'basis' und 'split_reason' gehen NIE als
#   Klartext ins Audit-Payload — dort stehen FAKTEN (primary_subject_id,
#   merged_subject_id, confidence_code/ordinal) + TEXTLAENGEN.
#
# NEBENLAEUFIGKEIT: alle Ketten- und Kollisionspruefungen laufen INNERHALB der
#   Transaktion (BEGIN IMMEDIATE haelt die Schreibsperre) — kein TOCTOU-Fenster.
#
# Version: v0.8.509 · Build: 509 · 2026-07-24
# =============================================================================

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.crossref.identified_subject_repo import CrossrefError
from management.gateway.coordinator_writer import CoordinatorWriter

logger = logging.getLogger(__name__)

#: Eingefrorene Code->Ordinal-Karte. Deckungsgleich mit der CHECK-Klausel in
#  m025 UND mit _CONFIDENCE in identified_subject_repo — bewusst DIESELBE
#  Skala (E4), damit eine Ermittlerin nicht zwei Bedeutungen lernen muss.
_CONFIDENCE: Dict[str, int] = {
    "verdacht": 10,
    "wahrscheinlich": 20,
    "gesichert": 30,
}


class SubjectMergeRepo:
    """Auditierte Lese-/Schreibmethoden auf 'subject_merge' (M025)."""

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
    def _tlen(text: Optional[str]) -> int:
        return len(text or "")

    @staticmethod
    def _ordinal(confidence_code: str) -> int:
        """Friert den Zahlenwert der Konfidenz ein. Wirft bei unbekanntem Code —
        der Repo laesst KEINE Stufe zu, die die DDL-CHECK spaeter ablehnte."""
        try:
            return _CONFIDENCE[confidence_code]
        except KeyError:
            raise CrossrefError(
                "Ungueltige Konfidenzstufe %r (erlaubt: %s)."
                % (confidence_code, ", ".join(_CONFIDENCE)))

    @staticmethod
    def _row_by_id(con: sqlite3.Connection,
                   merge_id: int) -> Optional[sqlite3.Row]:
        return con.execute(
            "SELECT * FROM subject_merge WHERE id = ?", (merge_id,)).fetchone()

    @staticmethod
    def _active_as_merged(con: sqlite3.Connection,
                          subject_id: int) -> Optional[sqlite3.Row]:
        """Aktive Zeile, in der 'subject_id' EINGEGLIEDERT ist."""
        return con.execute(
            "SELECT * FROM subject_merge "
            "WHERE merged_subject_id = ? AND is_active = 1",
            (subject_id,)).fetchone()

    @staticmethod
    def _active_as_primary(con: sqlite3.Connection,
                           subject_id: int) -> Optional[sqlite3.Row]:
        """Irgendeine aktive Zeile, in der 'subject_id' PRIMAER ist."""
        return con.execute(
            "SELECT * FROM subject_merge "
            "WHERE primary_subject_id = ? AND is_active = 1 LIMIT 1",
            (subject_id,)).fetchone()

    def _check_flat(self, con: sqlite3.Connection, primary: int,
                    merged: int, except_id: Optional[int] = None) -> None:
        """
        Setzt die FLACHE Struktur (E1) durch. Drei Konflikte, jeder mit einer
        sprechenden Meldung SAMT der beteiligten subject_ids — die Ermittlerin
        soll sofort sehen, WAS der Konflikt ist, statt ein generisches
        "geht nicht" zu lesen.
        """
        if primary == merged:
            # Zusaetzlich zur DDL-CHECK, damit die Meldung fachlich ist.
            raise CrossrefError(
                "Ein Konto kann nicht mit sich selbst zusammengefuehrt werden "
                "(subject_id %s)." % primary)

        # (1) Das einzugliedernde Konto haengt schon woanders.
        row = self._active_as_merged(con, merged)
        if row is not None and (except_id is None
                                or int(row["id"]) != except_id):
            raise CrossrefError(
                "Konto %s ist bereits aktiv dem Primaerkonto %s zugeordnet "
                "(Zusammenfuehrung #%d). Erst trennen, dann neu zuordnen."
                % (merged, int(row["primary_subject_id"]), int(row["id"])))

        # (2) Das einzugliedernde Konto ist selbst PRIMAER -> waere eine Kette.
        row = self._active_as_primary(con, merged)
        if row is not None and (except_id is None
                                or int(row["id"]) != except_id):
            raise CrossrefError(
                "Konto %s ist selbst Primaerkonto (z. B. fuer Konto %s) — "
                "Ketten sind nicht vorgesehen, weil ihre Aufloesung mehrdeutig "
                "waere. Haenge die betroffenen Konten stattdessen DIREKT an %s."
                % (merged, int(row["merged_subject_id"]), primary))

        # (3) Das Primaerkonto ist selbst eingegliedert -> ebenfalls Kette.
        row = self._active_as_merged(con, primary)
        if row is not None and (except_id is None
                                or int(row["id"]) != except_id):
            raise CrossrefError(
                "Konto %s ist selbst dem Primaerkonto %s zugeordnet — waehle "
                "%s als Primaerkonto, damit die Gruppe eindeutig bleibt."
                % (primary, int(row["primary_subject_id"]),
                   int(row["primary_subject_id"])))

    # ------------------------------------------------------------------- Lesen
    def list(self, include_split: bool = False) -> List[Dict[str, Any]]:
        """Zusammenfuehrungen; staerkste Konfidenz zuerst, dann Primaerkonto."""
        sql = "SELECT * FROM subject_merge"
        if not include_split:
            sql += " WHERE is_active = 1"
        sql += (" ORDER BY is_active DESC, confidence_ordinal DESC, "
                "primary_subject_id ASC, merged_subject_id ASC")
        return [self._as_dict(r) for r in self._con.execute(sql)]

    def group_of(self, subject_id: int) -> Dict[str, Any]:
        """
        ALLE Konten derselben Person — unabhaengig davon, WELCHES Konto gefragt
        wurde. Das ist die eigentliche Ermittlungsfrage ("was gehoert noch zu
        dem hier?"), und sie darf nicht davon abhaengen, ob man zufaellig das
        Primaerkonto erwischt hat.
        -> {'primary_subject_id', 'members': [...], 'merges': [...]}
        Ist das Konto in keiner aktiven Zusammenfuehrung, ist es sein eigenes
        Primaerkonto und die Gruppe besteht nur aus ihm (KEIN Leerbefund).
        """
        sid = int(subject_id)
        row = self._active_as_merged(self._con, sid)
        primary = int(row["primary_subject_id"]) if row is not None else sid

        merges = [self._as_dict(r) for r in self._con.execute(
            "SELECT * FROM subject_merge "
            "WHERE primary_subject_id = ? AND is_active = 1 "
            "ORDER BY confidence_ordinal DESC, merged_subject_id ASC",
            (primary,))]
        members = [primary] + [m["merged_subject_id"] for m in merges]
        return {
            "primary_subject_id": primary,
            "members": members,
            "merges": merges,
            # Fuer die Sicht: war das gefragte Konto das Primaerkonto?
            "queried_subject_id": sid,
            "is_primary": (primary == sid),
        }

    def counts(self) -> Dict[str, int]:
        """Aktive / getrennte Zusammenfuehrungen + betroffene Konten."""
        row = self._con.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS aktiv, "
            "SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END) AS getrennt "
            "FROM subject_merge").fetchone()
        # Betroffene Konten = Primaerkonten + eingegliederte Konten (aktiv).
        konten = self._con.execute(
            "SELECT COUNT(*) AS n FROM ("
            "  SELECT primary_subject_id AS s FROM subject_merge "
            "   WHERE is_active = 1"
            "  UNION"
            "  SELECT merged_subject_id AS s FROM subject_merge "
            "   WHERE is_active = 1)").fetchone()
        return {
            "total": int(row["total"] or 0),
            "aktiv": int(row["aktiv"] or 0),
            "getrennt": int(row["getrennt"] or 0),
            "konten": int(konten["n"] or 0),
        }

    # --------------------------------------------------------------- Schreiben
    def merge(self, *, primary_subject_id: int, merged_subject_id: int,
              basis: str, confidence_code: str,
              actor_id: Optional[int] = None,
              meta: Optional[Any] = None) -> Dict[str, Any]:
        """
        Fuehrt zwei Konten zusammen. Prueft E1/E3 IN der Transaktion.
        Auditiert. -> {'merge_id','primary_subject_id','merged_subject_id',
                       'audit_seq'}.
        """
        writer = self._require_writer()
        primary = int(primary_subject_id)
        merged = int(merged_subject_id)
        basis_txt = (basis or "").strip()
        if not basis_txt:
            raise CrossrefError(
                "Basis ist Pflicht: eine Zusammenfuehrung ist eine Hypothese "
                "und braucht die Indizien, auf die sie sich stuetzt.")
        ordinal = self._ordinal(confidence_code)

        now = int(time.time())
        state: Dict[str, Any] = {"row_id": None}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            self._check_flat(con, primary, merged)
            cur = con.execute(
                "INSERT INTO subject_merge "
                "(primary_subject_id, merged_subject_id, basis, "
                " confidence_code, confidence_ordinal, is_active, "
                " split_reason, merged_by, split_by, created_at, updated_at, "
                " split_at, audit_seq, created_audit_seq) "
                "VALUES (?, ?, ?, ?, ?, 1, NULL, ?, NULL, ?, ?, NULL, 0, 0)",
                (primary, merged, basis_txt, confidence_code, ordinal,
                 actor_id, now, now))
            state["row_id"] = int(cur.lastrowid or 0)
            # Payload: FAKTEN + Textlaenge, KEIN Freitext.
            return {
                "merge_id": state["row_id"],
                "primary_subject_id": primary,
                "merged_subject_id": merged,
                "confidence_code": confidence_code,
                "confidence_ordinal": ordinal,
                "basis_len": self._tlen(basis_txt),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute(
                "UPDATE subject_merge SET audit_seq = ?, created_audit_seq = ? "
                "WHERE id = ?", (seq, seq, state["row_id"]))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.SUBJECT_MERGED,
            actor_id=actor_id, target_type="subject_merge",
            target_id=str(primary), meta=meta, after_audit=_after,
        )
        logger.info("subject_merge #%s: %s <- %s (%s, Beleg #%d).",
                    state["row_id"], primary, merged, confidence_code, seq)
        return {"merge_id": state["row_id"],
                "primary_subject_id": primary,
                "merged_subject_id": merged, "audit_seq": seq}

    def revise(self, *, merge_id: int, basis: Optional[str] = None,
               confidence_code: Optional[str] = None,
               actor_id: Optional[int] = None,
               meta: Optional[Any] = None) -> Dict[str, Any]:
        """
        Laesst eine bestehende Zusammenfuehrung REIFEN (Konfidenz/Basis).
        Die beteiligten Konten sind bewusst NICHT aenderbar — eine andere
        Paarung ist eine andere Hypothese und entsteht durch split() + merge().
        Ein No-Op wirft und erzeugt KEINEN irrefuehrenden Beleg.
        """
        writer = self._require_writer()
        mid = int(merge_id)
        if confidence_code is not None:
            self._ordinal(confidence_code)   # frueh validieren
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._row_by_id(con, mid)
            if row is None:
                raise CrossrefError("Unbekannte Zusammenfuehrung #%d." % mid)
            if int(row["is_active"]) != 1:
                raise CrossrefError(
                    "Zusammenfuehrung #%d ist getrennt — sie wird erst durch "
                    "'Trennung zuruecknehmen' wieder bearbeitbar." % mid)

            new_conf = (confidence_code if confidence_code is not None
                        else row["confidence_code"])
            new_ord = self._ordinal(new_conf)
            new_basis = basis if basis is not None else row["basis"]
            new_basis = (new_basis or "").strip()
            if not new_basis:
                raise CrossrefError("Basis darf nicht geleert werden.")

            changes: Dict[str, Any] = {}
            if row["confidence_code"] != new_conf:
                changes["confidence"] = {
                    "alt": row["confidence_code"], "neu": new_conf,
                    "alt_ordinal": int(row["confidence_ordinal"]),
                    "neu_ordinal": new_ord,
                }
            if (row["basis"] or "") != new_basis:
                changes["basis_len"] = {"alt": self._tlen(row["basis"]),
                                        "neu": self._tlen(new_basis)}
            if not changes:
                raise CrossrefError(
                    "Keine Aenderung — die Werte entsprechen dem aktuellen "
                    "Stand (Zusammenfuehrung #%d)." % mid)

            con.execute(
                "UPDATE subject_merge SET basis = ?, confidence_code = ?, "
                "confidence_ordinal = ?, updated_at = ? WHERE id = ?",
                (new_basis, new_conf, new_ord, now, mid))
            return {"merge_id": mid,
                    "primary_subject_id": int(row["primary_subject_id"]),
                    "merged_subject_id": int(row["merged_subject_id"]),
                    "changes": changes}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE subject_merge SET audit_seq = ? WHERE id = ?",
                        (seq, mid))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.SUBJECT_MERGE_REVISED,
            actor_id=actor_id, target_type="subject_merge",
            target_id=str(mid), meta=meta, after_audit=_after,
        )
        logger.info("subject_merge #%d revidiert (Beleg #%d).", mid, seq)
        return {"merge_id": mid, "audit_seq": seq}

    def split(self, *, merge_id: int, reason: str,
              actor_id: Optional[int] = None,
              meta: Optional[Any] = None) -> Dict[str, Any]:
        """
        TRENNUNG (soft): is_active=0 + Pflicht-Grund + Zeitpunkt. Die Zeile
        BLEIBT — die Erkenntnis "wir hielten das mal fuer dieselbe Person" ist
        selbst ein Ermittlungsergebnis (E2). Danach darf dasselbe Konto erneut
        zugeordnet werden (partieller UNIQUE-Index).
        """
        writer = self._require_writer()
        mid = int(merge_id)
        reason_txt = (reason or "").strip()
        if not reason_txt:
            raise CrossrefError(
                "Grund ist Pflicht: eine Trennung muss so belegt sein wie die "
                "Zusammenfuehrung.")
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._row_by_id(con, mid)
            if row is None:
                raise CrossrefError("Unbekannte Zusammenfuehrung #%d." % mid)
            if int(row["is_active"]) != 1:
                raise CrossrefError(
                    "Zusammenfuehrung #%d ist bereits getrennt." % mid)
            con.execute(
                "UPDATE subject_merge SET is_active = 0, split_reason = ?, "
                "split_by = ?, split_at = ?, updated_at = ? WHERE id = ?",
                (reason_txt, actor_id, now, now, mid))
            return {"merge_id": mid,
                    "primary_subject_id": int(row["primary_subject_id"]),
                    "merged_subject_id": int(row["merged_subject_id"]),
                    "is_active": 0,
                    "reason_len": self._tlen(reason_txt)}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE subject_merge SET audit_seq = ? WHERE id = ?",
                        (seq, mid))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.SUBJECT_SPLIT,
            actor_id=actor_id, target_type="subject_merge",
            target_id=str(mid), meta=meta, after_audit=_after,
        )
        logger.info("subject_merge #%d getrennt (Beleg #%d).", mid, seq)
        return {"merge_id": mid, "audit_seq": seq}

    def remerge(self, *, merge_id: int, actor_id: Optional[int] = None,
                meta: Optional[Any] = None) -> Dict[str, Any]:
        """
        Nimmt eine Trennung zurueck (die Trennung war ein Irrtum). Die volle
        Ketten-/Kollisionspruefung laeuft erneut — inzwischen kann sich die
        Lage geaendert haben, und zwei widerspruechliche aktive Zuordnungen
        waeren schlimmer als eine abgelehnte Ruecknahme.
        """
        writer = self._require_writer()
        mid = int(merge_id)
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._row_by_id(con, mid)
            if row is None:
                raise CrossrefError("Unbekannte Zusammenfuehrung #%d." % mid)
            if int(row["is_active"]) == 1:
                raise CrossrefError(
                    "Zusammenfuehrung #%d ist bereits aktiv." % mid)
            self._check_flat(con, int(row["primary_subject_id"]),
                             int(row["merged_subject_id"]), except_id=mid)
            con.execute(
                "UPDATE subject_merge SET is_active = 1, split_reason = NULL, "
                "split_by = NULL, split_at = NULL, updated_at = ? WHERE id = ?",
                (now, mid))
            return {"merge_id": mid,
                    "primary_subject_id": int(row["primary_subject_id"]),
                    "merged_subject_id": int(row["merged_subject_id"]),
                    "is_active": 1}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE subject_merge SET audit_seq = ? WHERE id = ?",
                        (seq, mid))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.SUBJECT_REMERGED,
            actor_id=actor_id, target_type="subject_merge",
            target_id=str(mid), meta=meta, after_audit=_after,
        )
        logger.info("subject_merge #%d wieder aktiv (Beleg #%d).", mid, seq)
        return {"merge_id": mid, "audit_seq": seq}

    # ------------------------------------------------------------------ intern
    @staticmethod
    def _as_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": int(row["id"]),
            "primary_subject_id": int(row["primary_subject_id"]),
            "merged_subject_id": int(row["merged_subject_id"]),
            "basis": row["basis"],
            "confidence_code": row["confidence_code"],
            "confidence_ordinal": int(row["confidence_ordinal"]),
            "is_active": int(row["is_active"]) == 1,
            "split_reason": row["split_reason"],
            "merged_by": (int(row["merged_by"])
                          if row["merged_by"] is not None else None),
            "split_by": (int(row["split_by"])
                         if row["split_by"] is not None else None),
            "created_at": int(row["created_at"]),
            "updated_at": int(row["updated_at"]),
            "split_at": (int(row["split_at"])
                         if row["split_at"] is not None else None),
            "audit_seq": int(row["audit_seq"]),
            "created_audit_seq": int(row["created_audit_seq"]),
        }

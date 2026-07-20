# =============================================================================
# management/crossref/identified_subject_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Identitaet (AP-2A)
# =============================================================================
# Zweck (Ideen 9, 10):
#   Zugriffsschicht auf 'identified_subject' (M018) — den GLOBALEN Katalog
#   identifizierter Personen: je Forennutzer hoechstens ein Eintrag der Form
#   "Konto <subject_id> ist zugeordnet zu realer Person <real_identity>", mit
#   einer KONFIDENZSTUFE. SCHREIBEN ausschliesslich ueber das CoordinatorWriter-
#   Gateway: fachlicher Write + audit_log-Beleg committen in EINER Transaktion
#   oder gar nicht. Keine Zuordnung ohne lueckenlosen Beleg (Grundregel 1).
#
# SCHLUESSEL (mc 2026-07-20):
#   subject_id ist der Forennutzer-Schluessel NACH PREPPER-SCHEMA (Realnutzer:
#   subject_id == users.id; Geist: subject_id == prefix + mat_usernames.id,
#   Beleg: Entscheidung SubjectID/Geisternutzer 2026-07-20). Bewusst KEIN FK auf
#   cases: der Katalog ist global und betrifft teils Geister, fuer die (noch)
#   kein Fallpaket existiert. Fuer Realnutzer joint subject_id heute schon auf
#   cases.user_id. Die globale user_id->subject_id-Umstellung ist ein EIGENER
#   Folge-Build (Datenmigrationsleitfaden), NICHT Teil von 468.
#
# KONFIDENZ — ZWEI GETRENNTE ACHSEN (mc 2026-07-20):
#   Achse 1 (HIER umgesetzt): Identitaets-Konfidenz, rein erkenntnisbezogen:
#     'verdacht' < 'wahrscheinlich' < 'gesichert' (Ordinal 10/20/30, eingefroren
#     beim Schreiben — Muster m011: Code + eingefrorener Zahlenwert).
#     'gesichert' meint "nahezu zweifelsfrei"; bewusst NICHT 'gerichtsfest',
#     weil dieser Begriff Sicherheit mit Verwertbarkeit vermischte (E2).
#   Achse 2 (ZURUECKGESTELLT): VERWERTBARKEIT (prozessual/rechtlich) — juristisch
#     mit der StA abzustimmen, danach ADDITIV nachruestbar (append-faehige
#     Tabelle + audit_log). Bis dahin bleibt es bei Achse 1.
#
# SENSIBILITAETSREGEL (streng): real_identity/basis/note sind die kronjuwelen-
#   artigen PII-Freitexte, die das Werkzeug erzeugt. Sie gehen NIE in den
#   audit_log-Payload — dort stehen nur FAKTEN (subject_id, confidence_code,
#   confidence_ordinal) + TEXTLAENGEN. So bleibt der Beleg pruefbar, ohne die
#   sensiblen Inhalte zu spiegeln.
#
# AKTUALISIERBAR, JEDE AENDERUNG AUDITIERT: Eine Konfidenz reift belegt von
#   'verdacht' zu 'gesichert'. Darum UPDATE erlaubt (nicht hart append-only wie
#   investigation_results) — aber jede Aenderung schreibt ihren Beleg; die
#   Historie liegt im hash-verketteten audit_log. Ein No-Op (keine echte
#   Aenderung) wirft und erzeugt KEINEN irrefuehrenden Beleg (Muster PersonRepo).
#
# Version: v0.7.468 · Build: 468 · 2026-07-20
# =============================================================================

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.gateway.coordinator_writer import CoordinatorWriter

logger = logging.getLogger(__name__)

#: Eingefrorene Code->Ordinal-Karte der Identitaets-Konfidenz (Achse 1).
#  Muss zur CHECK-Klausel in m018 passen (dort LITERAL, m005-Prinzip: die
#  Migration importiert dieses Modul NICHT). Reihenfolge = Beweisstaerke.
_CONFIDENCE: Dict[str, int] = {
    "verdacht": 10,
    "wahrscheinlich": 20,
    "gesichert": 30,
}

#: Freitextfelder — im Audit-Payload NUR als Laenge, nie als Inhalt.
_TEXT_FIELDS = ("real_identity", "basis", "note")


class CrossrefError(Exception):
    """Fachlicher Fehler (ungueltige Eingabe, unbekannter Eintrag, No-Op)."""


class IdentifiedSubjectRepo:
    """Auditierte Lese-/Schreibmethoden auf 'identified_subject'."""

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
        """Friert den Zahlenwert der Konfidenz ein. Wirft bei unbekanntem Code
        — der Repo laesst KEINE Stufe zu, die die DDL-CHECK spaeter ablehnte."""
        try:
            return _CONFIDENCE[confidence_code]
        except KeyError:
            raise CrossrefError(
                "Ungueltige Konfidenzstufe %r (erlaubt: %s)."
                % (confidence_code, ", ".join(_CONFIDENCE)))

    def _row(self, con: sqlite3.Connection,
             subject_id: int) -> Optional[sqlite3.Row]:
        return con.execute(
            "SELECT * FROM identified_subject WHERE subject_id = ?",
            (subject_id,)).fetchone()

    # ------------------------------------------------------------------- Lesen
    def get(self, subject_id: int) -> Optional[Dict[str, Any]]:
        """Den Katalogeintrag eines Forennutzers als dict oder None."""
        row = self._row(self._con, int(subject_id))
        return self._as_dict(row) if row is not None else None

    def list(self) -> List[Dict[str, Any]]:
        """Alle Eintraege, staerkste Konfidenz zuerst, dann subject_id."""
        rows = self._con.execute(
            "SELECT * FROM identified_subject "
            "ORDER BY confidence_ordinal DESC, subject_id ASC").fetchall()
        return [self._as_dict(r) for r in rows]

    # --------------------------------------------------------------- Schreiben
    def upsert(
        self, *, subject_id: int, real_identity: str, confidence_code: str,
        basis: str = "", note: Optional[str] = None,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Legt einen Katalogeintrag an ODER aktualisiert den vorhandenen (je
        subject_id genau ein Eintrag). Auditiert. Ein No-Op (identische Werte)
        wirft CrossrefError. Freitext steht NICHT im Payload.
        -> {'subject_id', 'confidence_code', 'audit_seq', 'created'}.
        """
        writer = self._require_writer()
        sid = int(subject_id)

        real_identity = (real_identity or "").strip()
        if not real_identity:
            raise CrossrefError("real_identity darf nicht leer sein.")
        ordinal = self._ordinal(confidence_code)
        basis = basis or ""
        note_norm = note if (note is None or note != "") else None

        now = int(time.time())
        state: Dict[str, Any] = {"created": False, "row_id": None}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            # UNIQUE-Pruefung INNERHALB der Transaktion (BEGIN IMMEDIATE haelt
            # die Schreibsperre — kein TOCTOU-Fenster gegen konkurrierende
            # Schreiber, Muster PersonRepo/OnboardingRepo).
            row = self._row(con, sid)

            if row is None:
                # --- Erstidentifikation ------------------------------------
                con.execute(
                    "INSERT INTO identified_subject "
                    "(subject_id, real_identity, confidence_code, "
                    " confidence_ordinal, basis, note, created_by, updated_by, "
                    " created_at, updated_at, audit_seq, created_audit_seq) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)",
                    (sid, real_identity, confidence_code, ordinal, basis,
                     note_norm, actor_id, actor_id, now, now),
                )
                state["created"] = True
                state["row_id"] = int(self._row(con, sid)["id"])
                # Payload: FAKTEN + Textlaengen, KEIN Freitext. 'created' wird
                # ATOMAR hier (im INSERT-Zweig) bestimmt — race-frei, weil unter
                # BEGIN IMMEDIATE. Ein Vorab-Lesen waere gegen konkurrierende
                # Schreiber unsicher gewesen.
                return {
                    "subject_id": sid,
                    "created": True,
                    "confidence_code": confidence_code,
                    "confidence_ordinal": ordinal,
                    "real_identity_len": self._tlen(real_identity),
                    "basis_len": self._tlen(basis),
                    "note_len": self._tlen(note_norm),
                }

            # --- Revision einer bestehenden Zuordnung ----------------------
            changes: Dict[str, Any] = {}
            if row["confidence_code"] != confidence_code:
                changes["confidence"] = {
                    "alt": row["confidence_code"], "neu": confidence_code,
                    "alt_ordinal": int(row["confidence_ordinal"]),
                    "neu_ordinal": ordinal,
                }
            # Freitext-Diffs NUR als Laengenaenderung (Sensibilitaetsregel).
            for field, new_val in (
                ("real_identity", real_identity),
                ("basis", basis),
                ("note", note_norm),
            ):
                old_val = row[field]
                if (old_val or "") != (new_val or ""):
                    changes["%s_len" % field] = {
                        "alt": self._tlen(old_val), "neu": self._tlen(new_val)}

            if not changes:
                raise CrossrefError(
                    "Keine Aenderung — die Werte entsprechen dem aktuellen "
                    "Stand (subject_id=%s)." % sid)

            con.execute(
                "UPDATE identified_subject SET real_identity = ?, "
                "confidence_code = ?, confidence_ordinal = ?, basis = ?, "
                "note = ?, updated_by = ?, updated_at = ? WHERE id = ?",
                (real_identity, confidence_code, ordinal, basis, note_norm,
                 actor_id, now, int(row["id"])),
            )
            state["row_id"] = int(row["id"])
            return {"subject_id": sid, "created": False, "changes": changes}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            # audit_seq (und bei Erstanlage created_audit_seq) mit der echten
            # Beleg-seq nachtragen — atomar in derselben Transaktion.
            if state["created"]:
                con.execute(
                    "UPDATE identified_subject SET audit_seq = ?, "
                    "created_audit_seq = ? WHERE id = ?",
                    (seq, seq, state["row_id"]),
                )
            else:
                con.execute(
                    "UPDATE identified_subject SET audit_seq = ? WHERE id = ?",
                    (seq, state["row_id"]),
                )

        # EIN Ereignistyp fuer Anlage UND Revision (Muster OnboardingRepo:
        # ONBOARDING_STEP_SET). Ob es eine Erstanlage war, steht als 'created'
        # im Payload — dort ATOMAR unter BEGIN IMMEDIATE bestimmt. Zwei
        # getrennte Typen haetten einen Vorab-Lesezugriff verlangt, der gegen
        # konkurrierende Schreiber nicht rennfrei waere; der Audit-Explorer kann
        # ueber das Payload-Feld 'created' weiterhin unterscheiden.
        seq = writer.audited_write(
            do_write=_w, event_type=EventType.SUBJECT_IDENTITY_SET,
            actor_id=actor_id, target_type="identified_subject",
            target_id=str(sid), meta=meta, after_audit=_after,
        )
        logger.info("identified_subject subject_id=%s -> %s (Beleg #%d).",
                    sid, confidence_code, seq)
        return {"subject_id": sid, "confidence_code": confidence_code,
                "audit_seq": seq, "created": state["created"]}

    # ------------------------------------------------------------------ intern
    @staticmethod
    def _as_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": int(row["id"]),
            "subject_id": int(row["subject_id"]),
            "real_identity": row["real_identity"],
            "confidence_code": row["confidence_code"],
            "confidence_ordinal": int(row["confidence_ordinal"]),
            "basis": row["basis"],
            "note": row["note"],
            "created_by": (int(row["created_by"])
                           if row["created_by"] is not None else None),
            "updated_by": (int(row["updated_by"])
                           if row["updated_by"] is not None else None),
            "created_at": int(row["created_at"]),
            "updated_at": int(row["updated_at"]),
            "audit_seq": int(row["audit_seq"]),
            "created_audit_seq": int(row["created_audit_seq"]),
        }

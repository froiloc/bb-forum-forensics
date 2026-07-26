# =============================================================================
# management/audit/evidence_audit_log.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A)
# =============================================================================
# Zweck (Build 533):
#   Hash-verkettetes, append-only Audit-Log INNERHALB von evidence_<uid>.db.
#   Es ist das Gegenstueck zu management/audit/audit_log.py (coordinator.db) —
#   gleiche Formel, gleiche Semantik, andere Datei und andere Tabelle.
#
# ── WARUM ES DIESE KLASSE UEBERHAUPT GIBT ────────────────────────────────────
#
#   Recherche 2026-07-26 (Belege im Text): In evidence_<uid>.db gab es bis
#   Build 532 KEINEN Beleg fuer fachliche Schreibvorgaenge. Das vollstaendige
#   Schema (db/evidence_db.py:231-459) fuehrt 16 Tabellen; die beiden mit
#   "Audit" im Kommentar — report_opened (:386) und lock_takeover_requests
#   (:358) — sind zweckfremd. save_annotation (db/evidence_db.py:847-949)
#   schreibt und committet direkt (:947), ohne Gateway und ohne Audit-Eintrag;
#   der Handler protokolliert nur ins Logfile (forensic_api/annotate.py:253-256).
#
#   Fuer die TATZEIT ist das nicht tragbar. Aus ihr wird eine Verjaehrungsfrist
#   gerechnet, und deren Folge ist unumkehrbar. Grundregel 1 des Projekts sagt:
#   kein Beleg darf je STILL uebersprungen werden.
#
# ── WARUM NICHT CoordinatorWriter/AuditLog WIEDERVERWENDEN ───────────────────
#
#   CoordinatorWriter.audited_write garantiert "Write und Beleg committen
#   gemeinsam oder gar nicht" (coordinator_writer.py:8-11, :83-96). Diese
#   Garantie beruht darauf, dass BEIDES in DERSELBEN Datei liegt und damit in
#   DERSELBEN SQLite-Transaktion. annotation_tatzeit liegt in
#   evidence_<uid>.db, audit_log in coordinator.db — zwei Dateien, zwei
#   Transaktionen. Die Garantie waere weg.
#
#   Die Alternative waere das Best-Effort-Muster der Gegenlese-Kommentare
#   (management/server/management_app.py:2316-2337): Fachwrite hier, Pruefspur
#   dort, und bei Fehlschlag nur ein logger-Eintrag (:2333-2335). Genau das ist
#   das stille Ueberspringen, das Grundregel 1 verbietet.
#   ENTSCHEIDUNG mc 2026-07-26: eigene Kette in der evidence-Datei.
#
# ── WAS GETEILT WIRD UND WAS NICHT (die wichtigste Zeile dieses Kopfes) ──────
#
#   GETEILT wird management/audit/hashing.py — canonical(), compute_row_hash()
#   und GENESIS_PREV_HASH. Das ist die EINGEFRORENE Formel, und sie darf
#   zwischen den beiden Ketten unter keinen Umstaenden auseinanderlaufen.
#   Deshalb wird sie NICHT kopiert, sondern importiert.
#
#   NICHT geteilt wird die Klasse AuditLog. Sie ist auf den Tabellennamen
#   'audit_log', auf target_id='coordinator' in der Genesis-Zeile und auf einen
#   FOREIGN KEY nach person(id) festgelegt. In evidence_<uid>.db gibt es keine
#   Tabelle 'person' — der FK waere nicht aufloesbar. AuditLog dafuer
#   umzubauen hiesse, die produktiv laufende Kette der coordinator.db
#   anzufassen; das Risiko steht in keinem Verhaeltnis zum Gewinn.
#
#   DIE DUPLIZIERUNGSGEFAHR IST GESEHEN UND ABGESICHERT: Test EA07 rechnet fuer
#   dieselbe Eingabe den row_hash BEIDER Klassen aus und vergleicht sie. Laufen
#   sie je auseinander, schlaegt er fehl. Ein Test, der die WIRKUNG prueft —
#   die Lehre aus den beiden Fehlern von Build 532.
#
# ── actor_id OHNE FOREIGN KEY, UND WARUM DAS RICHTIG IST ─────────────────────
#
#   actor_id ist eine person.id aus coordinator.db. Ein FK darauf ist aus einer
#   anderen SQLite-Datei technisch nicht darstellbar. Die Spalte ist deshalb
#   NULL-faehig deklariert wie im Original, aber der Schreibpfad
#   (EvidenceWriter) laesst KEINEN Eintrag ohne Handelnden zu: ein Beleg ohne
#   Handelnden ist kein Beleg (dieselbe Regel wie
#   forensic_api/results_endpoint.py:222-228). Die Pruefung liegt also im
#   Gateway, nicht im Schema — und der Test EA05 haelt sie fest.
#
# ── APPEND-ONLY-TRIGGER: LEITPLANKE, NICHT BEWEIS ────────────────────────────
#
#   Wie beim Original (audit_log.py:24-27): die Trigger verhindern das
#   versehentliche UPDATE/DELETE ueber den Anwendungspfad. Der eigentliche
#   BEWEIS der Unveraendertheit ist die Hash-Kette — wer mit Roh-SQLite an die
#   Datei geht, kann Trigger loeschen, aber nicht die Kette glattziehen, ohne
#   jeden Folge-Hash neu zu rechnen. verify_chain() deckt genau das auf.
#
# ── TRANSAKTIONSRAHMEN ───────────────────────────────────────────────────────
#
#   append() oeffnet KEINE eigene Transaktion (identisch zu audit_log.py:19-22).
#   Es MUSS innerhalb einer aktiven Schreibtransaktion laufen, damit Tip-Lesen
#   und Insert atomar und gegen Nebenlaeufigkeit serialisiert sind. Den Rahmen
#   liefert management/gateway/evidence_writer.py.
#
# Version: v0.8.533 · Build: 533 · 2026-07-26
# =============================================================================

import logging
import sqlite3
import time
from typing import Any, NamedTuple, Optional, Tuple

from management.audit.event_types import EventType
from management.audit.hashing import (
    GENESIS_PREV_HASH,
    canonical,
    compute_row_hash,
)

logger = logging.getLogger(__name__)


class EvidenceAuditLogError(Exception):
    """Fehler in der evidence-Audit-Kette (Kette nicht initialisiert, Typ unbekannt)."""


class EvidenceVerifyResult(NamedTuple):
    """Ergebnis einer Ketten-Integritaetspruefung in evidence_<uid>.db."""

    ok: bool
    first_bad_seq: Optional[int]
    detail: str


class EvidenceAuditLog:
    """Append-only Hash-Kette auf der Tabelle evidence_audit_log."""

    #: Tabellenname als Klassenkonstante — die Migration m003 und die Tests
    #  beziehen sich darauf, damit der Name an EINER Stelle steht.
    TABLE: str = "evidence_audit_log"

    # --- DDL: Tabelle (Spaltensatz ab Zeile 1 EINGEFROREN) -------------------
    #   Spaltensatz und Reihenfolge sind ABSICHTLICH deckungsgleich mit
    #   audit_log (audit_log.py:63-77) — bis auf den fehlenden FOREIGN KEY
    #   (s. Kopf). Die Formel in hashing.py haengt an dieser Feldmenge; eine
    #   Abweichung wuerde die beiden Ketten unvergleichbar machen.
    DDL_TABLE = """
    CREATE TABLE IF NOT EXISTS evidence_audit_log (
        seq          INTEGER PRIMARY KEY AUTOINCREMENT,
        ts           INTEGER NOT NULL,
        actor_id     INTEGER,
        event_type   TEXT    NOT NULL,
        target_type  TEXT,
        target_id    TEXT,
        content      TEXT    NOT NULL,
        meta         TEXT    NOT NULL DEFAULT '',
        prev_hash    TEXT    NOT NULL,
        row_hash     TEXT    NOT NULL
    )
    """

    # --- DDL: Append-only-Trigger (Leitplanke) -------------------------------
    DDL_TRIG_UPDATE = """
    CREATE TRIGGER IF NOT EXISTS evidence_audit_log_no_update
        BEFORE UPDATE ON evidence_audit_log
        BEGIN SELECT RAISE(ABORT,
            'evidence_audit_log ist append-only (UPDATE unterbunden)'); END
    """
    DDL_TRIG_DELETE = """
    CREATE TRIGGER IF NOT EXISTS evidence_audit_log_no_delete
        BEFORE DELETE ON evidence_audit_log
        BEGIN SELECT RAISE(ABORT,
            'evidence_audit_log ist append-only (DELETE unterbunden)'); END
    """

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    # ------------------------------------------------------------------ Lesen
    def _rows(self, sql: str, args: tuple = ()):
        """
        Fuehrt ein SELECT mit benanntem Spaltenzugriff aus, OHNE die
        row_factory der Verbindung anzufassen.

        WARUM DIESER UMWEG (ein echter Fehler, gefunden am 2026-07-26):
        Der erste Entwurf setzte im Konstruktor 'con.row_factory =
        sqlite3.Row' — so, wie AuditLog es tut (audit_log.py:100-101). Dort ist
        das unschaedlich, weil jene Verbindungen ohnehin mit row_factory=Row
        geoeffnet werden. HIER NICHT: die evidence-Verbindung gehoert dem
        forensischen Server und wird von rund 150 Stellen mitbenutzt. Ein
        Konstruktoraufruf haette deren Lesart global umgestellt.
        Aufgefallen ist es, weil TZ10/TZ11 aus Build 532 fehlschlugen — ihre
        Verbindung liefert Tupel, und nach dem Lauf von m003 plötzlich Rows.
        Ein Test aus einem fremden Build hat also einen Nebenwirkungsfehler
        gefunden, den kein Test dieses Builds gesucht haette.

        Dieselbe Ueberlegung wie bei isolation_level im EvidenceWriter: die
        Verbindung wird geliehen, nicht genommen. Der Cursor dagegen gehoert
        uns — auf ihm ist die row_factory folgenlos.
        """
        cur = self._con.cursor()
        cur.row_factory = sqlite3.Row
        cur.execute(sql, args)
        return cur.fetchall()

    # ------------------------------------------------------------------ Schema
    @classmethod
    def create_schema(cls, con: sqlite3.Connection) -> None:
        """Legt Tabelle und Append-only-Trigger an (idempotent)."""
        con.execute(cls.DDL_TABLE)
        con.execute(cls.DDL_TRIG_UPDATE)
        con.execute(cls.DDL_TRIG_DELETE)
        logger.debug("evidence_audit_log-Schema sichergestellt.")

    # --------------------------------------------------------------------- Tip
    def tip(self) -> Tuple[str, int]:
        """
        Liefert (row_hash, seq) der letzten Zeile.
        Leere Kette -> (GENESIS_PREV_HASH, 0).
        """
        rows = self._rows(
            "SELECT seq, row_hash FROM evidence_audit_log "
            "ORDER BY seq DESC LIMIT 1")
        if not rows:
            return (GENESIS_PREV_HASH, 0)
        return (rows[0]["row_hash"], int(rows[0]["seq"]))

    # ----------------------------------------------------------------- Genesis
    def write_genesis(self, payload: Any, *, ts: Optional[int] = None) -> int:
        """
        Schreibt die Genesis-Zeile (seq=1) als Kettenanker.
        Nur in eine LEERE Kette zulaessig. Muss in aktiver Transaktion laufen.

        target_id ist 'evidence' (nicht 'coordinator'). Damit ist einer
        einzelnen Zeile ohne Kenntnis ihrer Herkunftsdatei anzusehen, zu
        welcher Kette sie gehoert — wichtig, sobald jemand Ausschnitte beider
        Ketten nebeneinanderlegt.
        """
        count = self._rows(
            "SELECT COUNT(*) AS c FROM evidence_audit_log")[0]["c"]
        if count != 0:
            raise EvidenceAuditLogError(
                "Genesis nur in leere Kette zulaessig (bereits %d Eintraege)."
                % count
            )
        return self._insert(
            seq=1,
            ts=ts if ts is not None else int(time.time()),
            actor_id=None,
            event_type=EventType.GENESIS,
            target_type="chain",
            target_id="evidence",
            payload=payload,
            meta=None,
            prev_hash=GENESIS_PREV_HASH,
        )

    # ------------------------------------------------------------------ Append
    def append(
        self,
        *,
        event_type: str,
        actor_id: Optional[int],
        target_type: Optional[str],
        target_id: Optional[str],
        payload: Any,
        meta: Optional[Any] = None,
        ts: Optional[int] = None,
    ) -> int:
        """
        Haengt ein Ereignis verkettet an. Muss in aktiver Schreibtransaktion
        (BEGIN IMMEDIATE) des aufrufenden Vorgangs laufen.
        Gibt die seq der neuen Zeile zurueck.
        """
        if not EventType.is_valid(event_type):
            raise EvidenceAuditLogError("Unbekannter event_type: %r" % event_type)
        prev_hash, prev_seq = self.tip()
        if prev_seq == 0:
            raise EvidenceAuditLogError(
                "Kette nicht initialisiert — m003 nicht angewandt "
                "(write_genesis fehlt)."
            )
        return self._insert(
            seq=prev_seq + 1,
            ts=ts if ts is not None else int(time.time()),
            actor_id=actor_id,
            event_type=event_type,
            target_type=target_type,
            target_id=target_id,
            payload=payload,
            meta=meta,
            prev_hash=prev_hash,
        )

    # ------------------------------------------------------------------ Insert
    def _insert(
        self,
        *,
        seq: int,
        ts: int,
        actor_id: Optional[int],
        event_type: str,
        target_type: Optional[str],
        target_id: Optional[str],
        payload: Any,
        meta: Optional[Any],
        prev_hash: str,
    ) -> int:
        # content/meta werden als KANONISCHE Strings gespeichert — exakt die
        # Form, die auch gehasht wird. verify_chain() rechnet daraus 1:1 nach.
        content_canonical = canonical(payload)
        meta_canonical = canonical(meta)  # None -> ""
        row_hash = compute_row_hash(
            prev_hash,
            seq,
            ts,
            actor_id,
            event_type,
            target_type,
            target_id,
            content_canonical,
            meta_canonical,
        )
        # Explizite seq (statt AUTOINCREMENT-Automatik), damit die gehashte seq
        # garantiert der gespeicherten seq entspricht.
        self._con.execute(
            "INSERT INTO evidence_audit_log "
            "(seq, ts, actor_id, event_type, target_type, target_id, "
            " content, meta, prev_hash, row_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                seq,
                ts,
                actor_id,
                event_type,
                target_type,
                target_id,
                content_canonical,
                meta_canonical,
                prev_hash,
                row_hash,
            ),
        )
        logger.debug(
            "evidence_audit_log append: seq=%d type=%s target=%s/%s",
            seq, event_type, target_type, target_id,
        )
        return seq

    # ------------------------------------------------------------------ Verify
    def verify_chain(self) -> EvidenceVerifyResult:
        """
        Rechnet die gesamte Kette nach und prueft die Verkettung.
        Liefert EvidenceVerifyResult(ok, first_bad_seq, detail).
        Reiner Lesevorgang (schreibt selbst keinen Beleg).
        """
        expected_prev = GENESIS_PREV_HASH
        rows = self._rows(
            "SELECT seq, ts, actor_id, event_type, target_type, target_id, "
            "       content, meta, prev_hash, row_hash "
            "FROM evidence_audit_log ORDER BY seq ASC")

        for r in rows:
            if r["prev_hash"] != expected_prev:
                return EvidenceVerifyResult(
                    False, int(r["seq"]),
                    "prev_hash-Bruch bei seq=%d" % int(r["seq"]),
                )
            recomputed = compute_row_hash(
                r["prev_hash"],
                int(r["seq"]),
                int(r["ts"]),
                None if r["actor_id"] is None else int(r["actor_id"]),
                r["event_type"],
                r["target_type"],
                r["target_id"],
                r["content"],
                r["meta"],
            )
            if recomputed != r["row_hash"]:
                return EvidenceVerifyResult(
                    False, int(r["seq"]),
                    "row_hash stimmt nicht bei seq=%d" % int(r["seq"]),
                )
            expected_prev = r["row_hash"]

        return EvidenceVerifyResult(
            True, None, "Kette in Ordnung (%d Zeilen)." % len(rows)
        )

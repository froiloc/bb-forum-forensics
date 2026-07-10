# =============================================================================
# management/audit/audit_log.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Hash-verkettetes, append-only Audit-Log in coordinator.db (Idee 13).
#   Jede Zeile enthält den row_hash der Vorzeile (prev_hash); jede Manipulation
#   an einer Zeile bricht die Kette ab diesem Punkt und ist über verify_chain()
#   nachweisbar. Das ist die forensische Manipulationssicherung des Management-
#   Interfaces für die spätere Gerichtsverwertbarkeit.
#
# Verantwortlichkeiten dieser Klasse:
#   - Schema-Erzeugung (Tabelle + Append-only-Trigger)        -> create_schema()
#   - Genesis-Zeile (Kettenanker)                             -> write_genesis()
#   - Anhängen neuer Ereignisse (verkettet)                   -> append()
#   - Integritätsprüfung der gesamten Kette                   -> verify_chain()
#
# Wichtig (Beleg: Bauplan B7 v0.2 §2.4/§2.6):
#   append() öffnet KEINE eigene Transaktion. Es MUSS innerhalb einer aktiven
#   Schreibtransaktion (BEGIN IMMEDIATE) des aufrufenden Vorgangs laufen, damit
#   Tip-Lesen + Insert atomar und gegen Nebenläufigkeit serialisiert sind.
#   Den Transaktionsrahmen liefern MigrationRunner bzw. CoordinatorWriter.
#
#   Die Append-only-Trigger sind eine Leitplanke gegen versehentliche/zufällige
#   Änderung über den Anwendungspfad. Der eigentliche BEWEIS der Unverändert-
#   barkeit ist die Hash-Kette (ein Admin mit Roh-SQLite-Zugriff kann Trigger
#   löschen — die Kette deckt genau das auf).
#
# Version: v0.7.306 · Build: 306 · 2026-07-01
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


class AuditLogError(Exception):
    """Fehler im Audit-Log (z. B. Kette nicht initialisiert, unbekannter Typ)."""


class VerifyResult(NamedTuple):
    """Ergebnis einer Ketten-Integritätsprüfung."""

    ok: bool
    first_bad_seq: Optional[int]
    detail: str


class AuditLog:
    """Append-only Hash-Kette auf der Tabelle audit_log in coordinator.db."""

    # --- DDL: Tabelle (Spaltensatz ab Zeile 1 EINGEFROREN) -------------------
    DDL_TABLE = """
    CREATE TABLE IF NOT EXISTS audit_log (
        seq          INTEGER PRIMARY KEY AUTOINCREMENT,
        ts           INTEGER NOT NULL,
        actor_id     INTEGER,
        event_type   TEXT    NOT NULL,
        target_type  TEXT,
        target_id    TEXT,
        content      TEXT    NOT NULL,
        meta         TEXT    NOT NULL DEFAULT '',
        prev_hash    TEXT    NOT NULL,
        row_hash     TEXT    NOT NULL,
        FOREIGN KEY(actor_id) REFERENCES person(id)
    )
    """
    # Build 342: FK-Ziel investigators -> person (Entitaets-Rename, Migration
    # M005). Nur der Referenzname aendert sich; der EINGEFRORENE Spaltensatz
    # (Grundlage der Hash-Kette) bleibt unveraendert. In der Migrationskette
    # entsteht audit_log bei M001 (person existiert dann noch als
    # 'investigators') unter FK OFF unkritisch; M005 zieht die Live-Referenz
    # ohnehin nach.

    # --- DDL: Append-only-Trigger (Leitplanke) -------------------------------
    DDL_TRIG_UPDATE = """
    CREATE TRIGGER IF NOT EXISTS audit_log_no_update
        BEFORE UPDATE ON audit_log
        BEGIN SELECT RAISE(ABORT, 'audit_log ist append-only (UPDATE unterbunden)'); END
    """
    DDL_TRIG_DELETE = """
    CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
        BEFORE DELETE ON audit_log
        BEGIN SELECT RAISE(ABORT, 'audit_log ist append-only (DELETE unterbunden)'); END
    """

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        # Benannter Spaltenzugriff (Projektkonvention).
        self._con.row_factory = sqlite3.Row

    # ------------------------------------------------------------------ Schema
    @classmethod
    def create_schema(cls, con: sqlite3.Connection) -> None:
        """Legt Tabelle und Append-only-Trigger an (idempotent)."""
        con.execute(cls.DDL_TABLE)
        con.execute(cls.DDL_TRIG_UPDATE)
        con.execute(cls.DDL_TRIG_DELETE)
        logger.debug("audit_log-Schema sichergestellt.")

    # --------------------------------------------------------------------- Tip
    def tip(self) -> Tuple[str, int]:
        """
        Liefert (row_hash, seq) der letzten Zeile.
        Leere Kette -> (GENESIS_PREV_HASH, 0).
        """
        row = self._con.execute(
            "SELECT seq, row_hash FROM audit_log ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return (GENESIS_PREV_HASH, 0)
        return (row["row_hash"], int(row["seq"]))

    # ----------------------------------------------------------------- Genesis
    def write_genesis(
        self, payload: Any, *, ts: Optional[int] = None
    ) -> int:
        """
        Schreibt die Genesis-Zeile (seq=1) als Kettenanker.
        Nur in eine LEERE Kette zulässig. Muss in aktiver Transaktion laufen.
        """
        count = self._con.execute(
            "SELECT COUNT(*) AS c FROM audit_log"
        ).fetchone()["c"]
        if count != 0:
            raise AuditLogError(
                "Genesis nur in leere Kette zulässig (bereits %d Einträge)." % count
            )
        return self._insert(
            seq=1,
            ts=ts if ts is not None else int(time.time()),
            actor_id=None,
            event_type=EventType.GENESIS,
            target_type="chain",
            target_id="coordinator",
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
        Hängt ein Ereignis verkettet an. Muss in aktiver Schreibtransaktion
        (BEGIN IMMEDIATE) des aufrufenden Vorgangs laufen.
        Gibt die seq der neuen Zeile zurück.
        """
        if not EventType.is_valid(event_type):
            raise AuditLogError("Unbekannter event_type: %r" % event_type)
        prev_hash, prev_seq = self.tip()
        if prev_seq == 0:
            raise AuditLogError(
                "Kette nicht initialisiert — write_genesis() fehlt."
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
            "INSERT INTO audit_log "
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
            "audit_log append: seq=%d type=%s target=%s/%s",
            seq, event_type, target_type, target_id,
        )
        return seq

    # ------------------------------------------------------------------ Verify
    def verify_chain(self) -> VerifyResult:
        """
        Rechnet die gesamte Kette nach und prüft die Verkettung.
        Liefert VerifyResult(ok, first_bad_seq, detail).
        Reiner Lesevorgang (schreibt selbst kein Audit).
        """
        expected_prev = GENESIS_PREV_HASH
        rows = self._con.execute(
            "SELECT seq, ts, actor_id, event_type, target_type, target_id, "
            "       content, meta, prev_hash, row_hash "
            "FROM audit_log ORDER BY seq ASC"
        ).fetchall()

        for r in rows:
            if r["prev_hash"] != expected_prev:
                return VerifyResult(
                    False, int(r["seq"]),
                    "prev_hash-Bruch bei seq=%d" % int(r["seq"]),
                )
            recomputed = compute_row_hash(
                r["prev_hash"],
                int(r["seq"]),
                int(r["ts"]),
                r["actor_id"],
                r["event_type"],
                r["target_type"],
                r["target_id"],
                r["content"],
                r["meta"],
            )
            if recomputed != r["row_hash"]:
                return VerifyResult(
                    False, int(r["seq"]),
                    "row_hash-Abweichung bei seq=%d (Inhalt manipuliert?)"
                    % int(r["seq"]),
                )
            expected_prev = r["row_hash"]

        return VerifyResult(True, None, "OK (%d Einträge)" % len(rows))

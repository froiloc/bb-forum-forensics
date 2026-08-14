# =============================================================================
# management/migration_fleet/ledger.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# MigrationLedger — append-only, hash-verketteter Writer fuer migration_runs
# (Build 318, Scheibe 2/4 der Migrations-Ausfuehrung).
#
#   Zweck: Der Migrationsvorgang SELBST ist forensisch bedeutsam und muss
#   manipulationssicher belegt sein. Jeder Lauf hinterlaesst unveraenderbare,
#   hash-verkettete Eintraege (analog audit_log). Die Kette macht nachtraegliche
#   Aenderung/Loeschung erkennbar (verify_chain).
#
#   EVENT-PER-ROW (nicht ein Zeile pro Lauf): Da die Kette append-only ist,
#   wird ein Lauf durch ZWEI Eintraege belegt —
#     1. record_start()  -> status 'started'  (VOR dem Anfassen der Daten;
#        ein Absturz danach hinterlaesst so eine Spur des Vorhabens)
#     2. record_result() -> status 'ok'|'failed'|'restored' (nach Abschluss)
#   Beide tragen dieselben identifizierenden Felder; korreliert wird ueber
#   (db_kind, uid, to_version) — bei vorwaerts-only erreicht jede Instanz jede
#   Zielversion hoechstens einmal, die Korrelation ist also eindeutig.
#
#   Das migration_runs-Schema stammt unveraendert aus Build 316; hier kommt
#   ausschliesslich der SCHREIBER hinzu (kein Schema-Eingriff). Build 318 ist
#   ISOLIERT: kein Executor, keine echte Migration, keine Evidenz — nur der
#   Writer + Verifikation + Tests. Die Verdrahtung folgt in Build 319.
#
#   Hash-Konstruktion: identisch zu audit_log (Feldtrenner 0x1F, SHA256,
#   GENESIS_PREV_HASH aus management/audit/hashing.py) — jedoch ueber die
#   ledger-eigenen Felder. Die Formel ist EINGEFROREN (Aenderung wuerde
#   bestehende Ketten ungueltig machen).
#
# Beleg: management/audit/hashing.py (GENESIS_PREV_HASH, 0x1F/SHA256-Formel),
#        management/migration_fleet/migration_db.py (migration_runs-Schema),
#        Datenmigrationsleitfaden_AIW.md v0.2 Paragraph 6.3, mc 2026-07-03.
# Version: v0.8.723 · Build: 723 · 2026-08-14 (Terminal-Status restore_refused)
# =============================================================================

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from typing import List, Optional

from management.audit.hashing import GENESIS_PREV_HASH

#: Feldtrenner (ASCII Unit Separator) — gleiche Konstruktion wie audit_log.
_USEP = "\x1f"

#: Zulaessige Abschluss-Status (Terminal-Events).
#:
#: BUILD 723 (Vorgang 69ede1c7) — 'restore_refused' kommt hinzu.
#:
#: WARUM EIN NEUER WERT UND NICHT EINE NOTIZ: migration_runs hat KEINE
#: Freitextspalte (Schema Build 316, migration_db.py). Der Status ist der
#: einzige Kanal, ueber den sich im Laufbuch ueberhaupt etwas sagen laesst —
#: und dass ein Rueckweg NICHT gelaufen ist, ist die wichtigste Tatsache eines
#: solchen Laufs. Sie darf nicht bloss auf der Konsole stehen, die niemand
#: aufbewahrt (Grundregel 1).
#:
#: WARUM DAS DIE KETTE NICHT BRICHT: Die Hash-Formel (_row_hash) ist
#: unveraendert, sie nimmt den Status als Zeichenkette entgegen. Bestehende
#: Zeilen werden nicht angefasst, ihre Hashes bleiben gueltig; der neue Wert
#: kann nur in NEUEN Zeilen auftreten. Die Tabelle hat auf 'status' KEINEN
#: CHECK-Constraint (nachgesehen in migration_db.py, _DDL_RUNS) — es ist also
#: auch keine Schema-Aenderung und keine Migration noetig.
#:
#: WAS DABEI NICHT VERGESSEN WERDEN DARF: interrupted_runs() zaehlt einen Lauf
#: nur dann als abgeschlossen, wenn ein Terminal-Event vorliegt. Ohne
#: Aufnahme in die dortige IN-Liste waere ein verweigerter Rueckweg als
#: 'unterbrochener Lauf' erschienen — eine falsche Auskunft ueber einen Lauf,
#: der sehr wohl zu Ende gefuehrt und protokolliert wurde.
_TERMINAL_STATUS = ("ok", "failed", "restored", "restore_refused")


def _row_hash(
    prev_hash: str, *, seq: int, db_kind: str, uid: Optional[int],
    from_version: int, to_version: int, started_at: int,
    finished_at: Optional[int], status: str, pre_sha512: Optional[str],
    post_sha512: Optional[str], backup_path: Optional[str],
    operator: Optional[str], verifier: Optional[str],
) -> str:
    """
    EINGEFRORENE Formel:
        sha256(prev_hash 0x1F seq 0x1F db_kind 0x1F uid 0x1F from_version 0x1F
               to_version 0x1F started_at 0x1F finished_at 0x1F status 0x1F
               pre_sha512 0x1F post_sha512 0x1F backup_path 0x1F operator 0x1F
               verifier)
    NULL/None-Felder gehen als "" ein. Deckt ALLE inhaltstragenden Spalten ab,
    sodass jede nachtraegliche Aenderung die Kette bricht.
    """
    parts = [
        prev_hash, str(seq), db_kind,
        "" if uid is None else str(uid),
        str(from_version), str(to_version), str(started_at),
        "" if finished_at is None else str(finished_at),
        status,
        pre_sha512 or "", post_sha512 or "", backup_path or "",
        operator or "", verifier or "",
    ]
    return hashlib.sha256(_USEP.join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LedgerVerifyResult:
    ok: bool
    first_bad_seq: Optional[int]
    detail: str


@dataclass(frozen=True)
class InterruptedRun:
    db_kind: str
    uid: Optional[int]
    to_version: int
    started_at: int
    start_seq: int


class MigrationLedger:
    """
    Append-only, hash-verketteter Schreiber/Leser fuer migration_runs.
    Bietet NUR Anhaengen (record_start/record_result) und Lesen — kein
    UPDATE/DELETE (Unveraenderbarkeit).
    """

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    # ------------------------------------------------------------- intern
    def _next_seq(self) -> int:
        row = self._con.execute("SELECT MAX(seq) FROM migration_runs").fetchone()
        return 1 if row[0] is None else int(row[0]) + 1

    def _last_hash(self) -> str:
        row = self._con.execute(
            "SELECT row_hash FROM migration_runs ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return GENESIS_PREV_HASH if row is None else row[0]

    def _append(self, **f) -> int:
        seq = self._next_seq()
        prev = self._last_hash()
        rh = _row_hash(prev, seq=seq, **f)
        self._con.execute(
            "INSERT INTO migration_runs (seq, db_kind, uid, from_version, "
            "to_version, started_at, finished_at, status, pre_sha512, "
            "post_sha512, backup_path, operator, verifier, prev_hash, row_hash) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (seq, f["db_kind"], f["uid"], f["from_version"], f["to_version"],
             f["started_at"], f["finished_at"], f["status"], f["pre_sha512"],
             f["post_sha512"], f["backup_path"], f["operator"], f["verifier"],
             prev, rh),
        )
        return seq

    # ------------------------------------------------------------- schreiben
    def record_start(self, *, db_kind: str, uid: Optional[int],
                     from_version: int, to_version: int,
                     started_at: Optional[int] = None,
                     pre_sha512: Optional[str] = None,
                     backup_path: Optional[str] = None,
                     operator: Optional[str] = None) -> int:
        """Beginn eines Laufs (status 'started'), VOR dem Anfassen der Daten."""
        started_at = int(time.time()) if started_at is None else int(started_at)
        return self._append(
            db_kind=db_kind, uid=uid, from_version=from_version,
            to_version=to_version, started_at=started_at, finished_at=None,
            status="started", pre_sha512=pre_sha512, post_sha512=None,
            backup_path=backup_path, operator=operator, verifier=None)

    def record_result(self, *, db_kind: str, uid: Optional[int],
                      from_version: int, to_version: int, started_at: int,
                      status: str, finished_at: Optional[int] = None,
                      post_sha512: Optional[str] = None,
                      backup_path: Optional[str] = None,
                      operator: Optional[str] = None,
                      verifier: Optional[str] = None) -> int:
        """
        Abschluss eines Laufs
        (status 'ok'|'failed'|'restored'|'restore_refused').

        'restore_refused' (Build 723): Die Migration ist gescheitert UND der
        Rueckweg ist nicht gelaufen. Er wird IMMER zusaetzlich zu 'failed'
        geschrieben, nie an dessen Stelle — 'failed' sagt, was mit der
        Migration war, 'restore_refused' sagt, was mit der Wiederherstellung
        war. Das sind zwei Tatsachen.
        """
        if status not in _TERMINAL_STATUS:
            raise ValueError(
                "Ungueltiger Abschluss-Status %r (erlaubt: %s)"
                % (status, ", ".join(_TERMINAL_STATUS)))
        finished_at = int(time.time()) if finished_at is None else int(finished_at)
        return self._append(
            db_kind=db_kind, uid=uid, from_version=from_version,
            to_version=to_version, started_at=int(started_at),
            finished_at=finished_at, status=status, pre_sha512=None,
            post_sha512=post_sha512, backup_path=backup_path,
            operator=operator, verifier=verifier)

    # ------------------------------------------------------------- lesen
    def list_runs(self, db_kind: Optional[str] = None,
                  uid: Optional[int] = None) -> List[sqlite3.Row]:
        sql = ("SELECT * FROM migration_runs")
        clauses, params = [], []
        if db_kind is not None:
            clauses.append("db_kind = ?"); params.append(db_kind)
        if uid is not None:
            clauses.append("IFNULL(uid,-1) = ?"); params.append(uid)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY seq"
        old_factory = self._con.row_factory
        self._con.row_factory = sqlite3.Row
        try:
            return self._con.execute(sql, params).fetchall()
        finally:
            self._con.row_factory = old_factory

    def verify_chain(self) -> LedgerVerifyResult:
        """
        Rechnet die gesamte Kette nach. Reiner Lesevorgang. Liefert
        LedgerVerifyResult(ok, first_bad_seq, detail).
        """
        expected_prev = GENESIS_PREV_HASH
        rows = self._con.execute(
            "SELECT seq, db_kind, uid, from_version, to_version, started_at, "
            "finished_at, status, pre_sha512, post_sha512, backup_path, "
            "operator, verifier, prev_hash, row_hash FROM migration_runs "
            "ORDER BY seq ASC"
        ).fetchall()
        for r in rows:
            (seq, db_kind, uid, fromv, tov, started, finished, status, pre,
             post, bkp, op, ver, prev_hash, row_hash) = r
            if prev_hash != expected_prev:
                return LedgerVerifyResult(False, seq, "prev_hash-Bruch bei seq %d" % seq)
            recomputed = _row_hash(
                prev_hash, seq=seq, db_kind=db_kind, uid=uid, from_version=fromv,
                to_version=tov, started_at=started, finished_at=finished,
                status=status, pre_sha512=pre, post_sha512=post,
                backup_path=bkp, operator=op, verifier=ver)
            if recomputed != row_hash:
                return LedgerVerifyResult(False, seq, "row_hash-Mismatch bei seq %d" % seq)
            expected_prev = row_hash
        return LedgerVerifyResult(True, None, "ok")

    def interrupted_runs(self) -> List[InterruptedRun]:
        """
        'started'-Events ohne spaeteres Terminal-Event fuer dieselbe
        (db_kind, uid, to_version) — unterbrochene/abgestuerzte Laeufe.
        """
        rows = self._con.execute(
            "SELECT s.db_kind, s.uid, s.to_version, s.started_at, s.seq "
            "FROM migration_runs s "
            "WHERE s.status='started' AND NOT EXISTS ("
            "  SELECT 1 FROM migration_runs t "
            # Build 723: 'restore_refused' gehoert hier dazu — siehe die
            # Begruendung bei _TERMINAL_STATUS. Die Liste wird aus der
            # Konstanten gebaut, damit sie nicht wieder auseinanderlaufen
            # kann; genau dieses Auseinanderlaufen war die Gefahr.
            "  WHERE t.status IN (%s) "
            % ",".join("'%s'" % s for s in _TERMINAL_STATUS) +
            "    AND t.db_kind = s.db_kind "
            "    AND IFNULL(t.uid,-1) = IFNULL(s.uid,-1) "
            "    AND t.to_version = s.to_version "
            "    AND t.seq > s.seq) "
            "ORDER BY s.seq"
        ).fetchall()
        return [InterruptedRun(db_kind=r[0], uid=r[1], to_version=r[2],
                               started_at=r[3], start_seq=r[4]) for r in rows]

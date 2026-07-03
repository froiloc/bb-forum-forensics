# =============================================================================
# management/migration_fleet/harness/integrity.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# IntegrityChecker — Phase-2-Primitive: PRAGMA integrity_check und
# PRAGMA foreign_key_check. Rein lesend.
#
#   Ist eine Datei so beschaedigt, dass schon die Abfrage scheitert, wird das
#   als Integritaetsfehler gemeldet (kein stiller Absturz, Grundregel 1).
#
# Beleg: Datenmigrationsleitfaden_AIW.md v0.2 §3 Phase 2, mc 2026-07-03.
# Version: v0.7.317 · Build: 317 · 2026-07-03
# =============================================================================

import sqlite3
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class IntegrityResult:
    ok: bool
    messages: List[str]


@dataclass(frozen=True)
class FkViolation:
    table: str
    rowid: object      # kann bei WITHOUT ROWID NULL sein
    parent: str
    fkid: int


class IntegrityChecker:
    """PRAGMA integrity_check / foreign_key_check als reine Lesepruefungen."""

    @staticmethod
    def integrity_check(path: str) -> IntegrityResult:
        con = None
        try:
            con = sqlite3.connect(path)
            rows = con.execute("PRAGMA integrity_check").fetchall()
            msgs = [str(r[0]) for r in rows]
            ok = (len(msgs) == 1 and msgs[0] == "ok")
            return IntegrityResult(ok=ok, messages=([] if ok else msgs))
        except sqlite3.DatabaseError as exc:
            # Datei so beschaedigt, dass die Pruefung selbst scheitert.
            return IntegrityResult(ok=False, messages=["DatabaseError: %s" % exc])
        finally:
            if con is not None:
                con.close()

    @staticmethod
    def foreign_key_check(path: str) -> List[FkViolation]:
        con = None
        try:
            con = sqlite3.connect(path)
            rows = con.execute("PRAGMA foreign_key_check").fetchall()
            # Zeilenformat: (table, rowid, parent, fkid)
            return [FkViolation(table=r[0], rowid=r[1], parent=r[2], fkid=r[3])
                    for r in rows]
        finally:
            if con is not None:
                con.close()

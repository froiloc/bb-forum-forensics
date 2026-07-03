# =============================================================================
# management/migration_fleet/harness/harness.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# MigrationHarness — duenne Fassade, die die Primitive zu zwei Operationen
# buendelt:
#   snapshot(path)                      -> DbSnapshot  (Messung VOR der Migration)
#   verify_against(path, pre, deltas)   -> VerifyReport (Pruefung NACH der Migration)
#
#   Die Fassade TRIFFT KEINE ENTSCHEIDUNG und fuehrt NICHTS aus — sie liefert
#   nur den aggregierten Report. Stop-and-Flag/Restore ist Sache des Executors
#   (Build 319). In Build 317 wird der Ablauf snapshot -> (Migration) ->
#   verify_against NICHT durchlaufen; hier existieren nur die Bausteine + Tests.
#
# Beleg: Bauplan Migrations-Ausfuehrung v0.1 §3.2/§3.3, mc 2026-07-03.
# Version: v0.7.317 · Build: 317 · 2026-07-03
# =============================================================================

from dataclasses import dataclass
from typing import Dict, List, Optional

from management.migration_fleet.harness.blob import BlobReport, BlobVerifier
from management.migration_fleet.harness.hashing import sha512_file
from management.migration_fleet.harness.integrity import (
    FkViolation,
    IntegrityChecker,
    IntegrityResult,
)
from management.migration_fleet.harness.rowcount import (
    RowcountReport,
    RowcountVerifier,
)


@dataclass(frozen=True)
class DbSnapshot:
    path: str
    sha512: str
    rowcounts: Dict[str, int]
    blob_digests: Dict[str, str]
    integrity: IntegrityResult
    fk_violations: List[FkViolation]


@dataclass(frozen=True)
class VerifyReport:
    ok: bool
    integrity: IntegrityResult
    fk_violations: List[FkViolation]
    rowcount: RowcountReport
    blob: BlobReport


class MigrationHarness:
    """Buendelt Backup-fremde Verifikationsprimitive (rein lesend)."""

    @staticmethod
    def snapshot(path: str) -> DbSnapshot:
        return DbSnapshot(
            path=path,
            sha512=sha512_file(path),
            rowcounts=RowcountVerifier.table_rowcounts(path),
            blob_digests=BlobVerifier.blob_digests(path),
            integrity=IntegrityChecker.integrity_check(path),
            fk_violations=IntegrityChecker.foreign_key_check(path),
        )

    @staticmethod
    def verify_against(path: str, pre: DbSnapshot,
                       expected_deltas: Optional[Dict[str, int]] = None
                       ) -> VerifyReport:
        integrity = IntegrityChecker.integrity_check(path)
        fk = IntegrityChecker.foreign_key_check(path)
        rowcount = RowcountVerifier.compare(
            pre.rowcounts, RowcountVerifier.table_rowcounts(path),
            expected_deltas)
        blob = BlobVerifier.compare(
            pre.blob_digests, BlobVerifier.blob_digests(path))
        ok = integrity.ok and not fk and rowcount.ok and blob.ok
        return VerifyReport(ok=ok, integrity=integrity, fk_violations=fk,
                            rowcount=rowcount, blob=blob)

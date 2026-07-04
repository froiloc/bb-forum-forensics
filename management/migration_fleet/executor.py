# =============================================================================
# management/migration_fleet/executor.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# FleetExecutor — Migrations-Ausfuehrung Scheibe 3/4 (Build 319).
#
#   Verbindet die Bausteine zu einem SAFE-BY-DESIGN-Vorgang je DB-Instanz:
#     Pre-Snapshot (Harness 317) -> Pflicht-Backup (317) -> Ledger-Start (318)
#     -> Migration (runner, audit=None fuer Beweis-DBs) -> Verify (317)
#     -> Erfolg: Ledger 'ok' + db_registry aktualisieren
#     -> Fehler/Ausnahme: RESTORE aus Backup + Ledger 'failed'+'restored' + STOP
#
#   GATING (mehrschichtig):
#     - dry_run=True als DEFAULT (echte Ausfuehrung nur bei dry_run=False)
#     - ohne backup_dir -> Ausfuehrung wird VERWEIGERT (Pflicht-Backup)
#     - prozedural: echte Ausfuehrung nur in der Vier-Phasen-Zeremonie +
#       Vieraugen (Leitfaden); der gefuehrte Companion (Build 320) erzwingt das.
#
#   SAFE-BY-DESIGN: Pflicht-Backup + Verify + Auto-Restore + vorwaerts-only.
#   Selbst bei versehentlichem dry_run=False auf realer Evidenz wird ein
#   fehlerhafter Lauf verlustfrei zurueckgerollt (runner rollt zudem die
#   fehlgeschlagene Einzelmigration selbst zurueck — Beleg runner._apply).
#
#   ISOLATION: jede Instanz eigenes Backup + eigene Verbindung; ein Fehler bei
#   Instanz A beruehrt Instanz B nicht (execute_fleet faengt Instanzfehler ab).
#
#   Build 319 wird NUR gegen synthetische, evidenz-/assets-/forensic-foermige
#   DBs getestet; echte Evidenz ist NICHT Teil der Lieferung. Kein GPG (Zeremonie).
#
# Beleg: Bauplan Build 319 v0.1 §2, Datenmigrationsleitfaden_AIW.md v0.2 §3/§8/§10,
#        management/migrations/runner.py, mc 2026-07-03.
# Version: v0.7.319 · Build: 319 · 2026-07-03
# =============================================================================

import logging
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from management.migration_fleet.catalog import DB_KIND_PACKAGES
from management.migration_fleet.harness.backup import BackupTool
from management.migration_fleet.harness.harness import MigrationHarness
from management.migration_fleet.ledger import MigrationLedger
from management.migration_fleet.migration_db import MigrationDb, RegistryEntry
from management.migration_fleet.planner import TargetDb, read_instance_version
from management.migrations.runner import MigrationRunner, discover

logger = logging.getLogger(__name__)


class _VerifyFailed(Exception):
    """Interner Marker: Lossless-Verify nach der Migration ist fehlgeschlagen."""


@dataclass(frozen=True)
class ExecutionResult:
    db_kind: str
    uid: Optional[int]
    path: str
    status: str                 # 'up_to_date'|'planned'|'ok'|'failed_restored'
    from_version: int
    to_version: int
    applied: List[int] = field(default_factory=list)
    backup_path: Optional[str] = None
    detail: str = ""


class FleetExecutor:
    """Fuehrt Beweis-DB-Migrationen safe-by-design und gated aus."""

    def __init__(self, mdb: MigrationDb, ledger: MigrationLedger, *,
                 backup_dir: Optional[str] = None,
                 operator: Optional[str] = None,
                 packages: Optional[Dict] = None) -> None:
        self._mdb = mdb
        self._ledger = ledger
        self._backup_dir = backup_dir
        self._operator = operator
        # packages injizierbar (Tests: synthetische Bad-Migrationen), sonst real.
        self._packages = packages if packages is not None else DB_KIND_PACKAGES

    # ------------------------------------------------------------- intern
    def _pending_modules(self, db_kind: str, current: int) -> List:
        pkg = self._packages.get(db_kind)
        if pkg is None:
            return []
        return [m for m in discover(pkg) if m.VERSION > current]

    @staticmethod
    def _restore(path: str, backup_path: str) -> None:
        """
        Stellt die Instanz aus dem Backup wieder her. Voraussetzung: keine
        offene Verbindung auf path (Aufrufer schliesst alle Verbindungen zuvor).
        WAL/SHM-Seitendateien werden entfernt, dann die saubere Backup-Kopie
        zurueckgespielt.
        """
        for suffix in ("-wal", "-shm"):
            side = path + suffix
            if os.path.exists(side):
                os.remove(side)
        shutil.copyfile(backup_path, path)

    def _apply_pending(self, path: str, pending: List) -> List[int]:
        con = sqlite3.connect(path)
        try:
            con.isolation_level = None
            # audit=None: Beweis-DBs fuehren kein audit_log; der forensische
            # Beleg des Vorgangs ist das migration_runs-Ledger (Build 318).
            return MigrationRunner(con, pending, audit=None,
                                   deployed_by=self._operator).run()
        finally:
            con.close()

    # ------------------------------------------------------------- oeffentlich
    def execute_instance(self, target: TargetDb, *, dry_run: bool = True,
                         verifier: Optional[str] = None) -> ExecutionResult:
        db_kind, path, uid = target.db_kind, target.path, target.uid
        current = read_instance_version(path)
        pending = self._pending_modules(db_kind, current)
        if not pending:
            return ExecutionResult(db_kind, uid, path, "up_to_date",
                                   current, current)
        to_version = max(m.VERSION for m in pending)

        if dry_run:
            return ExecutionResult(
                db_kind, uid, path, "planned", current, to_version,
                detail="Dry-Run: %d Migration(en) ausstehend (v%s)"
                       % (len(pending), ", v".join(str(m.VERSION) for m in pending)))

        # --- GATING: echte Ausfuehrung erfordert backup_dir (Pflicht-Backup) ---
        if not self._backup_dir:
            raise ValueError(
                "Ausfuehrung verweigert: kein backup_dir gesetzt — Pflicht-"
                "Backup fuer Beweis-DBs (mc 2026-07-03).")

        # 1. Pre-Snapshot
        pre = MigrationHarness.snapshot(path)
        # 2. Pflicht-Backup (konsistente VACUUM-INTO-Kopie)
        backup = BackupTool.create_backup(
            path, self._backup_dir, db_label=Path(path).stem, version=current)
        started_at = int(time.time())
        # 3. Ledger-Start (VOR dem Anfassen der Daten)
        self._ledger.record_start(
            db_kind=db_kind, uid=uid, from_version=current, to_version=to_version,
            started_at=started_at, pre_sha512=pre.sha512,
            backup_path=backup.path, operator=self._operator)

        try:
            applied = self._apply_pending(path, pending)
            # Baseline aendert keine Daten -> expected_deltas leer (streng).
            report = MigrationHarness.verify_against(path, pre, expected_deltas={})
            if not report.ok:
                raise _VerifyFailed()
            post = MigrationHarness.snapshot(path)
            self._ledger.record_result(
                db_kind=db_kind, uid=uid, from_version=current,
                to_version=to_version, started_at=started_at, status="ok",
                post_sha512=post.sha512, backup_path=backup.path,
                operator=self._operator, verifier=verifier)
            self._mdb.upsert_registry_entry(RegistryEntry(
                db_kind=db_kind, uid=uid, path=path, current_version=to_version,
                last_verified_at=int(time.time()), last_status="ok"))
            return ExecutionResult(db_kind, uid, path, "ok", current, to_version,
                                   applied=applied, backup_path=backup.path)
        except Exception as exc:
            # --- STOP-AND-FLAG + RESTORE (all-or-nothing je Instanz) ---
            self._restore(path, backup.path)
            self._ledger.record_result(
                db_kind=db_kind, uid=uid, from_version=current,
                to_version=to_version, started_at=started_at, status="failed",
                backup_path=backup.path, operator=self._operator)
            self._ledger.record_result(
                db_kind=db_kind, uid=uid, from_version=current,
                to_version=to_version, started_at=started_at, status="restored",
                backup_path=backup.path, operator=self._operator)
            self._mdb.upsert_registry_entry(RegistryEntry(
                db_kind=db_kind, uid=uid, path=path, current_version=current,
                last_verified_at=int(time.time()), last_status="failed"))
            detail = ("Lossless-Verify fehlgeschlagen -> wiederhergestellt"
                      if isinstance(exc, _VerifyFailed)
                      else "Fehler '%s' -> wiederhergestellt" % exc)
            logger.warning("Instanz %s/uid=%s: %s", db_kind, uid, detail)
            return ExecutionResult(db_kind, uid, path, "failed_restored",
                                   current, to_version, backup_path=backup.path,
                                   detail=detail)

    def execute_fleet(self, targets: List[TargetDb], *, dry_run: bool = True,
                      verifier: Optional[str] = None) -> List[ExecutionResult]:
        """
        Fuehrt mehrere Instanzen aus. Isolation: ein per-Instanz-Fehler
        (failed_restored) stoppt die Flotte NICHT. Ein Konfigurationsfehler
        (fehlendes backup_dir bei dry_run=False) bricht hingegen ab, bevor
        Daten angefasst werden.
        """
        return [self.execute_instance(t, dry_run=dry_run, verifier=verifier)
                for t in targets]

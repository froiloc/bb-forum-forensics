# =============================================================================
# management/backup/backup_executor.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Backup/PITR (Welle 0)
# =============================================================================
# BackupExecutor — Phase des SCHREIBENS (Build 353). Fuehrt fuer jeden Eintrag
# eines geprueften BackupPlan die eigentliche Sicherung durch:
#
#   1) optional 'wal_checkpoint(PASSIVE)' auf der Quelle (nicht blockierend;
#      nie TRUNCATE) — je config.backup.checkpoint,
#   2) transaktionaler Snapshot per 'VACUUM INTO' (via BackupTool, Build 317;
#      Quelle wird NICHT veraendert),
#   3) 'PRAGMA integrity_check' auf der KOPIE (zertifiziert das Backup, stoert
#      keinen Livezugriff; Beleg: Bauplan B7 v1.1 §11 Punkt 7),
#   4) SHA512 (aus BackupTool) als Integritaets-/Provenienzsiegel.
#
# Robustheit (Grundregel 1 — kein stiller Fehlpfad): ein Fehler bei EINER DB
# bricht den Gesamtlauf NICHT ab. Jede DB wird einzeln bilanziert; der Lauf ist
# nur dann ok, wenn ALLE Sicherungen erfolgreich UND integer sind. Alle
# Ergebnisse landen in einem JSON-Manifest je Lauf.
#
# Der Executor VERWEIGERT den Lauf, wenn die Speicherplatz-Vorabpruefung
# (BackupPlan.ok) fehlgeschlagen ist — halbe/unbrauchbare Kopien bei voller
# Platte werden so verhindert (vorfall-getrieben, 2026-07-01).
#
# Registrierung in der 'backups'-Registry + 'BACKUP_CREATED'-Audit folgt in
# Build 354 (bewusst getrennt).
#
# Beleg: Bauplan B7 v1.1 §11; Datenmigrationsleitfaden v0.2 §4; mc 2026-07-10.
# Version: v0.7.353 · Build: 353 · 2026-07-10
# =============================================================================

import json
import os
import re
import socket
import sqlite3
import time
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple

from management.backup.backup_config import BackupConfig
from management.backup.backup_planner import BackupPlan
from management.migration_fleet.harness.backup import BackupTool

#: Erkennt Backup-Dateinamen der Leitfaden-Konvention
#: '<label>_v<version>_<ts>_<host>.backup.db' fuer die Retention-Gruppierung.
_BACKUP_NAME_RE = re.compile(
    r"^(?P<label>.+)_v\d+_(?P<ts>\d{8}T\d{6}Z)_.+\.backup\.db$")


@dataclass(frozen=True)
class BackupItemResult:
    """Ergebnis der Sicherung EINER Datenbank."""
    label: str
    src: str
    backup_path: Optional[str]
    sha512: Optional[str]
    size: int
    user_version: int
    integrity_ok: bool
    error: Optional[str]   # None wenn erfolgreich, sonst Klartext-Grund


@dataclass(frozen=True)
class BackupRun:
    """Gesamtergebnis eines Backup-Laufs."""
    ok: bool
    results: List[BackupItemResult]
    pruned: List[str]
    manifest_path: Optional[str]
    reason: str


class BackupExecutor:
    """Fuehrt einen geprueften BackupPlan aus (schreibend, Quelle read-only)."""

    def __init__(self, backup_cfg: BackupConfig) -> None:
        self._cfg = backup_cfg

    # ------------------------------------------------------------------- run
    def run(self, plan: BackupPlan) -> BackupRun:
        """
        Sichert alle Quellen des Plans. Verweigert, wenn plan.ok False ist
        (Vorabpruefung fehlgeschlagen).
        """
        if not plan.ok:
            return BackupRun(
                ok=False, results=[], pruned=[], manifest_path=None,
                reason="Vorabpruefung fehlgeschlagen: " + plan.reason)

        run_ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        host = socket.gethostname()

        results = [self._backup_one(src, plan.dest_dir, run_ts, host)
                   for src in plan.sources]

        pruned = self._prune(plan.dest_dir)
        overall_ok = all(r.error is None and r.integrity_ok for r in results)
        manifest_path = self._write_manifest(
            plan.dest_dir, run_ts, host, results, pruned, overall_ok)

        reason = "" if overall_ok else (
            "Mindestens eine DB-Sicherung schlug fehl oder ist nicht integer "
            "(siehe Manifest).")
        return BackupRun(ok=overall_ok, results=results, pruned=pruned,
                         manifest_path=manifest_path, reason=reason)

    # ----------------------------------------------------------- backup_one
    def _backup_one(self, src, dest_dir: str, run_ts: str,
                    host: str) -> BackupItemResult:
        """Eine DB sichern; jeder Fehler wird gefangen und bilanziert."""
        try:
            if self._cfg.checkpoint == "passive":
                # Nicht-blockierender WAL-Trim; Fehlschlag ist unkritisch, weil
                # VACUUM INTO ohnehin konsistent liest -> nur protokollieren.
                self._checkpoint_passive(src.path)

            uv = self._user_version(src.path)
            res = BackupTool.create_backup(
                src.path, dest_dir, db_label=src.label, version=uv,
                host=host, ts=run_ts)

            integ_ok, detail = self._integrity_check(res.path)
            return BackupItemResult(
                label=src.label, src=src.path, backup_path=res.path,
                sha512=res.sha512, size=res.size, user_version=uv,
                integrity_ok=integ_ok,
                error=None if integ_ok else ("integrity_check: " + detail))
        except Exception as exc:  # bewusst breit: kein DB darf den Lauf killen
            return BackupItemResult(
                label=src.label, src=src.path, backup_path=None, sha512=None,
                size=0, user_version=0, integrity_ok=False, error=str(exc))

    # ------------------------------------------------------------- helpers
    def _checkpoint_passive(self, src_path: str) -> None:
        con = sqlite3.connect(src_path)
        try:
            con.isolation_level = None
            con.execute("PRAGMA wal_checkpoint(PASSIVE)")
        finally:
            con.close()

    def _user_version(self, src_path: str) -> int:
        con = sqlite3.connect(src_path)
        try:
            row = con.execute("PRAGMA user_version").fetchone()
            return int(row[0]) if row else 0
        finally:
            con.close()

    def _integrity_check(self, backup_path: str) -> Tuple[bool, str]:
        """'PRAGMA integrity_check' auf der Backup-Kopie (read-only)."""
        con = sqlite3.connect(backup_path)
        try:
            rows = con.execute("PRAGMA integrity_check").fetchall()
        finally:
            con.close()
        ok = (len(rows) == 1 and rows[0][0] == "ok")
        detail = "ok" if ok else "; ".join(str(r[0]) for r in rows[:5])
        return ok, detail

    # -------------------------------------------------------------- prune
    def _prune(self, dest_dir: str) -> List[str]:
        """
        Behaelt je DB-Label die retention_count neuesten Generationen (nach dem
        eingebetteten Zeitstempel, lexikografisch sortierbar) und loescht
        aeltere Backup-Dateien. Nur Dateien der Namenskonvention werden
        beruecksichtigt; alles andere bleibt unangetastet.
        """
        try:
            names = os.listdir(dest_dir)
        except OSError:
            return []

        groups = {}
        for name in names:
            m = _BACKUP_NAME_RE.match(name)
            if not m:
                continue
            groups.setdefault(m.group("label"), []).append(
                (m.group("ts"), name))

        pruned: List[str] = []
        for _label, items in groups.items():
            items.sort(reverse=True)  # neueste zuerst
            for _ts, name in items[self._cfg.retention_count:]:
                p = os.path.join(dest_dir, name)
                try:
                    os.remove(p)
                    pruned.append(p)
                except OSError:
                    pass  # bleibt bestehen; nicht fatal
        return pruned

    # ----------------------------------------------------------- manifest
    def _write_manifest(self, dest_dir: str, run_ts: str, host: str,
                        results: List[BackupItemResult], pruned: List[str],
                        overall_ok: bool) -> Optional[str]:
        """Schreibt ein JSON-Manifest des Laufs (ASCII-only)."""
        manifest = {
            "run_ts": run_ts,
            "host": host,
            "ok": overall_ok,
            "config": {
                "dest_dir": self._cfg.dest_dir,
                "retention_count": self._cfg.retention_count,
                "min_free_factor": self._cfg.min_free_factor,
                "checkpoint": self._cfg.checkpoint,
                "include_shared_dbs": self._cfg.include_shared_dbs,
            },
            "results": [asdict(r) for r in results],
            "pruned": pruned,
        }
        path = os.path.join(
            dest_dir, "manifest_%s_%s.json" % (run_ts, host))
        try:
            with open(path, "w", encoding="ascii") as fh:
                json.dump(manifest, fh, ensure_ascii=True, indent=2)
            return path
        except OSError:
            return None

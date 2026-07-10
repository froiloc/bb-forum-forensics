# =============================================================================
# tests/test_backups_registry.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Backup/PITR (Welle 0)
# =============================================================================
# Testsuite fuer Build 354: m007 'backups'-Registry + BackupsRepo + backup_admin.
#
# BR01 — m007 legt Tabelle 'backups' + Index an; idempotent (zweiter Lauf ok).
# BR02 — EventType.BACKUP_CREATED ist gueltig (Vokabular).
# BR03 — record_run: EIN BACKUP_CREATED-Beleg; je DB eine Zeile mit dessen seq.
# BR04 — list_backups: liefert Zeilen, Filter je db_label.
# CL01 — CLI 'run' + 'list': End-to-End ueber temp config.yaml (Integration).
# CL02 — CLI 'plan': Trockenlauf, kein DB-Write.
#
# Version: v0.7.354 · Build: 354 · 2026-07-10
# =============================================================================

import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations
from management.audit.audit_log import AuditLog
from management.audit.event_types import EventType
from management.migrations.runner import MigrationRunner, discover
from management.gateway.coordinator_writer import CoordinatorWriter
from management.backup.backup_config import BackupConfig
from management.backup.backup_planner import BackupPlanner
from management.backup.backup_executor import BackupExecutor
from management.backup.backups_repo import BackupsRepo
from management.backup import backup_admin

_PERSON = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY AUTOINCREMENT, system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL, is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0, is_support INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
)
"""

# Alt-Tabelle, die die destruktive Migration m002 nach 'cases' ueberfuehrt.
# Muss (wie im Server-Harness) VOR den Migrationen existieren (precount).
_OLD_SCRAPE_JOBS = """
CREATE TABLE scrape_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','running','done','failed')),
    manifest_path TEXT, output_path TEXT, worker_id TEXT,
    created_at INTEGER NOT NULL, started_at INTEGER, finished_at INTEGER,
    error_message TEXT, assigned_to INTEGER, note TEXT,
    FOREIGN KEY(assigned_to) REFERENCES person(id)
)
"""


def _mkdb(path, user_version=0, rows=2):
    con = sqlite3.connect(str(path))
    try:
        con.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
        con.executemany("INSERT INTO t(v) VALUES(?)",
                        [("y" * 15,) for _ in range(rows)])
        if user_version:
            con.execute("PRAGMA user_version=%d" % user_version)
        con.commit()
    finally:
        con.close()


def _build_coordinator(db_path):
    """coordinator.db mit person + allen Migrationen (inkl. m007) + genesis."""
    con = sqlite3.connect(db_path)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(_PERSON)
    con.execute(
        "INSERT INTO person (id, system_username, display_name, "
        "is_investigator, is_supervisor, is_support, created_at) "
        "VALUES (1, 'h0a2898', 'Chefin', 1, 1, 0, ?)", (int(time.time()),))
    con.execute(_OLD_SCRAPE_JOBS)
    audit = AuditLog(con)
    MigrationRunner(con, discover(coordinator_migrations), audit=audit,
                    deployed_by="tester").run()
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return con


class BackupsRegistryTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        base = Path(self._tmp)
        (base / "data").mkdir()
        (base / "data" / "evidence").mkdir()
        (base / "data" / "forensic").mkdir()
        (base / "data" / "assets").mkdir()
        (base / "backups").mkdir()
        self._base = base
        self._coord_path = str(base / "data" / "coordinator.db")
        self._dest = str(base / "backups")

        self.con = _build_coordinator(self._coord_path)
        _mkdb(base / "data" / "evidence" / "evidence_18.db", user_version=3)

        self._paths = {
            "coordinator_db": self._coord_path,
            "forensic_db_dir": str(base / "data" / "forensic"),
            "evidence_db_dir": str(base / "data" / "evidence"),
            "assets_db_dir": str(base / "data" / "assets"),
        }

    def tearDown(self):
        try:
            self.con.close()
        except Exception:
            pass
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    def _cfg(self, **over):
        base = dict(dest_dir=self._dest, retention_count=7,
                    min_free_factor=1.3, checkpoint="passive",
                    include_shared_dbs=False)
        base.update(over)
        return BackupConfig(**base)

    # BR01 -------------------------------------------------------------------
    def test_br01_migration_and_idempotent(self):
        have = {r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("backups", have)
        idx = {r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertIn("ix_backups_label_ts", idx)
        # up() erneut aufrufen -> No-op, kein Fehler.
        from management.migrations.coordinator import m007_backups
        m007_backups.up(self.con)

    # BR02 -------------------------------------------------------------------
    def test_br02_event_vocab(self):
        self.assertTrue(EventType.is_valid(EventType.BACKUP_CREATED))
        self.assertEqual(EventType.BACKUP_CREATED, "backup_created")

    # BR03 -------------------------------------------------------------------
    def test_br03_record_run_couples_audit(self):
        cfg = self._cfg()
        plan = BackupPlanner(self._paths, cfg).plan()
        run = BackupExecutor(cfg).run(plan)
        self.assertTrue(run.ok, run.reason)

        writer = CoordinatorWriter(self.con, AuditLog(self.con))
        seq = BackupsRepo(self.con, writer).record_run(run, actor_id=1)

        # Genau EIN backup_created-Beleg mit dieser seq.
        ev = self.con.execute(
            "SELECT event_type FROM audit_log WHERE seq=?", (seq,)).fetchone()
        self.assertEqual(ev[0], "backup_created")
        # Je DB eine Zeile, alle mit derselben audit_seq.
        rows = self.con.execute(
            "SELECT db_label, audit_seq, integrity_ok FROM backups").fetchall()
        self.assertEqual(len(rows), len(run.results))
        self.assertTrue(all(r[1] == seq for r in rows))
        self.assertTrue(all(r[2] == 1 for r in rows))
        # coordinator + evidence_18 sind dabei.
        labels = {r[0] for r in rows}
        self.assertEqual(labels, {"coordinator", "evidence_18"})

    # BR04 -------------------------------------------------------------------
    def test_br04_list_backups(self):
        cfg = self._cfg()
        run = BackupExecutor(cfg).run(BackupPlanner(self._paths, cfg).plan())
        writer = CoordinatorWriter(self.con, AuditLog(self.con))
        repo = BackupsRepo(self.con, writer)
        repo.record_run(run, actor_id=1)

        allrows = repo.list_backups()
        self.assertEqual(len(allrows), 2)
        only = repo.list_backups(db_label="coordinator")
        self.assertEqual(len(only), 1)
        self.assertEqual(only[0]["db_label"], "coordinator")

    # ---- CLI-Integration ---------------------------------------------------
    def _write_config(self):
        cfg_path = os.path.join(self._tmp, "config.yaml")
        with open(cfg_path, "w", encoding="utf-8") as fh:
            fh.write(
                "paths:\n"
                "  coordinator_db: %s\n"
                "  forensic_db_dir: %s\n"
                "  evidence_db_dir: %s\n"
                "  assets_db_dir: %s\n"
                "backup:\n"
                "  dest_dir: %s\n"
                "  include_shared_dbs: false\n"
                % (self._coord_path,
                   os.path.join(self._base, "data", "forensic"),
                   os.path.join(self._base, "data", "evidence"),
                   os.path.join(self._base, "data", "assets"),
                   self._dest))
        return cfg_path

    # CL01 -------------------------------------------------------------------
    def test_cl01_cli_run_then_list(self):
        # Verbindung schliessen, damit das CLI exklusiv arbeiten kann.
        self.con.close()
        cfg_path = self._write_config()
        rc_run = backup_admin.main(
            ["run", "--config", cfg_path, "--actor", "h0a2898"])
        self.assertEqual(rc_run, 0)
        rc_list = backup_admin.main(["list", "--config", cfg_path])
        self.assertEqual(rc_list, 0)
        # Registry-Zeilen wurden geschrieben.
        con = sqlite3.connect(self._coord_path)
        try:
            n = con.execute("SELECT COUNT(*) FROM backups").fetchone()[0]
        finally:
            con.close()
        self.assertGreaterEqual(n, 2)
        # Backup-Dateien liegen im Ziel.
        self.assertTrue(any(f.endswith(".backup.db")
                            for f in os.listdir(self._dest)))
        # Neu oeffnen fuer tearDown.
        self.con = sqlite3.connect(self._coord_path)

    # CL02 -------------------------------------------------------------------
    def test_cl02_cli_plan_no_write(self):
        cfg_path = self._write_config()
        before = self.con.execute("SELECT COUNT(*) FROM backups").fetchone()[0]
        rc = backup_admin.main(["plan", "--config", cfg_path])
        self.assertEqual(rc, 0)
        after = self.con.execute("SELECT COUNT(*) FROM backups").fetchone()[0]
        self.assertEqual(before, after)  # plan schreibt nichts


if __name__ == "__main__":
    unittest.main()

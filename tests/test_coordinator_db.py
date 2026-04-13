# =============================================================================
# tests/test_coordinator_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite für db/coordinator_db.py
#
# T01 — get_investigator(): bekannter Benutzer wird gefunden
# T02 — get_investigator(): unbekannter Benutzer gibt None zurück
# T03 — get_investigator(): Rollen-Flags korrekt
# T04 — get_assigned_job(): offener Job wird gefunden
# T05 — get_assigned_job(): kein offener Job gibt None zurück
# T06 — get_assigned_job(): abgeschlossener Job (done) wird ignoriert
# T07 — get_assigned_job(): Priorität bestimmt Auswahl (kleinste zuerst)
# T08 — get_job_by_id(): bekannter Job gefunden
# T09 — get_job_by_id(): unbekannte ID gibt None zurück
# T10 — update_job_status(): Status wird aktualisiert
# T11 — update_job_status(): ungültiger Status gibt False zurück
# T12 — update_job_status(): nicht vorhandene job_id gibt False zurück
# T13 — Retry-Logik: OperationalError führt zu Wiederholung
# T14 — JobRecord.output_path: NULL in DB → None im Record
#
# Version: v0.1.0 · Build: 007 · 2026-04-10
# =============================================================================

import sys, os, sqlite3, tempfile, textwrap, time, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import setup_logging, reset_for_testing
from core.config_loader import ConfigLoader
from db.coordinator_db import CoordinatorDb, InvestigatorRecord, JobRecord


def _setup_test_logging():
    reset_for_testing()
    tmp = tempfile.mkdtemp()
    config_path = os.path.join(tmp, "config.yaml")
    with open(config_path, "w") as fh:
        fh.write(textwrap.dedent(f"""
            logging:
              level: "debug"
              logfile: "{os.path.join(tmp, 'logs', 'test.log')}"
              max_bytes: 1048576
              backup_count: 2
            paths:
              coordinator_db: "./c.db"
              forensic_db_dir: "./f/"
              default_db: "./d.db"
              evidence_db_dir: "./e/"
        """))
    setup_logging(ConfigLoader(config_path=config_path))


def _make_cdb_attached() -> tuple[sqlite3.Connection, int, int]:
    """
    Erstellt coordinator.db in einer Temp-Datei, bindet sie per ATTACH an
    eine In-Memory-Haupt-DB. Gibt (con, investigator_id, job_id) zurück.
    """
    cdb_path = tempfile.mktemp(suffix=".db")
    cdb_con = sqlite3.connect(cdb_path)
    cdb_con.executescript("""
        CREATE TABLE investigators (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            system_username  TEXT NOT NULL UNIQUE,
            display_name     TEXT NOT NULL,
            is_investigator  INTEGER NOT NULL DEFAULT 1,
            is_supervisor    INTEGER NOT NULL DEFAULT 0,
            is_support       INTEGER NOT NULL DEFAULT 0,
            created_at       INTEGER NOT NULL
        );
        CREATE TABLE scrape_jobs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            username      TEXT NOT NULL,
            priority      INTEGER NOT NULL DEFAULT 3,
            status        TEXT NOT NULL DEFAULT 'pending',
            output_path   TEXT,
            assigned_to   INTEGER,
            created_at    INTEGER NOT NULL DEFAULT 0,
            started_at    INTEGER,
            finished_at   INTEGER,
            error_message TEXT,
            worker_id     TEXT,
            manifest_path TEXT
        );
        INSERT INTO investigators
            (system_username, display_name, is_investigator, is_supervisor, is_support, created_at)
            VALUES ('h012345', 'Ermittler Eins', 1, 0, 0, 1700000000);
        INSERT INTO investigators
            (system_username, display_name, is_investigator, is_supervisor, is_support, created_at)
            VALUES ('h099999', 'Supervisor', 1, 1, 0, 1700000001);
    """)
    inv_id = cdb_con.execute(
        "SELECT id FROM investigators WHERE system_username='h012345'"
    ).fetchone()[0]
    cdb_con.execute(
        "INSERT INTO scrape_jobs "
        "(user_id, username, priority, status, assigned_to, created_at) "
        "VALUES (42, 'verdaechtiger42', 3, 'pending', ?, 100)",
        (inv_id,),
    )
    job_id = cdb_con.execute("SELECT last_insert_rowid()").fetchone()[0]
    cdb_con.commit()
    cdb_con.close()

    main_con = sqlite3.connect(":memory:")
    main_con.row_factory = sqlite3.Row
    main_con.execute(f"ATTACH DATABASE '{cdb_path}' AS cdb")
    return main_con, inv_id, job_id


class TestCoordinatorDb(unittest.TestCase):
    def setUp(self):
        _setup_test_logging()
        self.con, self.inv_id, self.job_id = _make_cdb_attached()
        self.cdb = CoordinatorDb(self.con)

    def tearDown(self):
        self.con.close()
        reset_for_testing()

    def test_T01_get_investigator_bekannt(self):
        """T01: Bekannter Systembenutzer wird korrekt gefunden."""
        inv = self.cdb.get_investigator("h012345")
        self.assertIsNotNone(inv)
        self.assertIsInstance(inv, InvestigatorRecord)
        self.assertEqual(inv.system_username, "h012345")
        self.assertEqual(inv.display_name, "Ermittler Eins")

    def test_T02_get_investigator_unbekannt(self):
        """T02: Unbekannter Benutzer gibt None zurück."""
        self.assertIsNone(self.cdb.get_investigator("unbekannt"))

    def test_T03_rollen_flags(self):
        """T03: Rollen-Flags werden korrekt aus DB übernommen."""
        inv = self.cdb.get_investigator("h012345")
        self.assertTrue(inv.is_investigator)
        self.assertFalse(inv.is_supervisor)
        self.assertFalse(inv.is_support)

        sup = self.cdb.get_investigator("h099999")
        self.assertTrue(sup.is_investigator)
        self.assertTrue(sup.is_supervisor)

    def test_T04_get_assigned_job(self):
        """T04: Offener Job wird korrekt gefunden."""
        job = self.cdb.get_assigned_job(self.inv_id)
        self.assertIsNotNone(job)
        self.assertIsInstance(job, JobRecord)
        self.assertEqual(job.user_id, 42)
        self.assertEqual(job.username, "verdaechtiger42")
        self.assertEqual(job.status, "pending")

    def test_T05_kein_offener_job(self):
        """T05: Ermittler ohne zugewiesenen Job gibt None zurück."""
        sup_id = self.con.execute(
            "SELECT id FROM cdb.investigators WHERE system_username='h099999'"
        ).fetchone()[0]
        self.assertIsNone(self.cdb.get_assigned_job(sup_id))

    def test_T06_abgeschlossener_job_ignoriert(self):
        """T06: Jobs mit status='done' werden nicht zurückgegeben."""
        self.con.execute(
            "UPDATE cdb.scrape_jobs SET status='done' WHERE id=?",
            (self.job_id,),
        )
        self.con.commit()
        self.assertIsNone(self.cdb.get_assigned_job(self.inv_id))

    def test_T07_prioritaet(self):
        """T07: Job mit höchster Priorität (kleinste Zahl) wird bevorzugt."""
        self.con.execute(
            "INSERT INTO cdb.scrape_jobs "
            "(user_id, username, priority, status, assigned_to, created_at) "
            "VALUES (99, 'dringend', 1, 'pending', ?, 200)",
            (self.inv_id,),
        )
        self.con.commit()
        job = self.cdb.get_assigned_job(self.inv_id)
        self.assertEqual(job.user_id, 99)
        self.assertEqual(job.priority, 1)

    def test_T08_get_job_by_id_bekannt(self):
        """T08: get_job_by_id() gibt Job mit korrekter ID zurück."""
        job = self.cdb.get_job_by_id(self.job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job.id, self.job_id)

    def test_T09_get_job_by_id_unbekannt(self):
        """T09: Unbekannte job_id gibt None zurück."""
        self.assertIsNone(self.cdb.get_job_by_id(9999))

    def test_T10_update_job_status(self):
        """T10: Status wird korrekt aktualisiert."""
        result = self.cdb.update_job_status(self.job_id, "running", worker_id="ws01")
        self.assertTrue(result)
        row = self.con.execute(
            "SELECT status, worker_id FROM cdb.scrape_jobs WHERE id=?",
            (self.job_id,),
        ).fetchone()
        self.assertEqual(row["status"], "running")
        self.assertEqual(row["worker_id"], "ws01")

    def test_T11_update_job_ungültiger_status(self):
        """T11: Ungültiger Status gibt False zurück (kein DB-Zugriff)."""
        result = self.cdb.update_job_status(self.job_id, "geisterstatus")
        self.assertFalse(result)

    def test_T12_update_job_unbekannte_id(self):
        """T12: Nicht vorhandene job_id gibt False zurück."""
        result = self.cdb.update_job_status(9999, "running")
        self.assertFalse(result)

    def test_T13_retry_logik(self):
        """T13: Bei OperationalError wird bis zu _RETRY_COUNT Mal wiederholt."""
        import db.coordinator_db as cdb_module
        original_delay = cdb_module._RETRY_DELAY_S
        cdb_module._RETRY_DELAY_S = 0.0  # Delay für Tests auf 0 setzen

        call_count = [0]
        original_method = self.cdb._get_investigator_once

        def failing_then_succeeding(username):
            call_count[0] += 1
            if call_count[0] < 2:
                raise sqlite3.OperationalError("Simulierter Netzfehler")
            return original_method(username)

        self.cdb._get_investigator_once = failing_then_succeeding
        result = self.cdb.get_investigator("h012345")
        self.assertIsNotNone(result)
        self.assertEqual(call_count[0], 2)  # 1 Fehler + 1 Erfolg

        cdb_module._RETRY_DELAY_S = original_delay

    def test_T14_output_path_null(self):
        """T14: NULL output_path in DB → None im JobRecord."""
        job = self.cdb.get_job_by_id(self.job_id)
        self.assertIsNone(job.output_path)

    def test_T15_get_support_status_kein_support_nutzer(self):
        """T15: get_support_status() → inactive wenn kein Support-Nutzer aktiv."""
        # Fixture hat keinen Support-Nutzer (is_support=0) und keinen running-Job
        result = self.cdb.get_support_status()
        self.assertFalse(result.active)
        self.assertIsNone(result.username)
        self.assertIsNone(result.since_ms)

    def test_T16_get_support_status_support_nutzer_aktiv(self):
        """T16: get_support_status() → active wenn Support-Nutzer running-Job hat."""
        # Support-Nutzer anlegen
        self.con.execute(
            "INSERT INTO cdb.investigators "
            "(system_username, display_name, is_investigator, is_supervisor, is_support, created_at) "
            "VALUES ('h067890', 'Support User', 0, 0, 1, 1700000010)"
        )
        support_id = self.con.execute(
            "SELECT id FROM cdb.investigators WHERE system_username='h067890'"
        ).fetchone()[0]
        # running-Job für Support-Nutzer
        self.con.execute(
            "INSERT INTO cdb.scrape_jobs "
            "(user_id, username, priority, status, assigned_to, created_at, started_at) "
            "VALUES (999, 'testuser', 3, 'running', ?, 1700000000, 1744300000)",
            (support_id,),
        )
        self.con.commit()

        result = self.cdb.get_support_status()
        self.assertTrue(result.active)
        self.assertEqual(result.username, "h067890")
        self.assertEqual(result.since_ms, 1744300000 * 1000)

        # Aufräumen
        self.con.execute(
            "DELETE FROM cdb.scrape_jobs WHERE assigned_to=?", (support_id,)
        )
        self.con.execute(
            "DELETE FROM cdb.investigators WHERE id=?", (support_id,)
        )
        self.con.commit()

    def test_T17_get_support_status_support_nutzer_done(self):
        """T17: Support-Nutzer mit status='done' gilt nicht als aktiv."""
        self.con.execute(
            "INSERT INTO cdb.investigators "
            "(system_username, display_name, is_investigator, is_supervisor, is_support, created_at) "
            "VALUES ('h077777', 'Inactive Support', 0, 0, 1, 1700000020)"
        )
        support_id = self.con.execute(
            "SELECT id FROM cdb.investigators WHERE system_username='h077777'"
        ).fetchone()[0]
        # Nur done-Job → nicht aktiv
        self.con.execute(
            "INSERT INTO cdb.scrape_jobs "
            "(user_id, username, priority, status, assigned_to, created_at) "
            "VALUES (998, 'doneuser', 3, 'done', ?, 1700000000)",
            (support_id,),
        )
        self.con.commit()

        result = self.cdb.get_support_status()
        self.assertFalse(result.active)

        # Aufräumen
        self.con.execute(
            "DELETE FROM cdb.scrape_jobs WHERE assigned_to=?", (support_id,)
        )
        self.con.execute(
            "DELETE FROM cdb.investigators WHERE id=?", (support_id,)
        )
        self.con.commit()

    def test_T18_support_status_record_felder(self):
        """T18: SupportStatusRecord-Datenklasse hat korrekte Felder."""
        from db.coordinator_db import SupportStatusRecord
        rec = SupportStatusRecord(active=True, username="h099", since_ms=1234567890000)
        self.assertTrue(rec.active)
        self.assertEqual(rec.username, "h099")
        self.assertEqual(rec.since_ms, 1234567890000)
        # frozen=True → Zuweisung wirft Fehler
        with self.assertRaises((AttributeError, TypeError)):
            rec.active = False


if __name__ == "__main__":
    unittest.main(verbosity=2)

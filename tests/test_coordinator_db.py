# =============================================================================
# tests/test_coordinator_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite für db/coordinator_db.py
#
# T01 — get_investigator(): bekannter Benutzer wird gefunden
# T02 — get_investigator(): unbekannter Benutzer gibt None zurück
# T03 — get_investigator(): Rollen-Flags korrekt
# T04–T07 — ENTFERNT (Build 308): get_assigned_job() obsolet (Zuweisung -> cases)
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
        CREATE TABLE person (
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
        CREATE TABLE support_sessions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            supporter_id   INTEGER,
            started_at     INTEGER NOT NULL,
            last_heartbeat INTEGER NOT NULL,
            ended_at       INTEGER
        );
        INSERT INTO person
            (system_username, display_name, is_investigator, is_supervisor, is_support, created_at)
            VALUES ('h012345', 'Ermittler Eins', 1, 0, 0, 1700000000);
        INSERT INTO person
            (system_username, display_name, is_investigator, is_supervisor, is_support, created_at)
            VALUES ('h099999', 'Supervisor', 1, 1, 0, 1700000001);
    """)
    inv_id = cdb_con.execute(
        "SELECT id FROM person WHERE system_username='h012345'"
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

    # T04–T07 (get_assigned_job) ENTFERNT (Build 308): Methode obsolet — die
    # Zuweisung 'Ermittler -> Fall' ist auf cases übergegangen.
    # Beleg: Problem-1-Analyse 2026-07-01, mc.

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

    # T16/T17 (get_support_status via scrape_jobs-Proxy) ENTFERNT (Build 308):
    # Der Stellvertreter (scrape_jobs.assigned_to + status) ist mit M002 weg;
    # eine echte Support-Sitzungserfassung existiert (noch) nicht. get_support_status
    # liefert daher stets inactive. Beleg: Problem-1-Analyse 2026-07-01, mc.

    def test_T17_support_stets_inactive_ohne_sitzungserfassung(self):
        """T17 (Build 308): Auch mit einem is_support-Ermittler bleibt der Status
        inactive — es gibt keine persistierte Support-Sitzung, aus der Aktivität
        abgeleitet werden könnte."""
        self.con.execute(
            "INSERT INTO cdb.person "
            "(system_username, display_name, is_investigator, is_supervisor, is_support, created_at) "
            "VALUES ('h077777', 'Support', 0, 0, 1, 1700000020)"
        )
        self.con.commit()
        result = self.cdb.get_support_status()
        self.assertFalse(result.active)
        self.assertIsNone(result.username)

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


    # ------------------------------------------------------------------ D01
    def test_D01_support_status_aktiv_mit_sitzung(self):
        """D01 (Build 311): aktive support_sessions-Zeile → active + count=1."""
        import time as _t
        now = int(_t.time())
        self.con.execute(
            "INSERT INTO cdb.support_sessions "
            "(user_id, supporter_id, started_at, last_heartbeat) "
            "VALUES (42, ?, ?, ?)",
            (self.inv_id, 1700000000, now),
        )
        self.con.commit()
        r = self.cdb.get_support_status(user_id=42, stale_sec=30)
        self.assertTrue(r.active)
        self.assertEqual(r.username, "h012345")
        self.assertEqual(r.since_ms, 1700000000 * 1000)
        self.assertEqual(r.count, 1)

    # ------------------------------------------------------------------ D02
    def test_D02_support_status_stale_ist_inaktiv(self):
        """D02: Sitzung mit altem Heartbeat gilt als inaktiv."""
        import time as _t
        alt = int(_t.time()) - 10_000
        self.con.execute(
            "INSERT INTO cdb.support_sessions "
            "(user_id, supporter_id, started_at, last_heartbeat) "
            "VALUES (42, ?, ?, ?)",
            (self.inv_id, alt, alt),
        )
        self.con.commit()
        r = self.cdb.get_support_status(user_id=42, stale_sec=30)
        self.assertFalse(r.active)
        self.assertEqual(r.count, 0)

    # ------------------------------------------------------------------ D03
    def test_D03_support_status_zaehlt_mehrere(self):
        """D03: Mehrere aktive Sitzungen desselben Falls → count>1, username=frühester."""
        import time as _t
        now = int(_t.time())
        sup2 = self.con.execute(
            "SELECT id FROM cdb.person WHERE system_username='h099999'"
        ).fetchone()[0]
        self.con.executemany(
            "INSERT INTO cdb.support_sessions "
            "(user_id, supporter_id, started_at, last_heartbeat) VALUES (42, ?, ?, ?)",
            [(self.inv_id, 1700000000, now), (sup2, 1700000500, now)],
        )
        self.con.commit()
        r = self.cdb.get_support_status(user_id=42, stale_sec=30)
        self.assertTrue(r.active)
        self.assertEqual(r.count, 2)
        self.assertEqual(r.username, "h012345")  # frühester started_at

    # ------------------------------------------------------------------ D04
    def test_D04_support_status_ohne_user_id_inaktiv(self):
        """D04: Ohne Fallkontext (user_id=None) inaktiv — unveränderte Alt-Aufrufform."""
        r = self.cdb.get_support_status()
        self.assertFalse(r.active)
        self.assertEqual(r.count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

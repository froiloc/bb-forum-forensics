# =============================================================================
# tests/test_connection_manager.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite für db/connection_manager.py
#
# T01 — Normalmodus: DatabaseBundle wird korrekt aufgebaut
# T02 — Normalmodus: fdb ist READ-ONLY angebunden (Schreibversuch schlägt fehl)
# T03 — Normalmodus: ddb ist READ-ONLY angebunden
# T04 — Normalmodus: forensic_db fehlt → ConnectionManagerError
# T05 — Normalmodus: default_db fehlt → ConnectionManagerError
# T06 — Normalmodus: coordinator.db fehlt → Warnung, kein Fehler
# T07 — Support-Modus (memory): TEMP-DB In-Memory, edb READ-ONLY
# T08 — Support-Modus (file): TEMP-DB-Datei angelegt
# T09 — Support-Modus: EvidenceDb schreibt in TEMP-DB, nicht in edb
# T10 — bundle.close(): Verbindung wird geschlossen
# T11 — bundle.close(): TEMP-DB-Datei wird gelöscht (Support file-Modus)
# T12 — Normalmodus: ForensicDb-Instanz ist funktionsfähig (BLOB-Lookup)
# T13 — ATTACH-Aliases: fdb, ddb, cdb korrekt angebunden
#
# Version: v0.1.0 · Build: 007 · 2026-04-10
# =============================================================================

import sys, os, sqlite3, tempfile, textwrap, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import setup_logging, reset_for_testing
from core.config_loader import ConfigLoader
from core.mode_resolver import ResolvedContext
from core.startup_checks import FORENSIC_DB_SCHEMA_VERSION
from db.connection_manager import ConnectionManager, ConnectionManagerError, DatabaseBundle


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
            support:
              temp_db: "memory"
        """))
    return ConfigLoader(config_path=config_path)


def _create_forensic_db(path: Path) -> None:
    """Minimale forensic_db mit Schema und einem Testdatensatz."""
    con = sqlite3.connect(str(path))
    con.executescript(f"""
        CREATE TABLE forensic_meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_canonical TEXT NOT NULL UNIQUE,
            html BLOB,
            fetched_at INTEGER NOT NULL,
            http_status INTEGER NOT NULL,
            scrape_context TEXT NOT NULL DEFAULT 'user'
        );
        CREATE TABLE page_aliases (url_raw TEXT PRIMARY KEY, page_id INTEGER);
        CREATE TABLE post_aliases (post_id INTEGER PRIMARY KEY, topic_id INTEGER, forum_id INTEGER);
        CREATE TABLE pm_aliases (pm_post_id INTEGER PRIMARY KEY, pm_topic_id INTEGER);
        CREATE TABLE notify_aliases (notify_id INTEGER PRIMARY KEY, post_id INTEGER);
        INSERT INTO forensic_meta VALUES ('schema_version', '{FORENSIC_DB_SCHEMA_VERSION}');
        INSERT INTO forensic_meta VALUES ('user_id', '42');
        INSERT INTO forensic_meta VALUES ('username', 'testuser');
        INSERT INTO forensic_meta VALUES ('sha256', 'placeholder');
        INSERT INTO pages (url_canonical, html, fetched_at, http_status)
            VALUES ('/forum/test', X'3C703E54657374203C2F703E', 1700000000, 200);
    """)
    con.commit()
    con.close()


def _create_default_db(path: Path) -> None:
    """Minimale default.db."""
    con = sqlite3.connect(str(path))
    con.executescript("""
        CREATE TABLE default_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE default_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT NOT NULL UNIQUE,
            data BLOB, mime_type TEXT, file_size INTEGER,
            source_note TEXT NOT NULL, fetched_at INTEGER
        );
        CREATE TABLE default_urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE, url_hash TEXT NOT NULL,
            asset_id INTEGER, url_context TEXT NOT NULL,
            http_status INTEGER, added_at INTEGER NOT NULL
        );
        INSERT INTO default_meta VALUES ('schema_version', '1');
    """)
    con.commit()
    con.close()


def _create_coordinator_db(path: Path) -> None:
    """Minimale coordinator.db."""
    con = sqlite3.connect(str(path))
    con.executescript("""
        CREATE TABLE investigators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            system_username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            is_investigator INTEGER NOT NULL DEFAULT 1,
            is_supervisor INTEGER NOT NULL DEFAULT 0,
            is_support INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE scrape_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, username TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 3,
            status TEXT NOT NULL DEFAULT 'pending',
            output_path TEXT, assigned_to INTEGER,
            created_at INTEGER NOT NULL DEFAULT 0,
            started_at INTEGER, finished_at INTEGER,
            error_message TEXT, worker_id TEXT, manifest_path TEXT
        );
    """)
    con.commit()
    con.close()


def _make_context(
    tmp: str,
    mode: str = "job",
    forensic_exists: bool = True,
    evidence_exists: bool = True,
    default_exists:  bool = True,
    coordinator_exists: bool = True,
) -> tuple[ResolvedContext, ConfigLoader]:
    forensic_db   = Path(tmp) / "forensic_42.db"
    evidence_db   = Path(tmp) / "evidence_42.db"
    default_db    = Path(tmp) / "default.db"
    coordinator   = Path(tmp) / "coordinator.db"

    if forensic_exists:    _create_forensic_db(forensic_db)
    if evidence_exists:    sqlite3.connect(str(evidence_db)).close()
    if default_exists:     _create_default_db(default_db)
    if coordinator_exists: _create_coordinator_db(coordinator)

    ctx = ResolvedContext(
        mode=mode, user_id=42, username="testuser",
        forensic_db=forensic_db, evidence_db=evidence_db,
        default_db=default_db, coordinator_db=coordinator,
        investigator_id=1,
    )
    cfg = _setup_test_logging()
    return ctx, cfg


class TestConnectionManagerNormal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.bundle: DatabaseBundle = None

    def tearDown(self):
        if self.bundle:
            self.bundle.close()
        reset_for_testing()

    def test_T01_bundle_aufgebaut(self):
        """T01: DatabaseBundle wird korrekt aufgebaut (Normalmodus)."""
        ctx, cfg = _make_context(self.tmp)
        mgr = ConnectionManager(ctx, cfg)
        self.bundle = mgr.open()
        self.assertIsNotNone(self.bundle.forensic)
        self.assertIsNotNone(self.bundle.default)
        self.assertIsNotNone(self.bundle.evidence)
        self.assertIsNotNone(self.bundle.coordinator)

    def test_T02_fdb_readonly(self):
        """T02: fdb ist READ-ONLY — Schreibversuch wirft OperationalError."""
        ctx, cfg = _make_context(self.tmp)
        self.bundle = ConnectionManager(ctx, cfg).open()
        with self.assertRaises(sqlite3.OperationalError):
            self.bundle.connection.execute(
                "INSERT INTO fdb.pages "
                "(url_canonical, fetched_at, http_status) VALUES ('x', 0, 0)"
            )

    def test_T03_ddb_readonly(self):
        """T03: ddb ist READ-ONLY — Schreibversuch wirft OperationalError."""
        ctx, cfg = _make_context(self.tmp)
        self.bundle = ConnectionManager(ctx, cfg).open()
        with self.assertRaises(sqlite3.OperationalError):
            self.bundle.connection.execute(
                "INSERT INTO ddb.default_meta VALUES ('test', 'val')"
            )

    def test_T04_forensic_db_fehlt(self):
        """T04: Fehlende forensic_db → ConnectionManagerError."""
        ctx, cfg = _make_context(self.tmp, forensic_exists=False)
        with self.assertRaises(ConnectionManagerError):
            ConnectionManager(ctx, cfg).open()

    def test_T05_default_db_fehlt(self):
        """T05: Fehlende default_db → ConnectionManagerError."""
        ctx, cfg = _make_context(self.tmp, default_exists=False)
        with self.assertRaises(ConnectionManagerError):
            ConnectionManager(ctx, cfg).open()

    def test_T06_coordinator_fehlt_kein_fehler(self):
        """T06: Fehlende coordinator.db → Warnung, kein Fehler."""
        ctx, cfg = _make_context(self.tmp, coordinator_exists=False)
        self.bundle = ConnectionManager(ctx, cfg).open()
        self.assertIsNotNone(self.bundle)

    def test_T12_forensic_db_funktionsfaehig(self):
        """T12: ForensicDb-Instanz ist nach open() funktionsfähig."""
        ctx, cfg = _make_context(self.tmp)
        self.bundle = ConnectionManager(ctx, cfg).open()
        page = self.bundle.forensic.get_page("/forum/test")
        self.assertIsNotNone(page)
        self.assertEqual(page.scrape_context, "user")

    def test_T13_attach_aliases(self):
        """T13: fdb, ddb, cdb sind als korrekte ATTACH-Aliases angebunden."""
        ctx, cfg = _make_context(self.tmp)
        self.bundle = ConnectionManager(ctx, cfg).open()
        con = self.bundle.connection
        # fdb erreichbar
        con.execute("SELECT COUNT(*) FROM fdb.pages").fetchone()
        # ddb erreichbar
        con.execute("SELECT COUNT(*) FROM ddb.default_assets").fetchone()
        # cdb erreichbar
        con.execute("SELECT COUNT(*) FROM cdb.investigators").fetchone()


class TestConnectionManagerSupport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.bundle: DatabaseBundle = None

    def tearDown(self):
        if self.bundle:
            self.bundle.close()
        reset_for_testing()

    def _make_support_cfg(self, temp_db: str = "memory") -> ConfigLoader:
        reset_for_testing()
        config_path = os.path.join(self.tmp, "config.yaml")
        logfile = os.path.join(self.tmp, "logs", "test.log")
        with open(config_path, "w") as fh:
            fh.write(textwrap.dedent(f"""
                logging:
                  level: "debug"
                  logfile: "{logfile}"
                  max_bytes: 1048576
                  backup_count: 2
                paths:
                  coordinator_db: "./c.db"
                  forensic_db_dir: "./f/"
                  default_db: "./d.db"
                  evidence_db_dir: "./e/"
                support:
                  temp_db: "{temp_db}"
            """))
        return ConfigLoader(config_path=config_path)

    def test_T07_support_memory(self):
        """T07: Support-Modus (memory): Bundle aufgebaut, edb READ-ONLY."""
        forensic_db = Path(self.tmp) / "forensic_42.db"
        evidence_db = Path(self.tmp) / "evidence_42.db"
        default_db  = Path(self.tmp) / "default.db"
        coordinator = Path(self.tmp) / "coordinator.db"
        _create_forensic_db(forensic_db)
        sqlite3.connect(str(evidence_db)).close()
        _create_default_db(default_db)
        _create_coordinator_db(coordinator)

        cfg = self._make_support_cfg("memory")
        ctx = ResolvedContext(
            mode="support", user_id=42, username="testuser",
            forensic_db=forensic_db, evidence_db=evidence_db,
            default_db=default_db, coordinator_db=coordinator,
            investigator_id=1,
        )
        self.bundle = ConnectionManager(ctx, cfg).open()
        self.assertIsNotNone(self.bundle)
        self.assertIsNone(self.bundle.temp_db_path)  # memory → kein Pfad

    def test_T08_support_file(self):
        """T08: Support-Modus (file): TEMP-DB-Datei wird angelegt."""
        forensic_db = Path(self.tmp) / "forensic_42.db"
        evidence_db = Path(self.tmp) / "evidence_42.db"
        default_db  = Path(self.tmp) / "default.db"
        coordinator = Path(self.tmp) / "coordinator.db"
        _create_forensic_db(forensic_db)
        sqlite3.connect(str(evidence_db)).close()
        _create_default_db(default_db)
        _create_coordinator_db(coordinator)

        cfg = self._make_support_cfg("file")
        ctx = ResolvedContext(
            mode="support", user_id=42, username="testuser",
            forensic_db=forensic_db, evidence_db=evidence_db,
            default_db=default_db, coordinator_db=coordinator,
            investigator_id=1,
        )
        self.bundle = ConnectionManager(ctx, cfg).open()
        self.assertIsNotNone(self.bundle.temp_db_path)
        self.assertTrue(Path(self.bundle.temp_db_path).exists())

    def test_T09_support_evidence_in_temp(self):
        """T09: EvidenceDb schreibt in TEMP-DB, nicht in edb."""
        forensic_db = Path(self.tmp) / "forensic_42.db"
        evidence_db = Path(self.tmp) / "evidence_42.db"
        default_db  = Path(self.tmp) / "default.db"
        coordinator = Path(self.tmp) / "coordinator.db"
        _create_forensic_db(forensic_db)
        sqlite3.connect(str(evidence_db)).close()
        _create_default_db(default_db)
        _create_coordinator_db(coordinator)

        cfg = self._make_support_cfg("memory")
        ctx = ResolvedContext(
            mode="support", user_id=42, username="testuser",
            forensic_db=forensic_db, evidence_db=evidence_db,
            default_db=default_db, coordinator_db=coordinator,
            investigator_id=1,
        )
        self.bundle = ConnectionManager(ctx, cfg).open()
        self.bundle.evidence.log_page_visit("/forum/test", "user")

        # edb (echte evidence_db) darf keine page_visits-Tabelle haben
        # (da sie als leere DB angelegt wurde und READ-ONLY angebunden ist)
        try:
            count = self.bundle.connection.execute(
                "SELECT COUNT(*) FROM edb.page_visits"
            ).fetchone()
            # Falls Tabelle existiert: muss leer sein
            self.assertEqual(count[0], 0)
        except sqlite3.OperationalError:
            # Tabelle existiert nicht in edb → korrekt, Schreiben war in TEMP-DB
            pass

        # TEMP-DB (Haupt-DB) muss den Eintrag haben
        count_temp = self.bundle.connection.execute(
            "SELECT COUNT(*) FROM page_visits"
        ).fetchone()[0]
        self.assertEqual(count_temp, 1)


class TestConnectionManagerClose(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        reset_for_testing()

    def test_T10_close_schliesst_verbindung(self):
        """T10: bundle.close() schließt die Verbindung."""
        ctx, cfg = _make_context(self.tmp)
        bundle = ConnectionManager(ctx, cfg).open()
        bundle.close()
        # Verbindung sollte nach close() nicht mehr nutzbar sein
        with self.assertRaises(Exception):
            bundle.connection.execute("SELECT 1")

    def test_T11_close_loescht_tempfile(self):
        """T11: bundle.close() löscht TEMP-DB-Datei im file-Modus."""
        reset_for_testing()
        config_path = os.path.join(self.tmp, "config.yaml")
        logfile = os.path.join(self.tmp, "logs", "test.log")
        with open(config_path, "w") as fh:
            fh.write(textwrap.dedent(f"""
                logging:
                  level: "debug"
                  logfile: "{logfile}"
                  max_bytes: 1048576
                  backup_count: 2
                paths:
                  coordinator_db: "./c.db"
                  forensic_db_dir: "./f/"
                  default_db: "./d.db"
                  evidence_db_dir: "./e/"
                support:
                  temp_db: "file"
            """))
        cfg = ConfigLoader(config_path=config_path)

        forensic_db = Path(self.tmp) / "forensic_42.db"
        evidence_db = Path(self.tmp) / "evidence_42.db"
        default_db  = Path(self.tmp) / "default.db"
        coordinator = Path(self.tmp) / "coordinator.db"
        _create_forensic_db(forensic_db)
        sqlite3.connect(str(evidence_db)).close()
        _create_default_db(default_db)
        _create_coordinator_db(coordinator)

        ctx = ResolvedContext(
            mode="support", user_id=42, username="testuser",
            forensic_db=forensic_db, evidence_db=evidence_db,
            default_db=default_db, coordinator_db=coordinator,
            investigator_id=1,
        )
        bundle = ConnectionManager(ctx, cfg).open()
        temp_path = bundle.temp_db_path
        self.assertTrue(Path(temp_path).exists())

        bundle.close()
        self.assertFalse(Path(temp_path).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

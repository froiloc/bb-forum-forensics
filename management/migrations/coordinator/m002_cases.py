# =============================================================================
# management/migrations/coordinator/m002_cases.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Migration M002 — coordinator.db (DESTRUKTIV)
#   1) Rebuild von scrape_jobs OHNE assigned_to/note. Grund: assigned_to steht in
#      einer FK-Klausel -> ALTER TABLE ... DROP COLUMN ist in SQLite unzulässig.
#      Daher 12-Schritt-Rebuild (neue Tabelle, Zeilen kopieren, alte droppen,
#      umbenennen, Indizes neu). scrape_jobs fällt damit auf seine reine
#      Baustelle-0-Rolle zurück.
#   2) Anlegen der Fallakte 'cases' (1:1 zur user_id) als autoritative Quelle
#      für Zuweisung/Status/Freigabe/Fortschritt.
#
#   KEINE Daten-Migration (Dummies, Entscheidung 2026-07-01). 'cases' startet leer.
#
# Invariante (verify): Zeilenzahl scrape_jobs vorher == nachher (keine Job-Zeile
# verloren) UND foreign_key_check für scrape_jobs/cases sauber.
#
# Voraussetzung: Management-Verbindung mit foreign_keys=OFF (SQLite-Default) ->
# Rebuild im Transaktionsrahmen unproblematisch (keine eingehenden FKs auf
# scrape_jobs vorhanden, geprüft 2026-07-01).
#
# Beleg: Bauplan_Baustelle7_Management_v0_1.md v0.3 §3.2, mc 2026-07-01.
# Version: v0.7.307 · Build: 307 · 2026-07-01
# =============================================================================

import sqlite3

VERSION = 2
NAME = "cases + scrape_jobs-Rebuild (ohne assigned_to/note)"
KIND = "destructive"


# --- DDL: scrape_jobs neu (ohne assigned_to/note) ----------------------------
_DDL_SCRAPE_JOBS_NEW = """
CREATE TABLE scrape_jobs_new (
    id            INTEGER,
    user_id       INTEGER NOT NULL,
    username      TEXT    NOT NULL,
    priority      INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status        TEXT    NOT NULL DEFAULT 'pending'
                  CHECK(status IN ('pending','running','done','failed')),
    manifest_path TEXT,
    output_path   TEXT,
    worker_id     TEXT,
    created_at    INTEGER NOT NULL,
    started_at    INTEGER,
    finished_at   INTEGER,
    error_message TEXT,
    PRIMARY KEY(id AUTOINCREMENT)
)
"""

_COPY_SCRAPE_JOBS = """
INSERT INTO scrape_jobs_new
    (id, user_id, username, priority, status, manifest_path, output_path,
     worker_id, created_at, started_at, finished_at, error_message)
SELECT
    id, user_id, username, priority, status, manifest_path, output_path,
    worker_id, created_at, started_at, finished_at, error_message
FROM scrape_jobs
"""

# --- DDL: cases --------------------------------------------------------------
_DDL_CASES = """
CREATE TABLE cases (
    user_id             INTEGER PRIMARY KEY,
    username            TEXT    NOT NULL,
    assigned_to         INTEGER,
    priority            INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status              TEXT    NOT NULL DEFAULT 'open'
                        CHECK(status IN ('open','in_progress','approved','closed')),
    approved_at         INTEGER,
    total_pages_scraped INTEGER,
    note                TEXT,
    created_at          INTEGER NOT NULL,
    updated_at          INTEGER NOT NULL,
    FOREIGN KEY(assigned_to) REFERENCES investigators(id)
)
"""


def precount(con: sqlite3.Connection) -> int:
    return int(con.execute("SELECT COUNT(*) FROM scrape_jobs").fetchone()[0])


def up(con: sqlite3.Connection) -> None:
    # 1) scrape_jobs-Rebuild ohne assigned_to/note.
    con.execute(_DDL_SCRAPE_JOBS_NEW)
    con.execute(_COPY_SCRAPE_JOBS)
    con.execute("DROP TABLE scrape_jobs")
    con.execute("ALTER TABLE scrape_jobs_new RENAME TO scrape_jobs")
    con.execute("CREATE INDEX IF NOT EXISTS scrape_jobs_status_idx ON scrape_jobs(status)")
    con.execute("CREATE INDEX IF NOT EXISTS scrape_jobs_user_idx   ON scrape_jobs(user_id)")
    # 2) Fallakte cases.
    con.execute(_DDL_CASES)


def postcount(con: sqlite3.Connection) -> int:
    return int(con.execute("SELECT COUNT(*) FROM scrape_jobs").fetchone()[0])


def verify(con: sqlite3.Connection, before, after) -> None:
    # Invariante 1: keine Job-Zeile verloren.
    if before != after:
        raise RuntimeError(
            "M002 Invariante verletzt: scrape_jobs Zeilenzahl %r -> %r" % (before, after)
        )
    # Invariante 2: FK-Integrität der betroffenen Tabellen sauber.
    for table in ("scrape_jobs", "cases"):
        violations = con.execute(
            "PRAGMA foreign_key_check(%s)" % table
        ).fetchall()
        if violations:
            raise RuntimeError(
                "M002 foreign_key_check(%s) meldet %d Verletzung(en)"
                % (table, len(violations))
            )

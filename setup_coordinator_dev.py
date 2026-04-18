#!/usr/bin/env python3
# =============================================================================
# setup_coordinator_dev.py
# IT-Forensisches Ermittlungswerkzeug — coordinator.db DEV-Bootstrap
# =============================================================================
# Zweck:
#   Legt die minimal notwendigen Tabellen in coordinator.db an und fügt
#   einen DEV-Dummy-Ermittler ein, damit der Webserver (Build 029+) keine
#   "no such table: cdb.investigators"- oder
#   "no such column: j.assigned_to"-Warnungen mehr ausgibt.
#
# WICHTIG: Dies ist KEIN permanenter Fix.
#   Der vollständige coordinator.db-Aufbau (inkl. Audit-Log, Hash-Chaining,
#   vollständige Schema-Migration) ist Teil von Baustelle 5 und Baustelle 7.
#   Dieses Skript dient ausschließlich dazu, das DEV-System lauffähig zu halten.
#
# Verwendung:
#   python3 setup_coordinator_dev.py [--db ./data/coordinator.db]
#
# Idempotent: Kann beliebig oft ausgeführt werden.
#
# Beleg: Bauplan_Baustelle2_Webserver_v0_4.md § 9.1
# Beleg: Projektgespräch 2026-04-18
# =============================================================================

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

# Standardpfad passend zu config.yaml ("coordinator_db: ./data/coordinator.db")
DEFAULT_DB_PATH = Path("./data/coordinator.db")


# -----------------------------------------------------------------------------
# DDL
# Beleg: Bauplan_Baustelle2_Webserver_v0_4.md § 9.1
# -----------------------------------------------------------------------------

DDL_INVESTIGATORS = """
CREATE TABLE IF NOT EXISTS investigators (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    system_username  TEXT    NOT NULL UNIQUE,
    display_name     TEXT    NOT NULL,
    is_investigator  INTEGER NOT NULL DEFAULT 1,
    is_supervisor    INTEGER NOT NULL DEFAULT 0,
    is_support       INTEGER NOT NULL DEFAULT 0,
    created_at       INTEGER NOT NULL
)
"""

# Beleg: TP-A_Nutzerdaten_Tabellen_URLs_v0_34.md § 9.3
DDL_SCRAPE_JOBS = """
CREATE TABLE IF NOT EXISTS scrape_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    username        TEXT    NOT NULL,
    priority        INTEGER NOT NULL DEFAULT 3
                    CHECK (priority BETWEEN 1 AND 5),
    status          TEXT    NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','running','done','failed')),
    manifest_path   TEXT,
    output_path     TEXT,
    worker_id       TEXT,
    assigned_to     INTEGER REFERENCES investigators(id),
    created_at      INTEGER NOT NULL,
    started_at      INTEGER,
    finished_at     INTEGER,
    error_message   TEXT
)
"""

DDL_SCRAPE_JOBS_IDX_STATUS = """
CREATE INDEX IF NOT EXISTS scrape_jobs_status_idx ON scrape_jobs (status, priority DESC)
"""

DDL_SCRAPE_JOBS_IDX_USER = """
CREATE INDEX IF NOT EXISTS scrape_jobs_user_idx ON scrape_jobs (user_id)
"""

# ALTER TABLE: assigned_to nachrüsten wenn Tabelle ohne diese Spalte existiert.
# Beleg: Bauplan_Baustelle2_Webserver_v0_4.md § 9.1 (ALTER TABLE scrape_jobs)
DDL_ADD_ASSIGNED_TO = "ALTER TABLE scrape_jobs ADD COLUMN assigned_to INTEGER REFERENCES investigators(id)"


def _column_exists(con: sqlite3.Connection, table: str, column: str) -> bool:
    """Prüft ob eine Spalte in einer Tabelle existiert."""
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    """Prüft ob eine Tabelle existiert."""
    row = con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row and row[0] > 0)


def setup(db_path: Path) -> None:
    print(f"[setup_coordinator_dev] Zieldatenbank: {db_path.resolve()}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))

    try:
        # WAL-Modus — konsistent mit connection_manager.py
        con.execute("PRAGMA journal_mode=WAL")

        # ------------------------------------------------------------------
        # Tabellen anlegen (idempotent)
        # ------------------------------------------------------------------
        con.execute(DDL_INVESTIGATORS)
        print("[setup_coordinator_dev] investigators: OK (CREATE TABLE IF NOT EXISTS)")

        con.execute(DDL_SCRAPE_JOBS)
        print("[setup_coordinator_dev] scrape_jobs:   OK (CREATE TABLE IF NOT EXISTS)")

        # Indizes nur anlegen wenn priority-Spalte vorhanden — defensiv gegen
        # bereits existierende scrape_jobs mit abweichendem DEV-Schema.
        if _column_exists(con, "scrape_jobs", "priority"):
            con.execute(DDL_SCRAPE_JOBS_IDX_STATUS)
            con.execute(DDL_SCRAPE_JOBS_IDX_USER)
            print("[setup_coordinator_dev] scrape_jobs-Indizes: OK")
        else:
            print("[setup_coordinator_dev] scrape_jobs-Indizes: übersprungen (priority fehlt)")

        # ------------------------------------------------------------------
        # Migration: assigned_to nachrüsten
        # SQLite kennt kein ADD COLUMN IF NOT EXISTS — daher explizite Prüfung.
        # Beleg: Projektgespräch 2026-04-18
        # ------------------------------------------------------------------
        if _table_exists(con, "scrape_jobs") and not _column_exists(con, "scrape_jobs", "assigned_to"):
            con.execute(DDL_ADD_ASSIGNED_TO)
            print("[setup_coordinator_dev] scrape_jobs.assigned_to: Spalte nachgerüstet (ALTER TABLE)")
        else:
            print("[setup_coordinator_dev] scrape_jobs.assigned_to: bereits vorhanden — kein ALTER TABLE nötig")

        # ------------------------------------------------------------------
        # DEV-Dummy-Ermittler einfügen
        # system_username muss mit dem lokalen $USER übereinstimmen.
        # Bitte ggf. an den eigenen Benutzernamen anpassen.
        # ------------------------------------------------------------------
        now = int(time.time())
        dev_users = [
            ("dev",    "DEV-Ermittler (lokal)", 1, 1, 0),
            ("claude", "DEV-Testnutzer (CI)",   1, 0, 0),
        ]
        inserted = 0
        for username, display, is_inv, is_sup_v, is_sup_p in dev_users:
            cur = con.execute(
                """
                INSERT OR IGNORE INTO investigators
                    (system_username, display_name, is_investigator, is_supervisor, is_support, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (username, display, is_inv, is_sup_v, is_sup_p, now),
            )
            if cur.rowcount > 0:
                inserted += 1
                print(f"[setup_coordinator_dev] Ermittler '{username}' eingefügt")
            else:
                print(f"[setup_coordinator_dev] Ermittler '{username}' bereits vorhanden — übersprungen")

        con.commit()

        # ------------------------------------------------------------------
        # Abschlussprüfung
        # ------------------------------------------------------------------
        rows = con.execute(
            "SELECT id, system_username, display_name, is_investigator, is_supervisor, is_support "
            "FROM investigators"
        ).fetchall()
        print(f"\n[setup_coordinator_dev] investigators-Tabelle ({len(rows)} Einträge):")
        for row in rows:
            print(f"  id={row[0]}  username={row[1]}  display={row[2]}"
                  f"  inv={row[3]}  sup={row[4]}  support={row[5]}")

        cols = [r[1] for r in con.execute("PRAGMA table_info(scrape_jobs)").fetchall()]
        assert "assigned_to" in cols, "FEHLER: assigned_to fehlt nach Migration!"
        print(f"\n[setup_coordinator_dev] scrape_jobs.assigned_to: vorhanden ✓")
        print("[setup_coordinator_dev] Abgeschlossen — keine Fehler.")

    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="coordinator.db DEV-Bootstrap (Baustelle 5/7 Vorarbeit)"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Pfad zur coordinator.db (Standard: {DEFAULT_DB_PATH})",
    )
    args = parser.parse_args()
    setup(args.db)


if __name__ == "__main__":
    main()

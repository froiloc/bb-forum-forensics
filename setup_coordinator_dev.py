#!/usr/bin/env python3
# =============================================================================
# setup_coordinator_dev.py
# IT-Forensisches Ermittlungswerkzeug — coordinator.db DEV-Bootstrap
# =============================================================================
# Zweck:
#   Legt die minimal notwendigen Tabellen in coordinator.db an, fügt
#   DEV-Dummy-Ermittler ein und legt einen DEV-Job für user_id=18 an,
#   damit der Webserver (Build 030+) im Modus --mode=job für den
#   Systembenutzer 'paul' (id=3) startet und keine Struktur-Warnungen
#   ausgibt.
#
# WICHTIG: Dies ist KEIN permanenter Fix.
#   Der vollständige coordinator.db-Aufbau (inkl. Audit-Log, Hash-Chaining,
#   vollständige Schema-Migration) ist Teil von Baustelle 5 und Baustelle 7.
#   Dieses Skript dient ausschließlich dazu, das DEV-System lauffähig zu halten.
#
# M019-HINWEIS (Build 469):
#   Migration M019 benennt in coordinator.db die Spalte user_id nach subject_id
#   um (u.a. scrape_jobs, cases) sowie den Index scrape_jobs_user_idx nach
#   scrape_jobs_subject_idx. Dieses Skript baut BEWUSST den Vor-M019-Stand
#   (Spalte user_id) — die Migration benennt danach verlustfrei um (analog
#   zur 'investigators'->'person'-Kette, siehe Deprecation-Block unten).
#   Die Nach-Checks und der DEV-Job-Insert ermitteln die Subjekt-Spalte
#   dynamisch, damit das Skript auf einer BEREITS migrierten DB nicht crasht.
#
# DEPRECATION (Build 342, Welle 0):
#   Dieses Skript wird mittelfristig entfernt (Kennzeichnung als 'deprecated'
#   folgt in Kürze). Es hat aktuell keine reguläre Verwendung mehr und wird
#   hier NUR funktional erhalten. Es legt die Tabelle bewusst weiterhin unter
#   dem ALTEN Namen 'investigators' an — NICHT als 'person'. Grund:
#     - Die Migrationen M002-M004 verdrahten FK-Referenzen fest auf
#       'investigators(id)'. Läuft dieser Bootstrap VOR 'migrate.py', finden
#       diese FKs ihren Anker, und die Migration M005 benennt 'investigators'
#       anschließend verlustfrei nach 'person' um (FK-Nachzug inklusive).
#     - Würde dieses Skript direkt 'person' anlegen, liefen die FK-Klauseln von
#       M002-M004 in einem Frisch-DEV ins Leere (dangling), da M005 dann keine
#       'investigators'-Tabelle zum Umbenennen vorfände.
#   Die Test-Suite baut ihr Schema ohnehin inline (bereits auf 'person'
#   umgestellt) und ruft weder dieses Skript noch 'migrate.py' — der reguläre
#   DEV-Weg ist davon nicht betroffen.
#   OFFENER PUNKT (späterer Build): Wer erzeugt 'person' nach Wegfall dieses
#   Bootstraps? -> Bootstrap-/RBAC-Build.
#
# Verwendung:
#   python3 setup_coordinator_dev.py [--db ./data/coordinator.db]
#
# Idempotent: Kann beliebig oft ausgeführt werden.
#
# Beleg: Bauplan_Baustelle2_Webserver_v0_4.md § 9.1
# Beleg: Projektgespräch 2026-04-18
# Version: v0.7.469 · Build: 469 · 2026-07-20
# Build 469: Schluesselumstellung user_id -> subject_id (M019) — Skript baut
#            bewusst den Vor-M019-Stand; Nach-Checks jetzt migrationsrobust.
# =============================================================================

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path
from db.journal_policy import apply_journal_mode  # NEU Build 408
from management.help import cli_epilog  # noqa: E402

# Standardpfad passend zu config.yaml ("coordinator_db: ./data/coordinator.db")
DEFAULT_DB_PATH = Path("./data/coordinator.db")


# -----------------------------------------------------------------------------
# DDL
# Beleg: Bauplan_Baustelle2_Webserver_v0_4.md § 9.1
# -----------------------------------------------------------------------------

# Hinweis (Build 342): bewusst ALTER Name 'investigators' — siehe Deprecation-
# Block im Kopf. M005 benennt später verlustfrei nach 'person' um.
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

# ALTER TABLE: note nachrüsten — freies Notizfeld für Ermittler.
# Beleg: Projektgespräch 2026-04-18 — Bugfix 'no such column: j.note'
DDL_ADD_NOTE = "ALTER TABLE scrape_jobs ADD COLUMN note TEXT"

# Build 182 (Bug 2.78): Transportmechanismus für Fremd-Annotationen.
# Ermittler <iid> schreibt Annotation zu uid2 auf Seiten von uid.
# Transportdatei evidence_<uid2>_<iid>.db wird angelegt, Eintrag hier als Signal.
# uid2-Webserver integriert beim Start/stündlich/manuell und markiert integrated_at.
# Beleg: Projektgespräch 2026-05-12.
DDL_PENDING_CROSS_ANNOTATIONS = """
CREATE TABLE IF NOT EXISTS pending_cross_annotations (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    source_iid           INTEGER NOT NULL REFERENCES investigators(id),
    target_uid           INTEGER NOT NULL,
    db_path              TEXT    NOT NULL,
    annotation_local_id  TEXT    NOT NULL,
    created_at           INTEGER NOT NULL,
    integrated_at        INTEGER DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS pca_target_uid_idx
    ON pending_cross_annotations (target_uid)
    WHERE integrated_at IS NULL;
"""


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


def _subject_column(con: sqlite3.Connection, table: str) -> str:
    """
    M019-robust (Build 469): Ermittelt den Namen der Subjekt-Spalte einer
    Tabelle dynamisch. Vor Migration M019 heißt sie 'user_id' (der Stand,
    den dieses Skript anlegt), nach M019 'subject_id'. So funktionieren
    Nach-Checks und DEV-Job-Insert auf beiden Ständen ohne Crash.
    """
    if _column_exists(con, table, "subject_id"):
        return "subject_id"
    return "user_id"


def setup(db_path: Path) -> None:
    print(f"[setup_coordinator_dev] Zieldatenbank: {db_path.resolve()}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))

    try:
        # Build 408: Journalmodus konsistent mit connection_manager.py, aber
        # netzlaufwerkstauglich (WAL, sonst protokollierter Rueckfall).
        apply_journal_mode(con, str(db_path))

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
            # M019-robust (Build 469): Der user_id-Index kann nur auf dem
            # Vor-M019-Stand angelegt werden. Nach der Migration heißt die
            # Spalte subject_id und der Index scrape_jobs_subject_idx existiert
            # bereits (von M019 angelegt) — dann nichts tun, nicht crashen.
            if _column_exists(con, "scrape_jobs", "user_id"):
                con.execute(DDL_SCRAPE_JOBS_IDX_USER)
                print("[setup_coordinator_dev] scrape_jobs-Indizes: OK")
            else:
                print("[setup_coordinator_dev] scrape_jobs_user_idx: übersprungen "
                      "(DB bereits M019-migriert — subject_id/scrape_jobs_subject_idx)")
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
        # Migration: note nachrüsten
        # Beleg: Projektgespräch 2026-04-18 — Bugfix 'no such column: j.note'
        # ------------------------------------------------------------------
        if _table_exists(con, "scrape_jobs") and not _column_exists(con, "scrape_jobs", "note"):
            con.execute(DDL_ADD_NOTE)
            print("[setup_coordinator_dev] scrape_jobs.note: Spalte nachgerüstet (ALTER TABLE)")
        else:
            print("[setup_coordinator_dev] scrape_jobs.note: bereits vorhanden — kein ALTER TABLE nötig")

        # ------------------------------------------------------------------
        # Build 182 (Bug 2.78): pending_cross_annotations anlegen
        # ------------------------------------------------------------------
        if not _table_exists(con, "pending_cross_annotations"):
            con.executescript(DDL_PENDING_CROSS_ANNOTATIONS)
            con.commit()
            print("[setup_coordinator_dev] pending_cross_annotations: Tabelle angelegt")
        else:
            print("[setup_coordinator_dev] pending_cross_annotations: bereits vorhanden")

        # ------------------------------------------------------------------
        # DEV-Dummy-Ermittler einfügen
        # system_username muss mit dem lokalen $USER übereinstimmen.
        # Bitte ggf. an den eigenen Benutzernamen anpassen.
        # ------------------------------------------------------------------
        now = int(time.time())
        dev_users = [
            ("dev",    "DEV-Ermittler (lokal)", 1, 1, 0),
            ("claude", "DEV-Testnutzer (CI)",   1, 0, 0),
            # paul: lokaler Systembenutzer laut Serverlog 2026-04-18
            ("paul",   "Paul (DEV-Systembenutzer)", 1, 1, 0),
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
        # DEV-Job: user_id=18 für 'paul' (id=3) anlegen
        # Wird für --mode=job benötigt: mode_resolver sucht einen offenen
        # Job in scrape_jobs WHERE assigned_to = investigators.id
        #   AND status IN ('pending', 'running').
        # Beleg: Serverlog 2026-04-18, core/mode_resolver.py _query_job()
        # ------------------------------------------------------------------
        paul_row = con.execute(
            "SELECT id FROM investigators WHERE system_username = 'paul'"
        ).fetchone()
        if paul_row:
            paul_id = paul_row[0] if not hasattr(paul_row, 'keys') else paul_row["id"]
            # M019-robust (Build 469): Subjekt-Spalte dynamisch ermitteln —
            # 'user_id' vor der Migration, 'subject_id' danach.
            subj_col = _subject_column(con, "scrape_jobs")
            # Prüfen ob DEV-Job bereits vorhanden
            existing = con.execute(
                f"SELECT id FROM scrape_jobs "
                f"WHERE {subj_col}=18 AND assigned_to=? AND status='pending'",
                (paul_id,),
            ).fetchone()
            if not existing:
                con.execute(
                    f"""
                    INSERT INTO scrape_jobs
                        ({subj_col}, username, priority, status, assigned_to, created_at)
                    VALUES (18, 'DEV-Beschuldigter-uid18', 2, 'pending', ?, ?)
                    """,
                    (paul_id, int(time.time())),
                )
                print(f"[setup_coordinator_dev] DEV-Job {subj_col}=18 für 'paul' (id={paul_id}) angelegt")
            else:
                print(f"[setup_coordinator_dev] DEV-Job {subj_col}=18 bereits vorhanden — übersprungen")
            con.commit()
        else:
            print("[setup_coordinator_dev] WARNING: 'paul' nicht in investigators — kein Job angelegt")

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
        # M019-robust (Build 469): Spaltenname dynamisch — kein Crash auf
        # einer bereits migrierten DB (subject_id statt user_id).
        subj_col = _subject_column(con, "scrape_jobs")
        jobs = con.execute(
            f"SELECT id, {subj_col}, username, status, assigned_to FROM scrape_jobs"
        ).fetchall()
        print(f"\n[setup_coordinator_dev] scrape_jobs ({len(jobs)} Einträge):")
        for j in jobs:
            print(f"  id={j[0]}  {subj_col}={j[1]}  username={j[2]}  status={j[3]}  assigned_to={j[4]}")
        print(f"\n[setup_coordinator_dev] scrape_jobs.assigned_to: vorhanden ✓")
        print("[setup_coordinator_dev] Abgeschlossen — keine Fehler.")

    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="coordinator.db DEV-Bootstrap (Baustelle 5/7 Vorarbeit)",
        epilog=cli_epilog.epilog("setup_coordinator_dev"),
        formatter_class=cli_epilog.HilfeFormat,
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

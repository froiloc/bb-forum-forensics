# =============================================================================
# management/migrations/coordinator/m007_backups.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Migration M007 — coordinator.db (ADDITIV)
#   Legt die 'backups'-Registry an: EINE Zeile pro gesicherter Datenbank pro
#   Lauf (feingranular, jede Kopie ist ein Belegstueck; mc 2026-07-10, Frage 1).
#   Jede Zeile koppelt per audit_seq an genau EINEN BACKUP_CREATED-Beleg des
#   Laufs (der Lauf ist ein gemeinsamer Prozess fuer alle DBs; mc Frage 2),
#   analog rbac_grant/case_events (audit_seq NOT NULL -> audit_log(seq)).
#
#   Beleg: Bauplan_Baustelle7_Management_v1_1.md §11 ('backups'-Registry,
#          BACKUP_CREATED); m005-Prinzip (additiv, naechste freie Nummer,
#          eingefrorenes Schema, keine Laufzeit-Importe).
#
# IDEMPOTENZ: CREATE TABLE/INDEX IF NOT EXISTS. Zweiter Lauf ist ein No-op
#   (der Runner ueberspringt bereits angewandte Migrationen; die Guards hier
#   sichern zusaetzlich manuelle Wiederholung ab).
#
# ABGRENZUNG: Die Tabelle startet LEER. Zeilen entstehen ausschliesslich ueber
#   den auditierten Schreibpfad (BackupsRepo, Build 354) — nie per Migrations-
#   Seed (audit_seq muss an einen echten Beleg koppeln).
#
# Version: v0.7.354 · Build: 354 · 2026-07-10
# =============================================================================

import logging
import sqlite3

logger = logging.getLogger(__name__)

#: Fortlaufende Migrationsnummer (naechste freie nach m006).
VERSION = 7
NAME = "backups-Registry (Datensicherungs-Belege, audit_seq-gekoppelt)"
#: Additiv -> kein Zeilen-/Spaltenverlust; der Runner ruft keine pre/postcount.
KIND = "additive"

_DDL_BACKUPS = """
CREATE TABLE IF NOT EXISTS backups (
    id             INTEGER PRIMARY KEY,
    run_ts         TEXT    NOT NULL,          -- gemeinsamer Lauf-Zeitstempel (UTC)
    host           TEXT    NOT NULL,          -- Hostname des sichernden Systems
    db_label       TEXT    NOT NULL,          -- 'coordinator', 'evidence_18', ...
    src_path       TEXT    NOT NULL,          -- Quellpfad der DB
    backup_path    TEXT,                      -- Zielpfad der Kopie (NULL bei Fehler)
    sha512         TEXT,                      -- Integritaetssiegel (NULL bei Fehler)
    size           INTEGER NOT NULL DEFAULT 0,-- Groesse der Kopie in Bytes
    user_version   INTEGER NOT NULL DEFAULT 0,-- PRAGMA user_version der Quelle
    integrity_ok   INTEGER NOT NULL,          -- 0/1 (PRAGMA integrity_check auf Kopie)
    error          TEXT,                      -- NULL wenn ok, sonst Klartext-Grund
    manifest_path  TEXT,                      -- Lauf-Manifest (JSON)
    audit_seq      INTEGER NOT NULL           -- Kopplung an BACKUP_CREATED-Beleg
                   REFERENCES audit_log(seq),
    created_at     INTEGER NOT NULL           -- Unix-Sekunden der Registrierung
)
"""

_DDL_IX_BACKUPS = (
    "CREATE INDEX IF NOT EXISTS ix_backups_label_ts "
    "ON backups (db_label, run_ts)"
)


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _index_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone() is not None


def up(con: sqlite3.Connection) -> None:
    # Bereits angewandt? -> INFO-No-op statt Hard-Fail (idempotent).
    if _table_exists(con, "backups") and _index_exists(con, "ix_backups_label_ts"):
        logger.info("M007: 'backups' + Index bereits vorhanden — No-op.")
        return

    con.execute(_DDL_BACKUPS)
    con.execute(_DDL_IX_BACKUPS)

    # Inline-Verifikation (bei Verstoss 'raise' -> ROLLBACK im Runner;
    # kein stiller Teil-Zustand, Grundregel 1).
    if not _table_exists(con, "backups"):
        raise RuntimeError("M007: Tabelle 'backups' fehlt nach up().")
    if not _index_exists(con, "ix_backups_label_ts"):
        raise RuntimeError("M007: Index 'ix_backups_label_ts' fehlt nach up().")

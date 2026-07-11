# =============================================================================
# management/migrations/coordinator/m008_capacity.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Migration M008 — coordinator.db (ADDITIV)
#   Legt die Kapazitaets-Datenbasis an (Datenbasis fuer Prognose/Gantt/Ueberlast;
#   Beleg: Bauplan_Baustelle7_Management_v1_1.md §11.4). Vier Tabellen:
#
#     person_worktime   — Regel-Arbeitszeit je Wochentag (Minuten), datiert
#                          (effective_from/to), Soft-Delete.
#     holiday           — Feiertage (gelten fuer ALLE), region-gescopt.
#     availability_reason — Supervisor-erweiterbarer Grund-Katalog.
#     availability_entry  — Garantie/Einschraenkung je Person/Zeitraum;
#                          genau EINES von value_pct/value_minutes gesetzt.
#
#   Kapazitaet(Zeitraum) = Summe Arbeitstag-Minuten (Wochentag-Wert, sofern kein
#   Feiertag) minus Einschraenkungen im Rahmen der Garantien. Die BERECHNUNG
#   folgt in Build 357; hier nur das Schema.
#
#   Kopplung: JEDE Zeile traegt audit_seq NOT NULL -> audit_log(seq) (mc
#   2026-07-10, Entscheidung 2). Die Tabellen starten LEER; Zeilen entstehen
#   ausschliesslich ueber die auditierten Schreibpfade (Build 356) — auch der
#   availability_reason-Katalog (kein Migrations-Seed; m005-Prinzip).
#
#   Soft-Delete: 'deleted_at' statt DELETE (append-only Historie).
#
# IDEMPOTENZ: CREATE TABLE/INDEX IF NOT EXISTS + Guard (INFO-No-op).
# Version: v0.7.355 · Build: 355 · 2026-07-10
# =============================================================================

import logging
import sqlite3

logger = logging.getLogger(__name__)

VERSION = 8
NAME = "Kapazitaets-Schema (person_worktime/holiday/availability_reason/entry)"
KIND = "additive"

# person_worktime: Regel-Arbeitszeit je Wochentag in Minuten; datiert.
_DDL_WORKTIME = """
CREATE TABLE IF NOT EXISTS person_worktime (
    id             INTEGER PRIMARY KEY,
    person_id      INTEGER NOT NULL REFERENCES person(id),
    mon_min        INTEGER NOT NULL DEFAULT 0,
    tue_min        INTEGER NOT NULL DEFAULT 0,
    wed_min        INTEGER NOT NULL DEFAULT 0,
    thu_min        INTEGER NOT NULL DEFAULT 0,
    fri_min        INTEGER NOT NULL DEFAULT 0,
    sat_min        INTEGER NOT NULL DEFAULT 0,
    sun_min        INTEGER NOT NULL DEFAULT 0,
    effective_from TEXT    NOT NULL,          -- ISO-Datum: ab wann die Regel gilt
    effective_to   TEXT,                      -- NULL = offen
    audit_seq      INTEGER NOT NULL REFERENCES audit_log(seq),
    created_by     INTEGER,                   -- person.id (NULL = System)
    created_at     INTEGER NOT NULL,
    deleted_at     INTEGER                    -- Soft-Delete
)
"""

# holiday: gilt fuer ALLE; region-gescopt (NULL = ueberall).
_DDL_HOLIDAY = """
CREATE TABLE IF NOT EXISTS holiday (
    id         INTEGER PRIMARY KEY,
    day        TEXT    NOT NULL,              -- ISO-Datum
    label      TEXT    NOT NULL,
    region     TEXT,                          -- NULL = ueberall
    audit_seq  INTEGER NOT NULL REFERENCES audit_log(seq),
    created_by INTEGER,
    created_at INTEGER NOT NULL,
    deleted_at INTEGER
)
"""

# availability_reason: Supervisor-erweiterbarer Grund-Katalog.
_DDL_REASON = """
CREATE TABLE IF NOT EXISTS availability_reason (
    code       TEXT    PRIMARY KEY,
    label      TEXT    NOT NULL,
    sort       INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER,
    audit_seq  INTEGER NOT NULL REFERENCES audit_log(seq),
    created_at INTEGER NOT NULL,
    deleted_at INTEGER
)
"""

# availability_entry: Garantie/Einschraenkung je Person/Zeitraum.
# CHECK: kind aus Whitelist; genau EINES von value_pct/value_minutes gesetzt.
_DDL_ENTRY = """
CREATE TABLE IF NOT EXISTS availability_entry (
    id            INTEGER PRIMARY KEY,
    person_id     INTEGER NOT NULL REFERENCES person(id),
    period_start  TEXT    NOT NULL,           -- ISO-Datum
    period_end    TEXT    NOT NULL,
    kind          TEXT    NOT NULL
                  CHECK(kind IN ('garantie','einschraenkung')),
    value_pct     INTEGER,
    value_minutes INTEGER,
    reason_code   TEXT    REFERENCES availability_reason(code),
    note          TEXT,
    audit_seq     INTEGER NOT NULL REFERENCES audit_log(seq),
    created_by    INTEGER,
    created_at    INTEGER NOT NULL,
    updated_at    INTEGER,
    deleted_at    INTEGER,
    CHECK((value_pct IS NULL) <> (value_minutes IS NULL))
)
"""

_INDICES = (
    ("ix_worktime_person",
     "CREATE INDEX IF NOT EXISTS ix_worktime_person "
     "ON person_worktime (person_id, effective_from)"),
    ("ix_holiday_day",
     "CREATE INDEX IF NOT EXISTS ix_holiday_day ON holiday (day)"),
    ("ix_availability_person",
     "CREATE INDEX IF NOT EXISTS ix_availability_person "
     "ON availability_entry (person_id, period_start)"),
)

_TABLES = ("person_worktime", "holiday", "availability_reason",
           "availability_entry")


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
    # Bereits vollstaendig vorhanden? -> INFO-No-op (idempotent).
    if (all(_table_exists(con, t) for t in _TABLES)
            and all(_index_exists(con, ix) for ix, _ in _INDICES)):
        logger.info("M008: Kapazitaets-Schema bereits vorhanden — No-op.")
        return

    con.execute(_DDL_WORKTIME)
    con.execute(_DDL_HOLIDAY)
    con.execute(_DDL_REASON)
    con.execute(_DDL_ENTRY)
    for _name, ddl in _INDICES:
        con.execute(ddl)

    # Inline-Verifikation (Verstoss -> raise -> ROLLBACK im Runner;
    # kein stiller Teil-Zustand, Grundregel 1).
    for t in _TABLES:
        if not _table_exists(con, t):
            raise RuntimeError("M008: Tabelle '%s' fehlt nach up()." % t)
    for ix, _ddl in _INDICES:
        if not _index_exists(con, ix):
            raise RuntimeError("M008: Index '%s' fehlt nach up()." % ix)

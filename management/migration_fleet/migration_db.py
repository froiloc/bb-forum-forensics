# =============================================================================
# management/migration_fleet/migration_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Kapselt die zentrale Betriebs-Datenbank migration.db. Diese enthaelt
#   KEINEN Beweisinhalt (wie coordinator.db) und ist aus den Per-DB-
#   schema_migrations plus den signierten Phasen-Artefakten rekonstruierbar —
#   also kein Single Point of Failure (Leitfaden v0.2 Paragraph 1/6.4).
#
#   Drei Tabellen (Leitfaden v0.2 Paragraph 6.1-6.3):
#     - migration_catalog : deklarativer Soll-Zustand je DB-Art
#     - db_registry       : Flotten-Inventar (welche DB-Datei, welche Version)
#     - migration_runs    : append-only, hash-verkettetes Lauf-Ledger
#
#   Build 316 erstellt alle drei Tabellen und schreibt catalog + db_registry.
#   In migration_runs wird in diesem Build NOCH NICHT geschrieben — das
#   Schreiben (mit Hash-Verkettung) gehoert zur Migrations-AUSFUEHRUNG und
#   kommt im Folge-Build (Engine-Generalisierung). Die Tabelle wird hier
#   bereits angelegt, damit das Schema vollstaendig ist.
#
# Beleg: Datenmigrationsleitfaden_AIW.md v0.2 Paragraph 6, mc 2026-07-03.
# Version: v0.7.316 · Build: 316 · 2026-07-03
# =============================================================================

import sqlite3
from dataclasses import dataclass
from typing import List, Optional

# migration_catalog: Soll-Migrationen je DB-Art. checksum = SHA256 des
# m###-Skripts (identisch zu MigrationRunner._module_checksum, damit Katalog
# und Engine dieselbe Pruefsumme fuehren).
_DDL_CATALOG = """
CREATE TABLE IF NOT EXISTS migration_catalog (
    db_kind         TEXT    NOT NULL,
    version         INTEGER NOT NULL,
    name            TEXT    NOT NULL,
    checksum        TEXT    NOT NULL,
    kind            TEXT    NOT NULL CHECK(kind IN ('additive','destructive')),
    requires_backup INTEGER NOT NULL DEFAULT 1,
    depends_on      INTEGER,
    PRIMARY KEY(db_kind, version)
)
"""

# db_registry: Inventar der konkreten DB-Dateien. uid ist NULL fuer nicht-
# nutzerbezogene DBs (coordinator/default/templates). Da SQLite mehrere NULLs
# in einem PRIMARY KEY zulaesst, sichert ein funktionaler UNIQUE-Index die
# Eindeutigkeit inkl. NULL ueber IFNULL(uid,-1) ab; der Upsert nutzt genau
# diese Normalisierung (kein Duplikat je (db_kind, uid|NULL)).
_DDL_REGISTRY = """
CREATE TABLE IF NOT EXISTS db_registry (
    db_kind          TEXT    NOT NULL,
    uid              INTEGER,
    path             TEXT    NOT NULL,
    current_version  INTEGER NOT NULL DEFAULT 0,
    last_verified_at INTEGER,
    last_status      TEXT
)
"""
_DDL_REGISTRY_IDX = """
CREATE UNIQUE INDEX IF NOT EXISTS db_registry_key
    ON db_registry(db_kind, IFNULL(uid, -1))
"""

# migration_runs: append-only, hash-verkettet (Schreiben erst im Ausfuehrungs-
# Build). prev_hash/row_hash bilden die Kette analog audit_log.
_DDL_RUNS = """
CREATE TABLE IF NOT EXISTS migration_runs (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    db_kind      TEXT    NOT NULL,
    uid          INTEGER,
    from_version INTEGER NOT NULL,
    to_version   INTEGER NOT NULL,
    started_at   INTEGER NOT NULL,
    finished_at  INTEGER,
    status       TEXT    NOT NULL,
    pre_sha512   TEXT,
    post_sha512  TEXT,
    backup_path  TEXT,
    operator     TEXT,
    verifier     TEXT,
    prev_hash    TEXT    NOT NULL,
    row_hash     TEXT    NOT NULL
)
"""


@dataclass(frozen=True)
class CatalogEntry:
    db_kind: str
    version: int
    name: str
    checksum: str
    kind: str
    requires_backup: int
    depends_on: Optional[int]


@dataclass(frozen=True)
class RegistryEntry:
    db_kind: str
    uid: Optional[int]
    path: str
    current_version: int
    last_verified_at: Optional[int]
    last_status: Optional[str]


class MigrationDb:
    """Zugriff auf die zentrale migration.db (Katalog, Inventar, Ledger)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row

    # ---------------------------------------------------------------- Schema
    def ensure_schema(self) -> None:
        """Legt alle drei Tabellen (+ Registry-Index) idempotent an."""
        self._con.execute(_DDL_CATALOG)
        self._con.execute(_DDL_REGISTRY)
        self._con.execute(_DDL_REGISTRY_IDX)
        self._con.execute(_DDL_RUNS)

    # --------------------------------------------------------------- Catalog
    def upsert_catalog_entry(self, entry: CatalogEntry) -> None:
        """Fuegt einen Katalogeintrag ein oder ersetzt ihn (PK db_kind, version)."""
        self._con.execute(
            "INSERT OR REPLACE INTO migration_catalog "
            "(db_kind, version, name, checksum, kind, requires_backup, depends_on) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (entry.db_kind, entry.version, entry.name, entry.checksum,
             entry.kind, entry.requires_backup, entry.depends_on),
        )

    def list_catalog(self, db_kind: Optional[str] = None) -> List[CatalogEntry]:
        """Katalogeintraege (optional je DB-Art), aufsteigend nach Version."""
        if db_kind is None:
            rows = self._con.execute(
                "SELECT * FROM migration_catalog ORDER BY db_kind, version"
            ).fetchall()
        else:
            rows = self._con.execute(
                "SELECT * FROM migration_catalog WHERE db_kind = ? "
                "ORDER BY version", (db_kind,)
            ).fetchall()
        return [CatalogEntry(
            db_kind=r["db_kind"], version=r["version"], name=r["name"],
            checksum=r["checksum"], kind=r["kind"],
            requires_backup=r["requires_backup"], depends_on=r["depends_on"],
        ) for r in rows]

    # -------------------------------------------------------------- Registry
    def upsert_registry_entry(self, entry: RegistryEntry) -> None:
        """
        Traegt eine DB-Datei ins Inventar ein. Manueller Upsert ueber die
        IFNULL(uid,-1)-Normalisierung (siehe _DDL_REGISTRY_IDX), damit uid=NULL
        (nicht-nutzerbezogene DBs) nicht dupliziert wird.
        """
        self._con.execute(
            "DELETE FROM db_registry "
            "WHERE db_kind = ? AND IFNULL(uid, -1) = IFNULL(?, -1)",
            (entry.db_kind, entry.uid),
        )
        self._con.execute(
            "INSERT INTO db_registry "
            "(db_kind, uid, path, current_version, last_verified_at, last_status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (entry.db_kind, entry.uid, entry.path, entry.current_version,
             entry.last_verified_at, entry.last_status),
        )

    def list_registry(self, db_kind: Optional[str] = None) -> List[RegistryEntry]:
        if db_kind is None:
            rows = self._con.execute(
                "SELECT * FROM db_registry ORDER BY db_kind, IFNULL(uid, -1)"
            ).fetchall()
        else:
            rows = self._con.execute(
                "SELECT * FROM db_registry WHERE db_kind = ? "
                "ORDER BY IFNULL(uid, -1)", (db_kind,)
            ).fetchall()
        return [RegistryEntry(
            db_kind=r["db_kind"], uid=r["uid"], path=r["path"],
            current_version=r["current_version"],
            last_verified_at=r["last_verified_at"], last_status=r["last_status"],
        ) for r in rows]

    # ------------------------------------------------------------------ Runs
    def list_runs(self) -> List[sqlite3.Row]:
        """Liest das Lauf-Ledger (Schreiben erst im Ausfuehrungs-Build)."""
        return self._con.execute(
            "SELECT * FROM migration_runs ORDER BY seq"
        ).fetchall()

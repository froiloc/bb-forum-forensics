# =============================================================================
# management/migrations/runner.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Versioniertes, forward-only Migrations-Gerüst je schreibbarer Datenbank.
#   Führt ausstehende Migrationen geordnet, idempotent und transaktional aus und
#   protokolliert jede angewandte Migration in der Registry 'schema_migrations'
#   SOWIE — sofern ein AuditLog übergeben ist — in der Hash-Kette (MIGRATION_APPLIED).
#
# Eigenschaften (Beleg: Bauplan B7 v0.2 §2.7/§2.8):
#   - forward-only (keine Down-Migrations; Abwärtskompatibilität projektweit
#     nicht gefordert).
#   - idempotent: bereits angewandte Migrationen werden übersprungen.
#   - Default-Regel additiv & datenneutral; destruktive Migrationen führen
#     row_count_before/after und können eine Invariante (verify) erzwingen.
#   - WAL-Checkpoint(TRUNCATE) vor jeder Migration (nicht-fatal, falls geblockt).
#   - jede Migration läuft in EINER Transaktion (BEGIN IMMEDIATE). Kann die
#     Schreibsperre nicht erlangt werden (z. B. offene Ermittler-Verbindungen),
#     bricht die Migration sauber ab — KEIN Teilzustand.
#   - checksum (sha256 des Migrationsmoduls) erkennt nachträglich geänderte,
#     bereits angewandte Module (Warnung, keine Neuanwendung).
#
# Migrationsmodul-Vertrag (jede Klasse/jedes Modul eigene Datei, Grundregel 10):
#   VERSION : int           (fortlaufend je DB)
#   NAME    : str
#   KIND    : str           ('additive' | 'destructive')
#   up(con) : None          (führt die Schemaänderung aus)
#   optional precount(con)->int, postcount(con)->int, verify(con, before, after)
#
# Version: v0.7.306 · Build: 306 · 2026-07-01
# =============================================================================

import hashlib
import importlib
import logging
import pkgutil
import sqlite3
import time
from pathlib import Path
from typing import List, Optional

from management.audit.audit_log import AuditLog
from management.audit.event_types import EventType

logger = logging.getLogger(__name__)


def discover(package) -> list:
    """
    Findet Migrationsmodule (m<NNN>_*.py) in einem Paket und liefert sie nach
    VERSION sortiert. Beispiel: discover(management.migrations.coordinator).
    """
    mods = []
    for info in pkgutil.iter_modules(package.__path__):
        name = info.name
        if name.startswith("m") and name[1:4].isdigit():
            mods.append(importlib.import_module("%s.%s" % (package.__name__, name)))
    return sorted(mods, key=lambda m: m.VERSION)


class MigrationRunner:
    """Wendet ausstehende Migrationen einer Datenbank geordnet an."""

    DDL_REGISTRY = """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version           INTEGER PRIMARY KEY,
        name              TEXT    NOT NULL,
        kind              TEXT    NOT NULL CHECK(kind IN ('additive','destructive')),
        checksum          TEXT    NOT NULL,
        applied_at        INTEGER NOT NULL,
        row_count_before  INTEGER,
        row_count_after   INTEGER
    )
    """

    def __init__(
        self,
        con: sqlite3.Connection,
        migrations: List,
        *,
        audit: Optional[AuditLog] = None,
        deployed_by: Optional[str] = None,
    ) -> None:
        self._con = con
        # Explizite Transaktionssteuerung: Autocommit-Modus, wir setzen
        # BEGIN IMMEDIATE / COMMIT / ROLLBACK selbst.
        self._con.isolation_level = None
        self._migrations = sorted(migrations, key=lambda m: m.VERSION)
        self._audit = audit
        self._deployed_by = deployed_by

    # --------------------------------------------------------------- Registry
    def ensure_registry(self) -> None:
        self._con.execute(self.DDL_REGISTRY)

    def current_version(self) -> int:
        try:
            row = self._con.execute(
                "SELECT MAX(version) AS v FROM schema_migrations"
            ).fetchone()
        except sqlite3.OperationalError:
            return 0
        if row is None:
            return 0
        value = row[0]
        return int(value) if value is not None else 0

    # -------------------------------------------------------------------- Run
    def run(self) -> List[int]:
        """
        Wendet alle ausstehenden Migrationen an. Liefert die Liste der neu
        angewandten Versionsnummern (leer = nichts zu tun / bereits aktuell).
        """
        self.ensure_registry()
        current = self.current_version()
        applied: List[int] = []
        for mod in self._migrations:
            if mod.VERSION <= current:
                self._check_checksum(mod)
                continue
            self._apply(mod)
            applied.append(mod.VERSION)
        if applied:
            logger.info("Migrationen angewandt: %s", applied)
        else:
            logger.debug("Keine ausstehenden Migrationen (Version %d).", current)
        return applied

    # ------------------------------------------------------------------ Apply
    def _apply(self, mod) -> None:
        self._checkpoint()
        con = self._con
        kind = getattr(mod, "KIND", "additive")

        con.execute("BEGIN IMMEDIATE")
        try:
            before = None
            after = None
            if kind == "destructive" and hasattr(mod, "precount"):
                before = mod.precount(con)

            mod.up(con)

            if kind == "destructive" and hasattr(mod, "postcount"):
                after = mod.postcount(con)
            if kind == "destructive" and hasattr(mod, "verify"):
                # Invariante prüfen; wirft bei Verletzung -> ROLLBACK.
                mod.verify(con, before, after)

            checksum = self._module_checksum(mod)
            con.execute(
                "INSERT INTO schema_migrations "
                "(version, name, kind, checksum, applied_at, "
                " row_count_before, row_count_after) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (mod.VERSION, mod.NAME, kind, checksum, int(time.time()),
                 before, after),
            )

            if self._audit is not None:
                self._audit.append(
                    event_type=EventType.MIGRATION_APPLIED,
                    actor_id=None,  # System (Deploy-Zeit, kein eingeloggter Ermittler)
                    target_type="migration",
                    target_id=str(mod.VERSION),
                    payload={
                        "name": mod.NAME,
                        "kind": kind,
                        "checksum": checksum,
                        "row_count_before": before,
                        "row_count_after": after,
                        "deployed_by": self._deployed_by,
                    },
                )

            con.execute("COMMIT")
            logger.info("Migration M%03d '%s' angewandt.", mod.VERSION, mod.NAME)
        except Exception:
            con.execute("ROLLBACK")
            logger.exception(
                "Migration M%03d fehlgeschlagen — ROLLBACK, kein Teilzustand.",
                mod.VERSION,
            )
            raise

    # ------------------------------------------------------------- Checkpoint
    def _checkpoint(self) -> None:
        """WAL in Hauptdatei falten (nicht-fatal, falls geblockt/kein WAL)."""
        try:
            self._con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError as exc:
            logger.warning(
                "wal_checkpoint(TRUNCATE) nicht möglich (nicht-fatal): %s", exc
            )

    # --------------------------------------------------------------- Checksum
    @staticmethod
    def _module_checksum(mod) -> str:
        path = Path(mod.__file__)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _check_checksum(self, mod) -> None:
        row = self._con.execute(
            "SELECT checksum FROM schema_migrations WHERE version = ?",
            (mod.VERSION,),
        ).fetchone()
        if row is None:
            return
        stored = row[0]
        current = self._module_checksum(mod)
        if stored != current:
            logger.warning(
                "Migration M%03d: Checksumme weicht ab — Modul nachträglich "
                "geändert? gespeichert=%s aktuell=%s",
                mod.VERSION, stored, current,
            )

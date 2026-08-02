# =============================================================================
# management/migration_fleet/planner.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   DRY-RUN-Planner (Leitfaden v0.2 Paragraph 9). Berechnet je Ziel-Instanz die
#   ausstehende, geordnete Migrationsmenge aus:
#     - SOLL: migration_catalog (migration.db), je DB-Art
#     - IST : die DB-eigene schema_migrations der konkreten Instanz
#             (autoritativer Zustand, selbstbeschreibend — Paragraph 6.4)
#
#   Der Planner LIEST ausschliesslich: er oeffnet jede Instanz, ermittelt deren
#   aktuelle Version und listet die Katalog-Migrationen mit hoeherer Version.
#   Er fuehrt NICHTS aus, veraendert keine Instanz und schreibt NICHT ins
#   Ledger. Ausfuehrung + Backup/Verify + Ledger kommen im Folge-Build.
#
# Beleg: management/migrations/runner.py (schema_migrations, MAX(version)),
#        Datenmigrationsleitfaden_AIW.md v0.2 Paragraph 9, mc 2026-07-03.
# Version: v0.7.316 · Build: 316 · 2026-07-03
# =============================================================================

import sqlite3
from dataclasses import dataclass
from typing import List, Optional

from management.migration_fleet.migration_db import CatalogEntry, MigrationDb


@dataclass(frozen=True)
class TargetDb:
    """Eine zu pruefende DB-Instanz."""
    db_kind: str
    path: str
    uid: Optional[int] = None


@dataclass(frozen=True)
class InstancePlan:
    """Geplante (noch nicht ausgefuehrte) Migrationsschritte einer Instanz."""
    db_kind: str
    uid: Optional[int]
    path: str
    current_version: int
    pending: List[CatalogEntry]       # aufsteigend nach Version
    note: Optional[str] = None        # z. B. "keine Migrationen im Katalog"

    @property
    def up_to_date(self) -> bool:
        return not self.pending


def read_instance_version(path: str) -> int:
    """
    Liest die aktuelle Schema-Version einer Instanz aus deren eigener
    schema_migrations (MAX(version)). Fehlt die Tabelle (z. B. frische
    Beweis-DB ohne Registry), gilt Version 0 — dann sind alle Katalog-
    Migrationen ausstehend.

    BUILD 649 (Vorgang f51fd838): NUR LESEND geoeffnet - vorher stand "rein
    lesend" nur im Text. GEMESSEN: Auf einer nicht vorhandenen Datei lieferte
    die Funktion '0' UND legte die Datei an. 'Version 0' heisst 'alle
    Migrationen ausstehend' - der Planer haette also fuer eine Datenbank, die
    es gar nicht gibt, den vollen Migrationsweg geplant.
    """
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        con.isolation_level = None
        row = con.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()
        if row is None or row[0] is None:
            return 0
        return int(row[0])
    except sqlite3.OperationalError:
        # schema_migrations existiert nicht -> Instanz noch nicht migriert.
        return 0
    finally:
        con.close()


class MigrationPlanner:
    """Erstellt Dry-Run-Migrationsplaene aus Katalog (Soll) und Instanz (Ist)."""

    def __init__(self, mdb: MigrationDb) -> None:
        self._mdb = mdb

    def plan_instance(self, target: TargetDb) -> InstancePlan:
        catalog = self._mdb.list_catalog(target.db_kind)  # aufsteigend
        current = read_instance_version(target.path)
        if not catalog:
            return InstancePlan(
                db_kind=target.db_kind, uid=target.uid, path=target.path,
                current_version=current, pending=[],
                note="keine Migrationen im Katalog fuer db_kind=%s "
                     "(catalog-sync ausgefuehrt?)" % target.db_kind,
            )
        pending = [e for e in catalog if e.version > current]
        return InstancePlan(
            db_kind=target.db_kind, uid=target.uid, path=target.path,
            current_version=current, pending=pending,
        )

    def plan(self, targets: List[TargetDb]) -> List[InstancePlan]:
        """Dry-Run-Plan fuer mehrere Instanzen. Reine Leseoperation."""
        return [self.plan_instance(t) for t in targets]

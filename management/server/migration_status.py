# =============================================================================
# management/server/migration_status.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# MigrationStatusCheck — vergleicht beim Serverstart den in coordinator.db
# ANGEWANDTEN Migrationsstand (schema_migrations) mit den im Code VORHANDENEN
# Migrationsmodulen (management/migrations/coordinator/m###).
#
# ANLASS (Betriebsvorfall, Build 375/376): Migration m009 (evidence_scan_cache)
#   war ausgeliefert, aber in der produktiven coordinator.db nie angewandt —
#   Migrationen laufen NICHT beim Serverstart, sondern ueber das eigene CLI
#   'python -m management.migrate'. Folge: der Berichts-Scan-Cache fiel aus und
#   protokollierte je Fall eine beilaeufige Warnung ("no such table:
#   evidence_scan_cache"). Nichts ging verloren (der Cache ist bewusst nur ein
#   Beschleuniger), aber der Zustand war leicht zu uebersehen.
#
# ENTSCHEIDUNG (mc 2026-07-10): Der Server MIGRIERT NICHT SELBST. Das Anwenden
#   von Migrationen bleibt eine bewusste, protokollierte Handlung (Beleg im
#   Audit-Log, deployed_by). Der Server WARNT nur — dafuer aber deutlich, an der
#   sichtbarsten Stelle (Start), unter Nennung des exakten Befehls.
#
# Grundregel 1: Ein unvollstaendiger Migrationsstand wird nicht verschwiegen.
# Version: v0.7.376 · Build: 376 · 2026-07-10
# =============================================================================

import sqlite3
from typing import List, Optional

import management.migrations.coordinator as coordinator_migrations
from management.migrations.runner import discover

# Der Befehl, den der Betreiber ausfuehren muss. Zentral definiert, damit
# Meldung und Dokumentation nicht auseinanderlaufen.
MIGRATE_COMMAND = "python -m management.migrate --deployed-by <KENNUNG>"


class MigrationStatus:
    """Ergebnis der Migrationsstand-Pruefung (reines Datenobjekt)."""

    def __init__(self, applied: List[int], available: List[int]) -> None:
        self.applied = sorted(applied)
        self.available = sorted(available)

    @property
    def pending(self) -> List[int]:
        """Vorhandene, aber NICHT angewandte Migrationen."""
        return [v for v in self.available if v not in set(self.applied)]

    @property
    def ok(self) -> bool:
        return not self.pending

    @property
    def missing_registry(self) -> bool:
        """schema_migrations fehlt ganz -> die DB ist nicht initialisiert."""
        return not self.applied and bool(self.available)


class MigrationStatusCheck:
    """Ermittelt den Migrationsstand einer coordinator.db (rein lesend)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def status(self) -> MigrationStatus:
        available = [m.VERSION for m in discover(coordinator_migrations)]
        applied: List[int] = []
        try:
            rows = self._con.execute(
                "SELECT version FROM schema_migrations").fetchall()
            applied = [int(r[0]) for r in rows]
        except sqlite3.Error:
            # Registry fehlt -> applied bleibt leer (missing_registry greift).
            applied = []
        return MigrationStatus(applied, available)

    @staticmethod
    def warning_lines(status: MigrationStatus) -> List[str]:
        """
        Mehrzeilige, DEUTLICHE Startwarnung inkl. des exakten Befehls.
        Leere Liste, wenn alles angewandt ist.
        """
        if status.ok:
            return []
        pending = ", ".join("m%03d" % v for v in status.pending)
        bar = "!" * 72
        lines = [
            bar,
            "!! ACHTUNG: coordinator.db ist NICHT auf dem aktuellen Stand.",
            "!!",
            "!! Ausstehende Migration(en): %s" % pending,
            "!! Angewandt: %s"
            % (", ".join("m%03d" % v for v in status.applied) or "(keine)"),
            "!!",
            "!! Folge: Funktionen, die auf diesen Migrationen aufbauen, "
            "arbeiten",
            "!! eingeschraenkt oder gar nicht (z. B. der Berichts-Scan-Cache).",
            "!!",
            "!! Bitte Migrationen anwenden und den Server neu starten:",
            "!!",
            "!!     %s" % MIGRATE_COMMAND,
            "!!",
            "!! Der Server migriert BEWUSST NICHT selbst: das Anwenden von",
            "!! Migrationen ist eine kontrollierte, im Audit-Log belegte "
            "Handlung.",
            bar,
        ]
        if status.missing_registry:
            lines.insert(2, "!! Die Registry 'schema_migrations' fehlt ganz — "
                            "die Datenbank ist nicht initialisiert.")
        return lines

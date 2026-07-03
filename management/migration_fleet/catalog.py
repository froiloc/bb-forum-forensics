# =============================================================================
# management/migration_fleet/catalog.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Synchronisiert den migration_catalog aus dem CODE (den m###-Skripten je
#   DB-Art) und erkennt Katalog/Code-DRIFT. Die Pruefsumme ist SHA256 des
#   Migrationsmodul-Quelltexts — es wird BEWUSST MigrationRunner._module_checksum
#   WIEDERVERWENDET (nicht dupliziert), damit Katalog und Engine garantiert
#   dieselbe Pruefsumme fuehren (Leitfaden v0.2 Paragraph 6.4).
#
#   DB-Arten mit Migrationspaket: derzeit nur 'coordinator' (m001-m004). Die
#   Beweis-DB-Arten (evidence/forensic/assets) haben noch KEIN Migrationspaket
#   — fuer sie ist der Katalog leer (ehrlich, kein stiller Default). Sie kommen
#   im Engine-Generalisierungs-Build hinzu, indem sie in DB_KIND_PACKAGES
#   eingetragen werden.
#
# Beleg: management/migrations/runner.py (_module_checksum, discover),
#        Datenmigrationsleitfaden_AIW.md v0.2 Paragraph 6.4, mc 2026-07-03.
# Version: v0.7.316 · Build: 316 · 2026-07-03
# =============================================================================

from dataclasses import dataclass, field
from typing import Dict, List

import management.migrations.coordinator as _coordinator_pkg
from management.migration_fleet import EVIDENCE_DB_KINDS
from management.migration_fleet.migration_db import CatalogEntry, MigrationDb
from management.migrations.runner import MigrationRunner, discover

#: Abbildung DB-Art -> Migrationspaket. Erweiterbar; die Beweis-DB-Arten
#: werden hier eingetragen, sobald ihre m###-Pakete existieren.
DB_KIND_PACKAGES = {
    "coordinator": _coordinator_pkg,
}


def _requires_backup(db_kind: str, kind: str) -> int:
    """
    Backup-Politik je Katalogeintrag (Initialpolitik, justierbar):
      - Beweis-DB-Arten (evidence/forensic/assets): IMMER Backup (Beweisschutz).
      - coordinator/default/templates: nur bei destruktiven Migrationen
        (dort kann kein Ermittler-Wissen verloren gehen — Projektregel).
    """
    if db_kind in EVIDENCE_DB_KINDS:
        return 1
    return 1 if kind == "destructive" else 0


@dataclass
class ReconcileReport:
    """Ergebnis des Katalog/Code-Abgleichs je DB-Art."""
    ok: List[str] = field(default_factory=list)              # "db_kind:version"
    modified: List[str] = field(default_factory=list)        # Pruefsumme weicht ab
    uncataloged: List[str] = field(default_factory=list)     # im Code, nicht im Katalog
    missing_module: List[str] = field(default_factory=list)  # im Katalog, kein Modul

    @property
    def has_drift(self) -> bool:
        return bool(self.modified or self.uncataloged or self.missing_module)


class CatalogReconciler:
    """Synchronisiert und prueft den migration_catalog gegen den Code."""

    def __init__(self, mdb: MigrationDb,
                 db_kind_packages: Dict = None) -> None:
        self._mdb = mdb
        self._packages = (db_kind_packages if db_kind_packages is not None
                          else DB_KIND_PACKAGES)

    def _code_migrations(self, db_kind: str):
        """(version -> module) aller m###-Module einer DB-Art, per discover()."""
        pkg = self._packages.get(db_kind)
        if pkg is None:
            return {}
        return {m.VERSION: m for m in discover(pkg)}

    def sync(self) -> int:
        """
        Traegt alle im Code vorhandenen Migrationen in den Katalog ein
        (INSERT OR REPLACE). Gibt die Anzahl synchronisierter Eintraege zurueck.
        Bestehende Katalogeintraege mit gleicher (db_kind, version) werden mit
        der aktuellen Pruefsumme ueberschrieben — der Katalog folgt dem Code.
        """
        count = 0
        for db_kind in self._packages:
            for version, mod in sorted(self._code_migrations(db_kind).items()):
                checksum = MigrationRunner._module_checksum(mod)
                kind = getattr(mod, "KIND", "additive")
                self._mdb.upsert_catalog_entry(CatalogEntry(
                    db_kind=db_kind,
                    version=version,
                    name=mod.NAME,
                    checksum=checksum,
                    kind=kind,
                    requires_backup=_requires_backup(db_kind, kind),
                    depends_on=None,   # lineare m###-Folge -> Ordnung ueber version
                ))
                count += 1
        return count

    def reconcile(self) -> ReconcileReport:
        """
        Vergleicht Katalog (Soll, migration.db) mit Code (Ist, m###-Module):
          - OK              : Version in beidem, Pruefsumme gleich
          - MODIFIED        : Version in beidem, Pruefsumme verschieden
                              (Modul nachtraeglich geaendert -> Katalog veraltet)
          - UNCATALOGED     : Version im Code, aber nicht im Katalog
          - MISSING_MODULE  : Version im Katalog, aber kein Modul im Code
        Kein stilles Uebergehen (Grundregel 1): jede Abweichung wird gemeldet.
        """
        report = ReconcileReport()
        for db_kind in self._packages:
            code = self._code_migrations(db_kind)
            code_sums = {v: MigrationRunner._module_checksum(m)
                         for v, m in code.items()}
            cat = {e.version: e.checksum
                   for e in self._mdb.list_catalog(db_kind)}

            for version in sorted(set(code_sums) | set(cat)):
                tag = "%s:%d" % (db_kind, version)
                in_code = version in code_sums
                in_cat = version in cat
                if in_code and in_cat:
                    if code_sums[version] == cat[version]:
                        report.ok.append(tag)
                    else:
                        report.modified.append(tag)
                elif in_code and not in_cat:
                    report.uncataloged.append(tag)
                else:  # in_cat and not in_code
                    report.missing_module.append(tag)
        return report

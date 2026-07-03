# =============================================================================
# management/migration_fleet/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Paket: Flotten-Migrationsschicht (migration.db).
#   Trennung zu management/migrations/:
#     - management/migrations/       = die m###-Migrationsskripte je DB-Art +
#                                      MigrationRunner (Per-DB-Engine, wendet an).
#     - management/migration_fleet/  = migration.db als KATALOG (Soll je DB-Art),
#                                      INVENTAR (welche Dateien existieren) und
#                                      hash-verkettetes LEDGER (was geschah),
#                                      plus Dry-Run-PLANNER.
#
#   Rollentrennung (Leitfaden v0.2 Paragraph 6.4): Der autoritative
#   "welche Migration ist in DIESER Instanz angewandt"-Zustand bleibt IN der
#   jeweiligen DB (schema_migrations, selbstbeschreibend/gerichtsfest);
#   migration.db ist abgeleitet und rekonstruierbar (kein Single Point of
#   Failure).
#
#   Build 316 liefert: migration.db-Schema (3 Tabellen), Katalog/Code-Abgleich
#   und den Dry-Run-Planner. Das Schreiben ins Ledger (Ausfuehrung) und der
#   Backup+Verify-Harness folgen im naechsten Build (Engine-Generalisierung).
#
# Beleg: Datenmigrationsleitfaden_AIW.md v0.2 Paragraph 6/9, mc 2026-07-03.
# Version: v0.7.316 · Build: 316 · 2026-07-03
# =============================================================================

#: DB-Arten mit Beweisinhalt — Backup ist bei jeder Migration Pflicht
#: (Produktivbetrieb-Regel ab 2026-07-01).
EVIDENCE_DB_KINDS = frozenset({"evidence", "forensic", "assets"})

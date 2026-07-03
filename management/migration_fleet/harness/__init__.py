# =============================================================================
# management/migration_fleet/harness/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Backup-/Verify-Harness (Build 317). Reine Sicherheits-Primitive der
# Leitfaden-Phasen 1-2: konsistentes Backup + Verifikationsmessungen.
#
# STRIKTE ABGRENZUNG (Bauplan Migrations-Ausfuehrung v0.1 §3.1):
#   - fuehrt KEINE Migration aus
#   - fasst KEINE reale Evidenz an (nur synthetische Tests)
#   - schreibt NICHT ins Ledger
#   - trifft KEINE Abnahmeentscheidung (liefert nur Reports)
#   - BackupTool schreibt ausschliesslich die neue Backup-Datei, mutiert die
#     Quelle NIE.
#
# Klassen (je eigene Datei, Grundregel 10):
#   hashing.py   : sha512_file, blob_sha256
#   backup.py    : BackupTool
#   integrity.py : IntegrityChecker
#   rowcount.py  : RowcountVerifier
#   blob.py      : BlobVerifier
#   harness.py   : MigrationHarness (duenne Fassade)
#
# Beleg: Bauplan Migrations-Ausfuehrung v0.1 §3, Datenmigrationsleitfaden_AIW.md
#        v0.2 §3 (Phasen 1-2)/§8, mc 2026-07-03.
# Version: v0.7.317 · Build: 317 · 2026-07-03
# =============================================================================

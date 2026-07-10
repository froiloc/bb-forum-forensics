# Bauplan Build 354 — Backup Welle 0, Teil 3: Registry + Audit + CLI

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 0** (Abschluss Backup)
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11 (`backups`-Registry,
`BACKUP_CREATED`) · m005-Prinzip. **Basis:** 0.7.353. **mc:** 2026-07-10.

---

## 1. Ziel

Welle-0-Backup abschließen: jeden ausgeführten Lauf **auditiert registrieren**
und über ein **CLL** bequem bedienbar machen.

**Entscheidungen (mc):** (1) eine `backups`-Zeile **pro Datei pro Lauf**
(volle Details); (2) **ein** `BACKUP_CREATED`-Beleg **pro Lauf** (ein gemeinsam
angestoßener Prozess), alle Zeilen koppeln daran; (3) CLI direkt mit dabei.

---

## 2. Umfang (geliefert)

- **`management/audit/event_types.py`**: `BACKUP_CREATED = "backup_created"`
  aktiviert + in `ALL`. Append-only Vokabular (nichts umbenannt/entfernt).
- **`management/migrations/coordinator/m007_backups.py`** (`VERSION=7`,
  `KIND="additive"`): Tabelle `backups` (Zeile pro DB pro Lauf) mit
  `audit_seq NOT NULL → audit_log(seq)` + Index `ix_backups_label_ts`. Idempotent
  (IF NOT EXISTS + Guard), Inline-Verifikation. Startet leer.
- **`management/backup/backups_repo.py`** — `BackupsRepo`:
  `record_run(run, actor_id)` schreibt **einen** `BACKUP_CREATED`-Beleg
  (Lauf-Summary als Payload) und je DB eine `backups`-Zeile mit dessen
  `audit_seq` (`after_audit`-Hook → Write+Audit+Registry atomar). Auch
  fehlgeschlagene DBs bekommen eine Zeile (Fehlversuch bleibt belegt).
  `list_backups()` liest.
- **`management/backup/backup_executor.py`** (geändert): `BackupRun` um
  `run_ts`/`host` erweitert.
- **`management/backup/backup_admin.py`** — CLI `plan`/`run`/`list`
  (`main(argv)` testbar; Pfade/Rahmen aus `config.yaml`, `--coordinator-db`
  override, `--actor`).
- **Tests** `tests/test_backups_registry.py` (BR01–BR04, CL01–CL02) +
  `tests/test_management_dashboard.py` (d01-Migrationsliste um 7 ergänzt).

---

## 3. Regression (run_tests.py)

```
pytest : 905 passed, 59 skipped, 3 subtests   (899 + 6)
vitest : 511 passed, 1 skipped, 1 todo (513), 40 Testdateien   (unverändert)
```

---

## 4. Migration / Deploy / Nutzung

`m007` ist **additiv** (kein Datenverlust) und wird beim nächsten
Migrationslauf automatisch angewandt (`MIGRATION_APPLIED` in der Hash-Kette).

CLI:
```
python -m management.backup.backup_admin plan  [--config ./config.yaml]
python -m management.backup.backup_admin run   [--config ./config.yaml] --actor h0a2898
python -m management.backup.backup_admin list  [--config ./config.yaml] [--db-label evidence_18]
```

---

## 5. Stand Welle-0-Backup

**Komplett:** 352 (Config/Planner/Platzprüfung) · 353 (Executor:
`VACUUM INTO`/integrity/SHA512/Manifest/Retention) · 354 (Registry/Audit/CLI).
Nächster Welle-0-Rest laut Bauplan: **Kapazität/Workflow**. (PITR/Restore ist
eine spätere, eigene Ausbaustufe.)

---

*Dokument-Ende · Bauplan Build 354 · 2026-07-10*

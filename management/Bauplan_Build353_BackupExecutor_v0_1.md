# Bauplan Build 353 — Backup Welle 0, Teil 2: Executor

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 0**
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11 (Punkt 7:
`integrity_check` auf Kopie) · `Datenmigrationsleitfaden_AIW.md` v0.2 §4.
**Basis:** 0.7.352.

---

## 1. Ziel

Der **Executor** führt einen von Build 352 geprüften `BackupPlan` aus: pro
Datenbank ein transaktionaler Snapshot (`VACUUM INTO`), Zertifizierung der Kopie
(`integrity_check`), SHA512-Siegel, Retention und ein Lauf-Manifest. Baut auf
`BackupTool` (Build 317) und `BackupPlanner` (Build 352) auf.

**Quellen bleiben read-only** (`VACUUM INTO` liest nur). **Keine Migration.**

---

## 2. Umfang (geliefert)

- **`management/backup/backup_executor.py`** — `BackupExecutor` +
  `BackupItemResult`/`BackupRun`:
  - `run(plan)` **verweigert** bei `plan.ok=False` (Vorabprüfung fehlgeschlagen →
    keine halben Kopien bei voller Platte).
  - Je Quelle: (a) optional `wal_checkpoint(PASSIVE)` je `config.checkpoint`
    (**nie** TRUNCATE; Fehlschlag unkritisch), (b) `VACUUM INTO` via
    `BackupTool.create_backup` (Dateiname `<label>_v<user_version>_<ts>_<host>.
    backup.db`; `version` = `PRAGMA user_version` = forensische Provenienz),
    (c) `PRAGMA integrity_check` auf der **Kopie**, (d) SHA512.
  - **Pro-DB-Fehlerisolation** (Grundregel 1): ein Fehler bei einer DB bricht den
    Lauf nicht ab; jede DB einzeln bilanziert; Gesamt-`ok` nur wenn alle
    erfolgreich **und** integer.
  - **Retention:** je Label die `retention_count` neuesten Generationen behalten,
    ältere löschen (nur Dateien der Namenskonvention).
  - **Manifest:** JSON je Lauf (`manifest_<ts>_<host>.json`, ASCII-only) mit
    `run_ts`/`host`/`ok`, Config-Summary, Je-DB-Ergebnissen, `pruned`.
- **`tests/test_backup_executor.py`** (BE01–BE05): integere Backups + Manifest +
  SHA512-Verify; `user_version` im Dateinamen; Verweigerung bei fehlgeschlagener
  Vorabprüfung; Pro-DB-Fehlerisolation; Retention.

---

## 3. Regression (run_tests.py)

```
pytest : 899 passed, 59 skipped, 3 subtests   (894 + 5)
vitest : 511 passed, 1 skipped, 1 todo (513), 40 Testdateien   (unverändert)
```

---

## 4. Abnahme

In der VM ausführbar: schreibt echte Backups ins konfigurierte `dest_dir`
(Quellen unverändert). Ein bequemes CLI (`backup_admin`) kommt mit Build 354; bis
dahin lässt sich der Executor über ein kurzes Python-Snippet auslösen
(`BackupPlanner(paths, cfg).plan()` → `BackupExecutor(cfg).run(plan)`), das
Manifest im `dest_dir` prüfen.

---

## 5. Nächster Build (354)

`backups`-Registry (additive Migration, nächste freie Nummer, `audit_seq`-
Kopplung) + `BACKUP_CREATED`-Audit-Aktion + `backup_admin`-CLI (`plan`/`run`/
`list`), das Planner + Executor zusammenführt und jeden Lauf registriert.

---

*Dokument-Ende · Bauplan Build 353 · 2026-07-10*

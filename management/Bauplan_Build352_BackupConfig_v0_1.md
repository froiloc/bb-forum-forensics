# Bauplan Build 352 — Backup Welle 0, Teil 1: Konfiguration + Enumeration + Speicherplatz-Vorabprüfung

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 0** (Fundamente)
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11 (Backup/PITR, Pfad
aus `config.yaml`) · §7.5.3 (Speicherplatz-Vorabprüfung). **Basis:** 0.7.351.

---

## 1. Ziel und Split

Fundament der Datensicherung: die **Rahmenbedingungen** in `config.yaml`, die
**Enumeration aller** zu sichernden Datenbanken und die **Speicherplatz-
Vorabprüfung**. Diese Prüfung ist **vorfall-getrieben**: am 2026-07-01 lief die
Platte beim Fallanlegen voll und `default.db` wurde `malformed`. Ein Backup darf
nie begonnen werden, wenn am Ziel nicht genug Platz ist.

**Split (mc 2026-07-10):** 352 = Config + Planner + Platzprüfung (rein
pytest-testbar, **kein Schreiben**) · 353 = Executor (`VACUUM INTO` + integrity +
SHA512 + Manifest + Retention) · 354 = `backups`-Registry (additive Migration) +
`BACKUP_CREATED`-Audit + `backup_admin`-CLI.

**Keine Migration in 352.** Die Backup-Primitive `BackupTool` (Build 317,
`VACUUM INTO` + SHA512) existiert bereits und wird in 353 genutzt.

---

## 2. Umfang (geliefert)

- **`config.yaml`** (getrackt): neue, **ausführlich kommentierte** `backup:`-
  Sektion — `dest_dir` (inkl. UNC-Beispiel), `retention_count`, `min_free_factor`
  (Platzreserve), `checkpoint` (`passive`/`none`, **nie** `truncate`),
  `include_shared_dbs`. Zusätzlich `paths.translations_db` explizit aufgenommen.
- **`core/config_loader.py`**: `_DEFAULTS` um `paths.translations_db` und die
  `backup:`-Defaults erweitert; Zugriff via `cfg.get("backup.*")`.
- **`management/backup/backup_config.py`** — `BackupConfig` (frozen) +
  `from_loader()` mit Typprüfung und klaren Fehlern (`BackupConfigError`);
  `checkpoint="truncate"` wird abgewiesen; `retention>=1`; `factor>0`.
- **`management/backup/backup_planner.py`** — `BackupSource`/`BackupPlan` (DTOs)
  + `BackupPlanner`:
  - `enumerate_sources()`: coordinator immer; shared (default/templates/
    translations) je `include_shared_dbs`; je `*.db` in forensic/evidence/assets
    (Label = Dateiname-Stamm). Fehlende Einzel-DBs **und** fehlende Verzeichnisse
    landen sichtbar in `missing` (Grundregel 1).
  - `plan()`: `required_free = ceil(Gesamtgröße * min_free_factor)`; freier Platz
    via `shutil.disk_usage` am Ziel **oder** (genau eine Ebene) am direkten
    Elternverzeichnis. `ok=False` mit klarer Begründung bei unerreichbarem Ziel,
    keinen Quellen oder zu wenig Platz. **Rein lesend, kein `VACUUM`.**
- **`tests/test_backup_planner.py`** (BC01–BC03, BP01–BP07).

---

## 3. Regression (run_tests.py)

```
pytest : 894 passed, 59 skipped, 3 subtests   (883 + 11 Backup)
vitest : 511 passed, 1 skipped, 1 todo (513), 40 Testdateien   (unverändert)
```

---

## 4. Abnahme (rein lesend)

In der VM ohne Risiko prüfbar (kein Schreiben): einen `BackupPlanner` aus der
realen `config.yaml` konstruieren und `plan()` inspizieren — `sources` listet
alle DBs, `missing` etwaige Lücken, `ok`/`reason` das Ergebnis der Platzprüfung.
(Manuelles Snippet auf Wunsch; im Executor-Build 353 wird das Teil des
`backup_admin`-CLI.)

---

## 5. Nächste Builds

- **353 — Executor:** `VACUUM INTO` je Plan-Eintrag (via `BackupTool`),
  `integrity_check` auf der Kopie, SHA512, Manifest, Retention-Pruning.
- **354 — Registrierung:** `backups`-Registry (additive Migration, nächste freie
  Nummer) + `BACKUP_CREATED`-Audit + `backup_admin`-CLI.

---

*Dokument-Ende · Bauplan Build 352 · 2026-07-10*

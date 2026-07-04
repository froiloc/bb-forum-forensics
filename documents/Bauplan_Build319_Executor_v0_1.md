# Bauplan — Build 319: `schema_migrations`-Erstmigration + Flotten-Executor

## AIW · Migrations-Ausführung, Scheibe 3/4

**Version:** 0.1 (Entwurf; Umsetzung folgt im direkt anschließenden Schritt)
**Build-Bezug:** 318 (Basis)
**Datum:** 2026-07-03
**Status:** ENTWURF
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH

---

## 0. Kontext und bestätigte Entscheidungen (mc)

Scheibe 3/4 verbindet erstmals die Bausteine zu einem Migrationsvorgang:
**Backup (317) → Runner → Verify-Harness (317) → Ledger (318)**. Bestätigt:

1. **Vorwärts-only mit verpflichtendem, verifiziertem Backup.**
2. **Nur synthetische, evidenz-/assets-/forensic-förmige Testdaten;** echte
   Ausführung gegen reale Beweis-DBs bleibt hinter der Vier-Phasen-Zeremonie +
   Vieraugen verriegelt.
3. **`schema_migrations`-Registry als additive `m001` je Beweis-DB-Art**
   (vorab bestätigt).

Belege: `management/migrations/runner.py` (`audit: Optional[AuditLog]=None` →
für Beweis-DBs `audit=None`; `run()` wendet nur `VERSION>current` an);
`management/migration_fleet/{harness,ledger,migration_db,catalog,planner}`;
Datenmigrationsleitfaden_AIW.md v0.2 §3/§6/§8/§10; `evidence_schema_db.sql`,
`assets_schema_db.sql`; mc 2026-07-03.

---

## 1. Baseline-Migration `m001` je Beweis-DB-Art

Neue Pakete: `management/migrations/evidence/`, `.../forensic/`, `.../assets/`,
je mit `__init__.py` und `m001_baseline.py`.

- `VERSION = 1`, `NAME`, `KIND = "additive"`.
- `up(con)`: **dokumentierte Baseline ohne strukturelle Änderung** — die
  Tabellen der Beweis-DBs stammen aus dem Prepper und bleiben unangetastet.
  **Leicht-Guard (schema-agnostisch):** `sqlite_master` muss mindestens eine
  Nutzertabelle enthalten; sonst wird abgebrochen (kein Baselining einer leeren
  oder falschen Datei). Bewusst schema-agnostisch, da für `forensic_*` keine
  eigenständige Schemadatei vorliegt (Beleg §2 des Bauplans Migrations-
  Ausführung v0.1).
- Wirkung: Der Runner erzeugt via `ensure_registry()` die Tabelle
  `schema_migrations` und stempelt Version 1. Damit ist die Beweis-DB
  **selbstbeschreibend** (Leitfaden §6.0) — autoritativer Zustand liegt in der
  DB selbst.

**Katalog:** `DB_KIND_PACKAGES` (catalog.py) wird um `evidence/forensic/assets`
erweitert; `catalog-sync`, `reconcile` und `plan` (Build 316) decken die
Beweis-DB-Arten dann automatisch ab. `requires_backup` ist für diese Arten per
`_requires_backup` bereits `1` (immer sichern).

---

## 2. Flotten-Executor (`management/migration_fleet/executor.py`)

`FleetExecutor(mdb, ledger, *, backup_dir, operator=None)` mit
`execute_instance(target, *, dry_run=True, verifier=None) -> ExecutionResult`.

### 2.1 Gating (mehrschichtig)
- **`dry_run=True` als Default.** Echte Ausführung nur bei ausdrücklichem
  `dry_run=False`.
- **Ohne `backup_dir` → Verweigerung** der Ausführung.
- **Prozedural:** echte Ausführung nur im Rahmen der Leitfaden-Zeremonie +
  Vieraugen; der geführte Companion (Build 320) erzwingt den Ablauf.

### 2.2 Pipeline (armed, pro Instanz isoliert, all-or-nothing)
1. `current = read_instance_version(path)`; `pending` = Katalog-Migrationen mit
   `version > current`. Nichts ausstehend → `up_to_date`.
2. `pre = MigrationHarness.snapshot(path)`.
3. `backup = BackupTool.create_backup(path, backup_dir, db_label, version=current)`
   — **Pflicht**.
4. `ledger.record_start(db_kind, uid, from=current, to=ziel, pre_sha512, backup_path, operator)`.
5. `MigrationRunner(con, [pending-Module], audit=None, deployed_by=operator).run()`
   — `audit=None`, da Beweis-DBs kein `audit_log` führen (Beleg runner.py).
6. `report = MigrationHarness.verify_against(path, pre, expected_deltas={})` —
   Baseline ändert keine Daten, daher **keine** Zeilen-/BLOB-Änderung erlaubt;
   zusätzlich `integrity_check` + `foreign_key_check`.
7. **Erfolg** → `ledger.record_result('ok', post_sha512, ...)`;
   `db_registry` auf Zielversion aktualisieren.
   **Fehler/Ausnahme** → **RESTORE** aus dem Backup (Backupdatei zurückkopieren,
   WAL/SHM entfernen), `ledger.record_result('failed')` **und** `'restored'`,
   **STOP**. Die Instanz ist damit exakt im Ausgangszustand.

### 2.3 Safe-by-design
Pflicht-Backup **+** Verify **+** Auto-Restore **+** vorwärts-only: Selbst bei
versehentlichem `dry_run=False` auf realer Evidenz wird ein fehlerhafter Lauf
zurückgerollt — kein Datenverlust. **Isolation:** eigenes Backup und eigene
Verbindung je Instanz; ein Fehler bei Instanz A berührt Instanz B nicht.

---

## 3. `expected_deltas` (Baseline vs. Zukunft)

Für die Baseline `m001` gilt `expected_deltas={}` (keine Datenänderung), Verify
ist streng. Künftige **daten-transformierende** Migrationen deklarieren ihre
erwarteten Deltas selbst (eigene, spätere Scheibe) — nicht Teil von 319.

---

## 4. Abgrenzung (was 319 NICHT tut)

Keine echte Evidenz in der Lieferung (nur synthetische Tests); kein GPG (kommt
mit Zeremonie/Companion); keine WORM-Archivierung; keine daten-transformierende
Migration; kein Companion (Build 320). Backup-Zielort wird über
`config.yaml → paths.backup_dir` bezogen (wie bestätigt).

---

## 5. Tests (I01–I10, synthetisch, kein reales Beweismaterial)

- **I01** `m001`-Baseline: stempelt Version 1, `schema_migrations` entsteht,
  **keine** Datenänderung; zweiter Lauf idempotent.
- **I02** Baseline-Guard: leere DB (keine Nutzertabelle) → Abbruch.
- **I03** Katalog deckt evidence/forensic/assets nach `sync` ab; `reconcile` ohne Drift.
- **I04** Executor happy path: evidenz-förmige DB v0→v1; Ledger `started`+`ok`;
  `db_registry` aktualisiert; Instanz konsistent (`integrity_check` ok).
- **I05** `dry_run=True`: **nichts** passiert (kein Backup, kein Ledger-Eintrag,
  keine Änderung, Quelle bit-identisch).
- **I06** Backup-Pflicht: ohne `backup_dir` → Verweigerung (Ausführung unterbleibt).
- **I07** Verify-Fehler → **Restore**: eine synthetische „Bad-Migration"
  (entfernt Zeilen) wird vom Harness erkannt; Instanz aus Backup wiederhergestellt
  (SHA512 == Ausgangszustand); Ledger `failed`+`restored`.
- **I08** Ausnahme in `up()` → Restore + Ledger `failed`+`restored`.
- **I09** Isolation: Fehler bei Instanz A lässt Instanz B unberührt (B wird ok).
- **I10** Ledger-Kette nach allen Läufen `verify_chain()` == ok.

Volle Regression (`run_tests.py`) bleibt Pflicht.

---

## 6. Offene Punkte

1. Backup-Aufbewahrung/WORM/GPG-Signatur → Zeremonie/Companion (Build 320).
2. `expected_deltas`-Deklaration für daten-transformierende Migrationen → spätere Scheibe.
3. `forensic_*`-Schemafundstelle weiterhin offen — **nicht blockierend**
   (Baseline und Harness sind schema-agnostisch).

---

## Änderungshistorie

| Version | Datum      | Änderung                                                                 |
| ------- | ---------- | ----------------------------------------------------------------------- |
| 0.1     | 2026-07-03 | Entwurf: Baseline `m001` je Beweis-DB-Art + Flotten-Executor (safe-by-design, gated, synthetisch getestet). Basis mc 2026-07-03 (schema_migrations-Registry bestätigt). |

*Ende Bauplan Build 319 v0.1 — Umsetzung folgt im direkt anschließenden Schritt.*

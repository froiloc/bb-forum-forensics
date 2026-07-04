# MIGRATION.md — Handbuch: Datenmigration der Beweis-Datenbanken

## AIW · Bedienungsanleitung für Administrator:in und Chef-Ermittler:in

**Version:** 1.0
**Build-Bezug:** 321
**Datum:** 2026-07-04
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH

> Dieses Handbuch beschreibt **praktisch**, wie eine Migration durchgeführt wird
> und wie das Werkzeug zu bedienen ist. Der **verbindliche, gerichtsfeste
> Prozess** (Vier-Phasen-Zeremonie, GPG/WORM, Vieraugen) steht im
> `documents/Datenmigrationsleitfaden_AIW.md` (v0.2) und hat im Zweifel Vorrang.

---

## 1. Das Prinzip in Kürze

Seit dem 01.07.2026 (Produktivbetrieb) stehen die Beweis-Datenbanken
`evidence_<uid>.db`, `forensic_<uid>.db`, `assets_<uid>.db` unter
**Migrationsvorbehalt**: Änderungen müssen **verlustfrei** und
**gerichtsfest belegbar** sein. Das Werkzeug setzt dafür fünf Leitideen um:

- **Vorwärts-only mit Pflicht-Backup.** Keine Rückwärts-Migrationen; vor jeder
  Änderung ein verifiziertes Backup (`VACUUM INTO` + SHA512).
- **Selbstbeschreibende Datenbanken.** Jede DB führt ihre eigene Registry
  `schema_migrations` (welche Migration ist hier angewandt). Autoritativ ist
  immer die DB selbst — eine asservierte Kopie belegt ihre Herkunft ohne
  externe Datei.
- **Zentrale `migration.db`** als **Katalog** (Soll-Migrationen je DB-Art),
  **Inventar** (welche DB-Dateien, welche Version) und **hash-verkettetes
  Ledger** (`migration_runs`: was geschah). Sie ist abgeleitet und
  rekonstruierbar — **kein Single Point of Failure**.
- **Safe-by-design-Ausführung.** Pro Instanz: `Snapshot → Backup → Migration →
  Verify → ok` **oder** `→ automatische Wiederherstellung aus dem Backup`. Ein
  fehlerhafter Lauf wird verlustfrei zurückgerollt.
- **Geführter Companion (Teilautomatisierung, keine Vollautomatisierung).**
  Eine Zustandsmaschine mit **Toren**, die den Fortschritt bei Auffälligkeiten
  verweigert und dafür sorgt, dass nichts vergessen wird. Die **Entscheidungen
  und die Gegenzeichnung bleiben beim Menschen** (Vieraugen).

Die **echte Ausführung gegen reale Beweis-DBs** ist bewusst **verriegelt**:
Sie erfolgt nur im Rahmen der Vier-Phasen-Zeremonie mit Vieraugen.

---

## 2. Voraussetzungen

- Dedizierte, vom Produktivnetz **abgeschottete** Maschine (Windows-Cloud-VM,
  Python 3.14).
- `config.yaml` mit den Pfaden:
  - `paths.coordinator_db` — die coordinator.db,
  - `paths.migration_db` — die zentrale migration.db (wird bei Bedarf angelegt),
  - `paths.backup_dir` — Zielverzeichnis für die Pflicht-Backups.
- GPG-Schlüssel der zwei autorisierten Personen (Smartcard/HSM) für die
  Gegenzeichnung.
- **Zwei Personen** (Vieraugen): eine führt aus, eine prüft/gegenzeichnet.

---

## 3. Die Bausteine

- **`migrate.py`** — wendet Migrationen der **coordinator.db** an (Management-
  Datenbank; kein Beweisinhalt).
- **`migration_fleet` (CLI `migration_fleet_admin`)** — die **Flotten**-Schicht
  für die Beweis-DBs: Katalog, Abgleich, Plan, geführte Ausführung, Ledger.

Aufrufmuster (immer aus dem Repo-Wurzelverzeichnis, `python -m …`):

```
python -m management.migrate                                   [coordinator.db]
python -m management.migration_fleet.migration_fleet_admin <SUB> …   [Beweis-DBs]
```

---

## 4. Der Ablauf Schritt für Schritt

### Phase 0 — Vorbereitung (einmal je Migration × DB-Art)
Die Migration wird auf einer **synthetischen/anonymisierten Referenz-DB** gebaut
und getestet (Trockenlauf, Rollback-Test). Die zweite Person prüft **Skript und
Referenzlauf** (Vieraugen). Erst danach geht es an die Flotte. Details:
Leitfaden §2/§3.

### Schritt 1 — Katalog aus dem Code füllen
```
python -m management.migration_fleet.migration_fleet_admin catalog-sync \
    --migration-db <PFAD/migration.db>
```
Trägt alle Code-Migrationen (je DB-Art) mit ihrer Prüfsumme in `migration.db`.

### Schritt 2 — Katalog gegen Code prüfen
```
python -m management.migration_fleet.migration_fleet_admin reconcile \
    --migration-db <PFAD/migration.db>
```
Meldet Drift (`GEAENDERT`/`NICHT KATALOGISIERT`/`MODUL FEHLT`). Bei Drift:
Ursache klären, ggf. erneut `catalog-sync`. **Exit 1 bei Drift.**

### Schritt 3 — Vorschau (Trockenlauf, ohne Ausführung)
```
python -m management.migration_fleet.migration_fleet_admin companion \
    --migration-db <PFAD/migration.db> --backup-dir <PFAD/backups> \
    --target evidence:<PFAD/evidence_18.db>:18
```
**Ohne `--confirm`** führt der Companion nur die **Vorprüfung** (Tore) und den
**Dry-Run-Plan** aus — es wird **nichts** verändert. Prüfen Sie, dass keine
Tore blockieren und der Plan stimmt.

### Schritt 4 — Ausführung (verriegelt, nur mit Bestätigung)
```
python -m management.migration_fleet.migration_fleet_admin companion \
    --migration-db <PFAD/migration.db> --backup-dir <PFAD/backups> \
    --operator <SAMAccount> --verifier <SAMAccount> --confirm \
    --target evidence:<PFAD/evidence_18.db>:18 \
    --target forensic:<PFAD/forensic_18.db>:18
```
Mit `--confirm` führt der Companion **nur dann** aus, wenn **alle Tore offen**
sind. Pro Instanz: Backup → Migration → Verify → `ok` **oder** automatische
Wiederherstellung. `--target` ist wiederholbar (mehrere Instanzen/Arten).

### Schritt 5 — Ledger prüfen
```
python -m management.migration_fleet.migration_fleet_admin ledger-verify \
    --migration-db <PFAD/migration.db>
python -m management.migration_fleet.migration_fleet_admin ledger-list \
    --migration-db <PFAD/migration.db>
```
`ledger-verify` prüft die **Hashkette** (Exit 1 bei Bruch). `ledger-list` zeigt
alle Läufe und **unterbrochene** (Start ohne Abschluss).

### Schritt 6 — Gegenzeichnung (Vieraugen)
Die zweite Person zeichnet **Migrations-Definition** und **Ledger** per GPG
gegen; **Backups** werden signiert und WORM-archiviert (Leitfaden §3 Phase 3/4).

---

## 5. Befehlsreferenz (kompakt)

| Zweck                              | Befehl (`migration_fleet_admin …`)                          |
| ---------------------------------- | ----------------------------------------------------------- |
| Katalog füllen                     | `catalog-sync --migration-db P`                             |
| Katalog/Code-Drift prüfen          | `reconcile --migration-db P`                                |
| Dry-Run-Plan je Instanz            | `plan --migration-db P --target KIND:PFAD[:UID] …`          |
| Vorprüfung + Plan (nichts tun)     | `companion --migration-db P --backup-dir B --target …`      |
| Ausführung (verriegelt)            | `companion … --confirm --operator O --verifier V --target …`|
| Ledger-Kette prüfen                | `ledger-verify --migration-db P`                            |
| Ledger anzeigen                    | `ledger-list --migration-db P [--db-kind K] [--uid N]`      |
| coordinator.db migrieren           | `python -m management.migrate --coordinator-db P`           |

`--target` hat die Form `db_kind:PFAD[:uid]`, z. B.
`evidence:/data/evidence_18.db:18`. `db_kind` ∈
`evidence` / `forensic` / `assets` (Beweis) bzw. `coordinator`. Fehlen
`--migration-db`/`--backup-dir`, werden sie aus `config.yaml`
(`paths.migration_db` / `paths.backup_dir`) gezogen.

---

## 6. Sicherheitsgarantien (was das Werkzeug erzwingt)

- **Pflicht-Backup** vor jeder Änderung (ohne Backup-Ziel → Ausführung
  verweigert).
- **Verify** nach der Migration: `integrity_check`, `foreign_key_check`,
  Zeilenzahl-Abgleich, **BLOB-Bitidentität** getragener Rohdaten.
- **Automatische Wiederherstellung** bei jedem Fehler; **vorwärts-only**;
  **Isolation** je Instanz (ein Fehler bei A berührt B nicht).
- **Hash-verkettetes Ledger** (`migration_runs`) — Manipulation wird erkennbar.

---

## 7. Wenn ein Tor blockiert — und was zu tun ist

| Blocker                 | Bedeutung                                   | Maßnahme                                            |
| ----------------------- | ------------------------------------------- | --------------------------------------------------- |
| `KATALOG_DRIFT`         | Katalog ≠ Code                              | `catalog-sync` erneut; Code/Katalog prüfen          |
| `LEDGER_KETTE`          | Hashkette fehlerhaft                        | Manipulation/Korruption untersuchen — **nicht** ausführen |
| `UNTERBROCHENE_LAEUFE`  | Früherer Lauf ohne Abschluss                | `ledger-list` prüfen, betroffene Instanz klären     |
| `KEIN_BACKUP_DIR`       | Kein Pflicht-Backup-Ziel                    | `--backup-dir` bzw. `paths.backup_dir` setzen       |

**Status `failed_restored`** einer Instanz bedeutet: Die Migration schlug fehl,
die Instanz wurde **automatisch aus dem Backup wiederhergestellt** (Ausgangs-
zustand). Ursache der Migration prüfen, **nicht** blind erneut ausführen.

---

## 8. Verweise

- Verbindlicher Prozess: `documents/Datenmigrationsleitfaden_AIW.md` (v0.2).
- Werkzeug-Bausteine: `management/migration_fleet/` (Katalog/Inventar/Ledger,
  Harness, Executor, Companion) und `management/migrations/` (die m###-Skripte
  je DB-Art) sowie `management/migrate.py` (coordinator.db).

---

*Ende MIGRATION.md v1.0.*

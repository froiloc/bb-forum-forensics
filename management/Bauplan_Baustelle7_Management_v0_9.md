# Bauplan Baustelle 7 — Management-Interface

**Version:** 0.9 · **Datum:** 2026-07-02
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Auslieferung:** innerhalb `aiw_webserver`, im geschützten Unterordner `management/`
**Grundlage:** `Ideen_zum_Verwaltungswerkzeug.md`, bewertete Fassung v1.0 (2026-04-14),
verifizierte Schemata `coordinator_db.sql` / `templates_db.sql`, Projektgespräch 2026-07-01.

> **Status dieses Dokuments:** Abschnitt 2 (Tag 1) ist **freigabereif** und vollständig
> spezifiziert. Abschnitt 1 ist die abgestimmte Gesamt-Roadmap. Abschnitte ab Tag 2 sind
> als Roadmap-Stubs geführt und werden vor ihrer jeweiligen Umsetzung im Detail ausgearbeitet
> (Bauplan-Prinzip: Plan → mc → Umsetzung).

---

## 1. Gesamt-Roadmap (2 Wellen, je Arbeitspaket ≈ 1 Tag)

Arbeitspaket = 1 h Vorbereitung · 3 h Entwicklung · 2 h Test/Fehlerbehebung · 2 h Verbesserung · 1 h Doku.

**Welle P1 — minimal produktionsreif (Version 0.7.x):**

| Tag | Paket | Ideen | Schreibt nach | Schema-Änderung |
|-----|-------|-------|---------------|-----------------|
| 1 | Migrations-Gerüst + Audit-Log + Write-Gateway | 13 | `coordinator.db` | M001: `schema_migrations`, `audit_log` |
| 2 | `cases` + `scrape_jobs`-**Rebuild** + Repointing (`userinfo_data.py`) + auditierte Zuweisungs-CLI (**ein atomarer Build**) | — | `coordinator.db` | M002 (destruktiv): Rebuild `scrape_jobs` ohne `assigned_to`/`note`; Create `cases` |
| 2+ | Ereigniszeitstrahl `case_events` (eigener additiver Build M003, vor/mit Tag 3) | 11 | `coordinator.db` | M003 (additiv): Create `case_events` |
| 3 | Ampel-Dashboard (liest `cases`/`case_events` + `evidence_db`-Zähler, SSE) | 1 | — (read) | — |
| 4 | Backup- & PITR-Maske (WAL/SHM-bewusst, alle DBs per mtime, Pfad aus `config.yaml`) | 10 | Backup-Ziel (SMB) | M003: `backups`-Registry |

**Welle P2 — Erweiterung (Version 0.8.x):**

| Tag | Paket | Ideen |
|-----|-------|-------|
| 5 | Vorlageneditor (Autoren-UI + Schreib-Endpunkte auf bestehende `templates.db`-Infrastruktur) | NEU |
| 6 | Internes Nachrichtensystem (Template-only, SSE-Banner) | 9 |
| 7 | Ermittler-Metriken + Lastverteilung (nur Chefermittlerin-sichtbar) | 8, 6 |
| 8 | Rollenbasierte Layouts + StA-Statistik-Export + Vollregression | 15, 2 |

**Zurückgestellt auf v1.1/v2.0** (deckungsgleich mit der Bewertung): Gantt (5), Prognose (7),
Risiko-/Relevanz-Score (3 — § 261 StPO), Volltextsuche (14 — Indexer-Daemon),
B6-abhängige Teile von Berichtsfreigabe (4) und StA-Export (12).

> **Hinweis zur Sequenz:** Gegenüber der Bewertung v1.0 ist `cases` als eigene Fallakte
> (Tag 2) eingezogen worden. Begründung siehe Projektgespräch 2026-07-01: `scrape_jobs`
> trägt zwei Belange mit unterschiedlicher Kardinalität (N Scrape-Jobs je User vs. 1 Fall je
> User); der Fall-Read „neueste Job-Zeile" lässt bei Re-Scrape Zuweisung + Notiz **lautlos**
> aus der Ansicht fallen (Verstoß gegen Grundregel 1). `cases` (1:1 zur `user_id`) behebt das.

---

## 2. TAG 1 — Migrations-Gerüst + Audit-Log + Write-Gateway

### 2.0 Ziel und Abgrenzung

Tag 1 legt das Fundament, von dem **jede** spätere B7-Schemaänderung und **jeder**
schreibende Management-Zugriff auf `coordinator.db` abhängt. Tag 1 berührt den
Request-/Auslieferungspfad des Webservers **nicht** — `--user-id` und der gesamte
Ermittler-Arbeitsplatz bleiben unverändert. Es entstehen ausschließlich neue Dateien unter
`management/` plus ein `build.json`-Update.

### 2.1 Ordner- und Klassenstruktur (Grundregel 10: jede Klasse eigene Datei)

```
management/
├── __init__.py
├── migrations/
│   ├── __init__.py
│   ├── runner.py                 # Klasse MigrationRunner
│   ├── coordinator/
│   │   ├── __init__.py
│   │   └── m001_audit_log.py     # version, name, kind, up(con), (assert)
│   ├── evidence/
│   │   └── __init__.py           # PLATZHALTER: erste Migration rüstet schema_migrations nach (additiv)
│   └── assets/
│       └── __init__.py           # PLATZHALTER: dito (additiv, datenneutral)
├── audit/
│   ├── __init__.py
│   ├── audit_log.py              # Klasse AuditLog (append, verify_chain, tip)
│   ├── hashing.py                # kanonische Serialisierung + row_hash()
│   └── event_types.py            # eingefrorenes Enum der event_type-Werte
└── gateway/
    ├── __init__.py
    └── coordinator_writer.py     # Klasse CoordinatorWriter (atomar: Write + Audit)
```

Wiederverwendung bestehender Infrastruktur: `db/connection_manager.py` (WAL + busy_timeout +
Retry für `coordinator.db` auf SMB) und `core/config_loader.py`. Keine Duplikation.

### 2.2 Migration M001 — DDL

```sql
-- Registry je schreibbarer DB; auf coordinator.db zuerst.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version           INTEGER PRIMARY KEY,            -- fortlaufend je DB
    name              TEXT    NOT NULL,
    kind              TEXT    NOT NULL CHECK(kind IN ('additive','destructive')),
    checksum          TEXT    NOT NULL,               -- sha256 des Migrationsmoduls
    applied_at        INTEGER NOT NULL,
    row_count_before  INTEGER,                        -- Pflicht bei 'destructive'
    row_count_after   INTEGER                         -- Pflicht bei 'destructive'
);

-- Hash-verkettetes Audit-Log. Spaltensatz ab Zeile 1 EINGEFROREN.
CREATE TABLE IF NOT EXISTS audit_log (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,   -- monoton, lückenlos
    ts           INTEGER NOT NULL,
    actor_id     INTEGER,                             -- FK investigators.id; NULL = System
    event_type   TEXT    NOT NULL,                    -- aus event_types.py (Enum im Code)
    target_type  TEXT,                                -- z. B. 'case','migration','chain'
    target_id    TEXT,                                -- z. B. '18'
    content      TEXT    NOT NULL,                    -- kanonisches JSON (sort_keys, kompakt)
    meta         TEXT    NOT NULL DEFAULT '',         -- RESERVE: künftige Zusatzinfo, IM Hash
    prev_hash    TEXT    NOT NULL,                    -- hex sha256 der Vorzeile (Genesis: 64×'0')
    row_hash     TEXT    NOT NULL,                    -- siehe 2.3
    FOREIGN KEY(actor_id) REFERENCES investigators(id)
);

-- Append-only-Schutz (Leitplanke; der Manipulations-BEWEIS ist die Hash-Kette).
CREATE TRIGGER IF NOT EXISTS audit_log_no_update
    BEFORE UPDATE ON audit_log
    BEGIN SELECT RAISE(ABORT, 'audit_log ist append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
    BEFORE DELETE ON audit_log
    BEGIN SELECT RAISE(ABORT, 'audit_log ist append-only'); END;
```

`kind='additive'`, `row_count_*` = NULL für M001 (rein additiv, datenneutral).

### 2.3 Hash-Formel (exakt, eingefroren ab Zeile 1)

Kanonische Serialisierung von `content` und `meta`:
`json.dumps(obj, sort_keys=True, separators=(',',':'), ensure_ascii=False)` → UTF-8.

Feldzusammenstellung mit Unit-Separator `0x1F` (verhindert Feld-Injektion):

```
row_hash = sha256(
    prev_hash || 0x1F || str(seq) || 0x1F || str(ts) || 0x1F ||
    (str(actor_id) if actor_id is not None else "") || 0x1F ||
    event_type || 0x1F || (target_type or "") || 0x1F || (target_id or "") || 0x1F ||
    content_canonical || 0x1F || meta_canonical
).hexdigest()
```

- **Genesis:** erste Zeile `event_type='genesis'`, `prev_hash = '0'*64`,
  `content = {"db":"coordinator","schema":"M001","created_at":<ts>}`.
- **`meta` ist von Beginn an Teil der Formel** (Default `""`). Damit nimmt jede künftige
  Zusatzinfo `meta` auf, **ohne** dass die Formel oder ein Spalten-Rebuild nötig wird; alte
  Zeilen bleiben gültig (sie haben `meta=""` gehasht). Neue **typisierte** Spalten sind damit
  dauerhaft ausgeschlossen — genau das verhindert den schlimmsten Migrationsfall.

### 2.4 Klasse `AuditLog` (`audit/audit_log.py`)

- `tip(con) -> (prev_hash, seq)` — liest `row_hash`/`seq` der letzten Zeile; Default Genesis-Wert.
- `append(con, event_type, actor_id, target_type, target_id, payload, meta=None) -> int`
  Muss **innerhalb einer bereits geöffneten `BEGIN IMMEDIATE`-Transaktion** des schreibenden
  Vorgangs laufen (siehe 2.6). Liest Tip, berechnet `row_hash`, fügt Zeile ein, gibt `seq` zurück.
- `verify_chain(con) -> VerifyResult` — rechnet alle `row_hash` nach und prüft die Verkettung;
  liefert `OK` oder die `seq` der ersten Abweichung. Für die Chefermittlerin jederzeit aufrufbar
  (Idee 13). Schreibt selbst **kein** Audit (reiner Lesevorgang), kann aber auf Wunsch ein
  `CHAIN_VERIFIED`-Ereignis erzeugen.

### 2.5 `event_types.py` — eingefrorenes Enum (Tag-1-Umfang)

`GENESIS`, `MIGRATION_APPLIED`, `CHAIN_VERIFIED`. Weitere Werte (`CASE_CREATED`,
`CASE_ASSIGNED`, `CASE_STATUS_CHANGED`, `CASE_APPROVED`, `CASE_EVENT_ADDED`,
`NOTIFICATION_SENT`, `BACKUP_CREATED`, `RESTORE_PERFORMED`) werden mit ihren jeweiligen
Modulen ergänzt. Werte sind Versionsbestandteil — ein Wert im Log entspricht jahrelang
eindeutig einer Bedeutung.

### 2.6 Klasse `CoordinatorWriter` (`gateway/coordinator_writer.py`)

**Der einzige zulässige Schreibpfad** auf die Management-Tabellen von `coordinator.db`
(ab Tag 2: `cases`, `case_events`; später `notifications`, `backups`). Vertrag jeder
Schreibmethode:

1. `BEGIN IMMEDIATE` (Schreibsperre sofort halten → serialisiert Tip-Lesen+Insert, kein Race).
2. Fachlichen Write ausführen.
3. `AuditLog.append(...)` in **derselben** Transaktion.
4. `COMMIT` — entweder Write **und** Audit-Eintrag committen, oder keines von beidem.

Damit existiert kein Management-Write ohne Audit-Eintrag und kein Audit-Eintrag ohne seinen
Write. Das ist der forensische Kern.

### 2.7 Klasse `MigrationRunner` (`migrations/runner.py`)

- Findet Migrationsmodule unter `migrations/<db>/`, sortiert nach `version`.
- Aktuelle Version = `MAX(version)` aus `schema_migrations` (0, falls Tabelle fehlt).
- Für jede ausstehende Version: `PRAGMA wal_checkpoint(TRUNCATE)` → `BEGIN IMMEDIATE` →
  (bei `destructive`: `row_count_before` erfassen) → `up(con)` → (bei `destructive`:
  `row_count_after` erfassen + modul-eigene Invariante prüfen) → `INSERT schema_migrations`
  → `AuditLog.append(MIGRATION_APPLIED, actor_id=NULL, target_type='migration', target_id=version, payload={name,kind,checksum,counts})`
  → `COMMIT`.
- **Idempotent:** erneuter Lauf wendet nichts an. `checksum`-Vergleich erkennt nachträglich
  geänderte, bereits angewandte Migrationsmodule (Warnung, kein erneutes Anwenden).
- Forward-only (keine Down-Migrations; Abwärtskompatibilität ist projektweit nicht gefordert).

### 2.8 WAL/SHM- und Nebenläufigkeits-Regeln (verbindlich)

Eine „Datenbank" = Tripel `.db`/`.db-wal`/`.db-shm`. Daraus folgen **zwei getrennte** Politiken:

**a) Migrationen — kontrollierte Ruhe (Wartungsfenster).**
- Vor jeder destruktiven Migration: `PRAGMA wal_checkpoint(TRUNCATE)`, WAL in Hauptdatei gefaltet.
- Der Runner nimmt `BEGIN IMMEDIATE` + `busy_timeout` (bestehende Retry-Praxis,
  `connection_manager`). **Kann die Schreibsperre nicht erlangt werden** (z. B. weil noch
  Ermittler-Webserver `coordinator.db` offen haben), **bricht der Runner sauber ab — keine
  Teil-Migration, kein Teilzustand.** Destruktive `coordinator.db`-Migrationen sind daher im
  Wartungsfenster auszuführen.
- Hash-Ketten-Appends sind ohnehin durch `BEGIN IMMEDIATE` serialisiert.

**b) Backups — laufender Betrieb (Webserver der Ermittler darf aktiv sein).**
- Backups werden **nicht** per Dateikopie erstellt, sondern als **transaktionaler SQLite-
  Snapshot**: `VACUUM INTO '<ziel>.db'` (alternativ `Connection.backup()`). Im WAL-Mode liest
  der Snapshot-Leser den konsistenten committeten Stand, **während** ein anderer Prozess
  (Ermittler-Webserver) parallel weiterschreibt. Ergebnis ist eine **einzelne, saubere `.db`**
  ohne WAL/SHM-Tripel — robust und ohne Störung des Ermittlers.
- Kein TRUNCATE im Backup-Pfad; höchstens `wal_checkpoint(PASSIVE)` als nicht-blockierendes
  WAL-Trim. (Vollständige Backup-Mechanik in der Tag-4-Ausarbeitung.)

### 2.9 Tests (Grundregeln 3 + 9) — `tests/test_management_audit.py`

| ID | Prüfung |
|----|---------|
| A01 | `MigrationRunner` legt `schema_migrations` + `audit_log` an; zweiter Lauf = No-Op |
| A02 | Genesis korrekt: `prev_hash='0'*64`, `event_type='genesis'` |
| A03 | `append` verkettet korrekt; `row_hash` == Nachrechnung |
| A04 | `verify_chain` = OK auf intakter Kette |
| A05 | Manipulierte `content`-Zeile (Direkt-SQL) → `verify_chain` meldet exakte `seq` |
| A06 | `UPDATE`/`DELETE` auf `audit_log` → `RAISE(ABORT)` (Trigger) |
| A07 | Gateway: Rollback lässt **weder** Write **noch** Audit-Eintrag zurück (Atomarität) |
| A08 | `meta`-Reserve: Zeile mit gesetztem `meta` verifiziert; Formel unverändert |
| A09 | Zwei sequentielle Appends unter `BEGIN IMMEDIATE` → lückenlose, korrekte Kette |

Anschließend volle Regression `python run_tests.py` (Erwartung: bestehende 563 + neue, 0 Fehler).

### 2.10 Auslieferung

- **Build 306**, Version **0.7.306** (Minor-Bump für die P1-Welle; Buildnummer läuft fort).
- `build.json` im etablierten Detailstil (Beleg, geänderte Dateien, Regressionsergebnis).
- ZIP `aiw_webserver_306.zip` — nur neue/geänderte Dateien + `build.json`, absolute Pfade,
  MD5-Summen je Datei.
- Syntaxprüfung aller `.py` in der VM vor der Übergabe.

---

## 3. TAG 2 — cases + scrape_jobs-Rebuild + Repointing + Zuweisungs-CLI (Build 307)

### 3.0 Ziel und Abgrenzung

Tag 2 zieht die Fallakte `cases` (1:1 zur `user_id`) als autoritative Quelle ein, baut
`scrape_jobs` auf seine reine Baustelle-0-Rolle zurück, biegt den einen Lese-Pfad
(`userinfo_data.py`) auf `cases` um und liefert die erste **auditierte** Zuweisungs-CLI —
Ersatz für die bisherige Roh-SQL-Zuweisung (ein Roh-SQL-Write auf `cases` würde die
Audit-Kette umgehen). **Bewusst NICHT in diesem Build:** `case_events` (Ereigniszeitstrahl,
Idee 11) — eigener additiver Build M003 vor/mit Tag 3 (Entscheidung „Schritt für Schritt",
2026-07-01). Der Audit-Trail ist davon unberührt, da jeder `cases`-Write ohnehin einen
`audit_log`-Eintrag erzeugt.

**Keine Daten-Migration** (Dummies, Entscheidung 2026-07-01). `cases` startet leer; die
10 Live-User werden per CLI angelegt/zugewiesen. Der Request-/Auslieferungspfad und
`--user-id` bleiben unangetastet.

### 3.1 Neue/geänderte Dateien

```
management/
├── migrate.py                       # NEU: produktiver Migrations-Einstieg (CLI)
├── cases/
│   ├── __init__.py
│   ├── cases_repo.py                # NEU: CasesRepo (auditierte Lese-/Schreibmethoden)
│   └── cases_admin.py               # NEU: CLI (Anlegen/Zuweisen/Status/Priorität/Notiz)
└── migrations/coordinator/
    └── m002_cases.py                # NEU: M002 (destruktiv)
management/audit/event_types.py      # GEÄNDERT: CASE_* Ereignistypen ergänzt (additiv)
forensic_api/userinfo_data.py        # GEÄNDERT: Status-Read auf cases umgebogen
build.json                           # GEÄNDERT: Build 307
tests/test_management_cases.py       # NEU: Testmatrix B01–B10
```

### 3.2 Migration M002 (destruktiv) — DDL & Ablauf

`scrape_jobs.assigned_to` steht in einer FK-Klausel → `DROP COLUMN` unzulässig, daher
**Tabellen-Rebuild** (12-Schritt). Die Management-Verbindung führt `foreign_keys=OFF`
(SQLite-Default) → Rebuild im Transaktionsrahmen unproblematisch; nach dem Rebuild
`PRAGMA foreign_key_check` als Kontrolle (in verify()).

```sql
-- 1) scrape_jobs OHNE assigned_to/note neu aufbauen (Baustelle-0-Spalten + CHECKs erhalten)
CREATE TABLE scrape_jobs_new (
    id            INTEGER,
    user_id       INTEGER NOT NULL,
    username      TEXT    NOT NULL,
    priority      INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status        TEXT    NOT NULL DEFAULT 'pending'
                  CHECK(status IN ('pending','running','done','failed')),
    manifest_path TEXT,
    output_path   TEXT,
    worker_id     TEXT,
    created_at    INTEGER NOT NULL,
    started_at    INTEGER,
    finished_at   INTEGER,
    error_message TEXT,
    PRIMARY KEY(id AUTOINCREMENT)
);
INSERT INTO scrape_jobs_new
    (id,user_id,username,priority,status,manifest_path,output_path,worker_id,
     created_at,started_at,finished_at,error_message)
SELECT
    id,user_id,username,priority,status,manifest_path,output_path,worker_id,
    created_at,started_at,finished_at,error_message
FROM scrape_jobs;
DROP TABLE scrape_jobs;
ALTER TABLE scrape_jobs_new RENAME TO scrape_jobs;
-- Indizes neu:
CREATE INDEX IF NOT EXISTS scrape_jobs_status_idx ON scrape_jobs(status);
CREATE INDEX IF NOT EXISTS scrape_jobs_user_idx   ON scrape_jobs(user_id);

-- 2) Fallakte cases (1:1 zur user_id) — autoritative Quelle
CREATE TABLE cases (
    user_id             INTEGER PRIMARY KEY,
    username            TEXT    NOT NULL,
    assigned_to         INTEGER,
    priority            INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status              TEXT    NOT NULL DEFAULT 'open'
                        CHECK(status IN ('open','in_progress','approved','closed')),
    approved_at         INTEGER,
    total_pages_scraped INTEGER,
    note                TEXT,
    created_at          INTEGER NOT NULL,
    updated_at          INTEGER NOT NULL,
    FOREIGN KEY(assigned_to) REFERENCES investigators(id)
);
```

- `KIND='destructive'`; `precount` = `COUNT(*)` scrape_jobs vorher, `postcount` nachher.
- `verify(con, before, after)`: **assert before == after** (keine Job-Zeile verloren) UND
  `PRAGMA foreign_key_check` liefert keine Verletzung. Bei Verstoß → Exception → ROLLBACK,
  kein Teilzustand (Runner-Vertrag).
- `status`-Vokabular `cases`: `open / in_progress / approved / closed` (echter Ermittlungs-
  status; ersetzt im Nutzerinfo-Tab die bisherigen Job-Status). `approved_at` ist separate
  forensische Tatsache.

### 3.3 event_types.py (additiv erweitern, nie umbenennen)

Ergänzung: `CASE_CREATED`, `CASE_ASSIGNED`, `CASE_STATUS_CHANGED`, `CASE_APPROVED`,
`CASE_PRIORITY_SET`, `CASE_NOTE_SET`. Werte bleiben Versionsbestandteil.

### 3.4 CasesRepo (`management/cases/cases_repo.py`)

- Lesen: `get_case(user_id) -> dict | None` (für den Repoint in userinfo_data.py).
- Schreiben — **ausschließlich über `CoordinatorWriter.audited_write`**, sodass `cases`-Write
  und `audit_log`-Eintrag in EINER Transaktion committen:
  - `create_case(user_id, username, actor_id)` → `CASE_CREATED`
  - `assign(user_id, investigator_id, actor_id)` → `CASE_ASSIGNED`
  - `set_status(user_id, status, actor_id)` → `CASE_STATUS_CHANGED`; bei `approved`
    zusätzlich `approved_at` setzen (`CASE_APPROVED`)
  - `set_priority(...)`, `set_note(...)`
- `updated_at` bei jedem Write aktualisieren.

### 3.5 Zuweisungs-CLI (`management/cases/cases_admin.py`)

`python -m management.cases_admin --user-id N --username NAME [--assign SYSUSER] [--status S] [--priority P] [--note TEXT] [--actor SYSUSER]`

- Öffnet dedizierte `coordinator.db`-Verbindung (Autocommit, WAL), baut
  `AuditLog` + `CoordinatorWriter` + `CasesRepo`, führt die Aktion aus, gibt Ergebnis +
  `audit_log`-seq aus.
- `--actor SYSUSER`: `investigators.id` des Ausführenden → `audit_log.actor_id`. Fehlt es,
  `actor_id=NULL` (System) und OS-Benutzername in `content.performed_by`.
- Nicht-fatal, klare Fehlermeldungen.

### 3.6 Repoint `userinfo_data.py`

Ersetzt den „neueste scrape_jobs-Zeile"-Read durch:

```sql
SELECT c.status, c.priority, i.system_username AS assigned_to, c.note
FROM   cdb.cases c
LEFT JOIN cdb.investigators i ON i.id = c.assigned_to
WHERE  c.user_id = ?
```

Kein `ORDER BY/LIMIT` (1:1). **Gleiche Ergebnisform** (`status/priority/assigned_to/note`).
Kein `cases`-Eintrag → `None` → Nutzerinfo-Tab zeigt „nicht zugewiesen" (identisch zum
bisherigen „kein Job"-Verhalten; lautlose Auslassung bei Re-Scrape entfällt).

### 3.7 migrate.py (produktiver Einstieg)

`python -m management.migrate [--coordinator-db PATH] [--deployed-by NAME]`

- Pfad aus `--coordinator-db` oder `config.yaml` (`paths.coordinator_db`).
- Dedizierte Verbindung (Autocommit, WAL) → `AuditLog(con)` →
  `discover(management.migrations.coordinator)` → `MigrationRunner(...).run()` →
  Ausgabe der angewandten Versionen + `verify_chain()`-Ergebnis. Nicht-fatal.

### 3.8 Tests (`tests/test_management_cases.py`)

| ID | Prüfung |
|----|---------|
| B01 | M002 Rebuild: `scrape_jobs` ohne `assigned_to`/`note`, übrige Spalten + Indizes erhalten |
| B02 | M002: Zeilenzahl scrape_jobs vorher == nachher (Invariante) |
| B03 | M002: `PRAGMA foreign_key_check` sauber; `cases` angelegt |
| B04 | `create_case` → cases-Zeile + `CASE_CREATED` atomar |
| B05 | `assign` → `assigned_to` gesetzt + `CASE_ASSIGNED` |
| B06 | `set_status('approved')` → `approved_at` gesetzt + `CASE_APPROVED` |
| B07 | ungültiger Status → CHECK-Verletzung (abgewiesen) |
| B08 | Gateway-Rollback: fehlgeschlagener Write lässt weder cases-Änderung noch Audit zurück |
| B09 | Repoint-Read: `get_case` gleiche Schlüssel; `None` bei fehlendem Fall |
| B10 | Audit-Kette verifiziert nach cases-Writes (verify_chain OK) |

Danach volle Regression `python run_tests.py` (0 Fehler).

---

## 4. Geklärte Punkte — Tag 1 (Stand v0.2, Projektgespräch 2026-07-01)

1. **Migrations-Akteur:** GEKLÄRT — `actor_id = NULL` (System); OS-Benutzername des Deployers
   in `content.deployed_by` (aus Umgebung/Config).
2. **`schema_migrations` für `evidence`/`assets`:** GEKLÄRT — jetzt nur `coordinator.db`.
   Für `evidence`/`assets` werden in Tag 1 **Platzhaltermodule** angelegt
   (`migrations/evidence/__init__.py`, `migrations/assets/__init__.py`), damit der spätere,
   additive `schema_migrations`-Retrofit strukturell verankert und nicht vergessen ist.
   → **To-Do (offen):** `schema_migrations`-Retrofit in `evidence`/`assets` bei deren erster
   echter Migration; ist additiv und datenneutral auszuführen.
3. **WAL/Backup-Robustheit:** GEKLÄRT + verfeinert — TRUNCATE-Checkpoint nur für Migrationen
   im Wartungsfenster (Runner bricht bei nicht erlangbarer Sperre sauber ab). **Live-Backups
   laufen über transaktionalen SQLite-Snapshot (`VACUUM INTO`/Backup-API)**, robust bei
   laufendem Ermittler-Webserver. Siehe 2.8.

---

## 5. Ermittler-Verwaltung — investigators-CLI (Build 310)

### 5.0 Ziel und Abgrenzung
Ermittler sollen sauber über eine **auditierte CLI** angelegt und geändert werden können —
kein Einfügen per SQL-Direktzugriff mehr. Ein UI ergänzt die CLI später. **Reihenfolge-
Entscheidung (mc 2026-07-01):** CLI **vor** der Support-Sitzungserfassung, da Letztere
existierende Ermittler voraussetzt und die Einarbeitung neuer Mitarbeiter das saubere
Anlegen sofort braucht. **Rein additiv:** keine Schema-Änderung, keine Migration (Tabelle
`investigators` existiert bereits; es kommen nur zwei Audit-Event-Typen hinzu). Build 309
wird übersprungen; nächster Build ist **0.7.310** (mc).

### 5.1 Neue/geänderte Dateien
- `management/investigators/__init__.py` (neu)
- `management/investigators/investigators_repo.py` (neu) — `InvestigatorsRepo`
- `management/investigators/investigators_admin.py` (neu) — CLI
- `management/audit/event_types.py` (geändert) — `INVESTIGATOR_CREATED`, `INVESTIGATOR_UPDATED` additiv
- `tests/test_management_investigators.py` (neu) — C01–C10

### 5.2 `InvestigatorsRepo`
- `list_investigators()`, `get(id | system_username)` — Lesen.
- `create(system_username, display_name, is_investigator=True, is_supervisor=False, is_support=False)`
  → auditiert `INVESTIGATOR_CREATED`; UNIQUE-Prüfung innerhalb `BEGIN IMMEDIATE` (kein TOCTOU).
- `update(id | system_username; display_name?, is_investigator?, is_supervisor?, is_support?)`
  → auditiert `INVESTIGATOR_UPDATED`; nur tatsächlich geänderte Felder, Diff `{alt, neu}` je Feld
  im Payload; No-Op wirft `InvestigatorsError` (kein irreführender Audit-Eintrag).
- Schreiben **ausschließlich** über das `CoordinatorWriter`-Gateway (Write + Audit atomar).

### 5.3 Verbindliche Regeln (forensisch)
- **KEIN Löschen:** `cases.assigned_to` (FK) referenziert `investigators.id` — Löschen würde
  Fälle verwaisen lassen und Belege zerstören. Stilllegen erfolgt über `is_investigator=0`;
  die Zeile bleibt als Beleg erhalten.
- **`system_username` ist die Identität** (Windows-SAMAccountName) und wird **nie** geändert;
  nur `display_name` und Rollen-Flags sind änderbar.
- `--actor SYSUSER` → `audit_log.actor_id`; fehlt es, `actor_id=NULL` (System) + OS-Benutzer in
  `audit_log.meta.performed_by`. Bootstrap (allererster Ermittler) ohne `--actor` zulässig.

### 5.4 CLI-Aufruf (Subkommandos)
```
python -m management.investigators.investigators_admin list [--coordinator-db PATH] [--config ...]
python -m management.investigators.investigators_admin create --system-username h0XXXXX \
        --display-name "Nachname, Vorname" [--supervisor] [--support] [--no-investigator] \
        [--actor SYSUSER] [--coordinator-db PATH]
python -m management.investigators.investigators_admin update (--id N | --system-username h0X) \
        [--display-name "..."] [--set-investigator 0|1] [--set-supervisor 0|1] [--set-support 0|1] \
        [--actor SYSUSER] [--coordinator-db PATH]
```

### 5.5 Tests (`tests/test_management_investigators.py`, C01–C10)
create+Audit, Duplikat-Rollback (kein Row/Audit), `display_name`-Update mit `alt/neu`-Payload,
Flag-Update, No-Op ohne Audit, unbekannt→Fehler, `list` sortiert, `get` per id/username,
`verify_chain` grün nach allen Writes, Stilllegen statt Löschen.

### 5.6 Offener Nachlauf (mc 2026-07-01)
**Vor Abschluss Baustelle 7** analysieren, welche Funktionalität aus `setup_coordinator_dev.py`
überhaupt noch benötigt wird (das DEV-Skript rüstet u. a. das mit M002 entfernte
`scrape_jobs.assigned_to` per `ALTER` wieder nach — veraltet).

---

## 6. Echte Support-Sitzungserfassung (Build 311 = Backend, Build 312 = Verdrahtung/Frontend — BEIDE GELIEFERT)

### 6.0 Ziel und Zweischnitt
„Support aktiv" ist eine **Live-Sitzung**: solange die Instanz eines Supporters (Modus
`support`) einen Fall betrachtet, sieht der zugewiesene Ermittler das. Wegen der Delikatesse
der Live-SSE-Verdrahtung und des JS-Indikators (Browser-Test nötig) in **zwei Builds**:
- **Build 311 (Backend):** Migration `M003` (`support_sessions`), Event-Typen,
  `SupportSessionsRepo`, Read-Repoint `get_support_status(user_id)` inkl. Zähler. Nach außen
  **inert** (leere Tabelle → inactive), voll unit-getestet.
- **Build 312 (Verdrahtung + Frontend) — GELIEFERT 2026-07-02:** Support-Modus-SSE-Lebenszyklus
  (begin/heartbeat/resume/end) in `events.py` über die gekapselte Klasse `SupportPresenceBinder`
  (`forensic_api/support_presence.py`), `support_status`-Payload um `support_count`, Indikator
  zeigt „Support aktiv (N)". **Live-Verifikation im Browser steht noch aus** (dedizierte
  Test-Session 2026-07-02) — Code + Unit-/Regressionstests sind grün.

### 6.1 Datenmodell (M003, additiv, coordinator.db)
`support_sessions(id, user_id [Fall], supporter_id → investigators.id, started_at,
last_heartbeat, ended_at NULL)`, Index `(user_id, ended_at, last_heartbeat)`.
**Aktiv** = `ended_at IS NULL AND last_heartbeat ≥ now − stale`. coordinator.db ohne
Migrations-Lock; additiv/datenneutral.

### 6.2 Beleg vs. Präsenz
`support_sessions` ist **flüchtig** (prunebar). Der **permanente Zugriffsbeleg** lebt im
`audit_log`: `SUPPORT_SESSION_STARTED` / `_ENDED` (wer sah wann welchen Fall). Heartbeats
werden **nicht** auditiert (mc: Frage 2).

### 6.3 `SupportSessionsRepo`
`start()` [audit STARTED, gibt `session_id`], `heartbeat()` [plain, kein Audit], `end()`
[audit ENDED, idempotent], `get_active(user_id, stale_sec)` [Read], `prune(older_than_sec)`
[kein Audit]. Schreiben über das `CoordinatorWriter`-Gateway (start/end via `audited_write`;
heartbeat/prune via `writer.transaction()` **ohne** Audit).

### 6.4 Read-Repoint
`db/coordinator_db.get_support_status(user_id=None, stale_sec=30)` liest `cdb.support_sessions`
(Join `cdb.investigators`). Ohne `user_id` inaktiv (Alt-Aufrufform bleibt gültig bis 312).
`SupportStatusRecord` um `count` erweitert (Zähler; mc: Frage 3). Stale-Default **30 s** (mc: Frage 1).

### 6.5 Architektur (umgesetzt in Build 312)
Der Support-Webserver ist **erstmals Schreiber** von `coordinator.db`. Umgesetzt über eine
gekapselte Klasse `SupportPresenceBinder` (`forensic_api/support_presence.py`, Grundregel 10)
mit **dedizierter Direkt-Verbindung** zu `coordinator.db` (`isolation_level=None`, WAL,
`busy_timeout=10000`, `check_same_thread=False`) — getrennt von der ATTACHed-`cdb`-
Leseverbindung (analog `migrate.py`). Bindung `client_id → session_id`, thread-serialisiert.
`events.py` (nur `mode=='support'`, lazy): `begin()` beim SSE-Aufbau (`prune()` einmalig davor),
`heartbeat()` je Tick, `resume()` bei RESUMING (**bestehende** Sitzung umhängen, kein neuer
Beleg), `end()` **grace-gekoppelt** im `_grace_expired`-Callback (mc: Entscheidung 1 — ein Blip
innerhalb der Grace-Period führt die Sitzung fort, statt ein spurioses ENDED/STARTED-Paar in die
Audit-Kette zu schreiben). Alle DB-Fehler werden geloggt, nie geworfen (Präsenz-Bookkeeping darf
SSE-/Lock-Pfad nie brechen). Selbstheilung bei hartem Absturz: stale-Schwelle + `prune()`; der
`STARTED`-Beleg ohne `ENDED` ist forensisch korrekt (Zugriff fand statt).
Read (`_get_support_status`): **mode-aware** — im Support-Modus keine Selbstbeobachtung; sonst
Fall-`user_id` an `get_support_status(user_id, stale_sec)`, Payload um `support_count`.

### 6.6 Tests
Backend-Fundament (311): `tests/test_management_support_sessions.py` (S01–S10) +
`tests/test_coordinator_db.py` (D01–D04). Verdrahtung (312):
`tests/test_events_support_wiring.py` — W01–W10 (Binder-Lebenszyklus gegen echte
Temp-`coordinator.db`: begin/heartbeat/resume/end, Zähler, prune, `close()`, Audit-Kette gültig)
+ P01–P05 (`_get_support_status`-Payload: mode-aware, `support_count`, Fehlertoleranz).
Frontend: `tests/unit/test_support_indicator.test.js` (L01–L08, Zähler-/Announce-Logik).
Migrations-Integration M001–M003 via `discover`+Runner verifiziert.

---

## 7. Übergabe & Nächste Aufgaben (Stand nach Build 312)

> Dieser Abschnitt ist die **Übergabe an den nächsten Chat**. Er fasst den Stand,
> den konkreten nächsten Build und alle offenen Punkte zusammen, sodass nach einem
> frischen Klon reibungslos weitergearbeitet werden kann.

### 7.1 Projektstand (Builds 306–312, PROD-Betrieb ab 2026-07-01)
- **306:** Migrations-Framework + hash-verkettetes `audit_log` + Genesis + Write-Gateway (`CoordinatorWriter`).
- **307:** `cases`-Tabelle (Fallakte, 1:1 zu `user_id`) + `scrape_jobs`-Rebuild ohne `assigned_to`/`note` (M002, destruktiv) + `cases_admin`-CLI (auditierte Zuweisung) + Read-Repoint `userinfo_data`.
- **308:** Hotfix — restliche 4 Leser von `scrape_jobs.assigned_to` umgebogen (`mode_resolver._query_job` → `cases`; `forensic_db` immer aus `user_id`; `get_assigned_job` entfernt; `get_support_status` ehrlich inactive).
- **310:** Ermittler-Verwaltungs-CLI (`investigators_admin`: `create`/`update`/`list`, auditiert; kein Löschen, `system_username` unveränderlich). *(309 übersprungen — mc.)*
- **311:** Support-Sitzungserfassung **Teil 1/2 (Backend)** — M003 `support_sessions`, `SupportSessionsRepo`, Read-Repoint `get_support_status(user_id)` + Zähler. **Inert**, bis Build 312 verdrahtet.
- **312:** Support-Sitzungserfassung **Teil 2/2 (Verdrahtung + Frontend)** — `SupportPresenceBinder`
  (`forensic_api/support_presence.py`) verdrahtet den SSE-Lebenszyklus im Support-Modus
  (begin/heartbeat/resume/end, **grace-gekoppeltes** Ende), `_get_support_status` mode-aware +
  `support_count`, Indikator „Support aktiv (N)". Reine Code-Verdrahtung — **kein neuer `migrate.py`-Lauf**
  (M003 kam mit 311). **Live-Browser-Verifikation offen** (Test-Session 2026-07-02).

- **313:** Ereigniszeitstrahl `case_events` (Idee 11) — M004 (additiv), Spiegelung von
  Fallanlage/Zuweisung/Statuswechsel/Freigabe aus `CasesRepo` (atomar via neuem
  `after_audit`-Hook des Gateways, `audit_seq`-Kopplung an den `CASE_*`-Beleg), manuelle
  Einträge (`CASE_EVENT_ADDED`, Text nur im Zeitstrahl-Payload), `CaseEventsRepo` + CLI
  `case_events_admin` (list/add). **Deploy erfordert `migrate.py`-Lauf (M004).** Details §8.
- **314:** Ampel-Dashboard **Backend-Read-Model** (Tag 3, Teil 1/2). `DashboardRepo` — **nur
  lesend** auf `coordinator.db`, aggregiert je Fall `cases` + `case_events` + Support-Präsenz zu
  `CaseOverview` inkl. abgeleiteter **Ampel** (`classify_ampel`). Keine Migration, kein Schreibpfad,
  keine Beweis-DB berührt. **Frontend bewusst noch NICHT gebaut** (braucht Live-Abnahme) → Build 315.
  Ampel-Semantik **PROVISORISCH (mc ausstehend)**. Details §9. *(Kein `migrate.py`-Lauf nötig.)*

**Deploy-Hinweis 312:** Nur Code (support_presence.py [neu], events.py, toolbar.js). Keine
Migration, keine Schema-Änderung — M003/`support_sessions` sind bereits mit 311 deployt.

### 7.2 NÄCHSTE AUFGABE — Live-Verifikation Build 312 (Test-Session 2026-07-02)
Build 312 ist geliefert und grün in der Regression, aber **noch nicht im Browser live verifiziert**
(Alex konnte am 2026-07-01 nicht browserbasiert testen). Dedizierte Test-Session am **2026-07-02**:

**Verifikations-Szenario (Ist-Verhalten vor Bewertung per DevTools-Console prüfen):**
1. Supporter-Instanz (Modus `support`) öffnet einen zugewiesenen Fall → SSE-Stream baut auf.
   Erwartung: Zeile in `support_sessions` (`ended_at IS NULL`), Audit `SUPPORT_SESSION_STARTED`.
2. Ermittler-Fenster (Modus `job`/`cli`) desselben Falls: Indikator zeigt **„⚠️ Support aktiv · <Supporter>"**
   (bei mehreren Supportern „(N)"). Payload `support_status` enthält `support_count`.
3. Supporter schließt Fenster/verliert Verbindung → nach Grace-Period (5 s): Audit
   `SUPPORT_SESSION_ENDED`, Indikator verschwindet. Ein Reconnect **innerhalb** der Grace-Period
   (RESUMING) darf **kein** neues STARTED/ENDED-Paar erzeugen (Sitzung läuft weiter).
4. Heartbeat hält die Präsenz frisch (kein Verschwinden während aktiver Betrachtung trotz
   30-s-Stale-Schwelle).

**Falls Anpassungsbedarf:** Console-PoC → Fix → Regression → Folge-Build.

**Danach — Roadmap-Fortsetzung B7:** Tag 3 **Ampel-Dashboard** (liest `cases` + `case_events`
+ Support-Präsenz; Fall-/Support-Übersicht für die Chef-Ermittlerin) als **Build 314**,
dann Tag 4 Backup/PITR (§7.5). Die Dashboard-Voraussetzung `case_events` ist mit
**Build 313 geliefert** (§8). *(Stand 2026-07-02: Die Live-Verifikation von 312 konnte
am 02.07. noch nicht stattfinden — manueller Test folgt; automatische Tests grün, mc.)*

### 7.3 Relevante Code-Stellen (Anker, Stand nach Build 312)
- `forensic_api/support_presence.py` *(neu, 312)*: Klasse `SupportPresenceBinder` — dedizierte
  coordinator.db-Direktverbindung + `begin/heartbeat/resume/end/close`. Erste Anlaufstelle für die
  Live-Verifikation und spätere Feinjustierung (z. B. „ein Fenster = eine Sitzung"-Semantik).
- `forensic_api/events.py`: `_get_support_status(bundle, context, stale_sec=_SUPPORT_STALE_SEC)`
  (mode-aware, `support_count`); Konstanten `_SUPPORT_STALE_SEC=30`, `_SUPPORT_PRUNE_OLDER_THAN_SEC=3600`,
  `_GRACE_PERIOD_SEC=5`; `EventsEndpoint._get_support_binder()` (lazy) + `close()`; Verdrahtung in
  `_handle_stream` (begin/resume nach erstem `support_status`-Emit, `heartbeat` je Loop-Tick);
  grace-gekoppeltes `end()` in `_grace_expired`.
- `db/coordinator_db.py`: `SupportStatusRecord(active, username, since_ms, count=0)`;
  `DEFAULT_SUPPORT_STALE_SEC=30`; `get_support_status(user_id, stale_sec)` (liest
  `cdb.support_sessions` ⋈ `cdb.investigators`).
- `db/connection_manager.py`: `DatabaseBundle` (Feld `coordinator`, `get_active_sse_clients()`);
  `ctx.mode`/`ctx.user_id`/`ctx.investigator_id`/`ctx.coordinator_db`.
- `management/support_sessions/support_sessions_repo.py`: `SupportSessionsRepo` (siehe §7.4).
- Frontend: `toolbar/toolbar.js` `SupportIndicatorModule` — reine `_formatSupportLabel(count, safeUsername)`
  / `_formatSupportAnnounce(count, rawUsername)`, Handler `support:status_changed` (liest `support_count`);
  DOM `#forensic-support-indicator`; `userinfo/sse_layer.js` registriert `support_status`.
- Tests: `tests/test_events_support_wiring.py` (W01–W10, P01–P05),
  `tests/unit/test_support_indicator.test.js` (L01–L08).
- *(313)* `management/case_events/case_events_repo.py`: `EVENT_KINDS`, `insert_event_row()`
  (Spiegelungs-Helfer), `CaseEventsRepo` (`list_events`, `add_manual_event`);
  `management/gateway/coordinator_writer.py`: `audited_write(..., after_audit=...)`;
  `management/cases/cases_repo.py`: Spiegelung in `create_case`/`assign`/`set_status`;
  CLI `management/case_events/case_events_admin.py`; Tests
  `tests/test_management_case_events.py` (E01–E12).

### 7.4 `SupportSessionsRepo` — API-Kurzreferenz
- `start(user_id, supporter_id, *, actor_id=None, meta=None) -> session_id` — AUDIT `SUPPORT_SESSION_STARTED`.
- `heartbeat(session_id) -> bool` — plain UPDATE, **kein** Audit; False wenn Sitzung beendet/unbekannt.
- `end(session_id, *, actor_id=None, meta=None) -> Optional[int]` — AUDIT `SUPPORT_SESSION_ENDED`; idempotent (bereits beendet → None); unbekannt → `SupportSessionsError`.
- `get_active(user_id, stale_sec) -> list[dict]` — aktive Sitzungen (nicht beendet, Heartbeat frisch), sortiert `started_at ASC`.
- `prune(older_than_sec) -> int` — entfernt beendete/veraltete Zeilen, **kein** Audit.
- Verbindung muss `isolation_level=None` (Autocommit) sein (Gateway-Annahme).

### 7.5 Offene Nachläufe / To-Dos
1. **`setup_coordinator_dev.py`-Analyse (vor Abschluss B7):** Das DEV-Skript rüstet u. a. das mit M002 entfernte `scrape_jobs.assigned_to` per `ALTER` wieder nach. Prüfen, welche Funktionalität überhaupt noch gebraucht wird, dann bereinigen. *(mc 2026-07-01)*
2. **Live-Stammdaten anlegen:** Neue Mitarbeiter über `investigators_admin create` eintragen; Fälle über `cases_admin` zuweisen (die 10 Live-User waren mangels bekannter IDs zurückgestellt).
3. **Backup-Modul (P1, Tag 4):** Speicherplatz-Vorabprüfung einbauen — Auslöser war das `default.db`-Malformed durch Voll-Laufen der Platte beim Fallanlegen (2026-07-01).
4. **GitHub-PAT widerrufen:** am Session-Ende unter `github.com/settings/personal-access-tokens` löschen.
5. **Roadmap-Rest B7:** Tag 3 Ampel-Dashboard — **Backend Build 314 geliefert (§9)**, Frontend Build 315 offen; Tag 4 Backup/PITR (Migrations-Version **M005+**); P2-Welle (Vorlageneditor, Nachrichten, Metriken/Lastverteilung, Rollen-Layouts). ~~`case_events` als eigener additiver Build~~ — **erledigt mit Build 313 (M004, §8)**.

### 7.6 Build-Nummerierung & Workflow
- Nächster Code-Build: **315** (Ampel-Dashboard Frontend, browser-abnahmepflichtig). Buildnummern iterieren je Lieferung; ZIP `aiw_webserver_<build>.zip` (repo-relative Pfade), nur geänderte Dateien + `build.json`, MD5 je Datei.
- Workflow: Bauplan → **mc** → Syntaxcheck aller geänderten Dateien → volle Regression `run_tests.py` (pytest + vitest, 0 Fehler) → `build.json`-Bump → ZIP → MD5 → `present_files`.
- Umgebung hier: Python 3.12.3 / SQLite 3.45.1 (PROD: Python 3.14, SQLite 3.14, Windows-11-Offline-Cloud, UNC-Pfade). `mc` = Freigabe-Token.

---

## 8. Ereigniszeitstrahl `case_events` (Build 313 — GELIEFERT 2026-07-02)

### 8.0 Ziel
`case_events` (Idee 11) ist das chronologische **Lesemodell je Fall** für das
Ampel-Dashboard (Tag 3) und den Nutzerinfo-Tab: Fall angelegt, zugewiesen,
Statuswechsel, Freigabe, manuelle Ermittler-Einträge. Der forensische **Beweis**
jedes Ereignisses bleibt der hash-verkettete `audit_log`; jede Zeitstrahl-Zeile
trägt die `seq` ihres Belegs (`audit_seq`).

### 8.1 Migration M004 (additiv) — `m004_case_events.py`
`case_events(id, user_id → cases, event_kind, payload JSON, created_by →
investigators, created_at, audit_seq)`, Index `(user_id, created_at)`.
`event_kind` wird — wie `audit_log.event_type` — im **Code** validiert
(`EVENT_KINDS`), bewusst **ohne** CHECK-Constraint: neue kinds bleiben additiv
(kein Tabellen-Rebuild). **Deploy erfordert `migrate.py`-Lauf** (anders als 312).

### 8.2 Vokabular `EVENT_KINDS` (eingefroren, nur erweitern)
`case_created` · `assigned` · `status_changed` · `approved` · `manual`.
`approved` ist eigener kind, damit das Dashboard Freigaben ohne Payload-Parsing
hervorheben kann.

### 8.3 Gateway-Hook `after_audit` (`coordinator_writer.py`)
`audited_write(..., after_audit: Callable[[con, seq], None])` — läuft **nach**
dem Audit-Append, **innerhalb** derselben Transaktion. Damit committen
Fach-Write + Beleg + Zeitstrahl-Zeile atomar oder gar nicht; ein Hook-Fehler
rollt alles zurück (Grundregel 1, verifiziert E08/E12). Rückwärtskompatibel
(Default `None`).

### 8.4 Spiegelung aus `CasesRepo` (mc 2026-07-02)
`create_case` → `case_created` (Zeitstrahl-Anker; über den mc-Wortlaut
„Zuweisungen, Statuswechsel, Freigaben" hinaus ergänzt — ein Zeitstrahl ohne
Startpunkt wäre unvollständig; im Chat transparent angemerkt), `assign` →
`assigned` (auch Entzug, `assigned_to=None`), `set_status` → `status_changed`
bzw. `approved` (inkl. `approved_at`). **Bewusst NICHT gespiegelt:**
`set_priority`, `set_note` (geringer Zeitstrahl-Wert; `note` sensibel) —
verifiziert E07. Die Spiegelzeilen erzeugen **keinen zweiten** Audit-Eintrag;
ihr Beleg ist der ohnehin geschriebene `CASE_*`-Eintrag (`audit_seq`).

### 8.5 `CaseEventsRepo` + CLI
- `list_events(user_id, limit=None)` — chronologisch (Tie-Break `id`),
  `created_by` als `system_username` aufgelöst, `payload` als dict.
- `add_manual_event(user_id, text, actor_id, meta)` — Beleg `CASE_EVENT_ADDED`;
  **Text nur im Zeitstrahl-Payload**, Audit nur Faktum + `text_len`
  (Sensibilitätsregel analog `cases.note`). Fall-Existenz wird innerhalb der
  Schreibsperre geprüft (kein TOCTOU); leerer Text abgewiesen.
- CLI `python -m management.case_events.case_events_admin list|add ...`
  (Subkommando-Muster wie §5.4).

### 8.6 Tests (E01–E12, `tests/test_management_case_events.py`)
M004 via `discover`+Runner idempotent (E01); manuelle Einträge atomar +
Sensibilität (E02, E09); Spiegelung aller vier Wege inkl. `audit_seq`-Kopplung
(E03–E06); Nicht-Spiegelung priority/note (E07); Rollback-Atomarität über den
Hook (E08, E12); `list_events`-Semantik (E10); `verify_chain` grün (E11).
Bestandssuite `test_management_cases.py`: Fixture um M004 erweitert
(B01/B10-Zählwerte nachgeführt) — Spiegelung schlägt ohne `case_events` hart
fehl (gewollt, keine stille Degradation).

---

## 9. Ampel-Dashboard — Backend-Read-Model (Build 314 — GELIEFERT 2026-07-02)

### 9.0 Aufteilung 314/315 (wichtig)
Das Ampel-Dashboard (Tag 3) zeigt der Chef-Ermittlerin je Fall eine Ampel plus
Kennzahlen. Die **Anzeige** ist browserbasiert und muss **live abgenommen**
werden — das ist derzeit nicht möglich (nur automatisierte Tests). Deshalb ist
Tag 3 zweigeteilt:
- **Build 314 (hier):** das **Backend-Read-Model** — vollständig durch
  `run_tests.py` abgedeckt, ohne Browser prüfbar.
- **Build 315 (offen):** das **Frontend** — wird erst gebaut, wenn es im
  Browser verifiziert werden kann.

### 9.1 `DashboardRepo` (nur lesend)
`management/dashboard/dashboard_repo.py`. **Kein** `CoordinatorWriter`, **keine**
Migration, **kein** Anfassen von `evidence_/forensic_/assets_`-DB. `coordinator.db`
ist ohnehin nur-lesend (Produktivbetrieb-Regel) → **kein Datenverlust-Risiko**.
`list_case_overview(*, thresholds, support_stale_sec, now)` liefert je Fall ein
`CaseOverview`-DTO aus **einer** Aggregatabfrage über `cases` +
`case_events` (Build 313) + `support_sessions` (Build 311). Zugriffsstil:
direkte Verbindung, unqualifizierte Tabellennamen (wie `CasesRepo`), **nicht**
der `cdb.`-Stil aus `db/coordinator_db.py`.

### 9.2 Rohsignale + Sensibilität
`CaseOverview`: `status`, `priority`, `assigned_to` (→ `system_username`/
`display_name` aufgelöst), `has_note` (**bool, ohne den Notiztext zu lesen**),
`approved_at`, `total_pages_scraped`, `event_count`, `last_event_kind`,
`last_event_at`, `support_active/count/since`, `last_activity_at` =
`max(updated_at, last_event_at)`. Der **manuelle Ereignistext**
(`case_events.payload`) wird **bewusst nicht** gelesen (Sensibilität, analog
`cases.note`, §8.5).

### 9.3 Ampel-Ableitung `classify_ampel` — **PROVISORISCH (mc ausstehend)**
Reine Funktion, Regelreihenfolge (erste greift): `closed`→GRÜN (abgeschlossen);
`approved`→GRÜN (freigegeben); `open` & unzugewiesen→ROT (offen_nicht_zugewiesen);
offen/laufend & `idle ≥ red_idle_days`→ROT (inaktiv_lang) bzw.
`≥ amber_idle_days`→GELB (inaktiv_mittel); sonst GRÜN (aktiv).
Schwellen `AmpelThresholds(amber_idle_days=7, red_idle_days=21)` sind ein
**begründeter Vorschlag**, an **einer** Stelle austauschbar. **Support-Präsenz
fließt bewusst NICHT in die Farbe** — sie ist ein orthogonales Live-Abzeichen
(Design-Vorschlag). Da das Frontend fehlt, kann eine noch falsche Schwelle
derzeit **keine Ermittlung fehlleiten**.

### 9.4 Sortierung — **PROVISORISCH**
Priorität aufsteigend (1 zuerst), dann letzte Aktivität absteigend, dann
`user_id` — „was Aufmerksamkeit braucht, steht oben".

### 9.5 CLI + Tests
CLI `python -m management.dashboard.dashboard_admin list` (nur lesend,
ASCII-Ampel). Tests `tests/test_management_dashboard.py` (**D01–D12**,
automatisiert, kein Browser): Migrationslauf, leere Menge, alle Ampel-Zweige,
Idle-Schwellen (injiziertes `now`), Support frisch/stale, Ereignis-Aggregat,
`has_note` ohne Textausgabe, Sortierung, Schwellen-Justierbarkeit,
**Read-Only-Nachweis** (Zeilenzahlen vorher==nachher).

### 9.6 Offene Entscheidungen (mc)
1. **Ampel-Semantik** final: Schwellen (7/21 Tage), Regelreihenfolge und
   „Support = eigenes Abzeichen, nicht Farbe" bestätigen/justieren.
2. **Sortierung** der Übersicht bestätigen.
3. **Frontend-Verortung** für Build 315 (eigene Management-Seite vs. Einbettung).

---

## Änderungshistorie

- **v0.9 (2026-07-02):** §9 „Ampel-Dashboard — Backend-Read-Model" ergänzt
  (**Build 314 geliefert**): `DashboardRepo` (nur lesend, kein Datenverlust-Risiko),
  `CaseOverview`, reine `classify_ampel` mit **provisorischer** Ampel-Semantik
  (mc ausstehend), CLI, Tests D01–D12. Tag 3 in 314 (Backend) / 315 (Frontend)
  geteilt; Frontend braucht Live-Abnahme. §7.1/§7.5/§7.6 fortgeschrieben,
  nächster Build **315**. Live-Verifikation Build 312 weiterhin offen.

- **v0.8 (2026-07-02):** §8 „Ereigniszeitstrahl `case_events`" ergänzt (**Build 313
  geliefert**): M004 (additiv), `after_audit`-Gateway-Hook, Spiegelung
  Anlage/Zuweisung/Status/Freigabe aus `CasesRepo` mit `audit_seq`-Kopplung,
  manuelle Einträge (`CASE_EVENT_ADDED`), `CaseEventsRepo` + CLI, Tests E01–E12.
  §7.1/§7.3/§7.5/§7.6 fortgeschrieben; nächster Build **314** (Tag 3
  Ampel-Dashboard). Live-Verifikation Build 312 weiterhin offen (manueller Test
  verschoben, mc 2026-07-02).

- **v0.7 (2026-07-02):** §6/§7 auf **Build 312** (Verdrahtung + Frontend, geliefert) fortgeschrieben:
  `SupportPresenceBinder` (`forensic_api/support_presence.py`, gekapselte dedizierte
  coordinator.db-Direktverbindung), SSE-Lebenszyklus begin/heartbeat/resume/end mit
  **grace-gekoppeltem** Ende (mc: Entscheidung 1 — RESUMING führt bestehende Sitzung fort, kein
  spurioses ENDED/STARTED-Paar), `_get_support_status` mode-aware + `support_count`, Indikator
  „Support aktiv (N)". Neue Tests `tests/test_events_support_wiring.py` (W01–W10, P01–P05) und
  `tests/unit/test_support_indicator.test.js` (L01–L08). §7.2 neu = **Live-Verifikation
  (Test-Session 2026-07-02)**; nächster Build 313. Regression grün (Python 628/59 skip,
  JS 408/1 skip/1 todo).

- **v0.6 (2026-07-01):** §7 „Übergabe & Nächste Aufgaben" ergänzt (vollständiger Handover für
  Kontextwechsel: Projektstand 306–311, detaillierter Build-312-Plan mit Code-Ankern und
  JS-Console-PoC-Protokoll, `SupportSessionsRepo`-API-Referenz, offene Nachläufe, Workflow).

- **v0.5 (2026-07-01):** §6 „Echte Support-Sitzungserfassung" ergänzt; Backend-Fundament als
  **Build 311** (M003 `support_sessions`, `SupportSessionsRepo`, Read-Repoint `get_support_status`
  mit Zähler; Start/Ende auditiert, Heartbeat nicht; Stale-Default 30 s). Verdrahtung + Frontend
  als **Build 312** abgetrennt (Browser-Test nötig, Console-PoC-Protokoll).

- **v0.4 (2026-07-01):** §5 „Ermittler-Verwaltung — investigators-CLI (Build 310)" ergänzt
  (`InvestigatorsRepo` + auditierte CLI `create`/`update`/`list`; kein Löschen, `system_username`
  unveränderlich; zwei additive Audit-Event-Typen; Reihenfolge CLI **vor** Support-Sitzung).
  Nachlauf `setup_coordinator_dev.py`-Analyse verankert. Build 309 übersprungen (mc).


- **v0.3 (2026-07-01):** §3 „Tag 2" ergänzt (cases + scrape_jobs-Rebuild + Repointing
  userinfo_data.py + auditierte Zuweisungs-CLI, Build 307); Roadmap Tag 2 aktualisiert
  (Rebuild statt Drop wegen FK; `case_events` als eigener additiver Build M003 abgetrennt,
  Entscheidung „Schritt für Schritt"); altes §3 → §4.

- **v0.2 (2026-07-01):** Offene Punkte 1–3 geklärt; §2.8 in Migrations- vs. Live-Backup-Politik
  aufgetrennt (Snapshot statt Dateikopie); Platzhaltermodule `evidence`/`assets` in §2.1
  ergänzt; To-Do für `schema_migrations`-Retrofit verankert.
- **v0.1 (2026-07-01):** Erstfassung; Tag 1 vollständig spezifiziert, Gesamt-Roadmap.

---

*Dokument-Ende · Bauplan Baustelle 7 · Version 0.7 · 2026-07-02*

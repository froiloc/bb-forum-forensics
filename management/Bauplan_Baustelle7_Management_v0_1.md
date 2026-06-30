# Bauplan Baustelle 7 — Management-Interface

**Version:** 0.2 · **Datum:** 2026-07-01
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
| 2 | `cases` + `scrape_jobs`-Drop + Repointing (**ein atomarer Build**) + Ereigniszeitstrahl | 11 | `coordinator.db` | M002 (destruktiv): Drop `assigned_to`/`note`; Create `cases`, `case_events` |
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

## 3. Geklärte Punkte (Stand v0.2, Projektgespräch 2026-07-01)

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

## Änderungshistorie

- **v0.2 (2026-07-01):** Offene Punkte 1–3 geklärt; §2.8 in Migrations- vs. Live-Backup-Politik
  aufgetrennt (Snapshot statt Dateikopie); Platzhaltermodule `evidence`/`assets` in §2.1
  ergänzt; To-Do für `schema_migrations`-Retrofit verankert.
- **v0.1 (2026-07-01):** Erstfassung; Tag 1 vollständig spezifiziert, Gesamt-Roadmap.

---

*Dokument-Ende · Bauplan Baustelle 7 · Version 0.1 · 2026-07-01*

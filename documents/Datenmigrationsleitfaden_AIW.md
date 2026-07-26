# Leitfaden zur Datenmigration im Produktivbetrieb

## IT-Forensisches Ermittlungswerkzeug Advanced Investigation Wrapper (AIW) · NRW

**Version:** 0.6
**Build-Bezug:** 563 (coordinator-Migration M040, AP-3E/Instanz B; Abschnitt 15 unverändert aus v0.5/Build 540, Abschnitt 14 aus v0.4/Build 533, Abschnitte 1–13 aus v0.3/Build 469)
**Datum:** 2026-07-26
**Status:** Verbindlicher Workflow für Datenmigration im Produktivbetrieb
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH

---

## Änderungshistorie

| Version | Build | Datum      | Änderung                                                                                                                                                              |
| ------- | ----- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0.6     | 563   | 2026-07-26 | Neuer **Abschnitt 16**: die coordinator-Migration **M040** (`fulltext_zweck`, `fulltext_release`, Recht `fulltext.release`) für die fallübergreifende Volltextsuche (AP-3E, Instanz B) — rein additiv, **keine** Beweismitteldatenbank berührt. Enthält den **Sperrvermerk**: M040 darf erst eingespielt werden, wenn Instanz A ihre Migrationen m035–m039 geliefert hat, weil der `MigrationRunner` einen Höchststand statt einer Menge führt und später gelieferte niedrigere Nummern sonst **still übersprungen** würden (Beleg: `management/Vermerk_Migrationsluecke_Parallelbetrieb_v0_1.md`, reproduziert mit `tools/diag_migrationsluecke.py`). Neues Prüfwerkzeug `tools/pruefe_migrationskette.py`. *Anmerkung: zu v0.5 (Abschnitt 15, M034) gibt es keine Zeile in dieser Tabelle — der Kopf wurde fortgeschrieben, die Historie nicht. Hier nur vermerkt, nicht von mir nachgetragen.* |
| 0.4     | 533   | 2026-07-26 | Neuer **Abschnitt 14**: die evidence-Migrationen **M002** (`annotation_tatzeit`, Build 532) und **M003** (`evidence_audit_log` + Genesis, Build 533) — die ersten Strukturänderungen an einer Beweismitteldatenbank nach dem 01.07.2026. Beide additiv und datenneutral, nachgewiesen über Inhaltshashes (TZ04/EA03). Enthält den ausdrücklichen Vermerk, dass der Eintrag für M002 bis hierher **gefehlt** hat. Beleg: Entscheidung mc 2026-07-26 (eigene Beleg-Kette in der evidence-Datei statt Best-Effort-Eintrag in `coordinator.db`). |
| 0.1     | 303   | 2026-06-25 | Erstfassung — Migrationsleitfaden (Vier-Phasen-Workflow, Gerichtsfestigkeit, Einzel-DB)                                                                             |
| 0.3     | 469   | 2026-07-20 | Neuer **Abschnitt 13**: Migration **M019** — globale Schlüsselumstellung `user_id` → `subject_id` in `coordinator.db` (Weg A, `RENAME COLUMN`): Vorher-Backup, Weg-A-PoC-Protokoll (`tools/poc_m019_weg_a.py`), Roll-forward, Verifikations-Checkliste, Rollback-Pfad. Beleg: mc-Freigabe 2026-07-20, PoC bestanden. |
| 0.2     | 315   | 2026-07-03 | Fortschreibung für die **Datenbank-Flotte**: Bestandsaufnahme der vorhandenen Engine (`schema_migrations`), zentrale **`migration.db`** (Katalog/Inventar/Ledger), Rollentrennung, revidiertes Gegenzeichnungsmodell (lückenlose Belegbarkeit statt Instanz-Handunterschrift), geführter, teilautomatisierter **Companion-Workflow**, Dry-Run/Flottenplanung, Teil-Fehlschlag-Behandlung. Belege: `management/migrations/runner.py`, `management/migrate.py`, `evidence_schema_db.sql`. Grundlage: mc 2026-07-03. |

> **Lesehinweis zur v0.2:** Die Abschnitte 1–5 (Prinzipien, Phase 0, Vier-Phasen-Workflow, Teamregeln, Tool-Landschaft) aus v0.1 bleiben **inhaltlich erhalten**. Neu bzw. revidiert sind: die Verfeinerung des Vieraugenprinzips in §1 und Phase 3, sowie die **neuen Abschnitte 6–11** zur Flotten-Migration. Wo v0.2 einen v0.1-Punkt präzisiert, ist dies ausdrücklich vermerkt — es wird nichts stillschweigend ersetzt (Grundregel 1).

---

## 1. Grundlegende Prinzipien für Gerichtsfestigkeit

- **Lückenlose Nachvollziehbarkeit (Provenance):** Jeder Migrationsschritt erzeugt signierte Protokolle, die zusammen mit den Datenbanken archiviert werden.
- **Unveränderbarkeit:** Alle Protokolle, Prüfsummen und archivierten Datenbanken werden nach Erzeugung sofort mit einer digitalen Signatur (GPG) versehen und in einem schreibgeschützten Ablageort abgelegt.
- **Trennung von Umgebungen:** Migration findet nie auf dem Produktivsystem statt, sondern auf einer dedizierten, isolierten Maschine.
- **Reproduzierbarkeit:** Der gesamte Ablauf wird ausschließlich über versionierte Skripte gesteuert; kein manuelles SQL.
- **Vieraugenprinzip:** Die Verifikationsphase (Phase 3) muss von einer zweiten autorisierten Person durchgeführt werden, die nicht die Migration selbst geschrieben oder ausgeführt hat.

**Ergänzung v0.2 (mc 2026-07-03):**

- **Selbstbeschreibende Datenbanken:** Jede migrierbare Datenbank führt ihre eigene Migrations-Registry `schema_migrations` mit sich. Der autoritative „welche Migration ist hier angewandt"-Zustand liegt damit **in der Datenbank selbst** — eine exportierte oder asservierte Beweis-DB kann ihre Schema-Herkunft **ohne** externe Datei belegen (Provenance, gerichtsfeste Selbstauskunft).
- **Kein Single Point of Failure für Migrationswissen:** Die zentrale `migration.db` (Abschnitt 6) ist ein **Katalog- und Betriebsregister**, kein alleiniger Wahrheitsspeicher. Ginge sie verloren, ließe sie sich aus den Per-DB-`schema_migrations` und den signierten Phasen-Artefakten rekonstruieren.
- **Belegbarkeit statt Instanz-Handunterschrift (Präzisierung des Vieraugenprinzips):** Bei einer Flotte gleichartiger Datenbanken (`*_<uid>.db`) skaliert eine handschriftliche Gegenzeichnung *pro Instanz* nicht. Die Gegenzeichnung darf sich stattdessen auf **lückenlose Belegbarkeit aller vorgenommenen Änderungen** stützen: menschliche Vieraugen-Prüfung **einmal je Migration × Datenbank-Art** (auf Skript und synthetischer Referenz-DB, Phase 0) plus **maschinelle Lossless-Verifikation und vollständige, unveränderbare Protokollierung je Instanz** (Abschnitt 8). Details: Phase 3 (revidiert) und Abschnitt 8.

---

## 2. Vorbereitende Phase 0: Migrationsbau und Test

Bevor eine Produktivdatenbank angefasst wird:

0. **Migrationsskript versionieren** – Jede Schemaänderung bekommt eine eindeutige, aufsteigende Sequenznummer (z. B. `020_Add_hash_index.sql`). Alle Skripte liegen in einem Git-Repository mit Tag für die Softwareversion.
1. **Referenzdatenbank aufbauen** – Eine anonymisierte oder synthetische Produktivkopie wird erzeugt und in der Testumgebung bereitgestellt.
2. **Trockenlauf** – Migration wird exakt wie in Produktion durchlaufen, inkl. Prüfsummenberechnung, Signatur und Administrator-Verifikation. Das Ergebnis wird mit einem Erwartungswert abgeglichen.
3. **Rollback-Plan testen** – Wiederherstellung aus dem Backup der Phase 1 muss nachweislich funktionieren.
4. **Prüfprotokollvorlage bereitstellen** – Eine strukturierte Checkliste (z. B. Markdown oder PDF-Formular) für die manuelle Verifikation, die später unterschrieben und signiert wird.

**Ergänzung v0.2 — Phase 0 ist der Ort der menschlichen Verifikation je Datenbank-Art.** Die inhaltliche Vieraugen-Prüfung findet hier statt: auf dem **Migrationsskript** (Code-Review durch die zweite Person) und auf der **synthetischen Referenz-DB** (Trockenlauf mit Erwartungswert-Abgleich). Ist diese Prüfung je `db_kind` bestanden und gegengezeichnet, deckt sie die anschließende Flotten-Anwendung derselben Migration ab (Abschnitt 8) — sofern jede Instanz maschinell verifiziert und lückenlos protokolliert wird.

---

## 3. Der verfeinerte Vier-Phasen-Workflow

### Phase 1 – Sichern, Versionieren, Siegel setzen

Ziel: Ein kryptographisch verankerter Ausgangszustand, der jederzeit unverändert reproduziert werden kann.

1. **Datenbankintegrität prüfen** – `sqlite3 prod.db "PRAGMA integrity_check;"` → Ergebnis protokollieren.
2. **Datenbank in Backup-Verzeichnis kopieren** – Benennung: `db_v<versionsnr>_<timestamp>_<host>.backup.db`
3. **SHA512-Prüfsumme bilden** – `sha512sum db_...backup.db > db_...backup.db.sha512`
4. **Metadaten-Datei erzeugen** (z. B. `backup_manifest.json`):

   ```json
   {
     "source_db_path": "/data/prod.db",
     "software_version": "2.3.1",
     "timestamp": "2026-06-25T08:15:00Z",
     "sha512": "...",
     "operator": "m.mustermann",
     "integrity_check": "ok"
   }
   ```
5. **Gesamte Backup-Artefakte digital signieren** – `gpg --detach-sign --armor backup_manifest.json` und `gpg --detach-sign --armor db_...backup.db`. Die Signaturdateien werden mitarchiviert.
6. **Archivierung** – Alle Dateien kommen in ein Verzeichnis `migration/v2.3.1_to_v3.0.0/phase1/`, das sofort auf Read-Only gesetzt wird (z. B. `chmod -R a-w` oder WORM-fähiges NAS).

### Phase 2 – Automatisierte Migration mit Prüfprotokoll

Ziel: Transformation unter strenger Beobachtung, mit maschinell prüfbarem Äquivalenznachweis für alle unveränderten Daten.

**Empfohlenes Prinzip:** Die Migration wird in eine separate, leere SQLite-Datenbank geschrieben (Ziel-DB). Das bewahrt das Original unangetastet und ermöglicht später einfachen Vergleich.

1. **Arbeitskopie der gesicherten DB erstellen** (nur für Migration, Schreibzugriff).
2. **Vorher-Prüfsumme der Arbeitskopie notieren** (Zeuge, dass sie identisch zum signierten Backup ist).
3. **Migrationsskripte sequenziell ausführen** – Jedes Skript in eigener Transaktion; nach jedem Schritt: `PRAGMA integrity_check;`, Rowcounts pro Tabelle, SHA512 der gesamten DB in `migration_log.jsonl`.
4. **Automatisierte Prüfungen im Ziel-Schema:** alle Tabellen/Indizes vorhanden? Constraints eingehalten (`PRAGMA foreign_key_check;`)? Nicht migrierte Rohdaten (z. B. BLOB-Inhalte) bitidentisch zum Original?
5. **Differenzbericht erstellen** – Rowcounts und Prüfsummen vorher/nachher für Kernentitäten.
6. **Abschlussprüfung** – SHA512 der migrierten DB berechnen und ins Log schreiben.
7. **Signieren des gesamten Phase-2-Ordners** – `migration_log.jsonl`, `diff_report.txt`, Skripte, stdout-Logs → GPG.

**Ergänzung v0.2:** Die in Phase 2 ohnehin erhobenen Größen (Vorher/Nachher-SHA512, Rowcounts, `integrity_check`, `foreign_key_check`) werden zusätzlich **strukturiert in die zentrale `migration.db` (Tabelle `migration_runs`, Abschnitt 6.3)** geschrieben — append-only und hash-verkettet. Das `migration_log.jsonl` bleibt als signiertes Roh-Artefakt erhalten; die `migration.db` macht dieselben Belege **flottenweit abfragbar** (welche Instanz steht wo, was schlug wo fehl).

### Phase 3 – Administrator-Verifikation (revidiert v0.2)

Ziel: Menschliche Prüfung der Datenkonsistenz mit dokumentierter Nachvollziehbarkeit und Gegenzeichnung.

**Revision (mc 2026-07-03):** Die Gegenzeichnung stützt sich auf **lückenlose Belegbarkeit** statt auf eine Handunterschrift je Datenbank-Instanz. Konkret:

1. Die **menschliche** Verifikation erfolgt **einmal je Migration × Datenbank-Art** auf der synthetischen Referenz-DB aus Phase 0. Die zweite autorisierte Person prüft die vorab festgelegte **Verifikations-Checkliste**:
   - Vergleich der Zeilenzahlen kritischer Tabellen mit dem Diff-Report.
   - Sichtung der ersten und letzten 10 Einträge zentraler Protokolltabellen.
   - Prüfung exemplarischer Berechnungsergebnisse (z. B. Hashes forensischer Dateien).
   - Kontrolle von Metadatenfeldern (Zeitstempel, Versionseinträge).
   - Prüfung auf NULL-Werte, wo nach Migration Werte stehen müssen.
2. Jeder Checklistenpunkt wird mit **OK / Abweichung** quittiert; Abweichungen detailliert im Bemerkungsfeld.
3. Das unterzeichnete Dokument wird eingescannt und mit den Artefakten abgelegt.
4. **Digitale Gegenzeichnung:** Die zweite Person signiert (a) die **Migrations-Definition** (Skript + Katalogeintrag, Abschnitt 6.1) und (b) das **aggregierte, vollständig nachvollziehbare Lauf-Ledger** der Flotten-Anwendung (`migration_runs`, Abschnitt 6.3) mit ihrem GPG-Schlüssel.
5. **Für jede einzelne Instanz** genügt die **maschinelle** Lossless-Verifikation (Abschnitt 8) plus die unveränderbare Protokollierung im Ledger — **sofern** jede vorgenommene Änderung dort lückenlos belegt ist. Weicht eine Instanz vom erwarteten Muster ab (z. B. Rowcount außerhalb Toleranz, `foreign_key_check`-Fehler, BLOB-Hash-Abweichung), wird sie **nicht** stillschweigend mitgezeichnet, sondern vom System zur gesonderten menschlichen Prüfung markiert (Abschnitt 7).

### Phase 4 – Produktivübernahme und Archivierung

Ziel: Sicherstellen, dass genau die verifizierte Datenbank in Produktion geht, und alle Vorgangsdokumente unveränderbar archiviert werden.

1. **Vorher-Snapshot des Produktivsystems** (vor dem Austausch) – analog Phase 1.
2. **Konsistenzcheck** – SHA512 der migrierten/verifizierten DB gegen den in Phase 3 protokollierten Wert (Schutz vor Manipulation während der Übertragung).
3. **Austausch der Datenbank** – Dienste stoppen, alte DB wegsichern, neue DB an vorgesehenen Platz, Rechte setzen.
4. **Kaltstart-Integritätstest** – lesender Selbsttest nach dem Start.
5. **Dokumentation des Deployments** – Zeitstempel, ausführende Person, SHA512 der neuen DB, Testergebnis.
6. **Archivierung des gesamten Migrationspaketes** – Verzeichnisse `phase1`–`phase4` in einen finalen Archivordner; signierter Tarball auf WORM-Speicher; GPG-Signaturen aller Beteiligten separat dokumentiert.

**Ergänzung v0.2:** Nach erfolgreicher Übernahme aktualisiert das System `migration.db.db_registry` (neue `current_version`, `last_verified_at`, `last_status`) sowie den `migration_runs`-Abschluss. Erst wenn der Ledger-Eintrag geschrieben und die betroffene DB ihre eigene `schema_migrations` aktualisiert hat, gilt die Instanz als migriert (beide Belege müssen übereinstimmen — Abschnitt 6.4).

---

## 4. Regeln, die im Team verankert werden

- **Keine Migration ohne versioniertes Skript.**
- **Jede Migration erzeugt mindestens: Backup + SHA512 + signiertes Manifest + Migrationslog + Diff-Report + Verifikationsprotokoll + Deployment-Protokoll.**
- **Alle Protokolle sind Append-only / Write-Once.**
- **GPG-Schlüssel der Administratoren liegen auf getrennten, passwortgeschützten Smartcards oder HSM.**
- **Die Migration erfolgt auf einem dedizierten, vom Produktivnetz abgeschotteten Rechner.**
- **SQLite-WAL-Modus beachten:** Vor dem Sichern der Produktiv-DB `VACUUM INTO 'backup.db'` verwenden, um eine saubere, konsistente Kopie zu bekommen.
- **Kein einziges Byte der Originaldatenbank wird in Phase 2 verändert.** Die Migration arbeitet stets auf einer Kopie.

**Ergänzung v0.2:**

- **Katalog-Pflicht:** Keine Migration wird ausgeführt, deren Definition nicht im `migration_catalog` steht und deren Katalog-Prüfsumme nicht mit der Prüfsumme des `m###`-Skripts übereinstimmt (Abschnitt 6.4).
- **Ledger-Pflicht:** Kein Migrationslauf ohne append-only-Eintrag in `migration_runs` (Vorher/Nachher-SHA512, Status, Backup-Pfad, Operator).
- **Selbstbeschreibungs-Pflicht:** Nach jeder Migration muss die betroffene DB ihre eigene `schema_migrations`-Zeile tragen; `db_registry` und `schema_migrations` müssen übereinstimmen.

---

## 5. Vorschlag für die Tool-Landschaft

Es soll sehr viel mit Bordmitteln abgedeckt werden:

- **SQLite3-Kommandozeile** für Integritätschecks, VACUUM und Schemaexport.
- **GnuPG** für Signaturen.
- **Git** für die Migrationsskripte (mit Signed Tags).
- Für Phase 3 ein Markdown- oder PDF-Checklisten-Template.

**Ergänzung v0.2 — Python-Engine statt reinem Shell-Skript:** Für die Flotte tritt die **bereits vorhandene** Python-Migrations-Engine (`management/migrations/runner.py`, Abschnitt 5a) an die Stelle eines reinen Shell-Orchestrators. Die gerichtsfesten Primitive (GPG, WORM, SHA512, `VACUUM INTO`, abgeschotteter Rechner) **bleiben unverändert** gültig; sie werden von der Engine aufgerufen und im Ledger belegt.

### 5a. Bestandsaufnahme: Was die vorhandene Engine bereits leistet (Beleg)

Beleg: `management/migrations/runner.py`, `management/migrate.py`.

- **Geordnete Erkennung:** `discover()` findet `m###_*.py`-Migrationsmodule und ordnet sie nach `VERSION`.
- **Per-DB-Registry `schema_migrations`** mit den Spalten `version, name, kind ('additive'|'destructive'), checksum, applied_at, row_count_before, row_count_after`.
- **Manipulationsschutz:** Bereits angewandte Migrationen werden per `_check_checksum()` gegen nachträgliche Veränderung geprüft.
- **Zeilenzahl-Verifikation** (`row_count_before/after`) und **Audit-Anbindung** sind vorhanden; Einstiegspunkt ist `python -m management.migrate` mit anschließender `verify_chain()`-Prüfung der Audit-Kette.

**Was fehlt (und in den Folge-Builds entsteht):** Flotten-Orchestrierung über viele `*_<uid>.db`, ein **zentraler Katalog**, ein **Backup-+Verify-Harness speziell für die Beweis-DBs**, sowie die **geführte Begleitung** (Companion, Abschnitt 7). Die vorhandene Engine ist bisher auf `coordinator.db` angewandt (M001–M004).

---

## 6. Datenbank-Landschaft, `migration.db` und Rollentrennung (NEU)

### 6.0 Datenbank-Landschaft und Migrationsvorbehalt

Beleg: Projektvorgaben (Produktivbetrieb ab 2026-07-01) sowie `evidence_schema_db.sql`.

| Datenbank-Art        | Beispiel-Datei         | pro Nutzer | Inhalt                         | Status ab 2026-07-01                         | Zeremonie |
| -------------------- | ---------------------- | ---------- | ------------------------------ | -------------------------------------------- | --------- |
| evidence             | `evidence_<uid>.db`    | ja         | Ermittler-Ergebnisse (Beweis)  | **Migrationsvorbehalt** (verlustfrei!)       | voll (Phasen 1–4) |
| forensic             | `forensic_<uid>.db`    | ja         | gesicherte Forumsseiten (BLOB) | **Migrationsvorbehalt**                       | voll |
| assets               | `assets_<uid>.db`      | ja         | gesicherte Assets              | **Migrationsvorbehalt**                       | voll |
| coordinator          | `coordinator.db`       | nein       | Fall-/Koordinationsdaten       | nur-lesend durch Ermittler; Schema wandelt sich per Engine | reduziert |
| default / templates  | `default.db`, `templates.db` | nein | Vorlagen/Defaults              | nur-lesend                                    | reduziert |

**Wichtiger Beleg-Befund:** Die Beweis-DBs sind **noch nicht selbstbeschreibend**. `evidence_schema_db.sql` führt lediglich eine **Inhalts**-Spalte `version_nr INTEGER NOT NULL DEFAULT 1` (Z. 46) — das ist eine Datensatz-Version, **keine** `schema_migrations`-Registry. Die **Erst-Migration** jeder Beweis-DB-Art muss die Registry `schema_migrations` einziehen (rein additiv), damit die DB fortan ihre Schema-Herkunft selbst belegt.

### 6.1 `migration_catalog` — deklarativer Soll-Zustand

Beantwortet: „welche Migration in welcher Version, in welcher Reihenfolge, nichts vergessen".

```
migration_catalog(
    db_kind        TEXT    NOT NULL,   -- 'evidence' | 'forensic' | 'assets' | 'coordinator' | ...
    version        INTEGER NOT NULL,   -- aufsteigend je db_kind
    name           TEXT    NOT NULL,
    checksum       TEXT    NOT NULL,   -- Prüfsumme des zugehörigen m###-Skripts
    kind           TEXT    NOT NULL CHECK(kind IN ('additive','destructive')),
    requires_backup INTEGER NOT NULL DEFAULT 1,
    depends_on     INTEGER,            -- optionale explizite Reihenfolge-Abhängigkeit
    PRIMARY KEY(db_kind, version)
)
```

### 6.2 `db_registry` — Flotten-Inventar

```
db_registry(
    db_kind         TEXT    NOT NULL,
    uid             INTEGER,           -- NULL für nicht-nutzerbezogene DBs (coordinator/…)
    path            TEXT    NOT NULL,
    current_version INTEGER NOT NULL DEFAULT 0,
    last_verified_at INTEGER,
    last_status     TEXT,              -- 'ok' | 'pending' | 'failed'
    PRIMARY KEY(db_kind, uid)
)
```

### 6.3 `migration_runs` — append-only, hash-verkettetes Lauf-Ledger

Macht den Migrationsvorgang **selbst** manipulationssicher und flottenweit abfragbar (analog der Audit-Log-Philosophie des Projekts).

```
migration_runs(
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    db_kind     TEXT    NOT NULL,
    uid         INTEGER,
    from_version INTEGER NOT NULL,
    to_version  INTEGER NOT NULL,
    started_at  INTEGER NOT NULL,
    finished_at INTEGER,
    status      TEXT    NOT NULL,      -- 'started' | 'ok' | 'failed' | 'restored'
    pre_sha512  TEXT,
    post_sha512 TEXT,
    backup_path TEXT,
    operator    TEXT,
    verifier    TEXT,
    prev_hash   TEXT    NOT NULL,      -- Hash-Verkettung (Vorgänger-Zeile)
    row_hash    TEXT    NOT NULL       -- Hash dieser Zeile
)
```

### 6.4 Rollentrennung (verbindlich)

- **Autoritativ = in der DB:** Der Zustand „welche Migration ist in *dieser* Instanz angewandt" steht in der DB-eigenen `schema_migrations` (selbstbeschreibend, gerichtsfest). Sie ist die **Wahrheit**.
- **`migration.db` = Betriebsregister:** Katalog (Soll), Inventar (welche Dateien existieren, wo stehen sie) und Ledger (was geschah). Sie ist **abgeleitet und rekonstruierbar** — kein alleiniger Wahrheitsspeicher, kein Single Point of Failure.
- **Abgleich-Pflicht:** Vor jedem Lauf gilt (a) `migration_catalog.checksum == Prüfsumme(m###-Skript)` — sonst harte Warnung „Katalog/Code-Drift"; (b) nach jedem Lauf `db_registry.current_version == MAX(schema_migrations.version)` der Instanz — sonst harte Warnung „Registry/Inventar-Divergenz".

---

## 7. Der geführte, teilautomatisierte Ablauf (Companion-Prinzip) (NEU)

**Grundhaltung (mc 2026-07-03): keine Vollautomatisierung.** Ziel ist eine **aktive, geführte Begleitung** des Administrators durch den Prozess — das System nimmt ihm die mechanische Arbeit und die Verifikation ab, überlässt ihm aber die Entscheidungen an definierten Toren und sorgt dafür, dass **nichts vergessen** wird.

Das Werkzeug wirkt als **Zustandsmaschine/Checkliste** über Phase 0–4 und:

- **verweigert den Fortschritt**, solange ein Pflicht-Artefakt fehlt: fehlendes Backup, fehlende/abweichende SHA512, fehlgeschlagener `integrity_check`, fehlende GPG-Signatur, Katalog/Code-Drift.
- **weist aktiv auf Auffälligkeiten hin** (statt sie stillschweigend zu übergehen — Grundregel 1): Rowcount-Delta außerhalb der erwarteten Toleranz, `foreign_key_check`-Fehler, BLOB-Hash-Abweichung, Instanz auf unerwarteter Version, offene/fehlgeschlagene Vorläufe im Ledger.
- **schlägt den nächsten Schritt vor** und **protokolliert jede Entscheidung** (wer, wann, was) im Ledger.
- **markiert Ausreißer** zur gesonderten menschlichen Prüfung, statt sie in die Sammel-Gegenzeichnung aufzunehmen.

So bleibt die menschliche Verantwortung erhalten (Gates + Gegenzeichnung von Definition und Ledger), während die Wiederholarbeit über die Flotte teilautomatisiert und lückenlos belegt abläuft.

---

## 8. Lossless-Verifikation je Instanz (maschinell)

Für **jede** migrierte Instanz führt das System — zusätzlich zur einmaligen menschlichen Prüfung je `db_kind` (Phase 0/3) — folgende maschinelle Nachweise und schreibt sie ins Ledger:

1. `PRAGMA integrity_check;` → muss `ok` sein.
2. `PRAGMA foreign_key_check;` → keine Verletzungen.
3. **Rowcounts** getragener Tabellen: vorher == nachher, wo die Migration nichts entfernen darf; erwartete Deltas dort, wo sie es tut (aus der Migrations-Definition).
4. **BLOB-Bitidentität**: nicht transformierte BLOBs (Seiten/Assets) bit-für-bit unverändert (Hash-Vergleich).
5. **Referenzielle Kern-Invarianten** der Beweis-DB (z. B. Verknüpfung Annotationen ↔ Belegseiten).
6. **Vorher/Nachher-SHA512** der gesamten Instanz.

Schlägt eine Prüfung fehl: **Stop-and-Flag**, automatische Wiederherstellung aus dem Phase-1-Backup der betroffenen Instanz, Ledger-Status `failed`/`restored`. Kein stilles Weiterlaufen (Grundregel 1).

---

## 9. Dry-Run und Flotten-Planung (NEU)

- Der **Planner** liest `migration_catalog` (Soll) und je Instanz die DB-eigene `schema_migrations` (Ist) und berechnet **pro Instanz** die ausstehende, geordnete Migrationsmenge (topologisch nach `depends_on`/`version`).
- **Dry-Run zuerst:** Ausgabe des vollständigen Plans (betroffene Instanzen, Von→Zu-Version je `db_kind`, `kind`, Backup-Bedarf) **ohne** jede Ausführung.
- **Ausführung nur nach ausdrücklicher Bestätigung** des Administrators.

---

## 10. Teil-Fehlschläge und Wiederaufnahme (NEU)

- **Isolation pro Instanz:** eigenes Backup, eigene Transaktion. Ein Fehlschlag bei `evidence_<A>.db` darf `evidence_<B>.db` nicht berühren.
- **Bei Fehler:** Stop-and-Flag, Wiederherstellung aus dem Phase-1-Backup, Ledger-Eintrag `failed`.
- **Wiederaufnahme:** Der Planner überspringt bereits erfolgreiche Instanzen (per `db_registry`/`schema_migrations`) und nimmt nur die offenen wieder auf. Der Lauf ist damit **idempotent** und **fortsetzbar**.

---

## 11. Abgrenzung und offene Punkte

- **Abgrenzung `version_nr` ↔ `schema_migrations`:** `version_nr` (Inhalt, `evidence_schema_db.sql` Z. 46) und `schema_migrations` (Schema-Historie) sind getrennt zu führen; sie dürfen nicht vermischt werden.
- **GPG/HSM in der Windows-Cloud-VM:** Verfügbarkeit von Smartcards/HSM in der abgeschotteten VM ist zu klären.
- **Performance bei tausenden Instanzen:** Batch-Größen, Parallelität und `VACUUM INTO`-Kosten sind zu dimensionieren.
- **Nächste Bau-Schritte (nach Freigabe dieses Leitfadens):** (1) `migration.db`-Schema + Katalog/Code-Abgleich + Dry-Run-Planner; (2) Generalisierung der Engine (`runner.py`) von `coordinator.db` auf die Beweis-DB-Arten inkl. Backup-+Verify-Harness und Erst-Migration der `schema_migrations`-Registry in die Beweis-DBs.

---

*Ende Datenmigrationsleitfaden v0.2.*

---

## 12. Journalmodus-Umstempelung (NEU, Build 408)

**Anlass (Beleg: Diagnose 2026-07-14, Testsystem auf UNC-Share `\\KK31Storage15\Volume 1\...`, von Windows als `DriveType=4 REMOTE` gemeldet):** Der Webserver startete nicht — `PRAGMA journal_mode=WAL` scheiterte mit `disk I/O error` (erweiterter Code 8714). Ursache ist keine Fehlfunktion des Codes, sondern eine Architekturgrenze von SQLite: Der wal-index liegt in Shared Memory (`-shm`, per `mmap` im DB-Verzeichnis), und Shared Memory ist maschinenlokal. WAL wird auf Netzwerk-Dateisystemen daher ausdrücklich nicht unterstützt (sqlite.org/wal.html).

**Warum das ein Migrationsthema ist:** Der Journalmodus ist eine **persistente Eigenschaft der Datei** (Header-Byte 18/19: `1` = Rollback-Journal, `2` = WAL). Eine WAL-gestempelte Datei ist auf einem Netzlaufwerk **auch lesend nicht zu öffnen**. Bestandsdateien müssen daher einmalig umgestempelt werden — das fasst produktive Dateien an und unterliegt damit diesem Leitfaden.

**Gemessene Ausgangslage auf dem Testsystem:** `forensic_<uid>.db`, `evidence_<uid>.db`, `assets_<uid>.db`, `default.db`, `coordinator.db` waren WAL-gestempelt; `templates.db` und `translations.db` nicht.

**Verfahren (`tools/convert_journal_mode.py`):**

1. **Trockenlauf ist Default.** Geschrieben wird erst mit `--apply`.
2. Umstempelung **in-place** über `PRAGMA locking_mode=EXCLUSIVE` → `PRAGMA journal_mode=DELETE`. In diesem Modus kommt SQLite ohne `-shm` aus (auf dem Share empirisch grün). Die 4,8 GB grosse `default.db` muss **nicht** über das Netz kopiert werden.
3. **Kein Schemaeingriff, kein Inhaltseingriff.** Es ändert sich ausschliesslich der Header-Stempel.
4. **Siegelnachweis:** Für `forensic_<uid>.db` wird der **inhaltsbasierte** SHA-256 vor und nach der Umstempelung mit der Funktion des Servers (`StartupChecker._compute_content_sha256`, kein Nachbau) berechnet und verglichen. Er **muss** identisch bleiben — das Siegel ist bewusst inhalts- und nicht dateibasiert. Bei Abweichung: sofortige Rückstempelung auf WAL, Abbruch, keine weitere Datei wird angefasst.
5. **Vorbedingung wie bei jeder Migration:** Phase-1-Backup (`VACUUM INTO`) vor dem scharfen Lauf. Kein `wal_checkpoint(TRUNCATE)`.
6. Verwaiste `-wal`/`-shm`-Reste werden nach erfolgreicher Umstempelung entfernt und **gemeldet** (Grundregel 1).

**Serverseitige Weiche (`db/journal_policy.py`, `config.yaml` → `db.journal_mode`):** Default `auto` — WAL versuchen, bei Fehlschlag protokollierter Rückfall auf `delete`. Auf lokaler Platte (PROD) greift WAL wie bisher; das Verhalten dort ist unverändert.

**Offen (Architekturfrage, kein Bugfix):** Mehrere Rechner, die gleichzeitig **schreibend** auf **eine** `coordinator.db` auf einem SMB-Share zugreifen, sind auch im Rollback-Journalmodus keine von SQLite unterstützte Konfiguration (Sperren über Netzwerkspeicher). Für den Produktivbetrieb ist zu klären, ob dieser Fall auftritt.

---

## 13. Migration M019 — Schlüsselumstellung `user_id` → `subject_id` in `coordinator.db` (NEU, Build 469)

**Anlass und Entscheidung (mc 2026-07-20):** Der Ermittlungsschlüssel wird global von `user_id` auf `subject_id` (Prepper-Schema: Realnutzer `subject_id == users.id`; Geist `subject_id == prefix + mat_usernames.id`, `prefix = 1.000.000.000` beim Fall) umgestellt, damit die 552.334 Geister-Namen ohne Konto im gesamten Werkzeug schlüsselfähig werden. Belege: `claude_Entscheidung_SubjectID_Schema_Geisternutzer_2026-07-20.md`, `claude_Einstieg_Bauplan_Migration_user_id_zu_subject_id_v0_1.md`, mc-Freigabe Weg A 2026-07-20.

**Betroffen:** ausschließlich `coordinator.db` — 9 Tabellen (`cases` PK, `case_events`, `external_matters`, `investigation_results` mit Trigger/View/Index, `case_release`, `scrape_jobs`, `support_sessions`, `evidence_scan_cache` PK, `forum_promotion` UNIQUE), 6 Indizes, 1 Trigger, 1 View. **Nicht betroffen:** die versiegelten Paket-DBs `evidence_/forensic_/assets_<uid>.db` (für Realnutzer gilt `subject_id == user_id`; Geister-Pakete existieren noch nicht), `default.db`, `templates.db`, sowie `approved_reports.db` (physische Spalte bleibt `user_id`, Repo-API bildet per SQL-Alias auf `subject_id` ab — verlustfrei rückbaubar; eigene Migration bei Bedarf). Der **Migrationsvorbehalt der Beweis-DBs wird nicht ausgelöst**; es gilt die **reduzierte Zeremonie** der coordinator-Zeile (§6.0), wegen Produktivdaten seit 01.07. aber mit verschärfter Verifikation.

**Verfahren (Weg A):** `ALTER TABLE … RENAME COLUMN user_id TO subject_id` je Tabelle, in EINER Transaktion des MigrationRunners (`m019_subject_id_rename.py`, KIND=destructive mit precount/postcount/verify). SQLite ≥ 3.25 mit `legacy_alter_table=OFF` zieht die `REFERENCES`-Klauseln der 4 FK-Kinder sowie Trigger-/View-/Index-Rümpfe automatisch nach (derselbe Mechanismus trug M005 `investigators`→`person`). **Keine Zeile wird kopiert oder gelöscht** — das Datenverlust-Risiko ist konstruktiv null. Zusätzlich: Index-Umbenennung `scrape_jobs_user_idx`→`scrape_jobs_subject_idx`, `case_events_user_time_idx`→`case_events_subject_time_idx` (DROP+CREATE) und Meta-Beleg `subject_key_meta` (id=1, scheme='prepper-subject-id', scheme_version=1, migrated_from='user_id'; der prefix-Wert wird bewusst NICHT dupliziert — Autorität ist `mat_subject_map_meta` des Preppers).

**Workflow (verbindlich, Reihenfolge einhalten):**

1. **Phase 1 — Backup:** Dienste stoppen (kein offener Writer auf `coordinator.db`). `sqlite3 coordinator.db "VACUUM INTO 'backup/coordinator_pre_m019.db'"`; SHA512 + Manifest + GPG gemäß §3 Phase 1.
2. **Weg-A-PoC auf der Kopie (Pflicht-Gate):** `python tools\poc_m019_weg_a.py backup\coordinator_pre_m019_arbeitskopie.db` (Arbeitskopie des Backups, **ohne** `--seed`!). Das Skript prüft ausgabelastig: `legacy_alter_table=0`, RENAME auf PK-Spalte, FK-/Trigger-/View-/Index-Propagation, `foreign_key_check` leer, `integrity_check` ok, Zeilenzahlen/Werte identisch, Append-only-Schutz inkl. Beleg-Kopplung `audit_seq 0→seq`. Erwartung: **„WEG A GANGBAR"**. Konsolenprotokoll zu den Phase-2-Artefakten nehmen. Meldet das Skript vorbestehende FK-Verletzungen: nicht stillschweigend weiter — erst aufklären (Grundregel 1). Fällt der PoC durch: **STOP**, Weg B (Rebuild) gemäß Einstiegs-Bauplan §3 bauen.
3. **Roll-forward:** Code-Stand Build 469 ausrollen (Migration + Code-Sweep sind EIN atomarer Build — Alt-Code kann mit migrierter DB nicht arbeiten und umgekehrt). Dann `python -m management.migrate --coordinator-db <pfad> --deployed-by <name>` → wendet M019 an; der Runner protokolliert in `schema_migrations` + Audit-Kette (MIGRATION_APPLIED), `verify_chain()` läuft mit.
4. **Verifikations-Checkliste (nach dem Lauf):**
   - [ ] `schema_migrations` enthält Version 19; `row_count_before == row_count_after`.
   - [ ] Alle 9 Tabellen: Spalte `subject_id` vorhanden, `user_id` nicht mehr (`PRAGMA table_info`).
   - [ ] `PRAGMA foreign_key_check;` leer · `PRAGMA integrity_check;` = ok.
   - [ ] `subject_key_meta`: (1, 'prepper-subject-id', 1, 'user_id').
   - [ ] Audit-Kette: `verify_chain()` OK (Ausgabe von `management.migrate`).
   - [ ] Stichprobe: bekannte Fall-IDs (z. B. via Cockpit) unter `subject_id` unverändert auffindbar.
   - [ ] Kaltstart-Selbsttest: Management-Server startet, Cockpit-Fallliste lädt, ein Fall öffnet.
5. **Rollback-Pfad:** Bei jedem Fehlschlag rollt der Runner die Transaktion selbst zurück (kein Teilzustand). Für den Katastrophenfall: Dienste stoppen, `coordinator.db` durch das Phase-1-Backup ersetzen (SHA512-Abgleich!), Code-Stand auf Build 468 zurücksetzen — Alt-DB und Alt-Code passen zusammen. Der Vorgang ist im Ledger/Deployment-Protokoll zu dokumentieren.

**Code-Sweep (Bestandteil von Build 469, dieselbe Auslieferung):** Alle SQL-Strings, Python-/JS-Namen, Management-JSON-Keys und CLI-Flags (`--user-id`→`--subject-id`) sind subject_id-nativ (mc-Entscheidung: volle Nativität, keine Alias-Flags). **Ausnahmen (bewusst unverändert):** Schemata/Keys der nicht migrierten DBs (`known_users.user_id` in `default.db`, forensic_meta-Key `'user_id'`, `scraper_log.user_id` in evidence), forum-semantische IDs (`forum_user_id`, `target_user_id`, `actor_user_id`), Dateinamensmuster `evidence_/forensic_/assets_<uid>.db`, sowie **Lese-Fallbacks für historische audit_log-Payloads** (Alt-Einträge tragen den Key `user_id`; die Hash-Kette ist unveränderlich — Leser versuchen `subject_id`, fallen auf `user_id` zurück; neue Payloads schreiben `subject_id`).

**Hinweis Betriebsskripte:** Wer `--user-id` in eigenen Aufrufskripten verwendet (z. B. Prepper-Übergabe, Admin-CLIs), muss auf `--subject-id` umstellen — die alten Flags existieren nicht mehr.


---

## 14. Evidence-Migrationen M002 und M003 — die ersten Strukturänderungen an `evidence_<uid>.db` (NEU, Build 533)

> **Nachtrag, ausdrücklich benannt:** Für **M002** (Build 532, `annotation_tatzeit`) fehlte hier bis Build 533 ein Eintrag, obwohl es die **erste** Strukturänderung an einer Beweismitteldatenbank nach dem 01.07.2026 war. Die Begründung der Migration selbst ist im Modulkopf und in `build.json` vollständig belegt; was fehlte, war die Aufnahme in diesen Leitfaden. Sie wird hier nachgeholt — nicht stillschweigend, sondern als Auslassung kenntlich gemacht (Grundregel 1).

### 14.1 Was betroffen ist

| Migration | Build | DB-Art | Wirkung | KIND |
| --- | --- | --- | --- | --- |
| **M002** | 532 | `evidence_<uid>.db` | Neue Tabelle `annotation_tatzeit` + 4 Indizes | additive |
| **M003** | 533 | `evidence_<uid>.db` | Neue Tabelle `evidence_audit_log` (Hash-Kette) + 2 Append-only-Trigger + Genesis-Zeile | additive |

**Nicht betroffen:** `forensic_<uid>.db`, `assets_<uid>.db`, `coordinator.db`, `default.db`, `templates.db`, `approved_reports.db`.

**Beide Migrationen sind additiv und datenneutral.** Es wird ausschließlich Neues angelegt; keine bestehende Tabelle wird angefasst — kein `UPDATE`, kein `ALTER TABLE`, kein `DELETE`. Das ist **nachgewiesen, nicht behauptet**: TZ04 (M002) und EA03 (M003) bilden vor und nach dem Lauf einen **Inhaltshash** der Bestandstabellen und vergleichen ihn. Ein Vergleich der Datei-Prüfsumme wäre hier untauglich — die Datei ändert sich zwangsläufig, weil eine Tabelle hinzukommt.

**Der Migrationsvorbehalt ist damit gewahrt.** Verlustfreie Migration ist bei rein additiven Änderungen konstruktiv erfüllt: es gibt keinen Bestand, der überführt werden müsste. Die volle Zeremonie der Beweis-DB-Zeile (§6.0) gilt trotzdem — die Fleet erzwingt für Beweis-DB-Arten **immer** ein Backup (`management/migration_fleet/catalog.py:_requires_backup`).

### 14.2 Warum M003 überhaupt nötig war

Bis Build 532 gab es in `evidence_<uid>.db` **keinen Beleg für fachliche Schreibvorgänge**. Das Schema (`db/evidence_db.py:231-459`) führt 16 Tabellen; die beiden mit „Audit" im Kommentar — `report_opened` (:386) und `lock_takeover_requests` (:358) — sind zweckfremd. `save_annotation` (:847-949) schreibt und committet direkt (:947).

Für die **Tatzeit** ist das nicht tragbar: aus ihr wird eine Verjährungsfrist gerechnet, und deren Ablauf ist nicht heilbar. Ein Beleg in `coordinator.db` wäre **dateiübergreifend** und damit nicht atomar — die Best-Effort-Variante (Muster `management_app.py:2316-2337`) loggt einen Fehlschlag lediglich (:2333-2335), und das ist das stille Überspringen eines Belegs, das Grundregel 1 verbietet. **Entscheidung mc 2026-07-26:** eigene Kette in der evidence-Datei.

### 14.3 Reihenfolge (verbindlich)

M002 **vor** M003 — der Runner erzwingt das über `VERSION`. Beide brechen ab, wenn die Tabelle `annotations` fehlt: dann ist die Datei keine evidence-DB, und es bleibt **kein Teilzustand** (TZ08 / EA10).

M003 bricht außerdem ab, wenn `evidence_audit_log` bereits mit **abweichendem Aufbau** existiert (EA11) — sonst wäre ab diesem Lauf ein fremder Aufbau der offiziell geprüfte.

### 14.4 Workflow je Instanz

1. **Phase 1 — Backup.** Von der Fleet erzwungen; zusätzlich SHA512 + Manifest gemäß §3 Phase 1. **Kein offener Writer:** Der forensische Server hält `evidence_<uid>.db` als Hauptverbindung offen (`db/connection_manager.py:203`). Er ist für den Lauf zu stoppen — sonst schlägt `BEGIN IMMEDIATE` fehl und die Migration bricht sauber ab (kein Teilzustand, aber auch kein Fortschritt).
2. **Trockenlauf** über den Planner (`dry_run=True`): ändert nichts, erzeugt kein Backup, lässt die Quelle bit-identisch (I05).
3. **Kleine Charge zuerst** (`--grenze 3`), dann der Gesamtbestand mit Protokoll.
4. **Verifikations-Checkliste je Instanz:**
   - [ ] `schema_migrations` enthält Version 2 **und** 3, beide `kind='additive'`.
   - [ ] `PRAGMA table_info("annotation_tatzeit")` — 16 Spalten in der Reihenfolge aus `M002.ERWARTETE_SPALTEN`.
   - [ ] `PRAGMA table_info("evidence_audit_log")` — 10 Spalten in der Reihenfolge aus `M003.ERWARTETE_SPALTEN`, **ohne** Foreign Key.
   - [ ] Genau **eine** Zeile in `evidence_audit_log`: `seq=1`, `event_type='genesis'`, `target_id='evidence'`. (Der Runner schreibt für den evidence-Strang **kein** `MIGRATION_APPLIED` — er läuft dort ohne `AuditLog`. Der Beleg für die Migration selbst liegt in `schema_migrations` und im Fleet-Ledger.)
   - [ ] `EvidenceAuditLog(con).verify_chain().ok` ist `True`.
   - [ ] Append-only-Trigger greifen: ein `UPDATE`/`DELETE` auf `evidence_audit_log` wird abgewiesen.
   - [ ] `PRAGMA integrity_check;` = ok.
   - [ ] Zeilenzahl in `annotations` **unverändert** gegenüber dem Backup.
5. **Rollback-Pfad:** Bei jedem Fehlschlag rollt der Runner die Transaktion selbst zurück. Für den Katastrophenfall: Dienste stoppen, Datei aus dem Phase-1-Backup ersetzen (SHA512-Abgleich!), Code-Stand zurücksetzen. Zu beachten: **Alt-Code kann mit der migrierten Datei arbeiten** (die neuen Tabellen stören ihn nicht) — der Rückbau der Datei ist also nur nötig, wenn die Migration selbst beanstandet wird, nicht wegen eines Code-Problems.

### 14.5 Was die Prüfsumme angeht

Wie schon bei Build 531 vermerkt: `CREATE INDEX` und `CREATE TABLE` **ändern die Datei-Prüfsumme** (gemessen 2026-07-26: 77.824 → 143.360 B bei 5.000 Zeilen), der **Inhaltshash der Bestandstabellen bleibt unverändert**. Für die Beweiskette zählt der innere Hash. Die neue Datei-Prüfsumme ist nach dem Lauf im Manifest **fortzuschreiben**, nicht mit der alten zu vergleichen.

### 14.6 Ab wann die Kette lückenlos ist

Die Kette beginnt mit der Genesis-Zeile aus M003. **Sie belegt nichts, was vor ihr geschah** — Annotationen, die vor Build 533 erfasst wurden, tragen keinen Kettenbeleg, weil es zu ihrer Zeit keine Kette gab. Das ist keine Lücke, die geschlossen werden kann, und sie darf nicht so aussehen, als wäre sie eine: der Genesis-Zeitstempel ist der Beginn der Belegbarkeit dieser Datei und in der Akte als solcher zu benennen.

---

## 15. Migration M034 — QS-Stichprobe in `coordinator.db` (NEU, Build 540)

### 15.1 Warum dieser Abschnitt überhaupt nötig ist

M034 ist die **erste Migration der Welle 3, die neue Ermittlerdaten anlegt** — Prüfergebnisse, die von Menschen erzeugt werden und in einen Vermerk eingehen können. Für alle bisherigen Migrationen dieser Welle (M032 `tatzeit.edit`, M033 `matrix.view`) galt: reine Rechte-Seeds, keine Daten, kein Vorbehalt. Hier ist das anders, und deshalb steht es hier.

### 15.2 Warum sie trotzdem ohne Migrationsvorbehalt läuft

Drei nachprüfbare Gründe:

1. **Nur `coordinator.db`.** Die unter Vorbehalt stehenden Dateien `evidence_<uid>.db`, `forensic_<uid>.db` und `assets_<uid>.db` werden **nicht angefasst**.
2. **Rein additiv.** Drei neue Tabellen (`qs_sample`, `qs_sample_item`, `qs_review`), drei neue Indizes, zwei neue Fähigkeiten. **Keine** bestehende Tabelle wird geändert, keine Spalte umbenannt, keine Zeile angefasst.
3. **Es gibt nichts zu migrieren.** Vor M034 existierten diese Tabellen nicht; ein Datenverlust ist damit begrifflich ausgeschlossen. Die verlustfreie Migration ist trivial erfüllt.

**Ab dem ersten geschriebenen Prüfergebnis gilt der Vorbehalt allerdings für diese Tabellen mit.** Eine spätere Strukturänderung an `qs_review` — etwa ein zusätzliches Pflichtfeld — ist migrationspflichtig, und zwar mit demselben Aufwand wie bei den `evidence_<uid>.db`. Wer eine solche Änderung plant, beginnt bei Abschnitt 3.

### 15.3 Reihenfolge (verbindlich)

M034 setzt `person`, `cases`, `audit_log` und `rbac_capability` voraus und **scheitert laut**, wenn eine davon fehlt. Sie läuft nach M033 und vor allem, was danach kommt. Die Migrationskette der `coordinator.db` lautet nach diesem Build durchgehend 1–34.

### 15.4 Workflow

```
# 1. Sicherung (wie immer VOR jedem Lauf)
copy coordinator.db coordinator.db.vor_m034

# 2. Trockenlauf
python -m management.migrations.migrate_admin plan --db coordinator.db

# 3. Anwenden
python -m management.migrations.migrate_admin up --db coordinator.db --actor <SYSUSER>

# 4. Nachweis
python -m management.migrations.migrate_admin status --db coordinator.db
python -m management.audit.audit_admin verify --db coordinator.db
```

Erwartet nach Schritt 4: `schema_migrations` enthält Version 34, die Audit-Kette ist intakt, und `rbac_capability` zählt **43** Einträge.

### 15.5 Die Selbstprüfung der Migration

M034 prüft nach dem Anlegen **in einem SAVEPOINT, der immer zurückgerollt wird**, ob die CHECK-Bedingungen auch greifen: eine leere Begründung, ein unbekanntes Ergebnis, ein unbekanntes Verfahren und eine Stichprobe größer als die Grundgesamtheit müssen alle abgewiesen werden. Ein geschriebener, aber unwirksamer CHECK wäre schlimmer als keiner — er erzeugt Vertrauen, das er nicht trägt. Muster: M002 (Build 532).

Fehlen Person, Fall oder Audit-Eintrag (frische, leere Datenbank), wird die Probe **übersprungen und das protokolliert**. Eine Probe gegen leere Fremdschlüssel würde etwas anderes messen als gemeint.

### 15.6 Die Prüfsumme

`CREATE TABLE` und `CREATE INDEX` ändern die **Datei**-Prüfsumme der `coordinator.db`; der Inhalt der Bestandstabellen bleibt unberührt. Die neue Prüfsumme ist nach dem Lauf im Manifest **fortzuschreiben**, nicht mit der alten zu vergleichen (wie in §14.5 für die `evidence_<uid>.db`).

### 15.7 Die Rechte müssen danach vergeben werden

M034 seedet die Fähigkeiten `qs.view` und `qs.edit`, **nicht** die Zuweisung an eine Rolle (default-deny). Ohne Grant sieht niemand die Stichprobe:

```
python -m management.rbac.rbac_admin grant --role supervisor --capability qs.view  --actor <SYSUSER>
python -m management.rbac.rbac_admin grant --role supervisor --capability qs.edit  --actor <SYSUSER>
python -m management.rbac.rbac_admin grant --role lector     --capability qs.view  --actor <SYSUSER>
python -m management.rbac.rbac_admin grant --role lector     --capability qs.edit  --actor <SYSUSER>
```

Die Vergabe an `lector` ist eine Festlegung von mc (Entscheidung C-1, 2026-07-26) und kein Vorschlag: prüfte die Supervisorin allein, wäre sie genau dann das Nadelöhr, wenn die Fallzahl steigt.

---

## 16. Coordinator-Migration M040 — Inhaltsfreigabe der Volltextsuche (NEU, Build 561)

> **Kurzfassung:** Rein additiv, **nur `coordinator.db`**, zwei neue Tabellen und
> ein neuer RBAC-Seed. **Keine** Beweismitteldatenbank ist berührt, der
> Migrationsvorbehalt seit dem 01.07.2026 greift nicht. Es gibt aber einen
> **Sperrvermerk zur Reihenfolge** — s. §16.1. Der ist der eigentliche Grund,
> warum dieser Abschnitt existiert.

### 16.1 SPERRVERMERK — Reihenfolge vor Inhalt

**M040 darf erst eingespielt werden, wenn Instanz A ihre Migrationen
m035–m039 eingespielt hat** (oder mc festgestellt hat, dass es keine gibt).

**Grund** (reproduziert am 2026-07-26 mit `tools/diag_migrationsluecke.py`;
ausführlich in `management/Vermerk_Migrationsluecke_Parallelbetrieb_v0_1.md`):
`MigrationRunner` führt einen **Höchststand** und keine Menge —

```python
current = MAX(version) FROM schema_migrations
if mod.VERSION <= current:            # runner.py:119
    self._check_checksum(mod); continue
```

Läuft M040 vor m035–m039, werden diese Migrationen **für immer
übersprungen**: `run()` meldet dann „Keine ausstehenden Migrationen" für einen
Zustand, in dem sieben Schemaänderungen fehlen. `_check_checksum` schweigt
dabei, weil es zu einer nie angewandten Version gar keine Registry-Zeile gibt
(`runner.py:207-209`).

mc hat am 2026-07-26 entschieden, die Migrationen der Instanzen **strikt zu
serialisieren**, statt den Runner zu ändern. Diese Entscheidung verhindert, dass
die Falle **ausgelöst** wird; sie entschärft sie nicht.

**Vor jedem Einspielen — verbindlich:**

```
python tools/pruefe_migrationskette.py --db data/coordinator.db
```

Exit `0` = unbedenklich · `2` = **Lücke unterhalb des Höchststands** (diese
Migrationen laufen nie mehr) · `3` = die Datenbank kennt eine Version, die es im
Code nicht gibt. Das Werkzeug ist rein lesend (`mode=ro`) und auch auf einer
Produktivdatenbank unbedenklich.

**Die Nummer 40 ist vorläufig.** Solange diese Migration in keiner Datenbank
gelaufen ist, kostet ihre Umbenennung nichts. Danach ist sie unantastbar.

### 16.2 Was M040 anlegt

| Objekt | Art | Inhalt |
| ------ | --- | ------ |
| `fulltext_zweck` | Katalogtabelle | die vier Zweckcodes (`kreuzbezug_nickname`, `alias_pruefung`, `wiedervorlage`, `sonstiges`) |
| `fulltext_release` | Fachtabelle | wer darf den Trefferinhalt welches **fremden** Falls sehen, zu welchem Zweck, erteilt von wem, wann, Widerruf |
| `ux_fulltext_release_aktiv` | partieller UNIQUE-Index | höchstens **eine** gültige Freigabe je (Fall, Person) |
| `ix_fulltext_release_person` / `_fall` | Index | die beiden Abfragerichtungen |
| `fulltext.release` | RBAC-Seed | Recht, eine Inhaltsfreigabe zu erteilen/widerrufen |

Der Zweckkatalog ist eine **eingefrorene Kopie** von
`management/search/zweck_vokabular.py` (m005-Prinzip: eine angewandte Migration
darf ihr Laufzeitverhalten nie ändern). Die Brücke zwischen beiden ist der Test
**FR02**, der sie zur Bauzeit gegeneinander hält.

### 16.3 Migrationsklasse und Vorbehalt

Rein **additiv**, ausschließlich `coordinator.db`, ausschließlich **neue**
Tabellen. Keine bestehende Zeile wird angefasst, keine Spalte umgebaut. Die
Ermittler-Ergebnisdatenbanken (`evidence_`/`forensic_`/`assets_<uid>.db`) sind
**nicht berührt** — es kann kein bestehendes Wissen verloren gehen.

Der Vollständigkeit halber, weil es zum selben Arbeitspaket gehört: die
Volltextsuche **liest** alle `evidence_<uid>.db` ausschließlich mit `mode=ro`
und legt ihren FTS5-Index in einer eigenen, jederzeit verwerfbaren
`search_index.db` ab (Build 560). Auch von dieser Seite ist der
Migrationsvorbehalt nicht berührt; Test SI22 belegt das über SHA-512
vorher/nachher.

### 16.4 Verifikations-Checkliste

- [ ] `tools/pruefe_migrationskette.py` liefert Exit **0** (§16.1).
- [ ] `schema_migrations` enthält die Version von M040, `kind='additive'`.
- [ ] `SELECT COUNT(*) FROM fulltext_zweck` = **4**; die Codes stimmen mit
      `management/search/zweck_vokabular.py` überein.
- [ ] Die drei Indizes aus §16.2 existieren.
- [ ] `SELECT 1 FROM rbac_capability WHERE code='fulltext.release'` liefert eine
      Zeile; die Gesamtzahl der Fähigkeiten ist **44**.
- [ ] `PRAGMA integrity_check;` = ok.
- [ ] Zeilenzahlen aller **bestehenden** Tabellen unverändert gegenüber dem
      Backup (M040 fasst keine an).

### 16.5 Grants (nach dem Einspielen, default-deny)

```
python -m management.rbac.rbac_admin grant --role supervisor \
       --capability fulltext.release --actor <SYSUSER>
python -m management.rbac.rbac_admin grant --role supervisor \
       --capability evidence.fulltext_search --actor <SYSUSER>
```

`evidence.fulltext_search` liegt seit M006 im Katalog und ist **nicht** neu. Die
Rolle `searchagent` bleibt vorerst **ohne Grant** — Ausweitung erst nach einer
Lastmessung (Entscheidungen mc §1 E-2).

### 16.6 Rollback

Bei jedem Fehlschlag rollt der Runner die Transaktion selbst zurück; es bleibt
kein Teilzustand. Für den Katastrophenfall gilt der Weg aus §3 Phase 1
(Backup einspielen, SHA512-Abgleich). Zu beachten: **Alt-Code kann mit der
migrierten Datei arbeiten** — die beiden neuen Tabellen stören ihn nicht. Ein
Rückbau der Datei ist also nur nötig, wenn die Migration selbst beanstandet
wird, nicht wegen eines Code-Problems.

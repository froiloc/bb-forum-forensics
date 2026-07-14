# Leitfaden zur Datenmigration im Produktivbetrieb

## IT-Forensisches Ermittlungswerkzeug Advanced Investigation Wrapper (AIW) · NRW

**Version:** 0.2
**Build-Bezug:** 315 (Code-Baseline; dieser Leitfaden ist Design-Grundlage für die Folge-Builds migration.db + Engine-Generalisierung)
**Datum:** 2026-07-03
**Status:** Verbindlicher Workflow für Datenmigration im Produktivbetrieb
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH

---

## Änderungshistorie

| Version | Build | Datum      | Änderung                                                                                                                                                              |
| ------- | ----- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0.1     | 303   | 2026-06-25 | Erstfassung — Migrationsleitfaden (Vier-Phasen-Workflow, Gerichtsfestigkeit, Einzel-DB)                                                                             |
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


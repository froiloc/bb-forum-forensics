# Bauplan A4 — Governance: `pending_cross_annotations` in die Migrationskette

**Version:** 0.1 · **Datum:** 2026-07-24 · **Modul:** `aiw_webserver`
**Basis:** nach Build 505 · **Buildnummer:** 506
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Auftrag:** mc 2026-07-24 · Governance-Punkt aus Bauplan Build 474 §3 / 478 §5

---

## 1. Warum dieser Build **vor** A2 kommt (Reihenfolge-Abweichung, begründet)

Du hast „A1 bis A4" beauftragt. Ich ziehe **A4 vor A2** vor, weil der
Querfund-Rückkanal (A2) fachlich **auf** `pending_cross_annotations` aufsetzt: er
verknüpft seinen Zustand mit genau diesen Zeilen. Baute ich erst den Rückkanal
und richtete danach das Substrat her, müsste ich den Rückkanal ein zweites Mal
anfassen — mit einer zweiten Migration auf produktiven Daten. Die Reihenfolge
**A1 → A4 → A2 → A3** vermeidet das. Widersprich bitte, falls du das anders
willst; ich baue sonst in dieser Folge weiter.

---

## 2. Belegter Ist-Stand

| Befund | Beleg |
|---|---|
| Die Tabelle wird **zur Laufzeit** von `db/coordinator_db.py` angelegt (`executescript("CREATE TABLE IF NOT EXISTS …")` in `add_pending_cross_annotation`), **nicht** von einer Migration | `db/coordinator_db.py` Z. 408–421 |
| Grund der Notlösung: „coordinator.db verfügbar, aber `pending_cross_annotations`-Eintrag fehlte lautlos" (Build 185, Bug 2.78) | Kommentar ebenda Z. 403–407 |
| Der Schlüssel heißt `target_uid`, nicht `subject_id` | DDL ebenda; `CrossfindingsRepo` normalisiert erst beim Lesen (`crossfindings_repo.py:_as_dict`) |
| Als „eigener späterer Governance-Punkt" vermerkt | Bauplan Build 474 §3, Bauplan Build 478 §5 |

**Das Problem:** eine Tabelle außerhalb der Kette hat keine geprüfte DDL, keinen
Prüfsummen-Eintrag in `schema_migrations` und taucht in keiner Migrationsübersicht
auf. Für ein forensisches Werkzeug ist das ein Beleg-Loch: der Zustand der
Datenbank ist nicht vollständig aus der Kette rekonstruierbar.

---

## 3. Migration M023 `m023_pca_into_chain.py`

### 3.1 Was die Migration tut

1. **Kanonische DDL in die Kette holen** — `CREATE TABLE IF NOT EXISTS
   pending_cross_annotations (…)` **zeichengenau** wie die Laufzeit-DDL, plus den
   dort ebenfalls angelegten partiellen Index `pca_target_uid_idx`. Existiert die
   Tabelle bereits (Regelfall im Produktivbetrieb), ist das ein No-op — die
   **bestehenden Zeilen werden nicht angefasst**.
2. **`subject_id` angleichen** — additiv als **generierte Spalte**:
   ```sql
   ALTER TABLE pending_cross_annotations
     ADD COLUMN subject_id INTEGER GENERATED ALWAYS AS (target_uid) VIRTUAL;
   CREATE INDEX IF NOT EXISTS ix_pca_subject_id
     ON pending_cross_annotations (subject_id);
   ```
3. **Inline-Verifikation** → bei Verstoß `raise` → ROLLBACK im Runner:
   Tabelle da, Index da, Spalte in `PRAGMA table_xinfo` vorhanden **und**
   `SELECT COUNT(*) WHERE subject_id IS NOT target_uid` = 0, plus die
   **Zeilenzahl-Invariante** (vorher == nachher; Muster M020).

### 3.2 Warum eine GENERIERTE Spalte — Entwurfsentscheidung zur Abnahme

Es gab drei Wege. Ich habe den dritten gewählt:

| Weg | Bewertung |
|---|---|
| (a) `target_uid` **umbenennen** in `subject_id` | Bricht den **laufenden** Schreibpfad in `db/coordinator_db.py` und den `cross_annotation_integrator` — also die produktive Querfund-Pipeline. Höchstes Risiko, kein Zusatznutzen. **Verworfen.** |
| (b) Echte Spalte `subject_id` + Backfill + Schreibpfad ergänzen | Funktioniert, aber jede Zeile, die ein alter Binärstand schreibt, hätte `subject_id IS NULL` → stille Divergenz zwischen zwei Spalten, die dasselbe bedeuten sollen. Genau die Art Loch, die Grundregel 1 verbietet. **Verworfen.** |
| **(c) VIRTUAL GENERATED `subject_id AS (target_uid)`** | **Kann nicht divergieren** (SQLite berechnet den Wert bei jedem Lesen), braucht **keinen** Backfill, **keine** Änderung am produktiven Schreibpfad, ist indizierbar und rein additiv. Der physisch geschriebene Name bleibt `target_uid`, der kanonische Lesename ist `subject_id`. **Gewählt.** |

*Verifiziert:* SQLite 3.45.1 (Container) — `ALTER TABLE … ADD COLUMN … GENERATED
ALWAYS AS (…) VIRTUAL` inkl. Index und `SELECT *`-Sichtbarkeit erfolgreich
geprobt. Generierte Spalten gibt es ab SQLite 3.31 (2020); der Startcheck bekommt
eine ausdrückliche Mindestversions-Prüfung, damit ein zu altes SQLite **laut**
scheitert statt still.

**Nicht abschließend:** ein späterer Build kann `target_uid` konsolidieren, wenn
die Pipeline ohnehin angefasst wird. Der Beleg-Charakter ist mit (c) aber schon
jetzt hergestellt — das war das Ziel dieses Punktes.

### 3.3 `db/coordinator_db.py` — Kommentar-Änderung, keine Logik

Die Laufzeit-`CREATE TABLE IF NOT EXISTS` **bleibt** (sie ist die Absicherung
gegen den ursprünglichen Bug 2.78 und schadet nach der Migration nicht). Sie
bekommt einen Verweis auf M023 als nunmehr **kanonische** Quelle der DDL, damit
niemand die beiden Stellen auseinanderlaufen lässt. **Keine** funktionale
Änderung an der produktiven Pipeline.

### 3.4 `CrossfindingsRepo` liest `subject_id` nativ

`SELECT pca.subject_id` statt `pca.target_uid` mit anschließender Umbenennung.
Die **Ausgabeform bleibt identisch** (`subject_id`), damit Build 478 (Frontend)
und die bestehenden Tests unverändert gültig bleiben. Zusätzlich ein
Verträglichkeits-Zweig: fehlt die generierte Spalte (DB vor M023 — etwa in einer
Alt-Testfixture), fällt das Repo **belegt** auf `target_uid` zurück und
protokolliert das, statt zu scheitern.

---

## 4. Tests Build 506

`tests/test_m023_pca_chain.py` (**M2301–M2306**):

- M2301 — frische DB: Migration legt Tabelle + beide Indizes an.
- M2302 — **Bestandsfall**: Tabelle mit Zeilen existiert (Laufzeit-DDL);
  Migration ist verlustfrei — **Zeilenzahl und Inhalte identisch**, `subject_id`
  == `target_uid` für **jede** Zeile.
- M2303 — Idempotenz: zweiter Lauf ist No-op, keine Fehler.
- M2304 — nach der Migration geschriebene Zeilen (über den **echten**
  `CoordinatorDb.add_pending_cross_annotation`) tragen automatisch die korrekte
  `subject_id` — der Beweis, dass Divergenz ausgeschlossen ist.
- M2305 — `schema_migrations` enthält Version 23 mit `kind='additive'`.
- M2306 — `CrossfindingsRepo` liefert vor **und** nach der Migration die
  identische Ausgabeform (Verträglichkeits-Zweig).

**Anker:** `tests/test_management_dashboard.py` D01 Migrationsliste `…22` → `…23`.

---

## 5. Migrationsklasse und Produktivbetrieb

**Additiv**, nur `coordinator.db`. Es wird **keine** Zeile geschrieben, geändert
oder gelöscht; die neue Spalte ist virtuell und belegt keinen Speicher. Die
Ermittler-Datenbanken sind nicht berührt. Rückbau: `DROP INDEX` + `ALTER TABLE
DROP COLUMN` — beides verlustfrei, weil die Spalte keinen eigenen Inhalt trägt.

---
*Dokument-Ende · Bauplan A4 · v0.1 · 2026-07-24*

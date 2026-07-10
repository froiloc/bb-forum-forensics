# Bauplan Build 342 — Refactor `investigators` → `person`

**Baustelle 7 · Welle 0 · erster Build**
Autoritativ: `Bauplan_Baustelle7_Management_v1_1.md` §11.1/§11.7,
`UEBERGABE_BAUSTELLE_7_Welle0_ff.md` §3.
Freigabe: `mc` 2026-07-10.
Version des Dokuments: v0.1.

---

## 1. Ziel und Grenzschnitt

Rein **mechanische, verlustfreie** Umbenennung der coordinator.db-Entität
`investigators` nach `person`. Grund (Beleg: Bauplan B7 v1.1 §11.1): die Rollen
laufen auseinander (admin / lector / searchagent); `investigators` ist als
Tabellenname semantisch zu eng. Der Aufbau von RBAC (`person_role`, `rbac_*`)
ist **NICHT** Teil dieses Builds und folgt in separaten Builds.

Dieser Build ist **additiv** im Sinne des Migrations-Frameworks: keine Zeile,
keine Spalte, kein Wert geht verloren; lediglich ein Tabellenname und die daran
hängenden Bezeichner ändern sich.

### Bewusst UNBERÜHRT (Grenzschnitt, drei geklärte Scope-Entscheidungen)

1. **Forensischer Schreibpfad.** `RequestContext`/`ModeContext.investigator_id`
   (liefert nur eine Integer-ID an den FK), `forensic_api/*`
   (annotate/viewport/status/events/blob_handler) sowie die evidence_db-Spalte
   `annotations.investigator_id` bleiben unverändert. evidence_db unterliegt ab
   Go-Live dem Migrationsvorbehalt; hier wird sie nicht angefasst.
2. **Audit-Vokabular.** `EventType.INVESTIGATOR_CREATED/UPDATED` (Werte **und**
   Namen) und `target_type="investigator"` bleiben — die append-only Hash-Kette
   trägt historische Semantik, die nicht rückwirkend umgeschrieben werden darf.
   Mitgezogen wird nur der **CLI-Aufrufpfad** (`python -m management.person.
   person_admin`).
3. **Rolle-Konzept-Bezeichner.** `get_investigator`, `InvestigatorRecord`,
   `_get_investigator_once` (in `db/coordinator_db.py`, konsumiert vom
   forensischen Identitätspfad `forensic_api/investigator_me.py`,
   `editor_comment.py`) sowie die Boolean-Flags `is_investigator` /
   `is_supervisor` / `is_support` bleiben. Sie bezeichnen die **Rolle**, nicht
   die **Tabelle**.

Leitprinzip: **Der Tabellenname (Entitäts-Speicher) wird umbenannt; die
Rolle-/Identitäts-Bezeichner bleiben.** Technisch sauber trennbar, weil alle
Tabellenreferenzen die Pluralform `investigators` verwenden, alle
Rolle-Bezeichner hingegen Singular (`investigator_id`, `is_investigator`,
`get_investigator`) bzw. eine abweichende Schreibweise (`InvestigatorRecord`).

---

## 2. Kern: Migration M005

Neu: `management/migrations/coordinator/m005_person_rename.py`
(`VERSION = 5`, `KIND = "additive"`).

### 2.1 FK-Nachzug (der eigentliche Mechanismus)

In SQLite mit `legacy_alter_table = OFF` zieht `ALTER TABLE … RENAME TO …` alle
Fremdschlüssel-Referenzen in allen anderen Tabellen automatisch nach — sowohl
benannte Klauseln (`FOREIGN KEY(...) REFERENCES person(id)`) als auch
Inline-Spalten-FKs. Betroffene Referenzen auf `investigators(id)`:

| Tabelle | Spalte | Herkunft |
|---|---|---|
| `audit_log` | `actor_id` | `audit_log.py` (M001) |
| `cases` | `assigned_to` | M002 |
| `support_sessions` | `supporter_id` | M003 |
| `case_events` | `created_by` | M004 |
| `scrape_jobs` | `assigned_to` | Bootstrap (falls vorhanden) |
| `pending_cross_annotations` | `source_iid` | Bootstrap (falls vorhanden) |

`up()` setzt `PRAGMA legacy_alter_table=OFF` **explizit** vor dem Rename. Damit
gilt der Nachzug deterministisch, unabhängig vom Build-Default der jeweiligen
SQLite-Version (Prod: Python 3.14). Der Default ist seit SQLite 3.25.0 ohnehin
`OFF`; das explizite Setzen härtet gegen abweichende Builds ab.

**Die bereits angewandten Migrationen M002–M004 werden NICHT editiert.** Ein
nachträgliches Ändern angewandter Migrationen würde Checksum-Drift erzeugen und
Historie umschreiben (forensisch unzulässig). Ihr `REFERENCES investigators(id)`
wird ausschließlich durch den Live-Nachzug von M005 zu `person` — exakt wie im
Empirie-Test reproduziert.

### 2.2 Idempotenz / Frisch-Schema-Guard

- `investigators` fehlt, `person` existiert → **No-Op mit INFO-Log** (Rename
  bereits erfolgt oder Frisch-Schema). Kein Hard-Fail, aber auch kein stiller
  Durchgang (Grundregel 1).
- `investigators` **und** `person` fehlen → No-Op mit INFO-Log (kein Bootstrap
  gelaufen; dieser Pfad — coordinator.db rein aus m001–m005 ohne Bootstrap — war
  schon vor Build 342 unvollständig, da keine Migration je `investigators`
  erzeugt hat; siehe offener Punkt).
- `investigators` **und** `person` existieren gleichzeitig → `RuntimeError`
  (mehrdeutiger Zustand, manuelle Klärung).

### 2.3 Inline-Verifikation (statt Runner-Verify, da KIND=additive)

`up()` prüft nach dem Rename inline und wirft bei Verstoß (→ ROLLBACK im Runner,
kein Teilzustand):
- `person` existiert, `investigators` weg,
- Zeilenzahl-Invariante (`investigators` vorher == `person` nachher),
- `PRAGMA foreign_key_check(<t>)` == 0 für jede existierende abhängige Tabelle
  (`_FK_DEPENDENTS`, inkl. `audit_log`).

---

## 3. Umbenannte Artefakte

**Modul** (git mv, History-erhaltend): `management/investigators/` →
`management/person/`
- `investigators_repo.py` → `person_repo.py`:
  `InvestigatorsRepo` → `PersonRepo`, `InvestigatorsError` → `PersonError`,
  `list_investigators()` → `list_persons()`.
- `investigators_admin.py` → `person_admin.py`:
  CLI `python -m management.person.person_admin`, Log-Präfix `[person_admin]`.
- `__init__.py`: Modul-Kommentar aktualisiert.

**SQL-Tabellenreferenz `investigators` → `person`** (Rolle-Bezeichner bleiben):
`db/coordinator_db.py` (`cdb.investigators` → `cdb.person`),
`core/mode_resolver.py` (10 Plural-Tabellenrefs; 20× `investigator_id` +
4× `investigator_username` unberührt), `core/user_resolver.py` (Kommentar),
`management/dashboard/dashboard_repo.py` (+ `REQUIRED_TABLES`),
`management/workload/workload_repo.py` (+ `REQUIRED_TABLES`),
`management/support_overview/support_overview_repo.py` (+ `REQUIRED_TABLES`),
`management/cases/cases_repo.py` (JOIN + Parameter `investigator_id` →
`person_id` in `assign()`; alle Aufrufer positional, kein Update nötig) +
`cases_admin.py`, `management/case_events/case_events_repo.py` +
`case_events_admin.py`, `management/support_sessions/support_sessions_repo.py`,
`management/audit/audit_log.py` (FK-Ziel `actor_id` → `person`; eingefrorener
Spaltensatz unverändert).

**Tests (17)**: 16 per Plural-Ersetzung der Tabellen-DDL/SQL;
`tests/test_management_investigators.py` → `tests/test_management_person.py`
(git mv, Klassen-Rename); `test_management_dashboard.py` D01-Assertion um M005
erweitert (`[1,2,3,4]` → `[1,2,3,4,5]`, `assertIn(5)`).

**`setup_coordinator_dev.py`**: funktional unverändert — legt bewusst weiter
`investigators` an, damit M002–M004 ihren FK-Anker finden und M005 real
umbenennt. Nur Deprecation-/Kontext-Kommentare ergänzt.

---

## 4. Teststrategie und Ergebnis

- **E2E-Migrationstest** gegen eine realistisch gebootstrappte coordinator.db
  (investigators + scrape_jobs + pending_cross_annotations → migrate m001–m005):
  5 angewandt, `person` da, `investigators` weg, Zeilen erhalten, alle
  `REFERENCES`-Klauseln (inkl. `audit_log`) zeigen auf `person`,
  `foreign_key_check` global 0, idempotent (2. Lauf leer), Audit-Kette intakt.
- **Vollregression** `python run_tests.py`:
  Python **814 passed / 59 skipped / 3 subtests** (unverändert ggü. Baseline),
  JavaScript **467 passed / 1 skipped / 1 todo** (unverändert; kein JS geändert).

---

## 5. Deploy

- `migrate.py`-Lauf auf der VM **zwingend** (Schemaänderung coordinator.db).
- coordinator.db hat keinen Migrationslock (kein Beweismittel); Änderungen daran
  können kein Ermittlerwissen zerstören. Dennoch: Backup vor dem Lauf.
- Der Code-Teil (Leser/CLI) ist erst nach dem Rename konsistent; Migration und
  Code gehören in denselben Deploy-Schritt.

---

## 6. Offene Punkte (nachgelagert, NICHT in diesem Build)

1. **Wer erzeugt `person` nach Wegfall von `setup_coordinator_dev.py`?**
   Das Skript wird demnächst als deprecated markiert. Ein Bootstrap-/RBAC-Build
   muss das Anlegen der `person`-Tabelle (bzw. das erste Seed) sauber
   übernehmen.
2. **Build-Nummern-Kollision.** Die `build.json`-Notiz von Build 341 kündigte
   einen abweichenden Build 342 (`report_editor.js`, Baustelle 6) an. Dieser
   wurde nicht gebaut; der Nachzug ist neu zu nummerieren.
3. **RBAC.** `person_role`, `rbac_*`, Rollenableitung — separate Welle.

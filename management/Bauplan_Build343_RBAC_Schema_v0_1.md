# Detail-Bauplan Build 343 — RBAC Schnitt (a): Schema + Seed

**Version:** 0.1 · **Datum:** 2026-07-10 · **Build:** 343 · **Version:** 0.7.343
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11.1/§11.3/§11.7 (Welle 0).
**mc:** 2026-07-10 (drei Entscheidungen bestätigt, s. §3).

---

## 1. Ziel und Abgrenzung

Erster von drei RBAC-Schnitten der Welle 0 (nach dem `person`-Rename, Build 342).
Legt die RBAC-Matrix als additive coordinator.db-Migration an und seedet den
**Katalog** (Rollen + Fähigkeiten). Rein additiv, kein Datenverlust-Risiko
(`coordinator.db`, kein Beweismittel).

**In diesem Build NICHT enthalten** (spätere Schnitte):
- **(b)** Schreibpfad + `policy_admin`-CLI (Grant-/Rollenvergabe über den
  auditierten `CoordinatorWriter`, Katalog-Validierung).
- **(c)** Lese-/Durchsetzungsschicht (Resolver: Rollen→Grants→Scope; Start-Check
  „jede Code-Capability existiert in der DB").

---

## 2. Lieferumfang

| Datei | Art | Inhalt |
|---|---|---|
| `management/migrations/coordinator/m006_rbac_schema.py` | NEU | Migration M006 (VERSION=6, KIND=additive): DDL + Katalog-Seed |
| `management/rbac/__init__.py` | NEU | Paket-Kopf, Drei-Schnitte-Doku |
| `management/rbac/catalog.py` | NEU | Wahrheitsquelle im Code (ROLES, CAPABILITIES) |
| `tests/test_management_rbac_schema.py` | NEU | R01–R07 |
| `tests/test_management_dashboard.py` | GEÄNDERT | D01-Assertion `applied` → `[1..6]` |
| `build.json` | GEÄNDERT | Build 343 (ASCII-only) |
| `management/Bauplan_Build343_RBAC_Schema_v0_1.md` | NEU | dieses Dokument (git-ignored, `git add -f`) |

---

## 3. Entscheidungen (mc 2026-07-10)

1. **`rbac_grant` UND `person_role` starten LEER.** `audit_seq` ist `NOT NULL`
   und muss — wie `case_events` — **pro Zeile** an einen echten `audit_log`-
   Eintrag koppeln. Migrations-geseedete Grants hätten kein sauberes `audit_seq`.
   Die Basis-Grants (lector→`reports.review`, admin→`feedback.moderate`,
   searchagent→`evidence.fulltext_search` u. a., §11.3) und die Rollenzuweisungen
   kommen in **Schnitt (b)** über die auditierte `policy_admin`-CLI. `default-deny`
   + leer = niemand darf etwas → forensisch sauberer Ausgangszustand.
2. **Eingefrorener Seed (m005-Prinzip).** `m006` importiert `catalog.py`
   **nicht**; eine bereits angewandte Migration darf ihr Laufzeitverhalten nie
   ändern (sonst Nichtdeterminismus trotz gleicher Checksumme). Der Seed ist eine
   eingefrorene Kopie; **Test R02** verankert „`m006`-Seed == `catalog.py`" zur
   Bauzeit. Die Laufzeit-Invariante „jede Code-Capability existiert in der DB"
   (§11.3) setzt **Schnitt (c)** beim Start durch.
3. **Voller Fähigkeitskatalog geseedet** (15 aus §11.3), nicht minimal. Ohne Grant
   wirkungslos (`default-deny`), daher harmlos.

---

## 4. Schema (M006)

```
rbac_role(code PK, label, created_at)
rbac_capability(code PK, label, description, created_at)
rbac_grant(id PK,
  role_code -> rbac_role, capability_code -> rbac_capability,
  scope CHECK('alle'|'eigene'|NULL),
  audit_seq NOT NULL -> audit_log(seq),
  granted_by -> person, granted_at,
  revoked_at, revoked_by -> person, revoke_audit_seq -> audit_log(seq), note)
person_role(id PK,
  person_id -> person, role_code -> rbac_role,
  assigned_by, assigned_at, revoked_at, revoked_by,
  audit_seq NOT NULL -> audit_log(seq), revoke_audit_seq -> audit_log(seq))
ix_rbac_grant_active(role_code, capability_code) WHERE revoked_at IS NULL
ix_person_role_active(person_id)                 WHERE revoked_at IS NULL
```

**Zwei additive Verfeinerungen über die §11.3-Skizze hinaus** (transparent
angemerkt, analog `case_created`-Spiegel §8.4):
- **`person_role.revoke_audit_seq`** ergänzt (symmetrisch zu `rbac_grant`): ein
  Soft-Revoke einer Rollenzuweisung ist forensisch relevant und braucht seinen
  eigenen Beleg (Grundregel 1). Ohne diese Spalte müsste Schnitt (b)
  `coordinator.db` erneut altern.
- **`ix_person_role_active`**: der Resolver liest aktive Rollen je `person_id`;
  der Partial-Index stützt genau diesen Lesepfad.

### Katalog (Code-Wahrheitsquelle `catalog.py`, gespiegelt im M006-Seed)

**Rollen (6):** supervisor, investigator, support, admin, lector, searchagent.
**Fähigkeiten (15):** dashboard.view, assignment.edit, mentoring.view,
reports.review, reports.approve, stats.export_sta, workload.view,
support_history.view, mycases.view, myhistory.view, policy.view,
evidence.fulltext_search, feedback.moderate, capacity.edit, ops.view.

Codes sind stabile Bezeichner (wie `event_type`): **ergänzen, nie umbenennen**.

---

## 5. Idempotenz & Verifikation

- `CREATE TABLE/INDEX IF NOT EXISTS` + `INSERT OR IGNORE` → `up()` reentrant;
  zweiter Runner-Lauf wird ohnehin per `schema_migrations` übersprungen.
- Inline-Verify (`raise` → ROLLBACK im Runner): alle vier Tabellen + beide
  Indizes vorhanden; jede Seed-Zeile vorhanden (kein stiller Teil-Seed, GR1);
  `rbac_grant` leer (Grant-Abgrenzung belegt).
- Auditierung automatisch über den Runner: `MIGRATION_APPLIED` (`actor_id=None` =
  System), sofern ein `AuditLog` übergeben ist.

---

## 6. Tests (R01–R07, `tests/test_management_rbac_schema.py`)

- **R01** M006 via `discover`+Runner (M001..M006) angewandt; Tabellen + Indizes
  da; 2. Lauf No-Op.
- **R02** Seed == `catalog.py` (Codes **und** Label/Description; 6 Rollen, 15
  Fähigkeiten) — Brücke frozen-Migration ↔ Code-Katalog.
- **R03** `rbac_grant` + `person_role` angelegt und leer.
- **R04** `foreign_key_check` aller vier Tabellen sauber; erwartete FK-Ziele
  (person/audit_log/role/capability) vorhanden.
- **R05** beide Partial-Indizes mit `WHERE revoked_at IS NULL`.
- **R06** `MIGRATION_APPLIED`-Beleg für Version 6; `verify_chain` grün.
- **R07** Seed-Idempotenz: direkter 2. `up()` clobbert bestehende Zeile nicht
  (`INSERT OR IGNORE`) und dupliziert nicht („green and alive").

**Regression (`run_tests.py`):** Python **821** passed (814 + 7), 59 skipped,
3 subtests; JavaScript **467** passed, 1 skipped, 1 todo (kein JS geändert).

---

## 7. Deploy

`migrate.py`-Lauf auf der VM **zwingend** (Schemaänderung `coordinator.db`).
`coordinator.db` hat keinen Migrationslock (kein Beweismittel). Vor dem Lauf
Backup gemäß Betriebspraxis.

---

## 8. Anschluss (Folge-Builds)

- **344 — RBAC Schnitt (b):** `RbacRepo` + `policy_admin`-CLI über den
  `CoordinatorWriter`; `RBAC_GRANTED/REVOKED`, `ROLE_ASSIGNED/REVOKED` als neue
  `event_types`; Basis-Grants (§11.3-Zuschnitt) auditiert seeden.
- **345 — RBAC Schnitt (c):** Resolver (Rollen→Grants→Scope, `alle` > `eigene`)
  + Start-Check „Code-Capability ⊆ DB".

---

*Dokument-Ende · Detail-Bauplan Build 343 · v0.1 · 2026-07-10*

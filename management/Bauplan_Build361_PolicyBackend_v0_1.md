# Bauplan Build 361 — Policy-Sicht Teil 1: Backend `/api/policy` + PolicyRepo

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 1** (Cockpit-Sichten)
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11.3 · `RbacRepo`-
Lesepfade. **Basis:** 0.7.360. **mc:** 2026-07-10.

---

## 1. Ziel und Split

Erste Welle-1-Sicht: die **Rechte/Policy**-Sicht. Dieser Build liefert das
Backend — einen read-only `/api/policy`-Endpunkt, der genau die Matrix liefert,
die zuvor per SQL aus `coordinator.db` gelesen wurde. **Keine Migration.**
**Split (mc):** 361 Backend · 362 Frontend (console-first).

---

## 2. Umfang (geliefert)

- **`management/rbac/policy_repo.py`** — `PolicyRepo(con).snapshot([person_id])`:
  - `roles` (rbac_role: code, label), `capabilities` (rbac_capability: code,
    label, description),
  - `grants` (**aktive** rbac_grant: role/capability/scope/audit_seq/
    granted_by/granted_at/note),
  - `assignments` (**aktive** person_role, angereichert um `system_username`/
    `display_name`), plus `counts`.
  - Scope: `snapshot()` → volle Matrix; `snapshot(person_id)` → gefiltert (nur
    eigene Zuweisungen + Grants der eigenen Rollen = „meine Rechte");
    roles/capabilities bleiben voller Katalog.
- **`management/server/management_app.py`** (geändert): `CAP_POLICY =
  "policy.view"`; `/api/policy` → `_policy` (403 ohne Cap; scope-aware). read-only.
- **Tests** `tests/test_policy_repo.py` (PR01–PR04, EP01–EP03).

---

## 3. Regression (run_tests.py)

```
pytest : 947 passed, 59 skipped, 3 subtests   (940 + 7)
vitest : 519 passed, 1 skipped, 1 todo (521), 41 Testdateien   (unverändert)
```

---

## 4. Abnahme

Nach Grant `policy.view` (für supervisor bereits eingepflegt):
`GET /api/policy` → `{scope, roles, capabilities, grants, assignments, counts}`
— dieselbe Matrix wie zuvor per SQL.

---

## 5. Nächster Build (362, Frontend, console-first)

`cockpit_policy.js` (Tabulator-Tabellen für Grants + Zuweisungen, Rollen-/
Fähigkeiten-Katalog) + `cockpit.js`/`cockpit.html`-Verdrahtung + SSE-Reload;
vitest für die reine Aufbereitungs-Logik.

---

*Dokument-Ende · Bauplan Build 361 · 2026-07-10*

# Bauplan Build 365 — CLI-Filter für `rbac_admin` (Zwischenbuild)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface) · **Basis:** 0.7.364.
**Anlass:** Wunsch aus dem Betrieb (Filterung der RBAC-Listen). **Keine Migration.**

---

## 1. Ziel

`list-grants` und `list-roles` filterbar machen — ohne die bestehenden Ausgaben
zu verändern.

---

## 2. Umfang (geliefert)

- **`management/rbac/rbac_admin.py`** (geändert):
  - `list-grants --role R1,R2,…` — kommagetrennter Rollenfilter.
  - `list-roles --id N1,N2,…` — kommagetrennte `person_id`-Liste.
  - `list-roles --role R1,R2,…` — kommagetrennter Rollenfilter.
  - `--person` (system_username) und `--id` werden **vereinigt**; Personen- und
    Rollenfilter **UND**-verknüpft. `--all` (revozierte) bleibt.
  - **Grundregel 1:** unbekannte Rollen-Tokens → Warnung auf stderr; `--id` mit
    nicht-ganzzahligem Token → klare Fehlermeldung + Exit 1. Neue Helfer
    `_csv_set` / `_csv_int_set` / `_warn_unknown_roles`.
- **`tests/test_management_rbac_repo.py`** (geändert): A02 (list-grants Rollen-
  filter, einzeln + kommagetrennt) + A03 (list-roles `--id` / `--role` /
  kommagetrennt) via `rbac_admin.main(argv)`.

---

## 3. Regression (run_tests.py)

```
pytest : 953 passed, 59 skipped, 3 subtests   (951 + 2)
vitest : 534 passed, 1 skipped, 1 todo (536), 44 Testdateien   (unverändert)
```

---

## 4. Beispiele

```
python -m management.rbac.rbac_admin list-grants --role supervisor
python -m management.rbac.rbac_admin list-grants --role supervisor,investigator
python -m management.rbac.rbac_admin list-roles  --id 5
python -m management.rbac.rbac_admin list-roles  --id 1,2
python -m management.rbac.rbac_admin list-roles  --role supervisor,admin
python -m management.rbac.rbac_admin list-roles  --id 5 --role supervisor
```

---

*Dokument-Ende · Bauplan Build 365 · 2026-07-10*

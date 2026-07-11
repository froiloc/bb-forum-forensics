# Bauplan Build 357 — Kapazität Teil 2b: Schreibpfade Gründe + Verfügbarkeit

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 0**
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11.4 · Muster
`rbac_repo`/Build 356. **Basis:** 0.7.356. **mc:** 2026-07-10.

---

## 1. Ziel

Zweite Hälfte der Kapazitäts-Schreibpfade: der Grund-Katalog und die
Verfügbarkeits-Einträge (Garantie/Einschränkung). Damit sind alle vier
Kapazitäts-Tabellen beschreibbar. **Keine Migration.**

**Design-Entscheidungen (zum Veto):** `reason_code` optional, aber falls gesetzt
muss er einen **aktiven** Grund referenzieren; **kein Overlap-Guard** (Einträge
kombinieren erst in der Berechnung 358); Gründe sind **add/list** (die vereinbarte
Audit-Granularität kennt kein `REASON_REMOVED`); Validierung genau eines von
`value_pct`/`value_minutes`, `pct ∈ [0,100]`, `minutes ≥ 0`,
`period_start ≤ period_end`.

---

## 2. Umfang (geliefert)

- **`management/capacity/reason_repo.py`** — `ReasonRepo`: `add_reason` →
  `AVAILABILITY_REASON_ADDED` (Duplikat-Guard auf PK `code`); `list_reasons`;
  `is_active(code)`.
- **`management/capacity/availability_repo.py`** — `AvailabilityRepo`:
  `set_availability(...)` → `AVAILABILITY_SET` (Validierung s.o.);
  `remove_availability` → `AVAILABILITY_REMOVED` (**Soft-Delete**);
  `list_availability`.
- **`management/capacity/capacity_admin.py`** (geändert): `add-reason`,
  `list-reasons`, `set-availability`, `remove-availability`,
  `list-availability`.
- **Tests** `tests/test_capacity_availability.py` (RS01–RS02, AV01–AV05, CL01).

---

## 3. Regression (run_tests.py)

```
pytest : 926 passed, 59 skipped, 3 subtests   (918 + 8)
vitest : 511 passed, 1 skipped, 1 todo (513), 40 Testdateien   (unverändert)
```

---

## 4. Nutzung

```
python -m management.capacity.capacity_admin add-reason --code urlaub --label Urlaub --actor h0a2898
python -m management.capacity.capacity_admin set-availability --person h002 \
  --start 2026-08-01 --end 2026-08-14 --kind einschraenkung --pct 0 --reason urlaub --actor h0a2898
python -m management.capacity.capacity_admin list-availability --person-id 2
```

---

## 5. Stand & nächste Builds

**Kapazitäts-Schreibpfade komplett:** 355 (Schema) · 356 (Worktime/Holiday) ·
357 (Reason/Availability). **Nächste Builds:** 358 — Berechnung
`Kapazität(Zeitraum)` (Σ Arbeitstag-Minuten − Einschränkungen im Rahmen der
Garantien) · 359 — Cockpit-Sicht (Gantt/Überlast).

---

*Dokument-Ende · Bauplan Build 357 · 2026-07-10*

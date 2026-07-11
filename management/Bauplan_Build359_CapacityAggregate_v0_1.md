# Bauplan Build 359 — Kapazität Teil 4a: Aggregat-Endpunkt (Cockpit-Backend)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 0**
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11.4. **Basis:** 0.7.358.
**mc:** 2026-07-10.

---

## 1. Ziel und Split

Backend der Kapazitäts-Cockpit-Sicht: `/api/capacity` liefert **ohne**
`person_id` eine Team-Sicht (alle Ermittler). **Keine Migration.** **Split
(mc):** 359 Backend · 360 Frontend (ECharts, console-first) — analog Workload
350/351.

---

## 2. Umfang (geliefert)

- **`management/server/management_app.py`** (`_capacity` erweitert):
  - `start`/`end` Pflicht; `person_id` optional.
  - **mit** `person_id` → Einzelperson (flaches `CapacityResult`, unverändert
    seit 358).
  - **ohne** `person_id` → **Aggregat**: je Ermittler (`person.is_investigator=1`)
    eine Kapazitäts-Zeile (`CapacityResult` + `system_username` + `display_name`).
    Antwort `{scope, count, start, end, capacities:[...]}`.
  - scope-aware (`alle` → alle; `eigene` → nur eigene Zeile); 400 bei fehlenden
    `start`/`end`; `CapacityError` → 400. read-only, `capacity.edit`.
- **Tests** `tests/test_capacity_calculator.py`: EP05 (Aggregat alle), EP06
  (scope eigene), EP07 (bad request). EP01–EP04 (Einzelperson) unverändert.

---

## 3. Regression (run_tests.py)

```
pytest : 940 passed, 59 skipped, 3 subtests   (937 + 3)
vitest : 511 passed, 1 skipped, 1 todo (513), 40 Testdateien   (unverändert)
```

---

## 4. Abnahme

Nach Grant `capacity.edit`:
`GET /api/capacity?start=2026-07-06&end=2026-07-10` (ohne `person_id`) →
`{capacities:[{person_id, display_name, basis, einschraenkungen,
garantie_boden, netto, ...}]}`.

---

## 5. Nächster Build (360, Frontend, console-first)

`cockpit_capacity.js` (ECharts, UMD, Live-DEBUG): Basis vs. netto je Ermittler,
Auslastungs-Färbung `netto/basis`, Zeitraumwahl (Default laufender Monat);
`cockpit.js`/`cockpit.html`-Verdrahtung + SSE-Reload; vitest für die reine
Serien-Logik.

---

*Dokument-Ende · Bauplan Build 359 · 2026-07-10*

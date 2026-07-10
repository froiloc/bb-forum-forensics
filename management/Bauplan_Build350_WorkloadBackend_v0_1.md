# Bauplan Build 350 — Lastverteilung Backend `/api/workload` + ECharts-Vendoring

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), Welle 1 (Cockpit-Sichten)
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11.2 · vorhandene
`WorkloadRepo`. **Basis:** Version 0.7.349.

---

## 1. Ziel und Split

Backend-Teil der Cockpit-Sicht „Lastverteilung": ein read-only-Endpunkt
`/api/workload`, der je Ermittler eine aggregierte Last-Zeile liefert, plus die
ECharts-Bibliothek management-lokal vendort. Die **ECharts-Frontend-Sicht** folgt
in **Build 351** (browser-verifizierbar, console-first).

Management-Server bleibt **read-only/GET-only**. **Keine Migration.**

---

## 2. Umfang (geliefert)

- **GEÄNDERT `management/server/management_app.py`:**
  - Import `WorkloadRepo`/`WorkloadSchemaError` + `dataclasses.asdict`;
    `CAP_WORKLOAD = "workload.view"`; Dispatch-Route `/api/workload`.
  - `_workload(person_id)`: cap-Check (→ 403 ohne `workload.view`); scope-aware
    analog `_overview`:
    - `alle` → je Ermittler eine `InvestigatorLoad`-Zeile (auch 0 Fälle) plus
      eine Rückstau-Zeile (`is_backlog`, unzugewiesen).
    - `eigene` (oder ungesetzt) → nur die **eigene** Zeile
      (`investigator_id == person_id`); Rückstau/fremde gekapselt.
  - `WorkloadRepo.list_workload()` → `asdict` → `{scope, count, loads}`;
    `WorkloadSchemaError` → 503.
- **VENDOR `management/server/static/vendor/echarts/echarts.min.js`** (Apache
  ECharts 6.1.0). Wird über `StaticAssets` ausgeliefert; in 350 noch ungenutzt
  (Nutzung in 351), aber bereitgestellt + pytest-geprüft.
- **GEÄNDERT `tests/test_management_server.py`:**
  - Harness um `workload.view`-Grants erweitert (supervisor `alle`, investigator
    `eigene`) — bricht M01 nicht (dort nur `dashboard.view`/`ops.view` geprüft).
  - **W01–W05** (an bestehender Klasse/Harness, kein Duplikat — bewusste
    Abweichung vom Bauplan-Dateinamen `test_management_workload.py` zugunsten
    DRY): W01 scope `alle`, W02 scope `eigene`, W03 ohne Cap → 403, W04
    DTO-Aggregatfelder, W05 vendorte ECharts ausgeliefert. `m11` um
    `/api/workload` (read-only) ergänzt.

---

## 3. Regression (run_tests.py)

```
pytest : 883 passed, 59 skipped, 3 subtests   (878 + 5 Workload)
vitest : 504 passed, 1 skipped, 1 todo (506), 39 Testdateien   (unverändert — Backend-only)
```

---

## 4. Nächster Build (351) — ECharts-Frontend-Sicht (console-first)

- `cockpit_workload.js` (IIFE+UMD, Live-DEBUG): reine `toSeries(loads)`
  (horizontal gestapelte Ampel-Balken je Ermittler, Rückstau als eigene Zeile,
  sortiert rot desc); DOM `renderWorkload(mainEl, data, {ECharts})` (Instanz
  injizierbar → vitest).
- `cockpit.js`: `workload`-Zweig + SSE-Reload. `cockpit.html`: ECharts + Modul.
- vitest für die reine Serien-Logik; Chart-Render = Browser-Abnahme (console-first).

---

*Dokument-Ende · Bauplan Build 350 · 2026-07-10*

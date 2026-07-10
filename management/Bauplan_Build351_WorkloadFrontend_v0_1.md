# Bauplan Build 351 — Lastverteilung Frontend (ECharts-Sicht)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), Welle 1 (Cockpit-Sichten)
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11.2 · Build 350
(`/api/workload`, ECharts vendort). **Basis:** Version 0.7.350.

---

## 1. Ziel

Frontend-Teil der Cockpit-Sicht „Lastverteilung": die `/api/workload`-Daten als
horizontal gestapeltes **ECharts**-Balkendiagramm — je Ermittler ein Balken,
segmentiert nach Ampel (rot/gelb/grün); die Rückstau-Zeile (unzugewiesen) als
eigener Balken. Reihenfolge aus dem Backend (ROT desc, Rückstau ans Ende);
`yAxis.inverse` → dringlichster oben.

**Reiner Frontend-Build:** kein Backend, keine Migration.

---

## 2. DEPLOY-HINWEIS

`cockpit.html` wurde geändert → fällt unter `.gitignore` (`*.html`) → **muss** mit
`git add -f management/server/static/cockpit.html` eingecheckt werden.

---

## 3. Umfang (geliefert)

- **NEU `cockpit_workload.js`** (IIFE + UMD → `window.AIWCockpitWorkload`,
  Live-DEBUG):
  - Rein: `nameLabel`, `echartsOption(data)` (deterministische ECharts-Option:
    3 gestapelte Serien Rot/Gelb/Grün über den Ermittler-Kategorien;
    `yAxis.inverse`; Backend-Reihenfolge beibehalten), `scopeText`.
  - DOM: `renderWorkload(mainEl, data, {ECharts})` (Kopf + Diagramm; Container-
    Höhe wächst mit Zeilenzahl; ECharts-Ctor injizierbar → vitest).
  - **Farb-Vertrag:** Ampelfarben spiegeln `cockpit.css` (`--rot/--gelb/--gruen`)
    als Konstanten (ECharts liest keine CSS-Variablen).
- **GEÄNDERT `cockpit.js`**:
  - `selectView` → `workload`-Zweig lädt `loadWorkload()`.
  - `loadWorkload()` rendert via `AIWCockpitWorkload` und bindet einen
    Resize-Handler an die ECharts-Instanz.
  - **Lifecycle:** neue `destroyChart()` (ECharts `dispose()` + Resize abmelden)
    und `cleanupView()` (`destroyTable` + `destroyChart`) ersetzen die bisherigen
    `destroyTable`-Aufrufe in `selectView`/`loadOverview` — Tabelle **und**
    Diagramm werden beim Sichtwechsel/Reload sauber abgebaut.
  - SSE `changed`: auch die aktive Workload-Sicht wird neu geladen.
- **GEÄNDERT `cockpit.html`**: `echarts.min.js` + `cockpit_workload.js` (defer)
  eingebunden.
- **NEU `tests/unit/test_cockpit_workload.test.js`** (WL01–WL07): `nameLabel`,
  `echartsOption` (Kategorien/Serien/Werte, `yAxis.inverse`, Farben, `stack`,
  leere loads), `renderWorkload` (Kopf/Scope/Count, Stub-ECharts `init`+`setOption`,
  ohne ECharts → null + Hinweis).

---

## 4. Regression (run_tests.py)

```
pytest : 883 passed, 59 skipped, 3 subtests   (unverändert — reines Frontend)
vitest : 511 passed, 1 skipped, 1 todo (513), 40 Testdateien   (504 + 7; 39 + 1)
```

---

## 5. Browser-Abnahme (console-first)

In Prod zuerst `workload.view` granten:
```
python -m management.rbac.rbac_admin grant --role supervisor \
  --capability workload.view --scope alle --actor h0a2898 \
  --coordinator-db data/coordinator.db
```
(Die Testperson ist bereits supervisor.) Dann Cockpit laden → Tab
„Lastverteilung" zeigt das gestapelte Ampel-Balkendiagramm (dringlichster oben,
Rückstau als eigener Balken). **SSE:** auditierte Änderung → Diagramm lädt ohne
F5 neu. Bei Auffälligkeiten: Console-Output (`window.AIW_COCKPIT_DEBUG = true`) →
PoC → Fix.

---

## 6. Horizont

Welle 1 weitere Sichten: Zuweisung (Schreibpfad — eigener Architekturschritt),
Support-Historie. Welle 0 Rest: Backup/PITR, Kapazität/Workflow.

---

*Dokument-Ende · Bauplan Build 351 · 2026-07-10*

# Bauplan Build 360 — Kapazität Teil 4b: Cockpit-Sicht (ECharts-Frontend)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 0**
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11.4 · Build 359
(`/api/capacity`-Aggregat). **Basis:** 0.7.359. **mc:** 2026-07-10.

---

## 1. Ziel

Frontend-Teil der Kapazitäts-Cockpit-Sicht: die `/api/capacity`-Aggregat-Daten
als ECharts-Balkendiagramm — je Ermittler **Basis** (Regel-Soll) und **Netto**
(verfügbar), Netto nach **Auslastung** (`netto/basis`) gefärbt, mit
**Zeitraum-Wahl** (Default: laufender Monat). **Reiner Frontend-Build.**

---

## 2. DEPLOY-HINWEIS

`cockpit.html` geändert → `.gitignore` (`*.html`) → **`git add -f
management/server/static/cockpit.html`**. Ebenso die Bauplan-`.md`.

---

## 3. Umfang (geliefert)

- **NEU `cockpit_capacity.js`** (IIFE + UMD → `window.AIWCockpitCapacity`,
  Live-DEBUG):
  - Rein: `utilization` (`netto/basis`, `null` bei `basis≤0`), `utilColor`
    (≥0.8 grün, ≥0.5 gelb, sonst rot; grau ohne Basis), `sortRows` (stark
    reduzierte zuerst, basis-lose ans Ende), `echartsOption` (Serien Basis/Netto,
    Netto je Balken gefärbt, `yAxis.inverse`), `defaultPeriod(now)` (laufender
    Monat), `scopeText`.
  - DOM: `renderCapacity(mainEl, data, {ECharts, onPeriodChange})` (Kopf +
    Zeitraum-Wahlfelder + „Aktualisieren" → `onPeriodChange` + Diagramm).
- **GEÄNDERT `cockpit.js`**: `capacity` → `capacity.edit` im `VIEW_CATALOG`;
  `loadCapacity` (Aggregat für Zeitraum, `state.capacityPeriod` für SSE-Reload,
  Zeitraum-Wahl lädt neu); `selectView`-Zweig; SSE-Reload; ECharts-Lifecycle via
  `cleanupView`.
- **GEÄNDERT `cockpit.html`**: `cockpit_capacity.js` (defer) eingebunden.
- **Tests** `tests/unit/test_cockpit_capacity.test.js` (CA01–CA08) +
  `test_cockpit_nav.test.js` (Katalog-Länge 11 → 12).

---

## 4. Regression (run_tests.py)

```
pytest : 940 passed, 59 skipped, 3 subtests   (unverändert — reines Frontend)
vitest : 519 passed, 1 skipped, 1 todo (521), 41 Testdateien   (511 + 8; 40 + 1)
```

---

## 5. Browser-Abnahme (console-first)

`capacity.edit` granten (Supervisor hat es i. d. R.) → Cockpit laden → Tab
„Kapazitaet": je Ermittler Basis- und Netto-Balken für den laufenden Monat, Netto
nach Auslastung gefärbt; Zeitraum änderbar; SSE-Reload ohne F5. Bei
Auffälligkeiten `window.AIW_COCKPIT_DEBUG = true` → Console → PoC → Fix.

---

## 6. Stand

**Kapazität komplett:** 355 (Schema) · 356 (Worktime/Holiday) · 357
(Reason/Availability) · 358 (Berechnung) · 359 (Aggregat) · 360 (Sicht).
**Welle-0-Rest** laut Bauplan (Backup + Kapazität) damit abgearbeitet.
Ausblick: echte Verschneidung Netto vs. zugewiesene Fall-Last (Workload) als
eigener, späterer Baustein.

---

*Dokument-Ende · Bauplan Build 360 · 2026-07-10*

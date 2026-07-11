# Bauplan Build 371 — Statistiken Teil 2: Cockpit-Sicht (Frontend, Reiterstruktur)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 1**
**Autoritativ:** `Ideen_Verwaltungswerkzeug_konsolidiert.md` §2.4 · Build 370
(`/api/stats`). **Basis:** 0.7.370. **mc:** 2026-07-10.

---

## 1. Ziel

Frontend der Statistik-Sicht mit **Reiterstruktur** (Tabs), ECharts-Diagrammen,
Ermittler-Tabelle und **CSV/JSON-Download**. **Reiner Frontend-Build.**

---

## 2. DEPLOY-HINWEIS

`cockpit.html` geändert → `.gitignore` (`*.html`) → **`git add -f
management/server/static/cockpit.html`**. Ebenso die Bauplan-`.md`.

---

## 3. Umfang (geliefert)

- **NEU `cockpit_stats.js`** (UMD → `window.AIWCockpitStats`, Live-DEBUG):
  - Rein: `barOption`, `throughputOption`, `assigneeRows`, `totalsText`,
    `isoDate`.
  - DOM: `renderStats(mainEl, data, {ECharts, Tabulator, onDownloadCsv,
    onDownloadJson})` — Kopf + Summen + Download-Leiste + **3 Tabs**
    („Verteilungen": Status/Prio/Ampel-Balken; „Durchsatz": Linie; „Ermittler":
    Tabelle). Tab-Wechsel → Sichtbarkeit + `resize()` der sichtbaren Charts
    (ECharts rendert in `display:none` mit Größe 0). Rückgabe `{charts, tables}`;
    leicht um weitere Tabs erweiterbar.
- **GEÄNDERT `cockpit.js`**: `state.charts` (+ `cleanupView`-Dispose);
  `downloadBlob`; `loadStats` (Downloads: CSV via `?format=csv`, JSON aus den
  geladenen Daten); `selectView`-Zweig; SSE-Reload.
- **GEÄNDERT `cockpit.html`**: `cockpit_stats.js` (defer) eingebunden.
- **Tests** `tests/unit/test_cockpit_stats.test.js` (SS01–SS06).

---

## 4. Regression (run_tests.py)

```
pytest : 965 passed, 59 skipped, 3 subtests   (unverändert — reines Frontend)
vitest : 551 passed, 1 skipped, 1 todo (553), 47 Testdateien   (545 + 6; 46 + 1)
```

---

## 5. Browser-Abnahme (console-first)

`stats.export_sta` granten → Cockpit laden → Tab „Statistiken". Reiter
umschalten (Diagramme rendern nach Tab-Wechsel via resize korrekt). CSV/JSON-
Download testen. Supervisor (alle) alle Fälle; investigator (eigene) nur eigene.
Bei Auffälligkeiten `window.AIW_COCKPIT_DEBUG = true` → Console → PoC → Fix.

---

## 6. Stand

**Statistiken komplett** (370 Backend · 371 Frontend). Verdrahtete Welle-1-
Sichten: Dashboard, Integrität, Lastverteilung, Kapazität, Rechte/Policy, Meine
Aufträge, Meine Historie, Support-Historie, Ermittler-Betreuung, Statistiken.
**Offen:** Zuweisung (Schreib-Sicht), Berichts-Abnahme.

---

*Dokument-Ende · Bauplan Build 371 · 2026-07-10*

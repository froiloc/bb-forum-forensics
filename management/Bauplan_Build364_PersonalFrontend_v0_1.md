# Bauplan Build 364 — Persönliche Sichten Teil 2: Cockpit-Sichten (Frontend)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 1**
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11 · Build 363
(`/api/mycases`, `/api/myhistory`). **Basis:** 0.7.363. **mc:** 2026-07-10.

---

## 1. Ziel

Frontend der persönlichen Sichten: „Meine Aufträge" (eigene Fälle) und „Meine
Historie" (kombinierte Zeitleiste). **Reiner Frontend-Build.**

---

## 2. DEPLOY-HINWEIS

`cockpit.html` geändert → `.gitignore` (`*.html`) → **`git add -f
management/server/static/cockpit.html`**. Ebenso die Bauplan-`.md`.

---

## 3. Umfang (geliefert)

- **NEU `cockpit_mycases.js`** (UMD → `window.AIWCockpitMyCases`, Live-DEBUG):
  `daysSince`, `toRows`, `renderMyCases(mainEl, data, {Tabulator, nowSec})` —
  Kopf „Meine Auftraege" + Tabulator (user_id/username/status/prio/ampel/
  ereignisse/notiz/inaktiv-tage). Eigenständig.
- **NEU `cockpit_myhistory.js`** (UMD → `window.AIWCockpitMyHistory`,
  Live-DEBUG): `fmtTs`, `herkunftLabel` (ich / mein Fall / beides),
  `targetLabel`, `toRows`, `renderMyHistory(mainEl, data, {Tabulator})` — Kopf
  „Meine Historie" + Tabulator-Zeitleiste (seq/zeit/ereignis/ziel/herkunft).
- **GEÄNDERT `cockpit.js`**: `loadMyCases`/`loadMyHistory` (je eine Tabulator-
  Instanz → `state.table`); `selectView`-Zweige; SSE-Reload. (Views schon im
  `VIEW_CATALOG` → kein Nav-Count-Change.)
- **GEÄNDERT `cockpit.html`**: beide Skripte (defer) eingebunden.
- **Tests** `test_cockpit_mycases.test.js` (MYC01–05) + `test_cockpit_myhistory.
  test.js` (MYH01–05).

---

## 4. Regression (run_tests.py)

```
pytest : 951 passed, 59 skipped, 3 subtests   (unverändert — reines Frontend)
vitest : 534 passed, 1 skipped, 1 todo (536), 44 Testdateien   (524 + 10; 42 + 2)
```

Hinweis: vitest-Basis bei 363 war **524 / 42** (Korrektur der 363-Notiz, die
irrtümlich 519 nannte; die Python-Zahlen waren korrekt).

---

## 5. Browser-Abnahme (console-first)

`mycases.view`/`myhistory.view` (investigator, scope eigene) granten → Cockpit
laden → Tab „Meine Auftraege" (eigene Fälle) und „Meine Historie" (kombinierte
Zeitleiste; Spalte Herkunft: ich / mein Fall / beides). SSE-Reload ohne F5. Bei
Auffälligkeiten `window.AIW_COCKPIT_DEBUG = true` → Console → PoC → Fix.

---

## 6. Stand

**Persönliche Sichten komplett** (363 Backend · 364 Frontend). Verdrahtete
Welle-1-Sichten: Dashboard, Integrität, Lastverteilung, Kapazität, Rechte/Policy,
Meine Aufträge, Meine Historie. **Offen:** Zuweisung (Schreib-Sicht),
Ermittler-Betreuung, Berichts-Abnahme, Statistiken, Support-Historie.

---

*Dokument-Ende · Bauplan Build 364 · 2026-07-10*

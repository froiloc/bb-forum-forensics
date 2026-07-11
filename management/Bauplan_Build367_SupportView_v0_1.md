# Bauplan Build 367 — Support-Historie Teil 2: Cockpit-Sicht (Frontend)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 1**
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11 · Build 366
(`/api/support`). **Basis:** 0.7.366. **mc:** 2026-07-10.

---

## 1. Ziel

Frontend der Support-Historie: **zwei getrennte Listen** (über die Marker) plus
**Detail-Mini-Modal**. **Reiner Frontend-Build.**

---

## 2. DEPLOY-HINWEIS

`cockpit.html` geändert → `.gitignore` (`*.html`) → **`git add -f
management/server/static/cockpit.html`**. Ebenso die Bauplan-`.md`.

---

## 3. Umfang (geliefert)

- **NEU `cockpit_support.js`** (UMD → `window.AIWCockpitSupport`, Live-DEBUG):
  - Rein: `fmtTs`, `supporterLabel`, `markLabel`, `bucketize` (nicht-
    überlappend: `mine` → „Meine Sitzungen" [Vorrang], sonst `on_my_case` → „An
    meinen Fällen", sonst „Weitere"), `decorate` (Anzeige-Hilfsfelder; voller
    Record bleibt), `detailPairs` (volle Feldliste inkl. `status`/`anomaly`/
    Beleg-seq).
  - DOM: `buildDetailNode` (dl), `createModalRoot`/`showDetail`/`hideDetail`
    (Mini-Modal; Overlay-Klick/Button/Escape), `renderSupport(mainEl, data,
    {Tabulator})` — Kopf + bis zu drei nicht-leere Abschnitts-Tabellen + Modal;
    Zeilenklick öffnet Detail-Modal mit dem vollständigen Record. XSS: nur
    textContent.
- **GEÄNDERT `cockpit.js`**: `loadSupport` (mehrere Tabellen → `state.tables`);
  `selectView`-Zweig; SSE-Reload. (`support` schon im `VIEW_CATALOG`.)
- **GEÄNDERT `cockpit.html`**: `cockpit_support.js` (defer) eingebunden.
- **Tests** `tests/unit/test_cockpit_support.test.js` (SP01–SP06).

---

## 4. Regression (run_tests.py)

```
pytest : 956 passed, 59 skipped, 3 subtests   (unverändert — reines Frontend)
vitest : 540 passed, 1 skipped, 1 todo (542), 45 Testdateien   (534 + 6; 44 + 1)
```

---

## 5. Browser-Abnahme (console-first)

`support_history.view` granten → Cockpit laden → Tab „Support-Historie".
Supervisor (alle) sieht „Weitere Sitzungen"; investigator (eigene) sieht „Meine
Sitzungen" + „An meinen Fällen". Zeile anklicken → Mini-Modal mit vollem
Datensatz (`status`/`anomaly`/Belege). SSE-Reload ohne F5. Bei Auffälligkeiten
`window.AIW_COCKPIT_DEBUG = true` → Console → PoC → Fix.

---

## 6. Stand

**Support-Historie komplett** (366 Backend · 367 Frontend). Verdrahtete Welle-1-
Sichten: Dashboard, Integrität, Lastverteilung, Kapazität, Rechte/Policy, Meine
Aufträge, Meine Historie, Support-Historie. **Offen:** Zuweisung (Schreib-Sicht),
Ermittler-Betreuung, Berichts-Abnahme, Statistiken.

---

*Dokument-Ende · Bauplan Build 367 · 2026-07-10*

# Bauplan Build 362 — Policy-Sicht Teil 2: Cockpit-Sicht (Frontend)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 1**
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11.3 · Build 361
(`/api/policy`). **Basis:** 0.7.361. **mc:** 2026-07-10.

---

## 1. Ziel

Frontend der Rechte/Policy-Sicht: die `/api/policy`-Matrix im Cockpit — zwei
Tabulator-Tabellen (Grants, Rollen-Zuweisungen) plus Katalog. **Reiner
Frontend-Build.**

---

## 2. DEPLOY-HINWEIS

`cockpit.html` geändert → `.gitignore` (`*.html`) → **`git add -f
management/server/static/cockpit.html`**. Ebenso die Bauplan-`.md`.

---

## 3. Umfang (geliefert)

- **NEU `cockpit_policy.js`** (IIFE + UMD → `window.AIWCockpitPolicy`,
  Live-DEBUG):
  - Rein: `capLabelIndex`, `grantRows` (mit Fähigkeits-Label), `assignmentRows`,
    `scopeText`.
  - DOM: `renderPolicy(mainEl, data, {Tabulator})` — Kopf + counts, **Grants**-
    Tabelle (Rolle/Fähigkeit/Bezeichnung/Scope/Beleg/Notiz, mit headerFilter),
    **Zuweisungs**-Tabelle (Person/Kennung/Rolle/Beleg), **Katalog** (Rollen/
    Fähigkeiten). Gibt Array der Tabulator-Instanzen zurück. XSS: nur
    textContent / Tabulator-plaintext.
- **GEÄNDERT `cockpit.js`**: `state.tables` (mehrere Instanzen) + `cleanupView`
  baut sie ab; `loadPolicy`; `selectView`-Zweig; SSE-Reload. (`policy` war schon
  im `VIEW_CATALOG` → kein Nav-Count-Change.)
- **GEÄNDERT `cockpit.html`**: `cockpit_policy.js` (defer) eingebunden.
- **Tests** `tests/unit/test_cockpit_policy.test.js` (PO01–PO05).

---

## 4. Regression (run_tests.py)

```
pytest : 947 passed, 59 skipped, 3 subtests   (unverändert — reines Frontend)
vitest : 524 passed, 1 skipped, 1 todo (526), 42 Testdateien   (519 + 5; 41 + 1)
```

---

## 5. Browser-Abnahme (console-first)

`policy.view` ist für supervisor gegrantet → Cockpit laden → Tab „Rechte /
Policy": Grants-Tabelle (Rolle → Fähigkeit), Zuweisungs-Tabelle (Person → Rolle)
und Katalog — dieselbe Matrix wie zuvor per SQL, sortier-/filterbar. SSE-Reload
ohne F5. Bei Auffälligkeiten `window.AIW_COCKPIT_DEBUG = true` → Console → PoC →
Fix.

---

## 6. Stand

**Policy-Sicht komplett** (361 Backend · 362 Frontend). Verdrahtete Welle-1-
Sichten: Dashboard, Integrität, Lastverteilung, Kapazität, Rechte/Policy.
**Offen:** Zuweisung (Schreib-Sicht), Ermittler-Betreuung, Berichts-Abnahme,
Statistiken, Support-Historie, Meine Aufträge, Meine Historie.

---

*Dokument-Ende · Bauplan Build 362 · 2026-07-10*

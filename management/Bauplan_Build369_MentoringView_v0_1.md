# Bauplan Build 369 — Ermittler-Betreuung Teil 2: Cockpit-Sicht (Frontend, Live)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 1**
**Autoritativ:** `Ideen_Verwaltungswerkzeug_konsolidiert.md` §2.12 · Build 368
(`/api/mentoring`). **Basis:** 0.7.368. **mc:** 2026-07-10.

---

## 1. Ziel

Frontend der Ermittler-Betreuung: **Live-Sicht** der laufenden Support-Sitzungen
mit Live/Stale-Ampel und Laufzeit, plus **periodischem Refresh**. **Reiner
Frontend-Build.**

---

## 2. DEPLOY-HINWEIS

`cockpit.html` geändert → `.gitignore` (`*.html`) → **`git add -f
management/server/static/cockpit.html`**. Ebenso die Bauplan-`.md`.

---

## 3. Umfang (geliefert)

- **NEU `cockpit_mentoring.js`** (UMD → `window.AIWCockpitMentoring`,
  Live-DEBUG): `fmtDuration`, `supporterLabel`, `statusLabel`, `toRows`,
  `staleCount`, `renderMentoring(mainEl, data, {Tabulator})` — Kopf + Sub (N
  laufend, M stale) + Tabulator; `rowFormatter` hebt stale-Zeilen hervor.
- **GEÄNDERT `cockpit.js`**: `state.mentoringTimer`; `cleanupView` stoppt den
  Timer; `loadMentoring` (Erst-Laden + Timer) + `refreshMentoring` (Tick ohne
  Timer-Churn); `MENTORING_REFRESH_MS = 15000` (unter der 30-s-Stale-Schwelle);
  `selectView`-Zweig; SSE-Reload (Session-Start/-Ende auditiert; reine
  Heartbeats nicht → daher der Timer).
- **GEÄNDERT `cockpit.html`**: `cockpit_mentoring.js` (defer) eingebunden.
- **Tests** `tests/unit/test_cockpit_mentoring.test.js` (MT01–MT05).

---

## 4. Regression (run_tests.py)

```
pytest : 960 passed, 59 skipped, 3 subtests   (unverändert — reines Frontend)
vitest : 545 passed, 1 skipped, 1 todo (547), 46 Testdateien   (540 + 5; 45 + 1)
```

---

## 5. Browser-Abnahme (console-first)

`mentoring.view` granten → Cockpit laden → Tab „Ermittler-Betreuung": laufende
Sitzungen, stale-Zeilen hervorgehoben, Auto-Refresh alle 15 s. Test: eine
Support-Sitzung starten (erscheint live), Heartbeat aussetzen → nach ~30 s
wechselt sie auf stale. Bei Auffälligkeiten `window.AIW_COCKPIT_DEBUG = true` →
Console → PoC → Fix.

---

## 6. Stand

**Ermittler-Betreuung komplett** (368 Backend · 369 Frontend). Verdrahtete
Welle-1-Sichten: Dashboard, Integrität, Lastverteilung, Kapazität, Rechte/Policy,
Meine Aufträge, Meine Historie, Support-Historie, Ermittler-Betreuung.
**Offen:** Zuweisung (Schreib-Sicht), Berichts-Abnahme, Statistiken.

---

*Dokument-Ende · Bauplan Build 369 · 2026-07-10*

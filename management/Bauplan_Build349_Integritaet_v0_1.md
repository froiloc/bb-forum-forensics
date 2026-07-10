# Bauplan Build 349 — Integritäts-/Ops-Sicht + Ketten-Banner + Live-DEBUG

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), Welle 1 (Cockpit-Sichten)
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11.1 (Live via SSE) ·
§11.2 (Sichten). **Basis:** Version 0.7.348.

---

## 1. Ziel

Die **Integritäts-/Ops-Sicht** (`/api/integrity`) sichtbar machen und die
Ketten-Gesundheit des auditierten, hash-verketteten `audit_log` **global** im
Kopf-Banner anzeigen — jederzeit, unabhängig von der aktiven Sicht. Zusätzlich
das DEBUG-Flag zur **Laufzeit** umschaltbar machen (kein Reload).

**Reiner Frontend-Build:** kein Backend, keine Migration. `/api/integrity`
existiert seit 346 und liefert `{ok, first_bad_seq, detail, tip_seq}`.

**Entscheidungen (2026-07-10):** Banner global sofern `ops.view`; ohne `ops.view`
still (kein 403-Rauschen); Live-DEBUG in allen drei JS-Modulen.

---

## 2. WICHTIG — Deploy-Korrektur: fehlende `cockpit.html`

`management/server/static/cockpit.html` wurde bei 347/348 **nicht** eingecheckt,
weil `.gitignore` (`*.html`, Zeile 39) sie ausschließt. Lokal war sie vorhanden
(Browser lief), im **gepushten Repo fehlte sie** → ein Frisch-Deploy hätte auf
`/` ein **404** geliefert (`ManagementApp._index` serviert genau diese Datei).

**Behebung:** `cockpit.html` liegt in diesem ZIP (349-Stand) bei und **muss** mit
`git add -f management/server/static/cockpit.html` eingecheckt werden. Gleiches
Muster wie bei den Bauplan-`.md`.

---

## 3. Umfang (geliefert)

- **NEU `cockpit_integrity.js`** (IIFE + UMD → `window.AIWCockpitIntegrity`,
  Live-DEBUG):
  - Rein: `bannerModel(data)` → `{klass:'ok'|'fehler', text}`. Fehlende
    Sequenzwerte werden nicht still verschluckt (`'?'`).
  - DOM: `applyBanner(el, model)` (Klasse + Text, entfernt
    `aiw-integrity-hidden`), `renderIntegrity(main, data)` (Karte: Status mit
    Ampelpunkt, `tip_seq`, `first_bad_seq`, `detail`). XSS-sicher (textContent).
- **GEÄNDERT `cockpit.js`**:
  - `selectView` → `integrity`-Zweig lädt `loadIntegrity()`.
  - `loadIntegrity()` rendert die Sicht **und** aktualisiert den Banner (eine
    Quelle: `applyIntegrity`).
  - `refreshBanner()` hält den Banner **global** frisch (nur bei `ops.view`);
    ohne `ops.view` → Banner still (`aiw-integrity-hidden`).
  - SSE `changed`: aktive Sicht neu laden (dashboard→Overview,
    integrity→Integrität) **und** Banner nachziehen.
  - `boot()`: Platzhaltertext → `refreshBanner()` (Doppel-Fetch vermieden, wenn
    `integrity` erste Sicht ist).
  - **Live-DEBUG:** `debugOn()` liest `window.AIW_COCKPIT_DEBUG` bei jedem
    `log()`-Aufruf → ohne Reload umschaltbar.
- **GEÄNDERT `cockpit_overview.js`**: Live-DEBUG (`debugOn`).
- **GEÄNDERT `cockpit.html`**: `cockpit_integrity.js` vor `cockpit.js`; Banner-
  Kommentar auf 349.
- **GEÄNDERT `cockpit.css`**: `.aiw-integrity-hidden { display:none }`.
- **NEU `tests/unit/test_cockpit_integrity.test.js`** (IN01–IN08): `bannerModel`
  (ok/!ok/fehlende Sequenz), `applyBanner`, `renderIntegrity` (ok/!ok, Ampelpunkt,
  Sequenzen), `detail` via textContent.

---

## 4. Regression (run_tests.py)

```
pytest : 878 passed, 59 skipped, 3 subtests   (unverändert ggü. committetem 348 — reines Frontend)
vitest : 504 passed, 1 skipped, 1 todo (506), 39 Testdateien   (+8 Integrität)
```

*Hinweis: Der committete 348-Stand wies bereits 878 pytest / 496 vitest auf —
höher als die von mir gelieferte 348-Zahl (865/487). Bitte bei Gelegenheit
abgleichen, ob dort weitere Tests hinzugekommen sind.*

---

## 5. Browser-Abnahme

Als supervisor (`dashboard.view` + `ops.view`) das Cockpit laden → grüner
Ketten-Banner „Kette intakt bis Sequenz N"; Tab „Integritaet / Betrieb" zeigt die
Karte. **SSE:** auditierte Änderung (z. B. `rbac_admin grant`) → Banner-Sequenz
steigt **ohne F5**. **Live-DEBUG:** `window.AIW_COCKPIT_DEBUG = true` in der
Console wirkt sofort (kein Reload).

---

## 6. Horizont

Welle 0 Rest: Backup/PITR, Kapazität/Workflow. Welle 1 weitere Sichten
(Zuweisung, Lastverteilung mit ECharts, Support-Historie).

---

*Dokument-Ende · Bauplan Build 349 · 2026-07-10*

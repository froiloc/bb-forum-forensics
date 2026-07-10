# Bauplan Build 348 — Cockpit Overview-Sicht + SSE-Reload

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), Welle 1 (Cockpit-Sichten)
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11.2 (Tabellen mit
Tabulator.js, SSE-Reload) · §11.1 (Live via SSE, „alle schlägt eigene");
Referenzlayout `AIW_Verwaltung_Mockup.html`.
**Basis:** Version 0.7.347 (Cockpit-Shell).

---

## 1. Ziel und Abgrenzung

Build 348 macht die **Fall-Übersicht** (`/api/overview`) im Cockpit sichtbar —
als **Tabulator-v6-Tabelle** mit Ampel-Sortierung und Scope-Anzeige — und
aktiviert den **SSE-Reload**: steigt die `audit_log`-Spitze, lädt der Client
**nur die aktive Sicht** neu (kein F5).

**Reiner Frontend-Build:** kein Backend, keine Migration. `/api/overview`,
`/api/integrity`, `/events` und die statische Auslieferung existieren bereits
(346/347).

**Split (Entscheidung 2026-07-10):** Die **Integritäts-/Ops-Sicht**
(`/api/integrity` + Banner-Bindung) ist bewusst **nicht** enthalten → eigener
**Build 349** (kleinere baubare Einheit).

**console-first vorab bestätigt:** Ein Diagnose-PoC im echten Browser hat
Tabulator v6.4.0 (`tableBuilt`, DOM-Zeilen korrekt) und den SSE-Strom
(`hello`/`keepalive` im RFC-8895-Rahmen) **grün** gezeigt. Die Overview-Datenform
ist autoritativ aus dem Backend (`ManagementApp._overview`, 346) bekannt.

---

## 2. Umfang (geliefert)

- **NEU `management/server/static/cockpit_overview.js`** (IIFE + UMD →
  `window.AIWCockpitOverview`):
  - **Rein:** `ampelRank`, `reasonLabel`, `assigneeLabel`, `supportLabel`,
    `daysSince` (nowSec injizierbar), `toRows` (DTO → Zeilen + abgeleitete
    Felder, mutiert nicht), `sortRows` (Ampel-Schwere → Prio ↑ → letzte
    Aktivität ↓ → user_id; Kopie), `columnDefs` (10 Spalten), `scopeText`.
  - **DOM:** `renderOverview(mainEl, data, opts)` → Kopf (Titel, Scope-Banner,
    Anzahl) + Tabulator-Tabelle. `opts.Tabulator` injizierbar (Testbarkeit),
    Default `window.Tabulator`. Gibt die Instanz zurück.
  - **Konventions-Vertrag:** Ampel-Vokabular, `ampel_reason`-Labels und die
    Anzeige-Sortierung spiegeln `dashboard_repo.AMPEL_*` (Build 315)/`dashboard.js`;
    bewusst eigenständig + eigenständig getestet (Split-Build; der gemeinsame
    Vertrag ist das **Backend-Vokabular**, nicht die Datei).
  - **XSS-sicher:** Textspalten via Tabulator-`plaintext` (textContent); eigene
    Formatter bauen DOM-Knoten (kein `innerHTML` mit variablem Text).
- **GEÄNDERT `cockpit.js`:** `selectView` verzweigt (`dashboard`→`loadOverview`,
  sonst Platzhalter); `loadOverview` holt `/api/overview` und rendert; `state.table`
  + `destroyTable()` (Tabulator-Lifecycle — alte Instanz vor Neuaufbau/Sichtwechsel
  abbauen); `renderError()` (sichtbarer Fehlerhinweis); **SSE-Client** `startSse()`
  (`/events`; bei `changed` nur die aktive Sicht neu laden; `onerror` tolerant für
  Auto-Reconnect). `boot()` zeigt die erste Sicht über `selectView` und startet SSE.
- **GEÄNDERT `cockpit.html`:** `cockpit_overview.js` **vor** `cockpit.js`
  eingebunden (defer, Reihenfolge). Integritäts-Banner neutral (Bindung folgt 349).
- **GEÄNDERT `cockpit.css`:** dezente Ampel-Zeilenfärbung
  (`.tabulator-row.aiw-row-{rot,gelb,gruen}` via `box-shadow`).
- **NEU `tests/unit/test_cockpit_overview.test.js`** (OV01–OV10, JSDOM): reine
  Funktionen; `sortRows`/`toRows` (Reihenfolge + Nichtmutation); `columnDefs` (10)
  + Ampel-Formatter (Farbpunkt + Grund); `renderOverview` (Kopf/Scope/Count,
  Stub-Tabulator erhält sortierte Zeilen + Spalten, ohne Ctor → null + Hinweis).

---

## 3. Regression (run_tests.py)

```
pytest : 865 passed, 59 skipped, 3 subtests   (unverändert — reines Frontend)
vitest : 487 passed, 1 skipped, 1 todo (489), 36 Testdateien   (477 + 10; 35 + 1)
```

---

## 4. Browser-Abnahme (console-first Roll-out)

Cockpit neu laden → Tab „Dashboard" zeigt die Fall-Übersicht als
Tabulator-Tabelle (Ampel-Sortierung, Scope-Banner `alle`/`eigene`, Spalten
sortier-/filterbar). **SSE-Test:** eine auditierte Änderung erzeugen (z. B.
`rbac_admin grant`/`revoke-grant`) → die Übersicht lädt sich **ohne F5** neu
(Console bei `window.AIW_COCKPIT_DEBUG = true` zeigt `SSE changed`).

Bei Auffälligkeiten: Console-Output anfordern → PoC → Fix (console-first).

---

## 5. Nächster Build (349) — Integritäts-/Ops-Sicht

- Integritäts-Sicht an `/api/integrity` (Kette ok/first_bad_seq/tip_seq/detail).
- Banner-Bindung `#aiw-integrity` (grün/rot) inkl. SSE-Reaktualisierung.
- eigenes `cockpit_integrity.js` (IIFE+UMD) + vitest.

---

*Dokument-Ende · Bauplan Build 348 · 2026-07-10*

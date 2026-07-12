# Bauplan Build 375 — Berichts-Abnahme Teil 2: Cockpit-Sicht + Rechte-Korrektur

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 1**
**Autoritativ:** Build 374 (`/api/reports`). **Basis:** 0.7.374.

---

## 1. Gefundener Fehler (behoben)

Der Nav-Katalog gatete „Berichts-Abnahme" auf **`reports.approve`**, der
Endpunkt `/api/reports` (Build 374) aber auf **`reports.review`**. Bei der
bestehenden Grant-Lage (`supervisor → reports.approve`, `lector →
reports.review`) hieß das:

- **Supervisor:** sieht den Reiter → bekommt **403**.
- **Lektor:** hat das Leserecht → sieht den Reiter **gar nicht**.

**Behebung:** `/api/reports` akzeptiert **`reports.review` ODER
`reports.approve`** — *approve impliziert review* (wer freigeben darf, muss lesen
dürfen). Der wirksame Scope ist der weitere der beiden. Zusätzlich kann die Nav
jetzt **mehrere Fähigkeiten je Sicht** führen (`caps` = any-of; `cap` bleibt
Leitfähigkeit, rückwärtskompatibel).

---

## 2. Umfang (geliefert)

- **`management_app.py`**: `CAP_REPORTS_APPROVE`; `/api/reports` any-of-Gating.
- **`cockpit.js`**: `viewCaps` / `effectiveCap` / `visibleViews` (any-of);
  `caps: ['reports.approve','reports.review']`; `loadReports(mainEl, force)`;
  `selectView`-Zweig; SSE-Reload.
- **NEU `cockpit_reports.js`** (UMD → `window.AIWCockpitReports`): `toRows`,
  `filterByStatus`, `statusCounts`, `scanInfoText`, `renderReports(...)` —
  Kopf + **Scan-Info** (macht die Cache-Wirkung sichtbar: „N Fall-Datenbanken,
  davon M neu eingelesen"), **Statusfilter** (lokal), Knopf **„Neu einlesen"**
  (`?force=1`), Tabulator-Tabelle, **Hinweisbereich**: nicht lesbare evidence-DBs
  und Fälle **ohne** evidence-DB werden **angezeigt** (Grundregel 1). Die Sicht
  ist bewusst **nur lesend** — die Freigabe/Versiegelung folgt in 376.
- **`cockpit.html`**: Skript eingebunden.
- **Tests**: `test_cockpit_reports.test.js` (BR01–BR06) · `test_cockpit_nav.test.js`
  CN11 (any-of) · `test_reports_scan.py` RS09 (`reports.approve` allein genügt).

---

## 3. Regression (run_tests.py)

```
pytest : 982 passed, 59 skipped, 3 subtests   (981 + 1)
vitest : 564 passed, 1 skipped, 1 todo (566), 49 Testdateien   (557 + 7; 48 + 1)
```

---

## 4. Browser-Abnahme (console-first)

**Server neu starten.** Reiter „Berichts-Abnahme" (jetzt auch für den Supervisor
nutzbar): Berichtsliste aller Fälle, Statusfilter, „Neu einlesen". Die Scan-Info
zeigt beim zweiten Aufruf **„0 neu eingelesen"** (Cache greift). Nicht lesbare
DBs und Fälle ohne evidence-DB erscheinen als Hinweis.

---

## 5. Nächste Schritte

- **376 — Versiegelung:** `approved_reports.db` (nur `supervisor` schreibt, alle
  lesen), Inhaltshash nach der Konvention aus `core/startup_checks.py`
  (kanonischer Dump, **ohne** `report_comments` per `mc`), `POST
  /api/report/approve` (setzt `evidence.reports.status` + `report_approvals`,
  legt das statische Abbild zentral ab, schreibt den `coordinator`-Audit-Beleg)
  + `verify`-Pfad.
- **377 — Schreibsperre** im Ermittler-Webserver bei Status `approved`/`final`.

**Offen/vermerkt:** (a) Fallauswahl-GUI für Ermittler (Ermittler-Webserver;
Behelf `main.py --user-id`); (b) **Fall-Autodetektion gegen `data/`** — der
Scanner liefert dafür bereits `cases_without_db` und die DB-Liste.

---

*Dokument-Ende · Bauplan Build 375 · 2026-07-10*

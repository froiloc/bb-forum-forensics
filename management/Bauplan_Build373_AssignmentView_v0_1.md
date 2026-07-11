# Bauplan Build 373 — Zuweisung Teil 2: Cockpit-Schreib-Sicht (Frontend)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 1**
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §2.6 · Build 372
(Schreibpfad). **Basis:** 0.7.372.

---

## 1. Ziel

Frontend der ersten **Schreib**-Sicht: Fälle zuweisen/entziehen, Priorität und
Status setzen — alles über den auditierten POST-Pfad. Zusätzlich: **Korrektur
der irreführenden Server-Startmeldung** (Hinweis des Entwicklers).

---

## 2. DEPLOY-HINWEIS

`cockpit.html` geändert → `.gitignore` (`*.html`) → **`git add -f
management/server/static/cockpit.html`**. Ebenso die Bauplan-`.md`.

---

## 3. Umfang (geliefert)

- **NEU `cockpit_assignment.js`** (UMD → `window.AIWCockpitAssignment`):
  `assigneeLabel`, `toRows`, `investigatorOptions` (inkl. Last je Ermittler und
  „(nicht zugewiesen)"), `changeRequest(kind, userId, value)` → `{path, body}`
  (`''` → `person_id: null` = entziehen); `renderAssignment(mainEl, data,
  {onChange})` — Tabelle aller Fälle mit **drei Auswahlfeldern je Zeile**
  (Ermittler / Priorität / Status) + Rückmeldebereich; liefert `{setMessage}`.
  **Kein optimistisches UI** (bewusst, forensisch): die Oberfläche zeigt nie
  einen Zustand, der nicht bestätigt geschrieben ist.
- **GEÄNDERT `cockpit.js`**: `state.writeToken` (aus `/api/whoami`); **`postJson`**
  (Content-Type + `X-AIW-Token`; wertet Fehlerantworten aus und reicht die
  Server-Begründung weiter — Grundregel 1); `loadAssignment(mainEl, pendingMsg)`
  (schreibt → **lädt neu**; die Rückmeldung „Gespeichert (Beleg #`audit_seq`)"
  bzw. der Fehler wird durch den Reload getragen und bleibt sichtbar);
  `selectView`-Zweig; SSE-Reload.
- **GEÄNDERT `cockpit.html`**: `cockpit_assignment.js` (defer).
- **GEÄNDERT `management.py`**: **Startmeldung korrigiert.** Bisher „Server
  laeuft (read-only)" — seit Build 372 sachlich falsch. Neu: „Server laeuft:
  <url>" + „Lesezugriffe read-only; Schreibzugriffe nur über die auditierten
  POST-Routen (Token-geschützt, jede Änderung wird im `audit_log` belegt)."
- **Tests** `tests/unit/test_cockpit_assignment.test.js` (AZ01–AZ06).

---

## 4. Regression (run_tests.py)

```
pytest : 973 passed, 59 skipped, 3 subtests   (unverändert)
vitest : 557 passed, 1 skipped, 1 todo (559), 48 Testdateien   (551 + 6; 47 + 1)
```

---

## 5. Browser-Abnahme (console-first)

**Server neu starten.** `assignment.edit` (Scope `alle`) granten → Cockpit laden
→ Tab „Zuweisung": Ermittler/Priorität/Status per Auswahlfeld ändern → Meldung
„Gespeichert (Beleg #N)"; der Beleg ist im `audit_log` nachprüfbar (und taucht in
„Meine Historie" auf). Fehlerfall: Server neu starten **ohne** Seiten-Reload →
Schreibversuch scheitert mit Token-Fehlermeldung (altes Token); Seite neu laden
behebt es. Bei Auffälligkeiten `window.AIW_COCKPIT_DEBUG = true`.

---

## 6. Stand

**Zuweisung komplett** (372 Backend · 373 Frontend). Damit sind **alle**
Welle-1-Cockpit-Sichten verdrahtet **außer „Berichts-Abnahme"**
(`reports.approve`).
**Offen/vermerkt:** Fallauswahl-GUI für Ermittler (eigener Baustein am
**Ermittler**-Webserver; Behelf: `main.py --user-id`).

---

*Dokument-Ende · Bauplan Build 373 · 2026-07-10*

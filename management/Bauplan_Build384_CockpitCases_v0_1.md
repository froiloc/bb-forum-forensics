# Bauplan Build 384 — Cockpit-Sicht „Fall-Erkennung" (Frontend)

**Version:** 0.1 · **Datum:** 2026-07-12 · *(nachgereicht in Build 386)*
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Basis:** 0.7.383 · **mc:** 2026-07-12 · **Migration:** keine.

---

## 1. Abgrenzung

Reiner **Frontend**-Build zum Backend aus 383 (Festlegung 363: Backend und
Frontend sind immer getrennte Builds). Das Backend
(`GET /api/cases/detect`, `POST /api/cases/import`) bleibt **unverändert**.

**Recht:** `assignment.edit` — Backend-Vorgabe aus 383
(`_require_assignment_scope`, Scope `alle`). Es wird **bewusst keine zweite
Fähigkeit** eingeführt (`mc`).

---

## 2. Was die Sicht leistet

| Element | Zweck |
|---|---|
| Zähler der vier Zustände | `ok` / `neu` / `vermisst` / `unlesbar` |
| **Verzeichnisangaben** | *worüber* wurde gemessen — ohne sie ist „kein Fall gefunden" wertlos (ein falsches Verzeichnis sieht genauso aus) |
| **Warnbereich** (rot, **oberhalb** der Tabelle) | `vermisst` / `unlesbar` **mit Grund**. Ein Statusfilter kann ihn **nicht wegblenden** (Grundregel 1) |
| Statusfilter + Tabulator-Tabelle | Ampel-Zeilenfärbung: Missstand rot, aufnehmbar gelb, erfasst grün |
| Aktionsfeld | „Ausgewählte aufnehmen (n)" |

---

## 3. Die tragenden Entscheidungen

- **Auswahlkästchen nur bei `neu` + vorhandenem Benutzernamen.** Das ist exakt
  `CaseDetector.importable()`. Die Oberfläche bietet damit **keine Aktion an,
  die serverseitig zwingend als `skipped` zurückkäme**.
- **Eigener Formatter statt Tabulators `rowSelection`.** So gibt es **kein
  „alles auswählen"** im Spaltenkopf, und die Auswahlregel steht sichtbar im
  Code statt in einer Bibliotheksoption.
- **Zweistufig:** Knopf → **Bestätigungsblock** mit Auflistung und Hinweis auf
  die Belegpflicht (`case_created` im `audit_log`) → erst „Ja" schreibt. Ein
  Fehlklick verändert keine Fallakte.
- **Kein `{all:true}` im UI.** Der Stapelbetrieb bleibt dem CLI
  (`case_detect --auto`) vorbehalten (`mc`).
- **Die Auswahl lebt im Zustand, nicht im DOM** → ein Filterwechsel verliert sie
  **nicht still**.
- **Kein optimistisches UI.** Nach dem POST wird neu geladen; die Serverantwort
  wird **wörtlich** wiedergegeben: `imported` **mit Beleg-Nr.**, `skipped`
  **mit Grund**. Ein einziger übersprungener Fall färbt die Rückmeldung **rot** —
  das ist ein **Befund**, kein Erfolg.
- **Ohne Tabellenbibliothek** stehen Warnbereich und Zähler **trotzdem**. Die
  Warnung darf nicht an einer Bibliothek scheitern.

---

## 4. Umfang (geliefert)

- **NEU** `management/server/static/cockpit_cases.js` (IIFE + UMD, `window.AIWCockpitCases`)
- `cockpit.js` — Katalogeintrag `{id:'cases', cap:'assignment.edit', group:'Verwaltung'}`,
  `loadCases()`, Dispatch, SSE-Reload
- `cockpit.html` — Script-Tag (**`git add -f`**, `*.html` ist in `.gitignore`)
- `cockpit.css` — additiver Block, **eng auf `.aiw-cases-*` gefasst**: die
  übrigen Sichten (350–382) sind bislang ungestylt; eine globale
  `.aiw-btn`-Regel würde deren Aussehen mit verändern. Der Warnbereich ist der
  eigentliche Grund für das Stylesheet („deutliche Warnung" lässt sich mit
  Browser-Vorgaben nicht erfüllen).
- **NEU** `tests/unit/test_cockpit_cases.test.js` (FE01–FE11, 14 Fälle)
- `tests/unit/test_cockpit_nav.test.js` — Katalog 12 → 13, neu CN03b

**Testhinweis:** Der Fake-Tabulator **ruft die Spalten-Formatter auf**. Ohne das
würde der Test den Auswahl-/Bestätigungsweg gar nicht berühren — die
„grün aber tot"-Falle.

---

## 5. Regression (run_tests.py)

```
pytest : 1018 passed, 59 skipped, 6 subtests   (unverändert — Frontend-only)
vitest : 591 passed (576 + 14 + 1), 51 Testdateien
```

---

## 6. Abnahme

**Server neu starten** (sonst 404 auf neue Statik).

1. Nav „Verwaltung" → **Fall-Erkennung**; Zähler und Verzeichnisse müssen zur
   CLI-Ausgabe von `python -m management.cases.case_detect` passen.
2. **Gegenprobe:** eine `forensic_<uid>.db` umbenennen → **roter Warnbereich
   „VERMISST"** mit Grund; die **Fallakte bleibt unverändert**.
3. Einen `neu`-Fall auswählen → Knopf wird scharf → Bestätigung → Aufnahme →
   Rückmeldung **mit Beleg-Nr.**; der Fall steht danach auf „erfasst".
4. DEV-Log: `window.AIW_COCKPIT_DEBUG = true`.

---

*Dokument-Ende · Bauplan Build 384 · 2026-07-12*

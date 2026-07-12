# Bauplan Build 378 — Berichts-Freigabe im Cockpit (Frontend)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 · **Basis:** 0.7.377 · **Migration:** keine.
**Autoritativ:** Build 377 (`POST /api/report/approve`, `GET /api/report/verify`).

---

## 1. Ziel

Die Freigabe (Versiegelung) aus dem Cockpit heraus bedienbar machen — samt
**Siegelprüfung**. Reiner Frontend-Build.

---

## 2. DEPLOY-HINWEIS

`cockpit.html` geändert → `.gitignore` (`*.html`) → **`git add -f
management/server/static/cockpit.html`**. Ebenso die Bauplan-`.md`.

---

## 3. Umfang (geliefert)

- **`cockpit_reports.js`**:
  - `toRows` liefert `report_id` (für die Aktionen zwingend).
  - **`availableActions(row, canApprove)`** — spiegelt die **Server-Vorbedingungen**
    (Build 377): „Freigeben" nur aus `submitted` **und** nur mit
    `reports.approve`; „Endgültig freigeben" nur aus `approved`; „Siegel prüfen"
    bei `approved`/`final` — **auch ohne** `reports.approve` (prüfen darf, wer
    die Berichte sehen darf).
  - **`verifyText(v)`** — nennt eine **ABWEICHUNG** beim Namen
    („Manipulationsverdacht"); beschönigt nichts.
  - **Aktionsfeld** unter der Tabelle (Zeilenklick wählt den Bericht) mit den
    verfügbaren Knöpfen und Ergebnisbereich; `showVerify()` zeigt Klartext +
    **Gegenüberstellung Siegel-Hash / aktueller Hash**, Freigeber, Zeit, Beleg.
  - **Bewusst keine Knöpfe in den Tabellenzellen:** Die Freigabe ist ein
    Schreibvorgang mit Belegpflicht — erst Bericht wählen, dann handeln.
- **`cockpit.js`**: `canApprove` aus den Fähigkeiten; `onApprove` (POST mit
  Schreib-Token → **neu laden**, kein optimistisches UI; Rückmeldung nennt
  Beleg-Nummer und Hash-Anfang); `onVerify` (GET → Ergebnis im Aktionsfeld).
  Fehler werden sichtbar gemeldet.
- **Tests** `test_cockpit_reports.test.js`: BR08–BR10.

---

## 4. Regression (run_tests.py)

```
pytest : 994 passed, 59 skipped, 3 subtests   (unverändert — reines Frontend)
vitest : 568 passed, 1 skipped, 1 todo (570), 49 Testdateien   (565 + 3)
```

---

## 5. Browser-Abnahme (console-first)

**Server neu starten.** Voraussetzung: ein Bericht mit `status='submitted'`.
Cockpit → „Berichts-Abnahme" → Zeile anklicken → Aktionsfeld.
„Freigeben (versiegeln)" → Meldung „Freigegeben und versiegelt (Beleg #N,
Hash …)"; die Zeile steht danach auf „freigegeben". Erneut wählen → „Siegel
prüfen" → „Siegel in Ordnung".

**Gegenbeweis:** den Bericht direkt in der evidence-DB ändern (SQLite-Werkzeug,
am Werkzeug vorbei) → erneut „Siegel prüfen" → **„ABWEICHUNG …
Manipulationsverdacht"** samt Hash-Gegenüberstellung.

---

## 6. Stand & nächste Schritte

**Berichts-Abnahme komplett** (374 Scan · 375 Sicht · 377 Versiegelung · 378
Freigabe-Frontend). **Welle 1 abgeschlossen.**

- **379 — Schreibsperre im Ermittler-Webserver** bei `approved`/`final`
  (Durchsetzung dort, wo geschrieben wird; bisher schützt der zentrale Hash nur
  **nachträglich**).
- Danach: **Fall-Autodetektion gegen `data/`**.
- **Offen/vermerkt:** Fallauswahl-GUI für Ermittler (Behelf `main.py --user-id`).

---

*Dokument-Ende · Bauplan Build 378 · 2026-07-10*

# Bauplan Build 382 — Berichtseditor: „Zur Abnahme freigeben" (Frontend + Dialog)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Basis:** 0.7.381 · **mc:** 2026-07-10 · **Migration:** keine.
**Statusmodell:** `documents/Berichts_Statusmodell.md`

---

## 1. Warum ein Dialog

Das Einreichen hat **Tragweite**: Der Bericht wird damit **für den Autor
gesperrt** (Schreibsperre, Build 379). Zurückholen kann ihn **nur** der Lektor
oder die Chef-Ermittlerin. **Das darf kein versehentlicher Klick sein.**

Der Dialog klärt über **drei** Dinge auf:

| Abschnitt | Inhalt |
|---|---|
| **Tragweite** | Der Bericht wird **für Sie gesperrt** — keine Absätze mehr anlegen/ändern/löschen/umsortieren, keine Beweisanker. **Kommentare bleiben möglich.** |
| **Prozess** | Erscheint bei der Chef-Ermittlerin zur Abnahme → mit der Abnahme **versiegelt** (unwiderruflich) → danach Versand an die StA. |
| **Rückholung** | **Sie selbst können den Bericht nicht zurückholen.** Nur Lektor oder Chef-Ermittlerin können ihn zur Nachbesserung zurückgeben. |

**Zweistufig:** Der Bestätigen-Knopf ist **anfangs gesperrt** und wird erst durch
das Kontrollkästchen *„Mir ist bewusst, dass ich den Bericht danach nicht mehr
selbst bearbeiten kann."* freigeschaltet.

---

## 2. Umfang (geliefert)

- **NEU `userinfo/submit_dialog.js`** (IIFE + UMD → `window.SubmitDialog`):
  - `canSubmit(report, investigator)` — Knopf **nur** beim **eigenen** Bericht im
    Status **`draft`**. (Der Server prüft erneut; die Oberfläche ist keine
    Sicherheitsgrenze — sie soll nur keine Aktion anbieten, die zwingend
    scheitern würde.)
  - `dialogTexts(titel)` — die Aufklärung als **Daten** (testbar, nicht im
    DOM-Code versickert).
  - `open(doc, titel, onConfirm)` — Overlay-Dialog, zweistufig.
  - XSS: ausschließlich `textContent`.
- **GEÄNDERT `userinfo/report.js`**: `_meUsername` (aus
  `/_forensic/investigator/me` → `system_username`), `_reportsCache`;
  `_renderSubmitButton()` (Knopf in der Kopfzeile, nur wenn `canSubmit`);
  `_submitReport()` über den bestehenden **Lock-gesicherten** POST-Pfad; zeigt
  die **Tragweiten-Meldung des Servers** an, statt einen eigenen Text zu
  erfinden.
- **GEÄNDERT `forensic_api/static.py`**: Datei in die Auslieferungs-Whitelist.
- **GEÄNDERT `forensic_api/report.py`**: `<script src="/_forensic/submit_dialog.js">`.
- **Tests** `tests/unit/test_submit_dialog.test.js` (SD01–SD06).

---

## 3. Regression (run_tests.py)

```
pytest : 1011 passed, 59 skipped, 6 subtests   (unverändert — reines Frontend)
vitest : 576 passed, 1 skipped, 1 todo (578), 50 Testdateien   (570 + 6; 49 + 1)
```

---

## 4. Browser-Abnahme (console-first)

**Server neu starten** (neue statische Datei + Template). Editor mit einem
**eigenen** Bericht im Status `draft` öffnen → Knopf **„Zur Abnahme freigeben"**.
Klick → Dialog mit den drei Abschnitten; **Bestätigen ist gesperrt**, bis das
Kästchen gesetzt ist. Nach dem Bestätigen: Server-Meldung („… ist für Sie nun
gesperrt. Nur der Lektor oder die Chef-Ermittlerin …"), der Knopf verschwindet,
jede Inhaltsänderung wird abgewiesen; **Kommentare gehen weiterhin**. Im Cockpit
erscheint der Bericht als „eingereicht".

---

## 5. Stand

**Die Berichts-Zustandsmaschine ist vollständig umgesetzt:**

```
draft ──(382 Editor)──► submitted ──(378 Cockpit, versiegelt)──► approved
  ▲                         │                                        │
  └──(380 Cockpit: Lektor/Chefin)──┘                    (380)────────▼
                                                                  final
```

Schreibsperre (379) und Siegel-Nachweis (377) greifen.

**Nächster Punkt (vorgemerkt):** **Fall-Autodetektion** gegen `data/` — neue
evidence-DBs aufnehmen, fehlende melden (der Scanner liefert bereits
`cases_without_db` und die DB-Liste). **Weiterhin offen:** Fallauswahl-GUI für
Ermittler (Behelf `main.py --user-id`).

---

*Dokument-Ende · Bauplan Build 382 · 2026-07-10*

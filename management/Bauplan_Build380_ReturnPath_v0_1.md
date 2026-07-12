# Bauplan Build 380 — Rückgabe zur Nachbesserung + Korrekturen

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Basis:** 0.7.379 · **mc:** 2026-07-10 · **Migration:** keine.
**Statusmodell:** `documents/Berichts_Statusmodell.md` (v1.1)

---

## 0. Pfad-Korrektur

Das Statusmodell-Dokument liegt jetzt unter **`documents/`** (nicht `docs/`).
Der Verweis in `db/evidence_db.py` zeigte noch auf `docs/` — **toter Pfad**,
korrigiert.

---

## 1. Rückgabe zur Nachbesserung (`submitted → draft`)

**Nur aus `submitted`.** Abgenommene (`approved`) und versandte (`final`)
Berichte werden **nie** zurückgestuft — inhaltliche Schwächen eines abgenommenen
Berichts werden über einen **Nachtragsbericht** (`report_type='addendum'`)
behandelt.

**Berechtigt:** Lektor (`reports.review`) **und** Chef-Ermittlerin
(`reports.approve` — impliziert `review`). Scope `alle`.
**Der Autor kann sich nicht selbst zurückholen** — das ist der Sinn der Sperre.

**Ablauf:** Beleg (`REPORT_RETURNED` via `CoordinatorWriter`) **zuerst**, dann
Status setzen. Scheitert der zweite Schritt, bleibt der Beleg stehen und der
Aufrufer bekommt einen expliziten Fehler (Grundregel 1).

**Management-Pfad schreibt direkt:** bewusst **nicht** über
`EvidenceDb.update_report_status` — dessen Zustandsmaschine (Build 379) schützt
den **Ermittler**-Pfad; der Management-Pfad ist der autorisierte Weg, der genau
diese Übergänge vornehmen **darf** (und dabei auditiert).

---

## 2. Beschriftungs-Korrektur

„Endgültig freigeben" → **„Als versandt/abgeschlossen kennzeichnen"**.
`final` ist **keine höhere Freigabestufe**, sondern der **Versand an die StA**
(siehe Statusmodell).

---

## 3. Umfang (geliefert)

- `event_types.py`: `REPORT_RETURNED`.
- `approval_service.py`: `return_to_draft()`, `_set_evidence_status()`.
- `management_app.py`: **`POST /api/report/return`** (Lektor **oder** Chefin,
  Scope `alle`; 409 mit Begründung bei verletzter Vorbedingung).
- `cockpit_reports.js`: Aktion **„Zur Nachbesserung zurückgeben"** (auf
  `submitted`, für Lektor **oder** Chefin); Beschriftung korrigiert; aus
  `approved` **keine** Rückgabe mehr.
- `cockpit.js`: `canReview` durchgereicht; `onReturn` → POST → neu laden.
- `documents/Berichts_Statusmodell.md` → **v1.1** (Tabelle der umgesetzten
  Übergänge).
- Tests: `test_report_sealing.py` SE08–SE10 · `test_cockpit_reports.test.js`
  BR08 (aktualisiert), BR11, BR12.

---

## 4. Regression (run_tests.py)

```
pytest : 1005 passed, 59 skipped, 6 subtests   (1002 + 3)
vitest : 570 passed, 1 skipped, 1 todo (572), 49 Testdateien   (568 + 2)
```

---

## 5. Browser-Abnahme (console-first)

**Server neu starten.** Voraussetzung: ein Bericht im Status `submitted`.
Cockpit → „Berichts-Abnahme" → Zeile wählen:
- **Chefin** sieht „Freigeben (versiegeln)" **und** „Zur Nachbesserung
  zurückgeben".
- Ein **Lektor** (nur `reports.review`) sieht **nur** die Rückgabe.
- Nach der Rückgabe steht der Bericht auf **Entwurf**; der Autor kann ihn wieder
  bearbeiten (die Schreibsperre aus 379 ist aufgehoben).
- Bei `approved` erscheint jetzt **„Als versandt/abgeschlossen kennzeichnen"**.

---

## 6. Verbleibender offener Punkt → Build 381

**Ermittler-Editor:** Schaltfläche **„Zur Abnahme freigeben"**
(`draft → submitted`) mit **Bestätigungsdialog** (Tragweite: Autor wird gesperrt;
weiterer Prozess; Rückholmöglichkeit über Lektor/Chef-Ermittlerin) — **bewusste
Entscheidung, kein versehentlicher Klick.** *Endpunkt existiert noch nicht.*

---

*Dokument-Ende · Bauplan Build 380 · 2026-07-10*

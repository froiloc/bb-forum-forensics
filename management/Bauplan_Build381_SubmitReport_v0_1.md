# Bauplan Build 381 — Ermittler-Editor: „Zur Abnahme freigeben" (Backend)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Basis:** 0.7.380 · **mc:** 2026-07-10 · **Migration:** keine.
**Statusmodell:** `documents/Berichts_Statusmodell.md` · Code: **`BERICHTS-STATUSMODELL`**

---

## 1. Ziel

Der **letzte fehlende Übergang** der Zustandsmaschine: **`draft → submitted`** —
der Autor reicht seinen Bericht zur Abnahme ein. **Split:** 381 Backend · 382
Frontend (Knopf + **Bestätigungsdialog**).

---

## 2. Umfang (geliefert)

**`forensic_api/report.py`** — neue POST-Aktion **`submit_report`**:

1. `_require_lock` — der bestehende Editor-Lock-Schutz greift weiter (**423**
   ohne gültigen Lock). Der Lock ist an die `report_id` gebunden, deshalb liefert
   ein **unbekannter Bericht** ebenfalls 423 — *erst der Lock, dann die
   Fachlogik*.
2. `report_id` validieren (**400**), Bericht laden (**404**).
3. **Nur der Verfasser** darf einreichen (**403** für alle anderen). Abnahme und
   Rückgabe laufen über das Management-Cockpit, nicht hier.
4. **Expliziter Status-Check: nur aus `draft`** (**409** sonst).
   *Begründung:* Die Zustandsmaschine (Build 379) behandelt einen
   gleichbleibenden Status als **No-op-Erfolg** — ein 200 auf ein erneutes
   Einreichen wäre im Editor irreführend.
5. `update_report_status(..., 'submitted', ...)`; `EvidenceDbError` /
   `ReportSealedError` → **409**.

**Die Erfolgsantwort nennt die Tragweite:**
> „Der Bericht wurde zur Abnahme freigegeben und ist für Sie nun gesperrt. Nur
> der Lektor oder die Chef-Ermittlerin können ihn zur Nachbesserung zurückgeben."

**Tests** `tests/test_report_submit.py` (SB01–SB06) — **SB06** prüft den
eigentlichen Zweck: nach dem Einreichen ist der Bericht für den Autor **gesperrt**
(Schreibsperre Build 379), Kommentare bleiben möglich.

---

## 3. Nebenbefund (im Code dokumentiert, hier vermerkt)

`context.username` ist der **Beschuldigte** — der Ermittler steht in
**`context.investigator_username`** (Bug 3.1 / Build 117). Beim Schreiben des
Tests aufgefallen; im Test vermerkt.

---

## 4. Regression (run_tests.py)

```
pytest : 1011 passed, 59 skipped, 6 subtests   (1005 + 6)
vitest : 570 passed, 1 skipped, 1 todo (572), 49 Testdateien   (unverändert)
```

---

## 5. Abnahme (per Konsole, bis das Frontend in 382 folgt)

Bericht im Status `draft` öffnen (Lock erwerben), dann POST:
`{action:'submit_report', report_id:<id>, lock_id:<lock>}` → **200** mit
`status='submitted'` und der Tragweiten-Meldung.
Danach schlägt jede Inhaltsänderung fehl (**409**, Schreibsperre); ein
**Kommentar** geht weiterhin. Im Cockpit erscheint der Bericht als „eingereicht"
und kann **freigegeben** oder **zur Nachbesserung zurückgegeben** werden (380).

---

## 6. Nächster Build 382 (Frontend, console-first)

Schaltfläche **„Zur Abnahme freigeben"** im Berichtseditor mit
**Bestätigungsdialog**:
- **(a) Tragweite:** der Bericht wird für den Autor **gesperrt**.
- **(b) Weiterer Prozess:** Abnahme durch die Chef-Ermittlerin, danach
  **Versiegelung**.
- **(c) Rückholmöglichkeit:** **nur** über Lektor oder Chef-Ermittlerin.

**Bewusste Entscheidung, kein versehentlicher Klick** → zweistufige Bestätigung.

---

*Dokument-Ende · Bauplan Build 381 · 2026-07-10*

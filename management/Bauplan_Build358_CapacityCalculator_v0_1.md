# Bauplan Build 358 — Kapazität Teil 3: Berechnung + Lesepfad

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 0**
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11.4. **Basis:** 0.7.357.
**mc:** 2026-07-10.

---

## 1. Ziel

`Kapazität(Person, Zeitraum)` berechnen und read-only bereitstellen. **Keine
Migration.** **Split:** 358 = Calculator + `/api/capacity` · 359 = Cockpit-Sicht.

---

## 2. Rechenmodell (mc)

- **Basis** = Σ je Kalendertag: `0` bei Feiertag (**alle** nicht-gelöschten
  Feiertage zählen, Region nur informativ — Entscheidung 3), sonst die
  Wochentag-Minuten der zum Tag **aktiven** Arbeitszeit-Regel (größtes
  `effective_from ≤ Tag`, nicht gelöscht, `effective_to` offen/`≥ Tag`).
- **Verfügbarkeit** (aktiv, überlappend): `value_minutes` = **Total** des
  Eintrags, anteilig nach Kalendertagen auf die Überlappung umgelegt
  (Entscheidung 1); `value_pct` = Prozent der Basis der Überlappungstage.
- **`netto = max(Basis − Σ Einschränkungen, Σ Garantien)`** — Garantie ist Boden
  (Entscheidung 2); `netto` nie negativ.

---

## 3. Umfang (geliefert)

- **`management/capacity/capacity_calculator.py`** — `CapacityCalculator.compute`
  → `CapacityResult{person_id, period_start/end, days, working_days, basis,
  einschraenkungen, garantie_boden, netto}`. Rein lesend.
- **`management/server/management_app.py`** (geändert): `CAP_CAPACITY =
  "capacity.edit"`; `/api/capacity` (`person_id`/`start`/`end`; 400 bei
  fehlenden/ungültigen Parametern; scope-aware; `CapacityError` → 400).
  **Gating-Hinweis:** kein `capacity.view` im Katalog → Lesepfad bewusst auf
  `capacity.edit` gegatet; eine dedizierte `capacity.view` könnte später per
  Migration ergänzt werden.
- **Tests** `tests/test_capacity_calculator.py` (CC01–CC07, EP01–EP04).

---

## 4. Regression (run_tests.py)

```
pytest : 937 passed, 59 skipped, 3 subtests   (926 + 11)
vitest : 511 passed, 1 skipped, 1 todo (513), 40 Testdateien   (unverändert)
```

---

## 5. Abnahme

Nach Grant `capacity.edit`:
`GET /api/capacity?person_id=2&start=2026-07-06&end=2026-07-10` →
JSON mit `basis`/`einschraenkungen`/`garantie_boden`/`netto`.

---

## 6. Nächster Build

**359 — Cockpit-Sicht Kapazität** (Gantt/Überlast, ECharts; console-first).

---

*Dokument-Ende · Bauplan Build 358 · 2026-07-10*

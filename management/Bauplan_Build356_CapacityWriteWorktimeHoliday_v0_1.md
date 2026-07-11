# Bauplan Build 356 — Kapazität Teil 2a: Schreibpfade Arbeitszeit + Feiertage

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 0**
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11.4 · Muster
`rbac_repo`/`BackupsRepo`. **Basis:** 0.7.355. **mc:** 2026-07-10.

---

## 1. Ziel und Split

Auditierte Schreibpfade für die ersten beiden Kapazitäts-Tabellen. **Split
(mc):** 356 = Arbeitszeit + Feiertage · 357 = Gründe + Verfügbarkeits-Einträge.
**Keine Migration** (schreibt auf m008-Schema aus Build 355).

**Entscheidungen (mc):** 4 Repos; Worktime **append-only** (kein automatisches
`effective_to`-Schließen); Aufteilung in zwei Builds.

---

## 2. Umfang (geliefert)

- **`management/capacity/capacity_errors.py`** — `CapacityError`.
- **`management/capacity/worktime_repo.py`** — `WorktimeRepo`:
  `set_worktime(...)` → `WORKTIME_SET`, **append-only** neue datierte Zeile
  (`audit_seq == Beleg-seq`); Validierung Minuten ∈ [0, 1440]. `list_worktime`.
- **`management/capacity/holiday_repo.py`** — `HolidayRepo`:
  `add_holiday` → `HOLIDAY_ADDED` (Duplikat-Guard aktive `(day, region)`);
  `remove_holiday` → `HOLIDAY_REMOVED` (**Soft-Delete** `deleted_at`; nicht
  vorhanden → `CapacityError`); `list_holidays`.
  *Hinweis:* Das Schema führt bewusst keine `delete_audit_seq`-Spalte (§11.4);
  der Entfernungs-Beleg steht im `audit_log` mit `target_id=holiday_id`.
- **`management/capacity/capacity_admin.py`** — CLI `set-worktime`/`list-worktime`/
  `add-holiday`/`remove-holiday`/`list-holidays` (`main(argv)` testbar).
- **Tests** `tests/test_capacity_worktime_holiday.py` (WT01–WT03, HL01–HL04, CL01).

---

## 3. Regression (run_tests.py)

```
pytest : 918 passed, 59 skipped, 3 subtests   (910 + 8)
vitest : 511 passed, 1 skipped, 1 todo (513), 40 Testdateien   (unverändert)
```

---

## 4. Nutzung

```
python -m management.capacity.capacity_admin set-worktime --person h002 \
  --from 2026-07-01 --mon 480 --tue 480 --wed 480 --thu 480 --fri 300 --actor h0a2898
python -m management.capacity.capacity_admin add-holiday --day 2026-10-03 \
  --label "Tag der Deutschen Einheit" --actor h0a2898
python -m management.capacity.capacity_admin list-holidays
```

---

## 5. Nächste Builds

- **357 — Gründe + Verfügbarkeit:** `ReasonRepo` + `AvailabilityRepo` (+CLI).
- **358 — Berechnung:** `Kapazität(Zeitraum)`.
- **359 — Cockpit-Sicht:** Gantt/Überlast.

---

*Dokument-Ende · Bauplan Build 356 · 2026-07-10*

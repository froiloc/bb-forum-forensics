# Bauplan Build 355 — Kapazität Teil 1: Schema-Migration m008 + Audit-Vokabular

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 0**
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11.4 · m005-Prinzip.
**Basis:** 0.7.354. **mc:** 2026-07-10.

---

## 1. Ziel und Split

Datenbasis für Kapazität/Prognose/Gantt/Überlast — **Schema zuerst**. Dieser
Build liefert nur die additive Migration m008 (vier Tabellen) und das
Audit-Vokabular. **Kein Schreibpfad, keine Berechnung** (folgen in 356/357).

**Split (mc):** 355 Schema+Audit · 356 Repos + `capacity_admin`-CLL · 357
Kapazitäts-Berechnung + Lesepfad · 358 Cockpit-Sicht (Gantt/Überlast, ECharts).

---

## 2. Umfang (geliefert)

- **`management/migrations/coordinator/m008_capacity.py`** (`VERSION=8`,
  `KIND="additive"`): vier Tabellen exakt nach §11.4 —
  - `person_worktime` (Wochentag-Minuten, `effective_from/to`, Soft-Delete),
  - `holiday` (gilt für alle, `region`-gescopt),
  - `availability_reason` (Supervisor-erweiterbarer Grund-Katalog),
  - `availability_entry` (Garantie/Einschränkung je Person/Zeitraum).
  - **CHECKs:** `kind IN ('garantie','einschraenkung')`;
    `(value_pct IS NULL) <> (value_minutes IS NULL)` (genau eines gesetzt).
  - Indizes `ix_worktime_person` / `ix_holiday_day` / `ix_availability_person`.
  - **`audit_seq NOT NULL → audit_log(seq)`** in allen vier Tabellen (mc 2).
  - **Soft-Delete** `deleted_at` (append-only Historie).
  - **Tabellen starten leer** — auch `availability_reason` (Basis-Gründe per CLI
    in 356; kein Migrations-Seed, m005-Prinzip).
  - Idempotent (`IF NOT EXISTS` + Guard), Inline-Verifikation.
- **`management/audit/event_types.py`**: sechs Kapazitäts-Aktionen aktiviert + in
  `ALL` (append-only): `WORKTIME_SET`, `HOLIDAY_ADDED`, `HOLIDAY_REMOVED`,
  `AVAILABILITY_REASON_ADDED`, `AVAILABILITY_SET`, `AVAILABILITY_REMOVED`
  (Soft-Delete = eigener `_REMOVED`-Beleg).
- **Tests** `tests/test_capacity_schema.py` (CP01–CP05) +
  `tests/test_management_dashboard.py` (d01-Migrationsliste um 8 ergänzt).

---

## 3. Regression (run_tests.py)

```
pytest : 910 passed, 59 skipped, 3 subtests   (905 + 5)
vitest : 511 passed, 1 skipped, 1 todo (513), 40 Testdateien   (unverändert)
```

---

## 4. Migration / Deploy

`m008` ist **additiv** (kein Datenverlust); wird beim nächsten Migrationslauf
automatisch angewandt (`MIGRATION_APPLIED` in der Hash-Kette). Nur Schema — noch
keine Zeilen (die entstehen ausschließlich über die auditierten Schreibpfade in
356).

---

## 5. Nächste Builds

- **356 — Repos + CLI:** `WorktimeRepo`/`HolidayRepo`/`AvailabilityRepo`
  (auditierte Schreibpfade, Soft-Delete) + `capacity_admin`-CLI.
- **357 — Berechnung:** `Kapazität(Zeitraum)` = Σ Arbeitstag-Minuten − Einschr.
  im Rahmen der Garantien + Lesepfad.
- **358 — Cockpit-Sicht:** Gantt/Überlast (ECharts).

---

*Dokument-Ende · Bauplan Build 355 · 2026-07-10*

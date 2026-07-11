# Bauplan Build 363 — Persönliche Sichten Teil 1: Backends (Meine Aufträge + Meine Historie)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 1**
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11 · `DashboardRepo`/
`audit_log`-Lesepfade. **Basis:** 0.7.362. **mc:** 2026-07-10.

---

## 1. Ziel und Split

Zwei persönliche Ermittler-Sichten (Backend). **Split (mc): Backend und Frontend
künftig immer getrennt** → Frontends = Build 364. **Keine Migration.**

**Entscheidungen (mc):** „Meine Historie" **kombiniert** (eigene Aktionen +
Historie der eigenen Fälle); beide Sichten liefern **immer nur die eigenen**
Daten (Cap ist das Tor).

---

## 2. Umfang (geliefert)

- **`management/personal/myhistory_repo.py`** — `MyHistoryRepo.my_history(
  person_id, limit)`: kombinierte Historie aus `audit_log` — (a) eigene Aktionen
  (`actor_id == person`) **oder** (b) Fall-Ereignisse (`target_type='case'`) zu
  den aktuell zugewiesenen Fällen (`cases.assigned_to == person`; Fall-Adressierung
  über `target_id = str(user_id)`). Vereinigung, neueste zuerst, limitiert
  (Default 200 / Max 1000); je Eintrag `mine`/`mycase`.
- **`management/server/management_app.py`** (geändert): `CAP_MYCASES`/
  `CAP_MYHISTORY`; Modul-Helfer `_case_overview_item` (DRY; `_overview` nutzt ihn
  jetzt auch); `/api/mycases` → `_mycases` (eigene zugewiesene Fälle via
  `DashboardRepo`), `/api/myhistory` → `_myhistory` (`?limit=N`). read-only,
  personenbezogen.
- **Tests** `tests/test_personal_views.py` (MC01–MC02, MH01–MH02).

---

## 3. Regression (run_tests.py)

```
pytest : 951 passed, 59 skipped, 3 subtests   (947 + 4)
vitest : 519 passed, 1 skipped, 1 todo (521), 41 Testdateien   (unverändert)
```

---

## 4. Abnahme

Nach Grant `mycases.view`/`myhistory.view` (investigator, scope eigene):
`GET /api/mycases` → eigene Fälle; `GET /api/myhistory[?limit=N]` → kombinierte
Zeitleiste (`mine`/`mycase` markiert).

---

## 5. Nächster Build (364, Frontends, console-first)

`cockpit_mycases.js` + `cockpit_myhistory.js` (Tabulator) + `cockpit.js`/
`cockpit.html`-Verdrahtung + SSE-Reload; vitest für die reine Aufbereitung.

---

*Dokument-Ende · Bauplan Build 363 · 2026-07-10*

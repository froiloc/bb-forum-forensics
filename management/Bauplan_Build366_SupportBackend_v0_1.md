# Bauplan Build 366 — Support-Historie Teil 1: Backend `/api/support`

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 1**
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11 · `SupportOverviewRepo`
(vorhanden). **Basis:** 0.7.365. **mc:** 2026-07-10.

---

## 1. Ziel und Split

Support-Historie im Cockpit — Backend. **Keine Migration.** **Split (mc):** 366
Backend · 367 Frontend (zwei Listen + Mini-Modal, console-first).

**Entscheidungen (mc):** `SupportOverviewRepo` wiederverwenden; **beide
Perspektiven** als Markierungen (`mine_as_supporter`, `on_my_case`); **volle
Serialisierung**.

---

## 2. Umfang (geliefert)

- **`management/server/management_app.py`** (geändert): `CAP_SUPPORT =
  "support_history.view"`; `/api/support` → `_support`:
  - `SupportOverviewRepo.list_support_sessions()` (belegbasiert aus `audit_log`,
    inkl. `status`/`anomaly`/Beleg-seq),
  - je Sitzung `mine_as_supporter` (`supporter_id == ich`) + `on_my_case`
    (`user_id` ∈ eigene Fälle),
  - scope `alle` → alle; `eigene` → nur Sitzungen mit ≥1 Markierung,
  - volle `asdict`-Serialisierung + Marker; `SupportOverviewSchemaError` → 503.
  - Antwort `{scope, count, sessions:[...]}`.
- **Tests** `tests/test_support_view.py` (SV01–SV03).

---

## 3. Regression (run_tests.py)

```
pytest : 956 passed, 59 skipped, 3 subtests   (953 + 3)
vitest : 534 passed, 1 skipped, 1 todo (536), 44 Testdateien   (unverändert)
```

---

## 4. Abnahme

Nach Grant `support_history.view`: `GET /api/support` → `{sessions:[{… voller
Record …, mine_as_supporter, on_my_case}]}`. Supervisor (scope alle) sieht alle;
investigator (scope eigene) nur eigene / an eigenen Fällen.

---

## 5. Nächster Build (367, Frontend, console-first)

`cockpit_support.js` — **zwei getrennte Listen** (Meine Sitzungen / An meinen
Fällen) über die Marker, plus **Mini-Modal** zur schönen Detail-/JSON-Darstellung
eines Records; `cockpit.js`/`cockpit.html`-Verdrahtung + SSE-Reload.

---

*Dokument-Ende · Bauplan Build 366 · 2026-07-10*

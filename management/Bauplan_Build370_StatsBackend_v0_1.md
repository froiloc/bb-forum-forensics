# Bauplan Build 370 — Statistiken Teil 1: Backend `/api/stats` + StatsRepo

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 1**
**Autoritativ:** `Ideen_Verwaltungswerkzeug_konsolidiert.md` §2.4 · `DashboardRepo`
+ `audit_log`. **Basis:** 0.7.369. **mc:** 2026-07-10.

---

## 1. Ziel und Split

Auswertungs-/Statistik-Sicht (StA / Führung) — Backend. **Keine Migration.**
**Split (mc):** 370 Backend · 371 Frontend (Reiterstruktur/Diagramme).

**Entscheidungen (mc):** Basis-Kennzahlen **+ Durchsatz über Zeit** im ersten
Schwung; **CSV und JSON** als Backend-Export; `alle` umfasst zusätzlich `eigene`.

---

## 2. Umfang (geliefert)

- **`management/stats/stats_repo.py`** (`StatsRepo`): `compute([person_id])` →
  `totals`, `by_status`, `by_priority`, `by_ampel`, `by_assignee`,
  `throughput_by_day` (Fall-Ereignisse je Tag aus `audit_log` = Durchsatz),
  `scope`, `generated_at`. `to_csv(stats)` → Langformat
  `abschnitt,schluessel,wert` (Python-`csv`, sichere Escapes).
- **`management/server/management_app.py`** (geändert): `Response.csv`;
  `CAP_STATS = "stats.export_sta"`; `/api/stats` → `_stats` (403 ohne Cap;
  scope-aware; `format=json` [Vorgabe] / `format=csv`). Download-Dateiname macht
  das Frontend (Blob); gerichtsfester StA-Export bleibt späteres Subsystem.
- **Tests** `tests/test_stats_view.py` (ST01–ST05).

---

## 3. Regression (run_tests.py)

```
pytest : 965 passed, 59 skipped, 3 subtests   (960 + 5)
vitest : 545 passed, 1 skipped, 1 todo (547), 46 Testdateien   (unverändert)
```

---

## 4. Abnahme

Nach Grant `stats.export_sta`: `GET /api/stats` → Matrizen + Durchsatz;
`GET /api/stats?format=csv` → `text/csv`-Langformat. Supervisor (alle) alle
Fälle; investigator (eigene) nur eigene.

---

## 5. Nächster Build (371, Frontend, console-first)

`cockpit_stats.js` mit **Reiterstruktur** (Tabs) zwischen Tabellen/Diagrammen
(ECharts: Status-/Prioritäts-/Ampel-Verteilungen, Durchsatz-Zeitreihe;
Tabulator: `by_assignee`) + Download-Buttons (CSV via Endpunkt, JSON via
In-Memory-Blob) + Verdrahtung/SSE.

---

*Dokument-Ende · Bauplan Build 370 · 2026-07-10*

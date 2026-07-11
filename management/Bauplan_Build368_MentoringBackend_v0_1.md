# Bauplan Build 368 — Ermittler-Betreuung Teil 1: Backend `/api/mentoring` (Live)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 1**
**Autoritativ:** `Ideen_Verwaltungswerkzeug_konsolidiert.md` §2.12 („laufende
Support-Sitzungen begleiten") · `support_sessions`-Live-Tabelle ·
`DEFAULT_SUPPORT_STALE_SEC`. **Basis:** 0.7.367. **mc:** 2026-07-10.

---

## 1. Ziel und Split

Ermittler-Betreuung als **Live-Sicht** der aktuell **laufenden** Support-
Sitzungen (nicht Historie). **Keine Migration.** **Split (mc):** 368 Backend ·
369 Frontend (mit periodischem Refresh, console-first).

**Entscheidungen (mc):** Live-Sicht; Quelle = Live-Tabelle `support_sessions`
(neuer `list_running()`-Reader); scope `eigene` = nur eigene laufende Sitzungen;
stale zuerst.

---

## 2. Umfang (geliefert)

- **`management/support_sessions/support_sessions_repo.py`** (geändert): NEU
  `list_running()` — alle Sitzungen mit `ended_at IS NULL`, fallübergreifend,
  `LEFT JOIN person` (Supporter) + `cases` (username); read-only, keine
  Stale-Filterung.
- **`management/server/management_app.py`** (geändert): `CAP_MENTORING =
  "mentoring.view"`; `/api/mentoring` → `_mentoring`: annotiert je Sitzung
  `heartbeat_age_sec`, `started_ago_sec`, `live` (Alter ≤ `stale_sec` = 30 s);
  scope `alle` → alle laufenden, `eigene` → nur `supporter_id == ich`;
  Sortierung stale-zuerst. Antwort `{scope, stale_sec, count, sessions:[...]}`.
- **Tests** `tests/test_mentoring_view.py` (MN01–MN04).

---

## 3. Regression (run_tests.py)

```
pytest : 960 passed, 59 skipped, 3 subtests   (956 + 4)
vitest : 540 passed, 1 skipped, 1 todo (542), 45 Testdateien   (unverändert)
```

---

## 4. Abnahme

Nach Grant `mentoring.view`: `GET /api/mentoring` → laufende Sitzungen (stale
zuerst) mit `live`/`heartbeat_age_sec`. Supervisor (alle) alle; support (eigene)
nur eigene.

---

## 5. Nächster Build (369, Frontend, console-first)

`cockpit_mentoring.js` (Tabulator, Live/Stale-Ampel, Laufzeit) + **periodischer
Refresh** (Heartbeats sind nicht auditiert → SSE allein reicht nicht; Session-
Start/-Ende bleiben SSE-getrieben) + `cockpit.js`/`cockpit.html`-Verdrahtung.

---

*Dokument-Ende · Bauplan Build 368 · 2026-07-10*

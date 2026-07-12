# Bauplan Build 383 — Fall-Autodetektion (Backend + CLI)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Basis:** 0.7.382 · **mc:** 2026-07-10 · **Migration:** keine.

---

## 1. Was einen Fall definiert (mc)

Ein Fall **existiert**, sobald der Prepper seine **`forensic_<uid>.db`** geliefert
hat — **unabhängig** davon, ob schon jemand daran gearbeitet hat.
`evidence_<uid>.db` und `assets_<uid>.db` entstehen erst durch die
Ermittlungsarbeit und sind **kein Existenzkriterium**, sondern nur **Arbeitsstand**.

Der **Benutzername** kommt **autoritativ** aus `forensic_<uid>.db` →
`uid_profile` (NOT NULL, direkt aus `users.username`) — er wird **nicht geraten**.

---

## 2. Vier Zustände

| Zustand | Bedeutung |
|---|---|
| `ok` | erfasst **und** `forensic_<uid>.db` vorhanden |
| **`neu`** | DB da, **nicht** erfasst → **aufnehmbar** |
| **`vermisst`** | erfasst, aber DB **fehlt** → **melden!** |
| **`unlesbar`** | DB da, aber nicht lesbar / `uid_profile` fehlt → **melden!** |

**Grundregel 1:** `vermisst` und `unlesbar` werden **nie still übersprungen**.
Ein vermisster Fall wird **bewusst nicht** in der Fallakte verändert (kein
stiller Eingriff in Ermittlungsdaten, `mc`) — er wird **gemeldet**.

---

## 3. Umfang (geliefert)

- **`case_detector.py`** (`CaseDetector`, read-only) — der Abgleich oben, je Fall
  zusätzlich `has_evidence_db` / `has_assets_db` (Arbeitsstand).
- **`case_importer.py`** (`CaseImporter`) — nimmt `neu` **auditiert** auf:
  ausschließlich über `CasesRepo.create_case` → `CoordinatorWriter` → **Beleg
  `case_created` je Fall**. Nicht aufnehmbare Fälle werden **mit Grund** als
  `skipped` gemeldet; ein Fehlschlag bricht den Rest nicht ab.
- **`management_app.py`**: `GET /api/cases/detect` (rein lesend) ·
  `POST /api/cases/import` (auditiert; `user_ids` **oder** `all: true`). Beide
  `assignment.edit`, Scope `alle`. Neue Injektionen `forensic_dir` / `assets_dir`.
- **`case_detect.py`** (CLI): `python -m management.cases.case_detect`
  – ohne `--auto`: **nur Bericht** (rein lesend)
  – mit `--auto --actor <KENNUNG>`: nimmt alle `neu` auditiert auf (für Skripte;
  Normalfall bleibt der Knopf im Cockpit). `--auto` **ohne** `--actor` ist ein
  Fehler — der Beleg braucht einen Handelnden.
  **Exit:** 0 = in Ordnung · **2 = `vermisst`/`unlesbar`** · 1 = Aufruffehler.
- **Tests** `tests/test_case_detect.py` (CD01–CD07).

---

## 4. Regression (run_tests.py)

```
pytest : 1018 passed, 59 skipped, 6 subtests   (1011 + 7)
vitest : 576 passed, 1 skipped, 1 todo (578), 50 Testdateien   (unverändert)
```

---

## 5. Abnahme

**Server neu starten.**
1. `python -m management.cases.case_detect` → listet alle Fälle mit Zustand.
2. `GET /api/cases/detect` → dasselbe als JSON.
3. `POST /api/cases/import {user_ids:[…]}` (mit `X-AIW-Token`) → nimmt auf;
   jeder Fall bekommt einen **`case_created`-Beleg**.
4. **Gegenprobe:** eine `forensic_<uid>.db` vorübergehend umbenennen → der Fall
   erscheint als **VERMISST**, das CLI endet mit **Exit 2**, und die **Fallakte
   bleibt unverändert**.

---

## 6. Nächster Build 384 (Frontend, console-first)

Cockpit-Sicht **„Fall-Erkennung"**: Tabelle mit den vier Zuständen, Filter,
Auswahl + Knopf **„Ausgewählte aufnehmen"** (mit Bestätigung), deutliche Warnung
bei `vermisst`/`unlesbar`.

---

*Dokument-Ende · Bauplan Build 383 · 2026-07-10*

# Bauplan Build 374 — Berichts-Abnahme Teil 1: Lesepfad + WAL-sicherer Scan-Cache

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 1**
**Autoritativ:** `db/evidence_db.py` (`reports`, `report_approvals`) ·
`core/config_loader.py` (`paths.evidence_db_dir`). **Basis:** 0.7.373.
**mc:** 2026-07-10. **Migration:** **m009** (additiv).

---

## 1. Ausgangslage und Aufteilung

Berichte liegen **nicht** in `coordinator.db`, sondern **je Fall** in
`evidence_<uid>.db`. Der Management-Server liest damit erstmals **quer über die
Ermittler-DBs** — ausschließlich `mode=ro`.

**Aufteilung (mc):** **374** Scan/Übersicht (lesend) · **375** Frontend ·
**376** Versiegelung (`approved_reports.db`, Inhaltshash, `POST
/api/report/approve`) · **377** Schreibsperre im Ermittler-Webserver.

---

## 2. Zwei gemessene Befunde, die das Design bestimmen

**(a) Die WAL-Falle.** Ein `UPDATE` im WAL-Modus ändert `mtime` **und** Größe der
`.db`-Datei **nicht** — nur die `-wal`-Datei. Ein Cache, der nur die `.db` statet,
würde geänderte Berichte **still übersehen** (Grundregel 1). → `-wal` **muss** in
den Fingerabdruck.

**(b) Die `-shm`-Falle.** Die `-shm`-Datei (abgeleiteter Shared-Memory-Index,
enthält keine Daten) ändert sich schon bei einem **reinen Lesezugriff**. Mit
`-shm` im Abdruck **invalidiert der Cache sich selbst** — unser eigenes Lesen
macht ihn ungültig, jeder Scan läse alles neu. → `-shm` bleibt **draußen**.
Gemessen: ohne `-shm` ist der Abdruck lesestabil **und** erkennt echte Änderungen.

**Fingerabdruck:** `.db:size:mtime_ns|-wal:size:mtime_ns` (fehlende Datei → `-`).

**Drittens:** Der Abdruck wird **nach** dem Lesen gebildet — der *erste*
Lesezugriff legt die `-wal`-Datei erst an; ein vorher gebildeter Abdruck wäre
sofort wieder ungültig (Cache wirkungslos).

---

## 3. Umfang (geliefert)

- **m009** `evidence_scan_cache` (user_id, fingerprint, reports_json,
  scanned_at, error). **Kein `audit_seq`**: der Cache enthält keine
  Ermittlungsergebnisse, sondern jederzeit neu erzeugbare Metadaten — sonst
  würde jeder Seitenaufruf das Audit-Log fluten.
- **`EvidenceScanner`** — findet `evidence_<uid>.db` (Cross-Evidence
  `evidence_<uid>_<iid>.db` wird bewusst ignoriert), bildet den Abdruck.
- **`ReportsRepo.list_reports(force=False)`** → `{evidence_dir, case_db_count,
  rescanned, count, reports[], errors[], cases_without_db[]}`. Cache-Treffer →
  evidence-DB wird **gar nicht geöffnet**. **Grundregel 1:** defekte DBs werden
  **gemeldet** (`errors[]`), nicht übersprungen; Fälle ohne DB erscheinen in
  `cases_without_db[]`.
- **`GET /api/reports`** (`reports.review`, `?force=1`), scope-aware.
  `ManagementApp(..., evidence_dir=…)` (injizierbar; sonst aus `config.yaml`).
- **Tests** `tests/test_reports_scan.py` (RS01–RS08) · `d01`-Migrationsliste → 1..9.

---

## 4. Messung (Grundlage der Cache-Entscheidung)

300 evidence-DBs vollständig lesen = **161 ms** (0,54 ms je DB); stat-Vorfilter =
2 ms. Der Cache ist ein **Beschleuniger, kein Fundament** — die Korrektheit hängt
nie an ihm. In PROD (Windows/UNC/SMB) kann `mtime` grob/verzögert sein; ein
Fehltreffer kostet nur Zeit. Für **Beweisrelevantes** (Siegel, Build 376) zählt
**niemals** `mtime`, sondern ausschließlich der **Inhaltshash** (Konvention aus
`core/startup_checks.py`).

---

## 5. Regression (run_tests.py)

```
pytest : 981 passed, 59 skipped, 3 subtests   (973 + 8)
vitest : 557 passed, 1 skipped, 1 todo (559), 48 Testdateien   (unverändert)
```

---

## 6. Abnahme

**Server neu starten** (m009 läuft beim Start). Nach Grant `reports.review`:
`GET /api/reports` → Berichte aller Fälle mit Status; `rescanned` zeigt, wie
viele DBs tatsächlich gelesen wurden (**zweiter Aufruf: 0**).
`GET /api/reports?force=1` → Vollscan.

---

*Dokument-Ende · Bauplan Build 374 · 2026-07-10*

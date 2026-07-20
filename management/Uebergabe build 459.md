# Übergabe — Stand nach Build 459 (Welle 2, AP-2B/2C/2D/2F geliefert, AP-2G angearbeitet)

**Autoritativ:** mc · **Datum:** 2026-07-19 · **Modul:** `aiw_webserver` **Basis-Commit vor der Session:** `ae7b405` (Version 0.7.439)

Diese Session hat den Arbeitspaket-Plan `management/Bauplan_Baustelle7_Wellen2_3_Arbeitspakete_v0_1.md` begonnen und **20 Builds (440–459)** geliefert. Jeder Build: volle Regression grün,
ZIP mit MD5 an mc übergeben, lokaler Commit (Push durch mc — PAT ist read-only).

## 1. Was in dieser Session geliefert wurde

**AP-2B — Export-Vereinheitlichung (440–443):** Export-Framework (checksum/envelope),
Fallstatus→Excel (openpyxl), Retrofit der Sichten-Exporte, StA-Ausschleus-Verzeichnis. **Deploy:** `openpyxl` in der VM bereitstellen (in `requirements.txt` vermerkt).

**AP-2C — Statistik-Ausbau (444–448):** Kennzahlen-Glossar, StA-Berichtsgenerator (HTML+PDF),
Prognose (3 Szenarien), Gantt-Read-Model, **Frontend** Prognose-&-Gantt-Sicht + Endpunkte `/api/forecast`, `/api/gantt`.

**AP-2D — Annotations-Tortenstatistik (449–450):** Aggregat-Repo (evidence read-only) + **Frontend** Torten-Sicht + Endpunkt `/api/annotation-stats`.

**AP-2F — Steuerung/Eskalation (451–453):** aktive Überlastwarnung, Nächstbeste-Aktion-
Warteschlange, Eskalationsregeln (alle rein lesend, belegt).

**AP-2G — Betrieb/Governance (454–459, ANGEARBEITET):**

- 454: Speicher-/`data/`-Übersicht (`management/ops/storage_overview.py`) — Fremdforum-Kandidaten,
  Low-Disk-Alarm.
- 455: Übergabe-Protokoll bei Fall-Umverteilung (`cases/handover_log.py`, aus audit_log).
- 456: Aufbewahrungs-/Löschfristen-Übersicht (`ops/retention.py`, löscht NICHTS).
- 457: **Frontend** Kommandopalette (Strg-K, Sicht-Suche; `cockpit_palette.js`).
- 458: Fall-/Nutzer-Such-Endpunkt `GET /api/search` (`cases/case_search_repo.py`, `dashboard.view`).
- 459: **Frontend** Paletten-Fall-Sprung (Fall-Suche + `focusCase` in der Übersicht).

## 2. Regressionsstand nach Build 459 (Cloud)

- pytest: **1480 passed / 49 skipped** (`test_editor_renderer.py` ausgeklammert — Py-3.11-Artefakt).
- vitest: **867 passed / 1 skip / 1 todo** (73 Dateien).
- `py_compile` / `node --check` OK.

## 3. Offene Punkte / Nachläufe

1. **Live-Browser-Verifikation in der VM** für die neuen Frontend-Sichten: `planung` (448), `annostats` (450), Kommandopalette + Fall-Sprung (457/459). Code + Unit-/Regressionstests grün.
2. **Kein neues Recht/keine Migration** in AP-2B/2C/2D/2F/2G — neue Sichten hängen an `stats.export_sta` bzw. `dashboard.view`.
3. **Eskalation (453) ist nur Auswertung** — auditiertes Handeln (Benachrichtigung/F3-Zustand)
   ist ein späterer schreibender Build.
4. **Neue `config.yaml`-Schwellen** (optional, Vorgaben greifen ohne Eintrag): `workload.overload.*` (451), `escalation.*` (453), `retention.*` (456).

## 4. Noch offene Arbeitspakete (aus dem Plan)

- **AP-2A** Identität/Kreuzbezug (Ideen 6–11) — **mit Migration**, größtes Paket (~7 Builds).
- **AP-2E** Audit-/Revisions-Explorer (Idee 24) — rein lesend (~2 Builds).
- **AP-2G Rest:** Fremdforum-Promotion-Zustandsmaschine + externe Fallfreigabe (beide **schreibend/
  auditiert**), LKÄ-Distribution, Onboarding/Offboarding.
- **Welle 3** komplett (Fristen-Monitor, Metriken/QS, Volltextsuche 🔴, Feedback/Bugtracker …).

## 5. Arbeitsweise (unverändert)

Lieferung als `.zip` mit `aiw_webserver/`-Präfix, nur geänderte Dateien + `build.json`, MD5 je
Datei; vor jedem Build MD5-Handshake der zu ändernden Bestandsdateien. `journal_mode=delete`, `BEGIN IMMEDIATE`, `mode=ro` fürs Lesen. Migrationsvorbehalt für `evidence_/forensic_/assets_<uid>.db`.
Nächster Build: **460**.

## 6. Session-Ende — To-dos für mc

- Die **19 lokalen Commits** (440–459) prüfen, dann selbst pushen.
- Die 20 ZIPs in der VM einspielen; `python run_tests.py` fahren.
- **GitHub-PAT widerrufen** unter `github.com/settings/personal-access-tokens`.

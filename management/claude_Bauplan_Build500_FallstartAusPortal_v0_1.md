# Bauplan Build 500 — Fallstart aus dem Management-Portal

- **Modul:** aiw_webserver
- **Build:** 500 (Basis: 499 / v0.8.499)
- **Datum:** 2026-07-22
- **Beleg:** Projektgespraech 2026-07-22 (Bedarf: „Mitarbeiter sollen aus dem
  Management-Portal einen ihnen zugewiesenen Fall per Webserver starten koennen.")
- **Migrationsklasse:** **migrationsneutral** — kein Schema-/DB-Eingriff, kein
  neuer EventType, keine Aenderung an den migrationssensiblen Datenbanken
  (`evidence_/forensic_/assets_<uid>.db`). Reiner Lesezugriff auf `coordinator.db`
  (mode=ro) plus Prozess-Spawn.

## 1. Ausgangslage (Belege aus dem Code)

- Der **Forensik-Server** (`main.py`) wird pro Fall gestartet, heute ueber
  `start.bat` bzw. manuell:
  `main.py --mode cli --subject-id <id> --auto-port --open-browser`
  (Beleg: `main.py` Kopf, `start.bat`). Er waehlt selbst den Port (`--auto-port`)
  und oeffnet selbst den Browser (`--open-browser`).
- Das **Management-Portal** (`management.py`, `127.0.0.1:8090`) zeigt unter
  „Meine Auftraege" (`/api/mycases` → `cockpit_mycases.js`) die dem Aufrufer
  zugewiesenen Faelle (Filter `assigned_to == person_id`, Beleg
  `management_app.py::_mycases`). Bisher **ohne** Aktionsflaeche.
- Beide Server laufen in derselben Windows-VM. Es existierte **keine** Bruecke,
  die aus dem Portal heraus den Forensik-Server startet.

## 2. Grundsatzentscheidungen (mc 2026-07-22, in der Session festgelegt)

- **(E1) Start-Mechanik:** Das Portal startet `main.py` als **losgeloesten
  Subprozess** in derselben VM. Interpreter-Aufloesung gespiegelt aus `start.bat`
  (portable `..\Python\python.exe` → `sys.executable` → `python`). Aufruf mit
  `--auto-port --open-browser` (Server zuerst, dann Browser — Reihenfolge
  garantiert).
- **(E2) Zugriffsumfang:** **Nur eigene zugewiesene Faelle.** Tor ist die
  bestehende Capability `mycases.view`; zusaetzlich **serverseitige
  Eigentuemerpruefung** `cases.assigned_to == person_id`. Fremde Faelle → 403.
- **(E3) Fehlerpolitik:** **Nur starten, Fehler von `main.py` melden.** Keine
  Vorpruefung der fallspezifischen DBs, kein Doppelstart-Schutz. **Startzeit**-
  Fehler (fehlender Interpreter/`main.py`, OS-Fehler beim Spawn) werden als
  klare HTTP-500-Antwort sichtbar; **Laufzeit**-Fehler von `main.py`
  (z. B. fehlende DB) laufen in dessen harten Abbruch **im losgeloesten Prozess**
  und sind fuer das Portal nicht sichtbar (dokumentierter Tradeoff aus E3).

## 3. Umsetzung

### 3.1 Backend
- **Neu `management/cases/case_launcher.py`** — gekapselte Klasse `CaseLauncher`
  (Grundregel 10: eine Klasse je Datei). `build_command()`, `launch()`,
  `resolve_python()`; Prozess-Spawn ueber injizierbaren `spawn`-Parameter
  (Tests ohne echten Server). Plattformabhaengiger DETACHED-Start gespiegelt aus
  `core/browser_launcher.py`. Fehler → `CaseLaunchError`.
- **`management/server/management_app.py`** —
  - Import `CaseLauncher/CaseLaunchError`; Konstruktor-Parameter
    `case_launcher` (injizierbar, Default: echter `CaseLauncher`).
  - `dispatch_write`: neue Route `POST /api/case/launch` → `_case_launch`.
  - `_case_launch`: Cap `mycases.view` (Tor) → Existenz + Eigentuemerpruefung
    (mode=ro) → `CaseLauncher.launch()`. Antworten: 200 (ok/launched/pid),
    403 `not_owner`, 400 `unknown_case`, 403 (fehlende Cap), 500 `launch_failed`.
    **Kein DB-Schreibzugriff.**

### 3.2 Frontend (Projekt-JS-Gebote: IIFE, Debug-Log, Kommentare, Kapselung)
- **`cockpit_mycases.js`** — Aktionsspalte „Fall starten" (echtes `<button>`,
  kein innerHTML) via `actionColumn(onLaunch)`; Spalte erscheint nur mit
  `onLaunch`. Rueckmeldebanner (`opts.pendingMsg`, `is-ok`/`is-error`). Neue
  reine Funktion `columnsFor()` fuer die Testbarkeit.
- **`cockpit.js`** — `loadMyCases(mainEl, opts)` reicht `onLaunch` durch:
  `postJson('/api/case/launch', {subject_id})`; Erfolg/Fehler laden die Sicht
  mit `pendingMsg` neu (gleiches Muster wie die Notizen-Sicht).
- **`cockpit.css`** — scoped Stil `.aiw-mycases-btn` / `.aiw-mycases-banner`
  (kein globales `.aiw-btn`, analog `.aiw-cases-*`).

### 3.3 Tests (Grundregel 3)
- **Neu `tests/test_case_launch.py`** — CL01–CL06 (CaseLauncher-Einheit) und
  EP01–EP06 (Endpoint mit injiziertem Fake-Launcher: Eigentuemer 200, fremd 403,
  unbekannt 400, ohne Cap 403, Startzeitfehler 500, kein DB-Schreibzugriff).
- **`tests/unit/test_cockpit_mycases.test.js`** — MYC06–MYC09 (columnsFor,
  Button-Formatter + Klick, Aktionsspalte in Tabulator-Optionen, Banner).

## 4. Bewusst NICHT umgesetzt (nachruestbar, kein stiller Verzicht)

- **Audit-Beleg des Starts** in `coordinator.db`: bewusst ausgelassen, um
  migrationsneutral zu bleiben und E2/E3 minimal zu halten. Konsistent damit,
  dass auch der `start.bat`-Start nicht auditiert wird. Als eigene Entscheidung
  spaeter nachruestbar (neuer EventType `CASE_LAUNCHED` + Schreibpfad).
- **Vorpruefung fallspezifischer DBs** und **Doppelstart-Schutz** (E3).

## 5. Verifikation (in dieser Session)

- `ast.parse` (Py 3.13) fuer alle geaenderten `.py` OK; `node --check` fuer alle
  `.js` OK.
- **Volle Python-Suite (Py 3.13): 1672 passed, 61 skipped, 6 subtests**
  (Basis 499: 1660 → +12 durch `test_case_launch.py`).
- **Volle vitest-Suite: 1032 passed, 86 Dateien** (Basis 499: 1028 → +4 durch
  MYC06–09).

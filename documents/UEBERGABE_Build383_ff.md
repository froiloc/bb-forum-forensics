# ÜBERGABE — Stand Build 383 (Ende Session 2026-07-10/11)

**Für:** Fortsetzung in einem frischen Chat
**Repository-Stand bei Übergabe:** `froiloc/bb-forum-forensics` @ **0.7.383**
(Build 383 committet/gepusht — bitte beim Start verifizieren)
**Erstellt:** 2026-07-11

---

## 0. Erster Schritt im neuen Chat

```
cd /home/claude
git clone -b master https://<token>@github.com/froiloc/bb-forum-forensics.git aiw_webserver
git -C aiw_webserver log --oneline -1
python3 -c "import json;print(json.load(open('aiw_webserver/build.json'))['version'])"
cd aiw_webserver && npm install --no-audit --no-fund      # jsdom fehlt im frischen Klon
```

**Erwartet:** `0.7.383`. Der Prepper (`bb-forum-forensic-sqlite-prepper`) wurde in
dieser Session **nicht** angefasst (Stand v0.1.110).

**Regressionsbasis (Stand 383):** `python run_tests.py` →
**pytest 1018 passed / 59 skipped / 6 subtests** · **vitest 576 passed / 50 Testdateien**

---

## 1. Was diese Session gebaut hat (Builds 347–383)

**Cockpit (Baustelle 7) — alle Sichten verdrahtet:**
Dashboard (348) · Integrität (349) · Lastverteilung (350/351) · Backup/PITR
(352–354) · Kapazität (355–360) · Rechte/Policy (361/362) · Meine Aufträge +
Historie (363/364) · Support-Historie (366/367) · Ermittler-Betreuung (368/369) ·
Statistiken (370/371) · **Zuweisung** (372/373).

**Berichts-Abnahme (374–382)** — der große Block:
- **374** Scan über alle `evidence_<uid>.db` + WAL-sicherer Fingerabdruck-Cache
  (Migration **m009**)
- **375** Cockpit-Sicht + Rechte-Korrektur (`approve` impliziert `review`)
- **376** Migrationsstand-Warnung beim Serverstart
- **377** **Versiegelung**: `approved_reports.db` (Abbild + Inhaltshash),
  `POST /api/report/approve`, `GET /api/report/verify`
- **378** Freigabe-Frontend (Aktionsfeld, Siegelprüfung)
- **379** **Schreibsperre** in `evidence_db.py` + **Statusmodell verbindlich
  festgelegt** + `seal_check`-CLI
- **380** Rückgabe zur Nachbesserung (`submitted → draft`)
- **381/382** Editor-Knopf „Zur Abnahme freigeben" + Bestätigungsdialog

**Fall-Autodetektion (383)** — Backend + CLI (Frontend **fehlt noch**, s. u.).

**Weitere:** 365 (CLI-Filter `rbac_admin`).

---

## 2. OFFENE PUNKTE — hier geht es weiter

### 2.1 Direkt anschließend (kleiner Rest aus Welle 1)

| # | Punkt | Stand |
|---|---|---|
| **A** | **Build 384 — Cockpit-Sicht „Fall-Erkennung"** (Frontend zu 383): Tabelle mit den vier Zuständen (`ok`/`neu`/`vermisst`/`unlesbar`), Filter, Auswahl + Knopf „Ausgewählte aufnehmen" (mit Bestätigung), deutliche Warnung bei `vermisst`/`unlesbar`. Backend liegt fertig vor (`GET /api/cases/detect`, `POST /api/cases/import`). | **direkt baubar** |
| **B** | **Wiedervorlage externer Vorgänge** (Welle-1-Punkt laut Bauplan §11.7) | **kein Code vorhanden** — braucht Bauplan |
| **C** | **Textbaustein-Bibliothek** (Welle-1-Punkt laut Bauplan §11.7) | **kein Code vorhanden** — braucht Bauplan |
| **D** | **Provisorische PDF-Ausgabe** (Browser/OS-Print-to-PDF, laut Bauplan Teil von Welle 1) | **ungeprüft** — bitte messen, ob vorhanden |

> **Wichtig:** Welle 1 ist damit **noch nicht abgeschlossen** (B, C, ggf. D
> fehlen). Erst danach ist der Übergang zu Welle 2 sauber.

### 2.2 Vermerkte Wünsche (aus dieser Session, noch offen)

| # | Punkt |
|---|---|
| **E** | **Fallauswahl-GUI für Ermittler** (Ermittler-Webserver, **nicht** Cockpit): Beim Start sollen Ermittler ihre zugewiesenen Fälle sehen und **abweichend von der automatischen Auswahl des höchstpriorisierten Falls** gezielt einen anderen öffnen können — **ohne Konsole**. Behelf bis dahin: `main.py --user-id`. |
| **F** | **Suspended-User-Problem** (Prepper, offener Faden aus Build 110): Nutzer der Gruppe 32 bekommen beim Scraping Gruppe 110 zugewiesen; Ursache sind Sperren per Direkt-DB-Edit ohne `logs_group_id`. Diagnose-SQL liegt vor, Entscheidung PHP (`changegrp.php`) vs. Prepper steht aus. |
| **G** | **Passwort-Ähnlichkeits-Pipeline** — Architektur fertig (LSH/MinHash + Levenshtein via `rapidfuzz.cdist()`, eigene `password_similarity.db`), Implementierung noch nicht begonnen. |
| **H** | **Annotations-Statistik** (Baustelle 4): vierteiliges Layout vereinbart (verschachteltes ECharts-Tortendiagramm, Tag-Netzwerk, chronologische Tag-Verteilung, Tabulator-Detailtabelle); `/_forensic/annotation_stats` entworfen, Umsetzung offen. |
| **I** | **`?pid=`-Auflösung mit Paginierung** (repo-übergreifend: `post_aliases`, forensic-Migration, Webserver-Resolver) — wartet auf eigenes `mc` mit Migrationsvorbehalt. |

### 2.3 Welle 2 (laut Bauplan §11.7)

Export-Subsystem (**gerichtsfester PDF**, löst die provisorische Print-Ausgabe
ab) · Kreuzbezugs-Register · Annotations-Tortenstatistik · Abdeckungs-Score +
blinde Flecken · StA-Statistik/Prognose/Gantt · Nächstbeste-Aktion ·
Eskalationsregeln · Audit-/Revisions-Explorer · Fremdforum-Promotion +
`data/`-Übersicht · externe Fallfreigabe + LKÄ-Distribution · Kommandopalette ·
Datenschutz-/Löschkonzept · Übergabe-Protokoll · Onboarding/Offboarding.

---

## 3. Wichtige Festlegungen dieser Session (bitte im neuen Chat kennen)

### 3.1 BERICHTS-STATUSMODELL (verbindlich, `mc` 2026-07-10)

**Dokument:** `documents/Berichts_Statusmodell.md` · **Code-Suchbegriff:**
`BERICHTS-STATUSMODELL` (in `db/evidence_db.py`)

```
draft ──(Autor: "Zur Abnahme freigeben", Build 382)──► submitted
  ▲                                                       │
  └──(Lektor/Chefin: Rückgabe, Build 380)─────────────────┘
                                                          │
                     (Chefin: Abnahme + Versiegelung, 377/378)
                                                          ▼
                                                      approved  (unwiderruflich)
                                                          │
                              (Chefin: an StA versandt, Build 380)
                                                          ▼
                                                        final
```

- Ab **`submitted`** ist der Inhalt für den **Autor gesperrt** (Build 379).
  **Kommentare bleiben erlaubt** (bewusst — dokumentieren den Bedarf für einen
  Nachtragsbericht).
- `approved`/`final` sind **unwiderruflich**. Inhaltliche Schwächen → **Nachtrag**
  (`report_type='addendum'`).
- **Falle:** `final` gibt es **zweimal** — als **Status** (versandt) und als
  **report_type** (Abschlussbericht).

### 3.2 Zwei Schutzebenen für Berichte

| Ebene | Ort | Leistet | Leistet **nicht** |
|---|---|---|---|
| **Verhinderung** | `evidence_<uid>.db` (Schreibsperre 379) | blockt Änderungen über die **Anwendung** | schützt **nicht** gegen direkte DB-Manipulation |
| **Nachweis** | `approved_reports.db` (Siegel 377) | **deckt jede** Änderung nach Freigabe auf (Hash) | verhindert nichts |

**Prüfbefehl:** `python -m management.reports.seal_check` (Exit 2 =
Manipulationsverdacht).

### 3.3 Fall-Definition (`mc`)

Ein Fall **existiert**, sobald **`forensic_<uid>.db`** vorliegt — unabhängig von
`evidence_`/`assets_` (das ist nur **Arbeitsstand**). Benutzername **autoritativ**
aus `uid_profile.username`.

### 3.4 Schreibpfad des Management-Servers (seit Build 372)

Der Server ist **nicht mehr GET-only**. Eng begrenzter POST-Pfad:
- **Härtung:** `X-AIW-Token` (pro Serverlauf, ausgeliefert über `GET /api/whoami`)
  + erzwungener `Content-Type: application/json` + Origin-Prüfung + 64-KiB-Limit.
  `PUT/DELETE/PATCH` → 405.
- **Alle** Lesepfade bleiben `mode=ro`; nur die Schreibhandler öffnen `_rw_con()`.
- Schreiben **ausschließlich** über `CoordinatorWriter` → **jede Änderung erzeugt
  ihren `audit_log`-Beleg**.

### 3.5 Betrieb — zwei Stolperfallen (beide real aufgetreten)

1. **Migrationen laufen NICHT beim Serverstart.** Sie laufen über
   **`python -m management.migrate --deployed-by <KENNUNG>`**. Seit Build 376
   **warnt** der Server beim Start deutlich, wenn der Stand nicht aktuell ist
   (er migriert bewusst **nicht** selbst).
2. **Nach jedem Backend-Build den Management-Server neu starten** — sonst kennt
   der laufende Prozess neue Routen nicht (404!).

---

## 4. Arbeitsweise (unverändert, bitte fortführen)

- **Workflow:** Bauplan vorlegen → **explizites `mc`** → implementieren →
  `py_compile`/`node --check` → **volle Regression** (`python run_tests.py`) →
  ZIP mit **MD5 je Datei** → `present_files` → **Alex committet selbst**.
- **Backend und Frontend immer in getrennten Builds** (Festlegung Build 363).
- **Messen, nicht rechnen.** Diese Session hat allein dadurch gefunden: die
  WAL-mtime-Blindheit, die `-shm`-Selbstinvalidierung des Caches, die lückenhafte
  Schreibsperre (`final` völlig ungeschützt!), das nie definierte Statusmodell und
  den 403-Fehler durch `reports.approve` vs. `reports.review`.
- **Grundregel 1:** kein stiller Fehlschlag — alles wird gemeldet.
- **Grundregel 10:** jede Klasse in eine eigene Datei.
- **Deutsch** in Code, Kommentaren, Logs. **`build.json` ASCII-only**
  (`ensure_ascii=True`).
- **`git add -f`** nötig für `*.md`, `*.html` (in `.gitignore`).
- Max. **3 Fragen/Vorschläge** je Wortwechsel.
- **PAT:** einer pro Session, am Ende **löschen**
  (`https://github.com/settings/personal-access-tokens`).

---

## 5. Nützliche Kommandos

```
python run_tests.py                                   # pytest + vitest (Pflicht-Gate)
python -m management.migrate --deployed-by h0a2898    # Migrationen anwenden
python -m management.cases.case_detect                # Fall-Autodetektion (Bericht)
python -m management.cases.case_detect --auto --actor h0a2898   # + auditiert aufnehmen
python -m management.reports.seal_check               # alle Berichts-Siegel prüfen
python -m management.rbac.rbac_admin list-grants --role supervisor
python -m management.rbac.rbac_admin list-roles --id 5
```

---

*Dokument-Ende · Übergabe Stand Build 383 · 2026-07-11*

# Übergabedokument — Baustelle 7 (Support/SSE) & Ausblick
## IT-Forensisches Ermittlungswerkzeug · FluxBB/PunBB-Forum · NRW

**Stand:** 2026-07-07 · **Zuletzt ausgelieferter Build:** `aiw_webserver` 328 (v0.7.328)
**Ziel-Baustelle:** 7 (Management-Interface)
**Dieses Dokument richtet sich an:** die nächste Chat-Instanz zur Fortführung von Baustelle 7.

> Zweck: einen **belegten** Baseline-Fingerabdruck übergeben, damit der neue Chat
> nachweislich auf dem richtigen Stand aufsetzt (Grundregeln 5 & 8), und den in
> dieser Session behobenen Themenkomplex (Support-Präsenz/SSE, Builds 324–328)
> lückenlos dokumentieren, damit nichts doppelt untersucht wird.

---

## 1. Kontext (kurz)

Baustelle 7 = Management-Interface (Support-Sitzungen, Ermittler-Verwaltung,
Migrations-/Ampel-Dashboard). Diese Session hat ausschließlich den Themenkomplex
**Support-Präsenz-Indikator / SSE-Rollen / Nebenläufigkeit** stabilisiert
(Builds 324–328). Das Feature ist danach Ende-zu-Ende funktionsfähig, getestet
und – soweit in dieser Session prüfbar – produktionssicher.

---

## 2. Build-Baseline & Verifikation (KRITISCH — zuerst prüfen)

**Wichtig:** Im Arbeitsbaum des liefernden Chats war der **committete** HEAD noch
`b2aea51 Version 0.7.323`; die Builds **324–328 lagen als gestapelte, nicht in
meinem Klon committete Auslieferungen** darüber (der Entwickler committet in der
VM selbst). Der neue Chat MUSS daher nach dem Klonen den echten Stand bestätigen.

### 2.1 Startprozedur (neuer Chat)
1. Beide Repos frisch klonen (siehe Projekt-Brief).
2. `git -C aiw_webserver log --oneline -1` und `git -C aiw_sqlite_prepper log --oneline -1` melden.
3. `build.json` in `aiw_webserver` lesen: erwartet **build 328 / v0.7.328**, wenn 324–328 committet sind.
4. **MD5-Abgleich** der unten gelisteten Dateien gegen den frischen Klon. Weichen
   Buildnummer oder MD5 ab, ist VOR jeder weiteren Arbeit zu klären, welche Builds
   tatsächlich committet/gepusht wurden (Grundregel 8 — keine gemischten Versionen).

### 2.2 Ziel-Fingerabdruck nach 324–328 (Arbeitsbaum des liefernden Chats)
Diese MD5 sind der **kumulative** Zielzustand nach Build 328:

| Datei (repo-relativ) | MD5 | zuletzt geändert in |
|---|---|---|
| `build.json` | `c7babaf842f6734ab6dfc66f2b635717` | 328 |
| `toolbar/toolbar.js` | `7043ee2ca570443af2df00f10d1569bc` | 324 |
| `db/locking_connection.py` | `92eee1a18f7e6ac4a34c2479a6f04496` | 325 (NEU) |
| `db/connection_manager.py` | `1bea1fb2b8fbc5856e8737be8773ef21` | 325 |
| `db/assets_db.py` | `411c7805ccb07d0b9c951beb8e6d3dc5` | 325 |
| `forensic_api/windows.py` | `405f43896cb9924c42812d3382bfe690` | 326 |
| `forensic_api/events.py` | `fa126a9257c5bcc028b33367268b765c` | 326 |
| `userinfo/userinfo.js` | `99a7435310d8062008ab2e1b3ac73452` | 327 |
| `management/support_sessions/support_sessions_repo.py` | `ee9509cff9d414c8d797120723198792` | 328 |
| `forensic_api/support_presence.py` | `c2a8b965d8061bbdc47277c9590e764d` | 328 |
| `tests/test_locking_connection.py` | `932f6e0f39931541b77d30d3724401ee` | 325 (NEU) |
| `tests/test_window_registry_ttl.py` | `ab3b0a855989eeba09b34e8750802685` | 326 (NEU) |
| `tests/unit/test_support_preflight.test.js` | `791e61faaa86cc33ca3f7c03178e60d5` | 327 (in 324 NEU) |
| `tests/test_management_support_sessions.py` | `2280e4287b69c4e62a43490b4ad545a9` | 328 |

### 2.3 Erwartete Testbasis (Regressionsgate `python3 run_tests.py`)
Nach Build 328: **Python 747 passed / 59 skipped / 3 subtests**, **JavaScript 423 passed / 1 skipped / 1 todo**.
Weicht dies ab, ist der Baseline nicht sauber.

---

## 3. Was diese Session lieferte (Builds 324–328)

Ein zusammenhängender Themenkomplex: „Warum sieht der Ermittler (aiw) keinen
Support-Indikator, wenn der Supporter (paul) einen Fall öffnet?" — in mehreren
belegten Schritten (messen statt spekulieren) bis zur Wurzel verfolgt.

- **324 — Preflight-Header `role=main` (toolbar.js).** Der SSE-Preflight-fetch sandte
  `X-Forensic-Preflight: 1` nicht → Server behandelte ihn als echten Stream,
  beanspruchte die Rolle, das echte EventSource kollidierte mit sich selbst (409).
  Fix: Header ergänzt. (Vor der Verdichtung dieser Session ausgeliefert/deployt.)

- **325 — Thread-Safety der geteilten SQLite-Verbindung.** `socketserver.ThreadingMixIn`
  → jeder Request + der SSE-Stream in eigenem Thread, aber ALLE Fach-DBs teilen EINE
  `sqlite3.Connection`. Überlappende `execute/fetch` korrumpierten den Verbindungs-
  zustand (`InterfaceError: bad parameter or other API misuse`; belegt durch identische
  `get_page('/')`, die 22:43:13 gelangen und 22:43:40 scheiterten). Fix: NEU
  `db/locking_connection.py` (`LockingConnection`-Wrapper, ein RLock serialisiert jeden
  execute+fetch, Eager-Materialisierung). `connection_manager` wrappt die geteilte con
  in beiden Modus-Zweigen; `assets_db._con_lock` (redundant) entfernt.

- **326 — Geleakte SSE-Rolle (Selbstheilung).** `WindowRegistry._active_sse_roles`
  (role→client_id, ephemere uuid4 je SSE-Verbindung, events.py:443) hatte KEINEN TTL;
  Freigabe nur via Grace-Timer nach *erkanntem* Disconnect. Bei ungrazilem Disconnect
  leakte die Rolle → jeder Preflight dauerhaft 409 (belegt: `active_window_id=d12ae68a`
  trotz sauberem Neustart). Fix: Lebendigkeits-Zeitstempel `_sse_role_seen` + `touch_sse_role()`
  (lebender Stream frischt pro Poll-Iteration ≤15 s auf); Einträge älter als
  `_SSE_ROLE_TTL=60 s` gelten als verwaist und werden automatisch freigegeben.

- **327 — Preflight-Header `role=userinfo` (userinfo.js:413).** Gleiche Fehlerklasse wie
  324, aber für Fenster 2 (eigener Preflight-Pfad `initSSEWindow2`, OHNE `SSELayer`).
  Fix: `X-Forensic-Preflight: 1` ergänzt → alle drei Rollen (main/userinfo/report)
  senden den Header konsistent. Guard P04/P05 ergänzt.

- **328 — Audit-Lücke bei verwaisten `support_sessions`.** Bei ungrazilem Disconnect blieb
  `ended_at=NULL`; das bestehende `prune()` LÖSCHTE solche Waisen OHNE Audit → im
  `audit_log` stünde ein STARTED ohne ENDED (Verstoß gegen Grundregel 1). Fix: NEU
  `SupportSessionsRepo.close_orphans(stale_sec)` beendet Waisen AUDITIERT
  (`ended_at = last_heartbeat`, SUPPORT_SESSION_ENDED, `payload.reason="orphan_timeout"`,
  actor=System). Binder ruft es bei JEDEM `begin()` vor `prune()`.

**Verifiziert (kontrollierter Read-only-Test):** Eine synthetische aktive
`support_sessions`-Zeile ließ aiws Indikator korrekt erscheinen → aiws ATTACH-Lesepfad
ist intakt; die Ursache lag rein paul-seitig (SSE-Rollen-Leak + fehlender Header).

---

## 4. Geparkte Punkte & Restrisiken

1. **Faden 2 — Anzeige „paul" statt „aiw" im Feld *angemeldeter Benutzer*
   (`#forensic-session-user`).** Trat zuletzt NICHT mehr auf; evtl. Artefakt eines
   synthetischen Tests (abruptes `DELETE` statt sauberem `ended_at`) oder durch 326/328
   mit behoben. **Mechanismus NICHT gesichert** (der `support_status`-Handler fasst
   `_state.investigatorUsername` nicht direkt an). **Trigger:** Bei erneutem Auftreten
   im echten Betrieb → Protokoll „erst Console-Output anfordern, dann PoC, dann Fix".
2. **Restrisiko `close_orphans` (328):** Waisen von Supportern, die NIE wiederkommen,
   bleiben bis zum nächsten `begin()` irgendeines Supporters liegen (kein lebender
   Schreiber sonst). Forensisch unkritisch (Indikator dank 30 s-Staleness sauber,
   STARTED-Beleg vorhanden). Ein zeitgesteuerter Sweeper wäre Overkill — nur bei
   Bedarf erwägen.
3. **Responsive CSS** blendet Toolbar-Elemente bei Halbbild-Breite aus (u. a.
   Support-Indikator/Sektion 5). Nach den Nebenläufigkeits-Fixes erneut prüfen.
4. **Stale `Bauplan_`-Referenzen:** `Bauplan_Baustelle7_Management_v0_7.md` ist auf dem
   Stand Build 312 (Builds 313–328 nicht eingepflegt); Baustelle-3-Verweise auf
   Baustelle 4 als „Dummy/leer" sind veraltet und bei Gelegenheit zu entfernen.

---

## 5. Baustelle 7 — Stand & Kandidaten für den nächsten Schritt

**Vor jeder Arbeit gegen den echten Repo-Stand + den (ggf. zu aktualisierenden)
`Bauplan_Baustelle7_Management`-Stand abgleichen — die folgende Liste ist ein
Gedächtnis-Anker, kein Beleg.**

- Support-Sitzungs-Tracking + Frontend-Indikator: **fertig (324–328)**, live verifiziert.
- Migrations-Infrastruktur (`migration.db`-Flotte, `MigrationCompanion`, Ampel-Dashboard,
  Builds 316–323): geliefert, aber **Browser-Test des Dashboards steht noch aus**.
- Backup/PITR: laut früherem Stand **noch nicht gebaut**.
- Weitere P2-Themen der Management-Oberfläche (Ermittler-Administration, Support-
  Session-Übersicht, Arbeitsverteilung/-review): offen — Umfang aus dem Bauplan ziehen.
- Passwort-Ähnlichkeits-Pipeline (LSH/MinHash + Levenshtein via `rapidfuzz`,
  `password_similarity.db`): Architektur entworfen, **Implementierung nicht begonnen**.

---

## 6. Gesicherte Lernpunkte (Belege) — wiederverwendbar

- **Geteilte `sqlite3.Connection` + ThreadingMixIn** braucht Serialisierung: alle
  execute+fetch unter einem `threading.RLock` mit Eager-Materialisierung
  (`db/locking_connection.py`). Separate Verbindungen (Binder, `evidence_db.get_lock`,
  Export) sind NICHT betroffen (eigene Connection).
- **SSE-Rollen** (`_active_sse_roles`) sind ephemere uuid4, KEINE `window_id`; sie werden
  jetzt via TTL/`touch` selbstgeheilt (kein dauerhafter 409-Leak mehr).
- **SSE-Preflight** wird serverseitig NUR am Header `X-Forensic-Preflight: 1` als
  Slot-Check erkannt (events.py:333-335). Alle drei Rollen senden ihn nun.
- **`coordinator.db`** ist WAL; Fremdprozess-Commits sind für andere Verbindungen
  sichtbar (kontrolliert verifiziert). `support_sessions` ist FLÜCHTIGE Präsenz
  (prunebar); der permanente Beleg lebt im `audit_log` (START/ENDE, Heartbeats bewusst
  nicht auditiert).
- **Audit:** `CoordinatorWriter.audited_write` schreibt Write + Audit ATOMAR; `do_write`
  liefert den Payload; niemals eine nie beendete Sitzung ohne ENDED löschen (Grundregel 1).
- **Zeitstempel** in `support_sessions` sind Unix-Sekunden (UTC-basiert); Serverlogs
  zeigen Lokalzeit (CEST = UTC+2). `get_active`/`get_support_status` nutzen 30 s-Staleness.

---

## 7. Startprozedur-Checkliste (neuer Chat)

- [ ] PAT vorhanden? (nur `Read` für `content` + `metadata`, gültig genau diese Session)
- [ ] Beide Repos frisch klonen; HEAD beider Repos melden.
- [ ] `build.json` = 328/v0.7.328 bestätigen (sonst klären, was committet ist).
- [ ] MD5-Abgleich der Tabelle in §2.2.
- [ ] `python3 run_tests.py` grün (747 py / 423 js) — Baseline sichern.
- [ ] Konkretes Baustelle-7-Ziel mit dem Entwickler festlegen (§5) und Bauplan-Stand prüfen.
- [ ] Am Session-Ende: PAT löschen (`https://github.com/settings/personal-access-tokens`).

---

*Erstellt am 2026-07-07 zum Abschluss der Session mit Build 328. Alle MD5- und
Testangaben stammen aus dem Arbeitsbaum des liefernden Chats und sind im neuen Chat
gegen den frischen Klon zu verifizieren.*

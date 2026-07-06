# Bauplan Build 325 — Serialisierung der geteilten SQLite-Verbindung

**Modul:** `aiw_webserver` · **Ziel-Build:** 325 · **Bauplan-Version:** v0.1 · **Datum:** 2026-07-06
**Status:** Entwurf, wartet auf `mc`
**Belegquelle:** Live-Diagnose 2026-07-06 (aiw-Serverlog, Ports 8081/8082), Codeanalyse Build 324.

---

## 1. Problem & Beweiskette (belegt)

Der Support-Indikator erschien kurz und verschwand beim Fenster-Resize. Die Ursachenkette
ist **kein Anzeigefehler**, sondern ein **Thread-Sicherheitsproblem der geteilten
SQLite-Verbindung**. Jeder Schritt ist belegt:

1. **Multithreaded-Server:** `class ForensicHTTPServer(socketserver.ThreadingMixIn,
   http.server.HTTPServer)` — Beleg: `server/http_server.py:242`. Jeder HTTP-Request laeuft in
   einem eigenen Thread; der SSE-Stream in einem weiteren langlebigen Thread.
2. **Eine geteilte Verbindung `con`:** erzeugt in `db/connection_manager.py:191` (cli),
   `:323`/`:334` (support/job). Alle Fach-DBs sind ATTACHes auf **demselben** `con`
   (`fdb`, `ddb`, `cdb`, `adb`, `tdb`) und teilen sich dieses Objekt: `ForensicDb(con)`,
   `CoordinatorDb(con)`, `EvidenceDb(con)`, `DefaultDb(con)`, `AssetsDb(con)`,
   `TemplatesDb(con)` — Beleg: `connection_manager.py:259` u. Umfeld.
3. **Serialisierung fehlt genau dort:** `assets_db` hat ein privates `_con_lock`
   (`db/assets_db.py:138`), das aber **nur** assets-eigene Aufrufe serialisiert — nicht die
   Kollision mit `forensic_db`/`coordinator_db` auf demselben `con`. `forensic_db.get_page()`
   und `coordinator_db.get_support_status()` greifen **ohne Lock** zu.
4. **`get_support_status()` verschluckt jede Exception → `active=False`** — Beleg:
   `db/coordinator_db.py:171-178` (`except Exception: ... return SupportStatusRecord(active=False, ...)`).

**Schlagender Log-Beleg (aiw, 2026-07-06):** derselbe Aufruf `get_page('/')` lief um
**22:43:13 erfolgreich** (`page_id=2533`) und schlug um **22:43:40** mit
`sqlite3.InterfaceError: bad parameter or other API misuse` (`db/forensic_db.py:272`) fehl —
**gleiche Eingabe, anderes Ergebnis** → korrupter Verbindungszustand durch Nebenlaeufigkeit,
kein Eingabefehler. Zeitgleich: `Viewport-Batch ... no more rows available` → HTTP 400.

**Eine Ursache erklaert alle drei Symptome:**
- `bad parameter or other API misuse` in `get_page` → HTTP 500 (Ermittler kann Seiten
  zeitweise nicht laden — produktionskritisch).
- `no more rows available` in Viewport → HTTP 400.
- Support-Indikator bricht beim Resize weg (Viewport-POST-Flut trifft den periodischen
  SSE-Poll auf demselben `con` → `get_support_status` wirft → `active=False`).

Das ist keine Neu-Einschleppung von Build 312/324, sondern eine **latente Luecke**, die der
periodische Support-Poll (Build 311/312) jetzt zuverlaessig ausloest.

---

## 2. Scope

### 2.1 In Scope (wird serialisiert)
Ausschliesslich die **geteilte Laufzeit-Verbindung** `con` aus `connection_manager` und alle
Klassen/Handler, die sie nutzen. Vollstaendige Landkarte siehe §4.

### 2.2 Explizit NICHT in Scope (eigene Verbindungen, keine Cursor-Kollision)
Diese besitzen **eigene** `sqlite3.Connection`-Objekte und teilen den geteilten `con` nicht;
sie koennen dessen Cursor nicht korrumpieren (Datei-Ebene regelt WAL). Belegte Fundstellen:
- `forensic_api/support_presence.py:121` — eigene Verbindung fuer Session-Schreiben
  (begin/heartbeat/end).
- `db/evidence_db.py:2134` — eigene kurzlebige Verbindung fuer `get_lock()` (Build 098,
  bewusst thread-sicher).
- `forensic_api/annotate.py:367`, `forensic_api/export.py:338/546`,
  `forensic_api/cross_annotation_integrator.py:178` — eigene Verbindungen (Cross-Annotation/Export,
  teils Hintergrund-Threads).
- `core/mode_resolver.py`, `core/startup_checks.py` — Startphase, einthreadig, vor Serving.
- `management/*`, `setup_coordinator_dev.py`, alle `tests/*` — separate Prozesse/Testfixtures.

### 2.3 Separate Themen (nicht Teil von Build 325, geparkt)
- **Rechte/Umgebung:** `attempt to write a readonly database` — Ursache: `evidence_1488.db`
  gehoert `paul:paul` (`rw-r--r--`), Server laeuft als `aiw`. Loesung ueber Gruppe `aiw`
  (Betriebssystem-Rechte), **kein Code-Thema**. Bestaetigt Projektgespraech 2026-07-06.
- **Session-Lifecycle:** verwaiste/ueberlappende `support_sessions` (`id=3` und `id=4`
  gleichzeitig aktiv) — eigener Aufraeummechanismus, spaeteres Build.
- **`userinfo.js:413`** identischer Preflight-Header-Fehler (role=userinfo) — eigenes Build.
- **Responsive CSS** blendet bei Halbbild-Breite Toolbar-Elemente aus — nach dem
  Concurrency-Fix zu pruefen.

---

## 3. Design: `LockingConnection`-Wrapper

### 3.1 Grundidee
Statt an 150+ Stellen einzeln `with lock:` zu ergaenzen (fehleranfaellig, „vergessene Stelle"),
wird die **eine** geteilte `con` in genau **einem** Objekt gekapselt. Alle Zugriffe laufen
zwangslaeufig durch dieses eine Tor → keine Stelle kann durchrutschen. Neue Datei
`db/locking_connection.py` (Grundregel 10: jede Klasse eigene Datei).

### 3.2 Serialisierungs-Semantik
- Interner `threading.RLock` (reentrant → kein Selbst-Deadlock bei geschachtelten Aufrufen).
- **Der Lock umspannt execute UND fetch.** Das ist der Kern: `cur = con.execute(sql);
  cur.fetchone()` darf nicht durch einen zweiten Thread zwischen `execute` und `fetch`
  unterbrochen werden. Deshalb **materialisiert** `execute()` das Ergebnis unter dem Lock
  sofort in eine Liste und gibt einen Ergebnis-Cursor zurueck, der `fetchone/fetchmany/
  fetchall/Iteration` aus dem Speicher bedient. Damit ist execute+fetch atomar, ohne dass
  Aufrufer geaendert werden muessen.

### 3.3 Vertrag (deckt ALLE in §4/Muster-grep gefundenen Zugriffe ab)
Der Wrapper stellt bereit:
- `execute(sql, params=())` → `_LockedResult` mit `fetchone/fetchmany/fetchall`, Iteration,
  `lastrowid`, `rowcount`, `description`. (Deckt `con.execute(...).fetchone()`,
  `...fetchall()`, `cursor.lastrowid`, `cursor.rowcount` ab — Belege §4.)
- `cursor()` → `_LockedCursor`, dessen `execute()` ebenfalls unter Lock materialisiert.
  (Deckt `assets_db.py:192`, `default_db.py:137` ab.)
- `commit()`, `rollback()`, `close()` — jeweils unter Lock bzw. an die reale Verbindung
  weitergereicht.
- **Oeffentlicher `.lock`** (derselbe RLock) als Eskalations-Ausweg fuer kuenftige
  Mehr-Statement-/Streaming-Abschnitte (`with con.lock: ...`).
- **Attribut-Proxy** (`__getattr__`/`__setattr__`) fuer alles Nicht-Ueberschriebene:
  insbesondere `row_factory` (die Fach-DBs setzen `self._con.row_factory = sqlite3.Row`,
  z. B. `coordinator_db.py:145`), sowie `create_function`, `set_authorizer`, `text_factory`,
  `backup`, `iterdump` u. a. — an die reale Verbindung durchgereicht.
- `executescript`/`executemany` werden pro forma unter Lock durchgereicht (im Laufzeit-Code
  aktuell ungenutzt — Beleg: Muster-grep leer), damit kuenftige Nutzung sicher bleibt.

### 3.4 Einbindungspunkt (spaetes Wrappen)
In `connection_manager` wird `con` **erst nach** dem vollstaendigen Aufbau (ATTACH, PRAGMA,
Authorizer-Setup/-Deaktivierung) gewrappt — die einthreadige Startphase laeuft also auf der
rohen Verbindung, nur der mehrthreadige Laufzeitzugriff auf dem Wrapper. Konkret in allen
drei Modus-Zweigen (`:191` cli, `:323`/`:334` support/job) unmittelbar vor dem Bau der
Fach-DB-Objekte bzw. des `DbBundle`. `bundle.connection` traegt dann den Wrapper.

### 3.5 Warum das genuegt (Vollstaendigkeitsargument)
`assets_db`s privates `_con_lock` wird **entfernt**, weil der Wrapper nun die einzige
Serialisierungsautoritaet ist (sonst zwei Locks, verwirrend, aber ungefaehrlich). Alle
eigenen Verbindungen aus §2.2 bleiben unveraendert (kein geteilter Cursor). Damit ist die
Menge der auf `con` zugreifenden Threads vollstaendig durch den Wrapper serialisiert.

---

## 4. Vollstaendige Zugriffslandkarte (Blast-Radius, grep-belegt)

`execute/executemany/executescript/cursor`-Stellen im Laufzeit-Code, die den geteilten `con`
nutzen (Zaehlung `grep -rcE` 2026-07-06):

| Datei | Stellen | Muster |
|---|---:|---|
| `db/evidence_db.py` | 103 | reads + INSERT(`lastrowid`) + UPDATE/DELETE(`rowcount`); Ausnahme: eigene get_lock-Con `:2134` |
| `db/forensic_db.py` | 23 | reads (u. a. `get_page` `:272`) |
| `db/default_db.py` | 10 | reads; `.cursor()` `:137` |
| `db/coordinator_db.py` | 9 | reads (`get_support_status`) + writes(`lastrowid`/`rowcount`) |
| `db/assets_db.py` | 9 | reads; `.cursor()` `:192`; privates `_con_lock` (wird entfernt) |
| `db/templates_db.py` | 6 | reads |
| `forensic_api/events.py` | 8 | reads (support/lock-status im SSE-Poll) |
| `forensic_api/report.py`, `userinfo_data.py`, `userinfo.py`, `reports.py`, `placeholders.py`, `editor_comment.py`, `_lock_guard.py` | je 1–2 | ueber Fach-DBs |

**Konsequenz:** Weil alle diese Stellen `self._con.execute(...)`/`.cursor()` aufrufen und
`self._con` kuenftig der Wrapper ist, greift die Serialisierung an **allen** Stellen, ohne
sie einzeln zu editieren. Keine „vergessene Stelle" moeglich — es gibt nur ein Tor.

---

## 5. Migrationssicherheit

- **Keine Schema-Aenderung, keine Datenaenderung.** Reine prozessinterne Serialisierung des
  Verbindungszugriffs. `evidence_<uid>.db`, `forensic_<uid>.db`, `assets_<uid>.db` werden
  weder strukturell noch inhaltlich beruehrt → Migrationsvorbehalt (ab 01.07.2026) nicht
  tangiert.
- Kein Eingriff in `coordinator.db`/`default.db`/`templates.db`-Inhalte.
- Kein `m00x`-Migrationsschritt noetig.

---

## 6. Testplan (Regressionstests sind Pflicht)

### 6.1 Nebenlaeufigkeits-Reproduktionstest (neuer Guard, kein „gruen-aber-tot")
`tests/test_locking_connection.py`:
- **T-Repro-RAW:** N Threads (z. B. 8) fuehren parallel gemischte `execute`+`fetch` auf einer
  **rohen** geteilten `con` (`check_same_thread=False`) aus → Test **erwartet/duldet** die
  bekannten Fehler (`InterfaceError`/`ProgrammingError`) und dokumentiert damit, dass das
  Problem real ist (Beweis der Wirksamkeit; als `xfail`/kontrolliert markiert).
- **T-Repro-WRAP:** identische Last ueber den `LockingConnection` → **null** Fehler, korrekte
  Ergebnisse. Das ist der eigentliche Regressions-Guard.
- **T-Contract:** `execute().fetchone()/.fetchall()`, Iteration, `lastrowid` (INSERT),
  `rowcount` (UPDATE/DELETE), `cursor().execute()`, `row_factory=sqlite3.Row`-Weiterleitung,
  `commit`/`rollback`, `.lock`-Reentranz.

### 6.2 Volle Regression
`python3 run_tests.py` (pytest + vitest) bleibt gruen. Erwartung: Python 718+neu passed,
JavaScript unveraendert 421.

### 6.3 Live-Abnahme (nach Deploy)
Wiederholung S1–S4 mit Resize-Stress: Indikator bleibt stabil; keine 500/400 in `get_page`/
Viewport waehrend paralleler Last.

---

## 7. Lieferung (Build 325)

Geaenderte/neue Dateien (repo-relativ):
- **NEU** `db/locking_connection.py` — `LockingConnection` + `_LockedResult`/`_LockedCursor`.
- **MOD** `db/connection_manager.py` — spaetes Wrappen in allen drei Modus-Zweigen.
- **MOD** `db/assets_db.py` — privates `_con_lock` entfernt (Wrapper ist Autoritaet).
- **NEU** `tests/test_locking_connection.py` — Reproduktions-/Contract-Tests.
- **MOD** `build.json` — Build 325, ASCII-only Note (`ensure_ascii=True`).

Ablauf: `py_compile` aller geaenderten `.py` → `python3 run_tests.py` gruen → ZIP
`aiw_webserver_325.zip` mit repo-relativen Pfaden + MD5-Prüfsummen → `present_files` →
Alex committet. Server-Neustart genuegt (kein Cache-Bust noetig, reiner Python-Change).

---

## 8. Risiken & Gegenmassnahmen

| Risiko | Gegenmassnahme |
|---|---|
| Deadlock bei geschachtelten Zugriffen | `threading.RLock` (reentrant). |
| Performance (Lock-Contention) | Lock wird nur pro Statement kurz gehalten; lange Ops (Export) nutzen eigene Con (§2.2). Erwartete Contention gering. |
| Grosse Result-Sets durch Eager-Materialisierung | Laufzeit-SELECTs holen 1 bzw. begrenzte Zeilen (`get_page`: 1 Zeile; deckungsgleich mit heutigem `.fetchone()/.fetchall()`). Kein Lazy-Socket-Streaming vom geteilten `con`. |
| `row_factory`/Authorizer-Weiterleitung | Attribut-Proxy im Wrapper; spaetes Wrappen laesst Startphase auf roher Con laufen. |
| „Vergessene Stelle" | Ein einziges Tor (Wrapper); Landkarte §4 als Nachweis. |

---

## 9. Offene Punkte / Diskurs

1. `assets_db._con_lock` **entfernen** (empfohlen, saubere Einzelautoritaet) oder als
   redundante Doppelsicherung belassen? Empfehlung: entfernen.
2. Reihenfolge: Build 325 (dieser Fix) **vor** `userinfo.js`-Header-Fix und
   Session-Lifecycle-Aufraeumen — beide danach.
3. Soll `T-Repro-RAW` dauerhaft als dokumentierender `xfail` verbleiben (Beweis der
   Wirksamkeit) oder nur einmalig gefuehrt werden? Empfehlung: als markierter `xfail`
   dauerhaft, als lebender Beleg.

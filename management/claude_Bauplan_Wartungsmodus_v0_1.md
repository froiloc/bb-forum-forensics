# Bauplan: Wartungsmodus (Maintenance Mode) — v0.1

IT-Forensisches Ermittlungswerkzeug (AIW) · Repository `aiw_webserver`
Stand: 2026-07-19 · Autor: Claude · Status: **Entwurf, `mc` fuer Umsetzung erteilt**

---

## 1. Motivation (belegt)

Es gibt heute keinen koordinierten Weg, laufende Server dazu zu bringen, ihre
Datenbankverbindungen **freizugeben**. Das ist die Voraussetzung fuer jede
Operation, die **Exklusivzugriff** auf eine geteilte Datenbank braucht:

- Einmalige Journalmodus-Umstempelung (`tools/convert_journal_mode.py`) — Beleg:
  PROD-Logs 2026-07-19 (db-error, db-error2, db-error3). Der Server bzw. das
  Werkzeug scheitert, solange eine andere Instanz die geteilte `coordinator.db`
  auf dem UNC-Share (`\\prod01\...`) offen haelt.
- Kuenftige Migrationen der Produktivdaten (`evidence_<uid>.db`, `forensic_<uid>.db`,
  `assets_<uid>.db`) ab 01.07.2026 — migrationsgebunden, verlustfrei, mit
  Exklusivzugriff.

Zweite Motivation: Nach einer Migration darf **keine alte Programmversion mit
neuen Daten arbeiten**. Der Wartungsmodus ist der Ort, an dem dieser
Versions-WLchter greift.

## 2. Grundprinzipien

1. **Dateibasiert, DB-unabhaengig.** Das Wartungssignal darf NICHT in einer
   Datenbank liegen — man will die DBs ja gerade stillstellen (Henne-Ei). Alle
   Signale sind Dateien im geteilten Datenverzeichnis. Das wirkt ueber alle VMs
   hinweg (gemeinsamer UNC-Share) und funktioniert ohne SQLite-Lock — analog zur
   bereits etablierten "Header-Bytes ohne SQLite lesen"-Philosophie
   (`core/startup_checks.py`, `db/journal_policy.journal_stamp`).
2. **Kein stiller Betrieb (Grundregel 1).** Jeder Eintritt/Austritt, jedes
   Quiesce/Resume, jeder uebersprungene oder nicht antwortende Server wird
   protokolliert und — wo es einen Menschen betrifft — **namentlich** gemeldet.
3. **Messen, nicht rechnen.** Das Wartungswerkzeug glaubt ACKs nicht, sondern
   **beweist** die Ruhigstellung, indem es selbst einen Exklusiv-Lock auf die
   Ziel-DB erwirbt. Gelingt das nicht, ist die Wartung NICHT freigegeben.
4. **Atomare Schreibvorgaenge.** Alle Steuerdateien werden ueber
   `tempfile + os.replace` atomar geschrieben (kein halb geschriebenes Flag).
5. **ASCII-only in JSON** (`json.dump(ensure_ascii=True)`), konsistent mit
   `build.json`.
6. **Eine Klasse — eine Datei** (Grundregel 10). Neues Paket `maintenance/`.

## 3. Verzeichnis- und Dateiprotokoll

Basis: das konfigurierte Datenverzeichnis (`paths.data_dir`, dort liegen bereits
`coordinator.db` etc.). Neues Unterverzeichnis `_maintenance/`:

```
data/
  _maintenance/
    window.json                     # DAS Wartungsfenster-Flag (Existenz = aktiv)
    presence/
      <host>__<pid>__<role>.json    # Praesenz-Beacon je laufendem Server
    ack/
      <host>__<pid>__<role>.ack     # Quiesce-Bestaetigung je Server
    servers/
      <uuid>.json                   # Anmeldung je --maintenance-Server (+ kill-Feld)
```

`<role>` = `webserver:<user_id>` oder `management`.

### 3.1 `window.json` (das Flag)

```json
{
  "window_id": "<uuid4>",
  "angefordert_von": "<system_username>",
  "angefordert_am": 1721400000,
  "grund": "Journalmodus-Umstempelung coordinator.db",
  "ziel": ["coordinator"],              // oder ["all"] / ["evidence:1488", ...]
  "bei_aktivierung": "pause",           // "pause" | "beenden"
  "min_build": 433,                     // Versions-Waechter (0 = keine Anforderung)
  "ablauf_am": 1721403600               // optional; abgelaufenes Fenster gilt als inaktiv
}
```

Die **Existenz** der Datei bedeutet "Fenster aktiv" (sofern `ablauf_am` nicht
ueberschritten). `bei_aktivierung` steuert das Verhalten der Normalserver
(pausieren vs. beenden). `min_build`/`ziel` steuern Versions-Waechter und Umfang.

### 3.2 `presence/<...>.json` (Beacon)

Jeder laufende Server (normal wie `--maintenance`) schreibt beim Start eine
Praesenzdatei und **touched** ihre mtime periodisch (huckepack auf dem
vorhandenen Watchdog, `main.py:634`). Inhalt: `{role, host, pid, user_id, port,
build, started_at, letzter_touch}`. Die Wartungs-CLI liest daraus, **wer ACKen
muss**. Veraltete Beacons (mtime > N s) werden als "vermutlich tot, unbestaetigt"
gemeldet — nie still als tot angenommen.

### 3.3 `ack/<...>.ack` (Quiesce-Bestaetigung)

Ein Normalserver schreibt seine ACK-Datei, **nachdem** er alle DB-Verbindungen
geschlossen (Sperren freigegeben) hat. Inhalt: `{role, host, pid, quiesced_am,
window_id}`. Die CLI wartet auf ACKs UND auf den Exklusiv-Lock-Beweis.

### 3.4 `servers/<uuid>.json` (Anmeldung eines --maintenance-Servers)

```json
{
  "uuid": "<uuid4>",
  "role": "webserver:1488",
  "host": "KKVM-1488", "pid": 12345, "port": 8409,
  "user_id": 1488, "build": 433, "config": "config-hello77.yaml",
  "started_am": 1721400500,
  "window_id": "<uuid des Fensters, unter dem er startete>",
  "kill_angefordert": false,           // vom Kill-Werkzeug auf true gesetzt
  "kill_von": null, "kill_am": null
}
```

Kill-Kanal ist **dateivermittelt** (funktioniert cross-VM ohne Netz): Das
Kill-Werkzeug setzt `kill_angefordert=true`; der Server pollt seine eigene
Anmeldedatei, erkennt das, protokolliert, gibt DBs frei, beendet sich und
**entfernt** seine Anmeldedatei. Deren Verschwinden ist die Bestaetigung.

## 4. Rollen und Zustandsautomaten

### 4.1 Normalserver (Webserver `job`/`cli`, Management)

Zusaetzlicher **Maintenance-Poller** (Intervall z.B. 3 s) im vorhandenen
Watchdog-Thread (Webserver) bzw. neuer Poll-Thread neben `serve_forever`
(Management).

```
LAEUFT ── window.json erscheint ──► QUIESCE
QUIESCE: in-flight-Transaktionen sauber beenden/rollen; DB-Verbindungen
         schliessen; ack schreiben; Log (GR1).
         ├─ bei_aktivierung == "beenden"  ─► BEENDEN (server_close, exit 0)
         └─ bei_aktivierung == "pause"    ─► PAUSE
PAUSE:   HTTP 503 "Wartungsmodus" fuer DB-beruehrende Routen; pollt weiter.
         window.json verschwindet ──► RESUME
RESUME:  Versions-Waechter: erfuellt der Server min_build des (zuletzt
         gesehenen) Fensters?  nein ─► BEENDEN mit Klartext ("alte Version darf
         nicht mit neuen Daten arbeiten").  ja ─► DB-Verbindungen neu oeffnen,
         ack entfernen, weiter wie LAEUFT.
```

### 4.2 Wartungs-Testserver (`main.py --maintenance` / `management.py --maintenance`)

Zweck (Praezisierung des Entwicklers): **verhaelt sich wie ein normaler Server**,
damit man waehrend der Wartung gegen die (ggf. frisch migrierten) Daten testen
kann — er ignoriert also die Quiesce-Direktive. ABER:

1. **Start nur bei aktivem Fenster.** Ist kein `window.json` aktiv, wird der
   Start **aktiv verweigert** (Exit mit Klartext). Das verhindert, dass `--maintenance`
   als Hintertuer zur Umgehung des Quiesce-Verhaltens missbraucht wird
   (Schutz vor feindlicher Uebernahme).
2. **Sichtbare Meldung.** Beim Start und im Log unmissverstaendlich:
   "LAEUFT IM WARTUNGSMODUS (window_id=..., uuid=...)". Auch in der Web-UI ein
   deutliches Banner.
3. **Anmeldung.** Erzeugt eine UUID und schreibt `servers/<uuid>.json` (§3.4).
   Unter dieser UUID ist er auffindbar und beendbar.
4. **Selbstbeendigung bei Fensterende.** Verschwindet `window.json`, beendet sich
   der Wartungs-Testserver selbst (sein Daseinszweck ist vorbei) und entfernt
   seine Anmeldung. Zurueckbleibende ("rogue") Server sind der Fall fuer das
   Kill-Werkzeug.
5. **Kill-Reaktion.** Pollt `kill_angefordert`; bei `true`: beenden + Anmeldung
   entfernen.

### 4.3 Wartungs-CLI `tools/maintenance.py`

- `--enter --grund "..." [--on-active pause|beenden] [--ziel all|coordinator|evidence:<uid>...]
   [--min-build N] [--ablauf-min M] [--wait-timeout S]`
  1. Rechte-/Rollenpruefung des Aufrufers (nur Supervisor/Support duerfen; via
     `coordinator.db`-Identitaet, read-only).
  2. `window.json` atomar schreiben.
  3. Auf ACKs **aller** in `presence/` gefuehrten, lebenden Server warten;
     Nachzuegler namentlich melden.
  4. **Beweis**: fuer jede Ziel-DB einen Exklusiv-Lock erwerben
     (`BEGIN EXCLUSIVE` bzw. `locking_mode=EXCLUSIVE`), sonst NICHT freigeben.
  5. Ergebnis: "Wartung freigegeben" nur, wenn 3 UND 4 erfuellt.
- `--exit`: `window.json` entfernen; pausierte Server nehmen den Betrieb wieder auf.
- `--status`: Fenster, Praesenzen, ACKs, angemeldete `--maintenance`-Server.

### 4.4 Kill-Werkzeug `tools/maintenance_kill.py`

- `--list`: alle `servers/<uuid>.json` mit Metadaten anzeigen.
- `--uuid <uuid>` | `--all`: `kill_angefordert=true` setzen; auf Verschwinden der
  Anmeldedatei(en) warten (Bestaetigung); Nachzuegler namentlich melden (GR1).
- Zweck: "rogue" Wartungs-Testserver toeten, die nach Fensterende weiterlaufen.

## 5. Betroffene bestehende Dateien

- `main.py`: `--maintenance`-Argument; Poller-Anbindung im Watchdog; Start-Guard;
  Quiesce/Resume-Hooks am `ConnectionManager`/`DatabaseBundle`.
- `management.py` / `management/server/...`: `--maintenance`-Argument; Poll-Thread;
  Start-Guard; 503-Auslieferung im Wartungsfall.
- `db/connection_manager.py`: sauberes `close()`/`reopen()` des Bundles
  (Verbindungen wirklich freigeben, damit Sperren fallen).

## 6. Build-Sequenz (jede Stufe eigenstaendig lauffaehig + getestet)

- **Build A — Fundament (`maintenance/`-Paket).** Datei-/JSON-Protokoll:
  `WindowFlag`, `PresenceBeacon`, `AckFile`, `ServerRegistration` — je eigene
  Datei, atomare Schreibvorgaenge, Parsing/Validierung. Reine Logik, vollstaendig
  unit-getestet. Kein Server-Wiring. **Rein additiv, migrationsfrei.**
- **Build B — Webserver-Integration.** Poller im Watchdog; Quiesce/Pause/Beenden/
  Resume + Versions-Waechter; `--maintenance` (Start-Guard, Anmeldung,
  Normalbetrieb, Selbstbeendigung, Kill-Reaktion, sichtbares Banner).
- **Build C — Management-Integration.** Poll-Thread, Quiesce/Resume, `--maintenance`
  analog.
- **Build D — Werkzeuge.** `tools/maintenance.py` (enter/exit/status, ACK-Wartung
  + Exklusiv-Lock-Beweis) und `tools/maintenance_kill.py` (list/kill).

Frontend (503-Banner) bleibt minimal und wird mit dem jeweiligen Backend-Build
ausgeliefert; groessere UI-Anteile ggf. separater Build (Festlegung 363).

## 7. Teststrategie

- Build A: reine Dateiprotokoll-Tests (Erzeugen/Lesen/atomar/veraltet/ungueltig),
  keine Server noetig — schnell und deterministisch.
- Build B/C: Poller-Zustandsautomat gegen echte Flag-/Ack-Dateien in `tmp_path`;
  `--maintenance`-Start-Guard (ohne Fenster → Exit); Kill-Reaktion; Versions-
  Waechter (min_build > eigener Build → BEENDEN).
- Build D: CLI gegen echte SQLite-Dateien; Exklusiv-Lock-Beweis wird durch eine
  gehaltene Zweitverbindung als "nicht ruhig" erkannt (bewusst herbeigefuehrter
  Lock, dann Freigabe).
- Kanonisches Gate: `python run_tests.py` (pytest + vitest).

## 8. Offene Entscheidungen (Vorschlag = Default)

1. **Selbstbeendigung** eines `--maintenance`-Servers bei Fensterende: *Vorschlag
   ja* (Kill-Werkzeug nur fuer Ausreisser).
2. **Kill-Kanal dateivermittelt** (`kill_angefordert` in der Anmeldung), da
   cross-VM ohne Netz: *Vorschlag ja*.
3. **Berechtigung fuer `--enter`/Kill**: nur Supervisor/Support (RBAC ueber
   `coordinator.db`, read-only): *Vorschlag ja*.

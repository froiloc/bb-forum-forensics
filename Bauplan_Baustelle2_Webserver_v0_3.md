# Bauplan — Baustelle 2: Python-Webserver
## IT-Forensisches Ermittlungswerkzeug · FluxBB/PunBB-Forum · NRW

**Version:** 0.3  
**Build:** 002  
**Datum:** 2026-04-10  
**Basis:** Architektur v0.3 (Build 003) · UEBERGABE_BAUSTELLE_2_ff.md (Build 025)  
**Status:** Verbindliche Planungsgrundlage — freigegeben für Phase 1  
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH  

---

## Änderungshistorie

| Version | Build | Datum | Änderung |
|---|---|---|---|
| 0.1 | 001 | 2026-04-10 | Erstfassung — Bauplan-Entwurf auf Basis der Architektur v0.3 |
| 0.2 | 001 | 2026-04-10 | Vollständig überarbeitet nach Planungsgespräch: ATTACH-Architektur, modulare `forensic_api/`, Support-Modus mit TEMP-DB, Viewport-Tracking, BLOB-View, Debug-Log, erweiterte CLI-Argumente, SAMAccountName-Format, ausführliche Prosa-Beschreibungen aller Komponenten |
| 0.3 | 002 | 2026-04-10 | CLI-Datenbankargumente auf Verzeichnispfade umgestellt (konsistent mit config.yaml); Two-Phase-Load eingeführt (Shell sofort, BLOB per AJAX nachgeladen); URL-Muster in config.yaml ausgelagert; CAT_OTHER als sechste Annotationskategorie aufgenommen; Baustellen-Benennung in Abschnitt 12 korrigiert |

---

## Strategische Grundregeln (unveränderlich)

Alle Entscheidungen in diesem Dokument unterliegen den projektweiten Grundregeln:

1. Kein Beleg darf ausgelassen oder still übersprungen werden.
2. Jede Versionsnummer muss ein lauffähiges, getestetes System repräsentieren.
3. Regressionstests sind Pflicht bei jeder Änderung.
4. Versionierung und Buildnummern sind Pflicht und mit jedem Durchgang zu iterieren.
5. Kommentierung gesicherter Erkenntnisse und Intentionen ist Pflicht.
6. Änderungen sind als vollständige Datei zu übergeben — keine Diffs, keine Partiallieferungen.
7. MD5-Prüfsummen für alle im Einsatz befindlichen Dateien sind anzufordern.
8. Nur fehlerfrei kompilierbarer Code darf übergeben werden. Jede `.py`-Datei wird vor Übergabe syntaxgeprüft.
9. Der Code soll so modular wie möglich sein. Jede Klasse gehört in eine eigene Datei.

---

## 1. Einordnung in die Gesamtarchitektur

Baustelle 2 ist das operative Herzstück des Ermittlungswerkzeugs. Sie ist die einzige
Baustelle, mit der der ermittelnde Beamte unmittelbar interagiert. Alle anderen
Baustellen liefern entweder Daten (Baustelle 0) oder bauen auf Baustelle 2 auf
(Baustellen 3, 4, 5, 6, 7).

Der Python-Webserver hat folgende Kernaufgabe: Er nimmt HTTP-Anfragen auf der
Adresse `127.0.0.2` entgegen, sucht die passende statisch gespeicherte HTML-Seite
(BLOB) aus der forensischen Datenbank heraus und liefert diese an den Browser aus.
Dabei reichert er die Seite mit einem Forensik-Werkzeugbalken an, der es den
Ermittlern ermöglicht, Annotationen zu setzen, Befunde zu kategorisieren und ihre
Arbeit für spätere Berichterstattung zu dokumentieren. Der BLOB selbst wird niemals
verändert — alle Ergänzungen geschehen ausschließlich durch JavaScript im Browser
des Ermittlers.

Der Server läuft als Stand-alone-Prozess auf `localhost` und wird über einen
Eintrag in der Systemdatei `hosts` so eingebunden, dass der ursprüngliche
Hostname des Forums auf `127.0.0.2` zeigt. Der Browser des Ermittlers sieht damit
dieselbe URL, die auch der Beschuldigte im Forum gesehen hat — eine wichtige
Voraussetzung für die forensische Nachvollziehbarkeit.

---

## 2. Verzeichnisstruktur

Die gesamte Anwendung liegt in einem einzigen Verzeichnis `forensic_server/`.
Jede Klasse befindet sich in ihrer eigenen Datei. Dieses Prinzip ist nicht
verhandelbar — es ist die Voraussetzung dafür, dass einzelne Module in
getrennten Entwicklungsgesprächen (separaten KI-Chats) unabhängig voneinander
entwickelt, getestet und ausgetauscht werden können.

```
forensic_server/
│
├── main.py                          # Einstiegspunkt: CLI-Parsing, Config laden,
│                                    # Startmodus auflösen, Integritätsprüfung,
│                                    # Server starten.
│
├── config.yaml                      # Zentrale Konfigurationsdatei.
│                                    # Liegt relativ zum Skript. Pfad kann per
│                                    # CLI-Argument --config überschrieben werden.
│
├── core/
│   ├── __init__.py
│   ├── config_loader.py             # Lädt config.yaml und stellt alle
│   │                                # Konfigurationsparameter bereit.
│   │                                # Implementiert die Eskalationskette:
│   │                                # CLI-Argument > config.yaml > Coded Default.
│   │
│   ├── startup_checks.py            # Führt alle Voraussetzungsprüfungen beim
│   │                                # Serverstart durch: SHA-256-Integritätsprüfung
│   │                                # der forensic_db, Erreichbarkeit aller DBs,
│   │                                # Schema-Versionscheck.
│   │
│   ├── mode_resolver.py             # Löst den Startmodus auf (job / cli / support)
│   │                                # anhand der Eskalationskette und ermittelt den
│   │                                # Pfad zur forensic_db und die User-ID des
│   │                                # Beschuldigten. Der konkrete Dateiname der
│   │                                # forensic_db und evidence_db wird immer aus
│   │                                # Verzeichnispfad + User-ID zusammengesetzt,
│   │                                # niemals direkt als Dateipfad übergeben.
│   │
│   ├── user_resolver.py             # Ermittelt den Systembenutzernamen der
│   │                                # laufenden Session: unter Linux via
│   │                                # os.environ['USER'] / pwd.getpwuid(),
│   │                                # unter Windows via os.environ['USERNAME']
│   │                                # (SAMAccountName, Format: h012345).
│   │                                # Wird gegen investigators-Tabelle in
│   │                                # coordinator.db geprüft.
│   │
│   ├── hosts_manager.py             # Verwaltet den hosts-Eintrag für den
│   │                                # Forumshostnamen → 127.0.0.2.
│   │                                # Unter Linux (DEV): no-op — wird manuell
│   │                                # gesetzt. Unter Windows (PROD): schreibt
│   │                                # und entfernt den Eintrag automatisch.
│   │                                # UAC-Eskalation ist in der Produktions-
│   │                                # umgebung kein Hindernis.
│   │
│   └── logger.py                    # Konfiguriert zwei Log-Handler:
│                                    # (1) Konsolenausgabe (immer aktiv),
│                                    # (2) rotierende Logdatei forensic_server.log.
│                                    # Im Debug-Modus (--debug / config.yaml):
│                                    # SQL-Queries, Request-Timing, BLOB-Lookup-
│                                    # Pfade werden zusätzlich protokolliert.
│
├── db/
│   ├── __init__.py
│   ├── connection_manager.py        # Zentrale Klasse, die alle Datenbankverbindungen
│   │                                # öffnet und die ATTACH-Struktur herstellt.
│   │                                # Haupt-DB ist immer evidence_db (READ-WRITE)
│   │                                # bzw. im Support-Modus eine lokale TEMP-DB.
│   │                                # Alle anderen DBs werden per ATTACH angebunden.
│   │                                # Verbindliche ATTACH-Aliasnamen:
│   │                                #   forensic_<uid>.db → ATTACH AS fdb
│   │                                #   default.db        → ATTACH AS ddb
│   │                                #   coordinator.db    → ATTACH AS cdb
│   │                                # Im Support-Modus zusätzlich:
│   │                                #   evidence_<uid>.db → ATTACH AS edb (READ-ONLY)
│   │
│   ├── forensic_db.py               # Kapselt alle Lesezugriffe auf fdb.
│   │                                # Stellt Methoden bereit für: BLOB-Lookup
│   │                                # via View, Alias-Auflösungen, scrape_context-
│   │                                # Abfrage, Integritätsprüfung.
│   │
│   ├── default_db.py                # Kapselt alle Lesezugriffe auf ddb.
│   │                                # Liefert statische Assets (CSS, Bilder,
│   │                                # Smilies) anhand ihrer URL.
│   │
│   ├── evidence_db.py               # Kapselt alle Schreibzugriffe auf die
│   │                                # Haupt-Datenbank: Annotationen speichern,
│   │                                # Seitenbesuche protokollieren,
│   │                                # Viewport-Events schreiben.
│   │                                # Im Support-Modus: alle Schreibmethoden
│   │                                # werden gegen die lokale TEMP-DB geleitet,
│   │                                # nicht gegen die echte evidence_db.
│   │                                # Die Unterscheidung ist ausschließlich
│   │                                # logisch — keine DB-seitige Sperre.
│   │
│   └── coordinator_db.py            # Kapselt alle Zugriffe auf cdb.
│                                    # WAL-Modus und Retry-Logik (3 Versuche,
│                                    # 500 ms Pause) sind Pflicht, da die
│                                    # coordinator.db auf einem Netzlaufwerk
│                                    # (NRW-Cloud, SMB) liegt und von mehreren
│                                    # Workstations gleichzeitig genutzt wird.
│
├── server/
│   ├── __init__.py
│   ├── http_server.py               # Basiert auf http.server.HTTPServer (stdlib).
│   │                                # Lauscht auf 127.0.0.2, Port aus config.yaml.
│   │                                # Unterscheidet Shell-Request von AJAX-Request
│   │                                # anhand des Headers X-Forensic-Request: ajax.
│   │                                # Alle POST-Requests außerhalb /_forensic/
│   │                                # werden mit HTTP 404 beantwortet.
│   │
│   ├── router.py                    # Leitet eingehende Requests an den
│   │                                # zuständigen Handler weiter.
│   │                                # URL-Muster für Asset-Erkennung und
│   │                                # Alias-Auflösung werden aus config.yaml
│   │                                # geladen (url_patterns-Block).
│   │
│   ├── shell_handler.py             # Liefert beim ersten Seitenaufruf (Shell-
│   │                                # Request) die leere Shell-HTML aus: mit
│   │                                # vollständigem <head>, eingebundenem
│   │                                # toolbar.css und toolbar.js, leerem
│   │                                # #forensic-viewport. Der BLOB-Inhalt
│   │                                # ist zu diesem Zeitpunkt noch nicht
│   │                                # geladen — toolbar.js löst sofort nach
│   │                                # dem Laden einen AJAX-Request auf
│   │                                # /_forensic/page aus, um den BLOB
│   │                                # nachzuladen (Two-Phase-Load).
│   │
│   ├── blob_handler.py              # Beantwortet ausschließlich AJAX-Requests
│   │                                # auf /_forensic/page?url=...
│   │                                # Löst Aliasse auf, sucht den BLOB via
│   │                                # View, gibt JSON-Envelope zurück.
│   │                                # Dies ist der einzige Auslieferungspfad
│   │                                # für BLOB-Inhalte — kein dualer Pfad mehr.
│   │
│   ├── asset_handler.py             # Liefert statische Assets aus ddb aus.
│   │                                # Zuständig für alle Requests auf CSS-,
│   │                                # Bild- und Smilie-URLs, deren Muster
│   │                                # im url_patterns-Block der config.yaml
│   │                                # definiert sind.
│   │
│   └── head_extractor.py            # Parst den <head>-Bereich eines BLOBs
│                                    # mit html.parser (Python Stdlib).
│                                    # Extrahiert: <title>, <base href>,
│                                    # <link rel="stylesheet">, inline <style>.
│                                    # Entfernt aktiv: <meta http-equiv="refresh">.
│                                    # Alle anderen <head>-Elemente werden
│                                    # ignoriert.
│
├── forensic_api/
│   ├── __init__.py                  # Registriert alle API-Handler und stellt
│   │                                # eine einheitliche dispatch()-Funktion
│   │                                # bereit. Abhängigkeiten werden per
│   │                                # Dependency Injection übergeben —
│   │                                # kein globaler State.
│   │
│   ├── page.py                      # Endpunkt /_forensic/page?url=...
│   │                                # AJAX-Auslieferung des BLOB-Inhalts.
│   │                                # Gibt JSON-Envelope zurück (siehe 6.).
│   │
│   ├── annotate.py                  # Endpunkt /_forensic/annotate (POST)
│   │                                # Nimmt Annotationen entgegen und
│   │                                # schreibt sie in evidence_db.
│   │                                # Sechs Kategorien: CAT_PERSON,
│   │                                # CAT_LOCATION, CAT_176, CAT_184,
│   │                                # CAT_VICTIM, CAT_OTHER.
│   │
│   ├── status.py                    # Endpunkt /_forensic/status
│   │                                # Liefert Serverstatus als JSON.
│   │
│   ├── static.py                    # Endpunkte /_forensic/toolbar.js
│   │                                # und /_forensic/toolbar.css.
│   │
│   └── viewport.py                  # Endpunkt /_forensic/viewport (POST)
│                                    # Nimmt Viewport-Events entgegen und
│                                    # schreibt sie in viewport_events.
│                                    # Im Support-Modus: Schreiben in TEMP-DB.
│
├── toolbar/
│   ├── toolbar.js                   # Werkzeugbalken-JavaScript.
│   │                                # Implementiert Two-Phase-Load:
│   │                                # löst nach Shell-Load sofort AJAX-Request
│   │                                # auf /_forensic/page aus.
│   │                                # Fängt alle Link-Klicks ab und ersetzt
│   │                                # Navigation durch AJAX-Requests.
│   │                                # Implementiert IntersectionObserver für
│   │                                # Viewport-Tracking.
│   │                                # Wertet scrape_context aus config.yaml
│   │                                # aus und steuert Toolbar-Darstellung.
│   │
│   └── toolbar.css                  # Stylesheet des Werkzeugbalkens.
│                                    # CSS-Variablen für alle Farbzustände:
│                                    # normal, investigator-Kontext,
│                                    # actor-Kontext, NOT_IN_SCOPE.
│
└── tests/
    ├── __init__.py
    ├── test_config_loader.py
    ├── test_mode_resolver.py
    ├── test_user_resolver.py
    ├── test_startup_checks.py
    ├── test_blob_handler.py
    ├── test_shell_handler.py
    ├── test_head_extractor.py
    ├── test_url_routing.py
    ├── test_forensic_db.py
    ├── test_evidence_db.py
    ├── test_coordinator_db.py
    ├── test_forensic_api_page.py
    ├── test_forensic_api_annotate.py
    └── test_forensic_api_viewport.py
```

---

## 3. Startmodi und Eskalationskette

### 3.1 Prinzip der Eskalationskette

Das gesamte System folgt einer einheitlichen Eskalationskette für alle
Konfigurationsparameter. Diese Kette gilt ohne Ausnahme:

```
CLI-Argument  >  config.yaml  >  Coded Default
```

Für den Pfad zur `config.yaml` selbst gilt:

```
--config <pfad> (CLI-Argument)  >  ./config.yaml (relatives Default neben dem Skript)
```

Das bedeutet: Ein CLI-Argument überschreibt immer, was in der `config.yaml` steht.
Was in der `config.yaml` steht, überschreibt immer den einprogrammierten Standardwert.
Fehlt ein Parameter auf allen Ebenen, greift der Coded Default — und dieser ist in
einem Kommentar im Code dokumentiert, sodass keine impliziten Überraschungen entstehen.

### 3.2 Startmodi

Der Server kennt drei Betriebsmodi:

**Modus `job` (Default):**
Der Server ermittelt beim Start den Systembenutzernamen der laufenden Session und
sucht in `coordinator.db` nach einem offenen Job, der diesem Benutzer zugewiesen ist.
Den Pfad zur `forensic_<uid>.db` entnimmt er aus der Spalte `output_path` des
entsprechenden Eintrags in `scrape_jobs`. Den konkreten Dateinamen der
`evidence_<uid>.db` setzt er aus dem konfigurierten `evidence_db_dir` und der
User-ID zusammen. Dieser Modus ist für den regulären Ermittlungsbetrieb vorgesehen.

**Modus `cli`:**
User-ID oder Benutzername des Beschuldigten werden direkt als CLI-Argumente
übergeben. Der Server setzt die konkreten Dateinamen aller nutzerspezifischen
Datenbanken aus den konfigurierten Verzeichnispfaden und der so bestimmten User-ID
zusammen. Es ist nicht möglich, einzelne Datenbankdateien direkt per Pfad
anzugeben — die User-ID ist der einzige Schlüssel. Das verhindert, dass
absichtlich oder unabsichtlich Datenbanken verschiedener Beschuldigter gemischt
werden.

**Modus `support`:**
Alle Datenbanken werden read-only angebunden, mit Ausnahme der `coordinator.db`
(diese bleibt schreibbar, damit Support-Tätigkeiten und Statusmeldungen protokolliert
werden können). Alle Schreiboperationen, die normalerweise in `evidence_db` landen
würden (Annotationen, Seitenbesuche, Viewport-Events), werden stattdessen in eine
lokale TEMP-Datenbank umgeleitet. Diese TEMP-Datenbank ist entweder eine In-Memory-
SQLite3-Datenbank (schnell, verschwindet bei Session-Ende) oder eine Datei im
lokalen TEMP-Verzeichnis des Systems (persistent für die Session, nützlich bei
längeren Support-Gesprächen). Die Entscheidung zwischen beiden Varianten wird per
`config.yaml` gesteuert (`support.temp_db: memory | file`).

### 3.3 Vollständige Liste der CLI-Argumente

Alle Datenbankpfade werden als Verzeichnispfade angegeben. Der konkrete Dateiname
der nutzerspezifischen Datenbanken (`forensic_<uid>.db`, `evidence_<uid>.db`) wird
immer intern aus Verzeichnis + User-ID zusammengesetzt. Dies ist konsistent mit der
Struktur der `config.yaml` und verhindert die versehentliche oder vorsätzliche
Vermischung von Datenbanken unterschiedlicher Beschuldigter.

| Argument | Typ | Bedeutung | Coded Default |
|---|---|---|---|
| `--config <pfad>` | String | Pfad zur config.yaml | `./config.yaml` |
| `--mode job\|cli\|support` | Enum | Startmodus | `job` |
| `--user-id <int>` | Integer | Beschuldigter per User-ID (alle Modi außer job) | keiner |
| `--username <str>` | String | Beschuldigter per Benutzername (alle Modi außer job) | keiner |
| `--forensic-db-dir <pfad>` | String | Überschreibt `paths.forensic_db_dir` aus config | keiner |
| `--evidence-db-dir <pfad>` | String | Überschreibt `paths.evidence_db_dir` aus config | keiner |
| `--default-db <pfad>` | String | Überschreibt `paths.default_db` aus config | keiner |
| `--coordinator-db <pfad>` | String | Überschreibt `paths.coordinator_db` aus config | keiner |
| `--debug` | Flag | Aktiviert Debug-Log (SQL, Timing, Lookup-Pfade) | aus |

### 3.4 config.yaml — vollständige Struktur

```yaml
server:
  host: "127.0.0.2"
  port: 80                          # In DEV abweichend konfigurierbar, z.B. 8080
  mode: "job"                       # Default-Startmodus: job / cli / support

paths:
  coordinator_db: "/mnt/nrw-cloud/coordinator.db"
  forensic_db_dir: "/mnt/nrw-cloud/forensic/"
  default_db: "./data/default.db"
  evidence_db_dir: "./data/evidence/"
  # Dateinamensschema (unveränderlich, nicht konfigurierbar):
  #   forensic_<uid>.db  →  <forensic_db_dir>/forensic_<uid>.db
  #   evidence_<uid>.db  →  <evidence_db_dir>/evidence_<uid>.db

hosts_management:
  enabled: false                    # DEV: false (manuell gesetzt).
                                    # PROD/Windows: true (automatisch).
  forum_hostname: "obstgarten.example"
  target_ip: "127.0.0.2"

logging:
  level: "info"                     # info / debug
  logfile: "./logs/forensic_server.log"
  max_bytes: 10485760               # 10 MB pro Logdatei
  backup_count: 5                   # 5 Rotationsdateien vorhalten

support:
  temp_db: "memory"                 # memory (In-Memory) oder file (%TEMP% / /tmp)

url_patterns:
  # Muster für die Erkennung von Asset-URLs (statische Ressourcen in default_db).
  # Alle URLs, die auf eines dieser Präfixe passen, werden an asset_handler.py
  # weitergeleitet statt an blob_handler.py.
  # Diese Liste ist bewusst konfigurierbar, damit das Werkzeug bei späteren
  # Einsätzen mit anderen Forensoft-Strukturen ohne Code-Änderung angepasst
  # werden kann.
  asset_prefixes:
    - "/forum/style/"
    - "/forum/img/"
    - "/forum/extensions/"

  # Muster für die URL-Alias-Auflösung in router.py und blob_handler.py.
  # Jeder Eintrag beschreibt ein bekanntes URL-Muster, das vor dem BLOB-Lookup
  # aufgelöst werden muss. Auch diese Liste ist konfigurierbar für
  # Wiederverwendbarkeit des Werkzeugs.
  alias_patterns:
    post_id_param: "pid"            # ?pid=<post_id> → über post_aliases auflösen
    notify_param: "notify"          # ?notify=<notify_id> → über notify_aliases
    fragment_post: "p"              # #p<post_id> im Fragment → normalisieren
```

---

## 4. Datenbankarchitektur

### 4.1 Grundprinzip: evidence_db als Haupt-Datenbank mit ATTACH

Eine fundamentale Entscheidung dieser Architektur ist, dass `evidence_db` immer
die Haupt-Datenbankverbindung ist — die Datenbank, die mit `sqlite3.connect()`
geöffnet wird. Alle anderen Datenbanken werden über `ATTACH DATABASE` als
benannte Schemas angebunden. Der Grund für diese Wahl ist, dass `evidence_db` die
einzige Datenbank ist, in die im normalen Betrieb geschrieben wird. Views, die Daten
aus mehreren Datenbanken zusammenführen, können nur in der Haupt-Datenbank als
temporäre Views angelegt werden. Da der BLOB-Lookup-View Daten aus `fdb`
referenziert, muss `fdb` per ATTACH erreichbar sein. Der View selbst wird in
`evidence_db` als `CREATE TEMP VIEW` angelegt — er berührt die versiegelte
`forensic_db` nicht und verletzt damit nicht deren READ-ONLY-Integrität.

### 4.2 ATTACH-Konfiguration — normaler Ermittler-Modus

```
Haupt-Datenbank (READ-WRITE):
    evidence_<uid>.db

ATTACH DATABASE '<forensic_db_dir>/forensic_<uid>.db' AS fdb;  -- READ-ONLY
ATTACH DATABASE '<default_db>'                         AS ddb;  -- READ-ONLY
ATTACH DATABASE '<coordinator_db>'                     AS cdb;  -- READ-WRITE
```

Der BLOB-Lookup-View wird beim Öffnen der Verbindung als temporärer View angelegt:

```sql
CREATE TEMP VIEW IF NOT EXISTS blob_lookup AS
    -- Direkte Treffer: URL entspricht exakt url_canonical in pages
    SELECT
        p.id,
        p.url_canonical  AS url,
        p.html,
        p.fetched_at,
        p.http_status,
        p.scrape_context
    FROM fdb.pages p
    UNION ALL
    -- Alias-Treffer: URL ist eine bekannte Variante (Fragment-Anker, pid-Parameter)
    SELECT
        p.id,
        pa.url_raw       AS url,
        p.html,
        p.fetched_at,
        p.http_status,
        p.scrape_context
    FROM fdb.pages p
    JOIN fdb.page_aliases pa ON pa.page_id = p.id;
```

Dieser View vereinheitlicht den Zugriff auf BLOBs vollständig: Die aufrufende
Komponente muss nicht mehr unterscheiden, ob eine URL direkt in
`pages.url_canonical` steht oder über `page_aliases` aufgelöst werden muss.
Sie fragt immer nur `blob_lookup` ab.

### 4.3 ATTACH-Konfiguration — Support-Modus

Im Support-Modus ist die Haupt-Datenbank keine persistente Datei, sondern
eine lokale TEMP-Datenbank. Diese wird entweder im Arbeitsspeicher gehalten
(`file::memory:?cache=shared`) oder als Datei im temporären Verzeichnis des
Betriebssystems gespeichert (`%TEMP%\forensic_support_<session_id>.db`
unter Windows, `/tmp/forensic_support_<session_id>.db` unter Linux).

```
Haupt-Datenbank (READ-WRITE, lokal, temporär):
    :memory:  oder  /tmp/forensic_support_<session_id>.db

ATTACH DATABASE '<evidence_db_dir>/evidence_<uid>.db'  AS edb;  -- READ-ONLY
ATTACH DATABASE '<forensic_db_dir>/forensic_<uid>.db'  AS fdb;  -- READ-ONLY
ATTACH DATABASE '<default_db>'                         AS ddb;  -- READ-ONLY
ATTACH DATABASE '<coordinator_db>'                     AS cdb;  -- READ-WRITE
```

Im Support-Modus sind alle Annotationen, Seitenbesuche und Viewport-Events,
die während der Session entstehen, in der TEMP-Haupt-DB gespeichert. Sie sind
für den Supporter während der Session vollständig nutzbar (Lesezugriff auf alle
forensischen Daten über die angebundenen DBs), gehen aber nach Session-Ende
verloren — sofern sie nicht manuell exportiert und in die echte `evidence_db`
übertragen wurden. Ein solcher Transfer ist ein dokumentierter, bewusster Schritt
und kein automatischer Hintergrundprozess.

Der BLOB-Lookup-View wird im Support-Modus identisch zum normalen Modus als
temporärer View angelegt, da `fdb` in beiden Modi per ATTACH erreichbar ist.

### 4.4 Beschreibung der Datenbankmodule

**`connection_manager.py`** ist die zentrale Klasse, die beim Serverstart aufgerufen
wird und alle Datenbankverbindungen öffnet. Sie entscheidet anhand des Startmodus,
welche ATTACH-Konfiguration aufgebaut wird, prüft die Erreichbarkeit aller Pfade,
setzt den WAL-Modus für `cdb` und stellt sicher, dass der temporäre BLOB-Lookup-View
angelegt ist. Sie gibt an alle anderen Komponenten eine fertig initialisierte
Verbindung weiter. Niemand außer `connection_manager.py` ruft `sqlite3.connect()`
direkt auf — diese Regel ist im gesamten Projekt einzuhalten.

**`forensic_db.py`** kapselt alle Lesezugriffe auf die forensische Datenbank.
Die wichtigste Methode ist `get_page(url: str)`, die über den `blob_lookup`-View
eine Seite anhand ihrer URL findet. Weitere Methoden lösen die verschiedenen
Alias-Typen auf: `resolve_post_alias(post_id)` liefert `(topic_id, forum_id)`,
`resolve_pm_alias(pm_post_id)` liefert `pm_topic_id`, `resolve_notify_alias(notify_id)`
liefert `post_id`. Die Methode `verify_integrity()` prüft den SHA-256-Hash der
forensic_db gegen den in `forensic_meta` gespeicherten Wert. Diese Prüfung wird
beim Serverstart in `startup_checks.py` aufgerufen — bei Abweichung verweigert
der Server den Start.

**`default_db.py`** kapselt alle Lesezugriffe auf die Datenbank mit statischen
Assets. Die Methode `get_asset(url: str)` liefert ein Tupel `(bytes, mime_type)`
oder `None`, falls das Asset nicht gefunden wurde.

**`evidence_db.py`** kapselt alle Schreiboperationen. Im normalen Modus schreibt
sie in die Haupt-`evidence_db`. Im Support-Modus schreibt sie in die lokale TEMP-DB.
Diese Unterscheidung ist ausschließlich logisch implementiert — es gibt keine
Datenbank-seitige Sperre. Eine logische Sperre ist explizit, nachvollziehbar im
Code dokumentiert und forensisch defensibel.

**`coordinator_db.py`** verwaltet alle Zugriffe auf die gemeinsame Koordinations-
datenbank. Da diese auf einem SMB-Netzlaufwerk liegt und von mehreren Workstations
gleichzeitig genutzt wird, sind WAL-Modus und eine Retry-Logik mit drei Versuchen
und 500 ms Pause zwischen den Versuchen Pflicht. Die wichtigsten Methoden sind
`get_assigned_job(system_username)`, die den offenen Job für den aktuellen
Systembenutzer findet, und `get_investigator(system_username)`, die den Ermittler-
Datensatz aus der `investigators`-Tabelle lädt.

---

## 5. Server-Schicht

### 5.1 HTTP-Server (`http_server.py`)

Der HTTP-Server basiert auf `http.server.HTTPServer` aus der Python-Standard-
bibliothek. Es wird bewusst keine externe HTTP-Bibliothek verwendet, um die
Abhängigkeitsliste minimal zu halten und die Offline-Tauglichkeit der Anwendung
zu gewährleisten.

Der Server lauscht auf der IP-Adresse `127.0.0.2`. Der Port ist über `config.yaml`
konfigurierbar: Port 80 in der Produktionsumgebung, in der Entwicklungsumgebung
typischerweise Port 8080, um root-Rechte zu vermeiden.

Das Seitenladeverhalten folgt dem **Two-Phase-Load-Prinzip**: Beim ersten Aufruf
einer Forum-URL durch den Browser liefert der Server nicht sofort den BLOB-Inhalt
aus. Stattdessen sendet er zunächst eine leere Shell-HTML mit vollständigem
`<head>`, eingebundenem `toolbar.css` und `toolbar.js` sowie einem leeren
`#forensic-viewport`. Sobald `toolbar.js` im Browser geladen ist, löst es
automatisch einen AJAX-Request auf `/_forensic/page?url=<aktuelle-URL>` aus
und befüllt den `#forensic-viewport` mit dem zurückgegebenen BLOB-Inhalt.

Dieses Prinzip hat mehrere Vorteile: Die Toolbar ist sofort sichtbar und
betriebsbereit, bevor der BLOB geladen ist. Es gibt nur einen einzigen
Auslieferungspfad für BLOB-Inhalte — den AJAX-Endpunkt. `blob_handler.py` muss
nicht mehr zwischen zwei Zuständen (Shell-Request und AJAX-Request) unterscheiden.
Und `toolbar.js` arbeitet immer unter identischen Bedingungen, da der BLOB-Inhalt
immer per AJAX injiziert wird, nie direkt im initialen HTML-Dokument steht.

Alle POST-Requests, die nicht an den `/_forensic/`-Namensraum gerichtet sind,
werden mit HTTP 404 beantwortet. Formulare im Forum dürfen nicht ausgeführt
werden — die gespeicherten Seiten sind statische Momentaufnahmen, keine
interaktiven Anwendungen.

### 5.2 Router (`router.py`)

Der Router ist die erste Verarbeitungsstufe nach dem HTTP-Server. Er entscheidet
anhand der angeforderten URL, welcher Handler zuständig ist. Die URL-Muster für
diese Entscheidungen werden vollständig aus dem `url_patterns`-Block der
`config.yaml` geladen — kein Muster ist hart im Code verdrahtet. Das macht das
Werkzeug bei späteren Einsätzen mit anderen Forum-Strukturen wiederverwendbar,
ohne dass Code-Änderungen notwendig sind.

```
Eingehende URL
  │
  ├── Beginnt mit /_forensic/       → forensic_api/__init__.py dispatch()
  │     ├── /_forensic/page             → forensic_api/page.py
  │     ├── /_forensic/annotate         → forensic_api/annotate.py
  │     ├── /_forensic/status           → forensic_api/status.py
  │     ├── /_forensic/viewport         → forensic_api/viewport.py
  │     ├── /_forensic/toolbar.js       → forensic_api/static.py
  │     └── /_forensic/toolbar.css      → forensic_api/static.py
  │
  ├── URL beginnt mit einem Asset-Präfix aus url_patterns.asset_prefixes
  │                                   → asset_handler.py
  │
  └── Alle anderen URLs
        ├── Header X-Forensic-Request: ajax vorhanden?
        │     ja  → blob_handler.py   (AJAX, gibt JSON-Envelope zurück)
        │     nein → shell_handler.py  (erster Aufruf, gibt leere Shell zurück)
```

### 5.3 Shell-Handler (`shell_handler.py`)

Der Shell-Handler beantwortet alle Forum-URL-Anfragen, die ohne den
`X-Forensic-Request: ajax`-Header eintreffen — also den ersten Seitenaufruf
durch den Browser oder einen Direktlink.

Er liest den `<head>`-Bereich des zum URL passenden BLOBs via `head_extractor.py`
aus, um `<title>`, `<base>`, CSS-Links und inline `<style>`-Blöcke zu extrahieren.
Diese werden in das Shell-`<head>` eingebettet, ergänzt um die Einbindungen von
`/_forensic/toolbar.css` und `/_forensic/toolbar.js`.

Der `<body>` der Shell enthält ausschließlich:

```html
<body>
  <div id="forensic-toolbar"></div>
  <div id="forensic-viewport">
    <!-- Inhalt wird per AJAX nachgeladen durch toolbar.js -->
  </div>
</body>
```

Der Shell-Handler protokolliert keinen `page_visit` — das geschieht erst, wenn
der BLOB erfolgreich per AJAX nachgeladen wurde, da erst dann sichergestellt ist,
dass der Ermittler tatsächlich Seiteninhalte zu Gesicht bekommen hat.

Falls die angeforderte URL nicht im forensischen Datenbestand liegt (kein BLOB
vorhanden), liefert der Shell-Handler dennoch die Shell-HTML aus — aber mit dem
HTTP-Header `X-Forensic-Status: NOT_IN_SCOPE`. Die Toolbar kann diesen Header
auslesen und den Ermittler entsprechend informieren.

Für den Sonderfall, dass die URL zwar im Datenbestand liegt, aber `pages.html`
den Wert `NULL` hat (der Abruf in Stage 2 war fehlgeschlagen), wird die Shell
ebenfalls ausgeliefert. `toolbar.js` erhält über den nachgeladenen AJAX-Response
die Information über den gescheiterten Abruf und zeigt sie an.

### 5.4 BLOB-Handler (`blob_handler.py`)

Der BLOB-Handler ist ausschließlich für AJAX-Requests auf `/_forensic/page?url=...`
zuständig. Er ist der einzige Auslieferungspfad für BLOB-Inhalte. Es gibt keinen
zweiten Weg, einen BLOB zu erhalten — das vereinfacht die Logik erheblich und
stellt sicher, dass Toolbar und BLOB-Inhalt immer unter identischen Bedingungen
zusammenarbeiten.

**Verarbeitungsablauf:**

1. Die URL wird aus dem Query-Parameter `url` extrahiert und normalisiert.
   Fragment-Anker (`#p<post_id>`) werden vor dem Datenbankzugriff entfernt, aber
   im zurückgegebenen JSON für die JavaScript-Toolbar weitergegeben, damit diese
   den Browser nach dem Laden zum korrekten Anker scrollen kann.

2. Die URL wird gegen bekannte Alias-Muster aus `url_patterns` geprüft. Bei
   Treffern auf `?pid=<post_id>` wird `post_aliases` konsultiert, bei
   `?notify=<notify_id>` wird `notify_aliases` konsultiert. Das Ergebnis ist
   immer eine normalisierte kanonische URL.

3. Der BLOB wird über `forensic_db.get_page(url)` abgefragt, das intern den
   `blob_lookup`-View verwendet.

4. Ist der BLOB `NULL` (Abruf in Stage 2 fehlgeschlagen), wird dennoch ein
   JSON-Envelope zurückgegeben — mit `html: null`, dem gespeicherten
   `http_status` und `fetch_failed: true`. Kein stiller Fehler — Grundregel 1.

5. Ist die URL überhaupt nicht im Datenbestand, wird ein JSON-Envelope mit
   `in_scope: false` zurückgegeben.

6. Der `scrape_context` der gefundenen Seite wird in den JSON-Envelope aufgenommen.

7. Ein Eintrag in `page_visits` wird geschrieben.

8. Der JSON-Envelope wird zurückgegeben:

```json
{
  "html":           "<body-Inhalt des BLOBs, oder null bei Fehler>",
  "scrape_context": "user | investigator | actor:<uid>",
  "http_status":    200,
  "fetch_failed":   false,
  "in_scope":       true,
  "url_canonical":  "<normalisierte URL>",
  "fragment":       "p12345"
}
```

### 5.5 Head-Extractor (`head_extractor.py`)

Der Head-Extractor verwendet `html.parser` aus der Python-Standardbibliothek.
Es wird bewusst auf externe Parser (wie BeautifulSoup) verzichtet, um die
Abhängigkeitsliste minimal zu halten.

Extrahiert werden:

- `<title>` — wird in den Shell-`<head>` übernommen, damit die Browser-Titelleiste
  den korrekten Seitentitel zeigt.
- `<base href="...">` — wird übernommen. Der `hosts`-Eintrag sorgt dafür, dass
  relative URLs korrekt auf `127.0.0.2` aufgelöst werden.
- `<link rel="stylesheet" href="...">` — CSS-Einbindungen des Forums. Sie werden
  in den Shell-`<head>` übernommen, da das Forum-Styling für die korrekte
  Darstellung der gespeicherten Seiten erforderlich ist.
- Inline `<style>...</style>`-Blöcke — kommen gelegentlich in einzelnen
  Forum-Seiten vor und werden ebenfalls übernommen.

Aktiv entfernt werden:

- `<meta http-equiv="refresh">` — würde zu unerwünschten automatischen
  Weiterleitungen führen und muss daher unterdrückt werden.

Alle anderen `<head>`-Elemente (externe JavaScript-Einbindungen, Web-Fonts,
Favicons, CSP-Meta-Tags etc.) werden ignoriert. Die gespeicherten Forum-Seiten
sind statisch und kommen ohne JavaScript aus. Externe Ressourcen sind in der
Offline-Umgebung nicht erreichbar und würden nur zu Ladefehlern führen.

---

## 6. Forensik-API (`forensic_api/`)

Die Forensik-API ist ein Python-Paket (Verzeichnis mit `__init__.py`). Jeder
Endpunkt ist in einer eigenen Datei implementiert. Diese Struktur ist bewusst
gewählt: Jede Datei kann in einem separaten Entwicklungsgespräch unabhängig
entwickelt, getestet und erweitert werden, ohne dass andere Endpunkte davon
berührt werden.

`__init__.py` registriert alle Handler und stellt eine einzige
`dispatch(path, method, params, body, db_connection)`-Funktion bereit, die
`router.py` aufruft. Die Datenbankverbindung und alle weiteren Abhängigkeiten
werden per Dependency Injection übergeben — kein globaler State.

### Endpunkte im Überblick

**`/_forensic/page`** (GET, implementiert in `page.py`):
Liefert den BLOB-Inhalt einer Forum-Seite als JSON-Envelope. Wird von `toolbar.js`
aufgerufen, sowohl beim initialen Two-Phase-Load als auch bei jeder weiteren
Navigation im Forum. Gibt neben dem HTML-Inhalt auch `scrape_context`, den
originalen HTTP-Statuscode des Abrufs, `in_scope`, `fetch_failed` und `fragment`
zurück. Dieser Endpunkt ist der einzige Weg, über den BLOB-Inhalte den Browser
erreichen.

**`/_forensic/annotate`** (POST, implementiert in `annotate.py`):
Nimmt eine Annotation entgegen und schreibt sie in `evidence_db`. Eine Annotation
besteht aus: der URL der annotierten Seite (normalisiert), der Element-ID des
annotierten Elements (z.B. Post-ID `p12345`), der Kategorie, dem Freitext des
Ermittlers und dem Zeitstempel der Annotation. Im Support-Modus wird in die
TEMP-DB geschrieben.

Die sechs Annotationskategorien sind:

| Kategorie | Bedeutung |
|---|---|
| `CAT_PERSON` | Persönliche Identifikationsmerkmale (Namen, Pseudonyme, biographische Angaben) |
| `CAT_LOCATION` | Ortsangaben (Wohnort, Aufenthaltsort, geografische Hinweise) |
| `CAT_176` | Relevanz für §§ 176, 176a StGB (sexueller Missbrauch von Kindern) |
| `CAT_184` | Relevanz für §§ 184b, 184c StGB (Verbreitung von CSAM) |
| `CAT_VICTIM` | Hinweise auf mögliche Opfer oder opferbezogene Inhalte |
| `CAT_OTHER` | Sonstige ermittlungsrelevante Beobachtungen, die in keine der obigen Kategorien passen |

Die Kategorie `CAT_OTHER` ist bewusst aufgenommen worden: Eine nicht
kategorisierbare Beobachtung, die aus Mangel an passender Kategorie still
wegfällt, wäre ein verlorener potenzieller Beleg — Grundregel 1. Die
Qualitätssicherung bei der Kategorisierung ist Aufgabe der Ermittlungsleitung,
nicht des Werkzeugs.

**`/_forensic/status`** (GET, implementiert in `status.py`):
Liefert den aktuellen Serverstatus als JSON. Enthält: Startmodus, user_id des
Beschuldigten, Benutzername des Beschuldigten, Integritätsstatus der `forensic_db`
(geprüft / nicht geprüft / Alarm), aktueller Ermittler (system_username,
display_name), Versionsnummer des Servers, Timestamp des Serverstarts.

**`/_forensic/viewport`** (POST, implementiert in `viewport.py`):
Nimmt Viewport-Events vom Browser entgegen. Das JavaScript im Browser verfolgt
mit `IntersectionObserver`, welche Elemente (z.B. Posts) wie lange im sichtbaren
Bereich des Browserfensters waren. Diese Daten werden als Batch an diesen Endpunkt
gesendet und in `viewport_events` gespeichert. Die forensische Bedeutung dieser
Daten: Sie belegen, welche Inhalte der Ermittler tatsächlich gesichtet hat und wie
intensiv er sich damit befasst hat. Im Support-Modus: Speicherung in TEMP-DB.

**`/_forensic/toolbar.js`** und **`/_forensic/toolbar.css`** (GET, implementiert in `static.py`):
Liefern die Werkzeugbalken-Ressourcen aus. Diese werden vom Browser beim Shell-Load
angefragt und danach gecacht.

---

## 7. Werkzeugbalken (`toolbar/`)

Der Werkzeugbalken ist die sichtbare Benutzeroberfläche des Ermittlers. Er wird
einmalig beim ersten Seitenaufruf geladen und bleibt während der gesamten Session
persistent — auch wenn der Ermittler im Forum navigiert. Dies wird durch den
Two-Phase-Load-Ansatz ermöglicht: Die Shell wird nie vollständig neu geladen,
und `toolbar.js` ist nach dem initialen Load immer aktiv.

Die genaue visuelle Gestaltung des Toolbars (Farben, Layout, Schaltflächen,
Kontextanzeige) ist Aufgabe von Baustelle 3. Baustelle 2 stellt die technische
Grundlage bereit und garantiert, dass folgende Informationen für Baustelle 3
jederzeit zugänglich sind:

- `scrape_context` der aktuellen Seite (aus dem AJAX-Response-JSON)
- `in_scope`-Status (ob die Seite im forensischen Datenbestand liegt)
- `http_status` des ursprünglichen Abrufs der Seite in Stage 2
- `fetch_failed`-Flag (ob der Abruf in Stage 2 fehlgeschlagen ist)
- `fragment` (Post-Anker, zu dem nach dem Laden gescrollt werden soll)

**Two-Phase-Load-Ablauf in `toolbar.js`:**

1. Browser lädt Shell-HTML. `#forensic-viewport` ist leer.
2. `toolbar.js` wird ausgeführt.
3. `toolbar.js` liest die aktuelle URL aus `window.location`.
4. `toolbar.js` sendet AJAX-GET an `/_forensic/page?url=<aktuelle-URL>`.
5. Antwort (JSON-Envelope) wird empfangen.
6. `#forensic-viewport.innerHTML` wird mit `response.html` befüllt.
7. Falls `response.fragment` gesetzt, scrollt `toolbar.js` zum Anker.
8. `toolbar.js` aktualisiert den Toolbar-Zustand anhand von `scrape_context`
   und `in_scope`.

**Navigation im Forum:**

Alle Link-Klicks im `#forensic-viewport` werden von `toolbar.js` abgefangen
(`event.preventDefault()`). Statt einer vollständigen Seitenladung wird ein
AJAX-Request an `/_forensic/page` gesendet. Der `#forensic-viewport` wird mit
dem neuen BLOB-Inhalt befüllt, und `history.pushState()` aktualisiert die
Adressleiste auf die neue Forum-URL — ohne die Shell oder die Toolbar neu zu laden.

**Viewport-Tracking:**

`toolbar.js` implementiert einen `IntersectionObserver`, der alle relevanten
DOM-Elemente im `#forensic-viewport` beobachtet (primär Post-Container mit
CSS-Selektoren wie `div[id^="p"]` für Posts der Form `#p12345`). Wenn ein
Element in den sichtbaren Bereich eintritt oder ihn verlässt, wird der
Millisekunden-Zeitstempel notiert. Nach einem Debounce-Intervall werden
die gesammelten Events als Batch via AJAX an `/_forensic/viewport` gesendet.

---

## 8. Forensische Sonderfälle

Diese Sonderfälle sind nicht optional — sie sind Bestandteil der Grundregel,
dass kein Beleg still übergangen werden darf.

| Situation | Behandlung |
|---|---|
| URL nicht in `forensic_db` | Shell-Handler liefert Shell mit HTTP-Header `X-Forensic-Status: NOT_IN_SCOPE`. Der AJAX-Request auf `/_forensic/page` gibt `in_scope: false` zurück. Die Toolbar informiert den Ermittler. Kein stiller Fehler. |
| `pages.html IS NULL` (Abruf fehlgeschlagen) | AJAX-Response enthält `html: null`, `fetch_failed: true` und den gespeicherten `http_status` (z.B. 403, 500, 0 für Verbindungsfehler). Die Toolbar zeigt: „Seite wurde erfasst, Abruf schlug fehl (HTTP [status])". Der Eintrag in `pages` bleibt — Grundregel 1. |
| `scrape_context = 'investigator'` | `scrape_context` wird im AJAX-JSON-Envelope zurückgegeben. Visuelle Kennzeichnung (Toolbar-Färbung) durch Baustelle 3 definiert. Forensische Bedeutung: Der Beschuldigte hatte möglicherweise keinen Zugriff auf diese Seite. |
| `scrape_context` beginnt mit `'actor:'` | Wie `'investigator'`: Wert im JSON-Envelope, Darstellung durch Baustelle 3. Forensische Bedeutung: Diese Seite gehörte nicht zur originären Sicht des Beschuldigten. |
| POST-Request außerhalb `/_forensic/` | HTTP 404 ohne Body. Keine Ausnahmen. |
| SHA-256-Prüfung der `forensic_db` schlägt fehl | Server verweigert den Start vollständig. Fehlermeldung auf stdout und im Log mit exaktem Differenzbefund. Betrieb mit einer möglicherweise manipulierten forensic_db ist nicht zulässig. |

---

## 9. Neue und geänderte Tabellen

### 9.1 Neue Tabellen in `coordinator.db`

Die `coordinator.db` erhält zwei neue Strukturen. Die `investigators`-Tabelle
speichert alle bekannten Ermittler-Accounts. Sie wird beim Serverstart konsultiert,
um den aktuellen Systembenutzer zu identifizieren und seinen Rollen-Kontext zu
ermitteln. Ein Benutzer kann mehrere Rollen gleichzeitig innehaben — alle drei
Boolean-Flags können gleichzeitig den Wert 1 haben.

```sql
CREATE TABLE IF NOT EXISTS investigators (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    system_username  TEXT NOT NULL UNIQUE,
    -- Unter Linux (DEV): $USER / pwd.getpwuid().pw_name
    -- Unter Windows (PROD): SAMAccountName, Format h012345
    display_name     TEXT NOT NULL,
    is_investigator  INTEGER NOT NULL DEFAULT 1,  -- Boolean: 0 oder 1
    is_supervisor    INTEGER NOT NULL DEFAULT 0,  -- Boolean: 0 oder 1
    is_support       INTEGER NOT NULL DEFAULT 0,  -- Boolean: 0 oder 1
    created_at       INTEGER NOT NULL             -- Unix-Timestamp
);
```

Die `scrape_jobs`-Tabelle erhält eine neue Spalte, die die Zuweisung eines Jobs
an einen konkreten Ermittler ermöglicht. `NULL` bedeutet: noch nicht zugewiesen.

```sql
ALTER TABLE scrape_jobs
ADD COLUMN assigned_to INTEGER REFERENCES investigators(id);
```

### 9.2 Neue Tabellen in `evidence_db`

Die `evidence_db` erhält zwei neue Tabellen, die durch Baustelle 2 befüllt werden.

`page_visits` protokolliert jeden Seitenaufruf durch den Ermittler. Ein Eintrag
wird geschrieben, sobald `toolbar.js` den BLOB erfolgreich per AJAX empfangen
und in den Viewport injiziert hat — nicht beim Shell-Load, da zu diesem Zeitpunkt
noch kein Seiteninhalt sichtbar ist.

```sql
CREATE TABLE IF NOT EXISTS page_visits (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    page_url         TEXT NOT NULL,
    -- Normalisierte kanonische URL der aufgerufenen Seite
    scrape_context   TEXT NOT NULL,
    -- Forensisch relevanter Kontext der Seite: user / investigator / actor:<uid>
    ts               INTEGER NOT NULL,
    -- Unix-Timestamp (Sekunden) des Seitenaufrufs durch den Ermittler
    investigator_id  INTEGER REFERENCES investigators(id)
    -- Welcher Ermittler hat die Seite aufgerufen?
);
```

`viewport_events` protokolliert, welche Elemente (Posts, Beiträge) der Ermittler
tatsächlich im sichtbaren Bereich des Browserfensters hatte und für wie lange.
Diese Daten belegen die Intensität der Auseinandersetzung mit einzelnen Inhalten
und können im Ermittlungsbericht zur Dokumentation der Beweissichtung herangezogen
werden.

```sql
CREATE TABLE IF NOT EXISTS viewport_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    page_url         TEXT NOT NULL,
    -- Normalisierte URL der Seite, auf der das Element beobachtet wurde
    element_id       TEXT,
    -- DOM-ID des beobachteten Elements, z.B. "p12345" für Post-ID 12345.
    -- NULL, wenn kein spezifisches Element identifizierbar war.
    visible_ms       INTEGER NOT NULL,
    -- Gesamtdauer der Sichtbarkeit in Millisekunden (gemessen per IntersectionObserver)
    ts_enter         INTEGER NOT NULL,
    -- Unix-Timestamp in Millisekunden: Eintritt des Elements in den Viewport
    ts_leave         INTEGER NOT NULL,
    -- Unix-Timestamp in Millisekunden: Austritt des Elements aus dem Viewport
    investigator_id  INTEGER REFERENCES investigators(id)
);
```

---

## 10. Implementierungsreihenfolge

Die Implementierung erfolgt in fünf Phasen. Jede Phase endet mit einem vollständig
lauffähigen, getesteten Systemstand — keine Phase darf mit nicht-laufenden Tests
abgeschlossen werden.

**Phase 1 — Fundament (kein Server, nur Kern-Module und Tests):**
In dieser Phase wird keine einzige HTTP-Anfrage beantwortet. Stattdessen werden
alle Basismodule gebaut und mit Unit-Tests abgesichert: `config_loader.py`,
`mode_resolver.py`, `user_resolver.py`, `startup_checks.py`, `forensic_db.py`
(inklusive `verify_integrity()`, BLOB-Lookup-View, alle Alias-Auflösungsmethoden)
und `head_extractor.py`. Jedes Modul muss unabhängig von den anderen testbar sein.
Phase 1 endet erst, wenn alle Tests grün sind.

**Phase 2 — Server läuft und liefert Shells und BLOBs aus:**
`http_server.py`, `router.py`, `shell_handler.py`, `blob_handler.py` und
`asset_handler.py` werden implementiert. Am Ende dieser Phase kann der Ermittler
eine Forum-URL im Browser öffnen: Er erhält eine Shell mit leerem Viewport, und
`toolbar.js` lädt den BLOB per AJAX nach. Alias-Auflösung, `NOT_IN_SCOPE`-Handling
und korrekte HTTP-Statuscodes sind vollständig implementiert.

**Phase 3 — Forensik-API und Datenbankschicht vollständig:**
`forensic_api/` (alle Endpunkte: `page.py`, `annotate.py`, `status.py`, `static.py`),
`evidence_db.py`, `coordinator_db.py`, grundlegendes `toolbar.js` (Two-Phase-Load,
Link-Abfangen, AJAX-Navigation, sechs Annotationskategorien als Grundgerüst) und
`toolbar.css` werden implementiert. Am Ende dieser Phase kann der Ermittler
navigieren, Annotationen setzen und Seitenbesuche werden protokolliert.

**Phase 4 — Sonderfälle, Viewport-Tracking und Härtung:**
`hosts_manager.py` (PROD/Windows), `viewport.py` mit `IntersectionObserver` in
`toolbar.js`, vollständige Behandlung aller Sonderfälle aus Abschnitt 8,
vollständige Regressionstests für alle bisher implementierten Module. Am Ende
dieser Phase ist das System produktionsreif für die Entwicklungsumgebung.

**Phase 5 — Integration und Abnahme:**
`main.py` führt alle Module zusammen. Integrationstest mit einer echten
`forensic_db`. Alle Startmodi (`job`, `cli`, `support`) werden durchgetestet.
Abnahme durch den Entwickler. Vorbereitung der Übergabe an Baustelle 3.

---

## 11. Offene Punkte

| OP | Thema | Status | Zuständige Baustelle |
|---|---|---|---|
| OP-H1 | `<head>`-Behandlung (vollständige Liste) | Geschlossen — Abschnitt 5.5 | 2 |
| OP-H5 | Kennzeichnung `actor`-Seiten im Toolbar | Offen — visuelle Gestaltung nicht definiert | 3 |
| OP-32 | JavaScript-Schalter in Werkzeugleiste | Offen | 3 |
| OP-33 | Toolbar-Färbung bei `investigator`- und `actor`-Kontext | Offen — Baustelle 2 liefert Metadaten, Darstellung durch Baustelle 3 | 3 |
| OP-5 | Volltext-Stichwortsuche reaktivieren | Zurückgestellt | 2 / 3 |

---

## 12. Abhängigkeiten zu anderen Baustellen

Baustelle 2 ist das Fundament für alle nachgelagerten Baustellen. Die korrekte
Benennung der Baustellen ist:

- **Baustelle 3 — Werkzeugbalken:** Baustelle 2 liefert `scrape_context`,
  `in_scope`, `http_status`, `fetch_failed` und `fragment` als Metadaten im
  AJAX-JSON-Envelope. Baustelle 3 definiert auf dieser Basis die visuelle
  Darstellung des Werkzeugbalkens: Färbung bei `investigator`-Kontext,
  Hinweise bei `NOT_IN_SCOPE`, Annotationsformulare für die sechs Kategorien.
  Die Datenbankverbindung ist dieselbe ATTACH-Verbindung wie in Baustelle 2 —
  kein zusätzlicher Verbindungsaufbau notwendig.

- **Baustelle 4 — Nutzerinfo-Tab:** Zweites Browserfenster mit strukturierten
  Daten zum Beschuldigten. Greift lesend auf `fdb` (Stammdaten, Aktivitätsdaten)
  und auf `evidence_db` (bereits gesetzte Annotationen) zu. Abhängig von
  Baustelle 2 für die ATTACH-Verbindungsstruktur.

- **Baustelle 5 — Datenbank-Interface:** Datenagregation und Synchronisation
  zwischen Workstations über `coordinator.db`. Baustelle 2 liest `scrape_jobs`
  und `investigators`; Baustelle 5 schreibt Prioritäten, Zuweisungen und
  aggregierte Statistiken.

- **Baustelle 6 — Bericht und Export:** Die von Baustelle 2 in `evidence_db`
  geschriebenen Annotationen, Seitenbesuche und Viewport-Events sind die primäre
  Datenquelle für den automatisch generierten Ermittlungsbericht. Abhängig von
  Baustelle 3 (Annotationen) und Baustelle 4 (Nutzerinfo).

- **Baustelle 7 — Management-Interface:** Übersicht für die Ermittlungsleitung
  über alle laufenden Fälle. Greift direkt auf `coordinator.db` zu.
  Baustelle 2 und Baustelle 7 teilen sich `coordinator.db` als gemeinsame
  Schnittstelle; keine Abhängigkeit von Baustelle 2 als Laufzeitsystem.

---

*Dokument-Ende · Bauplan Baustelle 2 · Version 0.3 · Build 002 · 2026-04-10*  
*Internes Arbeitsdokument — IT-forensisches Ermittlungsprojekt NRW.*  
*Unterliegt der Vertraulichkeit des Ermittlungsverfahrens.*

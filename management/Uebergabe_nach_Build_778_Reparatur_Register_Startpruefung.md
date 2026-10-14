# Uebergabe nach Build 778 — Reparaturwerkzeuge (776), Register Datenbank-Vorfaelle (777), Startpruefung der evidence-Datei (778)

Lieferung: **`aiw_webserver_778`** (ein Bundle, Zweig `claude/build776`, Basis
`origin/master = 2247588`). Es enthaelt die Builds 776, 777 und 778.

## 1. Anlass

- PROD 13./14.10.2026: `evidence_2948078.db` war beschaedigt. Neu aufgebaut
  wurde sie von Hand mit `evidence_reparatur.py` 1.2.
- Festlegungen Alex 14.10.2026:
  - Was behebbar ist, wird beim Start automatisch behoben. Die neue Datei
    wird **auch dann eingesetzt**, wenn sie nicht freigegeben ist: „Die
    Ermittler MÜSSEN ARBEITEN KÖNNEN“.
  - Jeder Vorfall wird ein Eintrag in einer zentralen Datenbank und ist im
    Management sichtbar. Eine Statusdatei waere ein Medienbruch.
  - Eine Sicherung mit identischer SHA-256 wird nicht ein zweites Mal
    angelegt.
  - Scheitert ein Schritt, wird der Start verweigert, die Fehlerseite mit
    Hilfe geoeffnet und ein Eintrag angelegt.

## 2. Build 776 — Werkzeuge in den Bestand

- **Reparaturlogik als Modul** `db/reparatur/` (eine Klasse je Datei):
  `EvidenceReparierer`, `SeitenScanner`, `TabellenBergung`, `DefektSicherung`
  und `ReparaturZiel`.
- **Kommandozeilen** im Ordner `tools/`:
  - `evidence_reparatur.py`
  - `integritaetssonde.py`
  - `schadensanalyse.py`
  - `sperrsonde.py`
- **Abgleich mit Fassung 1.2:** auf acht Testdateien sind das JSON-Protokoll
  und der Inhalt der neuen Datei gleich.

## 3. Build 777 — Register „Datenbank-Vorfaelle“

**Tabelle und Belege**
- Migration M041 legt in coordinator.db die Tabelle `db_vorfall` an. Sie ist
  rein additiv: kein Recht, kein Grant.
- Belege `db_vorfall_erfasst` und `db_vorfall_geprueft`. Der Eintragsbeleg
  traegt die SHA-256 des vollstaendigen Befunds.
- Ein Eintrag ist idempotent ueber `vorfall_uid`.

**Sicht, Kachel, Export, Hilfe**
- Sicht „Datenbank-Vorfälle“ unter Administration, lesbar mit `ops.view`.
- „Als geprüft markieren“ braucht `wartung.durchfuehren` und eine Pflichtnotiz.
  Der Vermerk ist einseitig und wird belegt.
- Kachel `db_vorfaelle`, Akten-Export und Hilfekapitel `dbvorfaelle`.

**Puffer**
- Ist coordinator.db nicht erreichbar, wird der Vorfall nach
  `<backup.dest_dir>/defekt/ausstehende_vorfaelle` gepuffert, eine JSON-Datei
  je Vorfall.
- Nachgetragen wird beim naechsten Start irgendeines Falls.
- Die Sicht und die Kachel zeigen wartende und unlesbare Pufferdateien immer
  an.

## 4. Build 778 — Startpruefung der evidence-Datei

Die Startpruefung ist die letzte Pruefung im `StartupChecker`. Sie laeuft in
dieser Reihenfolge:

1. **Puffer nachtragen.** Dieser Schritt verhindert den Start nie.
2. **Pruefen.** `integrity_check` laeuft nur lesend (`mode=ro`). Je nach
   Befund geht es so weiter:
   - **ok:** Der Start geht ohne Eintrag weiter.
   - **gesperrt oder unklar** (unklar heisst z. B. SQLITE_IOERR): Es wird
     nicht eingegriffen. Der Start wird verweigert und ein Eintrag
     `start_verweigert` angelegt.
   - **Unterbrochene Transaktion** (heisses Journal):
     1. Datei und Journal werden als `*_vor_zurueckrollen_defekt_<ts>.db`
        gesichert.
     2. SQLite rollt zurueck, danach wird erneut geprueft.
     3. Ist die Datei jetzt in Ordnung, entsteht der Eintrag
        `journal_zurueckgerollt`. Sonst geht es weiter wie bei einem Schaden.
   - **Schaden:** Es folgen die Schritte 3 bis 7.
3. **Sichern und reparieren.** `EvidenceReparierer` legt die Sicherung und
   die neue Datei an und schreibt das Protokoll.
4. **Vormerken.** Eine vorlaeufige Meldung kommt in den Puffer.
5. **Austauschen** mit `EvidenceAustausch`, auch bei „nicht freigegeben“:
   - Vorher wird geprueft, dass das Original byte-gleich mit der Sicherung
     ist.
   - Begleitdateien werden verschoben, nicht geloescht.
   - Ersetzt wird mit `os.replace`.
   - Scheitert ein Schritt, wird alles zurueckgenommen.
6. **Nachpruefen.** Die eingesetzte Datei wird erneut geprueft.
7. **Eintragen.** Der Eintrag `repariert_freigegeben` oder
   `repariert_nicht_freigegeben` ersetzt die Vormerkung. Der Start geht im
   selben Prozess weiter.

**Supportmodus**
- Es wird nichts gesichert, zurueckgerollt oder ersetzt. Es entsteht ein
  Eintrag, und der Start wird verweigert.
- Das stand so im Plan, wurde aber **nicht ausdruecklich bestaetigt.**

**Fehlerseite**
- Mit `--open-browser` oeffnet `main.py` bei jedem Abbruch von Schritt 6 eine
  eigenstaendige HTML-Seite aus dem Protokollordner.
- Das gilt fuer `StartupCheckError` ebenso wie fuer unerwartete Ausnahmen.

**forensic-Datei**
- Ein `sqlite3.DatabaseError` wird zu einer verstaendlichen Meldung statt zu
  einem Traceback.
- Die forensic-Datei wird bewusst **nicht** repariert: Sie ist versiegelt und
  wird aus Stage 2 neu bezogen.

## 4a. Unabhaengige Durchsicht vor der Auslieferung (separater Agent)

Diese Befunde sind in 778 behoben:

1. **Gesperrte Datei:** Sie erzeugte keinen Eintrag, entgegen der Vorgabe.
   Test ES06 hatte das Gegenteil festgeschrieben. Jetzt entsteht ein Eintrag.
2. **Sicherung ueberschrieben:** Nach dem Zurueckrollen ueberschrieb die
   Reparatur die Sicherung desselben Zeitstempels. Daneben blieb eine fremde
   `-journal`-Kopie liegen. Jetzt gilt: Eine Sicherung wird nie
   ueberschrieben (Zusatz `_2`), und die Sicherung vor dem Zurueckrollen
   hat einen eigenen Namen.
3. **Falsche Aussage „unverändert“:** In drei Abbruchpfaden war die Datei
   tatsaechlich zurueckgerollt oder ersetzt. Meldung und Fehlerseite nennen
   jetzt den wirklichen Zustand.
4. **Abbruch zwischen Austausch und Eintrag:** Der Vorfall waere
   unregistriert geblieben. Jetzt gibt es eine Vormerkung im Puffer, die beim
   naechsten Start nachgetragen wird.
5. **Voruebergehender Lesefehler (IOERR):** Er galt als Schaden und haette
   eine gesunde Datei ersetzt. Jetzt wird nach dem SQLite-Fehlernamen
   eingeordnet; „unklar“ heisst: kein Eingriff.
6. **Austausch:** Eine halbe `.tmp`-Datei bei voller Platte und ein
   verdeckter Fehler im Aufraeumen sind behoben.
7. **Ausnahmeklassen** stehen jetzt in eigenen Dateien.
8. **Austauschbefehle von `tools/evidence_reparatur.py`:**
   - Sie liessen das Original als `.ersetzt_*` in `data/evidence` liegen und
     uebergingen die Begleitdateien.
   - Jetzt kommt beides in den Ordner `defekt`.
9. **Arbeitskopie der Reparatur:** Bleibt sie liegen, wird das jetzt gemeldet.

Benannt, aber nicht behoben:

- Ein gleichzeitiger Start desselben Falls auf zwei Rechnern ist nur ueber
  `os.replace` unter Windows abgesichert.
- Eine **relative** `backup.dest_dir` loesen Webserver und Management jeweils
  gegen ihr eigenes Arbeitsverzeichnis auf.

## 5. Einspielen

Einzuspielen ist `aiw_webserver_778`.

**Migration M041 (coordinator.db)**
- Vorher pruefen:
  `python tools/pruefe_migrationskette.py --db <coordinator.db>`.
- Nach M041 sieht jede Person mit `ops.view` die neue Sicht.

**Rechte**
- Fuer den Pruefvermerk muss `wartung.durchfuehren` an die Leitungsrolle
  vergeben sein. Sonst zeigt die Sicht „Nur lesend“.

**Konfiguration**
- `backup.dest_dir` muss in `config.yaml` gesetzt und vom Webserver aus
  beschreibbar sein.
- Sonst wird bei einem Schaden der Start verweigert. Es entsteht trotzdem ein
  Eintrag (mit Fehlerseite).

## 6. Nicht in der VM geprueft

- Das Oeffnen einer `file:`-Adresse im PROD-Browser.
- `os.replace` gegen eine unter Windows geoeffnete Datei. Das ist in ES07
  nur per mock nachgestellt.
- Die Dauer von `integrity_check` auf dem PROD-Laufwerk. Lokal gemessen:
  86 MB in 614 ms.

## 7. Offen

1. Supportmodus-Verhalten bestaetigen: nichts reparieren, Eintrag, Start
   verweigern.
2. Vorgaenge `280ce9c4` und `f61df99c` schliessen, sobald der Build in PROD
   abgenommen ist.
3. `management/migration_fleet/executor.py`: Flotten-Companion uebergibt
   `expected_deltas={}` (Issue `c90c9977`). Unveraendert offen.

# Regelwerk AIW — Kommandozeilen-Werkzeuge

**Stand:** Build 607 · 2026-07-31

## 1. Adressat

Eine technisch versierte Person, die Systeme aufsetzt, betreut und in einem einsatztauglichen Zustand hält; vertraut mit dem Betriebssystem und mit Python; in der Lage, komplexe Systemanbindungen und Datenmigrationen durchzuführen (Festlegung mc 2026-07-31).

Daraus folgt **Regel H-2**: In der CLI-Hilfe wird Fachsprache benutzt. `coordinator.db` heißt `coordinator.db`. Regel H-1 (Anwendersprache) gilt hier nicht — Einzelheiten in `rules-help.md`.

## 2. Jedes Werkzeug hat einen Katalogeintrag

`management/help/cli_katalog.py` führt **jedes** Kommandozeilen-Werkzeug mit: Aufrufform, Zweck in einem Satz, Art (lesend/schreibend/gemischt) **je Unterbefehl**, berührte Datenbanken samt Öffnungsart, Betriebsvoraussetzung, Belegpflicht, erzeugte Ausgabedateien und — wo nötig — einen Hinweis, den man vor dem Aufruf gelesen haben muss.

**Die Vollzähligkeit ist maschinell erzwungen.** Der Katalog wird gegen das Dateisystem abgeglichen, in beide Richtungen: kein Werkzeug ohne Eintrag, kein Eintrag ohne Werkzeug.
*Durchsetzung:* `tests/test_help_cli_katalog.py` CK02. Die Scan-Regel steht an einer Stelle im Test und ist selbst geprüft (CK03) — eine Regel, die zu eng greift, wäre grün, weil sie nichts sieht.

**Was als Werkzeug gilt:** `management/**/*_admin.py`, `management/**/*_cli.py`, `management/*.py`, `tools/*.py` und `*.py` im Wurzelverzeichnis.

**Ungeklärte Dateien** kommen auf eine ausdrückliche, begründete Liste, die einen Vorgang nennen muss und bis zum Abschluss der Baustelle leer sein muss (CK09/CK10). Sie sind damit nicht mehr blockierend, aber weiterhin sichtbar.

## 3. Die Art eines Aufrufs

**„Lesend" heißt: keine Datenbank wird verändert.** Eine erzeugte Ausgabedatei (HTML, PDF, XLSX) macht ein Werkzeug **nicht** schreibend; sie steht in einem eigenen Feld. Diese Unterscheidung ist keine Wortklauberei — sie entscheidet, ob ein Werkzeug den Migrationsvorbehalt berührt.

**Die Art wird je Unterbefehl geführt, nicht je Werkzeug.** Die meisten Werkzeuge sind gemischt, und die Frage „ändert *dieser* Aufruf etwas?" ist die, die vor dem Drücken der Eingabetaste zählt.
*Durchsetzung:* CK04 — `art` und Unterbefehle dürfen einander nicht widersprechen. Wer „lesend" liest und dann eine Änderung ausführt, ist die schlimmste Sorte Fehler in diesem Katalog.

## 4. Trockenlauf ist die Vorgabe

Jedes Werkzeug, das etwas verändert, tut das erst nach einem **ausdrücklichen Handgriff** — `--apply`, `--ausfuehren`, `--confirm`. Ohne ihn läuft es trocken und zeigt nur, was geschähe.

Bewährte Verschärfungen im Bestand: `repair_block_types` verlangt zusätzlich die Bestätigung, dass ein geprüftes Backup besteht, und bricht sonst ab. `lkae_admin` tut ohne Freigabeschalter gar nichts. `migration_fleet_admin` prüft vor dem scharfen Lauf vier Tore und verlangt eine Sicherung.

## 5. Exit-Codes sind Auskünfte, nicht nur Fehler

Mehrere Werkzeuge melden mit einem Code ungleich 0 einen **Befund**:

| Beispiel | Code | Bedeutung |
|---|---|---|
| `qs_admin nachziehen` | 1 | Abweichung gefunden — kein Programmfehler |
| `results_admin coverage` | 2 | nie bewertete Fälle — damit ein Skript es sieht |
| `index_cli --auffrischen` | 2 | gelaufen, aber mindestens ein Fall unvollständig |
| `external_admin list` | 2 | rote Ampeln vorhanden |
| `pruefe_migrationskette` | 2 / 3 | Lücke / unbekannte Version |
| `maintenance enter` | 2 | gesetzt, aber **nicht** vollständig bestätigt — kein freigegebenes Fenster |

Der Katalogeintrag nennt sie, damit niemand einen Befund für einen Absturz hält.

## 6. Beispiele werden gefahren, bevor sie geschrieben werden

Grundregel 9 sinngemäß auf die Dokumentation angewandt: **Kein Beispielaufruf kommt in den Katalog, der nicht vorher gegen Wegwerf-Testdaten tatsächlich gelaufen ist.** Ein Beispiel, das nicht funktioniert, ist schlimmer als keines — es kostet die Zeit dessen, der ihm vertraut.

## 7. Wartungsvorbehalt

> **Stand Build 612: dieser Abschnitt gilt.** Die Stufeneinteilung ist von mc am 2026-07-31 bestätigt (`Vermerk_Wartungsvorbehalt_Analyse_K1_K8_v1_0.md`), das Bauteil `maintenance/wartungsvorbehalt.py` ist gebaut, und alle fünf Werkzeuge der Stufe A setzen es ein. *Durchsetzung:* `tests/test_wartungsvorbehalt_einbau.py` — EB01–EB05 am Quelltext, EB06–EB10 am Verhalten.

**Der Anlass:** Bei sieben Werkzeugen ließ sich aus dem Bestand nicht beantworten, ob sie neben dem laufenden Betrieb gefahrlos sind. Zwei andere sagen es ausdrücklich — `convert_journal_mode` („braucht exklusiven Zugriff"), `backup_admin` („für den laufenden Betrieb gebaut"). Dazwischen liegt eine Lücke, die geraten werden müsste, wenn man sie nicht klärt.

**Die drei Stufen:**

- **Stufe A — Wartungsfenster erforderlich.** Das Werkzeug nimmt exklusive Sperren, tauscht Dateien aus, ändert Dateiköpfe oder schreibt in Datenbanken, die ein laufender Dienst geöffnet hält.
- **Stufe B — betriebsverträglich.** Das Werkzeug schreibt, aber so, dass ein laufender Dienst nicht gestört wird (kurze Transaktionen, keine exklusiven Sperren, kein Dateiaustausch).
- **Stufe C — rein lesend.** Kein Vorbehalt.

**Die sechs Werkzeuge der Stufe A** (fünf bestätigt 2026-07-31 und eingebaut in Build 612, das sechste nachgetragen in Build 615): `management/migrate.py`, `tools/migrate-dbs.py --apply`, `migration_fleet_admin companion --confirm`, `management/consolidate_default_db.py`, `tools/forensic_index_upgrade.py --ausfuehren`, `tools/convert_journal_mode.py --apply`. **Stufe B:** `management/search/index_cli.py` — es schreibt ausschließlich in `search_index.db`, die kein anderer Dienst offen hält.

> **Warum das sechste erst nachträglich kam — und was daraus folgt.** Die Analyse K1–K8 untersuchte die sieben Werkzeuge, bei denen sich die Frage *nicht* aus dem Bestand beantworten ließ. `convert_journal_mode` war nicht darunter, weil sein Dateikopf die Antwort zu geben schien: „braucht exklusiven Zugriff". **Eine Zusage im Kommentar ist aber keine technische Sperre.** Genau dieser Befundtyp liegt schon einmal im Eingang (Issue `906ede75`: zwei Auswertungswerkzeuge öffnen die `coordinator.db` schreibfähig, obwohl ihr Kopf das Gegenteil zusichert).
>
> **Die Lehre für künftige Einstufungen:** Ein Werkzeug ist nicht deshalb geklärt, weil es *sagt*, was es braucht. Die Frage lautet nicht „steht es im Kopf?", sondern „greift es?". Für `backup_admin` — das andere Werkzeug, das sich selbst einordnet („für den laufenden Betrieb gebaut") — ist die Gegenrichtung zu prüfen: dort ist die Zusage entlastend, und auch sie ist bislang nur eine Zusage.

**Der Vorbehalt greift nur am scharfen Lauf.** Trockenübung, Vorschau und Plan bleiben frei. Das ist keine Bequemlichkeit, sondern Teil der Sicherung: eine Vorschau, die erst nach einer Rückfrage kommt, wird übersprungen — und dann sieht niemand mehr, was passieren würde. *Durchsetzung:* EB08 und EB09.

**Und er greift nur, wo er hingehört.** Ein Vorbehalt an einer Stelle ohne Anlass erzeugt Rückfragen ohne Anlass, und wer oft ohne Anlass gefragt wird, tippt das Wort irgendwann, ohne zu lesen. Deshalb prüft EB04, dass `index_cli` (Stufe B) das Bauteil **nicht** aufruft.

**Jedes Werkzeug nennt die betroffenen Dateien konkret**, nicht pauschal — `migrate-dbs` etwa nur die Datenbanken, die dieser Lauf wirklich anfasst, nicht alle offenen. Die Datenwurzel findet `datenwurzel()` für alle fünf einheitlich, statt sie fünfmal zu raten.

### Die Durchsetzung bei Stufe A

Das gemeinsame Bauteil ist `maintenance/wartungsvorbehalt.py`. Ein Werkzeug ruft es mit den **konkret betroffenen Dateien** auf und wertet drei Felder aus:

```python
befund = wartungsvorbehalt(data_dir, betroffene, werkzeug="migrate",
                           was_geschieht="baut Tabellen der coordinator.db um")
print(befund.text)
if not befund.erlaubt:
    return befund.rueckgabewert
```

Der Ablauf in der Reihenfolge, in der er stattfindet:

Die Sperrprobe kennt **drei** Zustände je Datei, nicht zwei: `ruhig`, `belegt`, `unpruefbar`.

1. **Sperrprobe zuerst, immer.** Jede betroffene Datei wird einzeln probeweise exklusiv gesperrt (`BEGIN EXCLUSIVE` und sofortiges Zurückrollen). Ist auch nur eine **belegt**: **Abbruch unter Nennung der Datei, ohne Rückfrage.** Dass eine Datei belegt ist, ist ein Messwert und keine Ermessensfrage.
2. **Alle ruhig, keine unprüfbar, und ein Wartungsfenster deckt sie ab:** durchlaufen.
3. **Sonst:** Sachlage ausgeben, dann das Wort `OHNE WARTUNGSFENSTER` abfragen. Ein Tastendruck ist eine Reflexbewegung, ein getipptes Wort ist eine Entscheidung. **Ein Versuch**, keine Wiederholung — sonst wird aus der Entscheidung ein Geschicklichkeitsspiel.
4. **Kein Terminal** (Skript, geplante Aufgabe): immer Abbruch.

**Warum die Sperrprobe vor der Fensterfrage steht:** `maintenance.py enter --ziel all` löst `all` nur auf die Datenbanken der **obersten** Ebene auf; die Fall-Datenbanken in `evidence/`, `forensic/` und `assets/` sind nicht dabei (Befund 1 des Vermerks). Ein gesetztes Fenster ist damit kein Nachweis dafür, dass eine `evidence_<uid>.db` ruhig ist. **Das Fenster belegt die Absicht, die Sperre belegt die Ruhe — und nur die Ruhe darf entscheiden.**

### Der dritte Zustand: `unpruefbar` (Build 611)

**Auf einer schreibgeschützten Datei ist die Sperrprobe blind.** Sie meldet dort *immer* „exklusiv erhalten" — auch dann, wenn ein Leser oder sogar ein Schreiber die Datei hält. SQLite stuft eine nicht beschreibbare Datei still auf nur-lesend zurück, und eine nur lesende Verbindung nimmt beim `BEGIN EXCLUSIVE` keine Sperre; der Befehl gelingt folgenlos. Nachgestellt am 2026-07-31 als Nicht-root-Eigentümer, Journalmodus `delete`:

| Datei | Halter | Ergebnis der Probe | |
|---|---|---|---|
| schreibbar | Leser (SHARED) | `(False, 'database is locked')` | richtig |
| versiegelt | Leser (SHARED) | `(True, 'exklusiv erhalten')` | **blind** |
| versiegelt | Schreiber (EXCLUSIVE) | `(True, 'exklusiv erhalten')` | **blind** |

Betroffen sind genau die versiegelten `forensic_<uid>.db` — also genau die Dateien, die `forensic_index_upgrade --ausfuehren` entsiegelt und beschreibt.

**Folge:** Eine schreibgeschützte Datei wird gar nicht erst geprobt (eine Probe, deren Ergebnis feststeht, ist keine), sondern als `unpruefbar` geführt, unter eigener Überschrift benannt — und sie **erzwingt die Wortabfrage auch bei gesetztem Wartungsfenster**. Über eine Datei, deren Ruhe niemand messen kann, hat auch das Fenster nichts ausgesagt. Die Freigabezeile vermerkt das ausdrücklich, damit im Protokoll erkennbar bleibt, dass dort eine Entscheidung getroffen und kein Messwert abgelesen wurde.

*Durchsetzung:* WV22 hält den Befund selbst als Test fest — er schlägt an, wenn SQLite sich eines Tages anders verhält, und dann darf die Sonderbehandlung wieder verschwinden. WV25–WV29 decken die Folge auf jedem System ab.

**Der Befund betrifft `exklusiv_pruefen` selbst**, also auch `tools/maintenance.py enter/status`. Dort ist er **nicht** behoben: eine Änderung an der gemeinsamen Funktion würde das Verhalten eines produktiven Werkzeugs ändern und ist eine eigene Entscheidung. Vorgang: siehe Issue-Tracker.

**Rückgabewert 3** für alle drei Abbruchgründe, mit derselben Zusicherung: es wurde nichts geschrieben. Getrennte Werte lüden dazu ein, den Fall „nur das Wort fehlte" im Skript automatisch zu wiederholen — genau der Automatismus, den die Wortabfrage verhindern soll. Der Grund steht im Text, nicht im Zahlenwert.

**Was das Bauteil bewusst nicht hat:** keine Option zum Überspringen (`--ja`, `--force`) — eine Option wandert in ein Skript, und dort wäre der Vorbehalt wirkungslos. Keinen Schreibzugriff — es läuft, wenn noch nichts entschieden ist, und importiert nicht einmal `sqlite3` (`tests/test_maintenance_wartungsvorbehalt.py` WV18 prüft das am Quelltext). Und die Bestätigung ist an die **Standardeingabe** gebunden, nicht an die Ausgabe: sonst genügte `echo "OHNE WARTUNGSFENSTER" | python …`.

**Im Zweifel die strengere Stufe.** Eine tägliche Sicherung macht einen Datenverlust nicht harmlos, sie macht ihn nur reparabel — und das kostet Zeit, die im Ermittlungsbetrieb fehlt.

## 8. Das Dachwerkzeug

`python tools/hilfe.py` ist der Einstieg: `liste`, `zeige <kennung>`, `suche <begriff>`, `stand`.

Es **führt nichts aus, öffnet nichts und nimmt keine Sperre** — es gibt Text aus, sonst nichts. Damit ist es in jedem Betriebszustand aufrufbar, auch mitten in einer Migration.
*Durchsetzung:* `tests/test_help_cli_text.py` CT11 prüft am Quelltext, dass weder `sqlite3` noch `subprocess` noch `os.system` vorkommen — ein Verhaltenstest würde nur zeigen, dass bei *diesem* Aufruf nichts geöffnet wurde.

**Jeder gezeigte Eintrag endet mit dem `--help`-Aufruf des Zielwerkzeugs.** Der Katalog sagt, wozu ein Werkzeug da ist; die vollständige Liste der Optionen sagt das Werkzeug selbst — und zwar immer aktuell, während ein abgeschriebener Optionsblock veralten würde.

**Ein Leerbefund der Suche liefert Rückgabewert 1.** Ein Skript kann ihn damit erkennen, ohne die Ausgabe zu lesen; die Ausgabe sagt zusätzlich ausdrücklich, *worin* gesucht wurde — nämlich im Katalogtext und nicht im Quelltext der Werkzeuge.

### Form der Ausgabe

| Regel | Grund |
|---|---|
| **Reines ASCII** — keine Umlaute, kein ß | Die Windows-Eingabeaufforderung läuft nicht zwingend in UTF-8; ein Umlaut wird dort zum Kästchen. Der gesamte Katalog folgt dem Hausstil der argparse-Beschreibungen („Uebersicht", „gueltig"). |
| **Keine Escape-Sequenzen** — keine Farben, kein Fettdruck | Die Ausgabe muss sich in eine Datei umleiten und in einen Vermerk einfügen lassen. |
| **78 Zeichen** | Zwei weniger als die übliche Konsolenbreite, damit der Umbruch der Konsole nichts zerreißt. |
| **Ein zu langes Wort wird nicht zerschnitten** | Eine zerschnittene Kennung oder ein zerschnittener Pfad ist unbrauchbar — dann lieber eine zu lange Zeile, die man kopieren kann. |

*Durchsetzung:* CT08 (ASCII über alle erzeugbaren Ausgaben), CT09 (Breite, mit ausdrücklich geprüfter Ausnahme für unteilbare Wörter), CT01/CT02 (Umbruch und Spalten).

## 9. epilog (H20/H21, noch nicht ausgerollt)

Jedes Werkzeug bekommt in seinem argparse-Parser einen `epilog` mit ein bis drei Beispielaufrufen. Diese Beispiele stammen aus dem Katalog — kein dritter Bestand. Die Änderung ist rein additiv: kein Werkzeug ändert dabei Logik, Parameter oder Verhalten.

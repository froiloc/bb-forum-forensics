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

## 7. Wartungsvorbehalt — VORSCHLAG, noch nicht entschieden

> Dieser Abschnitt beschreibt einen **Vorschlag**. Er wird verbindlich, wenn Issue `da6c16d0-ef1e-4052-8eb1-526c647de613` entschieden ist. Bis dahin ist er als Vorschlag zu lesen und nicht als geltende Regel.

**Der Anlass:** Bei sieben Werkzeugen ließ sich aus dem Bestand nicht beantworten, ob sie neben dem laufenden Betrieb gefahrlos sind. Zwei andere sagen es ausdrücklich — `convert_journal_mode` („braucht exklusiven Zugriff"), `backup_admin` („für den laufenden Betrieb gebaut"). Dazwischen liegt eine Lücke, die geraten werden müsste, wenn man sie nicht klärt.

**Die drei Stufen:**

- **Stufe A — Wartungsfenster erforderlich.** Das Werkzeug nimmt exklusive Sperren, tauscht Dateien aus, ändert Dateiköpfe oder schreibt in Datenbanken, die ein laufender Dienst geöffnet hält.
- **Stufe B — betriebsverträglich.** Das Werkzeug schreibt, aber so, dass ein laufender Dienst nicht gestört wird (kurze Transaktionen, keine exklusiven Sperren, kein Dateiaustausch).
- **Stufe C — rein lesend.** Kein Vorbehalt.

**Die Durchsetzung bei Stufe A** (Vorschlag): ein gemeinsames Bauteil prüft vor dem scharfen Lauf, ob ein Wartungsfenster aktiv ist. Ist es aktiv, läuft das Werkzeug. Ist es **nicht** aktiv, bricht es ab — es sei denn, die aufrufende Person tippt ein vollständiges Wort zur Bestätigung. Kein bloßer Tastendruck: ein Tastendruck ist eine Reflexbewegung, ein getipptes Wort ist eine Entscheidung.

**Im Zweifel die strengere Stufe.** Eine tägliche Sicherung macht einen Datenverlust nicht harmlos, sie macht ihn nur reparabel — und das kostet Zeit, die im Ermittlungsbetrieb fehlt.

## 8. epilog (H20/H21, noch nicht ausgerollt)

Jedes Werkzeug bekommt in seinem argparse-Parser einen `epilog` mit ein bis drei Beispielaufrufen. Diese Beispiele stammen aus dem Katalog — kein dritter Bestand. Die Änderung ist rein additiv: kein Werkzeug ändert dabei Logik, Parameter oder Verhalten.

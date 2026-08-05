# Starten

```
cd issue-tracker
python run.py
```

Die Serverdatei heißt seit Build 650 `tracker_server.py` (Vorgang `7c7a738f`);
`server.py` hieß wie das Paket `server/` des Webservers und wurde beim Laden
aus dem Wurzelverzeichnis heraus mit diesem verwechselt.

# Was sich in Build 673 geändert hat

**Zwei Änderungen zum Vorgang `7d3c1a95` — beide betreffen den Umgang mit
`merge-new-tickets.sh`.**

1. **Ein reiner Historien-Nachtrag kommt jetzt an.** Bis Build 672 kannte
   `merge.py` für einen bereits vorhandenen Vorgang nur zwei Wege: *neu*
   (Kennung unbekannt) und *Konflikt* (eines von acht Vergleichsfeldern weicht
   ab). Eine gelieferte Fassung, die ausschließlich Update-Zeilen nachträgt,
   nahm keinen der beiden — es wurde nichts geschrieben, und das Werkzeug
   meldete trotzdem Erfolg. Neu ist ein dritter Zweig mit dem Konflikttyp
   `UPDATE_TIMELINE`; er wird **immer** über `MERGE_UPDATES` gelöst, auch bei
   `--auto-resolve target`. Bei diesem Typ ist per Konstruktion kein Feld
   abweichend — es gibt nichts zu entscheiden, nur etwas anzuhängen.

2. **Gelöscht wird erst nach der Gegenprobe.** `merge-new-tickets.sh` ruft nach
   dem Einmischen `pruefe_einmischung.py` auf. Das Skript sieht im **Bestand**
   nach, ob jede Kennung und jede Update-Zeile der Quelldatei dort steht, und
   erst dann wird die Quelldatei entfernt. Fällt die Probe, bricht der Lauf ab,
   die Datei bleibt liegen, und der EXIT-Trap erklärt die Lage.

   *Warum das wichtiger ist als Punkt 1:* Punkt 1 schließt eine bekannte Lücke.
   Punkt 2 sorgt dafür, dass die **nächste** Lücke keine Daten mehr kostet. Eine
   Erfolgsmeldung ist eine Behauptung; der Bestand ist der Beleg. Dasselbe
   Verhältnis wie zwischen `bundle_bauen.sh` und `pruefe_lieferung.sh`.

   Aufruf von Hand, falls einmal getrennt nötig:

   ```
   python pruefe_einmischung.py <quelldatei.json> [--bestand data/issues.json]
   ```

   Rückgabe: `0` alles angekommen · `1` etwas fehlt, Datei behalten ·
   `2` Aufruf-/Lesefehler.

Auf der **Erstellerseite** wacht seit Build 671 zusätzlich `IT06`
(`tests/test_issue_tracker_eintraege.py`): er meldet einen Nachtrag, der mangels
Feldabweichung nicht ankäme, schon vor der Lieferung.

# Was sich in Build 642 geändert hat

Vier Punkte, die den Umgang mit dem Werkzeug betreffen:

1. **`--output` fasst die Zieldatei nicht mehr an.** Bis Build 641 hat
   `merge.py --output ergebnis.json` zuerst `data/issues.json` überschrieben und
   das Ergebnis danach kopiert. Wer die Bestandsdatei schonen wollte, hat sie
   genau damit verändert. Jetzt wird ausschließlich die Ausgabedatei
   geschrieben; eine Sicherung entsteht in diesem Fall nicht, weil es nichts zu
   sichern gibt.

2. **Eine ungültige Eingangsdatei bricht den Merge ab, bevor etwas geschrieben
   wird.** Bis Build 641 wurde der ungültige Vorgang übersprungen und der Rest
   gespeichert — mit `✅ MERGE ABGESCHLOSSEN` am Ende. Das verstößt gegen
   Grundregel 1. Wer den Rest trotzdem einpflegen will, sagt `--force`; dann
   steht die Auslassung als Warnung im Ergebnis.

3. **Der Validator prüft mehr:** die Versionsmuster aus dem Schema und die
   Verweise in `related_to`. Verweise müssen die **volle UUID** führen, nicht
   die 8-Zeichen-Kurzform aus der Bildschirmausgabe. Eine Kurzform wird von der
   Weboberfläche nie aufgelöst — der Verweis steht dann in der Datei und ist
   nirgends zu sehen.

4. **Geschrieben wird atomar** (`json_safe_writer.py`), und **jeder räumt nur
   seine eigenen Sicherungen ab** (`backup_names.py`). Der Server hat bis
   Build 641 auch die `issues_backup_before_merge_*.json` gelöscht.

## Verkürzte Verweise reparieren

```
cd issue-tracker
python repair_related_ids.py            # Trockenlauf - ändert nichts
python repair_related_ids.py --apply    # sichert, dann ändert
```

Aufgelöst wird nur, was **eindeutig** ist. Mehrdeutige und unbekannte Verweise
bleiben stehen und werden einzeln benannt — geraten wird nicht.

Exit-Codes: `0` sauber bzw. behoben, `1` Mängel offen, `2` technischer Fehler.

# Anlegen neuer Einträge

Bitte nicht die Datei `issue-tracker/data/issues.json` direkt bearbeiten. Diese kann jederzeit von anderen geändert werden.

Es gibt ein Migrationsskript, das bestehende Einträge ändern kann und neue Einträge aufnimmt. Das Schema für solch eine Datei ist identisch mit dem herkömmlichen Schema in `issue-tracker.schema.json`.

Bestehende im Verzeichnis `issue-tracker` abgelegte Dateien mit dem Namen `eingang*.json` werden zu gegebener Zeit, im Regelfall vor jedem Git-Commit und -Push, eingepflegt.

# Einpflegen neuer Einträge
```
python merge.py --help
usage: merge.py [-h] [--target TARGET] [--output OUTPUT] [--dry-run] [--auto-resolve {newer,target,source,merge}] [--force] [--no-backup]
                [--verbose] [--stdin] [--validate-only]
                [source]

🔀 Issue Tracker Merge Tool - Führt Issue-JSON-Dateien zusammen

positional arguments:
  source                Pfad zur Import-JSON-Datei

options:
  -h, --help            show this help message and exit
  --target, -t TARGET   Pfad zur Ziel-Issue-Datei (Standard: data/issues.json)
  --output, -o OUTPUT   Pfad für die Ausgabedatei (optional, sonst wird Ziel überschrieben)
  --dry-run, -d         Nur Vorschau, keine Änderungen vornehmen
  --auto-resolve, -a {newer,target,source,merge}
                        Automatische Konfliktlösung (newer|target|source|merge)
  --force, -f           Ohne Rückfragen durchführen
  --no-backup           Kein Backup vor dem Merge erstellen
  --verbose, -v         Ausführliche Ausgabe
  --stdin               JSON von stdin lesen (für Pipe-Usage)
  --validate-only       Nur Validierung der Quelldatei, kein Merge

Beispiele:
  # Interaktiver Merge
  python merge.py neue_issues.json

  # Dry-Run (Vorschau ohne Änderungen)
  python merge.py neue_issues.json --dry-run

  # Automatisch neuere Version übernehmen
  python merge.py neue_issues.json --auto-resolve newer

  # Issues aus Git-Patch extrahieren und mergen
  git diff HEAD~1 -- data/issues.json | python merge.py --stdin

  # Bestimmte Ausgabedatei verwenden
  python merge.py neue_issues.json --target custom/issues.json
```

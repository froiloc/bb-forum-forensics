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

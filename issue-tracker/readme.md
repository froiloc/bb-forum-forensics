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

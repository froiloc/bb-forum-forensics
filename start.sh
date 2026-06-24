#!/bin/bash

# Bash 4.0+ erforderlich für einige Funktionen
# For-Schleife über alle assets_*.db Dateien im data/assets Verzeichnis
for file in ./data/assets/assets_*.db; do
    # Prüfen ob Dateien existieren (falls keine gefunden werden)
    [ -e "$file" ] || continue
    
    # Dateiname ohne Erweiterung und Pfad extrahieren
    filename=$(basename "$file" .db)
    
    # ID aus dem Dateinamen extrahieren (alles nach "assets_")
    id="${filename#assets_}"

    # Webbrowser finden
    webbrowser="$(which chromium-browser || which firefox || which google-chrome)"
    
    # Webbrowser im Hintergrund starten
    ${webbrowser} http://127.0.0.2:8080/ &
    
    # Python Skript im Hintergrund starten
    python main.py --user-id "$id" &
done

# Auf alle Hintergrundprozesse warten (optional)
wait

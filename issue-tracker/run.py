#!/usr/bin/env python3
"""
Einfaches Start-Script für den Issue Tracker
Verwendung: python run.py

BUILD 650 (Vorgang 7c7a738f): Die Serverdatei heisst jetzt
'tracker_server.py' und nicht mehr 'server.py'. Grund: Das Paket fuehrt ein
eigenes Verzeichnis 'server/' (server/shell_handler.py und weitere). Sobald
das Wurzelverzeichnis im Suchpfad steht - im Regressionslauf steht es immer
dort -, lieferte 'import server' das Paket des Webservers statt der Datei des
Trackers. Der Fehler lautete "module 'server' has no attribute 'app'", und im
Verbund hat sich eine ganze Testsuite deswegen still uebersprungen.

Im Betrieb hat das nie gestoert, weil der Start aus DIESEM Verzeichnis
heraus erfolgt (Auskunft mc, 2026-08-02). Es war eine Falle fuer den, der es
spaeter anders macht - jetzt ist sie weg statt nur beschildert.
"""

import subprocess
import sys
from pathlib import Path

def main():
    # Prüfen ob .env existiert
    env_file = Path(".env")
    if not env_file.exists():
        print("⚠️  Keine .env-Datei gefunden. Erstelle Standard-Konfiguration...")
        env_file.write_text("""# Server-Konfiguration
HOST=127.0.0.1
PORT=8000
RELOAD=true
DEBUG=false

# Pfade
DATA_DIR=./data
TEMPLATES_DIR=./templates
ISSUES_FILE=./data/issues.json

# UI
TITLE=Software Issue Tracker
MAX_TITLE_LENGTH=80
ITEMS_PER_PAGE=50

# Backup
AUTO_BACKUP=true
BACKUP_DIR=./backups
""")
        print("✅ .env-Datei erstellt. Du kannst sie jetzt anpassen.")
    
    # Prüfen ob Abhängigkeiten installiert sind
    try:
        import fastapi
        import uvicorn
        import jinja2
        import dotenv
    except ImportError as e:
        print(f"❌ Fehlende Abhängigkeit: {e}")
        print("Installiere mit: pip install fastapi uvicorn jinja2 python-dotenv python-multipart")
        sys.exit(1)
    
    # Server starten
    print("🚀 Starte Issue Tracker...")
    try:
        # Wichtig: Server als Subprozess starten für korrektes Reloading
        subprocess.run([sys.executable, "tracker_server.py"])
    except KeyboardInterrupt:
        print("\n👋 Server gestoppt.")

if __name__ == "__main__":
    main()
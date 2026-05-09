#!/usr/bin/env bash

# === Konfiguration ===
CLIPBOARD_SAVER="/opt/aiw_webserver/debug/clipboard-saver.sh"
LOG_FILE="/tmp/clipboard_watchdog.log"
CLIPBOARD_TYPE="clipboard"  # oder "primary" für mittlere Maustaste

# === Prüfe Voraussetzungen ===
if ! command -v clipnotify &> /dev/null; then
    echo "❌ clipnotify nicht gefunden. Installation: sudo apt install clipnotify"
    exit 1
fi

if [ ! -f "$CLIPBOARD_SAVER" ]; then
    echo "❌ Speicher-Skript nicht gefunden: $CLIPBOARD_SAVER"
    exit 1
fi

# === Logging Funktion ===
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# === Hauptloop ===
log "📋 Clipboard Watchdog gestartet"
log "Überwache: $CLIPBOARD_TYPE"
log "Rufe auf: $CLIPBOARD_SAVER"

while clipnotify -s "$CLIPBOARD_TYPE"; do
    log "🔔 Clipboard-Änderung erkannt"
    
    # Führe dein Skript aus
    if "$CLIPBOARD_SAVER"; then
        log "✅ Skript erfolgreich ausgeführt"
    else
        log "❌ Skript-Fehler (Exit-Code: $?)"
    fi
done

log "⚠️ Clipnotify beendet, Watchdog stoppt"

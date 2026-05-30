#!/usr/bin/env bash

# --- Konfiguration ---
# Definiere hier deine Regeln: (regex_pattern, ziel_datei)
# Die Reihenfolge der Regeln ist wichtig! Das erste Match gewinnt.
ROOTDIR="/opt/aiw_webserver"

declare -A REGELN=(
    ['\[Forensic\] Server|\[web-debug\]|Failed to load resource:|Navigated to http://127.0.0.2:8080/_forensic/report']="${ROOTDIR}/debug/devtools-console/last.log"
    ['"name": "WebInspector"']="${ROOTDIR}/debug/devtools-network/last.har"
    ['^# Fehler ']="${ROOTDIR}/debug/bugs-and-tasks/last.md"
    ['^<html ']="${ROOTDIR}/debug/dom-dump/last-html.html"
    ['<body id="report-editor-body"']="${ROOTDIR}/debug/dom-dump/last-body.html"
    ['<main id="report-main-col">']="${ROOTDIR}/debug/dom-dump/last-main.html"
    ['<aside id="support-sidebar"']="${ROOTDIR}/debug/dom-dump/last-sidebar.html"
    ['Logging initialisiert — Level: DEBUG']="${ROOTDIR}/debug/webserver-log/last.log"
)

PFAD_SCREENSHOTS="${ROOTDIR}/debug/screenshots/screenshot_$(date +%Y%m%d_%H%M%S).png"

# --- Hilfsfunktionen ---
zeige_verfuegbare_formate() {
    echo "Verfügbare Formate in der Zwischenablage:"
    xclip -selection clipboard -o -t TARGETS 2>/dev/null | tr '\t' '\n' | sed 's/^/  - /'
}

ist_bild_in_zwischenablage() {
    # Prüft, ob ein Bildformat in der Zwischenablage verfügbar ist
    xclip -selection clipboard -o -t TARGETS 2>/dev/null | grep -qiE "image/(png|jpg|jpeg|bmp|gif)"
}

bild_speichern() {
    echo "📸 Bild erkannt, speichere als: $PFAD_SCREENSHOTS"
    
    # Versuche verschiedene Bildformate (Priorität PNG > JPEG > usw.)
    for format in image/png image/jpeg image/jpg image/bmp image/gif; do
        if xclip -selection clipboard -t "$format" -o 2>/dev/null > "$PFAD_SCREENSHOTS"; then
            if [ -s "$PFAD_SCREENSHOTS" ]; then
                echo "✅ Bild erfolgreich gespeichert unter: $PFAD_SCREENSHOTS"
                return 0
            fi
        fi
    done
    
    echo "❌ Fehler: Konnte kein Bild aus der Zwischenablage extrahieren"
    return 1
}

text_aus_zwischenablage() {
    xclip -selection clipboard -o 2>/dev/null
}

pruefe_text_regeln() {
    local text="$1"
    
    for pattern in "${!REGELN[@]}"; do
        if [[ "$text" =~ $pattern ]]; then
            ziel_datei="${REGELN[$pattern]}"
            echo "📝 Regelmatch: '$pattern' -> Speichere in: $ziel_datei"
            xclip -selection clipboard -o > "$ziel_datei"
            echo "✅ Erfolgreich gespeichert in: $ziel_datei"
            return 0
        fi
    done
    
    return 1
}

# --- Hauptlogik ---

# Prüfe, ob xclip installiert ist
if ! command -v xclip &> /dev/null; then
    echo "❌ Fehler: xclip ist nicht installiert."
    echo "Installiere es mit: sudo apt install xclip  # Debian/Ubuntu"
    exit 1
fi

# Prüfe, ob etwas in der Zwischenablage ist
if ! text_aus_zwischenablage > /dev/null && ! ist_bild_in_zwischenablage; then
    echo "❌ Fehler: Zwischenablage ist leer oder enthält kein unterstütztes Format"
    zeige_verfuegbare_formate
    exit 1
fi

# 1. Prüfe zuerst auf Bild
if ist_bild_in_zwischenablage; then
    bild_speichern
    exit $?
fi

# 2. Prüfe auf Text mit Regex-Regeln
TEXT_INHALT=$(text_aus_zwischenablage)
if [ -n "$TEXT_INHALT" ]; then
    # Extrahiere die ersten 100 Zeichen für Regex-Test
    ERSTE_100_ZEICHEN=$(echo "$TEXT_INHALT" | head -c 100)
    
    if pruefe_text_regeln "$ERSTE_100_ZEICHEN"; then
        exit 0
    else
        echo "❌ Fehler: Keine Regex-Regel matcht die ersten 100 Zeichen der Zwischenablage"
        echo ""
        echo "Erste 100 Zeichen des Inhalts:"
        echo "----------------------------------------"
        echo "$ERSTE_100_ZEICHEN"
        echo "----------------------------------------"
        echo ""
        echo "Definierte Regeln waren:"
        for pattern in "${!REGELN[@]}"; do
            echo "  - '$pattern' -> ${REGELN[$pattern]}"
        done
        exit 1
    fi
fi

# Fallback: Kein Bild und kein Text
echo "❌ Fehler: Unbekannter Inhaltstyp in der Zwischenablage"
zeige_verfuegbare_formate
exit 1

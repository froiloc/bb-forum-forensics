#!/bin/bash
# =============================================================================
# start.sh — IT-Forensisches Ermittlungswerkzeug (aiw_webserver)
# -----------------------------------------------------------------------------
# Linux-Pendant zu start.bat.
#
# Startet fuer jede vorhandene data/assets/assets_<id>.db genau einen
# Server-Prozess. Der Server waehlt automatisch den naechsten freien Port
# ab 8080 (--auto-port) und oeffnet anschliessend SELBST den Browser
# (--open-browser). Reihenfolge garantiert: Server zuerst, dann Browser.
#
# Python-Interpreter: bevorzugt portable Laufzeit ../Python/bin/python3,
#                     sonst 'python3' aus dem PATH.
# Browser: ueber config.yaml (browser.path) oder automatische Erkennung
#          (chromium / google-chrome / firefox / ...). Die fruehere Zeile
#          'which chromium-browser || which firefox || which google-chrome'
#          ist nun in core/browser_launcher.py abgebildet und erweitert.
#
# Beleg: Projektgespraech 2026-06-24 (Light-Version / Auto-Port / Browser)
# =============================================================================
set -euo pipefail

# In das Verzeichnis dieses Skripts wechseln, damit relative Pfade stimmen.
cd "$(dirname "$0")"

# --- Python-Interpreter bestimmen -------------------------------------------
PYTHON="python3"
if [[ -x "../Python/bin/python3" ]]; then
    PYTHON="../Python/bin/python3"
fi

# --- Pro Fall (assets_<id>.db) einen Server starten -------------------------
shopt -s nullglob
found=0
for f in ./data/assets/assets_*.db; do
    bn="$(basename "${f}" .db)"     # -> assets_<id>
    id="${bn#assets_}"             # -> <id>
    found=1
    echo "Starte Fall user-id=${id} ..."
    "${PYTHON}" main.py --mode cli --user-id "${id}" --auto-port --open-browser &
done

if [[ "${found}" -eq 0 ]]; then
    echo "" >&2
    echo "[FEHLER] Keine data/assets/assets_*.db gefunden." >&2
    echo "Bitte die fallspezifische Datenbank nach data/assets/ ablegen." >&2
    echo "" >&2
    exit 1
fi

# Auf alle gestarteten Server-Prozesse warten (Skript bleibt im Vordergrund).
wait

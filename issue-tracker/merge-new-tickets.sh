#!/bin/bash
# =============================================================================
# issue-tracker/merge-new-tickets.sh
# IT-Forensisches Ermittlungswerkzeug -- Issue-Tracker
# =============================================================================
# Mischt die von Claude gelieferten Eintragsdateien
# (eintraege_claude_Build*.json) in data/issues.json ein.
#
#   ./merge-new-tickets.sh            # einmischen
#   ./merge-new-tickets.sh --trocken  # nur zeigen, was passieren wuerde
#
# -----------------------------------------------------------------------------
# BUILD 668 -- WARUM DAS NEU GESCHRIEBEN WURDE
#
# Die bisherige Fassung lautete:
#   python merge.py eintraege_claude_Build*.json --auto-resolve source && rm ...
#
# merge.py nimmt aber GENAU EINE Quelldatei. Das Muster expandierte zu sieben,
# und argparse brach ab ("unrecognized arguments: ..."). Der Aufruf ist also
# nie durchgelaufen -- weshalb sich die Dateien seit Build 661 angesammelt
# haben. Immerhin scheiterte er SICHER: durch das '&&' wurde nichts geloescht.
#
# ES WIRD JETZT EINZELN EINGEMISCHT, und zwar mit drei Zusagen:
#   1. Abbruch beim ersten Fehler. Sonst liefe der Rest weiter, waehrend eine
#      Datei stillschweigend liegenbliebe -- und man saehe am Ende nur, dass
#      "irgendetwas" nicht geklappt hat.
#   2. Geloescht wird eine Datei NUR, wenn genau ihr Einmischen gelungen ist.
#   3. Es wird gezaehlt und am Ende benannt, was verarbeitet wurde. Ein
#      stiller Erfolg ist von einem stillen Ausfall nicht zu unterscheiden.
#
# ZUR KONFLIKTSTRATEGIE: '--auto-resolve source' ersetzt einen vorhandenen
# Vorgang vollstaendig durch den gelieferten. Das ist gewollt -- der
# gelieferte Stand ist der neuere und traegt die Bearbeitung. Es setzt aber
# voraus, dass die gelieferte Fassung die bereits vorhandenen Update-Eintraege
# MITBRINGT; sonst geht Historie verloren. Geprueft wird das von
# tests/test_issue_tracker_eintraege.py (IT03) auf der Erstellerseite, damit
# der Fehler gar nicht erst bis hierher kommt.
#
# Version: v0.8.668 - Build: 668 - 2026-08-05
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")"

trocken=0
if [ "${1:-}" = "--trocken" ] || [ "${1:-}" = "--dry-run" ]; then
    trocken=1
fi

# python bevorzugen, auf python3 zurueckfallen -- auf Ubuntu gibt es 'python'
# haeufig gar nicht, in einer aktiven venv dagegen schon.
if command -v python >/dev/null 2>&1; then
    py=python
else
    py=python3
fi

dateien=(eintraege_claude_Build*.json)
if [ ! -e "${dateien[0]}" ]; then
    echo "Nichts einzumischen: keine eintraege_claude_Build*.json vorhanden."
    exit 0
fi

echo "Gefunden: ${#dateien[@]} Datei(en)."
[ "$trocken" -eq 1 ] && echo "TROCKENLAUF -- es wird nichts geaendert und nichts geloescht."
echo ""

verarbeitet=0
for f in "${dateien[@]}"; do
    echo "=== ${f} ==="
    if [ "$trocken" -eq 1 ]; then
        "$py" merge.py "$f" --auto-resolve source --dry-run
    else
        # --force: keine Rueckfragen. Die Entscheidung ist mit
        # '--auto-resolve source' schon gefallen; eine zusaetzliche Rueckfrage
        # je Datei wuerde nur dazu verleiten, sie durchzuklicken.
        # KEIN --no-backup: merge.py legt vor jeder Aenderung eine Sicherung
        # in backups/ an, und die wollen wir behalten.
        "$py" merge.py "$f" --auto-resolve source --force
        rm -- "$f"
        echo "  eingemischt und entfernt: ${f}"
    fi
    verarbeitet=$((verarbeitet + 1))
    echo ""
done

if [ "$trocken" -eq 1 ]; then
    echo "TROCKENLAUF beendet: ${verarbeitet} Datei(en) geprueft, nichts geaendert."
    echo "Zum wirklichen Einmischen ohne '--trocken' aufrufen."
else
    echo "Fertig: ${verarbeitet} Datei(en) eingemischt."
    echo "Sicherungen liegen in backups/. Bitte data/issues.json committen."
fi

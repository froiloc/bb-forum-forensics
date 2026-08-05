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

# BUILD 669: ein Abbruch muss sich erklaeren. Beim ersten echten Lauf am
# 05.08.2026 wies merge.py eine Datei ab (Titel zu lang), 'set -e' beendete
# das Skript - und auf dem Bildschirm stand nur die Ausgabe von merge.py, ohne
# ein Wort darueber, WAS das Skript jetzt gemacht hat und was nicht. Genau die
# Lehre aus bundle_einspielen.sh, hier noch einmal.
aktuelle_datei=""
trap 'rc=$?; if [ "$rc" -ne 0 ]; then
    echo "" >&2
    echo "----- ABGEBROCHEN -----" >&2
    [ -n "$aktuelle_datei" ] && echo "  bei: ${aktuelle_datei}" >&2
    echo "  Diese Datei wurde NICHT geloescht." >&2
    echo "  merge.py bricht vor dem Schreiben ab, wenn eine Quelldatei" >&2
    echo "  ungueltige Vorgaenge enthaelt - der Bestand ist dann unveraendert." >&2
    echo "  Der Grund steht in der Ausgabe direkt darueber." >&2
    echo "" >&2
    echo "  Bereits eingemischte Dateien sind erledigt und entfernt." >&2
    echo "  Nach dem Beheben einfach erneut aufrufen - die uebrigen Dateien" >&2
    echo "  werden dann verarbeitet." >&2
    echo "  Sicherungen: backups/" >&2
    echo "-----------------------" >&2
fi' EXIT

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
if [ "$trocken" -eq 1 ]; then
    echo "TROCKENLAUF -- es wird nichts geaendert und nichts geloescht."
    # BUILD 669, aus dem ersten echten Lauf: der Trockenlauf prueft JEDE
    # Datei gegen den AKTUELLEN Bestand, nicht gegen den Zustand, den die
    # vorherigen Dateien hinterlassen wuerden. Am 05.08.2026 meldete er fuer
    # Build664 "1 neu, 0 Konflikte"; im echten Lauf war es "0 neu, 1
    # Konflikt", weil Build663 denselben Vorgang kurz zuvor angelegt hatte.
    # Beides ist richtig - es sind verschiedene Fragen. Wer das nicht weiss,
    # haelt die Abweichung fuer einen Fehler.
    echo "HINWEIS: jede Datei wird gegen den JETZIGEN Bestand geprueft."
    echo "Im echten Lauf wirken die Dateien nacheinander; Zahlen koennen"
    echo "sich dadurch verschieben (aus 'neu' wird 'Konflikt')."
fi
echo ""

verarbeitet=0
for f in "${dateien[@]}"; do
    aktuelle_datei="$f"
    echo "=== ${f} ==="
    if [ "$trocken" -eq 1 ]; then
        "$py" merge.py "$f" --auto-resolve source --dry-run
    else
        # BUILD 669: KEIN --force MEHR.
        #
        # Nachgelesen, was der Schalter wirklich tut: er hebt genau die
        # Sperre auf, die uns schuetzt. OHNE ihn bricht merge.py ab, BEVOR
        # etwas geschrieben wird, sobald eine Quelldatei ungueltige Vorgaenge
        # enthaelt ("Es wurde NICHTS geschrieben"). MIT ihm werden die
        # gueltigen Vorgaenge eingepflegt und die ungueltigen mit einer
        # Warnung uebergangen - in einer Datei mit mehreren Eintraegen faende
        # sich der uebergangene nur noch in einer Zeile weiter oben.
        #
        # Zusammen mit dem 'rm' darunter waere das die Sorte Verlust, gegen
        # die dieses Skript gebaut wurde. Der Preis fuer den Verzicht ist ein
        # Abbruch, den man beheben muss - und das ist der richtige Preis.
        #
        # KEIN --no-backup: merge.py legt vor jeder Aenderung eine Sicherung
        # in backups/ an, und die wollen wir behalten.
        "$py" merge.py "$f" --auto-resolve source
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
    aktuelle_datei=""
    echo "Fertig: ${verarbeitet} Datei(en) eingemischt."
    echo "Sicherungen liegen in backups/. Bitte data/issues.json committen."
fi

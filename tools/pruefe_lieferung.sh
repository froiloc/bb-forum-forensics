#!/usr/bin/env bash
# =============================================================================
# tools/pruefe_lieferung.sh
# IT-Forensisches Ermittlungswerkzeug -- Datenaustausch
# =============================================================================
# ABNAHMEPROBE: entspricht der Arbeitsbaum wirklich dem, was geliefert wurde?
#
#   ./tools/pruefe_lieferung.sh 665
#   ./tools/pruefe_lieferung.sh MD5SUMS_Build665.txt
#
# -----------------------------------------------------------------------------
# WARUM ES DAS GIBT (Build 666)
#
# Bis Build 665 wurde bei JEDER Lieferung eine Pruefsummenliste erzeugt,
# mitgeliefert und committet -- und von niemandem geprueft. Gemessen am
# 04.08.2026: 173 MD5SUMS-Dateien im Bestand, null Vorkommen von 'md5sum -c'
# im gesamten Projekt. Grundregel 8 verlangt Pruefsummen genau dafuer, dass
# nicht mit unterschiedlichen Dateifassungen gearbeitet wird.
#
# Am selben Tag hat uns das Fehlen dieser Probe mehrere Wortwechsel gekostet:
# ein Testlauf lief auf dem falschen Zweig, drei Tests fielen, und die Frage
# "fehlt die Datei wirklich oder schauen wir an die falsche Stelle?" liess
# sich nicht in einem Zug beantworten. Diese Probe beantwortet sie.
#
# -----------------------------------------------------------------------------
# WAS DIE PROBE SAGT -- UND WAS NICHT
#
# Sie vergleicht die gelieferten Dateien mit dem Arbeitsbaum. Sie sagt NICHT,
# ob der Bestand insgesamt in Ordnung ist: die Liste enthaelt nur die Dateien,
# die eine Lieferung ANGEFASST hat (so erzeugt sie bundle_bauen.sh). Alles
# andere ist nicht Gegenstand dieser Probe -- und das steht in der Ausgabe,
# damit die Zahl nicht mehr verspricht, als sie belegt.
#
# ABWEICHUNG IST NICHT GLEICH FEHLER. Wurde bei einer Konfliktaufloesung
# bewusst die eigene Fassung behalten, MUSS hier eine Abweichung stehen. Die
# Probe faellt kein Urteil, sie legt den Unterschied offen.
#
# Rueckgabe: 0 alles gleich - 1 Abweichungen oder fehlende Dateien
#            2 falscher Aufruf oder Liste nicht gefunden
#
# Version: v0.8.666 - Build: 666 - 2026-08-04
# =============================================================================
set -euo pipefail

if ! wurzel="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    echo "ABBRUCH: kein Git-Repository im aktuellen Verzeichnis." >&2
    exit 2
fi
cd "$wurzel"

arg="${1:-}"
if [ -z "$arg" ]; then
    echo "Aufruf: $0 <buildnummer|md5-liste>" >&2
    echo "Beispiel: $0 665" >&2
    exit 2
fi

if [ -f "$arg" ]; then
    liste="$arg"
else
    liste="MD5SUMS_Build${arg}.txt"
fi

if [ ! -f "$liste" ]; then
    echo "ABBRUCH: ${liste} nicht gefunden." >&2
    echo "Vorhandene Listen:" >&2
    ls -1 MD5SUMS_Build*.txt 2>/dev/null | tail -5 | sed 's/^/  /' >&2 || true
    exit 2
fi

# -----------------------------------------------------------------------------
# Die Liste hat das Format von 'md5sum': "<summe>  <pfad>". Kommentar- und
# Leerzeilen werden uebersprungen -- md5sums_build.sh schreibt eine Kopfzeile.
#
# ES WIRD NICHT 'md5sum -c' BENUTZT. Dessen Ausgabe unterscheidet nicht
# zwischen "Datei fehlt" und "Datei ist anders", und genau diese Unterscheidung
# ist die interessante: eine fehlende Datei deutet auf einen unvollstaendigen
# Merge, eine abweichende auf eine Konfliktaufloesung.
# -----------------------------------------------------------------------------
gleich=0
fehlend=()
abweichend=()

while IFS= read -r zeile; do
    case "$zeile" in
        ''|'#'*) continue ;;
    esac
    soll="${zeile%% *}"
    datei="${zeile#* }"
    datei="${datei# }"                       # fuehrende Leerzeichen weg
    [ -n "$soll" ] && [ -n "$datei" ] || continue
    if [ ! -f "$datei" ]; then
        fehlend+=("$datei")
        continue
    fi
    ist="$(md5sum "$datei" | cut -d' ' -f1)"
    if [ "$ist" = "$soll" ]; then
        gleich=$((gleich + 1))
    else
        abweichend+=("$datei")
    fi
done < "$liste"

echo "Abnahmeprobe gegen ${liste}"
echo "  uebereinstimmend: ${gleich}"
echo "  abweichend:       ${#abweichend[@]}"
echo "  fehlend:          ${#fehlend[@]}"

if [ "${#abweichend[@]}" -gt 0 ]; then
    echo ""
    echo "ABWEICHEND (Inhalt anders als geliefert):"
    printf '  %s\n' "${abweichend[@]}"
fi
if [ "${#fehlend[@]}" -gt 0 ]; then
    echo ""
    echo "FEHLEND (gar nicht im Arbeitsbaum):"
    printf '  %s\n' "${fehlend[@]}"
fi

if [ "${#abweichend[@]}" -eq 0 ] && [ "${#fehlend[@]}" -eq 0 ]; then
    echo ""
    echo "BESTANDEN -- alle gelieferten Dateien liegen unveraendert vor."
    echo "(Geprueft wurden NUR die ${gleich} Dateien dieser Lieferung."
    echo " Ueber den uebrigen Bestand sagt diese Probe nichts.)"
    exit 0
fi

echo ""
echo "NICHT BESTANDEN."
echo "Das muss kein Fehler sein: wurde bei einer Konfliktaufloesung bewusst"
echo "die eigene Fassung behalten, gehoert die Datei hierher. Bitte einzeln"
echo "ansehen, bevor etwas geaendert wird:"
echo "  git diff refs/claude/build<N> -- <datei>"
exit 1

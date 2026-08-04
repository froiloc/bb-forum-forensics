#!/usr/bin/env bash
# =============================================================================
# tools/bundle_bauen.sh
# IT-Forensisches Ermittlungswerkzeug
# =============================================================================
# Zweck:
#   Baut eine Lieferung nach documents/data-exchange.md -- Vorabprobe, Bundle,
#   MD5-Listen, Protokoll, Auslieferungsarchiv. Gegenstueck zu
#   tools/bundle_einspielen.sh.
#
# Aufruf:
#   tools/bundle_bauen.sh <paket> <buildnummer> [testbefehl]
#
# Beispiel:
#   tools/bundle_bauen.sh aiw_webserver 662
#   tools/bundle_bauen.sh aiw_webserver 662 "python3 -m pytest tests/ -q"
#
# -----------------------------------------------------------------------------
# WOZU DIESES SKRIPT UEBERHAUPT
#
# Ein ZIP entsteht durch Kopieren: was kopiert wird, ist drin. Ein Bundle
# entsteht aus Commits: was NICHT committet ist, fehlt spurlos. Genau diese
# Eigenschaft macht die Vorabprobe aus data-exchange.md Abschnitt 3.3 noetig --
# und genau die war bis Build 661 eine redaktionelle Regel ohne Durchsetzung.
# Dieses Skript setzt sie durch: es BRICHT AB, wenn im Arbeitsbaum etwas liegt,
# das nicht im Bundle landen wuerde (GR1 -- keine stille Auslassung).
#
# ZUR FEHLERPRUEFUNG
# 'set -euo pipefail' prueft jeden Befehl, lueckenlos. Der ERR-Trap sagt
# zusaetzlich, in welcher Zeile es geknallt hat -- 'set -e' allein bricht
# wortlos ab.
#
# Version: v0.8.662 - Build: 662 - 2026-08-02
# =============================================================================
set -euo pipefail
trap 'echo "" >&2; echo "ABBRUCH in Zeile ${LINENO}: ${BASH_COMMAND}" >&2' ERR

paket="${1:-}"
build_no="${2:-}"

if [ -z "$paket" ] || [ -z "$build_no" ]; then
    echo "Aufruf: $0 <paket> <buildnummer> [testbefehl]" >&2
    echo "Beispiel: $0 aiw_webserver 662" >&2
    exit 2
fi

# Der Testbefehl ist herausgezogen, weil die Bauumgebung nicht ueberall
# gleich heisst. Ohne Angabe wird 'python' bevorzugt und auf 'python3'
# zurueckgefallen -- auf Ubuntu gibt es 'python' haeufig gar nicht.
if [ -n "${3:-}" ]; then
    testbefehl="$3"
elif command -v python >/dev/null 2>&1; then
    testbefehl="python run_tests.py"
else
    testbefehl="python3 run_tests.py"
fi

# Der Zweigname folgt der ERSTEN Buildnummer der Sitzung, die Lieferung
# dagegen der LETZTEN. Beides faellt also auseinander, sobald eine Sitzung
# mehrere Builds umfasst -- der Zweig wird deshalb aus HEAD gelesen und nicht
# aus der Buildnummer errechnet.
zweig="$(git rev-parse --abbrev-ref HEAD)"
basis_ref="origin/master"

stapel="$(mktemp -d)"
# Das Testprotokoll liegt AUSSERHALB des Stapelverzeichnisses -- sonst landet
# es im Auslieferungsarchiv (gemessen 2026-08-02: 'test.log' war im ZIP).
testlog="$(mktemp)"
# Der EXIT-Trap raeumt beides in jedem Fall weg, auch beim Abbruch. Der
# ERR-Trap oben bleibt davon unberuehrt.
trap 'rm -rf "$stapel" "$testlog"' EXIT

wurzel="$(git rev-parse --show-toplevel)"
cd "$wurzel"

# Zielverzeichnis fuer das Auslieferungsarchiv. In der Bauumgebung liegt der
# Ausgabepfad fest; sonst neben dem Bestand.
if [ -d /mnt/user-data/outputs ]; then
    zielverz="/mnt/user-data/outputs"
else
    zielverz="$(dirname "$wurzel")"
fi

# Das Bundle wird IM STAPELVERZEICHNIS gebaut und erst danach kopiert.
# Befund 2026-08-02: 'git bundle create' scheitert direkt auf dem
# Ausgabe-Mount der Bauumgebung mit
#   fatal: sha1 file '<stdout>' write error: Bad file descriptor
#   error: pack-objects died
# 'zip' und 'cp' funktionieren dort dagegen. Die Ursache liegt also im Mount,
# nicht in git -- der Umweg ueber /tmp umgeht sie zuverlaessig.
bundle_datei="${stapel}/${paket}_${build_no}.bundle"
archiv="${zielverz}/${paket}_Build${build_no}.zip"
md5_liste="MD5SUMS_Build${build_no}.txt"
protokoll_name="PROTOKOLL_Build${build_no}.md"

meld() { printf '\n=== %s ===\n' "$*"; }

# =============================================================================
# 0) Vorbedingungen
# =============================================================================
meld "0) Vorbedingungen"

case "$zweig" in
    claude/build*) : ;;
    *)  echo "ABBRUCH: HEAD steht auf '${zweig}'." >&2
        echo "Erwartet wird ein Auslieferungszweig 'claude/build<Nr>'," >&2
        echo "benannt nach der ERSTEN Buildnummer der Sitzung." >&2
        exit 1 ;;
esac

git rev-parse --verify --quiet "$basis_ref" >/dev/null || {
    echo "ABBRUCH: ${basis_ref} ist nicht bekannt." >&2; exit 1; }

anzahl_commits="$(git rev-list --count "${basis_ref}..HEAD")"
if [ "$anzahl_commits" -eq 0 ]; then
    echo "ABBRUCH: Keine Commits gegenueber ${basis_ref}." >&2
    echo "Es gibt nichts auszuliefern -- oder es wurde vergessen zu committen." >&2
    exit 1
fi
echo "Zweig ${zweig}, Lieferung Build ${build_no}, ${anzahl_commits} Commit(s) gegenueber ${basis_ref}."

# =============================================================================
# 1) Vorabprobe -- data-exchange.md Abschnitt 3.3
# =============================================================================
meld "1) Vorabprobe"

# (a) HARTER ABBRUCH: alles, was verfolgt geaendert oder unverfolgt-aber-nicht-
#     ignoriert im Baum liegt, waere im Bundle NICHT enthalten. Das ist genau
#     die stille Auslassung, die GR1 verbietet.
offen="$(git status --porcelain)"
if [ -n "$offen" ]; then
    echo "ABBRUCH: Es liegt Nicht-Committetes im Arbeitsbaum." >&2
    echo "Ein Bundle enthaelt NUR Committetes -- das hier waere spurlos weg:" >&2
    echo "$offen" >&2
    echo "" >&2
    echo "Entweder committen (ggf. mit 'git add -f'), oder wegraeumen." >&2
    exit 1
fi
echo "(a) Nichts Uncommittetes im Arbeitsbaum."

# (b) IGNORIERTE Dateien werden gelistet, nicht abgebrochen. Der Filter ist
#     ausdruecklich benannt und wandert ins Protokoll -- ein verschwiegener
#     Filter waere selbst wieder eine stille Auslassung.
# Build 665: 'logs/' dazu. run_tests.py legt dort seit diesem Build die
# Testprotokolle ab; ohne den Eintrag meldete JEDE Lieferung sie als
# 'ignorierte Datei im Baum'. Ein Hinweis, der immer kommt, wird nicht
# mehr gelesen - und dann faellt der Fall nicht mehr auf, fuer den er
# gedacht war.
filter='__pycache__|\.pytest_cache|node_modules|\.venv|\.mypy_cache|\.ruff_cache|^!! logs/'
ignoriert="$(git status --porcelain --ignored | grep '^!!' | grep -Ev "$filter" || true)"
if [ -n "$ignoriert" ]; then
    echo "(b) ACHTUNG -- ignorierte Dateien im Baum:"
    echo "$ignoriert"
    echo "    Soll davon etwas mitgeliefert werden? Dann: git add -f <datei>"
    echo "    und dieses Skript erneut aufrufen."
else
    echo "(b) Keine ignorierten Dateien ausserhalb des Rauschfilters."
fi

# =============================================================================
# 2) Aenderungsliste und MD5-Einzelpruefsummen (GR8)
# =============================================================================
meld "2) Geaenderte Dateien"

# --diff-filter=d schliesst Loeschungen aus -- fuer eine geloeschte Datei
# gibt es keine Pruefsumme. Geloeschtes wird getrennt ausgewiesen, damit es
# nicht unter den Tisch faellt.
mapfile -t geaendert < <(git diff --name-only --diff-filter=d "${basis_ref}..HEAD" \
                         | grep -v "^MD5SUMS_Build" || true)
mapfile -t geloescht < <(git diff --name-only --diff-filter=D "${basis_ref}..HEAD" || true)

printf '%s\n' "${geaendert[@]}"
if [ "${#geloescht[@]}" -gt 0 ] && [ -n "${geloescht[0]}" ]; then
    echo "GELOESCHT (keine Pruefsumme moeglich):"
    printf '  %s\n' "${geloescht[@]}"
fi

meld "3) MD5-Liste"
bash tools/md5sums_build.sh "$build_no" "${geaendert[@]}"

# Die MD5-Liste gehoert in den Commit -- sonst weicht der ausgelieferte Stand
# von dem ab, was das Bundle enthaelt. Das Nachziehen wird ausdruecklich
# gemeldet: eine stille Aenderung an einem Commit waere das Gegenteil dessen,
# was dieses Verfahren erreichen soll.
if [ -n "$(git status --porcelain -- "$md5_liste")" ]; then
    echo ""
    echo "HINWEIS: ${md5_liste} wird in den letzten Commit nachgezogen"
    echo "         (git add + git commit --amend --no-edit)."
    git add "$md5_liste"
    git commit -q --amend --no-edit
    echo "         Neuer Commit: $(git rev-parse --short HEAD)"
fi

# =============================================================================
# 4) Bundle
# =============================================================================
meld "4) Bundle"
rm -f "$bundle_datei"
# Die Form '<zweig> --not <basis>' ist die massgebliche: sie benennt die
# enthaltene Ref ausdruecklich und traegt die Baubasis als Voraussetzung ein.
# Die Kurzform mit '..' kann ein Bundle ohne benannte Ref erzeugen.
git bundle create "$bundle_datei" "$zweig" --not "$basis_ref"
# Der Stapelpfad wird durch den Auslieferungsnamen ersetzt -- im Protokoll
# soll stehen, wie die Datei beim Empfaenger heisst, nicht wo sie hier lag.
verify_ausgabe="$(git bundle verify "$bundle_datei" 2>&1 \
                  | sed "s#${bundle_datei}#$(basename "$bundle_datei")#g")"
echo "$verify_ausgabe"
bundle_md5="$(md5sum "$bundle_datei" | awk '{print $1}')"
echo "MD5 Bundle: ${bundle_md5}"
# Zusaetzlich lose neben das Archiv legen -- bequem, wenn nur das Bundle
# gebraucht wird. Schlaegt das fehl, ist das kein Grund zum Abbruch: die
# massgebliche Ausfertigung liegt im Archiv.
cp "$bundle_datei" "${zielverz}/" 2>/dev/null \
    || echo "HINWEIS: lose Kopie nach ${zielverz} nicht moeglich (nur im Archiv)."

# =============================================================================
# 5) Regression
# =============================================================================
meld "5) Regression"
test_ergebnis="NICHT GEFAHREN"
if [ "$testbefehl" = "-" ]; then
    echo "Uebersprungen (Testbefehl '-')."
    test_ergebnis="AUSDRUECKLICH UEBERSPRUNGEN"
else
    echo "\$ ${testbefehl}"
    if eval "$testbefehl" > "$testlog" 2>&1; then
        test_ergebnis="$(tail -n 3 "$testlog" | tr -d '\r')"
        tail -n 3 "$testlog"
    else
        echo "REGRESSION FEHLGESCHLAGEN -- letzte Zeilen:" >&2
        tail -n 20 "$testlog" >&2
        echo "" >&2
        echo "Es wird kein Auslieferungsarchiv gebaut (GR2, GR9)." >&2
        exit 1
    fi
fi

# =============================================================================
# 6) Protokoll -- data-exchange.md Abschnitt 6
# =============================================================================
meld "6) Protokoll"
basis_sha="$(git rev-parse "$basis_ref")"
{
    echo "# Protokoll ${paket} Build ${build_no}"
    echo ""
    echo "Maschinell erzeugt von tools/bundle_bauen.sh am $(date -u '+%Y-%m-%d %H:%M UTC')."
    echo "Die inhaltliche Uebergabe (offene Punkte, Befunde, Begruendungen) steht"
    echo "im gesondert verfassten Uebergabedokument."
    echo ""
    echo "## 1. Baubasis"
    echo ""
    echo '```'
    git --no-pager log --oneline -1 "$basis_ref"
    echo '```'
    echo ""
    echo "## 2. Enthaltene Commits"
    echo ""
    echo '```'
    git --no-pager log --oneline "${basis_ref}..HEAD"
    echo '```'
    echo ""
    echo "## 3. git bundle verify"
    echo ""
    echo '```'
    echo "$verify_ausgabe"
    echo '```'
    echo ""
    echo "Die geforderte Ref ist ${basis_sha} -- die Baubasis aus Abschnitt 1."
    echo ""
    echo "## 4. Vorabprobe (data-exchange.md 3.3)"
    echo ""
    echo "Harte Probe \`git status --porcelain\`: leer, nichts Uncommittetes."
    echo ""
    echo "Ignorierte Dateien, Filter \`${filter}\`:"
    echo ""
    echo '```'
    if [ -n "$ignoriert" ]; then echo "$ignoriert"; else echo "(keine)"; fi
    echo '```'
    echo ""
    echo "## 5. Geaenderte Dateien mit Einzel-MD5"
    echo ""
    echo '```'
    cat "$md5_liste"
    echo '```'
    if [ "${#geloescht[@]}" -gt 0 ] && [ -n "${geloescht[0]}" ]; then
        echo ""
        echo "Geloescht (keine Pruefsumme moeglich):"
        echo ""
        echo '```'
        printf '%s\n' "${geloescht[@]}"
        echo '```'
    fi
    echo ""
    echo "## 6. MD5 der Bundle-Datei"
    echo ""
    echo '```'
    echo "${bundle_md5}  $(basename "$bundle_datei")"
    echo '```'
    echo ""
    echo "## 7. Regressionsstand"
    echo ""
    echo "Befehl: \`${testbefehl}\`"
    echo ""
    echo '```'
    echo "$test_ergebnis"
    echo '```'
    echo ""
    echo "Bauumgebung: $(python3 --version 2>&1), git $(git --version | awk '{print $3}')."
    echo ""
    echo "## 8. Einspielen"
    echo ""
    echo '```'
    echo "tools/bundle_einspielen.sh ${paket} ${build_no}"
    echo '```'
    echo ""
    echo "Von Hand gleichbedeutend:"
    echo ""
    echo '```'
    echo "git bundle verify $(basename "$bundle_datei")"
    echo "git fetch $(basename "$bundle_datei") 'refs/heads/${zweig}:refs/claude/build${build_no}'"
    echo "git switch -c integration/${build_no} master"
    echo "git merge --no-ff refs/claude/build${build_no}"
    echo "${testbefehl}"
    echo "git switch master && git merge --ff-only integration/${build_no}"
    echo "git branch -d integration/${build_no}"
    echo '```'
    echo ""
    echo "Kein Rebase (data-exchange.md Abschnitt 5). refs/claude/build${build_no}"
    echo "bleibt stehen (Abschnitt 4.4)."
} > "${stapel}/${protokoll_name}"
echo "${protokoll_name} geschrieben."

# =============================================================================
# 7) Auslieferungsarchiv
# =============================================================================
meld "7) Archiv"
# Das Bundle liegt bereits im Stapelverzeichnis (siehe Abschnitt 4).
cp "$md5_liste" "${stapel}/"
# Ein von Hand verfasstes Uebergabedokument wird mitgenommen, wenn es da ist.
for kandidat in "UEBERGABE_Build${build_no}.md" "documents/UEBERGABE_Build${build_no}.md"; do
    [ -f "$kandidat" ] && cp "$kandidat" "${stapel}/"
done
rm -f "$archiv"
( cd "$stapel" && zip -q -r "$archiv" . )
echo "Archiv: ${archiv}"
unzip -l "$archiv" | tail -n +4 | head -n -2

meld "Fertig"
echo "MD5 Archiv: $(md5sum "$archiv" | awk '{print $1}')"
echo ""
echo "Noch zu tun: Uebergabedokument verfassen (Befunde, offene Punkte)."

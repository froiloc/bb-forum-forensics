#!/usr/bin/env bash
# =============================================================================
# tools/bundle_einspielen.sh
# IT-Forensisches Ermittlungswerkzeug
# =============================================================================
# Einspielen einer Bundle-Lieferung nach documents/data-exchange.md.
# Gegenstueck zu tools/bundle_bauen.sh.
#
# NUR UNTER LINUX. In der Windows-VM ist kein Git verfuegbar; dort erfolgt
# stets ein vollstaendiger Rollout des fertigen Bestandes.
#
# Version: v0.8.662 - Build: 662 - 2026-08-02
# -----------------------------------------------------------------------------
#
# Aufruf:   ./bundle_einspielen.sh <paket> <buildnummer> [testbefehl]
# Beispiel: ./bundle_einspielen.sh aiw_webserver 661
#           ./bundle_einspielen.sh aiw_webserver 661 "py run_tests.py"
#
# -----------------------------------------------------------------------------
# ZUR FEHLERPRUEFUNG
#
# Es steht bewusst KEIN 'if [ $? -ne 0 ]' hinter den einzelnen Befehlen. Das
# leistet 'set -euo pipefail' bereits fuer JEDEN Befehl, und zwar
# lueckenlos -- eine von Hand gepflegte Pruefkette vergisst irgendwann eine
# Zeile, diese hier nicht:
#   -e            bricht ab, sobald ein Befehl != 0 liefert
#   -u            bricht ab bei Verwendung einer nicht gesetzten Variablen
#   -o pipefail   laesst auch einen Fehler MITTEN in einer Pipe durchschlagen
#                 (ohne das liefert 'git log | tail' den Wert von 'tail')
#
# 'set -e' hat eine bekannte Luecke: in Bedingungen (if/&&/||) greift es nicht.
# Genau dort steht deshalb im Skript ein ausdruecklicher Zweig -- naemlich
# ueberall da, wo ein Fehlschlag ein VORGESEHENER Fall ist (Merge-Konflikt,
# Stash-Konflikt) und nicht einfach zum Abbruch fuehren soll.
#
# Der ERR-Trap sagt zusaetzlich, WO es geknallt hat. 'set -e' allein bricht
# wortlos ab, und man sucht.
# -----------------------------------------------------------------------------
set -euo pipefail
trap 'echo "" >&2; echo "ABBRUCH in Zeile ${LINENO}: ${BASH_COMMAND}" >&2' ERR

package="${1:-}"
build_no="${2:-}"
# Der Testbefehl ist herausgezogen, weil die Bauumgebung nicht ueberall gleich
# heisst. Ohne Angabe wird 'python' bevorzugt und auf 'python3' zurueckgefallen
# -- auf Ubuntu gibt es 'python' haeufig gar nicht.
if [ -n "${3:-}" ]; then
    testbefehl="$3"
elif command -v python >/dev/null 2>&1; then
    testbefehl="python run_tests.py"
else
    testbefehl="python3 run_tests.py"
fi

if [ -z "$package" ] || [ -z "$build_no" ]; then
    echo "Aufruf: $0 <paket> <buildnummer> [testbefehl]" >&2
    echo "Beispiel: $0 aiw_webserver 661" >&2
    exit 2
fi

# ABSOLUTER Pfad, und zwar BEVOR gestasht wird. Befund aus der Erprobung
# 02.08.2026: liegt die Bundle-Datei im Arbeitsbaum, raeumt 'git stash -u' sie
# mit beiseite -- der anschliessende Fetch scheitert dann mit "does not appear
# to be a git repository", zwei Schritte spaeter und ohne erkennbaren Bezug.
bundle="${package}_${build_no}.bundle"
[ -f "$bundle" ] && bundle="$(cd "$(dirname "$bundle")" && pwd)/$(basename "$bundle")"

# Der Quellzweig wird AUS DEM BUNDLE gelesen, nicht aus der Buildnummer
# errechnet: der Zweigname folgt der ersten Buildnummer einer Sitzung, die
# Lieferung der letzten. Bei einer Sitzung ueber mehrere Builds faellt beides
# auseinander (Beispiel: Zweig claude/build661, Lieferung Build 662).
zweig=""                       # wird in Schritt 1 gesetzt
ref="refs/claude/build${build_no}"
integration="integration/${build_no}"
stash_kennung=""

meld() { printf '\n=== %s ===\n' "$*"; }

# Ist noch etwas offen? 'git ls-files -u' listet Eintraege mit Konfliktstufe.
# Verlaesslicher als der Rueckgabewert von 'git mergetool', der auch dann 0
# liefern kann, wenn der Anwender das Werkzeug ohne Aufloesung verlassen hat.
offene_konflikte() { [ -n "$(git ls-files -u)" ]; }

# Konfliktaufloesung mit git mergetool -- nur wenn es sinnvoll moeglich ist.
# Ohne konfiguriertes merge.tool fragt mergetool interaktiv nach und haengt in
# einem Skript. Ohne Terminal (Aufruf aus einem anderen Skript, CI) ebenso.
aufloesen() {
    if ! git config --get merge.tool >/dev/null 2>&1; then
        echo "Kein merge.tool eingerichtet -- 'git mergetool' wird uebersprungen."
        echo "Einrichten:  git config --global merge.tool kdiff3"
        echo "             git config --global mergetool.keepBackup false"
        return 1
    fi
    if [ ! -t 0 ]; then
        echo "Kein Terminal -- 'git mergetool' wird uebersprungen."
        return 1
    fi
    echo "Starte git mergetool ($(git config --get merge.tool)) ..."
    git mergetool || true          # Rueckgabewert bewusst ignoriert, s.o.
    if offene_konflikte; then
        echo "Es sind noch Konflikte offen:"
        git --no-pager diff --name-only --diff-filter=U
        return 1
    fi
    echo "Alle Konflikte aufgeloest."
    return 0
}

# --- 0) Vorbedingungen ------------------------------------------------------
meld "0) Vorbedingungen"
git rev-parse --git-dir >/dev/null 2>&1 || { echo "Kein Git-Bestand." >&2; exit 1; }
[ -f "$bundle" ] || { echo "FEHLT: $bundle" >&2; exit 1; }

# Seit dem Umstieg auf eigene Arbeitszweige ist das kein Formalismus mehr:
# steht HEAD auf 'alex/irgendwas', wuerde die Lieferung dorthin gemergt.
aktueller_zweig="$(git rev-parse --abbrev-ref HEAD)"
if [ "$aktueller_zweig" != "master" ]; then
    echo "ABBRUCH: HEAD steht auf '${aktueller_zweig}', nicht auf 'master'." >&2
    echo "Eine Lieferung gehoert nach master. Vorher: git switch master" >&2
    exit 1
fi

if git rev-parse --verify --quiet "$ref" >/dev/null; then
    echo "ABBRUCH: $ref existiert bereits -- diese Lieferung wurde schon geholt." >&2
    echo "Pruefen mit: git log --oneline master..$ref" >&2
    exit 1
fi

case "$bundle" in
    "$(git rev-parse --show-toplevel)"/*)
        echo "HINWEIS: Die Bundle-Datei liegt IM Arbeitsbaum. Das geht, ist aber"
        echo "unsauber -- sie taucht als unverfolgte Datei im Bestand auf." ;;
esac
echo "master, $ref noch frei, Bundle vorhanden."

# --- 1) Bundle pruefen, bevor irgendetwas angefasst wird --------------------
meld "1) git bundle verify"
git bundle verify "$bundle"

anzahl_heads="$(git bundle list-heads "$bundle" | wc -l)"
if [ "$anzahl_heads" -ne 1 ]; then
    echo "ABBRUCH: Das Bundle enthaelt ${anzahl_heads} Refs, erwartet genau eine." >&2
    git bundle list-heads "$bundle" >&2
    exit 1
fi
zweig="$(git bundle list-heads "$bundle" | awk '{print $2}')"
echo "Quellzweig im Bundle: ${zweig}"

# --- 2) Arbeitsbaum sichern -------------------------------------------------
meld "2) Arbeitsbaum"
# Die Probe muss GENAU DAS messen, was 'git stash' (ohne -u) auch mitnimmt:
# verfolgte Aenderungen, im Baum wie im Index. Befund 2026-08-02: mit
# 'git status --porcelain' als Probe reichte EINE unverfolgte Datei, damit der
# Zweig betreten wurde -- 'git stash push' meldete dann "No local changes to
# save", legte nichts an, und das anschliessende 'git rev-parse stash@{0}'
# brach mit "unknown revision" ab.
if git diff --quiet && git diff --cached --quiet; then
    echo "Keine verfolgten Aenderungen."
    unverfolgt="$(git ls-files --others --exclude-standard)"
    if [ -n "$unverfolgt" ]; then
        echo "Unverfolgte Dateien bleiben liegen (durch den Merge nicht"
        echo "gefaehrdet -- kollidiert eine, bricht git laut ab):"
        echo "$unverfolgt" | sed 's/^/  /'
    fi
else
    echo "Verfolgte Aenderungen auf master:"
    echo "HINWEIS: Besser waere, diese Arbeit auf einem eigenen Zweig zu"
    echo "committen. Ein Stash-Konflikt am Ende ist laestiger als ein Merge."
    git status --short
    vorher="$(git rev-parse --verify --quiet 'stash@{0}' || true)"
    # OHNE -u: unverfolgte Dateien bleiben liegen. Sie mitzunehmen vergroessert
    # nur die Angriffsflaeche -- gemessen hat 'stash -u' einmal die Bundle-Datei
    # selbst beiseitegeraeumt, worauf der Fetch zwei Schritte spaeter scheiterte.
    git stash push -m "vor ${package} Build ${build_no}"
    nachher="$(git rev-parse --verify --quiet 'stash@{0}' || true)"
    if [ -z "$nachher" ] || [ "$nachher" = "$vorher" ]; then
        echo "ABBRUCH: 'git stash push' hat keinen neuen Eintrag angelegt." >&2
        echo "Der Arbeitsbaum wurde nicht veraendert. Bitte von Hand pruefen." >&2
        exit 1
    fi
    stash_kennung="$nachher"
    echo "Eigener Stash: $stash_kennung"
fi

# --- 3) Lieferung in eigene Ref holen (Arbeitsbaum bleibt unberuehrt) -------
meld "3) fetch"
git fetch "$bundle" "refs/heads/${zweig}:${ref}"
git --no-pager log --oneline "master..${ref}"

meld "4) Unterschied zum Bestand"
git --no-pager diff --stat "master..${ref}"

# --- 5) Integrationszweig ---------------------------------------------------
meld "5) Integrationszweig ${integration}"
git switch -c "$integration" master
if ! git merge --no-ff "$ref" -m "Uebernahme ${package} Build ${build_no}"; then
    echo ""
    echo "KONFLIKT beim Merge. Das ist der vorgesehene Fall, nicht der Ausnahmefall."
    if aufloesen; then
        git commit --no-edit
        echo "Merge abgeschlossen."
    else
        echo ""
        echo "Von Hand weiter:"
        echo "  git mergetool          # oder Konfliktmarkierungen im Editor"
        echo "  git commit"
        echo "  ${testbefehl}"
        echo "  git switch master && git merge --ff-only ${integration}"
        echo "  git branch -d ${integration}"
        [ -n "$stash_kennung" ] && echo "  git stash pop          # eigener Eintrag: ${stash_kennung}"
        exit 1
    fi
fi

# --- 6) Regression ----------------------------------------------------------
meld "6) Regression"
echo "\$ ${testbefehl}"
eval "$testbefehl"

# --- 7) master nachziehen ---------------------------------------------------
# --ff-only: hat sich master waehrend des Laufs bewegt, scheitert es LAUT,
# statt still einen zweiten Merge zu bauen.
meld "7) master"
git switch master
git merge --ff-only "$integration"
git branch -d "$integration"

# --- 8) Stash zurueckholen -- nur den EIGENEN -------------------------------
# Befund 02.08.2026: 'git stash' liefert AUCH BEI SAUBEREM BAUM den Wert 0
# ("No local changes to save"). Ein unbedingtes 'git stash pop' holt dann den
# naechstbesten aelteren Eintrag hervor -- gemessen landete ein Stash vom Juni
# kommentarlos im Arbeitsbaum. Deshalb wird die eigene Kennung verglichen.
if [ -n "$stash_kennung" ]; then
    meld "8) Stash zurueckholen"
    if [ "$(git rev-parse 'stash@{0}' 2>/dev/null || true)" != "$stash_kennung" ]; then
        echo "NICHT ZURUECKGEHOLT: stash@{0} ist nicht mehr der eigene Eintrag." >&2
        echo "Von Hand: git stash list ; git stash apply ${stash_kennung}" >&2
        exit 1
    fi
    # Beruehrt die zurueckgelegte Arbeit dieselbe Datei wie die Lieferung,
    # endet 'pop' mit einem Konflikt. Der Eintrag bleibt dabei erhalten --
    # es geht nichts verloren.
    if ! git stash pop; then
        echo ""
        echo "KONFLIKT beim Zurueckholen der eigenen Arbeit."
        if aufloesen; then
            git stash drop
            echo "Aufgeloest, Stash-Eintrag verworfen."
        else
            echo "Der Eintrag ${stash_kennung} ist NICHT verbraucht worden."
            echo "Aufloesen, dann: git stash drop"
            exit 1
        fi
    fi
fi

meld "Fertig"
git --no-pager log --oneline -3
echo ""
echo "Noch zu tun:  git push"
echo "${ref} bleibt stehen (data-exchange.md Abschnitt 4.4) -- nicht loeschen."

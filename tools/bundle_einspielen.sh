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
#
# BUILD 665 -- WIEDERAUFSETZBAR STATT ROLLBACK (Befund Alex 2026-08-04)
#
# ANLASS: ein Lauf brach in Schritt 6 ab (Regression rot). Danach stand
# HEAD auf dem Integrationszweig -- das Skript sagte es mit keinem Wort,
# und der naechste Testlauf lief auf dem falschen Zweig. Der Befund war
# damit nicht der geprueften Sache zuzuordnen. Das ist eine stille
# Auslassung (GR1) an der Stelle, an der ein Werkzeug am meisten
# schaden kann: es hat ABGEBROCHEN und trotzdem nicht gesagt, wo es
# einen stehenlaesst.
#
# KEIN ROLLBACK -- UND ZWAR ABSICHTLICH. Drei Gruende:
#   (1) 'master' bewegt sich als LETZTER Schritt, per --ff-only, nach
#       gruener Regression. Das Gut, das zu schuetzen waere, ist bereits
#       geschuetzt; alles davor passiert auf Wegwerf-Refs.
#   (2) Ein Rollback muesste 'refs/claude/build<N>' mit wegraeumen. Diese
#       Ref IST der Nachweis darueber, was geliefert wurde
#       (data-exchange.md 4.4) -- sie zu loeschen vernichtet die Spur
#       des Vorgangs. Das ist die falsche Richtung.
#   (3) Der Zustand ist ABLEITBAR; es braucht keine eigene Buchfuehrung.
#       Git ist das Protokoll: 'rev-parse --verify' sagt, ob geholt
#       wurde, 'merge-base --is-ancestor' sagt, ob gemergt bzw.
#       nachgezogen wurde. Eine Zustandsdatei koennte von der
#       Wirklichkeit abweichen -- ein abgeleiteter Zustand nicht.
#
# STATTDESSEN: jeder Schritt prueft, ob er schon erledigt ist, und
# UEBERSPRINGT sich dann, statt abzubrechen. Ein zweiter Lauf nach einer
# behobenen Ursache faehrt damit einfach weiter.
#
# DIE EINE AUSNAHME ist der Stash: er ist NICHT ableitbar. Bricht etwas
# zwischen Schritt 2 und Schritt 8 ab, bleibt er liegen, und ein zweiter
# Lauf findet einen sauberen Baum und holt nichts zurueck. Dagegen steht
# der EXIT-Trap: er nennt beim Abbruch die Kennung und den Befehl.
#
# EXIT-CODES (Build 665): 0 = fertig. Sonst 10 + Schrittnummer, also
#   12 Arbeitsbaum, 13 fetch, 15 Merge/Konflikt, 16 Regression rot,
#   17 master nachziehen, 18 Stash zurueckholen. 1 = Vorbedingung
#   (Schritt 0/1), 2 = falscher Aufruf. Der Code allein sagt damit, wo
#   es hing -- ohne die Ausgabe zurueckscrollen zu muessen.
#
# Version: v0.8.665 - Build: 665 - 2026-08-04
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
# errechnet. ACHTUNG: list-heads liefert den VOLL QUALIFIZIERTEN Ref
# ("refs/heads/claude/build663") -- $zweig ist hier also etwas anderes
# als die gleichnamige Variable in bundle_bauen.sh (dort der kurze Name).
# errechnet: der Zweigname folgt der ersten Buildnummer einer Sitzung, die
# Lieferung der letzten. Bei einer Sitzung ueber mehrere Builds faellt beides
# auseinander (Beispiel: Zweig claude/build661, Lieferung Build 662).
zweig=""                       # wird in Schritt 1 gesetzt
ref="refs/claude/build${build_no}"
integration="integration/${build_no}"
stash_kennung=""
schon_geholt=0                 # Build 665: Wiederaufnahme (s. Schritt 0)

meld() { printf '\n=== %s ===\n' "$*"; }

# schritt: die zuletzt BEGONNENE Schrittnummer. Der EXIT-Trap bildet daraus
# den Rueckgabewert und den Zustandsbericht.
schritt=0
fertig=0

# zustandsbericht: WO STEHT DER BESTAND JETZT. Wird bei jedem Abbruch
# ausgegeben. Das ist die Lehre aus dem Befund vom 04.08.2026: ein Abbruch,
# der nicht sagt, wo er einen stehenlaesst, verlagert den Fehler nur -- der
# naechste Handgriff passiert dann auf dem falschen Zweig.
zustandsbericht() {
    echo "" >&2
    echo "----- ZUSTAND NACH DEM ABBRUCH -----" >&2
    echo "  HEAD steht auf: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')" >&2
    if git rev-parse --verify --quiet "$ref" >/dev/null 2>&1; then
        echo "  ${ref}: vorhanden (bleibt stehen -- data-exchange.md 4.4)" >&2
    else
        echo "  ${ref}: NICHT vorhanden" >&2
    fi
    if git rev-parse --verify --quiet "refs/heads/${integration}" >/dev/null 2>&1; then
        echo "  ${integration}: vorhanden" >&2
    else
        echo "  ${integration}: nicht vorhanden" >&2
    fi
    if git merge-base --is-ancestor "$ref" master 2>/dev/null; then
        echo "  master: TRAEGT die Lieferung bereits" >&2
    else
        echo "  master: traegt die Lieferung NICHT (unveraendert)" >&2
    fi
    if [ -n "$stash_kennung" ]; then
        echo "" >&2
        echo "  ACHTUNG -- EIGENE ARBEIT LIEGT IM STASH:" >&2
        echo "    ${stash_kennung}" >&2
        echo "  Sie wurde NICHT zurueckgeholt. Ein zweiter Lauf findet einen" >&2
        echo "  sauberen Baum und holt sie ebenfalls nicht zurueck." >&2
        echo "  Von Hand:  git stash list ; git stash apply ${stash_kennung}" >&2
    fi
    echo "" >&2
    echo "  Dieses Skript ist WIEDERAUFSETZBAR: Ursache beheben, auf master" >&2
    echo "  zurueckwechseln und erneut aufrufen. Erledigte Schritte werden" >&2
    echo "  uebersprungen." >&2
    echo "    git switch master && $0 ${package} ${build_no}" >&2
    echo "------------------------------------" >&2
}

# beim_beenden: der EXIT-Trap. Er laeuft bei JEDEM Verlassen -- auch beim
# Abbruch durch 'set -e' und beim Abbruch von Hand (Strg-C loest EXIT mit aus).
#
# 'rc=$?' MUSS die erste Anweisung sein: jeder andere Befehl davor
# ueberschriebe den Rueckgabewert, der hier gerettet werden soll.
beim_beenden() {
    local rc=$?
    if [ "$fertig" -eq 1 ]; then
        exit "$rc"
    fi
    zustandsbericht
    # Build 665: schrittbezogener Rueckgabewert. Der Code allein sagt dann,
    # WO es hing, ohne die Ausgabe zurueckscrollen zu muessen. Die
    # Vorbedingungen (Schritt 0/1) behalten ihre 1 -- dort ist noch nichts
    # geschehen, und der Ort ist aus der Meldung ohnehin eindeutig.
    if [ "$rc" -ne 0 ] && [ "$schritt" -ge 2 ]; then
        exit $((10 + schritt))
    fi
    exit "$rc"
}
trap beim_beenden EXIT

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

# BUILD 665: eine bereits geholte Lieferung ist KEIN Abbruchgrund mehr.
# Frueher endete hier jeder zweite Lauf -- also genau der Lauf, den man nach
# einem behobenen Fehler braucht. Der Zustand wird stattdessen FESTGESTELLT
# und den Schritten mitgegeben; Schritt 3 ueberspringt sich dann.
if git rev-parse --verify --quiet "$ref" >/dev/null; then
    if git merge-base --is-ancestor "$ref" master 2>/dev/null; then
        echo "FERTIG: master traegt Build ${build_no} bereits."
        echo "Nichts zu tun. ($ref bleibt stehen -- data-exchange.md 4.4)"
        git --no-pager log --oneline -1 master
        fertig=1
        exit 0
    fi
    echo "WIEDERAUFNAHME: ${ref} ist schon geholt, master traegt sie noch nicht."
    echo "Schritt 3 wird uebersprungen."
    schon_geholt=1
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
schritt=2
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
schritt=3
meld "3) fetch"
if [ "$schon_geholt" -eq 1 ]; then
    echo "Uebersprungen: ${ref} ist bereits vorhanden."
else
    # BUILD 665: OHNE zweites "refs/heads/". 'git bundle list-heads'
    # liefert den VOLL QUALIFIZIERTEN Ref ("refs/heads/claude/build663");
    # das Praefix noch einmal davorzusetzen ergab
    # "refs/heads/refs/heads/claude/build663" und damit "Konnte Remote-
    # Referenz nicht finden" (Befund Alex, 04.08.2026). In
    # bundle_bauen.sh ist $zweig dagegen der KURZE Name aus
    # 'rev-parse --abbrev-ref' -- derselbe Variablenname fuer zwei
    # verschiedene Dinge, das war die eigentliche Ursache.
    git fetch "$bundle" "${zweig}:${ref}"
fi
git --no-pager log --oneline "master..${ref}"

meld "4) Unterschied zum Bestand"
git --no-pager diff --stat "master..${ref}"

# --- 5) Integrationszweig ---------------------------------------------------
schritt=5
meld "5) Integrationszweig ${integration}"
# BUILD 665: ein Integrationszweig aus einem abgebrochenen Lauf ist kein
# Muell, sondern ein Zwischenstand. Traegt er die Lieferung schon, wird er
# WIEDERVERWENDET statt neu gebaut -- sonst muesste man ihn von Hand
# wegraeumen, bevor ein zweiter Lauf ueberhaupt anfangen kann.
zu_mergen=1
if git rev-parse --verify --quiet "refs/heads/${integration}" >/dev/null; then
    if git merge-base --is-ancestor "$ref" "refs/heads/${integration}" 2>/dev/null \
       && git merge-base --is-ancestor master "refs/heads/${integration}" 2>/dev/null; then
        echo "WIEDERAUFNAHME: ${integration} traegt Lieferung und master bereits."
        git switch "$integration"
        zu_mergen=0
    else
        echo "ABBRUCH: ${integration} existiert, traegt aber nicht beides." >&2
        echo "Das ist ein halber Zwischenstand aus einem frueheren Lauf." >&2
        echo "Ansehen und dann entscheiden:" >&2
        echo "  git log --oneline ${integration}" >&2
        echo "  git branch -D ${integration}     # wenn er verworfen werden soll" >&2
        exit 1
    fi
else
    git switch -c "$integration" master
fi
if [ "$zu_mergen" -eq 1 ] \
   && ! git merge --no-ff "$ref" -m "Uebernahme ${package} Build ${build_no}"; then
    echo ""
    # BUILD 665: EIN GESCHEITERTER MERGE IST NICHT ZWANGSLAEUFIG EIN KONFLIKT.
    # Gemessen bei der Erprobung am 04.08.2026: ohne eingerichtete
    # git-Identitaet scheitert 'git merge' mit "unable to auto-detect email
    # address" - das Skript meldete daraufhin einen Konflikt, schickte in die
    # Konfliktaufloesung und liess einen mit einer Anleitung zurueck, die zur
    # Lage nicht passte. Die Probe ist 'git ls-files -u': stehen dort keine
    # Eintraege, gab es keinen Konflikt, sondern etwas anderes.
    if ! offene_konflikte; then
        echo "MERGE GESCHEITERT, ABER OHNE KONFLIKT." >&2
        echo "Es liegen keine Dateien mit Konfliktstufe vor - die Ursache" >&2
        echo "steht in der git-Ausgabe daruber. Haeufig: keine Identitaet" >&2
        echo "eingerichtet (git config user.name / user.email)." >&2
        echo "" >&2
        echo "Nach dem Beheben einfach erneut aufrufen." >&2
        exit 1
    fi
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
schritt=6
meld "6) Regression"
echo "\$ ${testbefehl}"
# BUILD 665: eine ROTE Regression ist der ZWECK dieses Schritts und kein
# Absturz. Sie bekommt deshalb einen eigenen, benannten Ausgang -- vorher
# schlug hier nur der ERR-Trap zu ("ABBRUCH in Zeile ...: python
# run_tests.py"), was wie ein Werkzeugfehler aussieht und nicht wie ein
# Befund. Wichtig ist die zweite Zeile: master ist unberuehrt.
if ! eval "$testbefehl"; then
    echo "" >&2
    echo "REGRESSION ROT auf ${integration}." >&2
    echo "MASTER IST UNBERUEHRT -- es wurde nichts uebernommen." >&2
    echo "" >&2
    echo "Der Fehler gehoert zur Lieferung, nicht zu diesem Werkzeug." >&2
    echo "Ansehen (der Testlauf schreibt seit Build 665 ein Protokoll):" >&2
    echo "  ls -t logs/test_*.log | head -2" >&2
    echo "" >&2
    echo "WICHTIG: der naechste eigene Testlauf gehoert AUF DIESEN ZWEIG." >&2
    echo "Ein Lauf auf master pruefte den Bestand OHNE die Lieferung und" >&2
    echo "waere dem Befund nicht zuzuordnen." >&2
    exit 1
fi

# --- 7) master nachziehen ---------------------------------------------------
# --ff-only: hat sich master waehrend des Laufs bewegt, scheitert es LAUT,
# statt still einen zweiten Merge zu bauen.
schritt=7
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
    schritt=8
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

schritt=0
fertig=1
meld "Fertig"
git --no-pager log --oneline -3
echo ""
echo "Noch zu tun:  git push"
echo "${ref} bleibt stehen (data-exchange.md Abschnitt 4.4) -- nicht loeschen."

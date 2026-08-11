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
# Version: v0.8.697 - Build: 697 - 2026-08-11 (Nummernabgleich + MD5-Gegenprobe)
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

# -----------------------------------------------------------------------------
# BUILD 697 -- DIE NUMMER IM AUFRUF MUSS DIE NUMMER IN build.json SEIN.
#
# WOZU: Die Buildnummer benennt hier vier Dinge (Bundle, Archiv, MD5-Liste,
# Protokoll) und beim Empfaenger die Ref, den Integrationszweig und den
# erwarteten Dateinamen. Ein Zahlendreher erzeugt ein Archiv, dessen Name
# nicht zu seinem Inhalt passt -- und faellt erst weit spaeter auf, wenn
# ueberhaupt. Die Angabe steht ohnehin schon in build.json; sie zweimal von
# Hand richtig zu tippen ist keine Pruefung, sondern eine Gelegenheit.
#
# KEIN STILLES DURCHWINKEN, wenn build.json nicht lesbar ist: dann ist etwas
# grundlegend nicht in Ordnung, und ein Archiv aus einem Bestand mit kaputter
# build.json waere ohnehin nichts wert (GR1, GR4).
# -----------------------------------------------------------------------------
if [ ! -f build.json ]; then
    echo "ABBRUCH: build.json nicht gefunden." >&2
    exit 1
fi
build_in_json="$(python3 -c 'import json;print(json.load(open("build.json"))["build"])' 2>/dev/null || true)"
if [ -z "$build_in_json" ]; then
    echo "ABBRUCH: build.json liess sich nicht lesen (Schluessel 'build')." >&2
    echo "Ohne sie ist nicht zu pruefen, ob die Nummer im Aufruf stimmt." >&2
    exit 1
fi
if [ "$build_in_json" != "$build_no" ]; then
    echo "ABBRUCH: Die Nummern gehen auseinander." >&2
    echo "  build.json sagt : ${build_in_json}" >&2
    echo "  Aufruf sagt     : ${build_no}" >&2
    echo "Eine der beiden ist falsch. Die Lieferung wuerde sonst unter einem" >&2
    echo "Namen ausgeliefert, der nicht zu ihrem Inhalt passt." >&2
    exit 1
fi
echo "build.json und Aufruf nennen dieselbe Nummer (${build_no})."

# -----------------------------------------------------------------------------
# BUILD 697 -- IST DIESE NUMMER SCHON AUSGELIEFERT?
#
# Der Empfaenger erkennt eine Lieferung an ihrer Nummer (refs/claude/build<N>).
# Eine zweite Lieferung unter derselben Nummer kommt dort deshalb NICHT an --
# gemessen am 11.08.2026, zweimal, jeweils mit gruener Meldung. Seit dem
# gleichen Datum bricht bundle_einspielen.sh in diesem Fall ab; hier faellt es
# schon eine Stufe frueher auf, naemlich beim Erzeuger.
#
# Es wird GEWARNT und nicht abgebrochen: 'Uebernahme ... Build <N>' ist die
# Betreffzeile, die der Empfaenger beim Einspielen setzt -- sie steht also
# erst NACH einer erfolgreichen Uebernahme in der Baubasis. Ein Treffer ist
# damit ein starkes Anzeichen, aber kein Beweis (der Betreff koennte auch aus
# einem anderen Anlass so lauten). Ein Abbruch auf ein Anzeichen hin waere
# hier das falsche Mass; ein Verschweigen aber auch.
# -----------------------------------------------------------------------------
schon_geliefert="$(git log --oneline "$basis_ref" \
                   --grep="Build ${build_no}\$" --grep="Build ${build_no} " \
                   -E -i | head -3 || true)"
if [ -n "$schon_geliefert" ]; then
    echo ""
    echo "ACHTUNG -- IN ${basis_ref} STEHT SCHON ETWAS ZU BUILD ${build_no}:"
    echo "$schon_geliefert" | sed 's/^/  /'
    echo ""
    echo "Wurde diese Nummer bereits ausgeliefert, kommt eine zweite Lieferung"
    echo "unter derselben Nummer beim Empfaenger NICHT an -- dort entscheidet"
    echo "die Nummer, nicht der Inhalt. Bitte eine freie Nummer verwenden."
    echo "(Wenn der Treffer aus einem anderen Anlass stammt: weitermachen.)"
    echo ""
fi

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
# BUILD 666 -- HENNE-EI-WARNUNG. Aendert eine Lieferung das EINSPIELWERKZEUG
# selbst, dann wird sie mit der ALTEN Fassung eingespielt. Verbesserungen am
# Einspielen wirken also erst ab der NAECHSTEN Lieferung. Das ist nicht zu
# beheben (das Werkzeug liefert sich selbst aus), aber es ist anzusagen:
# Befund 04.08.2026 -- Alex lief zweimal in genau diese Falle, einmal in den
# fehlerhaften Fetch-Refspec und einmal in den Abbruch "Ref existiert
# bereits", dessen Behebung in ebendieser Lieferung steckte.
selbstaenderung=0
for _d in "${geaendert[@]}"; do
    if [ "$_d" = "tools/bundle_einspielen.sh" ]; then selbstaenderung=1; fi
done
if [ "$selbstaenderung" -eq 1 ]; then
    echo ""
    echo "ACHTUNG -- DIESE LIEFERUNG AENDERT DAS EINSPIELWERKZEUG SELBST."
    echo "Sie wird noch mit der ALTEN Fassung von bundle_einspielen.sh"
    echo "eingespielt. Alles, was dieser Build am Einspielen verbessert,"
    echo "wirkt erst ab der NAECHSTEN Lieferung."
    echo "Ein Konflikt an dieser Datei ist zu erwarten, falls im Bestand"
    echo "ebenfalls daran gearbeitet wurde."
    echo ""
fi

bash tools/md5sums_build.sh "$build_no" "${geaendert[@]}"

# =============================================================================
# Die MD5-Liste gehoert in den Commit -- sonst weicht der ausgelieferte Stand
# von dem ab, was das Bundle enthaelt.
#
# BUILD 697 -- DIESE ABSICHT WAR SEIT BUILD 665 WIRKUNGSLOS (Vorgang
# a1c7f0d2). Bis hierher lautete die Bedingung:
#
#     if [ -n "$(git status --porcelain -- "$md5_liste")" ]; then
#
# '.gitignore' fuehrt aber 'MD5SUMS_Build*.txt' (Zeile 90), und
# 'git status --porcelain' OHNE '--ignored' gibt fuer eine ignorierte Datei
# NICHTS aus. Die Bedingung war also immer falsch, der Zweig lief nie -- und
# weil er nur im Erfolgsfall etwas ausgab, meldete er auch nichts.
#
# GEMESSEN am 11.08.2026 im Produktivbestand:
#     git ls-files | grep -c '^MD5SUMS'   ->  0
#     ls MD5SUMS_Build*.txt | wc -l       ->  26   (alle unverfolgt)
#
# FOLGE, und sie wiegt schwer: Keine MD5-Liste war je in einem Bundle. Beim
# Empfaenger fehlte sie deshalb im Arbeitsbaum, und Schritt 8 von
# bundle_einspielen.sh ("Abnahmeprobe") endete AUSNAHMSLOS mit "KEINE ABNAHME
# MOEGLICH". Die Probe, die in Build 666 eigens eingefuehrt wurde, weil 173
# Pruefsummenlisten erzeugt und nie geprueft worden waren, ist bis dahin kein
# einziges Mal gelaufen. Damit fiel auch der letzte Waechter aus, der eine
# nicht angekommene Lieferung haette aufdecken koennen.
#
# ZWEI AENDERUNGEN, und die zweite ist die wichtigere:
#   1. 'git add -f' -- ueberstimmt die .gitignore-Regel. Sie bleibt bestehen:
#      die uebrigen 26 Altlisten sollen weiterhin nicht im Bestand auftauchen,
#      und ein '.gitignore'-Eingriff waere eine Entscheidung ueber den
#      dauerhaften Inhalt des Bestandes, nicht ueber dieses Werkzeug.
#   2. EINE GEGENPROBE DANACH. Erst sie macht aus einer stillen Nichtwirkung
#      einen lauten Abbruch. Genau daran hat es gefehlt -- nicht am Vorsatz.
# =============================================================================
if ! git ls-files --error-unmatch "$md5_liste" >/dev/null 2>&1 \
   || [ -n "$(git status --porcelain --ignored -- "$md5_liste")" ]; then
    echo ""
    echo "HINWEIS: ${md5_liste} wird in den letzten Commit nachgezogen"
    echo "         (git add -f + git commit --amend --no-edit)."
    git add -f "$md5_liste"
    git commit -q --amend --no-edit
    echo "         Neuer Commit: $(git rev-parse --short HEAD)"
fi

# GEGENPROBE: liegt die Liste jetzt wirklich im Commit? Ohne sie kann der
# Empfaenger die Abnahme nach Grundregel 8 nicht fahren -- und das soll nicht
# noch einmal jahrelang unbemerkt bleiben.
if ! git ls-files --error-unmatch "$md5_liste" >/dev/null 2>&1; then
    echo "" >&2
    echo "ABBRUCH: ${md5_liste} liegt NICHT im Commit." >&2
    echo "Damit waere sie in keinem Bundle, beim Empfaenger nicht im" >&2
    echo "Arbeitsbaum, und die Abnahmeprobe (Schritt 8 von" >&2
    echo "bundle_einspielen.sh, Grundregel 8) koennte nicht laufen." >&2
    echo "" >&2
    echo "Pruefen: git check-ignore -v ${md5_liste}" >&2
    exit 1
fi
echo "${md5_liste} ist im Commit -- die Abnahmeprobe ist beim Empfaenger moeglich."

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

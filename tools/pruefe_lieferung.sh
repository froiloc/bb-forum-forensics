#!/usr/bin/env bash
# =============================================================================
# tools/pruefe_lieferung.sh
# IT-Forensisches Ermittlungswerkzeug -- Datenaustausch
# =============================================================================
# ABNAHMEPROBE: entspricht der Arbeitsbaum wirklich dem, was geliefert wurde?
#
#   ./tools/pruefe_lieferung.sh 665
#   ./tools/pruefe_lieferung.sh MD5SUMS_Build665.txt
#   ./tools/pruefe_lieferung.sh 665 refs/claude/build664   # abweichende Ref
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
# BUILD 695 -- DIE PROBE ORDNET IHRE BEFUNDE JETZT EIN (Vorgang 08c9c821-725e-4e9f-89cd-9b012ce18c28)
#
# ANLASS, gemessen am 11.08.2026: Build 693 wurde eingespielt. Der Merge lief
# sauber durch, die Regression war gruen, master war nachgezogen -- und dann
# meldete diese Probe eine Abweichung an toolbar/toolbar.js. Der Rollout wurde
# gestoppt. Die Aufklaerung dauerte mehrere Wortwechsel und endete mit dem
# Ergebnis, dass alles in Ordnung war: zwischen der Baubasis der Lieferung
# (0.8.689) und dem Einspielen war Build 691 auf master gelandet und hatte
# DIESELBE Datei angefasst. Git hatte beides richtig verschmolzen. Die
# verschmolzene Datei kann die Pruefsumme einer EINZELNEN Lieferung aber
# niemals treffen.
#
# DAS WAR KEIN FEHLALARM IM SINNE VON "ZU EMPFINDLICH". Die Probe hat richtig
# gemessen. Sie hat nur nicht gesagt, WAS sie gemessen hat -- und liess damit
# genau die beiden Faelle ununterscheidbar, die entgegengesetzte Schritte
# verlangen:
#
#   (a) Die Lieferung ist beschaedigt oder unvollstaendig angekommen.
#       -> anhalten, nachfassen, nicht weiterarbeiten.
#   (b) Die Lieferung ist unversehrt angekommen und wurde mit einer zweiten
#       Lieferung verschmolzen.
#       -> in Ordnung, weitermachen.
#
# Die alte Fassung nannte (b) im Kopftext als Moeglichkeit ("ABWEICHUNG IST
# NICHT GLEICH FEHLER") und ueberliess die Klaerung dem Menschen. Bei einer
# Probe, die im Einspielvorgang laeuft und einen Rollout anhaelt, ist das zu
# wenig: der Hinweis steht in der Quelle, der Bediener sieht die Ausgabe.
#
# WIE (a) UND (b) UNTERSCHIEDEN WERDEN: Der Nachweis liegt bereits vor, er
# wurde nur nicht benutzt. data-exchange.md 4.4 verlangt, dass die Ref
# 'refs/claude/build<N>' nach dem Einspielen STEHENBLEIBT -- sie ist die
# Lieferung selbst, unveraendert, als Git-Objekt. Damit sind drei Fragen
# beantwortbar, ohne irgendetwas zu vermuten:
#
#   1. Traegt die Ref genau die Datei aus der Liste?
#      'git show <ref>:<datei>' gegen die Sollsumme.
#      NEIN -> die Lieferung passt nicht zu ihrer eigenen Liste. Echter Befund,
#              und zwar auf der Erstellerseite.
#      JA   -> die Lieferung ist unversehrt. Weiter mit 2.
#   2. Ist die Ref in HEAD enthalten?
#      'git merge-base --is-ancestor <ref> HEAD'.
#      NEIN -> die Lieferung ist (noch) nicht eingespielt.
#   3. Welche Commits haben die Datei ausserdem angefasst?
#      'git log <ref>..HEAD -- <datei>'.
#      Sind welche da, ist der Unterschied ERKLAERT und wird benannt.
#
# NEUER RUECKGABEWERT 3 fuer den Fall, dass JEDE Abweichung so erklaert ist.
# Er ist bewusst nicht 0: es IST ein Unterschied zur Lieferung, und wer die
# Probe maschinell auswertet, soll ihn sehen. Er ist aber auch nicht 1, denn
# 1 heisst "hier muss jemand hinsehen", und das trifft hier nicht mehr zu.
#
# WAS DIESE ERWEITERUNG NICHT TUT: Sie prueft nicht, ob die VERSCHMOLZENE
# Fassung fachlich richtig ist. Das kann keine Pruefsumme. Dafuer ist die
# Regression zustaendig, die im Einspielvorgang VOR dieser Probe laeuft
# (Schritt 6) -- sie hatte am 11.08.2026 laengst gruen gemeldet, als diese
# Probe anschlug. Die Probe sagt: "die Lieferung ist unversehrt angekommen
# und wurde mit X verschmolzen". Ob X und die Lieferung zusammenpassen, sagt
# der Testlauf.
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
# Probe faellt kein Urteil, sie legt den Unterschied offen -- seit Build
# 695 zusaetzlich mit seiner Herkunft, soweit Git sie hergibt.
#
# Rueckgabe: 0 alles gleich
#            1 Abweichungen, die NICHT eingeordnet werden konnten
#            2 falscher Aufruf oder Liste nicht gefunden
#            3 Abweichungen, ALLE als Verschmelzung erklaert (Build 695)
#
# Version: v0.8.695 - Build: 695 - 2026-08-11
# =============================================================================
set -euo pipefail

if ! wurzel="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    echo "ABBRUCH: kein Git-Repository im aktuellen Verzeichnis." >&2
    exit 2
fi
cd "$wurzel"

arg="${1:-}"
if [ -z "$arg" ]; then
    echo "Aufruf: $0 <buildnummer|md5-liste> [lieferref]" >&2
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
# Build 695: Die Lieferref bestimmen.
#
# Sie wird aus der Buildnummer gebildet, und die Buildnummer wird notfalls aus
# dem Dateinamen der Liste gelesen -- der Aufruf mit einem Dateinamen ist
# ausdruecklich vorgesehen (PL05) und darf die Einordnung nicht verlieren.
# Der zweite Aufrufparameter schlaegt beides: es gibt Lieferungen, deren
# Zweigname einer FRUEHEREN Buildnummer folgt (bundle_bauen.sh benennt den
# Zweig nach der ersten Buildnummer einer Sitzung, die Lieferung nach der
# letzten). Ohne diesen Ausweg waere die Probe genau dort blind, wo eine
# Sitzung mehrere Builds umfasst.
# -----------------------------------------------------------------------------
build_no=""
case "$arg" in
    ''|*[!0-9]*) : ;;
    *)           build_no="$arg" ;;
esac
if [ -z "$build_no" ]; then
    _name="$(basename "$liste")"
    _kern="${_name#MD5SUMS_Build}"
    _kern="${_kern%.txt}"
    case "$_kern" in
        ''|*[!0-9]*) : ;;
        *)           build_no="$_kern" ;;
    esac
fi

ref="${2:-}"
if [ -z "$ref" ] && [ -n "$build_no" ]; then
    ref="refs/claude/build${build_no}"
fi

ref_da=0
ref_eingespielt=0
if [ -n "$ref" ] && git rev-parse --verify --quiet "$ref" >/dev/null 2>&1; then
    ref_da=1
    if git merge-base --is-ancestor "$ref" HEAD 2>/dev/null; then
        ref_eingespielt=1
    fi
fi

# -----------------------------------------------------------------------------
# einordnen <datei> <sollsumme> <lage>
#   lage: 'abweichend' oder 'fehlend'
# Schreibt "<CODE>|<Klartext>" nach stdout. CODE ist eines von:
#   VERSCHMOLZEN     erklaert, kein Handlungsbedarf
#   BEFUND           die Lieferung passt nicht zu ihrer eigenen Liste
#   NICHT-EINGESPIELT die Lieferung steckt nicht in HEAD
#   LOKAL            Unterschied nur im Arbeitsbaum, nicht committet
#   UNERKLAERT       eingespielt und unversehrt, aber kein Commit erklaert es
#   OFFEN            ohne Lieferref nicht einzuordnen (Verhalten bis Build 693)
# -----------------------------------------------------------------------------
einordnen() {
    local datei="$1" soll="$2" lage="$3"
    local blob commits

    if [ "$ref_da" -eq 0 ]; then
        if [ -z "$ref" ]; then
            echo "OFFEN|keine Lieferref bestimmbar (Buildnummer unbekannt) - nicht einzuordnen"
        else
            echo "OFFEN|${ref} ist nicht vorhanden - ohne sie nicht einzuordnen"
        fi
        return 0
    fi

    if ! blob="$(git show "${ref}:${datei}" 2>/dev/null | md5sum | cut -d' ' -f1)"; then
        echo "OFFEN|steht nicht in ${ref} - nicht einzuordnen"
        return 0
    fi
    if [ -z "$blob" ] || ! git cat-file -e "${ref}:${datei}" 2>/dev/null; then
        echo "OFFEN|steht nicht in ${ref} - nicht einzuordnen"
        return 0
    fi

    if [ "$blob" != "$soll" ]; then
        # Der schwerste Fall: schon die Lieferung selbst haelt ihre eigene
        # Liste nicht ein. Dann stimmt etwas an der ERSTELLERSEITE nicht,
        # und der Arbeitsbaum ist gar nicht die Frage.
        echo "BEFUND|schon ${ref} weicht von der Liste ab (dort ${blob}) - Liste und Bundle passen nicht zusammen"
        return 0
    fi

    if [ "$ref_eingespielt" -eq 0 ]; then
        echo "NICHT-EINGESPIELT|${ref} ist nicht in HEAD enthalten - die Lieferung steckt (noch) nicht im Bestand"
        return 0
    fi

    # 'git log <ref>..HEAD -- <datei>' nennt die Commits, die die Datei
    # ausser der Lieferung angefasst haben.
    #
    # DASS DER MERGE-COMMIT SELBST MIT AUFTAUCHEN KANN, ist beabsichtigt und
    # kein Rauschen: Git zeigt ihn genau dann, wenn sein Ergebnis von KEINEM
    # Elternteil abweicht -- also wenn dort tatsaechlich zusammengefuehrt oder
    # von Hand aufgeloest wurde. Ihn herauszufiltern wuerde die
    # Konfliktaufloesung unsichtbar machen, und das ist der Fall, den man am
    # ehesten sehen will.
    commits="$(git log --oneline "${ref}..HEAD" -- "$datei" 2>/dev/null | tr '\n' ';' | sed 's/;$//')"
    if [ -n "$commits" ]; then
        if [ "$lage" = "fehlend" ]; then
            # Eine Datei kann planmaessig verschwinden: merge-new-tickets.sh
            # LOESCHT die Eintragsdatei, nachdem sie eingemischt wurde (das
            # steht so in der Anleitung nach dem Einspielen). Bis Build 693
            # meldete die Probe das jedes Mal als FEHLEND, ohne Erklaerung.
            echo "VERSCHMOLZEN|Lieferung unversehrt in ${ref}; im Arbeitsbaum entfernt bzw. ersetzt durch: ${commits}"
        else
            echo "VERSCHMOLZEN|Lieferung unversehrt in ${ref}; zusaetzlich veraendert durch: ${commits}"
        fi
        return 0
    fi

    if [ "$lage" = "abweichend" ] && ! git diff --quiet HEAD -- "$datei" 2>/dev/null; then
        echo "LOKAL|Lieferung unversehrt und eingespielt; der Unterschied ist nicht committet"
        return 0
    fi

    echo "UNERKLAERT|Lieferung unversehrt und eingespielt, aber kein Commit erklaert den Unterschied - moeglicherweise eine Konfliktaufloesung im Merge"
}

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
befunde=()          # "<datei>|<CODE>|<Klartext>" fuer jede Abweichung
nicht_erklaert=0

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
        befunde+=("${datei}|$(einordnen "$datei" "$soll" fehlend)")
        continue
    fi
    ist="$(md5sum "$datei" | cut -d' ' -f1)"
    if [ "$ist" = "$soll" ]; then
        gleich=$((gleich + 1))
    else
        abweichend+=("$datei")
        befunde+=("${datei}|$(einordnen "$datei" "$soll" abweichend)")
    fi
done < "$liste"

# Wie viele Abweichungen sind NICHT als Verschmelzung erklaert?
for eintrag in ${befunde[@]+"${befunde[@]}"}; do
    _rest="${eintrag#*|}"
    _code="${_rest%%|*}"
    [ "$_code" = "VERSCHMOLZEN" ] || nicht_erklaert=$((nicht_erklaert + 1))
done

# Einordnung zu einer Datei aus der Befundliste holen: "[CODE] Klartext".
#
# Der CODE steht MIT in der Zeile und nicht nur im Quelltext: er ist das, was
# sich zitieren und maschinell auswerten laesst ("bei uns stand LOKAL"),
# waehrend der Klartext je nach Fall anders lautet. Beides zusammen, damit
# weder der Mensch noch ein Skript nachschlagen muss.
erlaeuterung() {
    local suche="$1" eintrag _rest _code _text
    for eintrag in ${befunde[@]+"${befunde[@]}"}; do
        if [ "${eintrag%%|*}" = "$suche" ]; then
            _rest="${eintrag#*|}"
            _code="${_rest%%|*}"
            _text="${_rest#*|}"
            echo "[${_code}] ${_text}"
            return 0
        fi
    done
    echo "[OFFEN] keine Einordnung vorhanden"
}

echo "Abnahmeprobe gegen ${liste}"
echo "  uebereinstimmend: ${gleich}"
echo "  abweichend:       ${#abweichend[@]}"
echo "  fehlend:          ${#fehlend[@]}"
if [ "${#abweichend[@]}" -gt 0 ] || [ "${#fehlend[@]}" -gt 0 ]; then
    if [ "$ref_da" -eq 1 ]; then
        echo "  Lieferref:        ${ref} (vorhanden, $([ "$ref_eingespielt" -eq 1 ] && echo "in HEAD enthalten" || echo "NICHT in HEAD"))"
    elif [ -n "$ref" ]; then
        echo "  Lieferref:        ${ref} NICHT VORHANDEN - Abweichungen bleiben unerklaert"
    else
        echo "  Lieferref:        nicht bestimmbar - Abweichungen bleiben unerklaert"
    fi
fi

if [ "${#abweichend[@]}" -gt 0 ]; then
    echo ""
    echo "ABWEICHEND (Inhalt anders als geliefert):"
    for d in "${abweichend[@]}"; do
        echo "  ${d}"
        echo "      $(erlaeuterung "$d")"
    done
fi
if [ "${#fehlend[@]}" -gt 0 ]; then
    echo ""
    echo "FEHLEND (gar nicht im Arbeitsbaum):"
    for d in "${fehlend[@]}"; do
        echo "  ${d}"
        echo "      $(erlaeuterung "$d")"
    done
fi

if [ "${#abweichend[@]}" -eq 0 ] && [ "${#fehlend[@]}" -eq 0 ]; then
    echo ""
    echo "BESTANDEN -- alle gelieferten Dateien liegen unveraendert vor."
    echo "(Geprueft wurden NUR die ${gleich} Dateien dieser Lieferung."
    echo " Ueber den uebrigen Bestand sagt diese Probe nichts.)"
    exit 0
fi

# ---------------------------------------------------------------------------
# Build 695: Alles erklaert -> eigener Ausgang.
#
# Der Satz muss beides sagen: dass die Lieferung nachweislich unversehrt
# angekommen ist UND dass der Arbeitsbaum trotzdem etwas anderes enthaelt.
# Wer nur den ersten Teil liest, haelt die Datei faelschlich fuer identisch.
# ---------------------------------------------------------------------------
if [ "$nicht_erklaert" -eq 0 ]; then
    echo ""
    echo "BESTANDEN MIT VERSCHMELZUNG."
    echo "Jede Abweichung ist erklaert: die gelieferten Dateien stecken"
    echo "unveraendert in ${ref}, und ${ref} ist in HEAD enthalten. Der"
    echo "Arbeitsbaum enthaelt zusaetzlich die oben genannten Aenderungen aus"
    echo "anderen Lieferungen -- deshalb kann er die Pruefsumme EINER"
    echo "Lieferung nicht treffen. Das ist der Normalfall, sobald zwei"
    echo "Lieferungen dieselbe Datei anfassen."
    echo ""
    echo "NICHT GEPRUEFT ist damit, ob die verschmolzene Fassung fachlich"
    echo "richtig ist -- das kann keine Pruefsumme. Dafuer steht der Testlauf."
    exit 3
fi

echo ""
echo "NICHT BESTANDEN."
echo "Das muss kein Fehler sein: wurde bei einer Konfliktaufloesung bewusst"
echo "die eigene Fassung behalten, gehoert die Datei hierher. Bitte einzeln"
echo "ansehen, bevor etwas geaendert wird:"
if [ -n "$ref" ]; then
    echo "  git diff ${ref} -- <datei>"
else
    echo "  git diff refs/claude/build<N> -- <datei>"
fi
exit 1

#!/bin/bash
# =============================================================================
# tools/md5sums_build.sh
# IT-Forensisches Ermittlungswerkzeug
# =============================================================================
# Zweck (Grundregel 8):
#   Erzeugt MD5SUMS_Build<N>.txt fuer GENAU die Dateien eines Builds, damit
#   Entwickler und Anlage nachweislich dieselben Dateiversionen benutzen.
#
# Aufruf:
#   tools/md5sums_build.sh <buildnummer> <datei> [<datei> ...]
#
# Version: v0.8.588 - Build: 588 - 2026-07-31
# =============================================================================
set -eu

if [ "$#" -lt 2 ]; then
    echo "Aufruf: $0 <buildnummer> <datei> [<datei> ...]" >&2
    exit 2
fi

build="$1"
shift
ziel="MD5SUMS_Build${build}.txt"

: > "${ziel}"
for f in "$@"; do
    if [ ! -f "$f" ]; then
        echo "FEHLT: $f" >&2
        exit 1
    fi
    md5sum "$f" >> "${ziel}"
done

echo "${ziel} geschrieben (${#} Dateien):"
cat "${ziel}"

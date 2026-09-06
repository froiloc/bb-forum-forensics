# -*- coding: utf-8 -*-
# =============================================================================
# management/maintenance/bestandsliste.py
# IT-Forensisches Ermittlungswerkzeug - aiw_webserver
# =============================================================================
# ZWECK
#   Die Aufzaehlung der Beweismittelbestaende eines Verzeichnisses - alle
#   'evidence_<uid>.db', nach Kennung sortiert.
#
# WARUM EIN EIGENES MODUL (Build 763)
#   Diese Aufzaehlung stand bis Build 762 privat in
#   tools/annotationen_bestand.py ('_bestaende_finden'). Mit der Erweiterung
#   der Ankerdiagnose auf ALLE Bestaende braucht ein zweites Werkzeug
#   dieselbe Aufzaehlung. Sie zu verdoppeln waere die Konstellation, die in
#   Build 762 zum Rueckbau von Block C gefuehrt hat: zwei Wege zu derselben
#   Frage laufen binnen weniger Builds auseinander, und dann gibt es zwei
#   Antworten und keine.
#
#   Es wird NICHTS an der Logik geaendert - die Funktion ist wortgleich
#   uebernommen und lediglich oeffentlich benannt. tools/annotationen_bestand
#   ruft sie von hier ab; sein bisheriger Name '_bestaende_finden' bleibt als
#   Verweis stehen, damit vorhandene Aufrufe und Tests unveraendert tragen.
#
# WARTUNGSSTUFE
#   Rein lesend. Das Modul oeffnet keine Datenbank, es liest nur den
#   Verzeichniseintrag.
# =============================================================================
from __future__ import annotations

import os
import re
from typing import List, Tuple

#: Dateiname einer Beweismitteldatenbank. Wortgleich zum Muster, das seit
#: Build 630 in tools/annotationen_bestand.py stand.
RE_EVIDENCE = re.compile(r"^evidence_(\d+)\.db$")


def bestaende_finden(evidence_dir: str) -> List[Tuple[str, str]]:
    """
    Alle evidence_<uid>.db im Verzeichnis, nach uid sortiert.

    Rueckgabe: Liste von (uid, absoluter_pfad).

    Es wird NICHT auf das Vorhandensein der forensic_<uid>.db geprueft. Ein
    Bestand ohne Seitenkopfdaten ist ein BEFUND und kein Grund, ihn
    wegzulassen (Grundregel 1).
    """
    if not os.path.isdir(evidence_dir):
        return []
    gefunden = []
    for name in sorted(os.listdir(evidence_dir)):
        m = RE_EVIDENCE.match(name)
        if m:
            gefunden.append((m.group(1), os.path.join(evidence_dir, name)))
    return sorted(gefunden, key=lambda p: int(p[0]))

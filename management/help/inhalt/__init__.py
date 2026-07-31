# =============================================================================
# management/help/inhalt/__init__.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H1)
# =============================================================================
# Zweck:
#   Der Zusammenbau des Auslieferungs-Registers aus den Teilbestaenden. Je
#   Nav-Gruppe entsteht im Lauf der Inhaltswellen eine Datei (Konzept §3.1);
#   dieses Modul ist die EINE Stelle, an der sie zusammengefuehrt werden.
#
#   WARUM EIN LADER UND KEIN IMPORT-STERN (gesicherte Erkenntnis): Die
#   Ladereihenfolge bestimmt die Kapitelreihenfolge im Handbuch. Steht sie an
#   genau einer Stelle, ist sie belegbar und aenderbar; verteilt auf Sternchen-
#   Importe waere sie ein Zufallsprodukt der Dateinamen.
#
#   STAND H1 (Build 588): Es gibt noch KEINEN einzigen Hilfetext. Das ist
#   Absicht und der ehrliche Zustand - H1 baut das Fundament und den
#   Vollstaendigkeitszwang, nicht den Inhalt. Die Fehlliste umfasst deshalb
#   alle 43 Sichten; das Werkzeug zeigt ueberall den Platzhalter "Hilfe
#   folgt". Kein Kapitel wird still ausgelassen (Grundregel 1).
#
# Version: v0.8.588 - Build: 588 - 2026-07-31
# =============================================================================

from __future__ import annotations

from typing import List, Tuple

from management.help.modell import HilfeRegister, Sichthilfe
from management.help.inhalt.shell import SHELL_KONTEXT
from management.help.inhalt.fallsteuerung import FALLSTEUERUNG

# --- Teilbestaende ------------------------------------------------------------
# Reihenfolge = Kapitelreihenfolge im Handbuch. Sie folgt der Nav-Gruppenfolge
# des VIEW_CATALOG (GRUPPEN_REIHENFOLGE), damit Handbuch und Navigation
# dieselbe Ordnung haben. Jede Inhaltswelle traegt hier ihre Datei nach.
#
# H1: noch leer. H4 (Build 591) bringt die Shell-Kontexthilfe (kein Kapitel,
# sondern Texte fuer die Bedienelemente, die in JEDER Sicht stehen).
# H5 (Build 592): die Pilotsicht 'faelle' in der Gruppe Fallsteuerung.
_TEILBESTAENDE: Tuple[Tuple[Sichthilfe, ...], ...] = (
    FALLSTEUERUNG,
)


def lade_register() -> HilfeRegister:
    """
    Baut das Auslieferungsregister. Reine Funktion ohne Zwischenspeicher:
    das Register ist eingefroren und billig zu bauen, ein Cache waere nur
    eine weitere Stelle, an der etwas veralten kann.
    """
    sichten: List[Sichthilfe] = []
    for teil in _TEILBESTAENDE:
        sichten.extend(teil)
    return HilfeRegister(sichten=tuple(sichten), shell=SHELL_KONTEXT)


# Die Sichten, die (noch) kein Kapitel haben, werden NICHT hier gefuehrt -
# sie werden in pruefung.fehlliste_sichten() aus Katalog minus Register
# ABGELEITET. Eine gepflegte Liste koennte luegen; eine abgeleitete nicht.

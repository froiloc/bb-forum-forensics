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

from typing import Dict, List, Tuple

from management.help.modell import HilfeRegister, Sichthilfe
from management.help.inhalt.shell import SHELL_KONTEXT
from management.help.inhalt.ueberblick import UEBERBLICK
from management.help.inhalt.fallsteuerung import FALLSTEUERUNG
from management.help.inhalt.abnahme import ABNAHME
from management.help.inhalt.auswertung import AUSWERTUNG
from management.help.inhalt.kennzahlen import KENNZAHLEN
from management.help.inhalt.redaktion import REDAKTION
from management.help.inhalt.persoenlich import PERSOENLICH

# --- Teilbestaende ------------------------------------------------------------
# Reihenfolge = Kapitelreihenfolge im Handbuch. Sie folgt der Nav-Gruppenfolge
# des VIEW_CATALOG (GRUPPEN_REIHENFOLGE), damit Handbuch und Navigation
# dieselbe Ordnung haben. Jede Inhaltswelle traegt hier ihre Datei nach.
#
# JE EINTRAG STEHT DER DATEIPFAD DABEI, und zwar nicht als Kommentar, sondern
# als Wert (Anlass: mc 2026-07-31, "es waere super, wenn bei den Abschnitten
# auch der relative Dateipfad aufgefuehrt wird"). Wer beim Gegenlesen eine
# Formulierung aendern will, soll nicht suchen muessen, in welcher der vier
# Dateien sie steht - die Lektoratsfassung nennt sie je Kapitel.
#
# Ein Kommentar haette das nicht geleistet: er waere beim Verschieben eines
# Kapitels stehengeblieben. Als Wert wandert der Pfad mit.
_TEILBESTAENDE: Tuple[Tuple[str, Tuple[Sichthilfe, ...]], ...] = (
    ("management/help/inhalt/ueberblick.py", UEBERBLICK),
    ("management/help/inhalt/fallsteuerung.py", FALLSTEUERUNG),
    ("management/help/inhalt/abnahme.py", ABNAHME),
    ("management/help/inhalt/redaktion.py", REDAKTION),
    ("management/help/inhalt/auswertung.py", AUSWERTUNG),
    ("management/help/inhalt/kennzahlen.py", KENNZAHLEN),
    ("management/help/inhalt/persoenlich.py", PERSOENLICH),
)

#: Der Pfad des Shell-Bestands (kein Kapitel, aber redaktionell zu lesen).
SHELL_QUELLE = "management/help/inhalt/shell.py"


def lade_register() -> HilfeRegister:
    """
    Baut das Auslieferungsregister. Reine Funktion ohne Zwischenspeicher:
    das Register ist eingefroren und billig zu bauen, ein Cache waere nur
    eine weitere Stelle, an der etwas veralten kann.
    """
    sichten: List[Sichthilfe] = []
    for _pfad, teil in _TEILBESTAENDE:
        sichten.extend(teil)
    return HilfeRegister(sichten=tuple(sichten), shell=SHELL_KONTEXT)


def quelle_je_sicht() -> Dict[str, str]:
    """
    Sicht-ID -> relativer Pfad der Datei, in der ihr Kapitel steht.

    Wird von der Lektoratsfassung benutzt und von einem Test, der erzwingt,
    dass hier keine Sicht fehlt: ein Kapitel ohne Pfadangabe waere beim
    Gegenlesen genau die Sucherei, die diese Angabe vermeiden soll.
    """
    raus: Dict[str, str] = {}
    for pfad, teil in _TEILBESTAENDE:
        for s in teil:
            raus[s.sicht] = pfad
    return raus


def quellen() -> Tuple[str, ...]:
    """Alle Inhaltsdateien in Ladereihenfolge, Shell zuerst."""
    return (SHELL_QUELLE,) + tuple(p for p, _ in _TEILBESTAENDE)


# Die Sichten, die (noch) kein Kapitel haben, werden NICHT hier gefuehrt -
# sie werden in pruefung.fehlliste_sichten() aus Katalog minus Register
# ABGELEITET. Eine gepflegte Liste koennte luegen; eine abgeleitete nicht.

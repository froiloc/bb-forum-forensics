# =============================================================================
# tests/_bedienelemente.py
# IT-Forensisches Ermittlungswerkzeug - Pruefhilfe zu Vorgang 17200856
# =============================================================================
# Zweck:
#   Zaehlt je Sichtdatei die BEDIENELEMENTE (button, input, select, textarea)
#   und stellt fest, welche davon eine Hilfe-Marke tragen.
#
# DER ANLASS (Vorgang 17200856, mc, woertlich): "Die Sichten haben sehr viele
#   Schaltflaechen und Eingabezeilen, aber keine einzige wird erklaert. Wie
#   soll der Anwender wissen, was er tun soll, wenn es ihm nicht definiert und
#   erklaert wird?"
#
# WARUM KEINE VORHANDENE PRUEFUNG DAS GEFUNDEN HAT - und das ist der Kern:
#   Die Paritaetspruefungen (SP01-SP08 in Python, UX11 in vitest) sagen "jede
#   MARKE hat einen Text, jeder TEXT hat eine Marke". Sie sagen NICHTS
#   darueber, ob ein Knopf ueberhaupt eine Marke bekommen hat. Ein Knopf ohne
#   Marke ist fuer sie kein Gegenstand - er kommt in ihrer Welt nicht vor.
#   Genau in dieser Luecke sitzt der Vorgang.
#
# =============================================================================
# DAS VERFAHREN - und warum es so und nicht anders ist
# =============================================================================
# GEZAEHLT WIRD AM QUELLTEXT, nicht am gerenderten Baum. Das ist eine
#   Abwaegung, und die Gegenseite ist stark: UX11 misst am gerenderten Baum
#   und trifft damit auch berechnete Anker. ABER: der Rendering-Aufbau
#   (REGISTER in test_cockpit_tabellen_ux.test.js) traegt heute ACHT Sichten.
#   Fuer die uebrigen 35 muesste je Sicht eine Attrappe samt Daten gebaut
#   werden - und eine Erhebung, die erst nach 35 Attrappen anfaengt, faengt
#   nie an. Die Quelltextsuche liefert die Zahl HEUTE, fuer ALLE Sichten.
#
# DIE GRENZEN DES VERFAHRENS, ausdruecklich (TE4). Alle drei fuehren dazu,
# dass die Zahl eine UNTERGRENZE ist - sie kann zu niedrig sein, nie zu hoch:
#   1. Ein Element, das eine Fabrik erzeugt (z. B. in cockpit_tablekit.js),
#      wird hier nicht gezaehlt. Es taucht in der Sichtdatei gar nicht auf.
#   2. Ein Element, das ueber eine andere Variable weitergereicht und erst
#      dort markiert wird, gilt hier als unmarkiert.
#   3. Formulare in Dialogen, die erst auf Klick entstehen, werden gezaehlt,
#      wenn sie im Quelltext stehen - was richtig ist -, aber ihre
#      Verschachtelung sieht die Suche nicht.
# Eine Untergrenze ist fuer diesen Zweck die richtige Richtung: sie kann die
# Lage nicht beschoenigen.
#
# WIE EINE MARKE GEFUNDEN WIRD. Der Bestand kennt zwei Schreibweisen, beide
#   mit LITERALER Kennung (Regel aus documents/rules-help.md):
#       el.setAttribute('data-hilfe-id', 'sicht.bedienung.name');   161-mal
#       tk.hilfeAnker(el, 'sicht.bedienung.name');                   14-mal
#   Beide werden erkannt. Gesucht wird die Marke AB der Zeile, in der das
#   Element entsteht, bis zum Ende der umgebenden Funktion - Elemente werden
#   im Bestand durchgehend erzeugt, konfiguriert und dann eingehaengt.
#
# UEBER ZEILENGRENZEN HINWEG (Build 632, nachgebessert): Gesucht wird im
#   ZUSAMMENHAENGENDEN Text dieses Bereichs, nicht Zeile fuer Zeile. Der
#   Grund ist eine Luecke, die beim ersten Setzen von Marken aufgefallen ist:
#       note.setAttribute('data-hilfe-id',
#           'approval.bedienung.bewertungsvermerk');
#   ist eine voellig gewoehnliche Umbruchstelle (die Fassung in einer Zeile
#   waere 82 Zeichen breit). Die zeilenweise Suche haette diese Marke NICHT
#   gefunden und das Element als unerklaert gemeldet - eine Zahl also, die zu
#   HOCH ist. Das widerspraeche der Zusicherung "Untergrenze" unten, und eine
#   Fehlliste, die zu schwarz malt, wird beim naechsten Mal nicht geglaubt.
#   Der Gegentest BD05c haelt den Fall fest.
#
# BELEGT AN ZWEI SICHTEN VON HAND (Build 631): 'alias' (die Sicht, die es
#   richtig macht) und 'approval' (eine, die es nicht macht). Die Zahlen der
#   Suche sind dort gegen den Quelltext nachgezaehlt worden; der Test
#   BD05/BD06 haelt beide Faelle fest, damit die Suche nicht unbemerkt
#   abdriftet.
#
# Version: v0.8.632 - Build: 632 - 2026-08-01
# =============================================================================

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

#: Die Elementarten, um die es geht. KEINE Ueberschriften, keine Absaetze,
#: keine Tabellenspalten - die haben ihre eigene Pruefung. Hier geht es um
#: das, was man ANKLICKT oder AUSFUELLT.
BEDIENARTEN: Tuple[str, ...] = ("button", "input", "select", "textarea")

#: 'var x = document.createElement("button")' - der Variablenname und die Art.
_ERZEUGT = re.compile(
    r"""(?:var|let|const)\s+(\w+)\s*=\s*\w+\.createElement\(\s*['"](\w+)['"]""")

#: Auch ohne Schluesselwort: 'x = document.createElement("input")'.
_ERZEUGT_OHNE = re.compile(
    r"""^\s*(\w+)\s*=\s*\w+\.createElement\(\s*['"](\w+)['"]""")

#: Beginn einer Funktion - die Suchgrenze fuer die Marke.
_FUNKTION = re.compile(r"^\s*(?:function\s+\w+|\w+\s*[:=]\s*function|"
                       r"(?:var|let|const)\s+\w+\s*=\s*function)")


def _marke_muster(var: str) -> re.Pattern:
    """Beide Schreibweisen, mit LITERALER Kennung."""
    v = re.escape(var)
    return re.compile(
        r"%s\.setAttribute\(\s*['\"]data-hilfe-id['\"]\s*,\s*['\"]([a-z0-9_.]+)"
        r"['\"]|hilfeAnker\(\s*%s\s*,\s*['\"]([a-z0-9_.]+)['\"]" % (v, v))


@dataclass(frozen=True)
class Element:
    """Ein Bedienelement im Quelltext einer Sicht."""
    datei: str
    zeile: int
    art: str
    variable: str
    marke: str = ""            # leer = keine Hilfe-Marke gefunden

    @property
    def erklaert(self) -> bool:
        return bool(self.marke)

    def __str__(self) -> str:
        return "%s:%d %s (%s)%s" % (self.datei, self.zeile, self.art,
                                    self.variable,
                                    " -> " + self.marke if self.marke else "")


@dataclass(frozen=True)
class Sichtbefund:
    """Die Lage EINER Sichtdatei."""
    datei: str
    elemente: Tuple[Element, ...] = ()

    @property
    def erklaert(self) -> int:
        return sum(1 for e in self.elemente if e.erklaert)

    @property
    def offen(self) -> Tuple[Element, ...]:
        return tuple(e for e in self.elemente if not e.erklaert)

    @property
    def gesamt(self) -> int:
        return len(self.elemente)


def untersuche(pfad: Path) -> Sichtbefund:
    """Eine Sichtdatei durchsehen."""
    zeilen = pfad.read_text(encoding="utf-8", errors="replace").split("\n")

    # Funktionsgrenzen vorab: bis wohin darf nach der Marke gesucht werden?
    starts = [i for i, z in enumerate(zeilen) if _FUNKTION.search(z)]

    def _ende_der_funktion(i: int) -> int:
        for s in starts:
            if s > i:
                return s
        return len(zeilen)

    gefunden: List[Element] = []
    for i, zeile in enumerate(zeilen):
        m = _ERZEUGT.search(zeile) or _ERZEUGT_OHNE.search(zeile)
        if not m:
            continue
        var, art = m.group(1), m.group(2).lower()
        if art not in BEDIENARTEN:
            continue
        muster = _marke_muster(var)
        # Der Suchbereich als EIN Text: die Marke darf umgebrochen sein
        # (siehe Kopf, Build 632). Die '\s*' im Muster fangen den Umbruch.
        bereich = "\n".join(zeilen[i:_ende_der_funktion(i)])
        treffer = muster.search(bereich)
        marke = (treffer.group(1) or treffer.group(2) or "") if treffer else ""
        gefunden.append(Element(datei=pfad.name, zeile=i + 1, art=art,
                                variable=var, marke=marke))
    return Sichtbefund(datei=pfad.name, elemente=tuple(gefunden))


def erhebung(verzeichnis: Path) -> Dict[str, Sichtbefund]:
    """Alle cockpit*.js eines Verzeichnisses, nur die mit Bedienelementen."""
    raus: Dict[str, Sichtbefund] = {}
    for pfad in sorted(verzeichnis.glob("cockpit*.js")):
        b = untersuche(pfad)
        if b.gesamt:
            raus[pfad.name] = b
    return raus


def offene_je_datei(verzeichnis: Path) -> Dict[str, int]:
    """Die Fehlliste in ihrer kuerzesten Form: Datei -> Zahl der offenen."""
    return {name: len(b.offen)
            for name, b in erhebung(verzeichnis).items() if b.offen}

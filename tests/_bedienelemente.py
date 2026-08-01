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
#      dort markiert wird, gilt hier als unmarkiert. TEILWEISE BEHOBEN in
#      Build 633: den haeufigsten Fall - eine Fabrik, die ihr Element
#      ZURUECKGIBT und deren Aufrufer es markieren - erkennt die Suche jetzt
#      (siehe 'Die Fabrikregel' unten). Andere Weiterreichungen nicht.
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
# DIE FABRIKREGEL (Build 633, nachgebessert): Ein Element, das seine Funktion
#   mit 'return' verlaesst, wird nicht dort markiert, wo es entsteht - es
#   bekommt seine Marke an der Abnahmestelle, und zwar an jeder eine ANDERE,
#   weil zwei Aufrufer zwei verschiedene Bedienelemente meinen. Der Anlass ist
#   '_select' in cockpit_assignment.js: eine Fabrik mit zwei Abnahmestellen
#   (Person und Prioritaet des Sammel-Steuerkopfs). Die Suche folgt jetzt
#   diesem Weg: Rueckgabe erkannt -> Name der Funktion -> alle
#   'var X = name(' im Bestand -> Marke auf X. ERKLAERT ist das Element nur,
#   wenn JEDE Abnahmestelle eine Marke setzt; eine einzige unmarkierte genuegt,
#   und es bleibt offen. Auch das ist eine Korrektur nach unten, die vorher in
#   die alarmierende Richtung falsch lag.
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
# Version: v0.8.633 - Build: 633 - 2026-08-01
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

#: Derselbe Beginn, aber mit dem NAMEN. Gebraucht fuer die Fabrikregel unten.
_FUNKTIONSNAME = re.compile(
    r"^\s*(?:function\s+(\w+)|(\w+)\s*[:=]\s*function|"
    r"(?:var|let|const)\s+(\w+)\s*=\s*function)")


def _marke_muster(var: str) -> re.Pattern:
    """Beide Schreibweisen, mit LITERALER Kennung."""
    v = re.escape(var)
    return re.compile(
        r"%s\.setAttribute\(\s*['\"]data-hilfe-id['\"]\s*,\s*['\"]([a-z0-9_.]+)"
        r"['\"]|hilfeAnker\(\s*%s\s*,\s*['\"]([a-z0-9_.]+)['\"]" % (v, v))


def _rueckgabe_muster(var: str) -> re.Pattern:
    """'return sel;' - das Kennzeichen einer Fabrik."""
    return re.compile(r"^\s*return\s+%s\s*;" % re.escape(var), re.M)


def _huelle_muster(var: str) -> re.Pattern:
    """
    'wrap.appendChild(inp)' - das Kennzeichen einer HUELLENFABRIK: Die
    Funktion gibt nicht das Bedienelement zurueck, sondern seine Umhuellung
    (im Bestand fast immer ein <label> mit Beschriftung und Feld darin).
    """
    return re.compile(r"(\w+)\.appendChild\(\s*%s\s*\)" % re.escape(var))


def _buendel_muster(var: str) -> re.Pattern:
    """'return { label: label, el: sel };' - die Fabrik gibt ein BUENDEL aus
    Huelle und Bedienelement zurueck. Die Abnahmestelle greift mit '.el' zu."""
    return re.compile(r"return\s*\{[^}]*\b%s\b[^}]*\}" % re.escape(var))


def _marke_muster_weit(var: str) -> re.Pattern:
    """
    Wie _marke_muster, aber der Weg vom Alias zum Element darf einen Schritt
    weit sein: 'fw.eingabe.setAttribute(...)' oder
    'fw.querySelector("input").setAttribute(...)'. Gebraucht bei einer
    Huellenfabrik - dort haelt die Abnahmestelle die Huelle in der Hand und
    nicht das Bedienelement.
    """
    return re.compile(
        r"%s\b[^;]{0,80}?\.setAttribute\(\s*['\"]data-hilfe-id['\"]\s*,\s*"
        r"['\"]([a-z0-9_.]+)['\"]" % re.escape(var))


def _aufruf_muster(funktion: str) -> re.Pattern:
    """'var kopfPerson = _select(' - eine Abnahmestelle MIT Variablen."""
    return re.compile(
        r"(?:var|let|const)\s+(\w+)\s*=\s*%s\(" % re.escape(funktion))


def _jeder_aufruf_muster(funktion: str) -> re.Pattern:
    """
    JEDE Verwendung der Fabrik, auch die ohne Variable
    ('bar.appendChild(_btn(doc, ...))'). Gebraucht, damit die Fabrikregel
    kein Schlupfloch wird: Eine Abnahmestelle, die das Ergebnis direkt
    weiterreicht, kann keine Marke tragen - und dann ist das Bedienelement
    dort STUMM, egal wie gut die uebrigen markiert sind.
    """
    return re.compile(r"(?<![\w.])%s\s*\(" % re.escape(funktion))


def _kennung(treffer: "re.Match") -> str:
    """Die erste nicht-leere Gruppe eines Markentreffers."""
    for g in treffer.groups():
        if g:
            return g
    return ""


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

    ganzer_text = "\n".join(zeilen)

    def _funktionsname(i: int) -> str:
        """Der Name der Funktion, in der Zeile i steht ('' wenn unbenannt)."""
        for s in reversed(starts):
            if s <= i:
                m = _FUNKTIONSNAME.search(zeilen[s])
                if not m:
                    return ""
                return m.group(1) or m.group(2) or m.group(3) or ""
        return ""

    def _marke_ueber_fabrik(var: str, i: int, bereich: str) -> str:
        """
        DIE FABRIKREGEL (Build 633). Ein Element, das seine Funktion
        ZURUECKGIBT, wird nicht dort markiert, wo es entsteht, sondern an
        jeder Abnahmestelle - und dort auch verschieden, weil zwei Aufrufer
        zwei verschiedene Bedienelemente meinen.

        Bis Build 632 galt so ein Element als unerklaert. Das war falsch in
        der ALARMIERENDEN Richtung: die Zahl der offenen Elemente war zu hoch,
        und zwar fuer Code, der alles richtig macht.

        Streng ist die Regel trotzdem: erklaert ist das Element nur, wenn
        JEDE Abnahmestelle eine Marke setzt. Eine einzige unmarkierte
        Abnahmestelle ist eine stumme Schaltflaeche - und dann bleibt das
        Element offen. Gibt es gar keine Abnahmestelle mit Variablenzuweisung
        (das Ergebnis wandert direkt in einen Aufruf), greift die Regel nicht;
        dann bleibt es beim alten Befund.
        """
        weit = False
        if not _rueckgabe_muster(var).search(bereich):
            # HUELLENFABRIK (Build 636): nicht das Element wird
            # zurueckgegeben, sondern seine Umhuellung. Der Bestand baut so
            # jedes beschriftete Feld - <label> mit Text und Eingabe darin.
            huellen = [m.group(1) for m in _huelle_muster(var).finditer(bereich)]
            if not any(_rueckgabe_muster(h).search(bereich) for h in huellen):
                # BUENDEL-RUECKGABE (Build 637): manche Fabrik gibt beides
                # heraus - 'return { label: label, el: sel };'. Die
                # Abnahmestelle greift dann mit '.el' auf das Bedienelement
                # zu. Das ist derselbe Fall wie die Huelle, nur anders
                # verpackt; cockpit_audit.js macht es seit Build 604 so und
                # markiert vorbildlich JEDE Abnahmestelle.
                if not _buendel_muster(var).search(bereich):
                    return ""
            weit = True
        fname = _funktionsname(i)
        if not fname:
            return ""
        aliase = [m.group(1) for m in _aufruf_muster(fname).finditer(ganzer_text)]
        if not aliase:
            return ""
        # Build 636: JEDE Verwendung zaehlen, nicht nur die mit Variable.
        # Der erste Treffer ist die Deklaration der Fabrik selbst, deshalb -1.
        # Reicht auch nur EINE Abnahmestelle das Ergebnis direkt weiter
        # ('bar.appendChild(_btn(...))'), kann sie keine Marke tragen; das
        # Bedienelement ist dort stumm, und der Befund bleibt offen.
        alle = len(_jeder_aufruf_muster(fname).findall(ganzer_text)) - 1
        if alle > len(aliase):
            return ""
        marken = []
        for alias in aliase:
            muster = _marke_muster_weit(alias) if weit else _marke_muster(alias)
            t = muster.search(ganzer_text)
            if not t:
                return ""            # eine Abnahmestelle ohne Marke genuegt
            marken.append(_kennung(t))
        return marken[0]

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
        marke = _kennung(treffer) if treffer else ""
        if not marke:
            marke = _marke_ueber_fabrik(var, i, bereich)
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

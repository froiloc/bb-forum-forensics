# =============================================================================
# tests/_lesende_verbindungen.py
# IT-Forensisches Ermittlungswerkzeug - Pruefhilfe zu Regel PY4
# =============================================================================
# Zweck:
#   Findet in einer Python-Datei alle 'sqlite3.connect'-Aufrufe, die NICHT
#   nur-lesend sind. Grundlage der Durchsetzung von Regel PY4
#   (documents/rules-coding.md): "Lesend heisst technisch lesend."
#
# KEINE TESTDATEI, SONDERN EIN BAUTEIL FUER TESTS - deshalb der Unterstrich
#   im Namen, nach dem Muster von tests/unit/_hilfe_schluessel.js. Benutzt
#   wird sie von tests/test_py4_lesend.py (bestandsweit, gesteuert vom
#   CLI-Katalog) und von tests/test_backup_executor.py BR02 (Sicherungspfad).
#   Zwei Abschriften derselben Suche waeren binnen zweier Builds
#   auseinandergelaufen.
#
# UEBER DEN SYNTAXBAUM UND NICHT ZEILENWEISE. Die erste Fassung dieser Suche
#   (Build 627, in BR02) las den Quelltext als Text - und fand dabei den
#   KOMMENTAR, der die Aenderung erklaerte. Eine Pruefung, die ihre eigene
#   Begruendung fuer einen Befund haelt, ist unbrauchbar.
#
# EINFACHE VARIABLE WERDEN AUFGELOEST, und das ist nicht Bequemlichkeit,
#   sondern Notwendigkeit: Das Hausmuster fuer eine nur lesende Verbindung
#   baut die URI oft eine Zeile vorher zusammen -
#
#       uri = "file:" + str(db).replace("?", "%3f") + "?mode=ro"
#       con = sqlite3.connect(uri, uri=True, timeout=5.0)
#
#   Eine Suche, die nur das Argument ansieht, haelt das fuer schreibfaehig.
#   Bei der Erhebung in Build 629 waren zwei von zehn Fundstellen genau
#   dieser Fall - haetten sie auf die Ausnahmeliste gemusst, waere die Liste
#   um zwei unwahre Eintraege laenger und um genauso viel weniger wert.
#
# WAS DIESE HILFE NICHT KANN (TE4):
#   * Sie sieht nur die Datei, die man ihr gibt. Oeffnet ein Werkzeug seine
#     Datenbank ueber ein Repo oder einen Helfer in einem ANDEREN Modul,
#     faellt das hier nicht auf. Der Bestand hat dieses Muster (die *_repo-
#     Klassen bekommen die Verbindung herein), aber ausgeschlossen ist es
#     nicht.
#   * Sie prueft nur 'sqlite3.connect'. Ein Zugriff ueber eine andere
#     Anbindung bliebe unbemerkt.
#   * Sie sagt nichts darueber, ob wirklich geschrieben WIRD - nur darueber,
#     ob es KOENNTE. Genau das ist der Gegenstand von PY4.
#
# Version: v0.8.649 - Build: 649 - 2026-08-01
#   Build 649: gemeinsame Wurzel '_alle_verbindungen'; dazu
#   'lesende_verbindungen' und 'hat_lesenden_oeffner' fuer Vorgang 88dc129b.
#   Die Beurteilung selbst ist unveraendert.
# =============================================================================

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True, order=True)
class Fundstelle:
    """
    Ein schreibfaehiger sqlite3.connect-Aufruf.

    BEWUSST EINE DATENKLASSE UND KEIN NamedTuple (Regel PY3). Ein NamedTuple
    ist ein Tupel, und '"%s" % fundstelle' zerlegt es dann in DREI Argumente
    statt __str__ zu benutzen - eine Fehlermeldung, die eine Fehlermeldung
    ausgeben will, faellt damit selbst um. Genau das ist beim Umbau von BR02
    passiert.
    """
    zeile: int
    funktion: str
    argument: str

    def __str__(self) -> str:                    # fuer lesbare Fehlermeldungen
        return "Z%d in %s(): %s" % (self.zeile, self.funktion, self.argument)


def _ist_nur_lesend(roh: str) -> bool:
    """Traegt dieser Ausdruck erkennbar 'mode=ro'?"""
    return "mode=ro" in roh


def _alle_verbindungen(pfad: str) -> List[Tuple[Fundstelle, bool]]:
    """
    JEDE sqlite3.connect-Fundstelle der Datei, je mit der Beurteilung
    'ist nur-lesend' (True) oder 'ist schreibfaehig' (False).

    WARUM DIESE ZWISCHENSTUFE (Build 649): Bis Build 648 gab es nur
    'offene_verbindungen'. Die verschwieg, ob eine Datei UEBERHAUPT einen
    nur-lesenden Oeffner besitzt - und genau das ist die Frage bei den
    Werkzeugen mit art='gemischt' (Vorgang 88dc129b): dort IST eine
    schreibfaehige Verbindung erlaubt, der Mangel ist das FEHLEN der
    zweiten, nur-lesenden. Eine zweite Abschrift derselben Suche haette
    das beantwortet und waere binnen zweier Builds abgewichen; deshalb
    eine gemeinsame Wurzel und zwei Sichten darauf.

    Die Beurteilung ist unveraendert die aus Build 629 - insbesondere die
    Aufloesung einfacher Variablen; sie ist hier nur EINMAL aufgeschrieben
    statt zweimal.
    """
    with open(pfad, encoding="utf-8") as fh:
        baum = ast.parse(fh.read(), filename=pfad)

    eltern = {}
    for knoten in ast.walk(baum):
        for kind in ast.iter_child_nodes(knoten):
            eltern[kind] = knoten

    def _umgebende_funktion(knoten):
        p = eltern.get(knoten)
        while p is not None and not isinstance(
                p, (ast.FunctionDef, ast.AsyncFunctionDef)):
            p = eltern.get(p)
        return p

    raus: List[Tuple[Fundstelle, bool]] = []
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Call):
            continue
        f = knoten.func
        if not (isinstance(f, ast.Attribute) and f.attr == "connect"
                and isinstance(f.value, ast.Name) and f.value.id == "sqlite3"):
            continue

        roh = ast.unparse(knoten.args[0]) if knoten.args else ""
        funktion = _umgebende_funktion(knoten)
        nur_lesend = _ist_nur_lesend(roh)

        # Einfache Variable aufloesen: eine Zuweisung an DENSELBEN Namen
        # innerhalb derselben Funktion (oder auf Modulebene), deren Wert
        # 'mode=ro' enthaelt. Bewusst grosszuegig - eine Variable, die
        # irgendwo mit mode=ro belegt wird, ist ein starkes Indiz, und die
        # Gegenrichtung (falsch als nur-lesend durchgewinkt) verlangt schon
        # eine absichtliche Irrefuehrung.
        if not nur_lesend and isinstance(
                knoten.args[0] if knoten.args else None, ast.Name):
            name = knoten.args[0].id
            bereich = funktion if funktion is not None else baum
            nur_lesend = any(
                isinstance(z, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name
                        for t in z.targets)
                and _ist_nur_lesend(ast.unparse(z.value))
                for z in ast.walk(bereich))

        raus.append((Fundstelle(
            zeile=knoten.lineno,
            funktion=funktion.name if funktion is not None else "(Modulebene)",
            argument=roh), nur_lesend))
    return sorted(raus)


def offene_verbindungen(pfad: str) -> List[Fundstelle]:
    """
    Alle SCHREIBFAEHIGEN sqlite3.connect-Aufrufe der Datei.

    Leere Liste heisst: jede Verbindung dieser Datei ist nur-lesend - oder
    es gibt gar keine. ACHTUNG, das ist zweierlei; wer die Unterscheidung
    braucht, nimmt 'hat_lesenden_oeffner'.
    """
    return [f for f, nur_lesend in _alle_verbindungen(pfad) if not nur_lesend]


def lesende_verbindungen(pfad: str) -> List[Fundstelle]:
    """Alle NUR-LESENDEN sqlite3.connect-Aufrufe der Datei."""
    return [f for f, nur_lesend in _alle_verbindungen(pfad) if nur_lesend]


def hat_lesenden_oeffner(pfad: str) -> bool:
    """
    Besitzt diese Datei ueberhaupt einen nur-lesenden Oeffner?

    DAS IST DER MASSSTAB FUER art='gemischt' (Vorgang 88dc129b). Ein
    Werkzeug, das schreibende UND lesende Unterbefehle hat, braucht ZWEI
    Oeffner - sonst laeuft auch der lesende Unterbefehl mit Schreibrecht
    auf ein Beweismittel. Das Hausmuster dafuer ist backup_admin seit
    Build 627.

    WAS DAS NICHT BELEGT (TE4): dass der lesende Unterbefehl den lesenden
    Oeffner auch BENUTZT. Ein Werkzeug mit beiden Oeffnern kann den
    falschen nehmen; das ist am Syntaxbaum nicht zu entscheiden und bleibt
    Sache der Durchsicht. Hier faellt nur der Fall auf, in dem die zweite
    Verbindung GAR NICHT EXISTIERT - dann ist der Mangel sicher.
    """
    return any(nur_lesend for _f, nur_lesend in _alle_verbindungen(pfad))

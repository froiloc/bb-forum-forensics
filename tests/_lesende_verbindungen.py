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
# Version: v0.8.629 - Build: 629 - 2026-08-01
# =============================================================================

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import List


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


def offene_verbindungen(pfad: str) -> List[Fundstelle]:
    """
    Alle schreibfaehigen sqlite3.connect-Aufrufe der Datei.

    Leere Liste heisst: jede Verbindung dieser Datei ist nur-lesend - oder
    es gibt gar keine.
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

    raus: List[Fundstelle] = []
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Call):
            continue
        f = knoten.func
        if not (isinstance(f, ast.Attribute) and f.attr == "connect"
                and isinstance(f.value, ast.Name) and f.value.id == "sqlite3"):
            continue

        roh = ast.unparse(knoten.args[0]) if knoten.args else ""
        if _ist_nur_lesend(roh):
            continue

        funktion = _umgebende_funktion(knoten)

        # Einfache Variable aufloesen: eine Zuweisung an DENSELBEN Namen
        # innerhalb derselben Funktion (oder auf Modulebene), deren Wert
        # 'mode=ro' enthaelt. Bewusst grosszuegig - eine Variable, die
        # irgendwo mit mode=ro belegt wird, ist ein starkes Indiz, und die
        # Gegenrichtung (falsch als nur-lesend durchgewinkt) verlangt schon
        # eine absichtliche Irrefuehrung.
        if isinstance(knoten.args[0] if knoten.args else None, ast.Name):
            name = knoten.args[0].id
            bereich = funktion if funktion is not None else baum
            belegt_ro = any(
                isinstance(z, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name
                        for t in z.targets)
                and _ist_nur_lesend(ast.unparse(z.value))
                for z in ast.walk(bereich))
            if belegt_ro:
                continue

        raus.append(Fundstelle(
            zeile=knoten.lineno,
            funktion=funktion.name if funktion is not None else "(Modulebene)",
            argument=roh))
    return sorted(raus)

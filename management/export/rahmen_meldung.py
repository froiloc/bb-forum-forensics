# =============================================================================
# management/export/rahmen_meldung.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem
# =============================================================================
# Zweck (Vorgang ff7e80ab):
#   EINE Stelle, an der ein Kommandozeilenwerkzeug die Rahmenbefunde eines
#   ExportContext auf seiner Fehlerausgabe benennt.
#
# WARUM ALS EIGENES BAUTEIL UND NICHT JE WERKZEUG:
#   Vor Build 702 hat jedes Werkzeug diese Lage eigenstaendig behandelt — und
#   entsprechend verschieden: 'export_admin' meldete (Z. 116-119, 145-152),
#   'glossary_admin' und 'ausschleus_admin' meldeten nur den Ausfall der
#   Datenbankverbindung, 'forecast_report_admin' und 'status_report_admin'
#   meldeten gar nichts (Vorgang ff7e80ab). Wortlaut und Umfang der Auskunft
#   haengen so davon ab, welches Werkzeug man aufruft. Genau das soll bei einer
#   Angabe, die die Herkunft eines Abgabedokuments belegt, nicht sein.
#
# WAS DIESES BAUTEIL AUSDRUECKLICH NICHT TUT:
#   Es bricht nicht ab und aendert keinen Rueckgabewert (Entscheidung Alex,
#   12.08.2026). Der Bericht IST geschrieben; ihn nachtraeglich zu
#   verwerfen, weil sein Vermerk unvollstaendig ist, wuerde ein brauchbares
#   Dokument vernichten und die Auskunft gleich mit. Der Weg ist derselbe wie
#   bei 'export_admin': schreiben, benennen, mit 0 zurueckkehren.
#
# Version: v0.8.702 · Build: 702 · 2026-08-12
# =============================================================================

from __future__ import annotations

import sys
from typing import Optional, TextIO

from management.export.export_envelope import ExportContext


# Der Nachsatz steht NACH den einzelnen Befunden und nur EINMAL. Er benennt die
# Folge fuer die Person, die das Dokument weitergibt — die einzelnen Befunde
# benennen nur die Ursache. Ohne diesen Satz muesste der Leser die Folge selbst
# erschliessen; das ist genau die Zumutung, die der Vorgang beanstandet hat.
_NACHSATZ = ("%s WARNUNG: Der erzeugte Bericht traegt KEINEN vollstaendigen "
             "Erzeugungsvermerk. Vor einer Weitergabe ist der Vermerk im "
             "Dokument anzusehen; die fehlenden Angaben sind dort ebenfalls "
             "als 'nicht ermittelbar' gekennzeichnet.")


def melde_rahmen_befunde(praefix: str, context: Optional[ExportContext],
                         stream: Optional[TextIO] = None) -> int:
    """
    Schreibt je Rahmenbefund eine Zeile auf 'stream' (Vorgabe: sys.stderr) und
    danach EINEN Nachsatz zur Folge. Gibt die Zahl der gemeldeten Befunde
    zurueck (0 = vollstaendiger Rahmen, nichts ausgegeben).

    'stream' ist injizierbar, damit die Meldung testbar ist, ohne die
    Fehlerausgabe des Testlaufs umzubiegen.

    'context' darf None sein: ein Werkzeug, das den Rahmen ueberhaupt nicht
    gebildet hat, soll diesen Aufruf nicht mit einer Fallunterscheidung
    umgeben muessen. None bedeutet hier 'nichts zu melden' — der Ausfall des
    Rahmens SELBST wird als Befund im Ersatzkontext gefuehrt (FELD_RAHMEN)
    und nicht durch dessen Abwesenheit ausgedrueckt.

    Die Ausgabe wird ausdruecklich GESPUELT: bei einem Werkzeug, das im
    Stapelbetrieb laeuft und dessen Fehlerausgabe in eine Datei umgeleitet
    ist, entscheidet sonst die Puffergroesse darueber, ob die Warnung vor oder
    nach der Erfolgsmeldung steht — oder bei einem harten Abbruch gar nicht.
    """
    if context is None or not context.rahmen_befunde:
        return 0

    ziel = stream if stream is not None else sys.stderr
    for befund in context.rahmen_befunde:
        print(befund.als_meldung(praefix), file=ziel)
    print(_NACHSATZ % praefix, file=ziel)

    try:
        ziel.flush()
    except Exception:  # pragma: no cover - Stream ohne flush (Testdoubles)
        pass
    return len(context.rahmen_befunde)

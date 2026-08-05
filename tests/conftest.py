"""
tests/conftest.py — Pytest/Unittest Path-Konfiguration
=======================================================
Stellt sicher, dass das Projektroot im sys.path liegt,
unabhängig davon aus welchem Verzeichnis die Tests aufgerufen werden.

Build: 003 · 2026-04-07
"""
import os
import sys
from pathlib import Path

import pytest

# Projektroot = Elternverzeichnis von tests/
_project_root = Path(__file__).parent.parent.resolve()
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# =============================================================================
# BUILD 667 — DIE TERMINALBREITE WIRD FESTGELEGT
# =============================================================================
# BEFUND (Alex, 2026-08-04, unter pytest-xdist): CE08 in
# tests/test_help_cli_epilog.py fiel mit "assert 135 <= 80" — aber nur im
# parallelen Lauf, nicht im sequenziellen.
#
# URSACHE, nachgemessen: argparse holt seine Zeilenbreite ueber
# shutil.get_terminal_size(), und das beachtet die Umgebungsvariable COLUMNS.
#   - Sequenziell greift pytests Ausgabeumleitung; die Groessenermittlung
#     scheitert und faellt auf 80 zurueck. Der Test bestand also AUS VERSEHEN.
#   - xdist reicht die Breite des Steuerprozesses per COLUMNS an die
#     Arbeitsprozesse weiter. Bei einem 140 Zeichen breiten Fenster kommt dort
#     140 an, und dieselbe Zusicherung faellt.
# Gegenprobe im Baucontainer: 'COLUMNS=140 pytest ...' laesst CE08 auch
# sequenziell fallen, mit exakt derselben Zahl (135). 'COLUMNS=200' laesst ihn
# schon an einer frueheren Zusicherung fallen.
#
# WARUM DAS MEHR IST ALS EIN TESTFEHLER: das Ergebnis eines Regressionstests
# hing an der Fensterbreite des Terminals, in dem er zufaellig lief. Damit
# konnten derselbe Bestand und dieselbe Fassung zweimal verschieden ausfallen,
# ohne dass es am Code lag — und der sequenzielle Lauf haette es nie gezeigt.
# Fuer einen Bestand mit Beweislast ist das keine Kleinigkeit: was hier
# gemessen wird, muss von der Sache abhaengen und nicht von der Umgebung.
#
# ES WIRD DESHALB NICHT DER EINE TEST GEFLICKT, SONDERN DIE URSACHE ENTFERNT.
# COLUMNS wird fuer JEDEN Lauf festgelegt. Damit liefern sequenzieller und
# paralleler Lauf dasselbe Ergebnis, und kein kuenftiger Test kann sich
# unbemerkt wieder an die Fensterbreite haengen.
#
# Der Wert 80 ist der klassische Rueckfallwert von shutil.get_terminal_size()
# und damit genau das, wogegen die bestehenden Zusicherungen ohnehin schon
# geschrieben waren.
#
# Beleg: Sitzung 2026-08-04, Messung Alex (16 min -> 5 min 39 s unter -n 8).
# =============================================================================

# Beim IMPORT setzen und nicht erst in einer Fixture: argparse-Objekte koennen
# schon beim Einsammeln der Tests entstehen (Modulebene), also bevor die erste
# Fixture laeuft. Unter xdist wird diese Datei in JEDEM Arbeitsprozess
# eingelesen — die Festlegung gilt damit auch dort.
os.environ["COLUMNS"] = "80"
os.environ["LINES"] = "24"


@pytest.fixture(autouse=True)
def _terminalbreite_festgelegt():
    """
    Haelt COLUMNS auch dann fest, wenn ein Test die Umgebung veraendert.

    Die Fixture stellt den Wert VOR jedem Test wieder her statt danach: ein
    Test, der COLUMNS setzt und dabei abbricht, wuerde sonst den naechsten
    mitreissen — und der Fehler saehe aus, als laege er beim Nachfolger.
    """
    os.environ["COLUMNS"] = "80"
    os.environ["LINES"] = "24"
    yield

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


# =============================================================================
# BUILD 764 — VORPRUEFUNG DES FREIEN PLATZES IM TEMPORAERVERZEICHNIS
# =============================================================================
# BEFUND (Regressionslauf Alex, 07.09.2026, unter xdist mit 12 Arbeitsprozessen):
# 65 Fehlschlaege und ein Sammelfehler, 6 min 24 s Laufzeit — ALLE auf denselben
# Grund zurueckzufuehren: '/tmp' war voll. Die Meldungen lauteten je nach Stelle
#   OSError: [Errno 28] No space left on device
#   sqlite3.OperationalError: database or disk is full
#   sqlite3.OperationalError: cannot rollback - no transaction is active
# und verteilten sich ueber 15 Testdateien. Keine einzige Zusicherung ist
# gefallen; es gab nichts zu beheben, aber viel zu lesen.
#
# WARUM DAS MEHR IST ALS EINE UNANNEHMLICHKEIT: Ein Regressionslauf, dessen
# Ergebnis von der Fuellung eines Verzeichnisses abhaengt, sagt nichts ueber den
# Code aus — und er sieht aus wie eine Aussage. Wer 65 rote Zeilen sieht, sucht
# den Fehler im Bauwerk. Das ist Zeit, die verloren geht, und im schlechteren
# Fall wird ein ECHTER Fehlschlag zwischen den unechten uebersehen.
#
# Die Pruefung laeuft EINMAL beim Einsammeln und bricht ab, bevor der erste Test
# startet. Sie ersetzt keinen Test — sie sorgt dafuer, dass die Tests ueberhaupt
# etwas messen koennen.
#
# ZUR SCHWELLE: Der Bestand legt je Test eine Handvoll SQLite-Dateien an; unter
# 12 Arbeitsprozessen laufen entsprechend viele gleichzeitig. 200 MB sind
# grosszuegig gegenueber dem tatsaechlichen Bedarf und knapp genug, um nicht auf
# einem sparsam bemessenen Bausystem grundlos auszuloesen. Wer weiss, was er
# tut, hebt sie mit AIW_TESTS_MIN_TMP_MB aus.
# =============================================================================
_MIN_TMP_MB_VORGABE = 200


def pytest_configure(config):
    """
    Bricht ab, wenn im Temporaerverzeichnis zu wenig Platz frei ist.

    Die Meldung nennt Pfad, freien Platz und Schwelle, damit der Grund ohne
    Rueckfrage feststeht.
    """
    import shutil
    import tempfile

    try:
        schwelle_mb = int(os.environ.get("AIW_TESTS_MIN_TMP_MB",
                                         _MIN_TMP_MB_VORGABE))
    except ValueError:
        schwelle_mb = _MIN_TMP_MB_VORGABE
    if schwelle_mb <= 0:            # ausdruecklich abgeschaltet
        return

    verzeichnis = tempfile.gettempdir()
    try:
        frei_mb = shutil.disk_usage(verzeichnis).free // (1024 * 1024)
    except OSError:
        # Laesst sich der Platz nicht ermitteln, wird NICHT abgebrochen: eine
        # Vorpruefung darf keinen Lauf verhindern, den sie nicht beurteilen
        # kann.
        return

    if frei_mb < schwelle_mb:
        raise pytest.UsageError(
            "Zu wenig Platz im Temporaerverzeichnis: %s hat %d MB frei, "
            "gefordert sind %d MB. Der Testbestand legt dort Datenbanken an; "
            "bei vollem Traeger scheitern Dutzende Tests mit 'No space left "
            "on device' beziehungsweise 'database or disk is full', ohne dass "
            "am Code etwas fehlt. Verzeichnis aufraeumen (etwa alte "
            "'pytest-of-*'-Ordner) und erneut fahren. Schwelle aendern: "
            "AIW_TESTS_MIN_TMP_MB, abschalten mit 0."
            % (verzeichnis, frei_mb, schwelle_mb))

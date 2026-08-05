#!/usr/bin/env python3
# =============================================================================
# run_tests.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Unified Testrunner: fuehrt Python-Tests (pytest) und JavaScript-Tests
#   (vitest via npm) aus und liefert eine gemeinsame Zusammenfassung sowie
#   einen Exit-Code, der sagt, WELCHE Seite gefallen ist.
#
# Aufruf (aus beliebigem Verzeichnis):
#   python /pfad/zu/aiw_webserver/run_tests.py
#   python /pfad/zu/aiw_webserver/run_tests.py --python-only
#   python /pfad/zu/aiw_webserver/run_tests.py --js-only
#   python /pfad/zu/aiw_webserver/run_tests.py --leise
#   python /pfad/zu/aiw_webserver/run_tests.py --log-dir /tmp/testlauf
#
# Exit-Codes:
#   0 - alle gefahrenen Suiten bestanden
#   1 - die PYTHON-Suite ist gescheitert
#   2 - die JAVASCRIPT-Suite ist gescheitert
#   3 - BEIDE Suiten sind gescheitert
#   Die Codes sind Bitmasken (1 = Python, 2 = JavaScript). Jeder Aufrufer der
#   Form 'if ! run_tests.py' verhaelt sich unveraendert; wer genauer hinsehen
#   will, erfaehrt aus dem Wert allein, welche Seite gefallen ist.
#
# Abhaengigkeiten:
#   Python:     pytest (pip install pytest)
#   JavaScript: npm + vitest (npm install im Projektverzeichnis)
#
# -----------------------------------------------------------------------------
# BUILD 665 - WARUM DIESER UMBAU (Befund Alex, 2026-08-04)
#
# DAS PROBLEM: bei einem roten Lauf war die Fehlerursache nicht mehr auffindbar.
# Sie stand zwar auf dem Bildschirm, aber tausende Zeilen weiter oben, ausserhalb
# des Bildlaufspeichers des Terminals. Ein Befund, den niemand lesen kann, ist
# von einem nicht erhobenen Befund nicht zu unterscheiden (Grundregel 1).
#
# GEMESSEN (Baucontainer, 2026-08-04, 3131 Tests):
#   pytest -v --tb=short    3240 Zeilen   <- bisheriger Stand
#   pytest -q --tb=long -rf   47 Zeilen
#   vitest (Vorgabe)         155 Zeilen
# Das '-v' allein erzeugte 3131 Zeilen "PASSED". Es faellt weg; '--tb=long'
# gibt im Fehlerfall sogar MEHR Zusammenhang als das bisherige '--tb=short',
# und '-rf' stellt die Liste der gefallenen Tests ganz ans Ende.
#
# DREI MASSNAHMEN:
#   1) Jede Suite schreibt ihre VOLLSTAENDIGE Ausgabe zusaetzlich in eine
#      Protokolldatei. Die Bildschirmausgabe kann abschneiden, die Datei nicht.
#   2) Der Fehlerauszug wird NACH der Zusammenfassung noch einmal ausgegeben.
#      Was man braucht, gehoert ans ENDE des Bildlaufs, nicht an den Anfang.
#   3) Getrennte Exit-Codes je Suite (s. o.).
#
# WARUM WEITERHIN LIVE AUSGEGEBEN WIRD: ein Lauf dauert Minuten. Ohne laufende
# Ausgabe ist ein arbeitendes Werkzeug von einem haengenden nicht zu
# unterscheiden. Wer das nicht will, nimmt '--leise'.
#
# NEBENWIRKUNG DER PROTOKOLLIERUNG: die Unterprozesse schreiben nicht mehr auf
# ein Terminal, sondern in eine Pipe. Beide Werkzeuge schalten dann von sich
# aus die Farbe ab. Deshalb wird sie ausdruecklich wieder eingeschaltet
# (pytest '--color=yes', vitest 'FORCE_COLOR'). Die Steuerzeichen landen damit
# auch in der Protokolldatei - das ist der Preis dafuer, dass der Bildschirm
# aussieht wie zuvor. 'less -R' zeigt sie richtig an.
# -----------------------------------------------------------------------------
#
# Changelog:
#   Build 003: Erstimplementierung (unittest, kein JS).
#   Build 043 (AP-E1): Vollstaendig neu geschrieben.
#     - Python-Suite: pytest statt unittest.TestLoader (bessere Ausgabe).
#     - JavaScript-Suite: vitest via subprocess (npm test).
#     - Gemeinsame Zusammenfassung mit Zaehlung bestanden/fehlgeschlagen.
#     - --python-only / --js-only Flags fuer selektiven Aufruf.
#     - Pruefung ob npm und node_modules vorhanden sind.
#     Beleg: AP-E1, Projektgespraech 2026-04-19
#   Build 665: Protokolldateien je Suite, Fehlerauszug am Ende, getrennte
#     Exit-Codes, --leise und --log-dir. pytest von '-v --tb=short' auf
#     '-q --tb=long -rf'. Beleg: Befund Alex 2026-08-04, Messung s. o.
#
# Version: v0.8.665 - Build: 665 - 2026-08-04
# =============================================================================

import argparse
import datetime
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from management.help import cli_epilog  # noqa: E402

# Projektroot: Verzeichnis in dem diese Datei liegt.
PROJECT_ROOT = Path(__file__).parent.resolve()

# Vorgabe-Ablage der Protokolle. 'logs/' und '*.log' stehen in .gitignore
# (geprueft 2026-08-04) - die Protokolle koennen also nicht versehentlich in
# eine Lieferung geraten.
LOG_DIR_VORGABE = PROJECT_ROOT / "logs"

# Exit-Code-Bits (s. Kopf).
BIT_PYTHON = 1
BIT_JS = 2

# Zeilen des Fehlerauszugs am Ende. Gross genug fuer mehrere Tracebacks,
# klein genug, um nicht selbst wieder aus dem Bildlauf zu fallen.
AUSZUG_ZEILEN = 120

# Marken, ab denen ein Protokoll interessant wird. Sie sind bewusst
# grosszuegig: lieber ein paar Zeilen zu viel im Auszug als der Anfang eines
# Tracebacks zu wenig.
MARKEN_PYTHON = ("FAILURES", "ERRORS", "short test summary")
MARKEN_JS = ("FAIL ", "Unhandled Error", "Failed Tests")


def _header(text: str) -> None:
    line = "=" * 60
    print(f"\n{line}")
    print(f"  {text}")
    print(line)


def _zeitstempel() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _lauf_mit_protokoll(cmd: List[str], log_pfad: Path, *, leise: bool,
                        umgebung: Optional[dict] = None
                        ) -> Tuple[int, List[str]]:
    """
    Fuehrt cmd aus, schreibt die Ausgabe in log_pfad UND (sofern nicht leise)
    auf den Bildschirm. Rueckgabe: (Exit-Code, alle Zeilen).

    stderr wird ausdruecklich nach stdout umgelenkt. Zwei getrennte Stroeme
    liessen sich nicht verlaesslich in die richtige Reihenfolge bringen, und
    eine Fehlermeldung an der falschen Stelle im Protokoll ist schlimmer als
    eine ohne Kennzeichnung.

    Die Ausgabe wird ZEILENWEISE weitergereicht und nicht am Ende auf einmal:
    ein Lauf dauert Minuten, und eine stumme Minute ist von einem Haenger
    nicht zu unterscheiden.
    """
    log_pfad.parent.mkdir(parents=True, exist_ok=True)
    zeilen: List[str] = []
    with open(log_pfad, "w", encoding="utf-8", errors="replace") as log:
        prozess = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=umgebung,
            text=True,
            errors="replace",
            bufsize=1,
        )
        if prozess.stdout is not None:
            for zeile in prozess.stdout:
                zeilen.append(zeile.rstrip("\n"))
                log.write(zeile)
                if not leise:
                    sys.stdout.write(zeile)
                    sys.stdout.flush()
        prozess.wait()
    return prozess.returncode, zeilen


def _fehlerauszug(zeilen: List[str], marken: Tuple[str, ...]) -> List[str]:
    """
    Sucht die erste Stelle, ab der es interessant wird, und gibt den Rest
    zurueck (hoechstens AUSZUG_ZEILEN).

    ABSICHTLICH KEINE KLUGE ANALYSE: der Auszug soll nichts WEGLASSEN, was zum
    Fehler gehoert - er schneidet nur vorne ab. Wird keine Marke gefunden,
    stehen die letzten Zeilen da; das ist immer noch besser als nichts, und
    die vollstaendige Fassung liegt ohnehin in der Protokolldatei. Wird
    gekuerzt, STEHT DAS DA (Grundregel 1) - ein stillschweigend beschnittener
    Auszug waere genau der Fehler, den dieser Umbau behebt.
    """
    start = None
    for i, z in enumerate(zeilen):
        if any(m in z for m in marken):
            start = i
            break
    auszug = zeilen[start:] if start is not None else list(zeilen)
    if len(auszug) > AUSZUG_ZEILEN:
        weggelassen = len(auszug) - AUSZUG_ZEILEN
        auszug = ([f"[... {weggelassen} Zeile(n) hier ausgelassen - "
                   f"vollstaendig in der Protokolldatei ...]"]
                  + auszug[-AUSZUG_ZEILEN:])
    return auszug


def _pytest_version() -> Optional[str]:
    """
    Die pytest-Fassung DIESES Interpreters - oder None, wenn er keine hat.

    Bewusst ueber 'sys.executable -m pytest --version' und nicht ueber
    'import pytest': geprueft werden muss genau der Aufruf, der gleich
    stattfindet. Ein Import im laufenden Prozess koennte gelingen, waehrend
    der Unterprozess an etwas anderem scheitert.
    """
    try:
        p = subprocess.run([sys.executable, "-m", "pytest", "--version"],
                           capture_output=True, text=True, timeout=60,
                           cwd=str(PROJECT_ROOT))
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    return (p.stdout or p.stderr).strip().splitlines()[0] if (p.stdout or p.stderr) else "unbekannt"


def _xdist_da() -> bool:
    """
    Ist pytest-xdist in DIESEM Interpreter vorhanden?

    Wie bei _pytest_version: geprueft wird der Interpreter, der gleich fahren
    soll - nicht der, in dem dieser Code laeuft, und schon gar nicht ein
    'pytest' auf dem PATH.
    """
    try:
        p = subprocess.run([sys.executable, "-c", "import xdist"],
                           capture_output=True, timeout=60,
                           cwd=str(PROJECT_ROOT))
    except (OSError, subprocess.SubprocessError):
        return False
    return p.returncode == 0


def run_python_tests(log_pfad: Path, leise: bool = False,
                     jobs: Optional[str] = None
                     ) -> Tuple[bool, List[str]]:
    """
    Fuehrt Python-Tests via pytest aus. Rueckgabe: (bestanden, Fehlerauszug).

    '-q --tb=long -rf' statt '-v --tb=short' (Build 665): '-v' erzeugte eine
    Zeile je Test - bei 3131 Tests der Grund, warum die Fehlermeldung nicht
    mehr auffindbar war. '--tb=long' gibt im Fehlerfall MEHR Zusammenhang als
    zuvor, '-rf' stellt die Liste der gefallenen Tests ans Ende.
    """
    _header("Python-Tests (pytest)")
    print(f"  Protokoll:    {log_pfad}")
    # BUILD 666 -- WOMIT WURDE GEMESSEN. Steht ab jetzt in jedem Lauf und in
    # jedem Protokoll. Anlass: am 04.08.2026 hat 'pytest --version' auf der
    # Kommandozeile funktioniert, waehrend derselbe Lauf ueber run_tests.py
    # an "No module named pytest" scheiterte -- weil auf dem PATH ein pytest
    # aus dem Benutzerverzeichnis lag, im venv aber keines. Zwei Interpreter
    # mit womoeglich verschiedenen Paketstaenden fahren dieselbe Suite; dann
    # kann derselbe Bestand zweimal verschieden ausfallen, ohne dass es am
    # Code liegt. Fuer ein forensisches Werkzeug ist "womit wurde gemessen"
    # keine Nebensache, sondern Teil des Befundes.
    print(f"  Interpreter:  {sys.executable}")

    # VORAUSSETZUNG ZUERST -- und als solche benannt. Die JavaScript-Seite
    # prueft ihre Voraussetzungen seit jeher (npm, node_modules), die
    # Python-Seite tat es nicht: eine fehlende Bibliothek sah deshalb aus wie
    # ein Testfehler. Das ist ein Unterschied ums Ganze - im einen Fall ist
    # der Bestand kaputt, im anderen die Umgebung.
    version = _pytest_version()
    if version is None:
        meldung = [
            "VORAUSSETZUNG FEHLT -- ES WURDE NICHT GETESTET.",
            "",
            f"Der Interpreter {sys.executable} kennt kein Modul 'pytest'.",
            "",
            "ACHTUNG: dass 'pytest --version' auf der Kommandozeile "
            "funktioniert, beweist das Gegenteil NICHT - dann liegt ein "
            "pytest auf dem PATH, aber nicht in DIESER Umgebung.",
            "",
            "Abhilfe (in der aktiven Umgebung):",
            "    python -m pip install pytest",
            "Nachpruefen:",
            "    python -m pytest --version",
        ]
        for z in meldung:
            print(z)
        return False, meldung
    print(f"  pytest:       {version}")

    cmd = [sys.executable, "-m", "pytest", "tests/",
           "-q", "--tb=long", "-rf", "--color=yes"]

    # BUILD 667 -- PARALLEL FAHREN, WENN MOEGLICH.
    # Gemessen auf der Maschine von Alex (2026-08-04): 16 min sequenziell
    # gegen 5 min 39 s mit '-n 8'. Es wird dabei KEINE Abdeckung aufgegeben -
    # es laufen dieselben 3147 Tests.
    #
    # ES DARF ABER NIE VORAUSSETZUNG WERDEN. Die Produktions-VM unter Windows
    # ist offline; dort laesst sich pytest-xdist nicht nachinstallieren. Fehlt
    # es, wird deshalb SEQUENZIELL GEFAHREN UND DAS GESAGT - nicht
    # abgebrochen (dann liefe gar nichts) und nicht verschwiegen (dann
    # glaubte man, parallel gemessen zu haben).
    if jobs:
        if _xdist_da():
            cmd += ["-n", jobs]
            print(f"  Parallel:     -n {jobs}")
        else:
            hinweis = (f"  Parallel:     ANGEFORDERT (-n {jobs}), ABER NICHT "
                       f"MOEGLICH - pytest-xdist fehlt in dieser Umgebung.\n"
                       f"                Es wird SEQUENZIELL gefahren. "
                       f"Abhilfe: python -m pip install pytest-xdist")
            print(hinweis)
    code, zeilen = _lauf_mit_protokoll(cmd, log_pfad, leise=leise)
    if code == 0:
        return True, []
    return False, _fehlerauszug(zeilen, MARKEN_PYTHON)


def run_js_tests(log_pfad: Path, leise: bool = False
                 ) -> Tuple[bool, List[str]]:
    """
    Fuehrt JavaScript-Tests via vitest (npm test) aus.
    Voraussetzung: node_modules muss vorhanden sein (npm install).
    Rueckgabe: (bestanden, Fehlerauszug).
    """
    _header("JavaScript-Tests (vitest)")
    print(f"  Protokoll:    {log_pfad}")

    npm_check = subprocess.run(
        ["npm", "--version"],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )
    if npm_check.returncode != 0:
        # DER AUSFALL WANDERT IN DEN AUSZUG. Sonst stuende am Ende nur
        # "JavaScript: FEHLGESCHLAGEN", und die Ursache waere wieder oben im
        # Bildlauf verschwunden - genau der Fehler, den dieser Umbau behebt.
        meldung = ["FEHLER: npm nicht gefunden. Bitte Node.js installieren.",
                   "        Download: https://nodejs.org/"]
        for z in meldung:
            print(z)
        return False, meldung

    node_modules = PROJECT_ROOT / "node_modules"
    if not node_modules.exists():
        print("node_modules nicht gefunden - fuehre npm install aus...")
        install = subprocess.run(["npm", "install"], cwd=str(PROJECT_ROOT))
        if install.returncode != 0:
            meldung = ["FEHLER: npm install fehlgeschlagen.",
                       "        Auf einer Maschine ohne Internetzugang "
                       "scheitert der Lauf hier und nicht an einem Test."]
            for z in meldung:
                print(z)
            return False, meldung

    # AIW_PYTHON (Build 603): die JavaScript-Seite muss fuer die Hilfe-Paritaet
    # das Hilferegister lesen und ruft dafuer Python auf. Ohne diesen Hinweis
    # muesste sie 'python3'/'python' raten - und traefe im ungluecklichen Fall
    # einen anderen Interpreter als die pytest-Seite, also womoeglich einen
    # anderen Stand des Registers. Hier ist der richtige bekannt.
    umgebung = dict(os.environ)
    umgebung["AIW_PYTHON"] = sys.executable
    # FORCE_COLOR (Build 665): die Ausgabe laeuft jetzt durch eine Pipe, und
    # vitest schaltet dann von sich aus die Farbe ab.
    umgebung["FORCE_COLOR"] = "1"
    code, zeilen = _lauf_mit_protokoll(["npm", "test"], log_pfad,
                                       leise=leise, umgebung=umgebung)
    if code == 0:
        return True, []
    return False, _fehlerauszug(zeilen, MARKEN_JS)


def zusammenfassen(ergebnisse: Dict[str, Tuple[bool, List[str], Path]]) -> int:
    """
    Zusammenfassung ausgeben, Fehlerauszuege anhaengen, Exit-Code bilden.

    Herausgezogen, damit die Regression sie ohne echte Testlaeufe pruefen kann
    (Grundregel: Tests sollen die ECHTE Funktion pruefen, nicht einen Nachbau).
    """
    _header("Testergebnis - Zusammenfassung")
    code = 0
    for suite, (passed, _auszug, pfad) in ergebnisse.items():
        status = "BESTANDEN" if passed else "FEHLGESCHLAGEN"
        symbol = "\u2713" if passed else "\u2717"
        print(f"  {symbol}  {suite}: {status}")
        # DER PFAD STEHT AUCH IM ERFOLGSFALL DA. Wer ihn erst sucht, wenn er
        # ihn braucht, sucht ihn im ungeeignetsten Moment.
        print(f"      Protokoll: {pfad}")
        if not passed:
            code |= BIT_PYTHON if suite.startswith("Python") else BIT_JS

    print()
    if code == 0:
        print("  Alle Testsuites bestanden.")
        print()
        return 0

    print("  FEHLER: Mindestens eine Testsuite fehlgeschlagen.")

    # DER AUSZUG STEHT GANZ UNTEN. Das ist der Kern dieses Umbaus: die
    # Bildschirmausgabe eines Laufs ist laenger als der Bildlaufspeicher, und
    # was man braucht, muss deshalb am ENDE stehen - dort, wo der Blick nach
    # dem Lauf ohnehin ist.
    for suite, (passed, auszug, pfad) in ergebnisse.items():
        if passed or not auszug:
            continue
        _header(f"Fehlerauszug - {suite}")
        for zeile in auszug:
            print(zeile)
        print()
        print(f"  Vollstaendig: {pfad}")

    print()
    return code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified Testrunner: Python (pytest) + JavaScript (vitest).",
        epilog=cli_epilog.epilog("run_tests"),
        formatter_class=cli_epilog.HilfeFormat,
    )
    parser.add_argument(
        "--python-only", action="store_true",
        help="Nur Python-Tests ausfuehren.",
    )
    parser.add_argument(
        "--js-only", action="store_true",
        help="Nur JavaScript-Tests ausfuehren.",
    )
    parser.add_argument(
        "--leise", action="store_true",
        help="Keine laufende Ausgabe. Es bleiben Protokolldatei, "
             "Zusammenfassung und im Fehlerfall der Auszug.",
    )
    parser.add_argument(
        "--jobs", default=None, metavar="N",
        help="Python-Tests parallel fahren (pytest-xdist). 'auto' nimmt die "
             "Zahl der Kerne. Fehlt xdist, wird sequenziell gefahren und das "
             "gemeldet.",
    )
    parser.add_argument(
        "--log-dir", default=None, metavar="VERZEICHNIS",
        help="Ablage der Protokolle (Vorgabe: <Projektwurzel>/logs).",
    )
    args = parser.parse_args()

    run_python = not args.js_only
    run_js     = not args.python_only

    log_dir = Path(args.log_dir).resolve() if args.log_dir else LOG_DIR_VORGABE
    stempel = _zeitstempel()

    ergebnisse: Dict[str, Tuple[bool, List[str], Path]] = {}

    if run_python:
        pfad = log_dir / f"test_pytest_{stempel}.log"
        ok, auszug = run_python_tests(pfad, args.leise, args.jobs)
        ergebnisse["Python (pytest)"] = (ok, auszug, pfad)

    if run_js:
        pfad = log_dir / f"test_vitest_{stempel}.log"
        ok, auszug = run_js_tests(pfad, args.leise)
        ergebnisse["JavaScript (vitest)"] = (ok, auszug, pfad)

    return zusammenfassen(ergebnisse)


if __name__ == "__main__":
    # Projektroot in sys.path eintragen damit Module gefunden werden.
    sys.path.insert(0, str(PROJECT_ROOT))
    sys.exit(main())

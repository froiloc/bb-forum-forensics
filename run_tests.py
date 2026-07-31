#!/usr/bin/env python3
# =============================================================================
# run_tests.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Unified Testrunner: fuehrt Python-Tests (pytest) und JavaScript-Tests
#   (vitest via npm) aus und liefert eine gemeinsame Zusammenfassung sowie
#   einen einheitlichen Exit-Code.
#
# Aufruf (aus beliebigem Verzeichnis):
#   python /pfad/zu/aiw_webserver/run_tests.py
#   python /pfad/zu/aiw_webserver/run_tests.py --python-only
#   python /pfad/zu/aiw_webserver/run_tests.py --js-only
#
# Exit-Codes:
#   0 — alle Suites bestanden
#   1 — mindestens eine Suite fehlgeschlagen oder nicht ausfuehrbar
#
# Abhaengigkeiten:
#   Python:     pytest (pip install pytest)
#   JavaScript: npm + vitest (npm install im Projektverzeichnis)
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
#
# Version: v0.6.043 · Build: 043 · 2026-04-19
# =============================================================================

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Projektroot: Verzeichnis in dem diese Datei liegt.
PROJECT_ROOT = Path(__file__).parent.resolve()


def _header(text: str) -> None:
    line = "=" * 60
    print(f"\n{line}")
    print(f"  {text}")
    print(line)


def run_python_tests() -> bool:
    """
    Fuehrt Python-Tests via pytest aus.

    Returns:
        True wenn alle Tests bestanden, False sonst.
    """
    _header("Python-Tests (pytest)")

    # pytest im Projektroot aufrufen — findet tests/ automatisch.
    cmd = [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return result.returncode == 0


def run_js_tests() -> bool:
    """
    Fuehrt JavaScript-Tests via vitest (npm test) aus.

    Voraussetzung: node_modules muss vorhanden sein (npm install).

    Returns:
        True wenn alle Tests bestanden, False sonst.
    """
    _header("JavaScript-Tests (vitest)")

    # Pruefe ob npm verfuegbar ist.
    npm_check = subprocess.run(
        ["npm", "--version"],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )
    if npm_check.returncode != 0:
        print("FEHLER: npm nicht gefunden. Bitte Node.js installieren.")
        print("       Download: https://nodejs.org/")
        return False

    # Pruefe ob node_modules vorhanden ist.
    node_modules = PROJECT_ROOT / "node_modules"
    if not node_modules.exists():
        print("node_modules nicht gefunden — fuehre npm install aus...")
        install = subprocess.run(
            ["npm", "install"],
            cwd=str(PROJECT_ROOT),
        )
        if install.returncode != 0:
            print("FEHLER: npm install fehlgeschlagen.")
            return False

    # vitest ausfuehren.
    #
    # AIW_PYTHON (Build 603): die JavaScript-Seite muss fuer die Hilfe-Paritaet
    # das Hilferegister lesen und ruft dafuer Python auf. Ohne diesen Hinweis
    # muesste sie 'python3'/'python' raten - und traefe im ungluecklichen Fall
    # einen anderen Interpreter als die pytest-Seite, also womoeglich einen
    # anderen Stand des Registers. Hier ist der richtige bekannt.
    umgebung = dict(os.environ)
    umgebung["AIW_PYTHON"] = sys.executable
    result = subprocess.run(
        ["npm", "test"],
        cwd=str(PROJECT_ROOT),
        env=umgebung,
    )
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified Testrunner: Python (pytest) + JavaScript (vitest).",
    )
    parser.add_argument(
        "--python-only",
        action="store_true",
        help="Nur Python-Tests ausfuehren.",
    )
    parser.add_argument(
        "--js-only",
        action="store_true",
        help="Nur JavaScript-Tests ausfuehren.",
    )
    args = parser.parse_args()

    run_python = not args.js_only
    run_js     = not args.python_only

    results: dict[str, bool] = {}

    if run_python:
        results["Python (pytest)"] = run_python_tests()

    if run_js:
        results["JavaScript (vitest)"] = run_js_tests()

    # Gemeinsame Zusammenfassung
    _header("Testergebnis — Zusammenfassung")
    all_passed = True
    for suite, passed in results.items():
        status = "BESTANDEN" if passed else "FEHLGESCHLAGEN"
        symbol = "✓" if passed else "✗"
        print(f"  {symbol}  {suite}: {status}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("  Alle Testsuites bestanden.")
    else:
        print("  FEHLER: Mindestens eine Testsuite fehlgeschlagen.")
    print()

    return 0 if all_passed else 1


if __name__ == "__main__":
    # Projektroot in sys.path eintragen damit Module gefunden werden.
    sys.path.insert(0, str(PROJECT_ROOT))
    sys.exit(main())

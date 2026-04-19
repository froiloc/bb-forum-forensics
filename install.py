#!/usr/bin/env python3
# =============================================================================
# install.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 1: Deployment
# =============================================================================
# Zweck:
#   Installiert den aiw_webserver auf dem Zielsystem.
#   Macht den Webserver lauffaehig: Python-Pakete, Verzeichnisstruktur,
#   optionale DEV-Werkzeuge (Node.js-Tests).
#
# Argumente:
#   --target=[dev|prod]   Installationsziel (Standard: prod)
#   --os=[win|linux]      Zielbetriebssystem (Standard: auto-detect)
#
#   DEV:  Laufzeit-Pakete + Dev-Pakete (pytest, Node.js optional)
#   PROD: Nur Laufzeit-Pakete, kein Node.js, kein pytest
#
# Node.js-Hinweis:
#   Node.js wird NUR im DEV-Modus fuer die JavaScript-Tests (vitest)
#   benoetigt. Im PROD-Modus ist Node.js nicht erforderlich.
#   Beleg: AP-E2, Projektgespraech 2026-04-19
#
# Aufruf:
#   python install.py                      # PROD, auto-detect OS
#   python install.py --target=dev         # DEV, auto-detect OS
#   python install.py --target=prod --os=win
#   python install.py --target=dev --os=linux
#
# Voraussetzungen:
#   - Python 3.10+ (wird geprueft)
#   - pip (Standard-Stdlib)
#   - setup/win64/wheels/ oder setup/linux64/wheels/ (befuellt von prepare_deployment.py)
#     ODER Internetverbindung fuer Online-Installation
#
# Beleg: AP-E2, Projektgespraech 2026-04-19
# Version: v0.6.044 · Build: 044 · 2026-04-19
# =============================================================================

import argparse
import platform
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Laufzeit-Abhaengigkeiten (PROD + DEV)
RUNTIME_PACKAGES = [
    "pyyaml",
    "lxml",
    "pyeditorjs",   # AP-E5: serverseitiger Editor.js-HTML-Export
]

# Nur-DEV-Abhaengigkeiten
DEV_PACKAGES = [
    "pytest",
    "pytest-asyncio",
]

# Mindest-Python-Version
MIN_PYTHON = (3, 10)


def _check_python() -> None:
    """Prueft die Python-Version. Bricht bei zu alter Version ab."""
    v = sys.version_info
    if (v.major, v.minor) < MIN_PYTHON:
        print(
            f"FEHLER: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ benoetigt, "
            f"gefunden: {v.major}.{v.minor}.{v.micro}"
        )
        sys.exit(1)
    print(f"  Python {v.major}.{v.minor}.{v.micro} — OK")


def _detect_os() -> str:
    """Erkennt das Betriebssystem automatisch."""
    system = platform.system().lower()
    if system == "windows":
        return "win"
    elif system == "linux":
        return "linux"
    else:
        print(f"WARNUNG: Unbekanntes OS '{system}' — verwende 'linux'.")
        return "linux"


def _wheels_dir(os_target: str) -> Path:
    """Gibt das Wheels-Verzeichnis fuer das Zielbetriebssystem zurueck."""
    subdir = "win64" if os_target == "win" else "linux64"
    return SCRIPT_DIR / "setup" / subdir / "wheels"


def _install_packages(packages: list[str], wheels_dir: Path) -> None:
    """
    Installiert Python-Pakete.
    Bevorzugt Offline-Installation aus wheels_dir,
    faellt auf Online-Installation zurueck wenn wheels fehlen.
    """
    if not packages:
        return

    if wheels_dir.exists() and any(wheels_dir.iterdir()):
        # Offline-Installation aus vorbereiteten Wheels
        print(f"  Offline-Installation aus {wheels_dir} …")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install",
             "--no-index", "--find-links", str(wheels_dir),
             "--upgrade"] + packages,
        )
    else:
        # Online-Installation (kein setup/ vorhanden oder leer)
        print(f"  Online-Installation (setup/wheels nicht gefunden) …")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade"] + packages,
        )

    if result.returncode != 0:
        print(f"FEHLER: pip install fehlgeschlagen.")
        sys.exit(1)


def _check_node_optional() -> None:
    """
    Prueft ob Node.js verfuegbar ist (nur DEV, nicht kritisch).
    Node.js ist nur fuer JavaScript-Tests (vitest) erforderlich.
    """
    result = subprocess.run(
        ["node", "--version"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"  Node.js {result.stdout.strip()} — gefunden (fuer JS-Tests)")
    else:
        print(
            "  HINWEIS: Node.js nicht gefunden.\n"
            "    JavaScript-Tests (vitest) koennen nicht ausgefuehrt werden.\n"
            "    Fuer Entwicklung: https://nodejs.org/ installieren.\n"
            "    Fuer PROD-Betrieb: Node.js nicht erforderlich."
        )


def _verify_installation(packages: list[str]) -> None:
    """Prueft ob alle installierten Pakete importierbar sind."""
    import importlib
    # Paketname -> Importname-Mapping fuer abweichende Namen
    import_names = {
        "pyyaml": "yaml",
        "pytest-asyncio": "pytest_asyncio",
    }
    all_ok = True
    for pkg in packages:
        import_name = import_names.get(pkg, pkg.replace("-", "_"))
        try:
            importlib.import_module(import_name)
            print(f"  {pkg} — OK")
        except ImportError:
            print(f"  {pkg} — FEHLER (nicht importierbar)")
            all_ok = False
    if not all_ok:
        print("\nFEHLER: Nicht alle Pakete konnten verifiziert werden.")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="aiw_webserver installieren (AP-E2)."
    )
    parser.add_argument(
        "--target",
        choices=["dev", "prod"],
        default="prod",
        help="Installationsziel: dev (inkl. Testwerkzeuge) oder prod (Standard)",
    )
    parser.add_argument(
        "--os",
        choices=["win", "linux"],
        default=None,
        help="Zielbetriebssystem (Standard: auto-detect)",
    )
    args = parser.parse_args()

    os_target = args.os or _detect_os()
    target    = args.target

    print("=" * 60)
    print(f"  install.py — aiw_webserver")
    print(f"  Ziel: {target.upper()} | OS: {os_target}")
    print("=" * 60)

    # Python-Version pruefen
    print("\n[1/4] Python-Version pruefen …")
    _check_python()

    # Pakete bestimmen
    packages = RUNTIME_PACKAGES.copy()
    if target == "dev":
        packages += DEV_PACKAGES

    # Pakete installieren
    print(f"\n[2/4] Python-Pakete installieren ({len(packages)}) …")
    wheels = _wheels_dir(os_target)
    _install_packages(packages, wheels)

    # Verifikation
    print("\n[3/4] Installation verifizieren …")
    _verify_installation(packages)

    # DEV: Node.js-Pruefung (optional, nicht kritisch)
    if target == "dev":
        print("\n[4/4] DEV: Node.js pruefen …")
        _check_node_optional()
    else:
        print("\n[4/4] PROD: Node.js nicht erforderlich — uebersprungen.")

    print("\n" + "=" * 60)
    print(f"  Installation abgeschlossen ({target.upper()} / {os_target}).")
    if target == "prod":
        print("  Webserver starten: python main.py")
    else:
        print("  Tests ausfuehren:  python run_tests.py")
        print("  Webserver starten: python main.py")
    print("=" * 60)


if __name__ == "__main__":
    main()

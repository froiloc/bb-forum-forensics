#!/usr/bin/env python3
# =============================================================================
# prepare_deployment.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 1: Deployment
# =============================================================================
# Zweck:
#   Bereitet die setup/-Verzeichnisse fuer den Installer (install.py) vor.
#   Laeuft auf einem Rechner MIT Internetzugang und Baustelle-1-Ressourcen.
#
#   Schritte:
#   1. Editor.js-Bundle bauen (ruft deployment/build_editor_bundle.py auf)
#   2. Python-Abhaengigkeiten als Wheels herunterladen (win64 + linux64)
#   3. Verzeichnisstruktur in setup/win64/ und setup/linux64/ aufbauen
#   4. MD5-Manifest fuer alle setup/-Dateien erstellen
#
#   Baustelle 1 wird spaeter ergaenzen:
#   - Portabler Firefox ESR (win64/linux64)
#   - Weitere plattformspezifische Ressourcen
#
# Aufruf:
#   python prepare_deployment.py
#   python prepare_deployment.py --skip-bundle   # nur wheels, kein npm
#   python prepare_deployment.py --skip-wheels   # nur bundle, keine wheels
#
# Voraussetzungen:
#   - Node.js >= 18, npm >= 9 (fuer --bundle)
#   - pip und Python 3.x (fuer --wheels)
#   - Internetverbindung
#
# Beleg: AP-E2, Projektgespraech 2026-04-19
# Version: v0.6.044 · Build: 044 · 2026-04-19
# =============================================================================

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR   = Path(__file__).resolve().parent
SETUP_WIN    = SCRIPT_DIR / "setup" / "win64"
SETUP_LINUX  = SCRIPT_DIR / "setup" / "linux64"
BUNDLE_SCRIPT = SCRIPT_DIR / "deployment" / "build_editor_bundle.py"
STATIC_EDITOR = SCRIPT_DIR / "static" / "editor"

# Python-Pakete fuer den Webserver (Laufzeit, kein Node.js)
RUNTIME_PACKAGES = [
    "pyyaml",
    "lxml",
]

# Python-Pakete nur fuer DEV (Tests etc.)
DEV_PACKAGES = [
    "pytest",
    "pytest-asyncio",
]


def _header(text: str) -> None:
    print(f"\n{'=' * 60}\n  {text}\n{'=' * 60}")


def _md5(path: Path) -> str:
    h = hashlib.md5()
    h.update(path.read_bytes())
    return h.hexdigest()


def _build_bundle(skip: bool) -> None:
    """Schritt 1: Editor.js-Bundle bauen."""
    _header("Schritt 1: Editor.js-Bundle")
    if skip:
        print("  Uebersprungen (--skip-bundle).")
        return
    if not BUNDLE_SCRIPT.exists():
        print(f"FEHLER: {BUNDLE_SCRIPT} nicht gefunden.")
        sys.exit(1)
    result = subprocess.run(
        [sys.executable, str(BUNDLE_SCRIPT)],
        cwd=str(SCRIPT_DIR),
    )
    if result.returncode != 0:
        print("FEHLER: build_editor_bundle.py fehlgeschlagen.")
        sys.exit(1)


def _download_wheels(target_dir: Path, platform_tag: str, packages: list[str]) -> None:
    """
    Laedt Python-Wheels fuer eine Zielplattform herunter.
    platform_tag: z.B. 'win_amd64' oder 'manylinux2014_x86_64'
    """
    wheels_dir = target_dir / "wheels"
    wheels_dir.mkdir(parents=True, exist_ok=True)

    print(f"  Wheels herunterladen fuer {platform_tag} nach {wheels_dir} …")
    result = subprocess.run(
        [
            sys.executable, "-m", "pip", "download",
            "--dest", str(wheels_dir),
            "--platform", platform_tag,
            "--python-version", "314",
            "--only-binary", ":all:",
            "--no-deps",
        ] + packages,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Fallback: ohne Platform-Einschraenkung (pure-Python-Pakete)
        print(f"  Hinweis: Platform-spezifischer Download fehlgeschlagen, "
              f"versuche universell …")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "download",
             "--dest", str(wheels_dir),
             "--no-deps",
            ] + packages,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"WARNUNG: Wheels konnten nicht heruntergeladen werden:")
            print(result.stderr[-500:])
            return

    # Heruntergeladene Dateien auflisten
    downloaded = list(wheels_dir.glob("*.whl")) + list(wheels_dir.glob("*.tar.gz"))
    for f in downloaded:
        print(f"    {f.name} [{_md5(f)[:8]}...]")


def _build_wheels(skip: bool) -> None:
    """Schritt 2: Python-Wheels fuer win64 und linux64 herunterladen."""
    _header("Schritt 2: Python-Wheels herunterladen")
    if skip:
        print("  Uebersprungen (--skip-wheels).")
        return

    all_packages = RUNTIME_PACKAGES + DEV_PACKAGES

    print("\n  [win64] …")
    _download_wheels(SETUP_WIN, "win_amd64", all_packages)

    print("\n  [linux64] …")
    _download_wheels(SETUP_LINUX, "manylinux2014_x86_64", all_packages)


def _write_setup_metadata() -> None:
    """Schritt 3: Metadaten und Platzhalter-Readme in setup/ schreiben."""
    _header("Schritt 3: Setup-Metadaten")

    for setup_dir, platform in [(SETUP_WIN, "win64"), (SETUP_LINUX, "linux64")]:
        setup_dir.mkdir(parents=True, exist_ok=True)
        readme = setup_dir / "README.txt"
        readme.write_text(
            f"aiw_webserver — Setup-Dateien fuer {platform}\n"
            f"Erstellt: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Enthaelt:\n"
            f"  wheels/  — Python-Pakete (Offline-Installation)\n"
            f"\nBaustelle 1 wird ergaenzen:\n"
            f"  firefox/ — Portabler Firefox ESR\n"
            f"  python/  — Portable Python-Laufzeitumgebung\n",
            encoding="utf-8",
        )
        print(f"  {readme}")


def _write_manifest() -> None:
    """Schritt 4: MD5-Manifest aller setup/-Dateien."""
    _header("Schritt 4: MD5-Manifest erstellen")

    manifest = {"created_at": int(time.time()), "files": {}}

    for setup_dir in (SETUP_WIN, SETUP_LINUX):
        if not setup_dir.exists():
            continue
        for f in sorted(setup_dir.rglob("*")):
            if f.is_file():
                rel = str(f.relative_to(SCRIPT_DIR))
                manifest["files"][rel] = _md5(f)

    # Bundle-Dateien
    if STATIC_EDITOR.exists():
        for f in sorted(STATIC_EDITOR.glob("*")):
            if f.is_file():
                rel = str(f.relative_to(SCRIPT_DIR))
                manifest["files"][rel] = _md5(f)

    manifest_path = SCRIPT_DIR / "setup" / "deployment_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  {manifest_path.name}: {len(manifest['files'])} Datei(en) erfasst")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deployment-Vorbereitung: Bundle + Wheels + Setup-Struktur."
    )
    parser.add_argument(
        "--skip-bundle", action="store_true",
        help="Editor.js-Bundle-Schritt ueberspringen"
    )
    parser.add_argument(
        "--skip-wheels", action="store_true",
        help="Wheel-Download-Schritt ueberspringen"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  prepare_deployment.py")
    print("  IT-Forensisches Ermittlungswerkzeug — AP-E2")
    print("=" * 60)

    _build_bundle(args.skip_bundle)
    _build_wheels(args.skip_wheels)
    _write_setup_metadata()
    _write_manifest()

    print("\n" + "=" * 60)
    print("  Deployment-Vorbereitung abgeschlossen.")
    print("=" * 60)


if __name__ == "__main__":
    main()

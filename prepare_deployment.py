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
# Version: v0.6.301 · Build: 301 · 2026-06-24
# =============================================================================

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from management.help import cli_epilog  # noqa: E402

SCRIPT_DIR   = Path(__file__).resolve().parent
SETUP_WIN    = SCRIPT_DIR / "setup" / "win64"
SETUP_LINUX  = SCRIPT_DIR / "setup" / "linux64"
BUNDLE_SCRIPT = SCRIPT_DIR / "deployment" / "build_editor_bundle.py"
STATIC_EDITOR = SCRIPT_DIR / "static" / "editor"

# Python-Pakete fuer den Webserver (Laufzeit, kein Node.js).
# Build 301: pyeditorjs + python-docx ergaenzt (zuvor fehlten beide offline).
# Beleg: Projektgespraech 2026-06-24 (offline-Vollstaendigkeit).
RUNTIME_PACKAGES = [
    "pyyaml",
    "lxml",
    "pyeditorjs",   # AP-E5: serverseitiger Editor.js-HTML-Export
    "python-docx",  # B6: DOCX-Export
    "reportlab",    # Build 404: PDF-Export. reportlab 5.0.0 ist py3-none-any
                    # (rein Python). --platform/--only-binary laedt es plus die
                    # Abhaengigkeiten pillow (cp314-Wheel je Plattform) und
                    # charset-normalizer automatisch mit (Beleg: PyPI 2026-07-14;
                    # Feinabnahme Build 399 §4.3 / mc §4.3).
]

# Python-Pakete nur fuer DEV (Tests etc.)
DEV_PACKAGES = [
    "pytest",
    "pytest-asyncio",
]

# Pakete, die auf PyPI NUR als sdist vorliegen (kein Wheel) und rein in Python
# geschrieben sind. Beim Cross-Platform-Download (--platform) erzwingt pip
# --only-binary=:all:, wodurch sdists ausgeschlossen werden — solche Pakete
# fielen sonst STILL aus dem Offline-Paket (Grundregel 1). Fuer sie wird auf der
# Vorbereitungsmaschine via 'pip wheel' ein plattformunabhaengiges
# py3-none-any-Wheel gebaut und in BEIDE Plattform-Verzeichnisse kopiert.
# Beleg: pyeditorjs 1.0.0b0 — PyPI liefert nur sdist, install_requires=[],
#        baut sauber zu py3-none-any. Geprueft 2026-06-24.
SOURCE_ONLY_PURE_PYTHON = [
    "pyeditorjs",
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
            # Build 301: --no-deps ENTFERNT — der vollstaendige Abhaengigkeitsbaum
            # wird mitgeladen (z.B. python-docx -> lxml, typing_extensions),
            # damit die Offline-Installation nicht an fehlenden transitiven
            # Paketen scheitert. Beleg: Projektgespraech 2026-06-24.
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
             # Build 301: --no-deps auch hier entfernt (vollstaendiger Baum).
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


def _build_source_wheels(target_dirs: list[Path], packages: list[str]) -> None:
    """
    Baut fuer rein in Python geschriebene, nur-als-sdist verfuegbare Pakete
    (SOURCE_ONLY_PURE_PYTHON, z.B. pyeditorjs) auf der Vorbereitungsmaschine
    ein plattformunabhaengiges py3-none-any-Wheel und kopiert es in alle
    Ziel-Wheels-Verzeichnisse (win64 + linux64).

    Begruendung: Solche Pakete koennen nicht per Cross-Platform-Download
    (--platform erzwingt --only-binary=:all:) erfasst werden. Ein einmal
    gebautes py3-none-any-Wheel ist plattformunabhaengig und auf der Offline-VM
    OHNE Build-Werkzeuge installierbar.
    Beleg: Projektgespraech 2026-06-24.
    """
    if not packages:
        return

    import shutil
    import tempfile

    print(f"  Source-only-Pakete als Wheel bauen: {', '.join(packages)} …")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "wheel",
             "--no-deps", "--wheel-dir", str(tmp_path)] + packages,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print("WARNUNG: 'pip wheel' fuer Source-Pakete fehlgeschlagen:")
            print(result.stderr[-500:])
            return

        built = list(tmp_path.glob("*.whl"))
        if not built:
            print("WARNUNG: 'pip wheel' erzeugte keine Wheels.")
            return

        for target in target_dirs:
            wheels_dir = target / "wheels"
            wheels_dir.mkdir(parents=True, exist_ok=True)
            for whl in built:
                dest = wheels_dir / whl.name
                shutil.copy2(whl, dest)
                print(f"    {whl.name} -> {dest.parent.name}/ [{_md5(dest)[:8]}...]")


def _build_wheels(skip: bool) -> None:
    """Schritt 2: Python-Wheels fuer win64 und linux64 herunterladen/bauen."""
    _header("Schritt 2: Python-Wheels herunterladen")
    if skip:
        print("  Uebersprungen (--skip-wheels).")
        return

    all_packages = RUNTIME_PACKAGES + DEV_PACKAGES

    # Source-only-Pakete (kein Wheel auf PyPI) aus dem Cross-Platform-Download
    # herausnehmen — sie wuerden den --only-binary-Download sonst abbrechen.
    # Sie werden anschliessend separat als Wheel gebaut.
    binary_packages = [p for p in all_packages if p not in SOURCE_ONLY_PURE_PYTHON]

    print("\n  [win64] …")
    _download_wheels(SETUP_WIN, "win_amd64", binary_packages)

    print("\n  [linux64] …")
    _download_wheels(SETUP_LINUX, "manylinux2014_x86_64", binary_packages)

    # Plattformunabhaengige Source-Pakete (pyeditorjs) bauen und in beide
    # Plattform-Verzeichnisse legen.
    print("\n  [source-only -> win64 + linux64] …")
    _build_source_wheels([SETUP_WIN, SETUP_LINUX], SOURCE_ONLY_PURE_PYTHON)


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
        description="Deployment-Vorbereitung: Bundle + Wheels + Setup-Struktur.",
        epilog=cli_epilog.epilog("prepare_deployment"),
        formatter_class=cli_epilog.HilfeFormat,
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

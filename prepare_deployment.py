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
# Aenderung Build 647 (Vorgang 0329896b): Ein gescheiterter Wheel-Download
#   fuehrt nicht mehr zu Rueckgabewert 0. Neu sind die Vollzaehligkeitspruefung
#   je Zielverzeichnis, die Schlussbilanz mit Namen und die Angabe der
#   erforderlichen Python-Nebenversion in README.txt und Manifest.
#
# Version: v0.8.647 · Build: 647 · 2026-08-01
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

#: DIE PYTHON-NEBENVERSION, FUER DIE GELADEN WIRD.
#:
#: Sie stand bis Build 646 nur als Zeichenkette '314' im pip-Aufruf und
#: NIRGENDS in der Ausgabe. Wer auf der Zielanlage eine andere Nebenversion
#: einsetzt, findet die Raeder nicht - auch dann nicht, wenn die Datei im
#: Verzeichnis liegt - und bekommt 'No matching distribution found'. Er sucht
#: den Fehler dann beim Paket und nicht bei der Version.
#: Beleg: Vorgang 0329896b, gemessen am 2026-07-31 mit
#: 'install.py --target dev --os linux' unter Python 3.13.
ZIEL_PYTHON_VERSION = "314"
ZIEL_PYTHON_KLARTEXT = "3.14"


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


def _download_wheels(target_dir: Path, platform_tag: str,
                     packages: list[str]) -> bool:
    """
    Laedt Python-Wheels fuer eine Zielplattform herunter.
    platform_tag: z.B. 'win_amd64' oder 'manylinux2014_x86_64'

    BUILD 647 (Vorgang 0329896b): Liefert jetzt True/False statt nichts. Der
    Fehlschlag wurde bis Build 646 als 'WARNUNG' gedruckt, danach kehrte die
    Funktion zurueck und der Lauf endete mit 0. Ein Skript, das
    prepare_deployment aufruft, hielt das Auslieferungspaket danach fuer
    fertig. DER BELEG LIEGT IM BESTAND: setup/win64/wheels hatte 13 Dateien,
    setup/linux64/wheels genau EINE - irgendwann ist der Linux-Download
    abgebrochen, das Werkzeug hat 0 gemeldet, und seither lag ein
    unvollstaendiges Offline-Paket im Repository.
    """
    wheels_dir = target_dir / "wheels"
    wheels_dir.mkdir(parents=True, exist_ok=True)

    print(f"  Wheels herunterladen fuer {platform_tag} nach {wheels_dir} …")
    result = subprocess.run(
        [
            sys.executable, "-m", "pip", "download",
            "--dest", str(wheels_dir),
            "--platform", platform_tag,
            "--python-version", ZIEL_PYTHON_VERSION,
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
            print(f"FEHLER: Wheels konnten nicht heruntergeladen werden "
                  f"({platform_tag}):")
            print(result.stderr[-500:])
            return False

    # Heruntergeladene Dateien auflisten
    downloaded = list(wheels_dir.glob("*.whl")) + list(wheels_dir.glob("*.tar.gz"))
    for f in downloaded:
        print(f"    {f.name} [{_md5(f)[:8]}...]")
    return True


def _build_source_wheels(target_dirs: list[Path], packages: list[str]) -> bool:
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
        return True

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
            print("FEHLER: 'pip wheel' fuer Source-Pakete fehlgeschlagen:")
            print(result.stderr[-500:])
            return False

        built = list(tmp_path.glob("*.whl"))
        if not built:
            print("FEHLER: 'pip wheel' erzeugte keine Wheels.")
            return False

        for target in target_dirs:
            wheels_dir = target / "wheels"
            wheels_dir.mkdir(parents=True, exist_ok=True)
            for whl in built:
                dest = wheels_dir / whl.name
                shutil.copy2(whl, dest)
                print(f"    {whl.name} -> {dest.parent.name}/ [{_md5(dest)[:8]}...]")
    return True


def _paketname_normalisiert(name: str) -> str:
    """
    Paketname -> die Form, in der er im Dateinamen eines Rades steht.

    'python-docx' wird zu 'python_docx', 'PyYAML' zu 'pyyaml'. Ohne diese
    Angleichung faende die Vollzaehligkeitspruefung genau die Pakete nicht,
    deren Name einen Bindestrich traegt - und meldete sie faelschlich als
    fehlend.
    """
    return name.strip().lower().replace("-", "_").replace(".", "_")


def _fehlende_raeder(wheels_dir: Path, packages: list[str]) -> list[str]:
    """
    DIE VOLLZAEHLIGKEITSPRUEFUNG (Build 647, Vorgang 0329896b).

    Fuer jedes verlangte Paket: Liegt in diesem Verzeichnis ein Rad, dessen
    Dateiname mit dem Paketnamen beginnt? Geprueft wird der ANFANG, weil der
    Dateiname eines Rades stets '<name>-<version>-...' lautet.

    WARUM ES DIESE PRUEFUNG BRAUCHT, obwohl der Download jetzt einen
    Rueckgabewert hat: Der Download kann TEILWEISE gelingen. pip laedt Paket
    fuer Paket; bricht es beim vierten ab, liegen drei Raeder da und der
    Aufruf meldet einen Fehler - beim naechsten Lauf mit anderer Reihenfolge
    aber vielleicht nicht. Erst diese Pruefung sagt, ob das Paket am Ende
    VOLLSTAENDIG ist. Genau das ist die Frage, die auf der Zielanlage zaehlt.

    WAS SIE NICHT LEISTET (TE4): Sie prueft nicht die transitiven
    Abhaengigkeiten (pillow, charset-normalizer, typing_extensions ...). Die
    kennt nur pip. Ein Rad je verlangtem Paket ist die Untergrenze, nicht der
    Beweis der Lauffaehigkeit - der bleibt 'install.py' auf der Zielanlage.
    """
    if not wheels_dir.is_dir():
        return list(packages)
    # NUR DER NAMENSTEIL WIRD ANGEGLICHEN, NICHT DER GANZE DATEINAME.
    #
    # BEFUND AUS DER EIGENEN GEGENPROBE (LB12, beim Bauen dieser Pruefung):
    # Die erste Fassung hat den GANZEN Dateinamen normalisiert - damit wurde
    # aus 'pytest_asyncio-1.3.0-...' die Zeichenfolge 'pytest_asyncio_1_3_0...',
    # und die Suche nach dem Praefix 'pytest_' traf sie. Die Pruefung haette
    # 'pytest' als vorhanden gemeldet, obwohl nur das Zusatzpaket dalag - sie
    # haette also VOLLZAEHLIGKEIT gemeldet, wo ein Paket fehlt. Eine
    # Vollzaehligkeitspruefung, die sich taeuschen laesst, ist schlimmer als
    # keine.
    #
    # Ein Dateiname hat die Form '<name>-<version>-...'. Der Namensteil ist
    # alles vor dem ERSTEN Bindestrich; er wird angeglichen und auf GLEICHHEIT
    # geprueft, nicht auf einen Anfang.
    vorhanden = {_paketname_normalisiert(f.name.split("-")[0])
                 for f in wheels_dir.iterdir() if f.is_file()}
    return [p for p in packages
            if _paketname_normalisiert(p) not in vorhanden]


def _build_wheels(skip: bool) -> list[str]:
    """
    Schritt 2: Python-Wheels fuer win64 und linux64 herunterladen/bauen.

    Liefert die Liste der BEFUNDE (leer = alles in Ordnung). Sie wird von
    main() ausgewertet und bestimmt den Rueckgabewert des Laufs.
    """
    _header("Schritt 2: Python-Wheels herunterladen")
    befunde: list[str] = []
    if skip:
        print("  Uebersprungen (--skip-wheels).")
        # KEIN BEFUND, ABER AUCH KEINE ZUSAGE: Wer '--skip-wheels' angibt,
        # bekommt kein vollstaendiges Paket zugesichert. Der Hinweis steht
        # deshalb in der Schlussbilanz.
        return befunde

    all_packages = RUNTIME_PACKAGES + DEV_PACKAGES

    # Source-only-Pakete (kein Wheel auf PyPI) aus dem Cross-Platform-Download
    # herausnehmen — sie wuerden den --only-binary-Download sonst abbrechen.
    # Sie werden anschliessend separat als Wheel gebaut.
    binary_packages = [p for p in all_packages if p not in SOURCE_ONLY_PURE_PYTHON]

    print("\n  [win64] …")
    if not _download_wheels(SETUP_WIN, "win_amd64", binary_packages):
        befunde.append("Download fuer win64 fehlgeschlagen")

    print("\n  [linux64] …")
    if not _download_wheels(SETUP_LINUX, "manylinux2014_x86_64", binary_packages):
        befunde.append("Download fuer linux64 fehlgeschlagen")

    # Plattformunabhaengige Source-Pakete (pyeditorjs) bauen und in beide
    # Plattform-Verzeichnisse legen.
    print("\n  [source-only -> win64 + linux64] …")
    if not _build_source_wheels([SETUP_WIN, SETUP_LINUX], SOURCE_ONLY_PURE_PYTHON):
        befunde.append("Bauen der Source-only-Pakete fehlgeschlagen")

    # --- Vollzaehligkeit, je Zielverzeichnis einzeln ----------------------
    _header("Schritt 2b: Vollzaehligkeit der Wheels")
    for setup_dir, name in ((SETUP_WIN, "win64"), (SETUP_LINUX, "linux64")):
        fehlt = _fehlende_raeder(setup_dir / "wheels", all_packages)
        if fehlt:
            print("  [%s] FEHLT: %s" % (name, ", ".join(fehlt)))
            befunde.append("%s: kein Rad fuer %s" % (name, ", ".join(fehlt)))
        else:
            print("  [%s] vollzaehlig: %d von %d Paketen"
                  % (name, len(all_packages), len(all_packages)))
    return befunde


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
            f"\nERFORDERLICHE PYTHON-NEBENVERSION: {ZIEL_PYTHON_KLARTEXT}\n"
            f"  Die Raeder in wheels/ sind fuer cp{ZIEL_PYTHON_VERSION} "
            f"gebaut. Unter einer ANDEREN Nebenversion findet pip sie nicht -\n"
            f"  auch dann nicht, wenn die Datei im Verzeichnis liegt. Die\n"
            f"  Meldung lautet dann 'No matching distribution found' und\n"
            f"  nennt das PAKET, nicht die Version. (Vorgang 0329896b)\n"
            f"\nBaustelle 1 wird ergaenzen:\n"
            f"  firefox/ — Portabler Firefox ESR\n"
            f"  python/  — Portable Python-Laufzeitumgebung\n",
            encoding="utf-8",
        )
        print(f"  {readme}")


def _write_manifest() -> None:
    """Schritt 4: MD5-Manifest aller setup/-Dateien."""
    _header("Schritt 4: MD5-Manifest erstellen")

    # Build 647 (Vorgang 0329896b): Die Zielversion gehoert INS MANIFEST.
    # Wer das Paket auf der Zielanlage auspackt, kann dann nachsehen, statt
    # zu raten - und ein Pruefwerkzeug kann sie gegen die dortige Laufzeit
    # halten.
    manifest = {"created_at": int(time.time()),
                "python_version": ZIEL_PYTHON_KLARTEXT,
                "python_tag": "cp" + ZIEL_PYTHON_VERSION,
                "files": {}}

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


def main() -> int:
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
    befunde = _build_wheels(args.skip_wheels)
    _write_setup_metadata()
    _write_manifest()

    # =====================================================================
    # DIE SCHLUSSBILANZ (Build 647, Vorgang 0329896b).
    #
    # Bis Build 646 endete dieser Lauf IMMER mit "abgeschlossen" und dem
    # Rueckgabewert 0 - auch wenn der Wheel-Download unterwegs gescheitert
    # war. Genau so ist ein Offline-Paket mit EINER von sieben
    # Abhaengigkeiten in den Bestand gekommen und dort liegengeblieben.
    #
    # Jetzt gilt: Ein Befund steht am ENDE (dort, wo man hinsieht), er nennt
    # die Pakete BEIM NAMEN, und der Rueckgabewert ist 1. Ein Skript, das
    # dieses Werkzeug aufruft, kann das auswerten, ohne die Ausgabe zu lesen.
    # =====================================================================
    print("\n" + "=" * 60)
    if befunde:
        print("  BEFUND — die Auslieferung ist NICHT vollstaendig:")
        for b in befunde:
            print("    - %s" % b)
        print("")
        print("  Das Paket ist in diesem Zustand NICHT auslieferungsfaehig.")
        print("  Auf der Zielanlage faellt es sonst erst bei 'install.py' auf,")
        print("  und dort sucht man den Fehler beim falschen Werkzeug.")
        print("=" * 60)
        return 1
    if args.skip_wheels:
        print("  Deployment-Vorbereitung abgeschlossen — OHNE Wheel-Schritt.")
        print("  '--skip-wheels' war gesetzt: ueber die Vollzaehligkeit der")
        print("  Offline-Pakete sagt dieser Lauf NICHTS.")
    else:
        print("  Deployment-Vorbereitung abgeschlossen.")
        print("  Wheels vollzaehlig fuer win64 und linux64 "
              "(Python %s)." % ZIEL_PYTHON_KLARTEXT)
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# =============================================================================
# deployment/build_editor_bundle.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 1: Deployment
# =============================================================================
# Zweck:
#   Baut das Editor.js-Bundle fuer den Offline-Einsatz.
#
#   Schritte:
#   1. npm install aller Editor.js-Plugins in ein temporaeres Verzeichnis
#   2. esbuild bundelt alles zu editor.bundle.js und editor.bundle.css
#   3. Scan aller generierten Dateien auf externe URL-Referenzen
#   4. Patching gefundener externer URLs auf /_forensic/static/editor/
#   5. Kopieren in static/editor/ des Webservers
#   6. MD5-Protokoll aller kopierten Dateien
#
#   Dieses Script laeuft auf einem Rechner MIT Internetzugang.
#   Das Ergebnis (static/editor/) wird dann ohne Netz deployt.
#
# Voraussetzungen:
#   - Node.js >= 18 und npm >= 9
#   - Internetverbindung
#   - Aufruf aus dem aiw_webserver-Verzeichnis ODER mit --output-dir
#
# Aufruf:
#   python deployment/build_editor_bundle.py
#   python deployment/build_editor_bundle.py --output-dir /pfad/zu/static/editor
#   python deployment/build_editor_bundle.py --skip-scan   # URL-Scan ueberspringen
#
# Beleg: AP-E2, Projektgespraech 2026-04-19
# Version: v0.6.044 · Build: 044 · 2026-04-19
# =============================================================================

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

# Editor.js-Plugins die installiert werden.
# Beleg: AP-E1/AP-E3, Projektgespraech 2026-04-19
EDITOR_PACKAGES = [
    "@editorjs/editorjs",
    "@editorjs/header",
    "@editorjs/paragraph",
    "@editorjs/nested-list",
    "@editorjs/table",
    "@cychann/editorjs-quote",
    "@editorjs/simple-image",
    "@editorjs/marker",
    "editorjs-annotation",
    "editorjs-undo",
    "@coolbytes/editorjs-delimiter",
]

# esbuild-Einstiegsdatei (wird temporaer erzeugt)
_ENTRY_TEMPLATE = """\
// editor-entry.js — Auto-generiert von build_editor_bundle.py
// Importiert alle Editor.js-Plugins und exportiert sie global.
import EditorJS from '@editorjs/editorjs';
import Header from '@editorjs/header';
import Paragraph from '@editorjs/paragraph';
import NestedList from '@editorjs/nested-list';
import Table from '@editorjs/table';
import Quote from '@cychann/editorjs-quote';
import SimpleImage from '@editorjs/simple-image';
import Marker from '@editorjs/marker';
import Annotation from 'editorjs-annotation';
import Undo from 'editorjs-undo';
import Delimiter from '@coolbytes/editorjs-delimiter';

// Global exportieren fuer editor.js (AP-E4)
window.EditorJS   = EditorJS;
window.EditorTools = {
    Header, Paragraph, NestedList, Table,
    Quote, SimpleImage, Marker, Annotation,
    Undo, Delimiter,
};
"""

# Muster fuer externe URL-Erkennung im Bundle
_EXTERNAL_URL_PATTERNS = [
    re.compile(r'https?://fonts\.googleapis\.com[^\s\'"]*'),
    re.compile(r'https?://fonts\.gstatic\.com[^\s\'"]*'),
    re.compile(r'https?://cdn\.[^\s\'"]*'),
    re.compile(r'https?://unpkg\.com[^\s\'"]*'),
    re.compile(r'https?://cdn\.jsdelivr\.net[^\s\'"]*'),
]


def _check_node() -> None:
    """Prueft ob node und npm verfuegbar sind."""
    for cmd in (["node", "--version"], ["npm", "--version"]):
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"FEHLER: '{cmd[0]}' nicht gefunden.")
            print("Bitte Node.js >= 18 installieren: https://nodejs.org/")
            sys.exit(1)
    result = subprocess.run(["node", "--version"], capture_output=True, text=True)
    version = result.stdout.strip().lstrip("v")
    major = int(version.split(".")[0])
    if major < 18:
        print(f"FEHLER: Node.js >= 18 benoetigt, gefunden: {version}")
        sys.exit(1)
    print(f"  Node.js {version} — OK")


def _check_esbuild(npm_dir: Path) -> Path:
    """Installiert esbuild lokal falls nicht vorhanden und gibt den Pfad zurueck."""
    esbuild = npm_dir / "node_modules" / ".bin" / "esbuild"
    if not esbuild.exists():
        print("  esbuild installieren …")
        subprocess.run(
            ["npm", "install", "esbuild", "--save-dev"],
            cwd=str(npm_dir), check=True, capture_output=True,
        )
    return esbuild


def _npm_install(work_dir: Path) -> None:
    """Installiert alle Editor.js-Plugins via npm."""
    print(f"  npm install ({len(EDITOR_PACKAGES)} Pakete) …")
    # package.json erzeugen
    pkg = {
        "name": "aiw-editor-bundle",
        "version": "1.0.0",
        "private": True,
        "type": "module",
        "dependencies": {pkg: "latest" for pkg in EDITOR_PACKAGES},
        "devDependencies": {"esbuild": "latest"},
    }
    (work_dir / "package.json").write_text(
        json.dumps(pkg, indent=2), encoding="utf-8"
    )
    result = subprocess.run(
        ["npm", "install"],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("FEHLER bei npm install:")
        print(result.stderr[-2000:])
        sys.exit(1)
    print(f"  npm install abgeschlossen.")


def _write_entry(work_dir: Path) -> Path:
    """Schreibt die esbuild-Einstiegsdatei."""
    entry = work_dir / "editor-entry.js"
    entry.write_text(_ENTRY_TEMPLATE, encoding="utf-8")
    return entry


def _run_esbuild(work_dir: Path, entry: Path, out_js: Path, out_css: Path) -> None:
    """Fuehrt esbuild aus und erzeugt Bundle."""
    esbuild = work_dir / "node_modules" / ".bin" / "esbuild"
    print("  esbuild — Bundle erstellen …")
    result = subprocess.run(
        [
            str(esbuild),
            str(entry),
            f"--bundle",
            f"--outfile={out_js}",
            f"--format=iife",
            f"--platform=browser",
            f"--target=firefox78",   # Firefox ESR Mindestversion
            f"--minify",
            f"--sourcemap",
        ],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("FEHLER bei esbuild:")
        print(result.stderr[-2000:])
        sys.exit(1)
    print(f"  Bundle erzeugt: {out_js.name} ({out_js.stat().st_size // 1024} KB)")


def _scan_external_urls(bundle_js: Path) -> list[str]:
    """Scannt das Bundle auf externe URL-Referenzen."""
    content = bundle_js.read_text(encoding="utf-8", errors="replace")
    found = []
    for pattern in _EXTERNAL_URL_PATTERNS:
        matches = pattern.findall(content)
        found.extend(matches)
    return list(set(found))


def _patch_external_urls(bundle_js: Path, urls: list[str]) -> int:
    """
    Ersetzt externe URLs im Bundle durch lokale Pfade.
    Gibt die Anzahl vorgenommener Ersetzungen zurueck.
    """
    content = bundle_js.read_text(encoding="utf-8", errors="replace")
    count = 0
    for url in urls:
        # Dateiname aus URL extrahieren
        filename = url.rstrip("/").split("/")[-1].split("?")[0]
        if not filename:
            filename = "external-resource"
        local_path = f"/_forensic/static/editor/{filename}"
        new_content = content.replace(url, local_path)
        if new_content != content:
            count += 1
            content = new_content
            print(f"    Patch: {url[:60]}... -> {local_path}")
    if count:
        bundle_js.write_text(content, encoding="utf-8")
    return count


def _md5(path: Path) -> str:
    h = hashlib.md5()
    h.update(path.read_bytes())
    return h.hexdigest()


def _copy_to_output(src_files: list[Path], output_dir: Path) -> dict[str, str]:
    """Kopiert Bundle-Dateien in output_dir und gibt MD5-Dict zurueck."""
    output_dir.mkdir(parents=True, exist_ok=True)
    checksums = {}
    for src in src_files:
        dst = output_dir / src.name
        shutil.copy2(src, dst)
        checksums[src.name] = _md5(dst)
        print(f"  Kopiert: {src.name} ({dst.stat().st_size // 1024} KB) [{checksums[src.name][:8]}...]")
    return checksums


def _write_manifest(output_dir: Path, checksums: dict[str, str]) -> None:
    """Schreibt bundle_manifest.json in output_dir."""
    import time
    manifest = {
        "built_at": int(time.time()),
        "packages": EDITOR_PACKAGES,
        "files": checksums,
    }
    manifest_path = output_dir / "bundle_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Manifest: {manifest_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Editor.js-Bundle fuer Offline-Einsatz bauen (AP-E2)."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Zielverzeichnis fuer das Bundle (Standard: static/editor/ relativ zu diesem Script)",
    )
    parser.add_argument(
        "--skip-scan",
        action="store_true",
        help="URL-Scan und -Patching ueberspringen",
    )
    args = parser.parse_args()

    # Zielverzeichnis bestimmen
    script_dir  = Path(__file__).resolve().parent
    webserver_dir = script_dir.parent
    output_dir = args.output_dir or (webserver_dir / "static" / "editor")

    print("=" * 60)
    print("  build_editor_bundle.py — AP-E2")
    print(f"  Ziel: {output_dir}")
    print("=" * 60)

    # Voraussetzungen pruefen
    print("\n[1/6] Voraussetzungen pruefen …")
    _check_node()

    with tempfile.TemporaryDirectory(prefix="aiw_editor_build_") as tmpdir:
        work_dir = Path(tmpdir)
        out_js   = work_dir / "editor.bundle.js"
        out_css  = work_dir / "editor.bundle.css"

        # npm install
        print("\n[2/6] npm install …")
        _npm_install(work_dir)

        # Einstiegsdatei schreiben
        print("\n[3/6] Bundle-Einstiegsdatei erzeugen …")
        entry = _write_entry(work_dir)

        # esbuild
        print("\n[4/6] esbuild — Bundle erstellen …")
        _run_esbuild(work_dir, entry, out_js, out_css)

        # URL-Scan und Patching
        if not args.skip_scan:
            print("\n[5/6] Externe URLs scannen und patchen …")
            urls = _scan_external_urls(out_js)
            if urls:
                print(f"  {len(urls)} externe URL(s) gefunden — patchen:")
                count = _patch_external_urls(out_js, urls)
                print(f"  {count} Ersetzung(en) vorgenommen.")
            else:
                print("  Keine externen URLs gefunden — kein Patching noetig.")
        else:
            print("\n[5/6] URL-Scan uebersprungen (--skip-scan).")

        # Kopieren und MD5
        print("\n[6/6] Bundle in Zielverzeichnis kopieren …")
        src_files = [f for f in [out_js, out_css, Path(str(out_js) + ".map")]
                     if f.exists()]
        checksums = _copy_to_output(src_files, output_dir)
        _write_manifest(output_dir, checksums)

    print("\n" + "=" * 60)
    print("  Bundle erfolgreich erstellt.")
    print(f"  Dateien in: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()

# =============================================================================
# core/build_info.py
# IT-Forensisches Ermittlungswerkzeug — Build-Information
# =============================================================================
# Zweck:
#   Liest build.json aus dem Projekt-Wurzelverzeichnis und stellt
#   Build-Nummer, Version und Datum als Python-Konstanten bereit.
#
#   Wird von main.py beim Start geladen und in die HTML-Templates injiziert.
#   Stellt ausserdem _log_file_checksums() bereit, das vor dem Server-Start
#   MD5-Prüfsummen aller relevanten Quelldateien ins Log schreibt.
#
# Build 174: Erstimplementierung.
# Beleg: Projektgespräch 2026-05-11
# =============================================================================

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("forensic.core.build_info")

# Verzeichnisse die in der Prüfsummen-Ausgabe berücksichtigt werden
# Relativ zum Projektroot (wo main.py liegt).
CHECKSUM_DIRS = [
    "forensic_api",
    "userinfo",
    "editor",
    "toolbar",
    "data",
    "core",
    "server",
    "static",
]

# Dateiendungen die geprüft werden
CHECKSUM_EXTENSIONS = {".py", ".js", ".css", ".html", ".json", ".sql"}


def _find_build_json(start: Path) -> Optional[Path]:
    """
    Sucht build.json ab start-Verzeichnis aufwärts (max. 3 Ebenen).
    Gibt den Pfad zurück oder None wenn nicht gefunden.
    """
    candidate = start
    for _ in range(4):
        p = candidate / "build.json"
        if p.exists():
            return p
        candidate = candidate.parent
    return None


class BuildInfo:
    """
    Kapselt Build-Nummer, Version und Datum aus build.json.

    Beleg: Projektgespräch 2026-05-11
    """

    def __init__(self, project_root: Optional[Path] = None) -> None:
        if project_root is None:
            project_root = Path(__file__).parent.parent

        build_json = _find_build_json(project_root)
        if build_json is None:
            logger.warning(
                "build.json nicht gefunden (gesucht ab '%s') — "
                "Fallback auf Build 0.",
                project_root,
            )
            self.build   = 0
            self.version = "0.0.0"
            self.date    = "unbekannt"
            self.note    = ""
        else:
            try:
                data = json.loads(build_json.read_text(encoding="utf-8"))
                self.build   = int(data.get("build",   0))
                self.version = str(data.get("version", "0.0.0"))
                self.date    = str(data.get("date",    ""))
                self.note    = str(data.get("note",    ""))
                logger.info(
                    "Build-Info geladen: v%s Build %d (%s) — %s",
                    self.version, self.build, self.date, build_json,
                )
            except Exception as exc:
                logger.error("build.json konnte nicht gelesen werden: %s", exc)
                self.build   = 0
                self.version = "0.0.0"
                self.date    = "unbekannt"
                self.note    = ""

    def as_dict(self) -> dict:
        return {
            "build":   self.build,
            "version": self.version,
            "date":    self.date,
            "note":    self.note,
        }


def log_file_checksums(project_root: Path) -> None:
    """
    Schreibt MD5-Prüfsummen aller relevanten Quelldateien ins Log.

    Wird in main.py aufgerufen bevor der Server den Port öffnet.
    Gibt für jede Datei eine Zeile aus:
        MD5  <relativerPfad>

    Beleg: Projektgespräch 2026-05-11
    """
    logger.info("=" * 70)
    logger.info("Datei-Prüfsummen (MD5) — relevante Verzeichnisse:")
    logger.info("=" * 70)

    total = 0
    for dirname in CHECKSUM_DIRS:
        dirpath = project_root / dirname
        if not dirpath.exists():
            logger.debug("  [nicht vorhanden] %s/", dirname)
            continue

        files = sorted(
            p for p in dirpath.rglob("*")
            if p.is_file()
            and p.suffix in CHECKSUM_EXTENSIONS
            and "__pycache__" not in p.parts
        )

        if not files:
            logger.debug("  [leer] %s/", dirname)
            continue

        logger.info("  %s/", dirname)
        for filepath in files:
            try:
                digest = hashlib.md5(filepath.read_bytes()).hexdigest()
                rel    = filepath.relative_to(project_root)
                logger.info("    %s  %s", digest, rel)
                total += 1
            except Exception as exc:
                logger.warning(
                    "    [FEHLER bei MD5 von %s]: %s",
                    filepath.relative_to(project_root), exc,
                )

    # build.json selbst auch prüfen
    build_json = project_root / "build.json"
    if build_json.exists():
        digest = hashlib.md5(build_json.read_bytes()).hexdigest()
        logger.info("  %s  build.json", digest)
        total += 1

    logger.info("=" * 70)
    logger.info("Prüfsummen ausgegeben: %d Dateien", total)
    logger.info("=" * 70)

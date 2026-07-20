# =============================================================================
# management/distribution/lkae_dist.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: LKAe-Distribution (AP-2G)
# =============================================================================
# Zweck (Idee 27, Teil 2 — Paketbau):
#   Baut ein SELF-CONTAINED LKAe-DEMO-PAKET (NICHT PROD) in ein SEPARATES
#   Zielverzeichnis: Laufzeit-Code + synthetische Demo-DB + Demo-config.yaml +
#   Startskripte + README + (optional) Dockerfile, dazu ein manifest.json mit
#   SHA-256 je Datei und Freigabe-Vermerk. Das Paket ist SELBST-PRUEFBAR
#   (verify()), Muster export/staging.py.
#
# SCHUTZMECHANISMEN (default-deny; Grundregel 1 — nichts still):
#   * FREIGABE PFLICHT: ohne Freigabe-Vermerk kein Bau (die "abhaengig: Freigabe"
#     der Idee). Der Vermerk landet im Manifest (Wer/Az).
#   * NICHT PROD: das Ziel darf keine PROD-Datenablage ueberlappen (weder darin
#     liegen noch eine enthalten) und muss leer/neu sein. Es gibt keinen Pfad,
#     auf dem echter Fallinhalt in das Paket gelangt — die Demo-DB ist rein
#     synthetisch (demo_seed).
#   * Interne Planungsdokumente (*.md) werden NICHT mitgepackt.
#
# Version: v0.7.466 · Build: 466 · 2026-07-20
# =============================================================================

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from management.distribution import demo_seed
from management.export.checksum import (
    content_sha256_bytes,
    json_payload_sha256,
)

logger = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.json"
MANIFEST_SCHEMA = "aiw.lkae_demo.manifest/1"

#: Nur diese Laufzeit-Bestandteile werden ins Paket kopiert (Whitelist).
RUNTIME_ITEMS = ("management", "core", "db", "management.py", "requirements.txt")

#: Verzeichnisnamen, die beim Kopieren uebersprungen werden.
_SKIP_DIRS = frozenset(("__pycache__", ".git", ".pytest_cache", "node_modules",
                        ".mypy_cache"))
#: Dateiendungen, die NICHT ins Paket gehoeren (Bytecode + interne Planungsdocs).
_SKIP_SUFFIX = (".pyc", ".pyo", ".md")

_DEMO_CONFIG = """# AIW — LKAe-DEMO (NICHT PROD). Nur synthetische Demo-Daten.
paths:
  coordinator_db: "./data/coordinator.db"
  evidence_db_dir: "./data/evidence/"
  forensic_db_dir: "./data/forensic/"
  assets_db_dir: "./data/assets/"
  templates_db: "./data/templates.db"
  default_db: "./data/default.db"
"""

_START_SH = """#!/bin/sh
# AIW LKAe-DEMO — NICHT PROD. Startet den Management-Server auf der Demo-DB.
python management.py --coordinator-db ./data/coordinator.db "$@"
"""

_START_BAT = """@echo off
REM AIW LKAe-DEMO — NICHT PROD. Startet den Management-Server auf der Demo-DB.
python management.py --coordinator-db ./data/coordinator.db %*
"""

_DOCKERFILE = """# AIW LKAe-DEMO — NICHT PROD. Nur zu Vorfuehrzwecken (separate Umgebung).
FROM python:3.14-slim
WORKDIR /aiw
COPY . /aiw
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "management.py", "--coordinator-db", "./data/coordinator.db"]
"""

_README = """# AIW — LKAe-Demo-Paket (NICHT PROD)

Dieses Paket dient AUSSCHLIESSLICH der Vorfuehrung des IT-forensischen
Ermittlungswerkzeugs. Es enthaelt **ausschliesslich synthetische Demo-Daten**
(erfundene Personen, Faelle und Vorgaenge) — **keinen realen Fallinhalt**.

## Start (lokal)
    ./start.sh        # Linux/macOS
    start.bat         # Windows
oder per Container:
    docker build -t aiw-demo .
    docker run --rm -it aiw-demo

## Selbstpruefung
Das Paket ist ueber `manifest.json` (SHA-256 je Datei) selbst-pruefbar:
    python -m management.distribution.lkae_admin verify --target .

## Hinweis
NICHT fuer den Produktivbetrieb. Keine echten Ermittlungsdaten einspielen.
"""


class LkaeDistributionError(Exception):
    """Bau-/Pruefbedingung verletzt (Freigabe fehlt, PROD-Ueberlappung, ...)."""


# ------------------------------------------------------------------- Helfer
def _repo_root() -> Path:
    # management/distribution/lkae_dist.py -> repo-Wurzel = 3 Ebenen hoch.
    return Path(__file__).resolve().parents[2]


def _overlaps(a: Path, b: Path) -> bool:
    """True, wenn a und b identisch sind oder eines im anderen liegt."""
    a = a.resolve()
    b = b.resolve()
    if a == b:
        return True
    return a in b.parents or b in a.parents


def _copy_ok(rel_parts, name: str) -> bool:
    if any(part in _SKIP_DIRS for part in rel_parts):
        return False
    if name.lower().endswith(_SKIP_SUFFIX):
        return False
    return True


def _write_text(path: Path, text: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if executable:
        os.chmod(path, 0o755)


def _sha256_file(path: Path) -> str:
    return content_sha256_bytes(path.read_bytes())


def _walk_files(root: Path):
    """Alle Dateien unter root, rel-Pfad mit '/'-Trennern (sortiert stabil)."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            absf = Path(dirpath) / fn
            rel = absf.relative_to(root).as_posix()
            out.append((rel, absf))
    return out


# --------------------------------------------------------------------- build
def build(
    *, target_dir: str, freigabe: str, actor: Optional[str] = None,
    source_root: Optional[str] = None,
    prod_data_paths: Optional[List[str]] = None,
    include_docker: bool = True, now: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Baut das Demo-Paket. -> Zusammenfassung. Wirft LkaeDistributionError bei
    verletzter Vorbedingung (nichts wird still uebersprungen).
    """
    if not (freigabe or "").strip():
        raise LkaeDistributionError(
            "Freigabe-Vermerk ist Pflicht: eine Distribution ist ein bewusster, "
            "belegter Akt (Idee 27 — abhaengig: Freigabe).")

    src = Path(source_root).resolve() if source_root else _repo_root()
    target = Path(target_dir).resolve()

    # PROD-Ueberlappung verweigern (NICHT PROD).
    for pp in (prod_data_paths or []):
        if not pp:
            continue
        if _overlaps(target, Path(pp)):
            raise LkaeDistributionError(
                "Ziel '%s' ueberlappt eine PROD-Datenablage ('%s') — abgewiesen "
                "(NICHT PROD)." % (target, pp))

    if target.exists() and any(target.iterdir()):
        raise LkaeDistributionError(
            "Ziel '%s' ist nicht leer — Demo-Paket nur in ein frisches "
            "Verzeichnis." % target)
    target.mkdir(parents=True, exist_ok=True)

    now = int(time.time()) if now is None else int(now)

    # --- 1) Laufzeit-Code kopieren (Whitelist, ohne *.md/*.pyc/__pycache__) --
    for item in RUNTIME_ITEMS:
        srcitem = src / item
        if not srcitem.exists():
            logger.warning("Distribution: '%s' fehlt in %s — uebersprungen.",
                           item, src)
            continue
        if srcitem.is_file():
            if _copy_ok((), srcitem.name):
                dst = target / item
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(srcitem, dst)
            continue
        for rel, absf in _walk_files(srcitem):
            rel_parts = Path(rel).parts
            if not _copy_ok(rel_parts, absf.name):
                continue
            dst = target / item / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(absf, dst)

    # --- 2) Demo-Scaffolding schreiben ---------------------------------------
    _write_text(target / "config.yaml", _DEMO_CONFIG)
    _write_text(target / "start.sh", _START_SH, executable=True)
    _write_text(target / "start.bat", _START_BAT)
    _write_text(target / "README_DEMO.md", _README)
    if include_docker:
        _write_text(target / "Dockerfile", _DOCKERFILE)

    # --- 3) Synthetische Demo-DB ---------------------------------------------
    seed_summary = demo_seed.seed(str(target / "data" / "coordinator.db"))

    # --- 4) Manifest (SHA-256 je Datei, ohne das Manifest selbst) ------------
    build_info = _read_build_info(src)
    files: Dict[str, str] = {}
    for rel, absf in _walk_files(target):
        if rel == MANIFEST_NAME:
            continue
        files[rel] = _sha256_file(absf)

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "is_demo": True,
        "marker": demo_seed.DEMO_MARKER,
        "generated_at": now,
        "freigabe": {"vermerk": freigabe.strip(), "actor": actor},
        "build": build_info.get("build"),
        "version": build_info.get("version"),
        "seed_summary": seed_summary,
        "file_count": len(files),
        "files": files,
        "manifest_digest": json_payload_sha256(files),
    }
    (target / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8")

    logger.info("LKAe-Demo-Paket gebaut: %s (%d Dateien).", target, len(files))
    return {
        "target": str(target), "file_count": len(files),
        "manifest_digest": manifest["manifest_digest"],
        "seed_summary": seed_summary,
    }


def _read_build_info(src: Path) -> Dict[str, Any]:
    bj = src / "build.json"
    if not bj.exists():
        return {}
    try:
        return json.loads(bj.read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover
        return {}


# -------------------------------------------------------------------- verify
def verify(target_dir: str) -> Dict[str, Any]:
    """
    Rechnet jede Datei gegen ihre Manifest-Pruefsumme nach. Erkennt Aenderung,
    Fehlen und Ergaenzung. -> {ok, mismatch[], missing[], extra[], file_count}.
    """
    target = Path(target_dir).resolve()
    mpath = target / MANIFEST_NAME
    if not mpath.exists():
        raise LkaeDistributionError("Kein manifest.json in %s." % target)
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    recorded: Dict[str, str] = manifest.get("files", {})

    mismatch: List[str] = []
    missing: List[str] = []
    for rel, digest in recorded.items():
        f = target / rel
        if not f.exists():
            missing.append(rel)
            continue
        if _sha256_file(f) != digest:
            mismatch.append(rel)

    present = {rel for rel, _ in _walk_files(target) if rel != MANIFEST_NAME}
    extra = sorted(present - set(recorded.keys()))

    ok = not mismatch and not missing and not extra
    return {"ok": ok, "mismatch": sorted(mismatch), "missing": sorted(missing),
            "extra": extra, "file_count": len(recorded)}

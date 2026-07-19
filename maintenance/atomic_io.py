# =============================================================================
# maintenance/atomic_io.py
# IT-Forensisches Ermittlungswerkzeug — Wartungsmodus (Build 435, Fundament)
# =============================================================================
# Zweck:
#   Atomares Schreiben und robustes Lesen der JSON-Steuerdateien des
#   Wartungsmodus, plus kleine Validierungshelfer.
#
# Intention / belegte Ueberlegungen:
#   * ATOMAR: Ein Poller darf niemals ein halb geschriebenes window.json sehen.
#     Deshalb wird in eine Temp-Datei IM SELBEN Verzeichnis geschrieben, geflusht,
#     fsync'ed und per os.replace() atomar an die Zielposition gehoben. os.replace
#     ist auf demselben Dateisystem atomar (auch auf Windows/NTFS, auch ueber
#     denselben UNC-Share). Ein Temp-Rest wird im Fehlerfall entfernt.
#   * ASCII-ONLY: json.dump(ensure_ascii=True) — konsistent mit build.json; keine
#     Codierungsueberraschungen ueber Plattformen/Shares hinweg.
#   * LESEN: Fehlt die Datei -> None (der Normalfall 'kein Fenster/keine ACK').
#     Ist sie vorhanden, aber unlesbar/kaputt -> MaintenanceProtocolError (laut,
#     nicht still; Grundregel 1).
#
# Abhaengigkeiten: json, os, tempfile, time, pathlib — reine Stdlib.
# Version: v0.7.435 · Build: 435 · 2026-07-19
# =============================================================================

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from maintenance.errors import MaintenanceProtocolError


def jetzt_epoch() -> int:
    """Aktuelle Zeit in ganzen Sekunden seit Epoch (stabil, plattformneutral)."""
    return int(time.time())


def schreibe_json_atomar(pfad: Path, daten: dict) -> None:
    """
    Schreibt 'daten' atomar als ASCII-JSON nach 'pfad'.

    Das Zielverzeichnis wird bei Bedarf angelegt. Es wird zuerst in eine
    Temp-Datei im selben Verzeichnis geschrieben und dann per os.replace()
    umbenannt — so entsteht nie ein teilweise geschriebenes Ziel.
    """
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(pfad.parent), prefix=".tmp_",
                               suffix="_" + pfad.name)
    try:
        with os.fdopen(fd, "w", encoding="ascii", newline="\n") as fh:
            json.dump(daten, fh, ensure_ascii=True, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, str(pfad))   # atomar
        tmp = None
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def lies_json(pfad: Path) -> Optional[dict]:
    """
    Liest eine JSON-Steuerdatei.

    Returns:
        dict, wenn vorhanden und gueltig.
        None, wenn die Datei NICHT existiert (Normalfall).
    Raises:
        MaintenanceProtocolError, wenn die Datei existiert, aber nicht als
        JSON-Objekt lesbar ist (laut melden, nicht still uebergehen).
    """
    pfad = Path(pfad)
    if not pfad.exists():
        return None
    try:
        text = pfad.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as exc:
        raise MaintenanceProtocolError(
            f"Steuerdatei nicht lesbar: {pfad} ({exc})") from exc
    try:
        d = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MaintenanceProtocolError(
            f"Steuerdatei kein gueltiges JSON: {pfad} ({exc})") from exc
    if not isinstance(d, dict):
        raise MaintenanceProtocolError(
            f"Steuerdatei ist kein JSON-Objekt: {pfad}")
    return d


def erwarte(d: dict, key: str) -> Any:
    """Liefert d[key] oder wirft MaintenanceProtocolError, wenn es fehlt."""
    if key not in d:
        raise MaintenanceProtocolError(f"Pflichtfeld fehlt: '{key}' in {d!r}")
    return d[key]

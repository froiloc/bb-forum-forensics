# =============================================================================
# maintenance/cli_support.py
# IT-Forensisches Ermittlungswerkzeug — Wartungsmodus (Build 438, Werkzeuge)
# =============================================================================
# Zweck:
#   Gemeinsame, reine Helfer fuer die Wartungs-Werkzeuge (tools/maintenance.py,
#   tools/maintenance_kill.py). Bewusst OHNE Config-/Server-Kopplung, damit sie
#   vollstaendig testbar bleiben.
#
# Enthaelt:
#   * ziel_zu_pfad / ziel_pfade — bildet Fenster-Ziele ('coordinator',
#     'evidence:1488', 'all') auf konkrete DB-Dateien ab.
#   * exklusiv_pruefen — DER Beweis der Ruhigstellung: Versuch, einen
#     EXCLUSIVE-Lock auf die Ziel-DB zu erhalten (Messen, nicht rechnen). Gelingt
#     das, haelt niemand mehr eine Sperre.
#   * quiesce_status — klassifiziert die lebenden Server anhand Praesenz + ACK.
#
# Version: v0.7.438 · Build: 438 · 2026-07-19
# =============================================================================

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from maintenance.ack_file import AckFile
from maintenance.atomic_io import jetzt_epoch
from maintenance.paths import MaintenancePaths
from maintenance.presence_beacon import PresenceBeacon

# Nutzerspezifische DBs liegen in Unterverzeichnissen; geteilte DBs top-level.
_UNTERVERZEICHNIS = {"evidence": "evidence", "forensic": "forensic",
                     "assets": "assets"}


def ziel_zu_pfad(data_dir, token: str) -> Optional[Path]:
    """
    Bildet ein Fenster-Ziel auf eine DB-Datei ab.
      'coordinator'   -> data_dir/coordinator.db
      'evidence:1488' -> data_dir/evidence/evidence_1488.db
      'templates'     -> data_dir/templates.db
    'all' wird hier NICHT aufgeloest (siehe ziel_pfade).
    """
    data_dir = Path(data_dir)
    token = str(token)
    if token == "all":
        return None
    if ":" in token:
        name, uid = token.split(":", 1)
        sub = _UNTERVERZEICHNIS.get(name)
        fname = f"{name}_{uid}.db"
        return (data_dir / sub / fname) if sub else (data_dir / fname)
    return data_dir / f"{token}.db"


def ziel_pfade(data_dir, ziel) -> list:
    """
    Liefert die konkreten DB-Pfade fuer eine Ziel-Liste. 'all' wird auf die
    geteilten Top-Level-DBs (data_dir/*.db) abgebildet — die per-Nutzer-DBs in
    Unterverzeichnissen werden bei 'all' bewusst NICHT einzeln gesperrt.
    """
    data_dir = Path(data_dir)
    if "all" in ziel:
        return sorted(data_dir.glob("*.db"))
    pfade = []
    for token in ziel:
        p = ziel_zu_pfad(data_dir, token)
        if p is not None:
            pfade.append(p)
    return pfade


def exklusiv_pruefen(db_path, timeout_s: float = 2.0) -> tuple:
    """
    Beweist die Ruhigstellung: versucht, einen EXCLUSIVE-Lock zu erhalten.

    Returns (ok, grund):
      ok=True  -> exklusiv erhalten (niemand haelt mehr eine Sperre) ODER Datei
                  nicht vorhanden ODER read-only/versiegelt (kein Schreiber).
      ok=False -> 'database is locked' (noch von jemandem gehalten) oder ein
                  anderer Pruefungsfehler.
    """
    p = Path(db_path)
    if not p.exists():
        return (True, "Datei nicht vorhanden — nichts zu sperren")
    con = None
    try:
        con = sqlite3.connect(str(p), timeout=timeout_s)
        con.execute("BEGIN EXCLUSIVE")
        con.execute("ROLLBACK")
        return (True, "exklusiv erhalten")
    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        if "locked" in msg or "busy" in msg:
            return (False, "database is locked — noch von jemandem gehalten")
        if "readonly" in msg or "read-only" in msg:
            return (True, "read-only (versiegelt) — kein Schreiber vorhanden")
        return (False, f"nicht pruefbar: {exc}")
    except sqlite3.Error as exc:
        return (False, f"nicht pruefbar: {exc}")
    finally:
        if con is not None:
            try:
                con.close()
            except sqlite3.Error:
                pass


def quiesce_status(paths: MaintenancePaths, window_id: str, stale_s: int,
                   jetzt: Optional[int] = None) -> dict:
    """
    Klassifiziert alle lebenden Server anhand Praesenz + ACK des Fensters:
      gequiesct : hat eine ACK zu diesem Fenster geschrieben
      offen     : lebt (frisches Beacon), aber noch KEINE ACK
      tot       : Beacon veraltet -> vermutlich tot, unbestaetigt (GR1)
    'fehler' sammelt kaputte Steuerdateien (werden gemeldet, nicht still).
    """
    fehler: list = []
    beacons = PresenceBeacon.alle_laden(paths, fehler=fehler)
    ack_keys = {(a.host, a.pid, a.role)
                for a in AckFile.fuer_fenster(paths, window_id, fehler=fehler)}
    now = jetzt if jetzt is not None else jetzt_epoch()

    gequiesct, offen, tot = [], [], []
    for b in beacons:
        key = (b.host, b.pid, b.role)
        if key in ack_keys:
            gequiesct.append(b)
        elif b.ist_veraltet(stale_s, now):
            tot.append(b)
        else:
            offen.append(b)
    return {"gequiesct": gequiesct, "offen": offen, "tot": tot, "fehler": fehler}
